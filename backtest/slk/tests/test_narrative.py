"""
The story behind the bias, in English.

These tests read like the messages will, on purpose: if a sentence here
does not make sense to a person, it will not make sense on a phone.
"""

from __future__ import annotations

from ...engine.structure import Direction
from ..narrative import (account_story, bias_story, confirmation_story,
                         confirmed_sentence,
                         liquidity_taken_sentence, rejection_sentence,
                         setup_story, sweep_sentence)
from ..sweep import Evidence


def test_a_weekly_sweep_says_what_went_and_what_is_still_standing():
    """Operator: "did the previous day or week low get swept and the high
    is standing". The standing side is the half that is easy to leave
    out, and it is the half that says which way price should expand."""
    got = sweep_sentence(
        Evidence(kind="sweep", direction=Direction.BULLISH, at="2026-09-20",
                 taken=1.0820, taken_kind="low", standing=1.1050),
        "Weekly")

    assert "swept a previous weekly low at 1.082" in got
    assert "high at 1.105 is still standing" in got
    assert "expand up" in got, "which way the story says price goes next"
    assert "internal range" in got


def test_a_bearish_sweep_mirrors_it():
    got = sweep_sentence(
        Evidence(kind="sweep", direction=Direction.BEARISH, at="2026-09-20",
                 taken=1.1050, taken_kind="high", standing=1.0820),
        "Daily")
    assert "swept a previous daily high at 1.105" in got
    assert "low at 1.082 is still standing" in got
    assert "expand down" in got


def test_a_sweep_with_no_recorded_other_side_still_reads():
    """The standing price can be missing if the candle predates the
    tracker. The sentence must not break, and must not invent one."""
    got = sweep_sentence(
        Evidence(kind="sweep", direction=Direction.BULLISH, at="2026-09-20",
                 taken=1.0820, taken_kind="low", standing=None),
        "Weekly")
    assert "still standing" not in got
    assert "1.082" in got


def test_a_rejection_says_which_level_and_why_it_is_one():
    got = rejection_sentence(
        Evidence(kind="rejection", direction=Direction.BEARISH,
                 at="2026-09-22", level=1.1650), "Daily")
    assert "Daily rejected from its key level at 1.165" in got
    assert "closed back away" in got
    assert "sells" in got, "a bearish level is used for sells"


def test_the_lower_timeframe_confirmation_is_said_out_loud():
    assert "H4 then broke structure to the upside" in \
        confirmed_sentence("H4", Direction.BULLISH)
    assert "to the downside" in confirmed_sentence("Daily", Direction.BEARISH)


def test_every_line_of_a_bias_story_carries_its_own_date():
    """"The Weekly rejected a key level" with no date cannot be checked
    against a chart, and checking it against a chart is the only thing
    these messages are for."""
    lines = bias_story(
        Evidence(kind="sweep", direction=Direction.BULLISH, at="2026-09-20 00:00",
                 taken=1.0820, taken_kind="low", standing=1.1050,
                 confirmed_at="2026-09-21 00:00", confirmed_price=1.0990),
        higher="Weekly", lower="Daily")

    assert len(lines) == 2
    assert "swept" in lines[0] and "2026-09-20" in lines[0]
    assert "Daily then broke structure to the upside" in lines[1]
    assert "closing through 1.099" in lines[1], "what the confirmation DID"
    assert "2026-09-21" in lines[1], "and when"


def test_the_timeframes_come_from_the_evidence_when_it_knows_them():
    lines = bias_story(Evidence(kind="rejection", direction=Direction.BEARISH,
                                 at="2026-09-22", level=1.1650,
                                 higher="Daily", lower="H4"))
    assert "Daily rejected" in lines[0]
    assert "H4 then broke structure" in lines[1]


def test_an_account_names_which_rung_leads_and_why():
    """The summary this replaces said "key level rejected" for all 27
    instruments, because it read the Daily route every time rather than
    the one that actually carried the answer."""
    from ..cascade import BiasAccount

    account = BiasAccount(
        direction=Direction.BEARISH, rung="Daily",
        evidence=Evidence(kind="rejection", direction=Direction.BEARISH,
                          at="2026-09-22", level=1.1650, higher="Daily",
                          lower="H4", confirmed_at="2026-09-25",
                          confirmed_price=1.1600),
        other_rung="Weekly", other_direction=Direction.BULLISH,
        other_evidence=Evidence(kind="sweep", direction=Direction.BULLISH,
                                 at="2026-09-14", taken=1.0820,
                                 taken_kind="low", standing=1.1050,
                                 higher="Weekly", lower="Daily"),
        dropped_reason="they disagree", alignment="not aligned")
    text = "\n".join(account_story(account, "EURUSD"))

    assert "EURUSD — BEARISH" in text
    assert "Daily says bearish:" in text
    assert "Daily rejected from its key level at 1.165" in text
    assert "2026-09-22" in text
    assert "Weekly says bullish" in text, "the rung that did NOT lead"
    assert "swept a previous weekly low at 1.082" in text
    assert "single candle liquidity" in text, "what to watch next"


def test_disagreement_is_the_headline_and_says_what_it_means():
    """Operator, 2026-09-25: "you know if daily isn't in alignment with
    weekly it's low probability, and it may just be a retracement in the
    weekly."

    The report used to say "Daily leads" on every instrument, which reads
    as though the Weekly were not in the model at all."""
    from ..cascade import BiasAccount

    text = "\n".join(account_story(BiasAccount(
        direction=Direction.BEARISH, rung="Daily",
        evidence=Evidence(kind="rejection", direction=Direction.BEARISH,
                          at="2026-09-22", level=1.1650, higher="Daily",
                          lower="H4"),
        other_rung="Weekly", other_direction=Direction.BULLISH,
        other_evidence=Evidence(kind="sweep", direction=Direction.BULLISH,
                                 at="2026-09-14", taken=1.0820,
                                 taken_kind="low", standing=1.1050,
                                 higher="Weekly", lower="Daily"),
        alignment="not aligned"), "EURUSD"))

    assert "NOT ALIGNED" in text and "lower probability" in text
    assert "retracement inside the Weekly" in text
    assert "targets a nearer liquidity" in text


def test_agreement_is_called_out_as_the_high_probability_case():
    from ..cascade import BiasAccount

    text = "\n".join(account_story(BiasAccount(
        direction=Direction.BULLISH, rung="Daily",
        evidence=Evidence(kind="rejection", direction=Direction.BULLISH,
                          at="2026-09-22", level=1.1650, higher="Daily",
                          lower="H4"),
        other_rung="Weekly", other_direction=Direction.BULLISH,
        other_evidence=Evidence(kind="rejection", direction=Direction.BULLISH,
                                 at="2026-09-14", level=1.1000,
                                 higher="Weekly", lower="Daily"),
        alignment="aligned"), "EURUSD"))

    assert "ALIGNED" in text
    assert "high-probability" in text


def test_a_daily_only_bias_says_the_weekly_has_nothing_yet():
    """Silence about the Weekly is what made it look unmodelled."""
    from ..cascade import BiasAccount

    text = "\n".join(account_story(BiasAccount(
        direction=Direction.BULLISH, rung="Daily",
        evidence=Evidence(kind="rejection", direction=Direction.BULLISH,
                          at="2026-09-22", level=1.1650, higher="Daily",
                          lower="H4"),
        other_rung="Weekly", alignment="daily only"), "EURUSD"))

    assert "no Weekly bias yet" in text
    assert "Weekly: nothing established yet." in text
    assert "Weaker than an aligned setup" in text


def test_an_account_with_no_bias_says_so_plainly():
    from ..cascade import BiasAccount
    assert account_story(BiasAccount(None), "EURUSD") == \
        ["EURUSD: no bias standing."]


def test_no_evidence_is_no_story_rather_than_a_guess():
    assert bias_story(None, "Weekly", "Daily") == []


def test_single_candle_liquidity_is_announced_by_name():
    """The operator asked for this message specifically: "single candle
    liquidity has been taken, okay, look for your confirmation"."""
    lines = liquidity_taken_sentence("EURUSD", Direction.BULLISH,
                                      price=1.16390, level_price=1.16400)
    text = " ".join(lines)
    assert "single candle liquidity has been taken" in text
    assert "the low at 1.1639 went" in text
    assert "nearest key level to it is 1.164" in text
    assert "look for your confirmation" in text.lower()


def test_the_setup_story_names_both_halves():
    lines = setup_story("EURUSD", Direction.BULLISH, liquidity=1.16390,
                        level_price=1.16400)
    text = " ".join(lines)
    assert "single candle liquidity taken: the low at 1.1639" in text
    assert "nearest key level to it: 1.164" in text
    assert "rejected from it" in text


def test_a_setup_still_waiting_says_so():
    lines = setup_story("EURUSD", Direction.BULLISH, 1.16390, 1.16400,
                        rejected=False)
    assert "waiting for price to reach that level" in " ".join(lines)


def test_each_confirmation_form_is_described_not_just_named():
    """A form name is jargon; the description is what makes the message
    checkable by someone who has not memorised my vocabulary."""
    engulf = " ".join(confirmation_story("engulf", 1.1000, 1.0990, 1.1100))
    assert "open-close key level was closed through" in engulf
    assert "10.0R" in engulf, "the reward, computed so it need not be"

    sweep = " ".join(confirmation_story("sweep_break", 1.1, 1.099, None))
    assert "highest-rated entry" in sweep
    assert "no external liquidity standing" in sweep


def test_an_unknown_form_falls_back_to_its_own_name():
    assert "mystery" in " ".join(confirmation_story("mystery", 1.1, 1.09, None))
