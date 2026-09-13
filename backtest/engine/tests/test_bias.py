import pandas as pd
import pytest

from ..candles import Candle
from ..structure import Direction
from ..key_levels import KeyLevel
from ..bias import (
    detect_confirmations, ConfirmationKind, BiasCascade, resolve_effective_bias,
)


def C(i, o, h, l, c):
    return Candle(pd.Timestamp("2024-01-01") + pd.Timedelta(hours=i), o, h, l, c, 1000)


def T(hours):
    return pd.Timestamp("2024-01-01") + pd.Timedelta(hours=hours)


def test_plain_breakout_detected_without_prior_sweep():
    # A clean, direct push through a swing high with no prior wick-sweep-and-reverse.
    candles = [
        C(0, 1.100, 1.105, 1.098, 1.102),
        C(1, 1.102, 1.108, 1.100, 1.106),
        C(2, 1.106, 1.112, 1.104, 1.107),  # swing high, high=1.112
        C(3, 1.107, 1.109, 1.102, 1.104),
        C(4, 1.104, 1.106, 1.100, 1.103),
        C(5, 1.103, 1.108, 1.101, 1.105),
        C(6, 1.105, 1.115, 1.104, 1.113),  # closes straight through 1.112 -- plain breakout
    ]
    confirmations = detect_confirmations(candles, n=2)
    breakouts = [c for c in confirmations if c.kind == ConfirmationKind.BREAKOUT]
    sweep_breaks = [c for c in confirmations if c.kind == ConfirmationKind.SWEEP_BREAK]

    assert any(c.direction == Direction.BULLISH for c in breakouts)
    assert sweep_breaks == []  # no sweep ever happened, so nothing should be tagged sweep_break


def test_plain_breakout_uses_the_swing_candles_close_not_its_wick():
    # Direct user correction: SLK reads breakouts off the LINE CHART (closing
    # prices) throughout, matching how A/V-shape key levels already work --
    # not the swing candle's wick. A later candle that closes beyond the
    # swing candle's CLOSE (1.107) but not beyond its wick HIGH (1.112) must
    # still count as a breakout.
    candles = [
        C(0, 1.100, 1.105, 1.098, 1.102),
        C(1, 1.102, 1.108, 1.100, 1.106),
        C(2, 1.106, 1.112, 1.104, 1.107),  # swing high: wick high=1.112, close=1.107
        C(3, 1.107, 1.109, 1.102, 1.104),
        C(4, 1.104, 1.106, 1.100, 1.103),
        C(5, 1.103, 1.108, 1.101, 1.105),
        C(6, 1.105, 1.111, 1.104, 1.109),  # closes at 1.109: beyond the swing's CLOSE, not its wick
    ]
    confirmations = detect_confirmations(candles, n=2)
    breakouts = [c for c in confirmations if c.kind == ConfirmationKind.BREAKOUT]
    assert any(c.direction == Direction.BULLISH and c.time == T(6) for c in breakouts)


def test_sweep_break_not_double_counted_as_breakout():
    # Reuses Phase 1's exact sweep+break sequence -- must be tagged SWEEP_BREAK only, not also BREAKOUT.
    candles = [
        C(0, 1.100, 1.105, 1.098, 1.102),
        C(1, 1.102, 1.108, 1.100, 1.106),
        C(2, 1.106, 1.112, 1.104, 1.107),  # swing high: 1.112
        C(3, 1.107, 1.109, 1.102, 1.104),
        C(4, 1.104, 1.106, 1.095, 1.096),  # swing low: 1.095
        C(5, 1.096, 1.099, 1.097, 1.098),
        C(6, 1.098, 1.101, 1.097, 1.099),
        C(7, 1.099, 1.100, 1.090, 1.097),  # sweep below 1.095
        C(8, 1.097, 1.120, 1.096, 1.115),  # closes back above 1.112 -- sweep+break bullish
    ]
    confirmations = detect_confirmations(candles, n=2)
    at_break_candle = [c for c in confirmations if c.time == T(8)]

    assert len(at_break_candle) == 1
    assert at_break_candle[0].kind == ConfirmationKind.SWEEP_BREAK


def test_close_based_sweep_break_confirms_where_wick_based_does_not_yet():
    """Same line-chart-vs-wick question as the plain breakout, applied to
    the sweep+break half instead -- passed through from detect_confirmations()
    into StructureTracker's own close_based_break."""
    candles = [
        C(0, 1.100, 1.105, 1.098, 1.102),
        C(1, 1.102, 1.108, 1.100, 1.106),
        C(2, 1.106, 1.112, 1.104, 1.107),  # swing high: wick 1.112, close 1.107
        C(3, 1.107, 1.109, 1.102, 1.104),
        C(4, 1.104, 1.106, 1.095, 1.096),  # swing low: 1.095
        C(5, 1.096, 1.099, 1.097, 1.098),
        C(6, 1.098, 1.101, 1.097, 1.099),
        C(7, 1.099, 1.100, 1.090, 1.097),  # sweeps below 1.095
        C(8, 1.097, 1.110, 1.096, 1.109),  # closes 1.109: past the swing's close, not its wick
    ]
    default_confirmations = detect_confirmations(candles, n=2)
    assert not any(c.kind == ConfirmationKind.SWEEP_BREAK and c.direction == Direction.BULLISH
                    for c in default_confirmations)

    close_based = detect_confirmations(candles, n=2, close_based_sweep_break=True)
    assert any(c.kind == ConfirmationKind.SWEEP_BREAK and c.direction == Direction.BULLISH
               for c in close_based)


def test_bias_flips_when_rejection_and_no_lower_tf_continuation():
    cascade = BiasCascade("Daily")
    cascade.set_initial_bias(Direction.BEARISH, T(0))

    next_key_level = KeyLevel(T(1), 1.1000, "A", Direction.BEARISH)
    rejection_candle = C(2, 1.099, 1.105, 1.098, 1.103)  # closes ABOVE 1.1000 -- rejects+closes new direction

    # Lower timeframe shows nothing continuing the OLD (bearish) direction.
    lower_tf_confirmations = []

    flipped = cascade.check_flip(next_key_level, rejection_candle, lower_tf_confirmations)

    assert flipped is True
    assert cascade.direction == Direction.BULLISH


def test_bias_does_not_flip_when_lower_tf_still_confirms_original_direction():
    cascade = BiasCascade("Daily")
    cascade.set_initial_bias(Direction.BEARISH, T(0))

    next_key_level = KeyLevel(T(1), 1.1000, "A", Direction.BEARISH)
    rejection_candle = C(2, 1.099, 1.105, 1.098, 1.103)  # rejects+closes new direction

    from ..bias import Confirmation
    # Lower timeframe STILL shows a bearish (original-direction) confirmation.
    lower_tf_confirmations = [Confirmation(T(3), Direction.BEARISH, ConfirmationKind.BREAKOUT, 1.090)]

    flipped = cascade.check_flip(next_key_level, rejection_candle, lower_tf_confirmations)

    assert flipped is False
    assert cascade.direction == Direction.BEARISH  # unchanged -- Video 16's resolved ambiguity


def test_bias_does_not_flip_without_rejection():
    cascade = BiasCascade("Daily")
    cascade.set_initial_bias(Direction.BEARISH, T(0))

    next_key_level = KeyLevel(T(1), 1.1000, "A", Direction.BEARISH)
    no_rejection_candle = C(2, 1.098, 1.099, 1.095, 1.097)  # still closes below 1.1000 -- respects, no rejection

    flipped = cascade.check_flip(next_key_level, no_rejection_candle, [])

    assert flipped is False
    assert cascade.direction == Direction.BEARISH


def test_weekly_beats_daily_in_priority_hierarchy():
    biases = {"Monthly": None, "Weekly": Direction.BEARISH, "Daily": Direction.BULLISH, "H4": Direction.BULLISH}
    direction, source_tf = resolve_effective_bias(biases)
    assert direction == Direction.BEARISH
    assert source_tf == "Weekly"


def test_falls_through_to_lower_timeframe_when_higher_ones_have_no_bias():
    biases = {"Monthly": None, "Weekly": None, "Daily": None, "H4": Direction.BULLISH}
    direction, source_tf = resolve_effective_bias(biases)
    assert direction == Direction.BULLISH
    assert source_tf == "H4"
