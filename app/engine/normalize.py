"""Tolerant views over the raw context dicts.

The judge can push partial, reshaped, or brand-new contexts at any time, so every
accessor here is defensive: missing keys return ``None``/empty, wrong types are
coerced or ignored, and nothing raises. The composer only ever reads through
these views, which keeps "don't fabricate, degrade gracefully" a single concern.
"""
from __future__ import annotations

from typing import Any, Optional


def _num(v: Any) -> Optional[float]:
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        try:
            return float(v.replace(",", "").strip())
        except ValueError:
            return None
    return None


class MerchantView:
    def __init__(self, raw: Optional[dict[str, Any]]):
        self.raw = raw or {}
        self.identity = self.raw.get("identity") or {}
        self.performance = self.raw.get("performance") or {}
        self.subscription = self.raw.get("subscription") or {}
        self.customer_aggregate = self.raw.get("customer_aggregate") or {}

    @property
    def merchant_id(self) -> Optional[str]:
        return self.raw.get("merchant_id")

    @property
    def category_slug(self) -> Optional[str]:
        return self.raw.get("category_slug")

    @property
    def name(self) -> Optional[str]:
        return self.identity.get("name")

    @property
    def owner_first_name(self) -> Optional[str]:
        return self.identity.get("owner_first_name")

    @property
    def locality(self) -> Optional[str]:
        return self.identity.get("locality")

    @property
    def city(self) -> Optional[str]:
        return self.identity.get("city")

    @property
    def languages(self) -> list[str]:
        langs = self.identity.get("languages")
        return [str(x) for x in langs] if isinstance(langs, list) else []

    @property
    def prefers_hindi(self) -> bool:
        return "hi" in [l.lower() for l in self.languages]

    @property
    def signals(self) -> list[str]:
        s = self.raw.get("signals")
        return [str(x) for x in s] if isinstance(s, list) else []

    def perf(self, key: str) -> Optional[float]:
        return _num(self.performance.get(key))

    def perf_delta(self, key: str) -> Optional[float]:
        return _num((self.performance.get("delta_7d") or {}).get(key))

    def agg(self, key: str) -> Optional[float]:
        return _num(self.customer_aggregate.get(key))

    def active_offers(self) -> list[dict[str, Any]]:
        offers = self.raw.get("offers")
        if not isinstance(offers, list):
            return []
        return [o for o in offers if isinstance(o, dict)
                and str(o.get("status", "active")).lower() == "active"]

    def best_active_offer(self) -> Optional[dict[str, Any]]:
        offers = self.active_offers()
        return offers[0] if offers else None


class CategoryView:
    def __init__(self, raw: Optional[dict[str, Any]]):
        self.raw = raw or {}
        self.voice = self.raw.get("voice") or {}

    @property
    def slug(self) -> Optional[str]:
        return self.raw.get("slug")

    @property
    def tone(self) -> Optional[str]:
        return self.voice.get("tone")

    @property
    def vocab_allowed(self) -> list[str]:
        v = self.voice.get("vocab_allowed")
        return [str(x) for x in v] if isinstance(v, list) else []

    @property
    def vocab_taboo(self) -> list[str]:
        v = self.voice.get("vocab_taboo") or self.voice.get("taboos")
        return [str(x) for x in v] if isinstance(v, list) else []

    def peer(self, key: str) -> Optional[float]:
        return _num((self.raw.get("peer_stats") or {}).get(key))

    def digest_by_id(self, item_id: Optional[str]) -> Optional[dict[str, Any]]:
        if not item_id:
            return None
        for it in self.raw.get("digest") or []:
            if isinstance(it, dict) and it.get("id") == item_id:
                return it
        return None

    def offer_catalog(self) -> list[dict[str, Any]]:
        c = self.raw.get("offer_catalog")
        return [o for o in c if isinstance(o, dict)] if isinstance(c, list) else []

    def seasonal_beats(self) -> list[dict[str, Any]]:
        b = self.raw.get("seasonal_beats")
        return [x for x in b if isinstance(x, dict)] if isinstance(b, list) else []


class TriggerView:
    def __init__(self, raw: Optional[dict[str, Any]]):
        self.raw = raw or {}
        self.payload = self.raw.get("payload") or {}

    @property
    def id(self) -> Optional[str]:
        return self.raw.get("id")

    @property
    def kind(self) -> str:
        return str(self.raw.get("kind") or "unknown")

    @property
    def scope(self) -> str:
        return str(self.raw.get("scope") or "merchant")

    @property
    def source(self) -> Optional[str]:
        return self.raw.get("source")

    @property
    def merchant_id(self) -> Optional[str]:
        return self.raw.get("merchant_id")

    @property
    def customer_id(self) -> Optional[str]:
        return self.raw.get("customer_id")

    @property
    def urgency(self) -> int:
        v = _num(self.raw.get("urgency"))
        return int(v) if v is not None else 2

    @property
    def suppression_key(self) -> Optional[str]:
        return self.raw.get("suppression_key")

    def p(self, key: str, default: Any = None) -> Any:
        return self.payload.get(key, default)


class CustomerView:
    def __init__(self, raw: Optional[dict[str, Any]]):
        self.raw = raw or {}
        self.identity = self.raw.get("identity") or {}
        self.relationship = self.raw.get("relationship") or {}
        self.preferences = self.raw.get("preferences") or {}
        self.consent = self.raw.get("consent") or {}

    @property
    def present(self) -> bool:
        return bool(self.raw)

    @property
    def customer_id(self) -> Optional[str]:
        return self.raw.get("customer_id")

    @property
    def name(self) -> Optional[str]:
        return self.identity.get("name")

    @property
    def language_pref(self) -> Optional[str]:
        return self.identity.get("language_pref")

    @property
    def prefers_hindi(self) -> bool:
        lp = (self.language_pref or "").lower()
        return "hi" in lp or "hindi" in lp

    @property
    def state(self) -> Optional[str]:
        return self.raw.get("state")

    @property
    def consent_scopes(self) -> list[str]:
        s = self.consent.get("scope")
        return [str(x) for x in s] if isinstance(s, list) else []

    def has_consent(self, *scopes: str) -> bool:
        """True if the customer opted in to at least one of the given scopes.

        If no consent block exists at all, treat as *not* opted in (safe default).
        """
        if not self.consent_scopes:
            return False
        allowed = set(self.consent_scopes)
        return any(s in allowed for s in scopes) if scopes else True
