"""Robustness under partial, malformed, or unexpected context.

The bot must never raise and never fabricate: missing facts degrade phrasing,
they don't invent numbers or names.
"""
from __future__ import annotations

from app.config import SendAs
from app.engine.compose import compose


def _m(**over):
    base = {"merchant_id": "m_x", "category_slug": "dentists",
            "identity": {"name": "Test Clinic", "owner_first_name": "Asha",
                         "locality": "Test Nagar", "languages": ["en", "hi"]},
            "performance": {"views": 1000, "calls": 10, "ctr": 0.02,
                            "delta_7d": {"calls_pct": -0.2}},
            "offers": [{"id": "o1", "title": "Cleaning @ ₹299", "status": "active"}]}
    base.update(over)
    return base


CAT = {"slug": "dentists", "voice": {"tone": "peer_clinical", "vocab_taboo": ["guaranteed"]},
       "peer_stats": {"avg_ctr": 0.03}, "digest": []}


def test_unknown_trigger_kind_uses_grounded_fallback():
    t = {"id": "t1", "kind": "some_brand_new_kind", "scope": "merchant",
         "merchant_id": "m_x", "payload": {}}
    r = compose(CAT, _m(), t)
    assert r.body and r.should_send
    assert "Asha" in r.body            # still personalized
    assert r.send_as == SendAs.VERA


def test_missing_performance_and_offers_still_composes():
    t = {"id": "t1", "kind": "perf_dip", "scope": "merchant", "merchant_id": "m_x",
         "payload": {"metric": "calls"}}
    m = _m(performance={}, offers=[])
    r = compose(CAT, m, t)
    assert r.body                       # no crash, graceful
    # no fabricated numbers when none are present
    assert "None" not in r.body


def test_empty_category_does_not_crash():
    t = {"id": "t1", "kind": "research_digest", "scope": "merchant",
         "merchant_id": "m_x", "payload": {"top_item_id": "missing"}}
    r = compose({}, _m(), t)
    assert r.body


def test_customer_trigger_without_consent_falls_back_to_advisory():
    t = {"id": "t1", "kind": "recall_due", "scope": "customer", "merchant_id": "m_x",
         "customer_id": "c1", "payload": {"due_date": "2026-11-12"}}
    cust = {"customer_id": "c1", "identity": {"name": "Riya", "language_pref": "hi-en mix"},
            "consent": {"scope": []}}   # no consent
    r = compose(CAT, _m(), t, cust)
    assert r.send_as == SendAs.VERA     # advisory to merchant, not direct outreach
    assert "Riya" not in r.body         # no PII used without consent


def test_customer_trigger_with_consent_is_direct():
    t = {"id": "t1", "kind": "recall_due", "scope": "customer", "merchant_id": "m_x",
         "customer_id": "c1", "payload": {"due_date": "2026-11-12",
                                          "available_slots": [{"label": "Wed 6pm"}]}}
    cust = {"customer_id": "c1", "identity": {"name": "Riya", "language_pref": "hi-en mix"},
            "consent": {"scope": ["recall_reminders"]}}
    r = compose(CAT, _m(), t, cust)
    assert r.send_as == SendAs.MERCHANT
    assert "Riya" in r.body


def test_none_and_wrong_types_are_tolerated():
    t = {"id": "t1", "kind": "perf_spike", "scope": "merchant", "merchant_id": "m_x",
         "payload": {"metric": None, "delta_pct": "not_a_number"}}
    m = _m(identity={"name": None, "languages": "en"}, performance=None)
    r = compose(CAT, m, t)
    assert isinstance(r.body, str) and r.body
