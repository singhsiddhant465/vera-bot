"""Endpoint contract tests (testing-brief §2)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import create_app

PKG = Path("/home/claude/pkg/dataset")


@pytest.fixture()
def client():
    return TestClient(create_app())


def _cat(slug="dentists"):
    return json.load(open(PKG / "categories" / f"{slug}.json"))


def _merchants():
    return json.load(open(PKG / "merchants_seed.json"))["merchants"]


def _triggers():
    return json.load(open(PKG / "triggers_seed.json"))["triggers"]


def test_healthz_shape(client):
    r = client.get("/v1/healthz")
    assert r.status_code == 200
    b = r.json()
    assert b["status"] == "ok"
    assert isinstance(b["uptime_seconds"], int)
    assert set(b["contexts_loaded"]) == {"category", "merchant", "customer", "trigger"}


def test_metadata_shape(client):
    b = client.get("/v1/metadata").json()
    for k in ("team_name", "team_members", "model", "approach",
              "contact_email", "version", "submitted_at"):
        assert k in b
    assert isinstance(b["team_members"], list)


def test_context_accept_and_counts(client):
    r = client.post("/v1/context", json={
        "scope": "category", "context_id": "dentists", "version": 1,
        "payload": _cat(), "delivered_at": "2026-04-26T10:00:00Z"})
    assert r.status_code == 200 and r.json()["accepted"] is True
    assert client.get("/v1/healthz").json()["contexts_loaded"]["category"] == 1


def test_context_idempotent_same_version(client):
    body = {"scope": "category", "context_id": "dentists", "version": 3,
            "payload": _cat(), "delivered_at": "2026-04-26T10:00:00Z"}
    a = client.post("/v1/context", json=body).json()
    b = client.post("/v1/context", json=body).json()   # re-post same version = no-op
    assert a["accepted"] and b["accepted"]
    assert client.get("/v1/healthz").json()["contexts_loaded"]["category"] == 1


def test_context_stale_version_409(client):
    client.post("/v1/context", json={"scope": "merchant", "context_id": "m1",
                                     "version": 5, "payload": {"merchant_id": "m1"}})
    r = client.post("/v1/context", json={"scope": "merchant", "context_id": "m1",
                                        "version": 2, "payload": {"merchant_id": "m1"}})
    assert r.status_code == 409
    b = r.json()
    assert b["accepted"] is False and b["reason"] == "stale_version"
    assert b["current_version"] == 5


def test_context_higher_version_replaces(client):
    client.post("/v1/context", json={"scope": "merchant", "context_id": "m1",
                                     "version": 1, "payload": {"merchant_id": "m1", "v": 1}})
    r = client.post("/v1/context", json={"scope": "merchant", "context_id": "m1",
                                        "version": 2, "payload": {"merchant_id": "m1", "v": 2}})
    assert r.status_code == 200 and r.json()["accepted"] is True


def test_context_invalid_scope_400(client):
    r = client.post("/v1/context", json={"scope": "widget", "context_id": "x",
                                        "version": 1, "payload": {}})
    assert r.status_code == 400
    assert r.json()["reason"] == "invalid_scope"


def _warm(client):
    for slug in ("dentists", "restaurants", "pharmacies", "gyms", "salons"):
        client.post("/v1/context", json={"scope": "category", "context_id": slug,
                                        "version": 1, "payload": _cat(slug)})
    for m in _merchants():
        client.post("/v1/context", json={"scope": "merchant",
                                        "context_id": m["merchant_id"], "version": 1, "payload": m})
    for t in _triggers():
        client.post("/v1/context", json={"scope": "trigger",
                                        "context_id": t["id"], "version": 1, "payload": t})


def test_tick_returns_actions(client):
    _warm(client)
    ids = [t["id"] for t in _triggers()][:6]
    r = client.post("/v1/tick", json={"now": "2026-04-26T10:30:00Z", "available_triggers": ids})
    assert r.status_code == 200
    actions = r.json()["actions"]
    assert len(actions) >= 1
    a = actions[0]
    for k in ("conversation_id", "merchant_id", "send_as", "trigger_id",
              "template_name", "body", "cta", "suppression_key", "rationale"):
        assert k in a
    assert a["body"] and a["send_as"] in ("vera", "merchant_on_behalf")


def test_tick_empty_when_no_context(client):
    r = client.post("/v1/tick", json={"now": "t", "available_triggers": ["nope"]})
    assert r.json() == {"actions": []}


def test_tick_dedupes_suppression_key_across_ticks(client):
    _warm(client)
    ids = [t["id"] for t in _triggers()][:6]   # under the 20-action/tick cap
    first = client.post("/v1/tick", json={"available_triggers": ids}).json()["actions"]
    second = client.post("/v1/tick", json={"available_triggers": ids}).json()["actions"]
    assert len(first) >= 1
    assert len(second) == 0   # everything already sent -> suppressed next tick


def test_reply_shape(client):
    r = client.post("/v1/reply", json={"conversation_id": "c1", "merchant_id": "m1",
                                      "from_role": "merchant", "message": "yes please",
                                      "received_at": "t", "turn_number": 2})
    b = r.json()
    assert b["action"] in ("send", "wait", "end")
