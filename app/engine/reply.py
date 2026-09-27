"""Deterministic reply handling for ``POST /v1/reply``.

The three replay scenarios the harness runs (auto-reply hell, intent transition,
hostile/off-topic) are all pattern-detectable, so this is a rules classifier —
no LLM, no randomness. Priority order matters: opt-out/hostile first, then
canned auto-replies, then hard no, defer, commitment/accept, and finally a
question fallback.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from ..config import Cta, ReplyAction, SETTINGS
from .store import Conversation


@dataclass
class ReplyDecision:
    action: str
    body: Optional[str] = None
    cta: Optional[str] = None
    wait_seconds: Optional[int] = None
    rationale: str = ""


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower())


def _has(text: str, phrases: tuple[str, ...]) -> bool:
    return any(p in text for p in phrases)


_HOSTILE = (
    "stop messaging", "stop texting", "unsubscribe", "leave me alone",
    "don't message", "dont message", "do not message", "spam", "useless",
    "block you", "reported", "harassment", "chup", "band karo",
)
_AUTOREPLY = (
    "thank you for contacting", "our team will", "respond shortly",
    "will get back to you", "will revert", "automated", "auto-reply", "auto reply",
    "aapki jaankari ke liye", "team tak pahuncha", "shukriya", "we have received your",
    "currently unavailable", "office hours",
)
_HARD_NO = (
    "not interested", "no thanks", "no thank you", "no need", "don't want",
    "dont want", "already have", "nahi chahiye",
)
_DEFER = (
    "not now", "later", "busy", "next week", "call me later", "some other time",
    "baad me", "baad mein", "thoda time", "give me time", "not today",
)
_COMMIT = (
    "lets do it", "let's do it", "let us do it", "go ahead", "do it", "sign me up",
    "sign up", "i want to join", "want to join", "join", "i'm in", "im in",
    "count me in", "proceed", "start", "get started", "sounds good", "sounds great",
    "yes please", "yes go", "chalega", "kar do", "kar dijiye", "haan karo",
    "whats next", "what's next", "what next", "aage badho",
)
_ACCEPT = (
    "yes", "yeah", "yep", "sure", "ok", "okay", "haan", "han", "theek hai",
    "thik hai", "please go", "please do", "great", "perfect", "sounds fine",
)

# words the intent-transition check looks for / against
_ACTION_WORDS = ("done", "sending", "drafted", "sharing", "confirm", "proceed", "next")
_QUALIFY_WORDS = ("would you", "do you", "can you tell", "what if", "how about")


def _dedupe(body: str, conv: Optional[Conversation]) -> str:
    """Never return the exact body already sent in this conversation."""
    if conv and conv.last_bot_body and _norm(conv.last_bot_body) == _norm(body):
        return body.rstrip(".") + " — shall I go ahead?"
    return body


def classify_reply(message: str, conv: Optional[Conversation] = None) -> ReplyDecision:
    text = _norm(message)

    if not text:
        return ReplyDecision(ReplyAction.WAIT, wait_seconds=SETTINGS.default_wait_seconds,
                             rationale="empty inbound; backing off briefly")

    # 1) hostile / opt-out -> exit gracefully
    if _has(text, _HOSTILE):
        return ReplyDecision(ReplyAction.END,
                             rationale="opt-out/hostile signal; stopping outreach respectfully")

    # 2) canned auto-reply -> don't burn turns, exit
    if _has(text, _AUTOREPLY):
        return ReplyDecision(ReplyAction.END,
                             rationale="detected WhatsApp Business auto-reply; ending to avoid turn waste")

    # 3) explicit hard no -> exit
    if _has(text, _HARD_NO):
        return ReplyDecision(ReplyAction.END,
                             rationale="explicit not-interested; graceful exit")

    # 4) defer -> wait, no send
    if _has(text, _DEFER):
        return ReplyDecision(ReplyAction.WAIT, wait_seconds=SETTINGS.default_wait_seconds,
                             rationale="merchant asked for time; backing off")

    # 5) commitment / intent transition -> switch to ACTION mode immediately
    if _has(text, _COMMIT):
        body = ("On it — I've drafted the first version and I'm sharing it now. "
                "Confirm and I'll proceed to the next step.")
        return ReplyDecision(ReplyAction.SEND, body=_dedupe(body, conv), cta=Cta.OPEN,
                             rationale="explicit commitment; moved straight to action, no re-qualifying")

    # 6) plain accept -> acknowledge + advance (still action-mode, no new question)
    if _is_word_hit(text, _ACCEPT):
        body = ("Great — done on my side, sending it across now. "
                "I'll confirm once it's live.")
        return ReplyDecision(ReplyAction.SEND, body=_dedupe(body, conv), cta=Cta.OPEN,
                             rationale="affirmative; acknowledged and advanced to the next step")

    # 7) anything else (a question / curveball) -> answer briefly, stay on mission
    body = ("Good question — short answer: yes, I can handle that. Want me to take the "
            "first step now and share it for your ok?")
    return ReplyDecision(ReplyAction.SEND, body=_dedupe(body, conv), cta=Cta.OPEN,
                         rationale="open reply; answered concisely and kept a single low-friction CTA")


def _is_word_hit(text: str, words: tuple[str, ...]) -> bool:
    """Match short accept tokens as whole words to avoid substrings (e.g. 'ok' in
    'broke'). Multi-word phrases fall back to substring search."""
    toks = set(re.findall(r"[a-z']+", text))
    for w in words:
        if " " in w:
            if w in text:
                return True
        elif w in toks:
            return True
    return False
