"""
The bias / storyline / confirmation channel.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from .. import signal_channel as sc
from ..signal_channel import SignalChannel


@dataclass
class FakeStoryline:
    stage: str = "hunting"
    direction: object = None
    effective_tf: str | None = "Weekly"
    reason: str = "Weekly/Daily/H4 aligned bullish -- watching H1 for the entry"
    daily_confirmed_at: object = "2026-09-22 00:00:00"
    h4_confirmed_at: object = "2026-09-25 08:00:00"
    weekly_confirmed_at: object = "2026-09-15 00:00:00"


class Dir:
    def __init__(self, value):
        self.value = value


@pytest.fixture
def sent(monkeypatch):
    out = []
    monkeypatch.setattr(sc, "send_message",
                        lambda token, chat, text: out.append((token, chat, text)) or True)
    return out


def test_from_env_is_none_unless_both_are_set(monkeypatch):
    """A bot with no signal channel configured must behave exactly as it
    did before this existed."""
    monkeypatch.delenv(sc.TOKEN_VAR, raising=False)
    monkeypatch.delenv(sc.CHAT_VAR, raising=False)
    assert SignalChannel.from_env() is None

    monkeypatch.setenv(sc.TOKEN_VAR, "t")
    assert SignalChannel.from_env() is None, "a token with no chat goes nowhere"

    monkeypatch.setenv(sc.CHAT_VAR, "c")
    assert SignalChannel.from_env() is not None


def test_the_variable_names_are_not_the_log_channels(monkeypatch):
    """Deliberately separate, so the two cannot be crossed and either can
    be rotated without touching the other."""
    assert sc.TOKEN_VAR != "TELEGRAM_BOT_TOKEN"
    assert sc.CHAT_VAR != "TELEGRAM_CHAT_ID"


def test_an_aligned_storyline_carries_its_whole_reasoning(sent):
    """"It should be adding the thought process in the message." A line
    saying "EURUSD hunting bullish" cannot be checked against a chart;
    this can."""
    SignalChannel("tok", "chat").storyline(
        "EURUSD", FakeStoryline(direction=Dir("bullish")), previous="waiting_htf")

    text = sent[0][2]
    assert "EURUSD" in text and "ALIGNED" in text and "bullish" in text
    assert "Weekly/Daily/H4 aligned" in text, "the reason itself"
    assert "Weekly  confirmed 2026-09-15" in text
    assert "Daily   confirmed 2026-09-22" in text
    assert "H4      confirmed 2026-09-25" in text
    assert "bias carried by Weekly" in text
    assert "was: waiting_htf" in text
    assert "liquidity taken" in text, "what to watch for next"


def test_a_waiting_storyline_says_why_it_is_waiting(sent):
    SignalChannel("tok", "chat").storyline(
        "GBPJPY",
        FakeStoryline(stage="waiting_htf", direction=None, effective_tf=None,
                      reason="Daily (bullish) and H4 (bearish) disagree -- "
                             "waiting for the 4H to come round to the Daily",
                      weekly_confirmed_at=None),
        previous="hunting")

    text = sent[0][2]
    assert "waiting" in text
    assert "disagree" in text, "the reason is the whole message"
    assert "Now watching H1" not in text, "nothing to hunt while waiting"


def test_a_confirmation_carries_the_numbers_needed_to_judge_it(sent):
    SignalChannel("tok", "chat").confirmation(
        "EURUSD", Dir("bullish"), "engulf", entry=1.16420, stop=1.16375,
        target=1.16980, storyline_reason="Weekly/Daily/H4 aligned bullish",
        level_price=1.16400, liquidity_price=1.16390)

    text = sent[0][2]
    assert "ENGULF" in text and "bullish" in text
    assert "1.1642" in text and "1.16375" in text and "1.1698" in text
    assert "4.5 pips" in text, "risk in pips, not raw price"
    assert "12.4R" in text, "the reward, computed so it need not be"
    assert "key level 1.164" in text
    assert "liquidity taken 1.1639" in text
    assert "Your call" in text


def test_a_confirmation_with_no_target_says_so_rather_than_inventing_one(sent):
    SignalChannel("tok", "chat").confirmation(
        "EURUSD", Dir("bearish"), "sweep_break", entry=1.1000, stop=1.1010,
        target=None)
    assert "no external liquidity" in sent[0][2]


def test_a_setup_message_says_there_is_nothing_to_do_yet(sent):
    SignalChannel("tok", "chat").setup("AUDCAD", Dir("bullish"),
                                        level_price=0.8900, liquidity_price=0.8895)
    text = sent[0][2]
    assert "SETUP" in text and "AUDCAD" in text
    assert "Nothing to do yet" in text


def test_the_label_says_which_engine_spoke(sent):
    """Two engines will be running side by side; a message that does not
    say which one sent it is a message you cannot act on."""
    SignalChannel("tok", "chat", label="SLK").setup(
        "AUDCAD", Dir("bullish"), 0.89, 0.8895)
    assert sent[0][2].startswith("[SLK]")


def test_a_telegram_failure_never_escapes(monkeypatch):
    """A notifier that can take down a trading process is worse than no
    notifier."""
    def boom(*_args, **_kwargs):
        raise RuntimeError("telegram is down")

    monkeypatch.setattr(sc, "send_message", boom)
    assert SignalChannel("tok", "chat").note("hello") is False
