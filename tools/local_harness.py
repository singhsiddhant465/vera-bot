#!/usr/bin/env python3
"""Offline dev harness — no API key required.

Mimics the judge lifecycle (warmup -> context push -> tick -> reply) against the
bot **in-process** so you can iterate fast without deploying or paying for an
LLM. It prints every composed message and runs the three replay scenarios and a
determinism check.

This is a *complement* to the official ``judge_simulator.py`` (which needs an LLM
key to produce real rubric scores). Use this to sanity-check behaviour and
grounding; use ``judge_simulator.py`` for scored evaluation.

Run:
    python tools/local_harness.py                       # auto-find ./dataset
    python tools/local_harness.py --dataset /path/to/dataset
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# make "app" importable when run from anywhere
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient  # noqa: E402

from app.main import create_app  # noqa: E402


def find_dataset(explicit: str | None) -> Path:
    candidates = []
    if explicit:
        candidates.append(Path(explicit))
    here = Path(__file__).resolve().parent.parent
    candidates += [here / "dataset", here.parent / "dataset",
                   here.parent / "pkg" / "dataset", Path("/home/claude/pkg/dataset")]
    for c in candidates:
        if c.exists() and (c / "merchants_seed.json").exists():
            return c
    print("Could not find the challenge dataset. Pass --dataset /path/to/dataset")
    sys.exit(2)


def load(ds: Path):
    cats = {p.stem: json.load(open(p)) for p in (ds / "categories").glob("*.json")}
    cats = {c.get("slug", k): c for k, c in cats.items()}
    M = {m["merchant_id"]: m for m in json.load(open(ds / "merchants_seed.json"))["merchants"]}
    C = {c["customer_id"]: c for c in json.load(open(ds / "customers_seed.json"))["customers"]}
    T = json.load(open(ds / "triggers_seed.json"))["triggers"]
    return cats, M, C, T


def spec_proxy(body: str) -> int:
    """A crude, non-authoritative 'specificity' proxy: count concrete anchors
    (numbers, %, ₹, dates). NOT the real judge — just a smoke signal."""
    return (len(re.findall(r"\d", body)) + body.count("%") + body.count("₹")
            + len(re.findall(r"\d{4}-\d{2}-\d{2}", body)))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", default=None)
    args = ap.parse_args()
    ds = find_dataset(args.dataset)
    cats, M, C, T = load(ds)

    app = create_app()
    cl = TestClient(app)

    print(f"== dataset: {ds}")
    print(f"== loaded {len(cats)} categories, {len(M)} merchants, {len(C)} customers, {len(T)} triggers\n")

    # Phase 1 — warmup: push everything, verify counts
    for slug, c in cats.items():
        cl.post("/v1/context", json={"scope": "category", "context_id": slug, "version": 1, "payload": c})
    for mid, m in M.items():
        cl.post("/v1/context", json={"scope": "merchant", "context_id": mid, "version": 1, "payload": m})
    for cid, cc in C.items():
        cl.post("/v1/context", json={"scope": "customer", "context_id": cid, "version": 1, "payload": cc})
    for t in T:
        cl.post("/v1/context", json={"scope": "trigger", "context_id": t["id"], "version": 1, "payload": t})
    hz = cl.get("/v1/healthz").json()
    print("WARMUP healthz.contexts_loaded:", hz["contexts_loaded"])
    meta = cl.get("/v1/metadata").json()
    print("METADATA team:", meta["team_name"], "| model:", meta["model"], "| contact:", meta["contact_email"], "\n")

    # Phase 2 — tick over all triggers (batches of 5, like the sim's _full)
    ids = [t["id"] for t in T]
    total, spec_sum = 0, 0
    print("== COMPOSED MESSAGES ==")
    for i in range(0, len(ids), 5):
        batch = ids[i:i + 5]
        actions = cl.post("/v1/tick", json={"available_triggers": batch}).json()["actions"]
        for a in actions:
            total += 1
            s = spec_proxy(a["body"])
            spec_sum += s
            tid = a["trigger_id"] or ""
            kind = next((t["kind"] for t in T if t["id"] == tid), "?")
            print(f"\n[{kind}]  send_as={a['send_as']}  cta={a['cta']}  anchors~{s}")
            print(f"  {a['body']}")
            print(f"  rationale: {a['rationale']}")
    print(f"\n== {total} messages composed; avg concrete-anchor proxy = "
          f"{(spec_sum/total):.1f} (heuristic only, not the real judge)\n")

    # Phase 4 — replay scenarios
    print("== REPLAY SCENARIOS ==")
    scenarios = [
        ("auto-reply", "Thank you for contacting us! Our team will respond shortly.", "end"),
        ("intent",     "Ok lets do it. Whats next?",                                   "send"),
        ("hostile",    "Stop messaging me. This is useless spam.",                     "end"),
    ]
    ok = True
    mid0 = next(iter(M))
    for i, (name, msg, expect) in enumerate(scenarios):
        r = cl.post("/v1/reply", json={"conversation_id": f"conv_{name}", "merchant_id": mid0,
                                       "from_role": "merchant", "message": msg, "turn_number": 2}).json()
        got = r["action"]
        mark = "PASS" if got == expect else "FAIL"
        if got != expect:
            ok = False
        extra = f'  body="{r.get("body","")[:60]}"' if got == "send" else ""
        print(f"  [{mark}] {name}: expected {expect}, got {got}{extra}")

    # intent must be true ACTION mode
    r = cl.post("/v1/reply", json={"conversation_id": "conv_intent2", "merchant_id": mid0,
                                   "from_role": "merchant", "message": "Ok lets do it. Whats next?"}).json()
    body = r.get("body", "").lower()
    action_ok = any(w in body for w in ("done", "sending", "drafted", "sharing", "confirm", "proceed", "next")) \
        and not any(w in body for w in ("would you", "do you", "can you tell", "what if", "how about"))
    print(f"  [{'PASS' if action_ok else 'FAIL'}] intent -> action-mode wording")
    ok = ok and action_ok

    # Determinism — two FRESH warmed instances must produce identical tick output
    def fresh_tick(batch):
        a = create_app(); c = TestClient(a)
        for slug, cat in cats.items():
            c.post("/v1/context", json={"scope": "category", "context_id": slug, "version": 1, "payload": cat})
        for mid, m in M.items():
            c.post("/v1/context", json={"scope": "merchant", "context_id": mid, "version": 1, "payload": m})
        for cid, cc in C.items():
            c.post("/v1/context", json={"scope": "customer", "context_id": cid, "version": 1, "payload": cc})
        for t in T:
            c.post("/v1/context", json={"scope": "trigger", "context_id": t["id"], "version": 1, "payload": t})
        return c.post("/v1/tick", json={"available_triggers": batch}).json()

    a1, a2 = fresh_tick(ids[:5]), fresh_tick(ids[:5])
    det_ok = json.dumps(a1, sort_keys=True) == json.dumps(a2, sort_keys=True)
    print(f"\n  [{'PASS' if det_ok else 'FAIL'}] determinism: identical tick output across fresh instances")

    print("\n== HARNESS", "OK ==" if (ok and det_ok) else "FAILURES PRESENT ==")
    return 0 if (ok and det_ok) else 1


if __name__ == "__main__":
    raise SystemExit(main())
