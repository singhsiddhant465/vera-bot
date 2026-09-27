"""In-memory persistence.

Two stores, both process-local (the testing brief permits in-memory as long as
the process isn't restarted mid-test):

* ``ContextStore`` — versioned, idempotent context by ``(scope, context_id)``.
* ``ConversationState`` — per-conversation turn log + a set of suppression keys
  already sent, so the bot never repeats itself and de-dupes across ticks.

A single ``threading.Lock`` guards mutations; FastAPI may serve requests
concurrently and the harness fires up to 10 req/s.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any, Optional

from .determinism import stable_hash


@dataclass
class StoredContext:
    scope: str
    context_id: str
    version: int
    payload: dict[str, Any]
    delivered_at: Optional[str]
    ack_id: str


class ContextStore:
    """Idempotent, version-aware store.

    Semantics (testing brief §2.1):
      * new id                    -> store,  accepted=True
      * incoming.version >  stored -> replace, accepted=True (atomic)
      * incoming.version == stored -> no-op,  accepted=True (idempotent re-post)
      * incoming.version <  stored -> reject, accepted=False, reason=stale_version
    """

    def __init__(self) -> None:
        self._data: dict[tuple[str, str], StoredContext] = {}
        self._lock = threading.Lock()

    def put(self, scope: str, context_id: str, version: int,
            payload: dict[str, Any], delivered_at: Optional[str]) -> dict[str, Any]:
        ack_id = "ack_" + stable_hash(scope, context_id, version, length=10)
        with self._lock:
            cur = self._data.get((scope, context_id))
            if cur is not None and version < cur.version:
                return {"accepted": False, "reason": "stale_version",
                        "current_version": cur.version}
            if cur is not None and version == cur.version:
                # Idempotent: leave stored state untouched, ack the existing one.
                return {"accepted": True, "ack_id": cur.ack_id,
                        "stored_at": _stored_at(delivered_at)}
            self._data[(scope, context_id)] = StoredContext(
                scope, context_id, version, payload or {}, delivered_at, ack_id)
            return {"accepted": True, "ack_id": ack_id,
                    "stored_at": _stored_at(delivered_at)}

    def get(self, scope: str, context_id: Optional[str]) -> Optional[dict[str, Any]]:
        if context_id is None:
            return None
        with self._lock:
            sc = self._data.get((scope, context_id))
            return sc.payload if sc else None

    def counts(self) -> dict[str, int]:
        counts = {"category": 0, "merchant": 0, "customer": 0, "trigger": 0}
        with self._lock:
            for (scope, _), _sc in self._data.items():
                counts[scope] = counts.get(scope, 0) + 1
        return counts

    def clear(self) -> None:
        with self._lock:
            self._data.clear()


def _stored_at(delivered_at: Optional[str]) -> str:
    """Echo ``delivered_at`` when present (keeps the ack deterministic for tests);
    fall back to wall-clock only when the caller supplied nothing."""
    if delivered_at:
        return delivered_at
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


@dataclass
class Conversation:
    conversation_id: str
    merchant_id: Optional[str] = None
    customer_id: Optional[str] = None
    turns: list[dict[str, Any]] = field(default_factory=list)
    last_bot_body: Optional[str] = None
    ended: bool = False


class ConversationState:
    def __init__(self) -> None:
        self._convs: dict[str, Conversation] = {}
        self._sent_keys: dict[str, int] = {}   # suppression_key -> tick index first sent
        self._tick_index = 0
        self._lock = threading.Lock()

    # --- suppression bookkeeping (used by /tick) ---------------------------
    def next_tick(self) -> int:
        with self._lock:
            self._tick_index += 1
            return self._tick_index

    def already_sent(self, suppression_key: str, window_ticks: int) -> bool:
        if not suppression_key:
            return False
        with self._lock:
            first = self._sent_keys.get(suppression_key)
            if first is None:
                return False
            return (self._tick_index - first) < window_ticks

    def mark_sent(self, suppression_key: str) -> None:
        if not suppression_key:
            return
        with self._lock:
            self._sent_keys.setdefault(suppression_key, self._tick_index)

    # --- conversation log (used by /reply) ---------------------------------
    def get_conv(self, conversation_id: str, merchant_id: Optional[str] = None,
                 customer_id: Optional[str] = None) -> Conversation:
        with self._lock:
            conv = self._convs.get(conversation_id)
            if conv is None:
                conv = Conversation(conversation_id, merchant_id, customer_id)
                self._convs[conversation_id] = conv
            return conv

    def record_inbound(self, conversation_id: str, role: str, message: str,
                       merchant_id: Optional[str] = None) -> Conversation:
        conv = self.get_conv(conversation_id, merchant_id)
        with self._lock:
            conv.turns.append({"from": role, "body": message})
            return conv

    def record_bot(self, conversation_id: str, body: Optional[str]) -> None:
        with self._lock:
            conv = self._convs.get(conversation_id)
            if conv is not None:
                conv.turns.append({"from": "bot", "body": body})
                if body:
                    conv.last_bot_body = body

    def clear(self) -> None:
        with self._lock:
            self._convs.clear()
            self._sent_keys.clear()
            self._tick_index = 0
