import pandas as pd
import pytest

from ..candles import Candle
from ..structure import Direction, StructureTracker, body_closes_beyond, wick_sweeps_without_close


def C(i, o, h, l, c):
    return Candle(pd.Timestamp("2024-01-01") + pd.Timedelta(hours=i), o, h, l, c, 1000)


def test_body_close_vs_wick_sweep_bullish():
    level = 1.1000
    wick_only = C(0, 1.1010, 1.1010, 0.9990, 1.1005)  # wicks below, closes back above
    closed_through = C(0, 1.1010, 1.1010, 0.9990, 0.9995)  # closes below the level

    assert wick_sweeps_without_close(wick_only, level, Direction.BEARISH)
    assert not body_closes_beyond(wick_only, level, Direction.BEARISH)
    assert body_closes_beyond(closed_through, level, Direction.BEARISH)
    assert not wick_sweeps_without_close(closed_through, level, Direction.BEARISH)


def test_bullish_sweep_and_break_produces_strong_low():
    """
    Construct: a swing low forms, then later price wicks below it (sweep)
    and closes back above the swing high that was in place at sweep time
    (break) -- should emit sweep + valid_sweep_break and set strong_low to
    the swept point.
    """
    candles = [
        C(0, 1.100, 1.105, 1.098, 1.102),
        C(1, 1.102, 1.108, 1.100, 1.106),
        C(2, 1.106, 1.112, 1.104, 1.107),  # confirmed swing high (n=2): high=1.112
        C(3, 1.107, 1.109, 1.102, 1.104),
        C(4, 1.104, 1.106, 1.095, 1.096),  # confirmed swing low (n=2): low=1.095
        C(5, 1.096, 1.099, 1.097, 1.098),
        C(6, 1.098, 1.101, 1.097, 1.099),
        # sweep: wicks below the swing low (1.095) without closing beyond it
        C(7, 1.099, 1.100, 1.090, 1.097),
        # break: closes back above the swing high (1.112)
        C(8, 1.097, 1.120, 1.096, 1.115),
    ]

    tracker = StructureTracker(n=2)
    events = tracker.run(candles)

    kinds = [(e.kind, e.direction) for e in events]
    assert ("sweep", Direction.BULLISH) in kinds
    assert ("valid_sweep_break", Direction.BULLISH) in kinds
    assert tracker.strong_low is not None
    assert tracker.strong_low.price == pytest.approx(1.090)


def test_wick_only_sweep_does_not_confirm_break():
    """A wick-sweep with no subsequent close-through should never emit valid_sweep_break."""
    candles = [
        C(0, 1.10, 1.105, 1.098, 1.102),
        C(1, 1.102, 1.108, 1.100, 1.106),
        C(2, 1.106, 1.110, 1.104, 1.107),
        C(3, 1.107, 1.109, 1.103, 1.104),
        C(4, 1.104, 1.106, 1.095, 1.096),
        C(5, 1.096, 1.100, 1.094, 1.098),
        C(6, 1.098, 1.101, 1.097, 1.099),
        C(7, 1.099, 1.100, 1.090, 1.097),  # sweeps below prior low, but never closes back above 1.110
        C(8, 1.097, 1.099, 1.093, 1.095),
        C(9, 1.095, 1.098, 1.092, 1.094),
    ]

    tracker = StructureTracker(n=2)
    events = tracker.run(candles)

    assert all(e.kind != "valid_sweep_break" for e in events)
    assert tracker.strong_low is None


# --- close_based_break -----------------------------------------------------
#
# Same class of line-chart-vs-wick question already settled for the plain
# breakout (detect_confirmations' close_based_breakout): the SWEEP stays
# wick-based either way (a sweep is legitimately a wick event -- video-07's
# notes: "a mere sweep without a close-through does not invalidate it"),
# but the LEVEL a break is measured against can be read off the swing
# candle's close (line chart) instead of its wick.

def test_close_based_break_confirms_where_wick_based_does_not_yet():
    """idx2's swing high has a big upper wick (1.112) but closes much
    lower (1.107). idx8 closes at 1.109 -- beyond the swing's CLOSE but
    still short of its WICK -- so close_based_break=True must confirm
    the break right there while the default (wick-based) does not."""
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

    def _kinds(events):
        return [(e.kind, e.direction) for e in events]

    wick_events = StructureTracker(n=2, close_based_break=False).run(candles)
    assert ("valid_sweep_break", Direction.BULLISH) not in _kinds(wick_events)

    close_events = StructureTracker(n=2, close_based_break=True).run(candles)
    assert ("valid_sweep_break", Direction.BULLISH) in _kinds(close_events)


def test_close_based_break_default_is_unchanged_wick_behavior():
    """close_based_break defaults to False -- omitting it entirely must
    reproduce the exact same result as passing False explicitly."""
    candles = [
        C(0, 1.100, 1.105, 1.098, 1.102),
        C(1, 1.102, 1.108, 1.100, 1.106),
        C(2, 1.106, 1.112, 1.104, 1.107),
        C(3, 1.107, 1.109, 1.102, 1.104),
        C(4, 1.104, 1.106, 1.095, 1.096),
        C(5, 1.096, 1.099, 1.097, 1.098),
        C(6, 1.098, 1.101, 1.097, 1.099),
        C(7, 1.099, 1.100, 1.090, 1.097),
        C(8, 1.097, 1.120, 1.096, 1.115),
    ]
    default_events = StructureTracker(n=2).run(candles)
    explicit_events = StructureTracker(n=2, close_based_break=False).run(candles)
    assert default_events == explicit_events
