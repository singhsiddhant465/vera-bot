"""Determinism: the same inputs must always yield the same bytes out."""
from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from app.engine.compose import compose_contract
from app.main import create_app

PKG = Path("/home/claude/pkg/dataset")


def _load():
    cats = {s: json.load(open(PKG / "categories" / f"{s}.json"))
            for s in ("dentists", "salons", "restaurants", "gyms", "pharmacies")}
    M = {m["merchant_id"]: m for m in json.load(open(PKG / "merchants_seed.json"))["merchants"]}
    C = {c["customer_id"]: c for c in json.load(open(PKG / "customers_seed.json"))["customers"]}
    T = json.load(open(PKG / "triggers_seed.json"))["triggers"]
    return cats, M, C, T


def test_compose_is_deterministic_across_all_triggers():
    cats, M, C, T = _load()
    for t in T:
        m = M.get(t.get("merchant_id"))
        if not m:
            continue
        cat = cats[m["category_slug"]]
        cust = C.get(t.get("customer_id")) if t.get("customer_id") else None
        a = compose_contract(cat, m, t, cust)
        b = compose_contract(cat, m, t, cust)
        assert a == b, f"non-deterministic compose for {t['kind']}"


def test_tick_is_deterministic():
    cats, M, C, T = _load()

    def run():
        app = create_app()
        cl = TestClient(app)
        for slug, c in cats.items():
            cl.post("/v1/context", json={"scope": "category", "context_id": slug,
                                        "version": 1, "payload": c})
        for mid, m in M.items():
            cl.post("/v1/context", json={"scope": "merchant", "context_id": mid,
                                        "version": 1, "payload": m})
        for cid, c in C.items():
            cl.post("/v1/context", json={"scope": "customer", "context_id": cid,
                                        "version": 1, "payload": c})
        for t in T:
            cl.post("/v1/context", json={"scope": "trigger", "context_id": t["id"],
                                        "version": 1, "payload": t})
        ids = [t["id"] for t in T]
        return cl.post("/v1/tick", json={"available_triggers": ids}).json()

    r1, r2 = run(), run()
    # compare on the content fields (ack timestamps aren't part of tick output)
    assert json.dumps(r1, sort_keys=True) == json.dumps(r2, sort_keys=True)
