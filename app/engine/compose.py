"""The composition core.

``compose()`` is the function the brief asks for. It wires the four context
views into the right ``trigger.kind`` handler and attaches the deterministic
suppression key and conversation id. The public dict form matches the required
contract exactly: ``body, cta, send_as, suppression_key, rationale``.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from ..config import SETTINGS, SendAs
from .determinism import stable_hash
from .handlers import Draft, get_handler
from .normalize import CategoryView, CustomerView, MerchantView, TriggerView
from .suppression import build_suppression_key


@dataclass
class Composed:
    body: str
    cta: str
    send_as: str
    suppression_key: str
    rationale: str
    # engine-internal (not part of the 5-field contract, used by /tick)
    conversation_id: str = ""
    should_send: bool = True
    suppress_reason: Optional[str] = None
    levers: list[str] = field(default_factory=list)
    kind: str = "unknown"
    trigger_id: Optional[str] = None
    merchant_id: Optional[str] = None
    customer_id: Optional[str] = None

    def to_contract(self) -> dict[str, Any]:
        return {
            "body": self.body,
            "cta": self.cta,
            "send_as": self.send_as,
            "suppression_key": self.suppression_key,
            "rationale": self.rationale,
        }


def _conversation_id(merchant_id: Optional[str], customer_id: Optional[str],
                     trigger_id: Optional[str], kind: str) -> str:
    base = merchant_id or "m"
    if customer_id:
        base += f"_{customer_id}"
    tail = trigger_id or kind
    # short stable suffix keeps ids decodable but unique
    return f"conv_{base}_{stable_hash(tail, length=8)}"


def compose(category: dict, merchant: dict, trigger: dict,
            customer: Optional[dict] = None) -> Composed:
    """Compose the next message for a (category, merchant, trigger, customer?) tuple.

    Deterministic: identical inputs always yield an identical ``Composed``.
    """
    m = MerchantView(merchant)
    c = CategoryView(category)
    t = TriggerView(trigger)
    cust = CustomerView(customer)

    draft: Draft = get_handler(t.kind)(m, c, t, cust)

    # Optional LLM rephrasing (off by default). Only rewrites wording under a
    # fact whitelist; never changes the action, CTA, send_as or facts. Any
    # failure falls back to the deterministic body.
    body = draft.body
    if SETTINGS.llm_enhance:
        try:
            from .enhancer import enhance  # local import: optional dependency path
            body = enhance(draft, m, c, t, cust) or draft.body
        except Exception:
            body = draft.body

    supp = build_suppression_key(t, m, draft.send_as)
    conv_id = _conversation_id(m.merchant_id or t.merchant_id, t.customer_id,
                               t.id, t.kind)

    return Composed(
        body=body,
        cta=draft.cta,
        send_as=draft.send_as,
        suppression_key=supp,
        rationale=draft.rationale,
        conversation_id=conv_id,
        should_send=draft.should_send,
        suppress_reason=draft.suppress_reason,
        levers=list(draft.levers),
        kind=t.kind,
        trigger_id=t.id,
        merchant_id=m.merchant_id or t.merchant_id,
        customer_id=t.customer_id,
    )


def compose_contract(category: dict, merchant: dict, trigger: dict,
                     customer: Optional[dict] = None) -> dict[str, Any]:
    """The exact 5-field dict the challenge's ``compose`` signature returns."""
    return compose(category, merchant, trigger, customer).to_contract()
