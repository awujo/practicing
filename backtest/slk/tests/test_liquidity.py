"""
External range liquidity: a previous period's own extreme, still
standing.
"""

from __future__ import annotations

import pandas as pd

from ...engine.candles import Candle
from ...engine.structure import Direction
from ..liquidity import target_for, untaken_extremes

T0 = pd.Timestamp("2026-01-01")


def d(i, o, h, l, c):
    return Candle(time=T0 + pd.Timedelta(days=i), open=o, high=h, low=l,
                  close=c, volume=0)


def test_a_high_that_a_later_period_traded_through_is_gone():
    """Taken liquidity is not a target. bd2: "after external liquidity
    is taken, expect a reversal"."""
    days = [d(0, 1.10, 1.15, 1.09, 1.12),    # high 1.15
            d(1, 1.12, 1.13, 1.11, 1.12),    # 1.13 -- also taken, by day 2
            d(2, 1.12, 1.18, 1.11, 1.17),    # trades through both
            d(3, 1.17, 1.19, 1.16, 1.18)]    # still forming -- excluded
    standing = untaken_extremes(days, "high")

    assert 1.15 not in standing, "day 2 traded through it"
    assert 1.13 not in standing, "day 2 traded through this one too"
    assert standing == [1.18], "only the last closed day's high still stands"


def test_the_period_containing_now_is_never_a_previous_high():
    """A period that has not closed is not a "previous" anything -- and
    its cached high is the FINAL one, which is how a backtest reads
    tomorrow by accident."""
    days = [d(0, 1.10, 1.15, 1.09, 1.12), d(1, 1.12, 1.30, 1.11, 1.29)]
    assert 1.30 not in untaken_extremes(days, "high")
    assert untaken_extremes(days, "high") == [1.15]


def test_too_little_history_yields_nothing_rather_than_guessing():
    assert untaken_extremes([], "high") == []
    assert untaken_extremes([d(0, 1.1, 1.2, 1.0, 1.15)], "high") == []


def test_the_target_is_the_nearest_untaken_liquidity_beyond_entry():
    """"The FIRST target" -- nearest, not furthest. There is no reason
    to hold past it."""
    days = [d(0, 1.10, 1.20, 1.09, 1.12),    # 1.20 standing
            d(1, 1.12, 1.16, 1.11, 1.15),    # 1.16 standing
            d(2, 1.15, 1.155, 1.14, 1.15)]   # forming, excluded
    got = target_for(1.13, Direction.BULLISH, days)
    assert got == 1.16, "nearest beyond entry, not the 1.20"


def test_no_liquidity_in_that_direction_returns_none_not_a_ratio():
    """R multiples are outputs in this course, never inputs. A caller
    that cannot name a target must not invent one."""
    days = [d(0, 1.10, 1.12, 1.09, 1.11), d(1, 1.11, 1.13, 1.10, 1.12),
            d(2, 1.12, 1.125, 1.115, 1.12)]
    assert target_for(1.50, Direction.BULLISH, days) is None


def test_daily_and_weekly_are_searched_together_and_nearest_wins():
    daily = [d(0, 1.10, 1.18, 1.09, 1.12),      # 1.18 stands
             d(1, 1.12, 1.14, 1.11, 1.13),      # 1.14 stands, but below entry
             d(2, 1.13, 1.135, 1.125, 1.13)]    # forming, excluded
    weekly = [d(0, 1.10, 1.16, 1.05, 1.12),     # 1.16 taken by the next week
              d(7, 1.12, 1.17, 1.11, 1.15),     # 1.17 stands
              d(14, 1.15, 1.155, 1.145, 1.15)]  # forming, excluded

    assert untaken_extremes(weekly, "high") == [1.17], "1.16 was traded through"
    got = target_for(1.14, Direction.BULLISH, daily, weekly)
    assert got == 1.17, "the weekly 1.17 is nearer than the daily 1.18"
