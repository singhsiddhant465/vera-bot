"""Small, deterministic language helpers.

Kept intentionally light: a few natural Hindi-English connective phrases for
customer-facing messages when the language preference calls for it, plus
salutation and list-joining utilities. No randomness — the same inputs always
produce the same wording.
"""
from __future__ import annotations

from typing import Optional


def salutation_merchant(owner_first_name: Optional[str], name: Optional[str],
                        is_doctor: bool = False) -> str:
    """Address the merchant by owner first name when available."""
    if owner_first_name:
        return f"Dr. {owner_first_name}" if is_doctor else owner_first_name
    if name:
        return name
    return "there"


def salutation_customer(name: Optional[str]) -> str:
    return name if name else "there"


def join_human(items: list[str]) -> str:
    """``[a, b, c] -> 'a, b and c'`` (deterministic, no Oxford comma)."""
    items = [i for i in items if i]
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    if len(items) == 2:
        return f"{items[0]} and {items[1]}"
    return ", ".join(items[:-1]) + f" and {items[-1]}"


# Reusable code-mix fragments, chosen by intent so wording stays natural.
_HI = {
    "slots_ready": "aapke liye {n} slots ready hain",
    "ready": "ready hai",
    "reply_confirm": "Reply CONFIRM",
    "reply_yes": "Reply YES",
    "or_time": "ya koi aur time batayein",
    "namaste": "Namaste",
}


def slots_ready_phrase(n: int, prefers_hindi: bool) -> str:
    if prefers_hindi:
        return _HI["slots_ready"].format(n=n)
    return f"{n} slots are open for you"


def or_time_phrase(prefers_hindi: bool) -> str:
    return _HI["or_time"] if prefers_hindi else "or tell us a time that works"


def opener_customer(prefers_hindi: bool, senior: bool = False) -> str:
    if senior and prefers_hindi:
        return _HI["namaste"]
    return "Namaste" if prefers_hindi else "Hi"
