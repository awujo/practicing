"""
The morning watchlist.
"""

from __future__ import annotations

from ..roll_call import ALIGNED, DAILY_ONLY, NOT_ALIGNED, line_for, roll_call


class Dir:
    def __init__(self, value):
        self.value = value


class Account:
    def __init__(self, direction, alignment, other=None):
        self.direction = direction
        self.alignment = alignment
        self.other_direction = other


def test_aligned_pairs_come_first_because_they_are_the_days_focus():
    """Operator: "know the pairs to put in my watch list, know the ones
    to remove, know the ones I'll be focusing on that day"."""
    text = roll_call("[SLK]", "DAILY ROLL CALL", [
        ("USDCHF", Account(Dir("bullish"), DAILY_ONLY)),
        ("EURUSD", Account(Dir("bearish"), ALIGNED)),
        ("GBPJPY", Account(Dir("bullish"), NOT_ALIGNED, Dir("bearish"))),
    ])
    assert text.index("ALIGNED —") < text.index("NOT ALIGNED —")
    assert text.index("NOT ALIGNED —") < text.index("DAILY ONLY")
    assert "EURUSD" in text and "GBPJPY" in text and "USDCHF" in text


def test_a_not_aligned_line_says_what_the_weekly_thinks():
    """Otherwise the reader cannot tell which way the retracement runs."""
    line = line_for("GBPJPY", Account(Dir("bullish"), NOT_ALIGNED,
                                       Dir("bearish")))
    assert "bullish" in line and "Weekly bearish" in line


def test_pairs_with_no_bias_are_named_so_they_can_be_dropped():
    """Knowing which pairs to IGNORE today is half a watchlist."""
    text = roll_call("[SLK]", "DAILY ROLL CALL", [
        ("EURUSD", Account(Dir("bearish"), ALIGNED)),
        ("USOIL", None),
        ("ETHUSD", Account(None, "")),
    ])
    assert "NO BIAS (2)" in text
    assert "ETHUSD, USOIL" in text, "named, sorted, and not detailed"


def test_the_count_of_focus_pairs_is_stated():
    text = roll_call("[SLK]", "DAILY ROLL CALL", [
        ("EURUSD", Account(Dir("bearish"), ALIGNED)),
        ("AUDCAD", Account(Dir("bullish"), ALIGNED)),
        ("USOIL", None),
    ])
    assert "2 pair(s) with both timeframes agreeing." in text


def test_an_empty_book_still_produces_a_readable_message():
    text = roll_call("[SLK]", "DAILY ROLL CALL", [])
    assert "DAILY ROLL CALL" in text
    assert "0 pair(s)" in text


def test_the_label_says_which_engine_spoke():
    """Two engines send this; a roll call that does not say which one is
    a roll call you cannot act on."""
    assert roll_call("[SLK]", "X", []).startswith("[SLK]")
    assert roll_call("[aggressive]", "X", []).startswith("[aggressive]")
