"""Deterministic primitives.

Everything on the decision path must be reproducible: same input -> same bytes
out. That rules out ``random``, wall-clock reads, and set-iteration order leaking
into output. This module centralises those primitives so the rest of the engine
can stay pure.
"""
from __future__ import annotations

import hashlib
from typing import Any, Callable, Iterable, Sequence, TypeVar

T = TypeVar("T")


def stable_hash(*parts: Any, length: int = 12) -> str:
    """Short, stable, cross-process hash of the given parts.

    ``str()`` of each part is joined with a separator that cannot appear in a
    normal id, then sha256'd. Unlike the builtin ``hash()`` this is stable across
    processes and Python's hash randomisation, so suppression keys and ack ids are
    reproducible.
    """
    joined = "\x1f".join("" if p is None else str(p) for p in parts)
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()[:length]


def _indian_group(n: int) -> str:
    """Group an integer the Indian way: ``100000 -> '1,00,000'``."""
    sign = "-" if n < 0 else ""
    s = str(abs(int(n)))
    if len(s) <= 3:
        return sign + s
    last3, rest = s[-3:], s[:-3]
    chunks: list[str] = []
    while len(rest) > 2:
        chunks.insert(0, rest[-2:])
        rest = rest[:-2]
    if rest:
        chunks.insert(0, rest)
    return sign + ",".join(chunks) + "," + last3


def format_int(n: float | int | None) -> str | None:
    return None if n is None else _indian_group(int(round(float(n))))


def format_inr(amount: float | int | str | None) -> str | None:
    """``299 -> '₹299'``, ``100000 -> '₹1,00,000'``. ``None`` stays ``None``."""
    if amount is None:
        return None
    try:
        return "₹" + _indian_group(int(round(float(amount))))
    except (TypeError, ValueError):
        return None


def format_pct(x: float | int | None) -> str | None:
    """A number already expressed in percent: ``38 -> '38%'``, ``2.1 -> '2.1%'``."""
    if x is None:
        return None
    xf = float(x)
    if abs(xf - round(xf)) < 1e-9:
        return f"{int(round(xf))}%"
    return f"{xf:.1f}%"


def frac_to_pct(x: float | int | None, *, signed: bool = False) -> str | None:
    """A fraction expressed as percent: ``0.021 -> '2.1%'``, ``-0.5 -> '50%'``.

    With ``signed=True`` the sign is preserved (``-0.5 -> '-50%'``); otherwise the
    magnitude is returned so the caller can supply the direction word ("down").
    """
    if x is None:
        return None
    try:
        val = float(x) * 100.0
    except (TypeError, ValueError):
        return None
    if not signed:
        val = abs(val)
    return format_pct(val)


def stable_sort(items: Iterable[T], key: Callable[[T], Sequence[Any]]) -> list[T]:
    """Sort by a fully explicit key tuple. Python's sort is stable; forcing a
    total-order key removes any reliance on insertion order for tie-breaking."""
    return sorted(items, key=key)
