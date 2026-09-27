# Vera Message Engine — magicpin AI Challenge submission

A hosted bot that engages merchants (and their customers) the way Vera does, exposing the
five `/v1/*` endpoints the judge harness calls. Composition is a **deterministic, grounded
rules engine** — no LLM on the default path — with an *optional* temperature-0 LLM
rephraser that is off by default.

## Approach in one line
Dispatch by `trigger.kind` → a per-kind handler that grounds every fact in the pushed
context, encodes the smart move for that situation, and ends on a single low-friction CTA.

## Why deterministic (the core trade-off)
The brief allows an LLM (temp 0) but doesn't require one. A grounded template engine gives
us four things an LLM path can't guarantee together: **reproducibility** (same input → same
bytes), **zero fabrication** (a number/name/date appears only if it was read from context),
**no API-key/latency risk** inside the 30s tick budget, and **offline testability**. The
LLM is kept as an optional *rephraser under a fact-whitelist* (`VERA_LLM_ENHANCE=1`) that
can only reword the already-chosen body and is discarded if it adds any ungrounded fact.

## Architecture
```
app/
  main.py                FastAPI factory + uvicorn entry
  config.py              team metadata (env-overridable), enums, caps, flags
  api/
    schemas.py           request models (extra="allow" — tolerant of new fields)
    routes.py            the 5 endpoints (+ optional /v1/teardown)
  engine/
    store.py             versioned idempotent ContextStore + ConversationState
    normalize.py         defensive views over raw context dicts (never raise)
    handlers.py          24 grounded per-trigger-kind handlers + generic fallback
    compose.py           compose(category, merchant, trigger, customer?) -> 5-field contract
    suppression.py       dedup key (reuses trigger.suppression_key when present)
    reply.py             deterministic auto-reply / intent / hostile / defer classifier
    language.py          Hindi-English code-mix, salutations
    determinism.py       stable hashing + Indian-format currency/number/percent
    enhancer.py          OPTIONAL temp-0 LLM rephraser (off by default)
    service.py           engine facade: tick/reply/healthz/metadata
tools/local_harness.py   offline judge-flow harness (no API key)
tests/                   contract, determinism, compose, reply, adversarial
```

## The contract (testing-brief §2)
- `GET /v1/healthz` → status, uptime, `contexts_loaded` counts
- `GET /v1/metadata` → team identity (set via env before submitting)
- `POST /v1/context` → idempotent by `(context_id, version)`; higher replaces; **lower ⇒ 409
  `stale_version`**; bad scope ⇒ **400 `invalid_scope`**
- `POST /v1/tick` → `actions[]` (may be empty; ≤20/tick; one per (merchant, conversation)/tick)
- `POST /v1/reply` → `send` | `wait` | `end`, with anti-repetition

## How the 5 rubric dimensions are addressed
- **Specificity** — handlers inject only real anchors: `trial_n`, batch numbers, perf deltas,
  peer CTR, prices from the merchant's own catalogue, source citations resolved from
  `category.digest[]` by id.
- **Category fit** — per-category voice (clinical for dentists, operator for restaurants,
  coach for gyms, precise for pharmacies); taboo vocab is asserted absent in tests.
- **Merchant fit** — owner first name (`owner_first_name`), locality, the merchant's own
  numbers and active offers; customer messages honour `language_pref` (hi-en code-mix).
- **Trigger relevance** — every body states *why now* from the trigger payload; the
  `rationale` names the kind and the reasoning.
- **Engagement compulsion** — one compulsion lever chosen per kind (loss aversion, social
  proof, curiosity, effort-externalisation, asking-the-merchant) + a single binary/open CTA.

Encoded judgement (not just templating): weekend IPL → push **delivery**, not a match-night
promo; an *expected* seasonal dip → **reframe as normal**, redirect spend to retention; a
far-off festival → a **prep reminder**, not an early promo; `supply_alert` states the chronic
pool size but **never** claims an un-provided "affected" count.

## Run
```bash
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8080     # or: ./run.sh  /  docker compose up
```

## Test
```bash
pytest -q                                            # 36 tests: contract/determinism/compose/reply/adversarial
python tools/local_harness.py --dataset ./dataset    # offline judge-flow + determinism check (no API key)
```

## Score with the official judge
```bash
# in the challenge package folder, set LLM_PROVIDER + LLM_API_KEY + BOT_URL in judge_simulator.py, then:
export BOT_URL=http://localhost:8080
python judge_simulator.py
```

## Optional LLM rephraser (off by default)
`VERA_LLM_ENHANCE=1` + `ANTHROPIC_API_KEY=...` rewords the deterministic body under a
fact-whitelist at temperature 0; any ungrounded token or failure falls back to the
deterministic body. Leaving it off keeps the engine fully offline and reproducible.

## Before submitting — set these
```bash
export VERA_TEAM_NAME="…"  VERA_TEAM_MEMBERS="Siddhant Singh"  VERA_CONTACT_EMAIL="you@college.ac.in"
```
Then: deploy to a public URL (Render / Railway / Fly / ngrok), keep the bot live for the test
window, and submit the URL via the portal **from your college email ID**.

## Limitations / what would help most
- Composition is rules-based, so wording variety is bounded; the optional rephraser widens it.
- Some payloads reference facts not in the base dataset (e.g. per-office building names in the
  corporate-thali example) — the engine deliberately declines to invent them, trading a little
  flourish for zero fabrication.
- The most useful extra context would be **per-merchant available slots/inventory** and an
  **explicit "affected customer" count** on recall/supply triggers, so customer-facing sends
  could be exact without any derivation.
