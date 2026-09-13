import pandas as pd
import pytest

from ...data_pipeline import cache
from ..candles import Candle
from ..structure import Direction
from ..bias import detect_confirmations, Confirmation, ConfirmationKind
from ..key_levels import detect_key_levels
from ..entries import imbalance_stop_loss
from ..runner import (
    run_backtest, _stop_on_correct_side, _find_liquidity_setups, _find_entry_candidates,
    _aligned_timeframes, _reaction_trigger, _natural_stop_too_wide, _nearest_erl, _unswept_period_extremes,
    _resolve_date_range, _parse_rr, _resolve_trade_outcome, _reaction_leg_extreme, _bootstrap_origin,
)
from ..structure import StructureEvent
from ..bias import Confirmation, ConfirmationKind

SOURCE = "test"
SYMBOL = "RUNNERPAIR"


def D(i, o, h, l, c):
    return Candle(pd.Timestamp("2024-01-01") + pd.Timedelta(days=i), o, h, l, c, 1000)


def H4(i, o, h, l, c):
    return Candle(pd.Timestamp("2024-01-01") + pd.Timedelta(hours=4 * i), o, h, l, c, 1000)


def W(i, o, h, l, c):
    return Candle(pd.Timestamp("2023-01-01") + pd.Timedelta(weeks=i), o, h, l, c, 1000)


H1_BASE = pd.Timestamp("2024-01-01") + pd.Timedelta(days=20)  # well past the daily series' own
# last internal bias flip (day 9) -- comfortably within ALIGNMENT_LOOKBACK.


def H1(i, o, h, l, c):
    return Candle(H1_BASE + pd.Timedelta(hours=i), o, h, l, c, 1000)


def _write(granularity, candles):
    rows = [
        {"time": c.time.isoformat(), "open": c.open, "high": c.high,
         "low": c.low, "close": c.close, "volume": c.volume}
        for c in candles
    ]
    cache.append(SOURCE, SYMBOL, granularity, rows)


@pytest.fixture
def synthetic_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(cache, "DATA_ROOT", str(tmp_path))

    # Same bullish sweep+break sequence validated in test_structure.py --
    # produces one valid_sweep_break (BULLISH, strong_low=1.090) at day 8.
    daily = [
        D(0, 1.100, 1.105, 1.098, 1.102),
        D(1, 1.102, 1.108, 1.100, 1.106),
        D(2, 1.106, 1.112, 1.104, 1.107),
        D(3, 1.107, 1.109, 1.102, 1.104),
        D(4, 1.104, 1.106, 1.095, 1.096),
        D(5, 1.096, 1.099, 1.097, 1.098),
        D(6, 1.098, 1.101, 1.097, 1.099),
        D(7, 1.099, 1.100, 1.090, 1.097),
        D(8, 1.097, 1.120, 1.096, 1.115),
    ]

    # Constructs the full Bishop liquidity cascade the gate now requires:
    # a clean BULLISH breakout at idx5 (closes beyond idx2's swing high,
    # 1.1030 -- idx5's own high is deliberately NOT a local max, via
    # idx6's higher high, so idx5 doesn't self-overwrite as its own swing
    # high before the breakout check runs), then a single-candle
    # liquidity point (a swing low, n=1) at idx7, with the nearest prior
    # BULLISH H4 key level (a "V" close-trough at idx4, price 1.1012) as
    # the reaction level. See scratchpad diagnostics for the derivation;
    # verified via detect_confirmations()/detect_key_levels()/
    # _find_liquidity_setups() directly before wiring into this fixture.
    h4 = [
        H4(0, 1.1000, 1.1010, 1.0995, 1.1005),
        H4(1, 1.1005, 1.1015, 1.1000, 1.1010),
        H4(2, 1.1010, 1.1030, 1.1005, 1.1020),  # swing high, price 1.1030
        H4(3, 1.1020, 1.1025, 1.1010, 1.1015),
        H4(4, 1.1015, 1.1022, 1.1008, 1.1012),  # close-trough ("V") key level, price 1.1012
        H4(5, 1.1012, 1.1038, 1.1010, 1.1035),  # BREAKOUT: closes beyond 1.1030
        H4(6, 1.1035, 1.1042, 1.1025, 1.1030),
        H4(7, 1.1030, 1.1032, 1.1015, 1.1020),  # single-candle liquidity point, low 1.1015
        H4(8, 1.1020, 1.1028, 1.1018, 1.1025),
    ]

    h1 = [
        H1(0, 1.1020, 1.1024, 1.1018, 1.1021),
        H1(1, 1.1021, 1.1023, 1.1010, 1.1013),  # sweeps the H4 liquidity point (low <= 1.1015)
        H1(2, 1.1013, 1.1014, 1.1008, 1.1010),  # touches the H4 reaction level (1.1012), bearish
        H1(3, 1.1010, 1.1035, 1.1005, 1.1030),  # bullish engulf of candle 2 -- the entry trigger
        H1(4, 1.1030, 1.1045, 1.1025, 1.1040),
        H1(5, 1.1040, 1.1060, 1.1035, 1.1055),
        H1(6, 1.1055, 1.1075, 1.1050, 1.1070),
        H1(7, 1.1070, 1.1085, 1.1065, 1.1080),
        # Task 5: stop-loss is keyed to the trigger (engulfing here -- the
        # more extreme of H1(2)'s/H1(3)'s own lows, 1.1005) -- a tighter,
        # closer-to-entry stop than the old liquidity-point-anchored rule,
        # which in turn needs one more candle than before to actually
        # clear the closer-in target.
        H1(8, 1.1080, 1.1115, 1.1075, 1.1110),  # high clears the 1:3 target
    ]

    _write("D", daily)
    _write("H4", h4)
    _write("H1", h1)
    return tmp_path


def test_run_backtest_produces_a_winning_trade_end_to_end(synthetic_cache):
    records = run_backtest(SYMBOL, "conservative", source=SOURCE, pip_size=0.0001)

    assert len(records) == 1
    trade = records[0]

    assert trade.instrument == SYMBOL
    assert trade.direction == Direction.BULLISH
    assert trade.bias_daily == Direction.BULLISH
    assert trade.effective_bias_timeframe == "Daily"
    assert trade.entry_pattern == "fresh_irl_required"
    # Stop-loss is keyed to the trigger (here, engulfing -- the more
    # extreme of H1(2)'s low, 1.1008, and H1(3)'s own low, 1.1005 --
    # 1.1005 wins, stop = 1.1005 - 1 pip).
    assert trade.trigger_type == "engulfing"
    assert trade.stop_kind == "engulfing"
    assert trade.stop_loss == pytest.approx(1.1004)
    # 3 same-direction candidates are in play here (1.1005, 1.101, 1.1012),
    # nearest-to-extreme from the swept liquidity point (1.1015) is
    # [1.1012, 1.101, 1.1005] -- "we don't predict, we react": the nearest
    # candidate (1.1012) is tried first, and the fixture's H1(2)/H1(3)
    # touch-and-engulf IS a genuine reaction off it, so it wins outright;
    # the farther candidates are never even tried.
    assert trade.key_level_price == pytest.approx(1.1012)
    assert trade.key_level_shape == "V"
    assert trade.entry_price == pytest.approx(1.1030)  # conservative -> engulf candle's close
    assert trade.status == "closed_win"
    assert trade.exit_reason == "target_hit"
    # Task 8: ERL is Daily/Weekly period extremes only, not H4 swing
    # fractals (an earlier version capped here at H4 idx6's swing high --
    # wrong, H4 is the cascade's own internal timeframe, not external).
    # This fixture's own 9-day daily series has day8's own high (1.120)
    # dwarfing everything before it, but day8 itself can never qualify as
    # a candidate (no day9 exists yet to confirm it's a COMPLETED period)
    # -- so every earlier day's high counts as already "swept" by day8's
    # still-forming high well before this entry, leaving no valid ERL
    # candidate at all. The plain, uncapped 3:1 target applies.
    assert trade.primary_target == pytest.approx(1.1108)
    assert trade.r_multiple == pytest.approx(3.0)
    assert trade.mfe_r is not None and trade.mfe_r >= trade.r_multiple  # ran at least as far as the close

    # Task 7: stop/target decision audit trail. The engulfing stop wasn't
    # too wide, so no fallback -- natural_stop_loss equals the stop
    # actually used. No ERL candidate qualified, so raw_target and
    # primary_target match and erl_capped is False.
    assert trade.natural_stop_loss == pytest.approx(trade.stop_loss)
    assert trade.stop_fallback_used is False
    assert trade.raw_target == pytest.approx(1.1108)
    assert trade.erl_price is None
    assert trade.erl_capped is False


def test_run_backtest_filters_by_date_range(synthetic_cache):
    # This fixture's only trade enters on H1_BASE (day 20).
    entry_day = H1_BASE.normalize()

    # A range that excludes the entry entirely.
    before = run_backtest(SYMBOL, "conservative", source=SOURCE, pip_size=0.0001,
                           start_date=entry_day + pd.Timedelta(days=1))
    assert before == []
    after = run_backtest(SYMBOL, "conservative", source=SOURCE, pip_size=0.0001,
                          end_date=entry_day - pd.Timedelta(days=1))
    assert after == []

    # A range that includes it.
    included = run_backtest(SYMBOL, "conservative", source=SOURCE, pip_size=0.0001,
                             start_date=entry_day, end_date=entry_day + pd.Timedelta(days=1))
    assert len(included) == 1
    assert included[0].trade_id == 1  # reported IDs stay contiguous from 1, not from the full-history count


def test_run_backtest_date_filtering_does_not_change_the_trades_themselves(synthetic_cache):
    # start_date/end_date bound which trades get REPORTED, never which
    # history gets loaded -- so a trade that survives the filter must come
    # out byte-identical to its counterpart in the unfiltered run. If the
    # window were ever allowed to narrow the loaded data, bias-building
    # and alignment would silently see less history and this would drift.
    _add_earlier_trade()

    full = run_backtest(SYMBOL, "conservative", source=SOURCE, pip_size=0.0001)
    assert len(full) == 2

    filtered = run_backtest(SYMBOL, "conservative", source=SOURCE, pip_size=0.0001,
                             start_date=H1_BASE.normalize())
    assert len(filtered) == 1
    later = full[1]
    assert filtered[0].entry_time == later.entry_time
    assert filtered[0].entry_price == later.entry_price
    assert filtered[0].stop_loss == later.stop_loss
    assert filtered[0].trigger_type == later.trigger_type
    assert filtered[0].raw_target == later.raw_target


def test_run_backtest_respects_a_custom_rr(synthetic_cache):
    default_run = run_backtest(SYMBOL, "conservative", source=SOURCE, pip_size=0.0001)
    rr4_run = run_backtest(SYMBOL, "conservative", source=SOURCE, pip_size=0.0001, rr=4.0)

    assert len(default_run) == len(rr4_run) == 1
    entry, stop = default_run[0].entry_price, default_run[0].stop_loss
    assert default_run[0].raw_target == pytest.approx(entry + 3 * (entry - stop))
    assert rr4_run[0].raw_target == pytest.approx(entry + 4 * (entry - stop))


# ---- avoid_rollover_entries: STRATEGY.md Section 8, "spread widens
# sharply around session rollover" -- confirmed live 2026-08-31, a
# GBPAUD entry at 22:00 UTC filled 54 points worse than requested,
# turning $1,000 of intended risk into a $1,530.32 realized loss.

@pytest.fixture
def synthetic_cache_entry_at_22_utc(tmp_path, monkeypatch):
    """Identical to `synthetic_cache` (same daily/H4 structure, same H1
    OHLC shapes) except H1_BASE is shifted so the same entry candle
    (index 3) lands at 22:00 UTC -- squarely inside the rollover window
    -- instead of 03:00. Daily/H4 timestamps don't depend on H1_BASE at
    all, so the underlying structure/bias/alignment is unaffected;
    only the entry candle's clock hour changes."""
    monkeypatch.setattr(cache, "DATA_ROOT", str(tmp_path))
    base = H1_BASE - pd.Timedelta(hours=3) + pd.Timedelta(hours=22)  # index 3 lands at 22:00 UTC

    daily = [
        D(0, 1.100, 1.105, 1.098, 1.102), D(1, 1.102, 1.108, 1.100, 1.106),
        D(2, 1.106, 1.112, 1.104, 1.107), D(3, 1.107, 1.109, 1.102, 1.104),
        D(4, 1.104, 1.106, 1.095, 1.096), D(5, 1.096, 1.099, 1.097, 1.098),
        D(6, 1.098, 1.101, 1.097, 1.099), D(7, 1.099, 1.100, 1.090, 1.097),
        D(8, 1.097, 1.120, 1.096, 1.115),
    ]
    h4 = [
        H4(0, 1.1000, 1.1010, 1.0995, 1.1005), H4(1, 1.1005, 1.1015, 1.1000, 1.1010),
        H4(2, 1.1010, 1.1030, 1.1005, 1.1020), H4(3, 1.1020, 1.1025, 1.1010, 1.1015),
        H4(4, 1.1015, 1.1022, 1.1008, 1.1012), H4(5, 1.1012, 1.1038, 1.1010, 1.1035),
        H4(6, 1.1035, 1.1042, 1.1025, 1.1030), H4(7, 1.1030, 1.1032, 1.1015, 1.1020),
        H4(8, 1.1020, 1.1028, 1.1018, 1.1025),
    ]
    h1_shape = [
        (1.1020, 1.1024, 1.1018, 1.1021), (1.1021, 1.1023, 1.1010, 1.1013),
        (1.1013, 1.1014, 1.1008, 1.1010), (1.1010, 1.1035, 1.1005, 1.1030),
        (1.1030, 1.1045, 1.1025, 1.1040), (1.1040, 1.1060, 1.1035, 1.1055),
        (1.1055, 1.1075, 1.1050, 1.1070), (1.1070, 1.1085, 1.1065, 1.1080),
        (1.1080, 1.1115, 1.1075, 1.1110),
    ]
    h1 = [Candle(base + pd.Timedelta(hours=i), o, h, l, c, 1000)
          for i, (o, h, l, c) in enumerate(h1_shape)]

    _write("D", daily)
    _write("H4", h4)
    _write("H1", h1)
    return base


def test_avoid_rollover_entries_skips_an_entry_inside_the_window(synthetic_cache_entry_at_22_utc):
    base = synthetic_cache_entry_at_22_utc
    assert (base + pd.Timedelta(hours=3)).hour == 22  # sanity: the fixture lands where intended

    without_filter = run_backtest(SYMBOL, "conservative", source=SOURCE, pip_size=0.0001)
    assert len(without_filter) == 1  # unaffected by default -- opt-in only

    with_filter = run_backtest(SYMBOL, "conservative", source=SOURCE, pip_size=0.0001,
                                avoid_rollover_entries=True)
    assert with_filter == []


def test_avoid_rollover_entries_does_not_affect_an_entry_outside_the_window(synthetic_cache):
    # The original fixture's entry is at 03:00 UTC -- outside the
    # window, so the flag must be a no-op here.
    assert (H1_BASE + pd.Timedelta(hours=3)).hour == 3

    without_filter = run_backtest(SYMBOL, "conservative", source=SOURCE, pip_size=0.0001)
    with_filter = run_backtest(SYMBOL, "conservative", source=SOURCE, pip_size=0.0001,
                                avoid_rollover_entries=True)
    assert len(without_filter) == len(with_filter) == 1


# ---- min_reward_r: direct 2026-09-01 question, "a trade of less than
# 1R doesn't make sense to hold" -- skip entries whose (ERL-capped)
# target is too close to entry to justify the risk.

def test_min_reward_r_skips_an_entry_whose_target_is_too_close(synthetic_cache):
    # rr=0.5 with no ERL candidate in this fixture (see the end-to-end
    # test's own comment -- no ERL candidate qualifies here, so the
    # raw rr-based target applies uncapped) makes the target only 0.5R
    # away -- below the 1.0 threshold.
    without_filter = run_backtest(SYMBOL, "conservative", source=SOURCE, pip_size=0.0001, rr=0.5)
    assert len(without_filter) == 1
    entry, stop, target = without_filter[0].entry_price, without_filter[0].stop_loss, without_filter[0].primary_target
    assert abs(target - entry) / abs(entry - stop) == pytest.approx(0.5)

    with_filter = run_backtest(SYMBOL, "conservative", source=SOURCE, pip_size=0.0001,
                                rr=0.5, min_reward_r=1.0)
    assert with_filter == []


def test_min_reward_r_does_not_affect_an_entry_that_already_clears_it(synthetic_cache):
    # The fixture's default 3:1 target comfortably clears a 1R minimum --
    # the filter must be a no-op here, not accidentally block everything.
    without_filter = run_backtest(SYMBOL, "conservative", source=SOURCE, pip_size=0.0001)
    with_filter = run_backtest(SYMBOL, "conservative", source=SOURCE, pip_size=0.0001, min_reward_r=1.0)
    assert len(without_filter) == len(with_filter) == 1


def test_resolve_date_range_returns_tz_aware_utc_bounds():
    # Regression test for a real bug: pd.Timestamp(year=..., month=...,
    # day=...) is tz-NAIVE by default, but cached candle timestamps are
    # tz-aware UTC (parsed from the CSV's own "+00:00" ISO strings) --
    # comparing naive against aware raises "Cannot compare tz-naive and
    # tz-aware timestamps". This slipped past every other test in this
    # file because ALL of this file's own fixtures build NAIVE
    # timestamps throughout (see H1_BASE etc.) -- only a real production
    # run against real (aware) cached data actually hit it.
    start, end = _resolve_date_range(2026, None, None)
    assert start.tzinfo is not None and end.tzinfo is not None

    production_like_time = pd.Timestamp("2026-06-15T12:00:00+00:00")  # tz-aware, like real candle data
    assert start <= production_like_time <= end  # must not raise


def test_resolve_date_range_year_shorthand_spans_the_whole_calendar_year():
    start, end = _resolve_date_range(2026, None, None)
    assert start == pd.Timestamp("2026-01-01T00:00:00+00:00")
    assert end == pd.Timestamp("2026-12-31T23:59:59+00:00")


def test_resolve_date_range_widens_a_bare_end_date_to_end_of_day():
    start, end = _resolve_date_range(None, "2026-03-01", "2026-03-10")
    assert start == pd.Timestamp("2026-03-01T00:00:00+00:00")
    assert end == pd.Timestamp("2026-03-10T23:59:59+00:00")


def test_resolve_date_range_returns_none_none_when_nothing_given():
    assert _resolve_date_range(None, None, None) == (None, None)


def test_parse_rr_accepts_a_bare_number():
    assert _parse_rr("4") == 4.0


def test_parse_rr_accepts_ratio_notation():
    # This is the exact input that crashed a real GitHub Actions run:
    # someone typed "3:1" (STRATEGY.md's own notation) into a bare
    # `type=float` argument.
    assert _parse_rr("3:1") == 3.0
    assert _parse_rr("4:1") == 4.0
    assert _parse_rr("2:0.5") == 4.0


def _h1(i, o, h, l, c):
    return Candle(pd.Timestamp("2024-01-01") + pd.Timedelta(hours=i), o, h, l, c, 1000)


def test_resolve_trade_outcome_caps_mae_at_the_stop_on_a_wide_stop_hit_candle():
    # A real 2026 GBPUSD backtest produced mae_r=-28 on a trade whose
    # realized loss was exactly -1R: a single wide H1 candle undershot a
    # tight stop by many multiples of R, and the old code recorded that
    # candle's raw low as MAE instead of capping at the stop price (the
    # position is closed the instant the stop is touched, so excursion
    # beyond that point was never actually experienced).
    entry, stop, target = 100.0, 99.0, 103.0  # risk = 1.0
    path = [_h1(1, 100.0, 100.2, 70.0, 71.0)]  # low blows straight through the stop
    reason, price, time, mae_r, mfe_r = _resolve_trade_outcome(entry, stop, target, Direction.BULLISH, path)
    assert reason == "stop_hit"
    assert price == stop
    assert mae_r == -1.0  # capped, not -30


def test_resolve_trade_outcome_caps_mae_on_a_bearish_wide_stop_hit_candle():
    entry, stop, target = 100.0, 101.0, 97.0  # risk = 1.0
    path = [_h1(1, 100.0, 130.0, 99.8, 129.0)]  # high blows straight through the stop
    reason, price, time, mae_r, mfe_r = _resolve_trade_outcome(entry, stop, target, Direction.BEARISH, path)
    assert reason == "stop_hit"
    assert price == stop
    assert mae_r == -1.0


def test_resolve_trade_outcome_still_tracks_real_mae_before_a_clean_stop_hit():
    entry, stop, target = 100.0, 99.0, 103.0  # risk = 1.0
    path = [
        _h1(1, 100.0, 100.5, 99.4, 99.6),   # dips to -0.6R, doesn't touch stop
        _h1(2, 99.6, 99.8, 99.0, 99.0),      # then touches the stop exactly
    ]
    reason, price, time, mae_r, mfe_r = _resolve_trade_outcome(entry, stop, target, Direction.BULLISH, path)
    assert reason == "stop_hit"
    assert mae_r == -1.0


def test_resolve_trade_outcome_mfe_is_not_capped_on_a_wide_target_hit_candle():
    # MFE overshoot on a target-hit candle is real, legitimate information
    # (price kept moving favorably before/around the target) -- only the
    # MAE-on-stop-hit case is the bug; this pins that MFE is untouched.
    entry, stop, target = 100.0, 99.0, 103.0  # risk = 1.0
    path = [_h1(1, 100.0, 110.0, 99.8, 109.0)]  # high blows well past the target
    reason, price, time, mae_r, mfe_r = _resolve_trade_outcome(entry, stop, target, Direction.BULLISH, path)
    assert reason == "target_hit"
    assert price == target
    assert mfe_r == 10.0  # (110 - 100) / 1.0, uncapped


def test_run_backtest_aggressive_style_enters_at_key_level_price(synthetic_cache):
    # This fixture's reaction level (1.1012) sits BEYOND (further in the
    # trade direction than) the swept liquidity point (1.1015) -- with the
    # OLD origin_stop_loss()-anchored-to-liquidity-point rule, an
    # aggressive entry AT the key level itself (1.1012) would have landed
    # that stop on the WRONG side of entry. Task 5's trigger-keyed
    # engulfing stop (the more extreme of both candles' own wicks, 1.1004
    # here) fixes this naturally -- it's derived from price actually near
    # entry, not a separate liquidity-point reference that can end up on
    # the far side of a reaction level closer to the sweep.
    records = run_backtest(SYMBOL, "aggressive", source=SOURCE, pip_size=0.0001)

    assert len(records) == 1
    # Aggressive enters at the key level itself (the H4 reaction level), not the confirmation close.
    # See test_run_backtest_produces_a_winning_trade_end_to_end for why this is 1.1012, the nearest
    # same-direction candidate to the swept liquidity point, not a scored pick.
    assert records[0].entry_price == pytest.approx(1.1012)
    assert records[0].stop_loss == pytest.approx(1.1004)


def _add_earlier_trade():
    """Give the fixture a SECOND, earlier trade, so tests that care about
    what happens when a trade has a predecessor (date-range filtering,
    position stacking) have one to work with instead of a series
    containing exactly one entry. This appends a second, independent H4
    breakout+liquidity+reaction cascade (H4 idx9-17, a fresh price range
    so it doesn't interact with synthetic_cache's own idx0-8 swing
    points) plus its own H1 sweep+engulf entry at day 10 -- after
    synthetic_cache's own Daily confirmation (~day 8-9, needed for the
    Daily+H4 alignment gate) but before H1_BASE (day 20), so it's
    processed first and becomes "origin", leaving the caller's own
    H1_BASE-anchored trade as "continuation". Verified directly against
    _find_liquidity_setups()/_find_entry_candidates() before wiring in."""
    def H4b(i, o, h, l, c):
        return Candle(pd.Timestamp("2024-01-01") + pd.Timedelta(hours=4 * i), o, h, l, c, 1000)

    extra_h4 = [
        H4b(9, 1.1025, 1.1060, 1.1020, 1.1055),
        H4b(10, 1.1055, 1.1065, 1.1050, 1.1060),
        H4b(11, 1.1060, 1.1080, 1.1055, 1.1070),
        H4b(12, 1.1070, 1.1075, 1.1060, 1.1065),
        H4b(13, 1.1065, 1.1072, 1.1058, 1.1062),
        H4b(14, 1.1062, 1.1095, 1.1060, 1.1090),  # BREAKOUT (closes beyond idx11's 1.1080 swing high)
        H4b(15, 1.1090, 1.1098, 1.1085, 1.1092),
        H4b(16, 1.1092, 1.1094, 1.1075, 1.1080),
        H4b(17, 1.1080, 1.1088, 1.1078, 1.1085),
    ]
    second_base = pd.Timestamp("2024-01-01") + pd.Timedelta(days=10)

    def S(i, o, h, l, c):
        return Candle(second_base + pd.Timedelta(hours=i), o, h, l, c, 1000)

    extra_h1 = [
        S(0, 1.1063, 1.1067, 1.1061, 1.1064),
        S(1, 1.1064, 1.1066, 1.1053, 1.1059),  # sweeps this cascade's own liquidity point (1.1058)
        S(2, 1.1059, 1.1061, 1.1055, 1.1057),  # touches its reaction level (1.106), bearish
        S(3, 1.1056, 1.1075, 1.1050, 1.1070),  # bullish engulf -- the entry trigger
        S(4, 1.1070, 1.1090, 1.1065, 1.1085),
        S(5, 1.1085, 1.1120, 1.1080, 1.1115),  # clears its own target
    ]
    _write("H4", extra_h4)
    _write("H1", extra_h1)


def test_run_backtest_uses_imbalance_stop_for_plug_and_play_continuation_trades(synthetic_cache):
    _add_earlier_trade()

    # Insert 3 H1 candles BETWEEN the sweep (index 1) and the reaction/
    # engulf (indices 2-3), forming a bullish FVG that brackets the H4
    # reaction level (1.1012, the nearest same-direction candidate to the
    # swept liquidity point -- see test_run_backtest_produces_a_winning_
    # trade_end_to_end): A.high=1.1009, C.low=1.1020. Deliberately placed BEFORE the entry, not after --
    # imbalance_overlap now only matches imbalances formed between the
    # key level's own formation and the entry (see the run_backtest
    # comment at the overlapping= computation), matching "price is
    # returning to fill an ALREADY-existing gap", not a gap that only
    # forms later. B's own body is bearish and stays well clear of
    # 1.101 specifically so no (prev, curr) pair among these 3 candles
    # (or their neighbors) accidentally satisfies classify_entry_pattern's
    # touched-and-engulfing check before the real entry at index 3.
    extra = [
        Candle(H1_BASE + pd.Timedelta(hours=1.25), 1.1008, 1.1009, 1.0998, 1.1000, 1000),
        Candle(H1_BASE + pd.Timedelta(hours=1.5), 1.1000, 1.1005, 1.0995, 1.0998, 1000),
        Candle(H1_BASE + pd.Timedelta(hours=1.75), 1.1020, 1.1028, 1.1020, 1.1025, 1000),
    ]
    _write("H1", extra)

    records = run_backtest(SYMBOL, "conservative", source=SOURCE, pip_size=0.0001)
    assert len(records) == 2
    trade = records[1]

    assert trade.imbalance_overlap is True
    assert trade.trigger_type == "plug_and_play"
    assert trade.stop_kind == "plug_and_play"
    # Far edge of the overlapping imbalance (1.1009, A's high) minus a
    # 1-pip pad -- NOT the engulfing-wick-anchored stop this same reaction
    # would otherwise get (Task 5: plug and play takes priority over the
    # trigger-specific rules whenever an overlapping imbalance exists).
    assert trade.stop_loss == pytest.approx(1.1008)
    # Task 7: no fallback concept for plug and play -- the imbalance-
    # anchored stop IS the natural rule.
    assert trade.natural_stop_loss == pytest.approx(1.1008)
    assert trade.stop_fallback_used is False


def test_run_backtest_ignores_an_overlapping_imbalance_formed_after_entry(synthetic_cache):
    _add_earlier_trade()

    # Regression test for a real bug found via the trade-chart viewer: a
    # live trade got an 83-pip "plug and play" stop because h1_imbalances
    # (computed once over the WHOLE H1 series) was matched against a key
    # level's price with no regard for WHEN the imbalance formed --
    # something from years away, price-only-coincidentally overlapping,
    # could win. Same geometry as the "uses_imbalance_stop" test right
    # above (a bullish gap bracketing the 1.1012 reaction level), but
    # placed hours AFTER the entry trigger instead of between the sweep
    # and the reaction -- a gap that doesn't exist yet at entry time
    # can't be the one price is "returning to fill", so it must NOT be
    # picked up, and the trade should fall through to the trigger's own
    # (engulfing) stop-loss rule instead.
    extra = [
        Candle(H1_BASE + pd.Timedelta(hours=10), 1.1008, 1.1009, 1.0998, 1.1000, 1000),
        Candle(H1_BASE + pd.Timedelta(hours=10.5), 1.1000, 1.1005, 1.0995, 1.0998, 1000),
        Candle(H1_BASE + pd.Timedelta(hours=11), 1.1020, 1.1028, 1.1020, 1.1025, 1000),
    ]
    _write("H1", extra)

    records = run_backtest(SYMBOL, "conservative", source=SOURCE, pip_size=0.0001)
    assert len(records) == 2
    trade = records[1]

    assert trade.imbalance_overlap is False
    assert trade.trigger_type == "engulfing"
    assert trade.stop_kind == "engulfing"
    assert trade.stop_loss == pytest.approx(1.1004)


def test_aligned_timeframes_requires_each_tiers_own_confirmation():
    t = pd.Timestamp("2024-06-01")

    def conf(days_before, direction):
        return Confirmation(t - pd.Timedelta(days=days_before), direction, ConfirmationKind.BREAKOUT, 1.10)

    weekly = [conf(20, Direction.BULLISH)]
    daily = [conf(5, Direction.BULLISH)]
    h4 = [conf(1, Direction.BULLISH)]

    assert _aligned_timeframes(Direction.BULLISH, t, weekly, daily, h4) == ["Weekly", "Daily", "H4"]


def test_aligned_timeframes_excludes_a_tier_confirming_the_opposite_direction():
    t = pd.Timestamp("2024-06-01")

    def conf(days_before, direction):
        return Confirmation(t - pd.Timedelta(days=days_before), direction, ConfirmationKind.BREAKOUT, 1.10)

    daily = [conf(5, Direction.BEARISH)]  # opposite direction -- shouldn't count
    h4 = [conf(1, Direction.BULLISH)]

    assert _aligned_timeframes(Direction.BULLISH, t, [], daily, h4) == ["H4"]


def test_aligned_timeframes_excludes_a_confirmation_outside_the_lookback_window():
    t = pd.Timestamp("2024-06-01")
    daily = [Confirmation(t - pd.Timedelta(days=200), Direction.BULLISH, ConfirmationKind.BREAKOUT, 1.10)]
    h4 = [Confirmation(t - pd.Timedelta(hours=1), Direction.BULLISH, ConfirmationKind.BREAKOUT, 1.10)]

    assert _aligned_timeframes(Direction.BULLISH, t, [], daily, h4) == ["H4"]


def test_aligned_timeframes_excludes_a_confirmation_that_hasnt_happened_yet():
    # A future-dated confirmation (relative to `t`) can't be what price is
    # currently aligned with -- same reasoning as the imbalance-matching
    # fix: only what's already happened counts.
    t = pd.Timestamp("2024-06-01")
    daily = [Confirmation(t + pd.Timedelta(days=1), Direction.BULLISH, ConfirmationKind.BREAKOUT, 1.10)]
    h4 = [Confirmation(t - pd.Timedelta(hours=1), Direction.BULLISH, ConfirmationKind.BREAKOUT, 1.10)]

    assert _aligned_timeframes(Direction.BULLISH, t, [], daily, h4) == ["H4"]


def test_run_backtest_rejects_an_h4_setup_with_no_daily_alignment(synthetic_cache):
    # "4H can't stand alone if at least the Daily isn't aligned to it."
    # synthetic_cache's own daily series only gives its breakout/sweep+break
    # confirmations around day 8-9, and H1_BASE sits ~20 days later --
    # within ALIGNMENT_LOOKBACK for H4, but this test additionally monkeypatches
    # H4's own lookback down to something the fixture's H4 breakout (day ~1)
    # can't reach from H1_BASE (day 20), simulating "H4 aligned, but nothing
    # else nearby enough to count as Daily support" and confirming the trade
    # gets rejected rather than taken on H4 alone.
    import backtest.engine.runner as runner_module
    original = runner_module.ALIGNMENT_LOOKBACK
    runner_module.ALIGNMENT_LOOKBACK = {**original, "Daily": pd.Timedelta(days=0)}
    try:
        records = run_backtest(SYMBOL, "conservative", source=SOURCE, pip_size=0.0001)
    finally:
        runner_module.ALIGNMENT_LOOKBACK = original
    assert records == []


def test_run_backtest_produces_an_origin_trade_close_to_the_bias_bootstrap(tmp_path, monkeypatch):
    # Same Bishop cascade as `synthetic_cache`, but with H1 candles placed
    # close in time to the Daily bias bootstrap (2024-01-01 for this
    # fixture -- see the daily series below) instead of `synthetic_cache`'s
    # deliberate 20-day-later placement. Historically (before an early
    # fix) the stop was anchored to a Daily-timeframe strong-low snapshot
    # that hadn't been set yet this early (StructureTracker's
    # valid_sweep_break doesn't fire until day 9) -- `_strong_at()`
    # returned None and the trade was silently dropped; this
    # regression-tests that a trade this early in the series still gets
    # produced at all. Stop-loss itself is now keyed to the TRIGGER
    # (Task 5) -- see
    # test_run_backtest_produces_a_winning_trade_end_to_end for the
    # identical engulfing-stop derivation (this fixture reuses the exact
    # same H4/H1 cascade, just time-shifted).
    monkeypatch.setattr(cache, "DATA_ROOT", str(tmp_path))

    daily = [
        # Prepended so the new multi-timeframe alignment gate has a Daily
        # breakout to find before entry (day 2) -- a swing high peaking at
        # day -3 (1.099), with day 0's own close (1.102, unchanged below)
        # confirming the breakout above it. Doesn't touch day 0 onward, so
        # first_origin's sweep+break detection (day ~8-9) is unaffected.
        D(-5, 1.090, 1.093, 1.088, 1.091),
        D(-4, 1.091, 1.096, 1.089, 1.093),
        D(-3, 1.093, 1.099, 1.091, 1.095),  # swing high, price 1.099
        D(-2, 1.095, 1.097, 1.092, 1.094),
        D(-1, 1.094, 1.096, 1.090, 1.093),
        D(0, 1.100, 1.105, 1.098, 1.102),
        D(1, 1.102, 1.108, 1.100, 1.106),
        D(2, 1.106, 1.112, 1.104, 1.107),
        D(3, 1.107, 1.109, 1.102, 1.104),
        D(4, 1.104, 1.106, 1.095, 1.096),
        D(5, 1.096, 1.099, 1.097, 1.098),
        D(6, 1.098, 1.101, 1.097, 1.099),
        D(7, 1.099, 1.100, 1.090, 1.097),
        D(8, 1.097, 1.120, 1.096, 1.115),
    ]
    h4 = [
        H4(0, 1.1000, 1.1010, 1.0995, 1.1005),
        H4(1, 1.1005, 1.1015, 1.1000, 1.1010),
        H4(2, 1.1010, 1.1030, 1.1005, 1.1020),
        H4(3, 1.1020, 1.1025, 1.1010, 1.1015),
        H4(4, 1.1015, 1.1022, 1.1008, 1.1012),
        H4(5, 1.1012, 1.1038, 1.1010, 1.1035),
        H4(6, 1.1035, 1.1042, 1.1025, 1.1030),
        H4(7, 1.1030, 1.1032, 1.1015, 1.1020),  # single-candle liquidity point, low 1.1015
        H4(8, 1.1020, 1.1028, 1.1018, 1.1025),
    ]
    origin_h1_base = pd.Timestamp("2024-01-01") + pd.Timedelta(days=2)

    def origin_H1(i, o, h, l, c):
        return Candle(origin_h1_base + pd.Timedelta(hours=i), o, h, l, c, 1000)

    h1 = [
        origin_H1(0, 1.1020, 1.1024, 1.1018, 1.1021),
        origin_H1(1, 1.1021, 1.1023, 1.1010, 1.1013),  # sweeps the H4 liquidity point (low <= 1.1015)
        origin_H1(2, 1.1013, 1.1014, 1.1008, 1.1010),  # touches the H4 reaction level (1.1012), bearish
        origin_H1(3, 1.1010, 1.1035, 1.1005, 1.1030),  # bullish engulf -- the entry trigger
        origin_H1(4, 1.1030, 1.1045, 1.1025, 1.1040),
        origin_H1(5, 1.1040, 1.1060, 1.1035, 1.1055),
        origin_H1(6, 1.1055, 1.1075, 1.1050, 1.1070),
        origin_H1(7, 1.1070, 1.1085, 1.1065, 1.1080),
        origin_H1(8, 1.1080, 1.1115, 1.1075, 1.1110),  # high clears the 1:3 target
    ]

    _write("D", daily)
    _write("H4", h4)
    _write("H1", h1)

    records = run_backtest(SYMBOL, "conservative", source=SOURCE, pip_size=0.0001)
    assert len(records) == 1
    trade = records[0]

    assert trade.trigger_type == "engulfing"
    assert trade.stop_kind == "engulfing"
    # More extreme of H1(2)'s low (1.1008) and H1(3)'s own low (1.1005) --
    # 1.1005 wins -- minus a 1-pip pad. NOT some multi-hundred-pip Daily
    # structural extreme (e.g. the 1.090 strong low this fixture's daily
    # series would otherwise produce), and NOT the liquidity-point anchor
    # (1.1015) the old origin-keyed rule used either.
    assert trade.stop_loss == pytest.approx(1.1004)
    assert trade.status == "closed_win"
    # Task 8: ERL is Daily/Weekly period extremes, not H4 -- and as of
    # this early (day 2) entry, no completed prior day's high reaches
    # anywhere near entry (1.1030) yet, so no ERL candidate qualifies and
    # the plain, uncapped 3:1 target applies.
    assert trade.primary_target == pytest.approx(1.1108)
    assert trade.r_multiple == pytest.approx(3.0)
    assert trade.erl_price is None
    assert trade.erl_capped is False


def test_reaction_trigger_prefers_engulfing_then_falls_through_to_fourth_man():
    # Engulfing: bearish prev, bullish curr fully covering prev's body.
    prev = H1(0, 1.1020, 1.1025, 1.0995, 1.1000)
    curr = H1(1, 1.0998, 1.1040, 1.0996, 1.1030)
    assert _reaction_trigger(prev, curr, Direction.BULLISH) == "engulfing"

    # 4th man: curr sweeps prev's low, reclaims into prev's range, prev's
    # high stays untouched -- NOT an engulfing shape (curr's open sits
    # above prev's close, so it doesn't "fully cover" prev's body).
    prev2 = H1(2, 1.1010, 1.1020, 1.1000, 1.1015)
    curr2 = H1(3, 1.1015, 1.1018, 1.0990, 1.1005)
    assert _reaction_trigger(prev2, curr2, Direction.BULLISH) == "fourth_man"

    # Neither pattern fires.
    prev3 = H1(4, 1.1010, 1.1020, 1.1000, 1.1015)
    curr3 = H1(5, 1.1015, 1.1018, 1.1005, 1.1010)  # stays fully inside prev3's range
    assert _reaction_trigger(prev3, curr3, Direction.BULLISH) is None


def test_natural_stop_too_wide_uses_the_configured_pip_threshold():
    # 20 pips from entry -- within the default 30-pip threshold.
    assert _natural_stop_too_wide(1.1030, 1.1010, pip_size=0.0001) is False
    # 40 pips from entry -- exceeds it.
    assert _natural_stop_too_wide(1.1030, 1.0990, pip_size=0.0001) is True
    # A tighter custom threshold catches the same 20-pip gap.
    assert _natural_stop_too_wide(1.1030, 1.1010, pip_size=0.0001, max_pips=15.0) is True


def test_run_backtest_fires_on_a_fourth_man_reaction(tmp_path, monkeypatch):
    # Same daily/H4 cascade as synthetic_cache, but H1(2) is a 4th-man
    # sweep-and-reclaim against H1(1) (the sweep candle) instead of an
    # engulf: H1(2) sweeps below H1(1)'s low (1.1010), reclaims back above
    # it (close 1.1012), while H1(1)'s own high (1.1023) stays untouched --
    # and is NOT an engulfing shape (H1(2)'s close sits below H1(1)'s
    # open, so it never "fully covers" H1(1)'s body). Confirms the 4th-man
    # trigger (Task 3's detector) actually fires as an entry trigger
    # through the real gate, not just in isolation.
    monkeypatch.setattr(cache, "DATA_ROOT", str(tmp_path))

    daily = [
        D(0, 1.100, 1.105, 1.098, 1.102),
        D(1, 1.102, 1.108, 1.100, 1.106),
        D(2, 1.106, 1.112, 1.104, 1.107),
        D(3, 1.107, 1.109, 1.102, 1.104),
        D(4, 1.104, 1.106, 1.095, 1.096),
        D(5, 1.096, 1.099, 1.097, 1.098),
        D(6, 1.098, 1.101, 1.097, 1.099),
        D(7, 1.099, 1.100, 1.090, 1.097),
        D(8, 1.097, 1.120, 1.096, 1.115),
    ]
    h4 = [
        H4(0, 1.1000, 1.1010, 1.0995, 1.1005),
        H4(1, 1.1005, 1.1015, 1.1000, 1.1010),
        H4(2, 1.1010, 1.1030, 1.1005, 1.1020),
        H4(3, 1.1020, 1.1025, 1.1010, 1.1015),
        H4(4, 1.1015, 1.1022, 1.1008, 1.1012),
        H4(5, 1.1012, 1.1038, 1.1010, 1.1035),
        H4(6, 1.1035, 1.1042, 1.1025, 1.1030),
        H4(7, 1.1030, 1.1032, 1.1015, 1.1020),
        H4(8, 1.1020, 1.1028, 1.1018, 1.1025),
    ]
    h1 = [
        H1(0, 1.1020, 1.1024, 1.1018, 1.1021),
        H1(1, 1.1021, 1.1023, 1.1010, 1.1013),  # sweeps the H4 liquidity point (low <= 1.1015)
        H1(2, 1.1013, 1.1018, 1.0998, 1.1012),  # 4th-man reaction off H1(1) -- the entry trigger
        H1(3, 1.1010, 1.1035, 1.1005, 1.1030),
        H1(4, 1.1030, 1.1045, 1.1025, 1.1040),
        H1(5, 1.1040, 1.1060, 1.1035, 1.1055),
        H1(6, 1.1055, 1.1075, 1.1050, 1.1070),
        H1(7, 1.1070, 1.1085, 1.1065, 1.1080),
    ]
    _write("D", daily)
    _write("H4", h4)
    _write("H1", h1)

    records = run_backtest(SYMBOL, "conservative", source=SOURCE, pip_size=0.0001)
    assert len(records) == 1
    trade = records[0]

    assert trade.trigger_type == "fourth_man"
    assert trade.stop_kind == "fourth_man"
    # A pad below H1(2)'s own low (1.0998, the candle that did the
    # sweeping) -- the 4th-man default.
    assert trade.stop_loss == pytest.approx(1.0997)
    assert trade.status == "closed_win"
    # Task 8: ERL is Daily/Weekly period extremes, not H4 -- same
    # dwarfed-by-day8's-still-forming-high reasoning as
    # test_run_backtest_produces_a_winning_trade_end_to_end, so no ERL
    # candidate qualifies and the plain, uncapped 3:1 target applies.
    assert trade.primary_target == pytest.approx(1.1057)
    assert trade.r_multiple == pytest.approx(3.0)


def test_run_backtest_falls_back_to_the_key_level_when_the_natural_stop_is_too_wide(tmp_path, monkeypatch):
    # Same daily/H4/H1 cascade as synthetic_cache, but H1(2) (the engulfed
    # candle) has a 64-pip wick down to 1.0950 -- an engulfing-anchored
    # stop there would be unreasonably wide (Task 5's universal fallback:
    # "if the logic is correct and price shouldn't come back to it...
    # 1 or 2 out of 10"). The stop should fall back to just beyond the H4
    # key level itself (1.1012) instead of chasing the wide wick down to
    # 1.0950.
    monkeypatch.setattr(cache, "DATA_ROOT", str(tmp_path))

    daily = [
        D(0, 1.100, 1.105, 1.098, 1.102),
        D(1, 1.102, 1.108, 1.100, 1.106),
        D(2, 1.106, 1.112, 1.104, 1.107),
        D(3, 1.107, 1.109, 1.102, 1.104),
        D(4, 1.104, 1.106, 1.095, 1.096),
        D(5, 1.096, 1.099, 1.097, 1.098),
        D(6, 1.098, 1.101, 1.097, 1.099),
        D(7, 1.099, 1.100, 1.090, 1.097),
        D(8, 1.097, 1.120, 1.096, 1.115),
    ]
    h4 = [
        H4(0, 1.1000, 1.1010, 1.0995, 1.1005),
        H4(1, 1.1005, 1.1015, 1.1000, 1.1010),
        H4(2, 1.1010, 1.1030, 1.1005, 1.1020),
        H4(3, 1.1020, 1.1025, 1.1010, 1.1015),
        H4(4, 1.1015, 1.1022, 1.1008, 1.1012),
        H4(5, 1.1012, 1.1038, 1.1010, 1.1035),
        H4(6, 1.1035, 1.1042, 1.1025, 1.1030),
        H4(7, 1.1030, 1.1032, 1.1015, 1.1020),
        H4(8, 1.1020, 1.1028, 1.1018, 1.1025),
    ]
    h1 = [
        H1(0, 1.1020, 1.1024, 1.1018, 1.1021),
        H1(1, 1.1021, 1.1023, 1.1010, 1.1013),  # sweeps the H4 liquidity point (low <= 1.1015)
        H1(2, 1.1013, 1.1014, 1.0950, 1.1010),  # touches 1.1012, but with a 64-pip wick down to 1.0950
        H1(3, 1.1010, 1.1035, 1.1005, 1.1030),  # bullish engulf -- the entry trigger
        H1(4, 1.1030, 1.1045, 1.1025, 1.1040),
        H1(5, 1.1040, 1.1060, 1.1035, 1.1055),
        H1(6, 1.1055, 1.1075, 1.1050, 1.1070),
        H1(7, 1.1070, 1.1085, 1.1065, 1.1080),
        H1(8, 1.1080, 1.1115, 1.1075, 1.1110),
    ]
    _write("D", daily)
    _write("H4", h4)
    _write("H1", h1)

    records = run_backtest(SYMBOL, "conservative", source=SOURCE, pip_size=0.0001)
    assert len(records) == 1
    trade = records[0]

    assert trade.trigger_type == "engulfing"
    assert trade.stop_kind == "engulfing_kl_fallback"
    # 1 pip beyond the H4 reaction level itself (1.1012), NOT the 64-pip
    # engulfed wick (1.0950).
    assert trade.stop_loss == pytest.approx(1.1011)
    assert trade.status == "closed_win"
    # Task 8: ERL is Daily/Weekly period extremes, not H4 -- same
    # dwarfed-by-day8's-still-forming-high reasoning as
    # test_run_backtest_produces_a_winning_trade_end_to_end, so no ERL
    # candidate qualifies and the plain, uncapped 3:1 target applies.
    assert trade.primary_target == pytest.approx(1.1087)
    assert trade.r_multiple == pytest.approx(3.0)

    # Task 7: the audit trail shows what the natural (too-wide) stop
    # WOULD have been -- 1 pip beyond the 64-pip wick (1.0950) -- even
    # though the fallback fired and stop_loss ended up at 1.1011 instead.
    assert trade.natural_stop_loss == pytest.approx(1.0949)
    assert trade.stop_fallback_used is True


def test_unswept_period_extremes_excludes_the_still_forming_last_period():
    daily = [
        D(0, 1.0990, 1.1050, 1.0980, 1.1000),  # completed -- high 1.1050
        D(1, 1.1000, 1.1010, 1.0990, 1.1005),  # completed -- high 1.1010
        D(2, 1.1005, 1.1005, 1.0995, 1.1000),  # LAST candle -- can't confirm it's "complete" yet
    ]
    # Neither day0 nor day1 is exceeded by anything after it (day2's own
    # high, 1.1005, is smaller than both), so both survive -- but day2
    # itself is never returned regardless of its own high, since there's
    # no day3 yet to confirm day2 has actually closed.
    extremes = _unswept_period_extremes(daily, pd.Timestamp("2024-01-05"), "high")
    assert extremes == [pytest.approx(1.1050), pytest.approx(1.1010)]


def test_unswept_period_extremes_excludes_a_high_already_swept_by_a_later_day():
    daily = [
        D(0, 1.0990, 1.1050, 1.0980, 1.1000),  # completed high 1.1050 -- swept below
        D(1, 1.1000, 1.1010, 1.0990, 1.1005),
        D(2, 1.1005, 1.1080, 1.0995, 1.1010),  # day2's high (1.1080) exceeds day0's (1.1050)
        D(3, 1.1010, 1.1015, 1.1000, 1.1012),  # only here to confirm day2 has closed
    ]
    # day0's high (1.1050) was exceeded by day2's high (1.1080) before day3
    # even starts -- no longer real untaken liquidity. Only day2's own high
    # (now itself confirmed complete by day3) remains.
    extremes = _unswept_period_extremes(daily, pd.Timestamp("2024-01-05"), "high")
    assert extremes == [pytest.approx(1.1080)]


def test_nearest_erl_picks_the_closest_untaken_point_across_daily_and_weekly():
    daily = [
        D(0, 1.0990, 1.1060, 1.0980, 1.1000),  # nearer than weekly's
        D(1, 1.1000, 1.1010, 1.0990, 1.1005),
        D(2, 1.1005, 1.1010, 1.0995, 1.1008),  # confirms day0/day1 complete
    ]
    weekly = [
        W(0, 1.0990, 1.1200, 1.0980, 1.1000),  # farther than daily's
        W(1, 1.1000, 1.1010, 1.0990, 1.1005),
    ]
    entry_price = 1.1030
    as_of_time = pd.Timestamp("2024-01-05")

    erl = _nearest_erl(Direction.BULLISH, entry_price, as_of_time, daily, weekly)
    assert erl == pytest.approx(1.1060)  # the nearer daily point wins, not weekly's farther (but real) 1.1200


def test_nearest_erl_ignores_points_behind_entry():
    daily = [
        D(0, 1.1000, 1.1060, 1.0995, 1.1010),
        D(1, 1.1010, 1.1015, 1.1005, 1.1012),
        D(2, 1.1012, 1.1018, 1.1008, 1.1015),  # confirms day0/day1 complete
    ]
    # day0's high (1.1060) is BEHIND entry (1.1070) in the trade direction
    # -- already passed, not an external constraint anymore.
    assert _nearest_erl(Direction.BULLISH, 1.1070, pd.Timestamp("2024-01-05"), daily) is None


def test_run_backtest_calls_nearest_erl_with_only_daily_and_weekly(synthetic_cache, monkeypatch):
    # Wiring regression test for the actual bug: an earlier version of
    # this call site passed h4 into _nearest_erl() alongside daily/weekly,
    # treating H4's own dense swing fractals as if they were external
    # liquidity -- on real EURUSD data that capped 96% of trades and flipped
    # a backtest from solidly positive total R to negative. H4 is the
    # cascade's own internal working timeframe, not external relative to
    # it, so it must never reach _nearest_erl() at all.
    import backtest.engine.runner as runner_module
    calls = []
    original = runner_module._nearest_erl

    def spy(direction, entry_price, as_of_time, *period_series):
        calls.append(period_series)
        return original(direction, entry_price, as_of_time, *period_series)

    monkeypatch.setattr(runner_module, "_nearest_erl", spy)
    records = run_backtest(SYMBOL, "conservative", source=SOURCE, pip_size=0.0001)

    assert len(records) == 1
    assert len(calls) == 1
    # exactly 2 series passed (daily, weekly) -- never a 3rd (h4)
    assert len(calls[0]) == 2


def test_run_backtest_skips_erl_cap_entirely_when_disabled(synthetic_cache, monkeypatch):
    # erl_cap=False is for comparing flat-rr against ERL-capped, not a
    # claim that the cap is wrong -- _nearest_erl() must not even be
    # called (not just have its result ignored), and the recorded target
    # must equal the flat rr target with nothing capping it.
    import backtest.engine.runner as runner_module
    calls = []
    monkeypatch.setattr(runner_module, "_nearest_erl", lambda *a, **k: calls.append(a))

    records = run_backtest(SYMBOL, "conservative", source=SOURCE, pip_size=0.0001, erl_cap=False)

    assert len(records) == 1
    assert calls == []
    trade = records[0]
    assert trade.erl_price is None
    assert trade.erl_capped is False
    assert trade.primary_target == trade.raw_target


def test_find_liquidity_setups_finds_breakout_then_liquidity_then_reaction_level():
    h4 = [
        H4(0, 1.1000, 1.1010, 1.0995, 1.1005),
        H4(1, 1.1005, 1.1015, 1.1000, 1.1010),
        H4(2, 1.1010, 1.1030, 1.1005, 1.1020),
        H4(3, 1.1020, 1.1025, 1.1010, 1.1015),
        H4(4, 1.1015, 1.1022, 1.1008, 1.1012),
        H4(5, 1.1012, 1.1038, 1.1010, 1.1035),
        H4(6, 1.1035, 1.1042, 1.1025, 1.1030),
        H4(7, 1.1030, 1.1032, 1.1015, 1.1020),
        H4(8, 1.1020, 1.1028, 1.1018, 1.1025),
    ]
    n = 2
    confs = detect_confirmations(h4, n)
    levels = detect_key_levels(h4, n)
    setups = _find_liquidity_setups(h4, confs, levels, n)

    assert len(setups) == 1
    setup = setups[0]
    assert setup.direction == Direction.BULLISH
    assert setup.liquidity_price == pytest.approx(1.1015)
    # 3 same-direction candidates are in play here (1.1005, 1.101, 1.1012),
    # ordered nearest-to-extreme from the swept liquidity point (1.1015):
    # "we don't predict, we react" -- _find_liquidity_setups() itself makes
    # no pick, it just orders the candidates for _find_entry_candidates()
    # to try in sequence.
    assert [lvl.price for lvl in setup.reaction_level_candidates] == pytest.approx([1.1012, 1.101, 1.1005])


def test_find_liquidity_setups_yields_nothing_without_a_breakout():
    # Flat, directionless H4 candles -- no swing extreme ever gets a body
    # close beyond it, so detect_confirmations() produces nothing, and
    # _find_liquidity_setups() correctly finds no setups either.
    h4 = [H4(i, 1.1000, 1.1005, 1.0995, 1.1000) for i in range(9)]
    n = 2
    confs = detect_confirmations(h4, n)
    levels = detect_key_levels(h4, n)
    assert _find_liquidity_setups(h4, confs, levels, n) == []


def test_run_backtest_rejects_a_bias_aligned_engulf_with_no_underlying_cascade(tmp_path, monkeypatch):
    # Regression test for the actual reported problem: an earlier version
    # of this runner fired on ANY H1 engulfing candle aligned with bias,
    # with no check that a real Bishop-cascade setup (4H breakout ->
    # liquidity sweep -> KL reaction) had actually formed -- and came back
    # from a live run with a 1.6% win rate. A flat H4 series (no breakout
    # at all) plus the exact H1 engulf that used to trigger an entry under
    # the old logic must now produce ZERO trades.
    monkeypatch.setattr(cache, "DATA_ROOT", str(tmp_path))

    daily = [
        D(0, 1.100, 1.105, 1.098, 1.102),
        D(1, 1.102, 1.108, 1.100, 1.106),
        D(2, 1.106, 1.112, 1.104, 1.107),
        D(3, 1.107, 1.109, 1.102, 1.104),
        D(4, 1.104, 1.106, 1.095, 1.096),
        D(5, 1.096, 1.099, 1.097, 1.098),
        D(6, 1.098, 1.101, 1.097, 1.099),
        D(7, 1.099, 1.100, 1.090, 1.097),
        D(8, 1.097, 1.120, 1.096, 1.115),
    ]
    h4_flat = [H4(i, 1.1000, 1.1005, 1.0995, 1.1000) for i in range(9)]
    h1 = [
        H1(0, 1.1000, 1.1005, 1.0998, 1.1003),
        H1(1, 1.1003, 1.1008, 1.1001, 1.1006),
        H1(2, 1.1006, 1.1011, 1.1004, 1.1009),
        H1(3, 1.1009, 1.1014, 1.1007, 1.1012),
        H1(4, 1.1012, 1.1017, 1.1010, 1.1015),
        H1(5, 1.1020, 1.1025, 1.0995, 1.1000),  # bearish -- gets engulfed next
        H1(6, 1.0998, 1.1035, 1.0996, 1.1030),  # bullish engulf -- would have fired under the old logic
        H1(7, 1.1030, 1.1050, 1.1015, 1.1045),
        H1(8, 1.1045, 1.1090, 1.1040, 1.1085),
        H1(9, 1.1085, 1.1145, 1.1080, 1.1140),
    ]
    _write("D", daily)
    _write("H4", h4_flat)
    _write("H1", h1)

    records = run_backtest(SYMBOL, "conservative", source=SOURCE, pip_size=0.0001)
    assert records == []


def test_run_backtest_rejects_invalid_entry_style(synthetic_cache):
    with pytest.raises(ValueError):
        run_backtest(SYMBOL, "yolo", source=SOURCE)


def test_run_backtest_returns_empty_for_missing_data(tmp_path, monkeypatch):
    monkeypatch.setattr(cache, "DATA_ROOT", str(tmp_path))
    assert run_backtest("NOPE", "conservative", source=SOURCE) == []


@pytest.fixture
def synthetic_cache_with_weekly(synthetic_cache):
    # Same bullish sweep+break shape as the `daily` fixture above (validated
    # in test_structure.py), just scaled/timestamped as weekly candles well
    # before H1_BASE -- so Weekly's bootstrapped bias is BULLISH and active
    # by the time the H1 entry fires.
    weekly = [
        W(0, 1.080, 1.085, 1.078, 1.082),
        W(1, 1.082, 1.088, 1.080, 1.086),
        W(2, 1.086, 1.092, 1.084, 1.087),
        W(3, 1.087, 1.089, 1.082, 1.084),
        W(4, 1.084, 1.086, 1.075, 1.076),
        W(5, 1.076, 1.079, 1.077, 1.078),
        W(6, 1.078, 1.081, 1.077, 1.079),
        W(7, 1.079, 1.080, 1.070, 1.077),
        W(8, 1.077, 1.100, 1.076, 1.095),
    ]
    _write("W", weekly)
    return synthetic_cache


def test_run_backtest_weekly_bias_takes_priority_when_available(synthetic_cache_with_weekly):
    records = run_backtest(SYMBOL, "conservative", source=SOURCE, pip_size=0.0001)

    assert len(records) == 1
    trade = records[0]
    assert trade.bias_weekly == Direction.BULLISH
    assert trade.effective_bias_timeframe == "Weekly"  # Weekly outranks Daily/H4 per TIMEFRAME_PRIORITY


def test_stop_on_correct_side_rejects_inverted_bullish_stop():
    # Regression test for a real corruption found via a synthetic stress
    # run: an "origin" trade's stop comes from a Daily-timeframe structural
    # extreme snapshot that can be stale relative to current H1 price. When
    # that snapshot ends up ABOVE the entry price for a BULLISH trade, the
    # computed "stop" isn't actually downside protection -- hitting it is a
    # favorable move, so the trade would close as "closed_loss" while
    # carrying a POSITIVE r_multiple. This must be rejected before a trade
    # is opened, not silently logged.
    assert _stop_on_correct_side(entry_price=1.2000, stop_loss=1.1950, direction=Direction.BULLISH) is True
    assert _stop_on_correct_side(entry_price=1.2000, stop_loss=1.2050, direction=Direction.BULLISH) is False
    assert _stop_on_correct_side(entry_price=1.2000, stop_loss=1.2050, direction=Direction.BEARISH) is True
    assert _stop_on_correct_side(entry_price=1.2000, stop_loss=1.1950, direction=Direction.BEARISH) is False


def test_run_backtest_falls_back_to_daily_when_weekly_data_missing(synthetic_cache):
    # No "W" cache written -- regression check that the pre-Weekly behavior
    # (Daily->H4->H1 chain) still works unchanged when Weekly data isn't
    # available yet for an instrument.
    records = run_backtest(SYMBOL, "conservative", source=SOURCE, pip_size=0.0001)

    assert len(records) == 1
    trade = records[0]
    assert trade.bias_weekly is None
    assert trade.effective_bias_timeframe == "Daily"


# ---- stop_anchor="structural": anchor the stop to the setup's own
# reaction-leg extreme rather than a candle wick, and drop the width test.
# Direct 2026-09-01/02 correction from the source study -- see
# OPERATIONS_LOG.md. The pip WIDTH is an output, never a target or a cap.

def test_reaction_leg_extreme_bearish_takes_the_highest_high_of_the_leg():
    h1 = [
        H1(0, 1.1020, 1.1024, 1.1018, 1.1021),
        H1(1, 1.1021, 1.1043, 1.1010, 1.1013),   # the leg's high: 1.1043
        H1(2, 1.1013, 1.1030, 1.1008, 1.1010),
        H1(3, 1.1010, 1.1035, 1.1005, 1.1030),   # entry candle
    ]
    assert _reaction_leg_extreme(h1, 3, Direction.BEARISH, None) == pytest.approx(1.1043)


def test_reaction_leg_extreme_bullish_takes_the_lowest_low_of_the_leg():
    h1 = [
        H1(0, 1.1020, 1.1024, 1.1018, 1.1021),
        H1(1, 1.1021, 1.1023, 1.1002, 1.1013),   # the leg's low: 1.1002
        H1(2, 1.1013, 1.1014, 1.1008, 1.1010),
        H1(3, 1.1010, 1.1035, 1.1005, 1.1030),   # entry candle
    ]
    assert _reaction_leg_extreme(h1, 3, Direction.BULLISH, None) == pytest.approx(1.1002)


def test_reaction_leg_extreme_ignores_structure_older_than_the_key_level():
    # THE point of the whole change: an extreme from before this setup
    # existed must not become its stop. CHFJPY's live stop landed at
    # 198.101 -- the 28 Aug highs -- on a setup whose entire session
    # traded 197.1-197.7.
    h1 = [
        H1(0, 1.1020, 1.1900, 1.1018, 1.1021),   # ancient spike, unrelated
        H1(1, 1.1021, 1.1043, 1.1010, 1.1013),
        H1(2, 1.1013, 1.1030, 1.1008, 1.1010),
        H1(3, 1.1010, 1.1035, 1.1005, 1.1030),
    ]
    kl_time = H1_BASE + pd.Timedelta(hours=1)   # key level formed at index 1
    assert _reaction_leg_extreme(h1, 3, Direction.BEARISH, kl_time) == pytest.approx(1.1043)
    # Without the scoping, the ancient spike would win:
    assert _reaction_leg_extreme(h1, 3, Direction.BEARISH, None) == pytest.approx(1.1900)


def test_reaction_leg_extreme_is_bounded_when_the_key_level_predates_the_window():
    # A key level far in the past must not drag the window back forever --
    # max_lookback still bounds it.
    h1 = [H1(i, 1.1020, 1.1024 + (0.01 if i == 0 else 0), 1.1018, 1.1021) for i in range(10)]
    ancient = H1_BASE - pd.Timedelta(days=30)
    assert _reaction_leg_extreme(h1, 9, Direction.BEARISH, ancient, max_lookback=3) == pytest.approx(1.1024)


def test_structural_anchor_never_uses_the_collapsed_key_level_fallback(synthetic_cache):
    # The default can emit a stop_kind of *_kl_fallback, which on
    # aggressive style anchors to the entry price itself (a ~1 pip stop --
    # the live EURGBP INVALID_STOPS rejection). Structural mode must never
    # produce that kind at all.
    for style in ("conservative", "aggressive"):
        records = run_backtest(SYMBOL, style, source=SOURCE, pip_size=0.0001,
                                stop_anchor="structural")
        for trade in records:
            assert trade.stop_kind.endswith("_structural")
            assert "kl_fallback" not in trade.stop_kind


def test_structural_anchor_leaves_the_default_path_untouched(synthetic_cache):
    default = run_backtest(SYMBOL, "aggressive", source=SOURCE, pip_size=0.0001)
    assert default[0].stop_kind == "engulfing"      # unchanged by the new flag existing
    assert default[0].stop_loss == pytest.approx(1.10040)


# ---- stop_anchor="zone": the rule read directly off Bishop's 60-page
# chart deck (all pages studied 2026-09-02, ~35 measured trades, zero
# exceptions). Stop = FAR EDGE of the imbalance zone the entry is taken
# from, so the stop distance is that zone's own height. Trigger-
# independent, no width test, and no zone => skip the setup.

def test_zone_anchor_skips_a_setup_with_no_identifiable_zone(synthetic_cache):
    # The core discipline: no zone means no defined invalidation point, so
    # there is no valid stop and the trade must not be taken at all --
    # rather than falling back to a candle wick, which is what the default
    # does and what put a CHFJPY stop at 198.101 on a session that traded
    # 197.1-197.7. This fixture has no overlapping imbalance.
    default = run_backtest(SYMBOL, "aggressive", source=SOURCE, pip_size=0.0001)
    assert len(default) == 1                       # default still takes it, on a wick anchor
    assert default[0].stop_kind == "engulfing"

    zoned = run_backtest(SYMBOL, "aggressive", source=SOURCE, pip_size=0.0001,
                          stop_anchor="zone")
    assert zoned == []


def test_zone_anchor_stop_is_the_far_edge_of_the_zone_bullish():
    # Direct check of the rule against the one page in the deck that
    # pairs a chart with its broker screenshot: EURCHF, pink zone
    # 0.93147-0.93193, order BUY LIMIT 0.93193 / SL 0.93147. A long's
    # stop is the zone's LOW (far edge), padded.
    stop = imbalance_stop_loss(0.93147, 0.93193, Direction.BULLISH, pip_size=0.0001)
    assert stop < 0.93147                      # just past the far edge
    assert stop == pytest.approx(0.93147 - 0.0001)


def test_zone_anchor_stop_is_the_far_edge_of_the_zone_bearish():
    # Mirror, per the deck's shorts (e.g. EURNZD H3: zone 1.96156-1.96472
    # sitting ABOVE entry, red label at 1.96472 = the stop).
    stop = imbalance_stop_loss(1.96156, 1.96472, Direction.BEARISH, pip_size=0.0001)
    assert stop > 1.96472
    assert stop == pytest.approx(1.96472 + 0.0001)


def test_zone_anchor_imposes_no_width_limit():
    # Observed stops in the deck run 3.0 to 518.9 pips and every one is
    # correct, because each is simply its own zone's height. A width test
    # cannot express that -- MAX_NATURAL_STOP_PIPS=30 would reject the
    # valid EURNZD (31.6), XAUUSD (~62.8), USOIL (68.6/82.8) and
    # XAGUSD (518.9) trades outright.
    tiny = imbalance_stop_loss(0.85289, 0.85319, Direction.BULLISH, pip_size=0.0001)
    huge = imbalance_stop_loss(57.2402, 60.4838, Direction.BEARISH, pip_size=0.001)
    assert tiny == pytest.approx(0.85289 - 0.0001)
    assert huge == pytest.approx(60.4838 + 0.001)


# --- _bootstrap_origin() / origin_kind ------------------------------------
#
# bias.py's own module docstring: "EITHER a plain breakout... OR a
# sweep+break of structure... Both are valid; a confirmation check should
# accept either shape." run_backtest()'s origin bootstrap required the
# stricter sweep+break alone for the very FIRST bias -- an inconsistency
# with the engine's own stated rule, raised directly by the operator
# (2026-09-13) after compare_history_window.py found GBPJPY producing
# zero trades at any tested window: a plain breakout needs only one swing
# pivot to exist, a sweep+break needs a full reversal cycle, so requiring
# the latter for the bootstrap alone can silently need much more history
# than the engine's own confirmation rule would otherwise require.

_SWEEP_BREAK_EVENT = StructureEvent(pd.Timestamp("2026-01-10"), "valid_sweep_break", Direction.BEARISH, 1.05)
_EARLIER_BREAKOUT_CONFIRMATION = Confirmation(pd.Timestamp("2026-01-05"), Direction.BULLISH,
                                               ConfirmationKind.BREAKOUT, 1.10)
_SWEEP_BREAK_CONFIRMATION = Confirmation(pd.Timestamp("2026-01-10"), Direction.BEARISH,
                                          ConfirmationKind.SWEEP_BREAK, 1.05)


def test_bootstrap_origin_default_uses_sweep_break_only():
    result = _bootstrap_origin([_SWEEP_BREAK_EVENT], [_EARLIER_BREAKOUT_CONFIRMATION, _SWEEP_BREAK_CONFIRMATION],
                                origin_kind="sweep_break")
    assert result is _SWEEP_BREAK_EVENT


def test_bootstrap_origin_sweep_break_mode_ignores_confirmations_entirely():
    """A breakout-only confirmations list (no sweep_break present) still
    yields no origin under the default mode, even though "any" mode
    would find one -- confirms the two modes are genuinely independent
    code paths, not one silently falling back to the other."""
    result = _bootstrap_origin([], [_EARLIER_BREAKOUT_CONFIRMATION], origin_kind="sweep_break")
    assert result is None


def test_bootstrap_origin_any_mode_prefers_the_earlier_breakout():
    result = _bootstrap_origin([_SWEEP_BREAK_EVENT], [_EARLIER_BREAKOUT_CONFIRMATION, _SWEEP_BREAK_CONFIRMATION],
                                origin_kind="any")
    assert result is _EARLIER_BREAKOUT_CONFIRMATION
    assert result.direction == Direction.BULLISH   # the earlier breakout's direction, not the later sweep+break's


def test_bootstrap_origin_any_mode_falls_back_to_sweep_break_when_no_breakout_exists():
    result = _bootstrap_origin([_SWEEP_BREAK_EVENT], [_SWEEP_BREAK_CONFIRMATION], origin_kind="any")
    assert result is _SWEEP_BREAK_CONFIRMATION


def test_bootstrap_origin_any_mode_with_no_confirmations_at_all_is_none():
    result = _bootstrap_origin([_SWEEP_BREAK_EVENT], [], origin_kind="any")
    assert result is None


def test_run_backtest_any_origin_matches_default_when_no_earlier_breakout_exists(synthetic_cache):
    """The fixture's own daily series has exactly one confirmation of any
    kind (the day-8/9 sweep+break itself -- verified directly against
    detect_confirmations()), so "any" mode has nothing earlier to prefer
    and must reproduce the default bit-for-bit. A genuine regression
    check: the new code path is inert when it should be."""
    default = run_backtest(SYMBOL, "conservative", source=SOURCE, pip_size=0.0001)
    any_mode = run_backtest(SYMBOL, "conservative", source=SOURCE, pip_size=0.0001, origin_kind="any")
    assert len(default) == 1
    assert default == any_mode
