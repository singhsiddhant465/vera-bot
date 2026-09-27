"""The engine facade the API talks to.

Holds the two stores and turns raw endpoint payloads into decisions. Kept free
of FastAPI types so it can be unit-tested directly.
"""
from __future__ import annotations

import time
from typing import Any, Optional

from ..config import ReplyAction, SETTINGS
from .compose import Composed, compose
from .normalize import MerchantView, TriggerView
from .reply import classify_reply
from .store import ContextStore, ConversationState


class VeraEngine:
    def __init__(self) -> None:
        self.contexts = ContextStore()
        self.state = ConversationState()
        self._start = time.time()

    # --- /v1/context -------------------------------------------------------
    def push_context(self, scope: str, context_id: str, version: int,
                     payload: dict[str, Any], delivered_at: Optional[str]) -> dict[str, Any]:
        return self.contexts.put(scope, context_id, version, payload, delivered_at)

    # --- /v1/healthz -------------------------------------------------------
    def healthz(self) -> dict[str, Any]:
        return {
            "status": "ok",
            "uptime_seconds": int(time.time() - self._start),
            "contexts_loaded": self.contexts.counts(),
        }

    # --- /v1/metadata ------------------------------------------------------
    def metadata(self) -> dict[str, Any]:
        s = SETTINGS
        return {
            "team_name": s.team_name,
            "team_members": list(s.team_members),
            "model": s.model,
            "approach": s.approach,
            "contact_email": s.contact_email,
            "version": s.version,
            "submitted_at": s.submitted_at,
        }

    # --- /v1/tick ----------------------------------------------------------
    def tick(self, now: str, available_triggers: list[str]) -> dict[str, Any]:
        self.state.next_tick()
        actions: list[dict[str, Any]] = []
        seen_pairs: set[tuple[Optional[str], str]] = set()

        for trg_id in available_triggers or []:
            if len(actions) >= SETTINGS.max_actions_per_tick:
                break
            trigger = self.contexts.get("trigger", trg_id)
            if not trigger:
                continue
            tv = TriggerView(trigger)
            merchant_id = tv.merchant_id
            merchant = self.contexts.get("merchant", merchant_id)
            if not merchant:
                continue
            category_slug = MerchantView(merchant).category_slug
            category = self.contexts.get("category", category_slug)
            if not category:
                continue
            customer = self.contexts.get("customer", tv.customer_id) if tv.customer_id else None

            composed = compose(category, merchant, trigger, customer)
            if not composed.should_send:
                continue
            if self.state.already_sent(composed.suppression_key, SETTINGS.resend_window_ticks):
                continue
            pair = (composed.merchant_id, composed.conversation_id)
            if pair in seen_pairs:
                continue
            seen_pairs.add(pair)

            self.state.mark_sent(composed.suppression_key)
            self.state.record_bot(composed.conversation_id, composed.body)
            actions.append(_build_action(composed, tv))

        return {"actions": actions}

    # --- /v1/reply ---------------------------------------------------------
    def reply(self, conversation_id: str, merchant_id: Optional[str],
              from_role: str, message: str) -> dict[str, Any]:
        conv = self.state.record_inbound(conversation_id, from_role, message, merchant_id)
        decision = classify_reply(message, conv)

        if decision.action == ReplyAction.SEND:
            self.state.record_bot(conversation_id, decision.body)
            return {"action": ReplyAction.SEND, "body": decision.body,
                    "cta": decision.cta, "rationale": decision.rationale}
        if decision.action == ReplyAction.WAIT:
            return {"action": ReplyAction.WAIT,
                    "wait_seconds": decision.wait_seconds or SETTINGS.default_wait_seconds,
                    "rationale": decision.rationale}
        # end
        self.state.get_conv(conversation_id).ended = True
        return {"action": ReplyAction.END, "rationale": decision.rationale}

    # --- housekeeping ------------------------------------------------------
    def teardown(self) -> dict[str, Any]:
        self.contexts.clear()
        self.state.clear()
        return {"wiped": True}


def _template_name(composed: Composed) -> str:
    prefix = "mx_onbehalf" if composed.send_as == "merchant_on_behalf" else "vera"
    return f"{prefix}_{composed.kind}_v1"


def _build_action(composed: Composed, tv: TriggerView) -> dict[str, Any]:
    # First outbound uses a template shape (WhatsApp session rule). Params are a
    # small deterministic set the harness can map to {{1}}/{{2}}.
    primary_fact = ""
    for k in ("top_item_id", "match", "festival", "theme", "competitor_name",
              "molecule", "intent_topic", "due_date"):
        v = tv.p(k)
        if v:
            primary_fact = str(v)
            break
    return {
        "conversation_id": composed.conversation_id,
        "merchant_id": composed.merchant_id,
        "customer_id": composed.customer_id,
        "send_as": composed.send_as,
        "trigger_id": composed.trigger_id,
        "template_name": _template_name(composed),
        "template_params": [composed.merchant_id or "", composed.kind, primary_fact],
        "body": composed.body,
        "cta": composed.cta,
        "suppression_key": composed.suppression_key,
        "rationale": composed.rationale,
    }
