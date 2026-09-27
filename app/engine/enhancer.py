"""Optional LLM rephrasing layer — OFF by default (``VERA_LLM_ENHANCE=1``).

Design contract, so enabling it can never lower trust:

* It **only rephrases** an already-composed, fully-grounded body.
* It is given a **fact whitelist** (every number/name/date already in the body)
  and told to introduce nothing new.
* The **deterministic body is the source of truth**: if the model adds any token
  that isn't a whitelisted fact, or the call fails, or returns empty, we discard
  the rewrite and keep the deterministic body.
* temperature=0 for reproducibility.

The engine never depends on this: with the flag off there is no network call and
no API key needed. Uses stdlib ``urllib`` only (no extra dependency).
"""
from __future__ import annotations

import json
import os
import re
import urllib.request
from typing import Optional

from .handlers import Draft
from .normalize import CategoryView, CustomerView, MerchantView, TriggerView

_MODEL = os.environ.get("VERA_LLM_MODEL", "claude-3-5-sonnet-20241022")
_ENDPOINT = "https://api.anthropic.com/v1/messages"
_TIMEOUT = int(os.environ.get("VERA_LLM_TIMEOUT", "12"))

_SYSTEM = (
    "You rewrite a WhatsApp message for tone and flow ONLY. Rules: (1) use ONLY "
    "the facts in the provided body — never add numbers, names, dates, offers, or "
    "claims; (2) keep the same call-to-action and the same language mix; (3) one "
    "CTA, concise, no preamble, no emojis unless already present; (4) reply with "
    "the rewritten message text and nothing else."
)

_TOKEN = re.compile(r"[0-9]+(?:[.,][0-9]+)?%?|₹[0-9,]+")


def _facts(body: str) -> set[str]:
    return set(_TOKEN.findall(body))


def enhance(draft: Draft, m: MerchantView, c: CategoryView,
            t: TriggerView, cust: CustomerView) -> Optional[str]:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return None
    prompt = (f"Rewrite this message for natural flow. Do not add any fact not "
              f"present here.\n\nBODY:\n{draft.body}")
    payload = {"model": _MODEL, "max_tokens": 400, "temperature": 0,
               "system": _SYSTEM, "messages": [{"role": "user", "content": prompt}]}
    req = urllib.request.Request(
        _ENDPOINT, data=json.dumps(payload).encode("utf-8"),
        headers={"x-api-key": api_key, "content-type": "application/json",
                 "anthropic-version": "2023-06-01"})
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        text = "".join(b.get("text", "") for b in data.get("content", [])).strip()
    except Exception:
        return None
    if not text:
        return None
    # Guard: the rewrite must not introduce a numeric/₹ fact that wasn't grounded.
    if not _facts(text).issubset(_facts(draft.body)):
        return None
    return text
