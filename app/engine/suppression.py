"""Suppression keys.

A suppression key identifies "this decision" for dedup. When the trigger already
carries a ``suppression_key`` (the dataset provides one, designed for exactly
this), we reuse it — that's the authoritative dedup unit. Otherwise we build a
stable key from the parts that make two sends "the same": merchant, kind,
audience, and the single most salient payload fact.
"""
from __future__ import annotations

from typing import Any

from .determinism import stable_hash
from .normalize import MerchantView, TriggerView


# the payload field that best identifies a specific send, per kind
_PRIMARY_FACT = {
    "research_digest": "top_item_id",
    "regulation_change": "top_item_id",
    "cde_opportunity": "digest_item_id",
    "supply_alert": "alert_id",
    "festival_upcoming": "festival",
    "ipl_match_today": "match",
    "review_theme_emerged": "theme",
    "competitor_opened": "competitor_name",
    "recall_due": "due_date",
    "chronic_refill_due": "stock_runs_out_iso",
    "wedding_package_followup": "wedding_date",
    "active_planning_intent": "intent_topic",
}


def build_suppression_key(t: TriggerView, m: MerchantView, send_as: str) -> str:
    if t.suppression_key:
        return t.suppression_key
    fact_key = _PRIMARY_FACT.get(t.kind)
    fact: Any = t.p(fact_key) if fact_key else None
    merchant_id = m.merchant_id or t.merchant_id or "m"
    audience = "cust" if send_as == "merchant_on_behalf" else "mx"
    return f"{t.kind}:{audience}:" + stable_hash(merchant_id, t.kind, audience, fact, length=10)
