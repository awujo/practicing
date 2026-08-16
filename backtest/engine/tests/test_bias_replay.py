import pandas as pd
import pytest

from ..candles import Candle
from ..structure import Direction
from ..key_levels import KeyLevel
from ..bias import replay_bias, bias_at, origin_time_at, Confirmation, ConfirmationKind


def C(i, o, h, l, c):
    return Candle(pd.Timestamp("2024-01-01") + pd.Timedelta(days=i), o, h, l, c, 1000)


def T(days):
    return pd.Timestamp("2024-01-01") + pd.Timedelta(days=days)


def test_replay_bias_stays_put_when_nothing_ever_tests_it():
    candles = [C(i, 1.10, 1.11, 1.09, 1.105) for i in range(5)]
    breakpoints = replay_bias(candles, levels=[], confirmations=[],
                               initial_direction=Direction.BEARISH, timeframe_label="Daily")
    assert breakpoints == [(candles[0].time, Direction.BEARISH)]
    assert bias_at(breakpoints, T(3)) == Direction.BEARISH


def test_replay_bias_flips_when_level_tested_and_no_lower_tf_continuation():
    # Bearish bias; a bearish-biased key level sits at 1.1000. Candle 3
    # trades into it and rejects+closes above (disrespect) -- with no
    # lower-timeframe confirmations left in the original (bearish) direction.
    candles = [
        C(0, 1.120, 1.125, 1.115, 1.118),
        C(1, 1.118, 1.119, 1.108, 1.110),
        C(2, 1.110, 1.112, 1.098, 1.102),
        C(3, 1.099, 1.115, 1.098, 1.112),  # trades into 1.1000-ish and closes back up
    ]
    level = KeyLevel(T(0.5), 1.1000, "A", Direction.BEARISH)

    breakpoints = replay_bias(candles, levels=[level], confirmations=[],
                               initial_direction=Direction.BEARISH, timeframe_label="Daily")

    assert breakpoints[-1][1] == Direction.BULLISH
    assert bias_at(breakpoints, candles[-1].time) == Direction.BULLISH
    assert bias_at(breakpoints, candles[0].time) == Direction.BEARISH  # before the flip


def test_replay_bias_does_not_flip_if_lower_tf_still_confirms_original():
    candles = [
        C(0, 1.120, 1.125, 1.115, 1.118),
        C(1, 1.118, 1.119, 1.108, 1.110),
        C(2, 1.110, 1.112, 1.098, 1.102),
        C(3, 1.099, 1.115, 1.098, 1.112),  # same rejection candle as above
    ]
    level = KeyLevel(T(0.5), 1.1000, "A", Direction.BEARISH)
    # Lower-timeframe confirmation AFTER the rejection still shows bearish continuation.
    still_bearish = Confirmation(candles[3].time + pd.Timedelta(hours=1), Direction.BEARISH,
                                  ConfirmationKind.BREAKOUT, 1.095)

    breakpoints = replay_bias(candles, levels=[level], confirmations=[still_bearish],
                               initial_direction=Direction.BEARISH, timeframe_label="Daily")

    assert breakpoints == [(candles[0].time, Direction.BEARISH)]  # never flipped


def test_bias_at_returns_none_before_any_breakpoint():
    breakpoints = [(T(5), Direction.BULLISH)]
    assert bias_at(breakpoints, T(1)) is None


def test_origin_time_at_returns_the_active_breakpoints_own_time():
    breakpoints = [(T(0), Direction.BEARISH), (T(5), Direction.BULLISH)]
    assert origin_time_at(breakpoints, T(3)) == T(0)   # still the bearish leg
    assert origin_time_at(breakpoints, T(10)) == T(5)  # the bullish leg's own origin


def test_origin_time_at_returns_none_before_any_breakpoint():
    breakpoints = [(T(5), Direction.BULLISH)]
    assert origin_time_at(breakpoints, T(1)) is None
