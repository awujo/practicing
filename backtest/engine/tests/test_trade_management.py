import pandas as pd
import pytest

from ..structure import Direction
from ..trade_management import (
    PositionManager, primary_target, tiered_exit_targets, conservative_countertrend_target,
)


def T(hours):
    return pd.Timestamp("2024-01-01") + pd.Timedelta(hours=hours)


def test_stacking_allows_multiple_concurrent_same_direction_positions():
    mgr = PositionManager()
    p1 = mgr.open_position(Direction.BULLISH, 1.1000, 1.0990, T(0), "4H")
    p2 = mgr.open_position(Direction.BULLISH, 1.1010, 1.1000, T(1), "1H")  # stacked entry, original still live

    open_bullish = mgr.open_positions(Direction.BULLISH)
    assert len(open_bullish) == 2
    assert p1 in open_bullish and p2 in open_bullish


def test_closing_one_stacked_position_leaves_the_other_open():
    mgr = PositionManager()
    p1 = mgr.open_position(Direction.BULLISH, 1.1000, 1.0990, T(0), "4H")
    p2 = mgr.open_position(Direction.BULLISH, 1.1010, 1.1000, T(1), "1H")

    mgr.close_position(p1, "closed_win")

    open_bullish = mgr.open_positions(Direction.BULLISH)
    assert open_bullish == [p2]


def test_open_positions_filters_by_direction():
    mgr = PositionManager()
    mgr.open_position(Direction.BULLISH, 1.1000, 1.0990, T(0), "4H")
    mgr.open_position(Direction.BEARISH, 1.2000, 1.2010, T(1), "4H")

    assert len(mgr.open_positions(Direction.BULLISH)) == 1
    assert len(mgr.open_positions(Direction.BEARISH)) == 1
    assert len(mgr.open_positions()) == 2


def test_primary_target_is_1_to_3():
    entry, stop = 1.1000, 1.0990  # 10 pip risk
    target = primary_target(entry, stop, Direction.BULLISH)
    assert target == pytest.approx(1.1030)  # 30 pips = 3x risk

    target_bear = primary_target(1.1000, 1.1010, Direction.BEARISH)
    assert target_bear == pytest.approx(1.0970)


def test_primary_target_is_capped_by_a_closer_erl_price():
    entry, stop = 1.1000, 1.0990  # 10 pip risk -> plain 1:3 target would be 1.1030
    # ERL sits BEFORE the plain target -- caps there instead.
    capped = primary_target(entry, stop, Direction.BULLISH, erl_price=1.1020)
    assert capped == pytest.approx(1.1020)

    # ERL sits BEYOND the plain target -- doesn't change anything (the
    # plain 1:3 ratio is still the tighter, binding constraint).
    uncapped = primary_target(entry, stop, Direction.BULLISH, erl_price=1.1080)
    assert uncapped == pytest.approx(1.1030)

    # Bearish mirror.
    capped_bear = primary_target(1.1000, 1.1010, Direction.BEARISH, erl_price=1.0985)
    assert capped_bear == pytest.approx(1.0985)


def test_tiered_exit_targets():
    tiers = tiered_exit_targets(entry_timeframe_erl=1.1050, origin_timeframe_next_key_level=1.1200)
    assert tiers.partial_target == pytest.approx(1.1050)
    assert tiers.ultimate_target == pytest.approx(1.1200)


def test_conservative_countertrend_target_caps_at_nearest_liquidity():
    capped = conservative_countertrend_target(
        nearest_liquidity=1.1050, opposite_structure_extreme=1.0800, is_countertrend=True
    )
    assert capped == pytest.approx(1.1050)

    uncapped = conservative_countertrend_target(
        nearest_liquidity=1.1050, opposite_structure_extreme=1.0800, is_countertrend=False
    )
    assert uncapped == pytest.approx(1.0800)
