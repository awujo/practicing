import pandas as pd
import pytest

from ..candles import Candle
from ..structure import Direction
from ..liquidity import scf_tag, SequentialLiquidityTracker, structural_liquidity_points


def C(i, o, h, l, c):
    return Candle(pd.Timestamp("2024-01-01") + pd.Timedelta(hours=i), o, h, l, c, 1000)


def test_scf_tag_bullish():
    candle = C(0, 1.10, 1.12, 1.09, 1.11)
    tag = scf_tag(candle, Direction.BULLISH)
    assert tag.irl_price == 1.09  # low = IRL in bullish structure
    assert tag.erl_price == 1.12  # high = ERL


def test_scf_tag_bearish():
    candle = C(0, 1.10, 1.12, 1.09, 1.11)
    tag = scf_tag(candle, Direction.BEARISH)
    assert tag.irl_price == 1.12  # high = IRL in bearish structure
    assert tag.erl_price == 1.09  # low = ERL


def test_sequential_liquidity_flips_target_after_sweep():
    tracker = SequentialLiquidityTracker("daily", high=1.20, low=1.10)
    assert tracker.target_price() is None  # neither side taken yet

    tracker.on_sweep("high")
    assert tracker.next_target == "low"
    assert tracker.target_price() == pytest.approx(1.10)

    tracker.on_sweep("low")
    assert tracker.next_target == "high"
    assert tracker.target_price() == pytest.approx(1.20)


def test_sequential_liquidity_resets_on_new_period():
    tracker = SequentialLiquidityTracker("daily", high=1.20, low=1.10)
    tracker.on_sweep("high")
    tracker.on_new_period(high=1.25, low=1.15)
    assert tracker.next_target is None
    assert tracker.high == pytest.approx(1.25)


def test_structural_liquidity_points_recovers_swing_points():
    candles = [
        C(0, 1.10, 1.105, 1.098, 1.102),
        C(1, 1.102, 1.108, 1.100, 1.106),
        C(2, 1.106, 1.130, 1.104, 1.107),  # clear swing high
        C(3, 1.107, 1.109, 1.103, 1.104),
        C(4, 1.104, 1.106, 1.070, 1.096),  # clear swing low
        C(5, 1.096, 1.100, 1.094, 1.098),
        C(6, 1.098, 1.101, 1.097, 1.099),
    ]
    points = structural_liquidity_points(candles, n=2)
    kinds = [(p.kind, p.price) for p in points]
    assert ("high", 1.130) in kinds
    assert ("low", 1.070) in kinds
