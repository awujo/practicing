"""Tests for setup_validity.check_setup().

Includes the two real signals from the 2026-09-01 incident, replayed with
their actual audited numbers, because the whole point of this module is
to make the right call on exactly those.
"""

from dataclasses import dataclass

import pandas as pd
import pytest

from backtest.engine.structure import Direction
from bot.setup_validity import Validity, check_setup


@dataclass(frozen=True)
class Bar:
    """Minimal stand-in -- check_setup only reads high/low/time."""
    high: float
    low: float
    time: str = "T"


def test_fresh_signal_is_alive():
    v = check_setup(1.1000, 1.0990, 1.1030, Direction.BULLISH, [])
    assert v.alive
    assert not v.entry_revisited


def test_long_stop_breached_is_dead():
    bars = [Bar(high=1.1005, low=1.0985)]
    v = check_setup(1.1000, 1.0990, 1.1030, Direction.BULLISH, bars)
    assert v.validity is Validity.STOP_BREACHED
    assert not v.alive


def test_short_stop_breached_is_dead():
    bars = [Bar(high=1.1015, low=1.0995)]
    v = check_setup(1.1000, 1.1010, 1.0970, Direction.BEARISH, bars)
    assert v.validity is Validity.STOP_BREACHED


def test_long_target_mostly_achieved_is_dead():
    # reward 30 pips; 80% of it is 1.1024. A high of 1.1025 clears it.
    bars = [Bar(high=1.1025, low=1.1000)]
    v = check_setup(1.1000, 1.0990, 1.1030, Direction.BULLISH, bars)
    assert v.validity is Validity.TARGET_ACHIEVED


def test_long_target_not_quite_achieved_stays_alive():
    # 1.1020 is 67% of the way -- under the 80% threshold.
    bars = [Bar(high=1.1020, low=1.1000)]
    v = check_setup(1.1000, 1.0990, 1.1030, Direction.BULLISH, bars)
    assert v.alive


def test_short_target_mostly_achieved_is_dead():
    bars = [Bar(high=1.1000, low=1.0975)]
    v = check_setup(1.1000, 1.1010, 1.0970, Direction.BEARISH, bars)
    assert v.validity is Validity.TARGET_ACHIEVED


def test_alive_and_entry_never_revisited():
    """The case the old code threw away: price simply hasn't come back."""
    bars = [Bar(high=1.1008, low=1.1002)]
    v = check_setup(1.1000, 1.0990, 1.1030, Direction.BULLISH, bars)
    assert v.alive
    assert not v.entry_revisited
    assert "not returned" in v.reason


def test_alive_and_entry_revisited():
    bars = [Bar(high=1.1008, low=1.0999)]
    v = check_setup(1.1000, 1.0990, 1.1030, Direction.BULLISH, bars)
    assert v.alive
    assert v.entry_revisited


def test_stop_wins_when_one_candle_spans_both():
    """A candle covering stop AND target resolves as the loss.

    Must match `_resolve_trade_outcome()`'s handling of the same
    ambiguity in the backtest -- the two must not disagree about
    identical price action.
    """
    bars = [Bar(high=1.1030, low=1.0985)]
    v = check_setup(1.1000, 1.0990, 1.1030, Direction.BULLISH, bars)
    assert v.validity is Validity.STOP_BREACHED


def test_earlier_candle_decides_before_a_later_one():
    bars = [Bar(high=1.1005, low=1.0985, time="first"),
            Bar(high=1.1030, low=1.1000, time="second")]
    v = check_setup(1.1000, 1.0990, 1.1030, Direction.BULLISH, bars)
    assert v.validity is Validity.STOP_BREACHED
    assert "first" in v.reason


def test_degenerate_target_at_entry_does_not_divide_by_zero():
    bars = [Bar(high=1.1050, low=1.0995)]
    v = check_setup(1.1000, 1.0990, 1.1000, Direction.BULLISH, bars)
    assert v.alive


# --- the real 2026-09-01 signals, from the audit database ---

def test_chfjpy_short_the_actual_incident():
    """CHFJPY 17:00 signal: entry 197.8515, stop 198.101 (both audited).

    Sent at 18:58 as a market order and filled ~197.336 -- 50 pips past
    its own entry, carrying a stop sized for a price it never opened at,
    leaving risk ~0.76 against reward ~0.23.

    The verdict here is ALIVE with the entry revisited, and that is the
    whole argument for resting limits: price traded back UP through
    197.8515 (the 18:00 bar's high) before continuing down, so a limit at
    the computed entry fills at the price the setup was actually sized
    for. The 50-pip drift is not detected and declined -- it never
    happens.

    Target is not in the audit row, so it is derived the way the engine
    would: rr=3 on the 0.2495 stop distance -> 197.103.
    """
    entry, stop, target = 197.8515, 198.101, 197.103
    bars = [Bar(high=197.86, low=197.60, time="18:00"),
            Bar(high=197.62, low=197.33, time="18:58")]
    v = check_setup(entry, stop, target, Direction.BEARISH, bars)
    assert v.alive
    assert v.entry_revisited
    # 197.33 is only ~69% of the way to target -- real room still left.
    assert v.validity is Validity.ALIVE


def test_eurgbp_long_still_waiting_would_now_be_kept():
    """EURGBP: entry 0.85574, stop 0.85564 (the 1-pip fallback stop).

    Its stop is indefensible and is fixed elsewhere, but the SETUP was
    never invalidated -- price drifted above the entry without ever
    returning. The old code market-ordered it into an INVALID_STOPS
    rejection; the right answer is that it is alive and belongs on a
    resting limit.
    """
    bars = [Bar(high=0.85610, low=0.85580, time="19:00"),
            Bar(high=0.85625, low=0.85592, time="20:00")]
    v = check_setup(0.85574, 0.85564, 0.85720, Direction.BULLISH, bars)
    assert v.alive
    assert not v.entry_revisited


def test_works_with_real_backtest_candles():
    """Guards the duck-typed interface against the engine's own Candle."""
    from backtest.engine.candles import Candle
    bars = [Candle(pd.Timestamp("2026-09-01T18:00Z"), 1.10, 1.1005, 1.0985, 1.099, 0.0)]
    v = check_setup(1.1000, 1.0990, 1.1030, Direction.BULLISH, bars)
    assert v.validity is Validity.STOP_BREACHED
