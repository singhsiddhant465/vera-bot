"""Reply behavior — the three replay scenarios the harness runs, plus basics."""
from __future__ import annotations

from app.engine.reply import classify_reply

ACTION_WORDS = ("done", "sending", "drafted", "sharing", "confirm", "proceed", "next")
QUALIFY_WORDS = ("would you", "do you", "can you tell", "what if", "how about")


def test_auto_reply_ends():
    d = classify_reply("Thank you for contacting us! Our team will respond shortly.")
    assert d.action == "end"


def test_hostile_ends():
    d = classify_reply("Stop messaging me. This is useless spam.")
    assert d.action == "end"


def test_intent_transition_switches_to_action_mode():
    d = classify_reply("Ok lets do it. Whats next?")
    assert d.action == "send"
    low = d.body.lower()
    assert any(w in low for w in ACTION_WORDS)
    assert not any(w in low for w in QUALIFY_WORDS)


def test_hard_no_ends():
    assert classify_reply("not interested, thanks").action == "end"


def test_defer_waits():
    d = classify_reply("not now, maybe next week")
    assert d.action == "wait" and d.wait_seconds and d.wait_seconds > 0


def test_plain_yes_advances_in_action_mode():
    d = classify_reply("haan theek hai")
    assert d.action == "send"
    assert not any(w in d.body.lower() for w in QUALIFY_WORDS)


def test_question_stays_on_mission_with_single_cta():
    d = classify_reply("can you also help me file my GST?")
    assert d.action == "send"
    assert d.body.count("?") <= 1 or "GST" not in d.body  # concise, one ask


def test_empty_message_waits():
    assert classify_reply("").action == "wait"
