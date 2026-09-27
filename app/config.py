"""Central configuration.

Every tunable lives here so there are no magic numbers scattered through the
engine. Team-identity and the optional LLM enhancer are environment-overridable
so the same image can be submitted by any team without code edits.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field


# --- output enums (the composition contract) -------------------------------
class SendAs:
    VERA = "vera"                      # merchant-facing (Vera speaking to the merchant)
    MERCHANT = "merchant_on_behalf"    # customer-facing (drafted for the merchant's WA number)


class Cta:
    BINARY = "binary"        # single YES/STOP-style commitment
    OPEN = "open_ended"      # a question that invites a free-form reply
    NONE = "none"            # pure information, no ask


class ReplyAction:
    SEND = "send"
    WAIT = "wait"
    END = "end"


VALID_SCOPES = ("category", "merchant", "customer", "trigger")


def _env(name: str, default: str) -> str:
    return os.environ.get(name, default)


@dataclass(frozen=True)
class Settings:
    # Identity returned by GET /v1/metadata — override via env before submitting.
    team_name: str = _env("VERA_TEAM_NAME", "Siddhant Singh")
    team_members: tuple[str, ...] = field(
        default_factory=lambda: tuple(
            m.strip() for m in _env("VERA_TEAM_MEMBERS", "Siddhant Singh").split(",") if m.strip()
        )
    )
    contact_email: str = _env("VERA_CONTACT_EMAIL", "your-college-email@dtu.ac.in")
    model: str = _env("VERA_MODEL", "vera-deterministic-composer/no-llm")
    approach: str = _env(
        "VERA_APPROACH",
        "Deterministic rules composer: dispatch by trigger.kind, ground every fact "
        "in pushed context, single-CTA output. Optional temp-0 LLM enhancer (off by default).",
    )
    version: str = _env("VERA_VERSION", "1.0.0")
    submitted_at: str = _env("VERA_SUBMITTED_AT", "2026-09-27T00:00:00Z")

    # Optional LLM enhancer. OFF by default -> engine is 100% deterministic and
    # needs no network/API key. When on, the LLM only *rephrases* the already
    # chosen, fully-grounded body under a fact-whitelist; it never picks the
    # action and never introduces new facts. See engine/enhancer.py.
    llm_enhance: bool = _env("VERA_LLM_ENHANCE", "0") == "1"

    # Suppression / cadence.
    resend_window_ticks: int = int(_env("VERA_RESEND_WINDOW_TICKS", "999999"))  # once per key per test
    default_wait_seconds: int = int(_env("VERA_DEFAULT_WAIT_SECONDS", "1800"))

    # Operational caps (match testing brief §5).
    max_actions_per_tick: int = 20


SETTINGS = Settings()
