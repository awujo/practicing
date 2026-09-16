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


# ---------------------------------------------------------------------------
# single_candle_liquidity -- the SLK "single candle liquidity" concept.
#
# These exist because the entry path used to source this concept from
# structural_liquidity_points(h4, n=1), i.e. from a fractal swing
# detector, and that is simply a different thing. The decisive test is
# test_real_gbpusd_level_that_swing_detection_cannot_see below: real
# cached candles, a level the trader drew and price actually took, which
# the swing detector provably cannot return.
# ---------------------------------------------------------------------------

def test_every_candle_supplies_a_pool_not_just_swing_points():
    # Strictly rising lows: a fractal detector finds NOTHING here.
    candles = [C(0, 10, 11, 9.0, 10.5),
               C(1, 10.5, 11.5, 9.5, 11.0),
               C(2, 11, 12, 10.0, 11.5)]
    from ..liquidity import single_candle_liquidity
    pools = single_candle_liquidity(candles, "low")
    assert [p.price for p in pools] == [9.0, 9.5, 10.0]
    assert structural_liquidity_points(candles, n=1) == []


def test_highs_for_the_sell_side():
    from ..liquidity import single_candle_liquidity
    candles = [C(0, 10, 11, 9, 10.5), C(1, 10.5, 11.5, 9.5, 11.0)]
    pools = single_candle_liquidity(candles, "high")
    assert [p.price for p in pools] == [11, 11.5]
    assert all(p.kind == "high" for p in pools)


def test_pool_is_not_known_until_its_candle_has_closed():
    """The self-sweep guard: a candle cannot take the low it just made."""
    from ..liquidity import single_candle_liquidity
    candles = [C(0, 10, 11, 9, 10.5), C(1, 10.5, 11.5, 9.5, 11.0)]
    pools = single_candle_liquidity(candles, "low")
    assert pools[0].time == candles[0].time
    assert pools[0].known_at == candles[1].time  # next bar's open, not its own
    assert pools[0].known_at > pools[0].time


def test_last_candle_pool_is_not_yet_usable():
    from ..liquidity import single_candle_liquidity
    candles = [C(0, 10, 11, 9, 10.5), C(1, 10.5, 11.5, 9.5, 11.0)]
    pools = single_candle_liquidity(candles, "low")
    # No next bar exists, so known_at carries this bar's own width forward.
    assert pools[-1].known_at == candles[-1].time + pd.Timedelta(hours=1)


def test_start_and_limit_bound_the_window():
    from ..liquidity import single_candle_liquidity
    candles = [C(i, 10 + i, 11 + i, 9 + i, 10.5 + i) for i in range(10)]
    assert len(single_candle_liquidity(candles, "low", start=4)) == 6
    assert len(single_candle_liquidity(candles, "low", start=4, limit=2)) == 2
    assert [p.price for p in single_candle_liquidity(candles, "low", start=4, limit=2)] == [13, 14]
    # limit running past the end is clamped, not an error
    assert len(single_candle_liquidity(candles, "low", start=8, limit=50)) == 2


def test_rejects_a_bad_kind():
    from ..liquidity import single_candle_liquidity
    with pytest.raises(ValueError):
        single_candle_liquidity([C(0, 10, 11, 9, 10.5)], "close")


def test_real_gbpusd_level_that_swing_detection_cannot_see():
    """GBPUSD H4, 2026-08-09 20:00 .. 2026-08-11 00:00, from the
    production Dukascopy cache.

    The breakout is 08-10 12:00 (high 1.35303). The candle after it
    leaves low 1.35050 -- the level the trader drew. Price returned at
    08-10 20:00 to 1.35012 and closed back up at 1.35105: taken and
    reacted.

    structural_liquidity_points() cannot return 1.35050, because
    is_swing_low needs low <= both neighbours and 1.35050 > 1.34899. The
    only low it CAN return in this stretch is the breakout candle's own
    1.34899, which price never revisited -- so the bot armed a level that
    was never going to be touched and took no trade."""
    from ..liquidity import single_candle_liquidity
    rows = [(1.34898, 1.34965, 1.34806, 1.34883),
            (1.34884, 1.34935, 1.34829, 1.34846),
            (1.34847, 1.35011, 1.34834, 1.34957),
            (1.34957, 1.35064, 1.34922, 1.35009),
            (1.35008, 1.35303, 1.34899, 1.35254),   # 4: breakout
            (1.35254, 1.35266, 1.35050, 1.35077),   # 5: leaves the pool
            (1.35077, 1.35111, 1.35012, 1.35105),   # 6: takes it, closes back up
            (1.35105, 1.35150, 1.35023, 1.35099)]
    gbp = [C(i * 4, o, h, l, c) for i, (o, h, l, c) in enumerate(rows)]

    pools = single_candle_liquidity(gbp, "low", start=5)
    assert pools[0].price == pytest.approx(1.35050)
    # usable only from the NEXT bar, which is the one that sweeps it
    assert pools[0].known_at == gbp[6].time
    assert gbp[6].low < pools[0].price          # genuinely taken
    assert gbp[6].close > pools[0].price        # and reacted back above

    swing_lows = [p.price for p in structural_liquidity_points(gbp, n=1) if p.kind == "low"]
    assert 1.35050 not in swing_lows
    assert pytest.approx(1.34899) in swing_lows  # the breakout candle's own low
    assert min(c.low for c in gbp[5:]) > 1.34899  # which price never went back to
