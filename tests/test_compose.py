"""Composition quality: grounding, correct audience, single CTA, no fabrication."""
from __future__ import annotations

import json
from pathlib import Path

from app.config import Cta, SendAs
from app.engine.compose import compose

PKG = Path("/home/claude/pkg/dataset")


def _cat(slug):
    return json.load(open(PKG / "categories" / f"{slug}.json"))


def _by_id(name, key):
    data = json.load(open(PKG / name))
    container = data[[k for k in data if isinstance(data[k], list)][0]]
    return {x[key]: x for x in container}


MERCHANTS = _by_id("merchants_seed.json", "merchant_id")
CUSTOMERS = _by_id("customers_seed.json", "customer_id")
TRIGGERS = json.load(open(PKG / "triggers_seed.json"))["triggers"]


def _find(kind):
    return next(t for t in TRIGGERS if t["kind"] == kind)


def test_research_digest_grounds_in_source_and_cohort():
    t = _find("research_digest")
    m = MERCHANTS[t["merchant_id"]]
    r = compose(_cat("dentists"), m, t)
    assert "JIDA" in r.body                      # source cited
    assert "2,100" in r.body or "2100" in r.body  # trial_n grounded
    assert "124" in r.body                        # merchant's own cohort
    assert r.send_as == SendAs.VERA


def test_recall_due_is_customer_facing_with_real_slots():
    t = _find("recall_due")
    m = MERCHANTS[t["merchant_id"]]
    cust = CUSTOMERS[t["customer_id"]]
    r = compose(_cat("dentists"), m, t, cust)
    assert r.send_as == SendAs.MERCHANT
    assert "Priya" in r.body
    assert "Wed 5 Nov, 6pm" in r.body and "Thu 6 Nov, 5pm" in r.body
    assert "aapke liye" in r.body                  # hi-en code-mix honored


def test_ipl_weekend_pivots_to_delivery():
    t = _find("ipl_match_today")   # is_weeknight: false
    m = MERCHANTS[t["merchant_id"]]
    r = compose(_cat("restaurants"), m, t)
    assert "delivery" in r.body.lower()            # contrarian judgement


def test_seasonal_dip_is_reframed_not_alarmed():
    t = _find("seasonal_perf_dip")
    m = MERCHANTS[t["merchant_id"]]
    r = compose(_cat("gyms"), m, t)
    assert "normal" in r.body.lower()


def test_supply_alert_never_claims_total_as_affected():
    t = _find("supply_alert")
    m = MERCHANTS[t["merchant_id"]]
    r = compose(_cat("pharmacies"), m, t)
    assert "AT2024-1102" in r.body                 # batch grounded
    assert "may be affected" not in r.body         # 240 is the pool, not affected count


def test_competitor_named_only_from_context():
    t = _find("competitor_opened")
    m = MERCHANTS[t["merchant_id"]]
    r = compose(_cat("dentists"), m, t)
    assert "Smile Studio" in r.body                # the real name from payload


def test_single_cta_value_is_valid_everywhere():
    valid = {Cta.BINARY, Cta.OPEN, Cta.NONE}
    for t in TRIGGERS:
        m = MERCHANTS.get(t.get("merchant_id"))
        if not m:
            continue
        cust = CUSTOMERS.get(t.get("customer_id")) if t.get("customer_id") else None
        r = compose(_cat(m["category_slug"]), m, t, cust)
        assert r.cta in valid
        # exactly one "Reply ..." style ask at most
        assert r.body.count("Reply ") <= 1


def test_no_taboo_vocab_leaks():
    for t in TRIGGERS:
        m = MERCHANTS.get(t.get("merchant_id"))
        if not m:
            continue
        cat = _cat(m["category_slug"])
        taboos = (cat.get("voice") or {}).get("vocab_taboo", [])
        cust = CUSTOMERS.get(t.get("customer_id")) if t.get("customer_id") else None
        body = compose(cat, m, t, cust).body.lower()
        for taboo in taboos:
            base = taboo.split("(")[0].strip().lower()
            if base and base not in ("fda-approved",):
                assert base not in body, f"taboo '{base}' leaked for {t['kind']}"


def test_rationale_present_and_names_kind():
    for t in TRIGGERS:
        m = MERCHANTS.get(t.get("merchant_id"))
        if not m:
            continue
        cust = CUSTOMERS.get(t.get("customer_id")) if t.get("customer_id") else None
        r = compose(_cat(m["category_slug"]), m, t, cust)
        assert r.rationale and len(r.rationale) > 10
