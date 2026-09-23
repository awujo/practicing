import pandas as pd
import pytest

from ...data_pipeline import cache
from ..candles import Candle
from ..structure import Direction
from ..bias import detect_confirmations, Confirmation, ConfirmationKind
from ..key_levels import detect_key_levels, KeyLevel
from ..entries import imbalance_stop_loss
from ..runner import (
    run_backtest, _stop_on_correct_side, _find_liquidity_setups, _find_entry_candidates,
    _aligned_timeframes, _reaction_trigger, _natural_stop_too_wide, _nearest_erl, _unswept_period_extremes,
    _resolve_date_range, _parse_rr, _resolve_trade_outcome, _reaction_leg_extreme, _bootstrap_origin,
    _trim_to_recent_years, LiquiditySetup, TRIGGERS_TAUGHT,
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
    # "We don't predict, we react": the candidates are ordered
    # nearest-to-extreme from the swept pool and tried in sequence; the
    # fixture's H1(2)/H1(3) touch-and-engulf is a genuine reaction off
    # the winner, so the farther candidates are never tried.
    # CHANGED 2026-09-18 (review finding 1): was 1.1012. That level is
    # an A/V key level confirmed by bar i+n, and bar i+n is stamped at
    # its OPEN -- so it is readable only once that bar CLOSES, which is
    # after this reaction. The next candidate down, 1.1010, wins now.
    assert trade.key_level_price == pytest.approx(1.1010)
    # open_close, not "V": the level that wins under corrected timing
    # is a different shape as well as a different price.
    assert trade.key_level_shape == "open_close"
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
    # CHANGED 2026-09-18: was None. The daily fixture's last bar (day 8,
    # high 1.1200) closed eleven days before this entry, so it is a real
    # untaken ERL point. It used to be dropped because
    # `_unswept_period_extremes` tested "does a successor bar exist"
    # rather than "has this bar closed", and day 8 has no day 9 -- the
    # same wrong proxy that made live signals appear hours late.
    #
    # It does not CAP anything (1.1108 is nearer than 1.1200 for a long),
    # so the target, R and win are all unchanged -- only the recorded
    # candidate is, which is what makes this a safe correction rather
    # than a behaviour change hiding in a test edit.
    assert trade.erl_price == pytest.approx(1.1200)
    assert trade.erl_capped is False
    assert trade.primary_target == pytest.approx(trade.raw_target)


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
    # CHANGED 2026-09-18 (review finding 1): was 1.1012. That level is
    # an A/V key level confirmed by bar i+n, and bar i+n is stamped at
    # its OPEN -- so it is readable only once that bar CLOSES, which is
    # after this reaction. The next candidate down, 1.1010, wins now.
    assert records[0].entry_price == pytest.approx(1.1010)
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
    # The two are DIFFERENT FACTS and each gets its own field. An earlier
    # version of both the code and this test had `trigger_type` overwritten
    # with "plug_and_play" here, which erased the only record of which
    # pattern fired -- and in the 2026-09-23 run that was 22% of all
    # trades, making the trigger breakdown unreadable. The stop rule is
    # plug-and-play; the trigger that fired is still the engulfing.
    assert trade.trigger_type == "engulfing"
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
    # Task 8: ERL is Daily/Weekly period extremes, not H4.
    #
    # CHANGED 2026-09-18: was an uncapped 3:1 at 1.1108. Day 1's high
    # (1.1080) closed at midnight, three hours before this entry, and it
    # is a real untaken point above it -- so the 3:1 target is capped
    # there.
    #
    # It used to be discarded as "already swept by day 2", whose high is
    # 1.1120. But day 2 is the day this entry happens ON: it opened three
    # hours ago and does not close until tomorrow. Asserting at 03:00
    # that it has taken 1.1080 requires knowing the rest of the day. The
    # sweep test now requires the SWEEPING period to have closed as well.
    #
    # The trade-off is explicit and conservative: an ERL that intraday
    # price has genuinely already taken stays on the candidate list until
    # its period closes, because this function only ever sees period
    # candles and cannot tell. Overstating available liquidity caps
    # targets slightly short; understating it -- the old behaviour --
    # made the answer depend on data that did not exist yet, which is
    # what made signals appear and disappear for days.
    assert trade.primary_target == pytest.approx(1.1080)
    # 1.92R, not the full 3R: the ERL cap shortens the target, and the
    # realized R follows it. That is the cap working as designed -- see
    # primary_target()'s docstring on it reducing realized R:R rather
    # than the ratio itself.
    assert trade.r_multiple == pytest.approx(1.9230769, abs=1e-6)
    assert trade.erl_price == pytest.approx(1.1080)
    assert trade.erl_capped is True


def test_reaction_trigger_prefers_engulfing_then_falls_through_to_fourth_man():
    # Engulfing: bearish prev, bullish curr fully covering prev's body.
    prev = H1(0, 1.1020, 1.1025, 1.0995, 1.1000)
    curr = H1(1, 1.0998, 1.1040, 1.0996, 1.1030)
    assert _reaction_trigger([prev, curr], 1, Direction.BULLISH) == "engulfing"

    # 4th man: curr sweeps prev's low, reclaims into prev's range, prev's
    # high stays untouched -- NOT an engulfing shape (curr's open sits
    # above prev's close, so it doesn't "fully cover" prev's body).
    prev2 = H1(2, 1.1010, 1.1020, 1.1000, 1.1015)
    curr2 = H1(3, 1.1015, 1.1018, 1.0990, 1.1005)
    assert _reaction_trigger([prev2, curr2], 1, Direction.BULLISH) == "fourth_man"

    # Neither pattern fires.
    prev3 = H1(4, 1.1010, 1.1020, 1.1000, 1.1015)
    curr3 = H1(5, 1.1015, 1.1018, 1.1005, 1.1010)  # stays fully inside prev3's range
    assert _reaction_trigger([prev3, curr3], 1, Direction.BULLISH) is None


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
        # Sweeps the H4 liquidity pool, which corrected known_at timing
        # moved from 1.1015 to 1.1008 (2026-09-18 review, finding 1) --
        # so this low drops 1.1010 -> 1.1005 to still take it. Without
        # that the sweep lands one candle later and the H1(1)/H1(2)
        # pair this test exists to exercise is never examined: the test
        # went green on an `engulfing` and stopped testing 4th-man at all.
        H1(1, 1.1021, 1.1023, 1.1005, 1.1013),
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
    # 1 pip beyond the H4 reaction level itself, NOT the 64-pip engulfed
    # wick (1.0950).
    # CHANGED 2026-09-18 (review finding 1): was 1.1012. That level is
    # an A/V key level confirmed by bar i+n, and bar i+n is stamped at
    # its OPEN -- so it is readable only once that bar CLOSES, which is
    # after this reaction. The next candidate down, 1.1010, wins now.
    assert trade.stop_loss == pytest.approx(1.1009)
    assert trade.status == "closed_win"
    # Task 8: ERL is Daily/Weekly period extremes, not H4 -- same
    # dwarfed-by-day8's-still-forming-high reasoning as
    # test_run_backtest_produces_a_winning_trade_end_to_end, so no ERL
    # candidate qualifies and the plain, uncapped 3:1 target applies.
    # 1.1093, not 1.1087: 3:1 off the corrected stop (1.1009, see above).
    assert trade.primary_target == pytest.approx(1.1093)
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
    # itself is never returned, because as_of_time falls INSIDE it and a
    # still-forming period is not a fixed "previous" reference.
    #
    # as_of_time moved 2026-09-18 from 2024-01-05 to midday on day2. It
    # had been asserting that a bar which closed two days earlier was
    # still forming -- true only because the old implementation used
    # "does a successor exist in the data" as its proxy for "has this
    # closed", which is the bug being fixed. The property the test is
    # named for is unchanged and still checked, just asked at a moment
    # when it actually applies.
    extremes = _unswept_period_extremes(daily, pd.Timestamp("2024-01-03 12:00"), "high")
    assert extremes == [pytest.approx(1.1050), pytest.approx(1.1010)]


def test_unswept_period_extremes_excludes_a_high_already_swept_by_a_later_day():
    daily = [
        D(0, 1.0990, 1.1050, 1.0980, 1.1000),  # completed high 1.1050 -- swept below
        D(1, 1.1000, 1.1010, 1.0990, 1.1005),
        D(2, 1.1005, 1.1080, 1.0995, 1.1010),  # day2's high (1.1080) exceeds day0's (1.1050)
        D(3, 1.1010, 1.1015, 1.1000, 1.1012),  # only here to confirm day2 has closed
    ]
    # day0's high (1.1050) was exceeded by day2's high (1.1080) -- no
    # longer real untaken liquidity. Only day2's own high remains; day3
    # is excluded because as_of_time falls inside it (see the note in
    # test_unswept_period_extremes_excludes_the_still_forming_last_period
    # on why this moved off 2024-01-05).
    extremes = _unswept_period_extremes(daily, pd.Timestamp("2024-01-04 12:00"), "high")
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


def _liquidity_setup_h4():
    return [
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


def test_find_liquidity_setups_swing_mode_finds_breakout_then_liquidity_then_reaction_level():
    """The swing path, pinned.

    CHANGED 2026-09-18 (review finding 1). This used to assert the pool
    was 1.1015 and said swing "must keep producing exactly what it always
    produced" -- pinned so the single-candle A/B had a fixed baseline.
    That premise is gone: the baseline itself was reading swing points a
    bar before they existed.

    A swing point at bar i is confirmed by bar i+n, and bar i+n is
    stamped at its OPEN, so the point is readable only once that bar
    CLOSES. With that corrected, the 1.1015 pool is not yet known when
    the breakout happens and the next one that IS known, 1.1008, is
    armed instead.

    This is the correct answer, not a regression -- and it means every
    A/B ever run between swing and the single-candle modes was measured
    against a baseline that could see ahead. Those comparisons have to be
    re-run."""
    h4 = _liquidity_setup_h4()
    n = 2
    confs = detect_confirmations(h4, n)
    levels = detect_key_levels(h4, n)
    setups = _find_liquidity_setups(h4, confs, levels, n, liquidity_mode="swing")

    assert len(setups) == 1
    setup = setups[0]
    assert setup.direction == Direction.BULLISH
    assert setup.liquidity_price == pytest.approx(1.1008)  # was 1.1015 pre-fix
    # Candidates ordered nearest-to-extreme from the swept pool: "we
    # don't predict, we react" -- _find_liquidity_setups() makes no pick,
    # it just orders them for _find_entry_candidates() to try in
    # sequence.
    #
    # Pre-fix this was [1.1012, 1.101, 1.1005]. 1.1012 has dropped out
    # for the same reason the pool moved: an A/V key level is confirmed
    # by bar i+n, which is stamped at its open, so it is readable only
    # once that bar closes -- and by then the setup has already formed.
    assert [lvl.price for lvl in setup.reaction_level_candidates] == pytest.approx([1.101, 1.1005])


def test_single_candle_mode_arms_every_post_breakout_low_not_just_the_swing():
    """The corrected concept. The swing path can only ever return 1.1015
    here (the one local extreme); the candles either side of it left
    1.1025 and 1.1018 sitting there too, and which one price comes back
    for is not knowable in advance -- the trader's own JP225 chart had
    two marked at once."""
    h4 = _liquidity_setup_h4()
    n = 2
    confs = detect_confirmations(h4, n)
    levels = detect_key_levels(h4, n)
    setups = _find_liquidity_setups(h4, confs, levels, n, liquidity_mode="single_candle")

    assert [s.liquidity_price for s in setups] == pytest.approx([1.101, 1.1025, 1.1015, 1.1018])
    assert all(s.direction == Direction.BULLISH for s in setups)
    # The swing path's single pool is still among them -- this is a
    # superset, not a different set.
    assert pytest.approx(1.1015) in [s.liquidity_price for s in setups]
    # Distinct setup_ids, so the trade loop can cap each at one trade.
    assert len({s.setup_id for s in setups}) == len(setups)


def test_the_breakout_candles_own_low_is_a_valid_pool():
    """Operator correction, 2026-09-16: "it must not be the next candle
    after the breakout -- it might even be the breakout candle low."

    An earlier version excluded it on the reasoning that price has no
    reason to return to the extreme it just broke away from. That was
    wrong, and costly: the swing path's first qualifying point is very
    often exactly this low, so excluding it made "single_candle" a
    different set rather than a superset -- with the most-traded pool
    missing."""
    h4 = _liquidity_setup_h4()
    n = 2
    confs = detect_confirmations(h4, n)
    levels = detect_key_levels(h4, n)
    breakout_time = confs[0].time
    setups = _find_liquidity_setups(h4, confs, levels, n, liquidity_mode="single_candle")

    prices = [s.liquidity_price for s in setups]
    assert pytest.approx(1.1010) in prices, "the breakout candle's own low must be armed"
    assert setups[0].liquidity_time == breakout_time
    # Still nothing from BEFORE the breakout.
    assert all(s.liquidity_time >= breakout_time for s in setups)


def test_single_candle_is_a_true_superset_of_swing():
    """Every pool the swing path finds must also be armed by the
    single-candle path -- otherwise the A/B compares two different sets
    rather than a tighter rule against a looser one.

    NARROWED 2026-09-18 (review finding 1). The two paths no longer share
    a known_at, and correctly so:

      swing point at bar i   -> confirmed by bar i+n, readable at ITS close
      single candle at bar i -> readable at bar i's own close

    So swing pools now become available strictly later than the
    equivalent single-candle pool, and a pool sitting right on a window
    boundary can be admitted by one path and not the other. The subset
    claim therefore holds on PRICES ARMED ANYWHERE, not on the pools
    selected for a particular breakout window.

    Asserting it on the raw pool prices keeps the property the test
    exists for -- single_candle must not MISS anything swing sees -- while
    no longer pretending the two have identical timing."""
    from ...engine.liquidity import single_candle_liquidity, structural_liquidity_points
    h4 = _liquidity_setup_h4()
    swing_pools = {p.price for p in structural_liquidity_points(h4, n=1)}
    sc_pools = ({p.price for p in single_candle_liquidity(h4, "low")}
                | {p.price for p in single_candle_liquidity(h4, "high")})
    assert swing_pools <= sc_pools, (
        f"swing pools missing from single_candle: {swing_pools - sc_pools}")


def test_pool_is_never_swept_by_the_candle_that_formed_it():
    """liquidity_known_at is the forming candle's CLOSE, so a sweep scan
    starting there can never count that candle as taking its own low."""
    h4 = _liquidity_setup_h4()
    n = 2
    confs = detect_confirmations(h4, n)
    levels = detect_key_levels(h4, n)
    for s in _find_liquidity_setups(h4, confs, levels, n, liquidity_mode="single_candle"):
        assert s.liquidity_known_at > s.liquidity_time


def test_max_pools_caps_how_many_setups_one_breakout_can_produce():
    h4 = _liquidity_setup_h4()
    n = 2
    confs = detect_confirmations(h4, n)
    levels = detect_key_levels(h4, n)
    capped = _find_liquidity_setups(h4, confs, levels, n,
                                     liquidity_mode="single_candle", max_pools=1)
    assert len(capped) == 1
    # Oldest first, and the oldest is now the breakout candle itself.
    assert capped[0].liquidity_price == pytest.approx(1.101)
    assert capped[0].liquidity_time == confs[0].time


def test_find_liquidity_setups_rejects_an_unknown_mode():
    h4 = _liquidity_setup_h4()
    n = 2
    confs = detect_confirmations(h4, n)
    levels = detect_key_levels(h4, n)
    with pytest.raises(ValueError):
        _find_liquidity_setups(h4, confs, levels, n, liquidity_mode="fractal")


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


def test_run_backtest_close_based_sweep_break_false_matches_default(synthetic_cache):
    """False is the default -- passing it explicitly must be a no-op."""
    default = run_backtest(SYMBOL, "conservative", source=SOURCE, pip_size=0.0001)
    explicit_false = run_backtest(SYMBOL, "conservative", source=SOURCE, pip_size=0.0001,
                                   close_based_sweep_break=False)
    assert default == explicit_false


def test_run_backtest_close_based_sweep_break_true_runs_end_to_end(synthetic_cache):
    """Precise wick-vs-close divergence is covered directly at the
    structure.py/bias.py unit level (see test_structure.py and
    test_bias.py); this just confirms the parameter actually reaches
    run_backtest() end to end without crashing."""
    records = run_backtest(SYMBOL, "conservative", source=SOURCE, pip_size=0.0001,
                            close_based_sweep_break=True)
    assert isinstance(records, list)


# --- max_history_years -------------------------------------------------
#
# The production version of compare_history_window.py's monkeypatched
# windowed_loader() -- see bot/OPERATIONS_LOG.md, 2026-09-13, for the
# per-instrument escalation search that has to confirm any real value
# used here before it's trusted.

def test_trim_to_recent_years_keeps_only_the_trailing_window():
    candles = [D(i, 1, 1, 1, 1) for i in range(5 * 365)]   # D() from this file: one candle/day
    trimmed = _trim_to_recent_years(candles, 1.0)
    assert trimmed[0].time == candles[-1].time - pd.Timedelta(days=365)
    assert trimmed[-1].time == candles[-1].time


def test_trim_to_recent_years_is_a_noop_for_none_or_zero():
    candles = [D(i, 1, 1, 1, 1) for i in range(10)]
    assert _trim_to_recent_years(candles, None) == candles
    assert _trim_to_recent_years(candles, 0) == candles


def test_trim_to_recent_years_handles_an_empty_list():
    assert _trim_to_recent_years([], 2.0) == []


def test_run_backtest_max_history_years_none_matches_default(synthetic_cache):
    """None is the default -- passing it explicitly must be a no-op."""
    default = run_backtest(SYMBOL, "conservative", source=SOURCE, pip_size=0.0001)
    explicit_none = run_backtest(SYMBOL, "conservative", source=SOURCE, pip_size=0.0001,
                                  max_history_years=None)
    assert default == explicit_none


def test_run_backtest_max_history_years_generous_window_matches_default(synthetic_cache):
    """The fixture's whole span is under a month -- a 5-year cap on every
    granularity can't possibly cut anything, so this must reproduce the
    unpatched baseline bit-for-bit."""
    default = run_backtest(SYMBOL, "conservative", source=SOURCE, pip_size=0.0001)
    generous = run_backtest(SYMBOL, "conservative", source=SOURCE, pip_size=0.0001,
                             max_history_years={"D": 5, "W": 5, "H4": 5, "H1": 5})
    assert default == generous


def test_run_backtest_max_history_years_too_short_loses_the_origin(synthetic_cache):
    """Same fixture used in test_a_window_too_short_to_see_the_origin_breakout_loses_the_trade
    (compare_history_window.py's own tests) -- capping Daily to 1 day cannot
    see the day-8 breakout, so this must return no trades, the same way
    `if first_origin is None: return []` already does for real."""
    records = run_backtest(SYMBOL, "conservative", source=SOURCE, pip_size=0.0001,
                            max_history_years={"D": 1 / 365, "W": 1 / 365,
                                                "H4": 1 / 365, "H1": 1 / 365})
    assert records == []


# ---------------------------------------------------------------------------
# One setup may now offer several reactions.
#
# Why: _find_entry_candidates() picks BEFORE any of the trade loop's gates
# run (entry-time bias re-check, alignment, IRL/ERL, rollover window, zone
# fill, R:R). USDCHF 2026-09-15 is the case that exposed it -- the single
# candidate was an engulfing at 22:00, thrown out by avoid_rollover_entries
# because 22:00 is the rollover hour, while two genuine 4th-man reactions
# off the same 0.81842 level followed at 04:00->05:00 and 05:00->06:00 the
# next morning and were never looked at.
# ---------------------------------------------------------------------------

def _h1(i, o, h, l, c):
    return Candle(pd.Timestamp("2024-01-01") + pd.Timedelta(hours=i), o, h, l, c, 1000)


def _two_reaction_series():
    """H1 where, after the sweep, the SAME level produces two separate
    4th-man reactions. Level sits at 1.1000."""
    from ..key_levels import KeyLevel as KL
    level = KL(pd.Timestamp("2023-12-31"), 1.1000, "V", Direction.BULLISH)
    h1 = [
        _h1(0, 1.1020, 1.1025, 1.1015, 1.1020),
        _h1(1, 1.1020, 1.1022, 1.1004, 1.1010),   # sweeps the 1.1005 pool
        _h1(2, 1.1010, 1.1014, 1.1002, 1.1008),   # prev for reaction A
        _h1(3, 1.1008, 1.1012, 1.0998, 1.1006),   # 4th man: takes 1.1002, reclaims
        _h1(4, 1.1006, 1.1010, 1.1001, 1.1004),   # prev for reaction B
        _h1(5, 1.1004, 1.1008, 1.0997, 1.1003),   # 4th man again, same level
        _h1(6, 1.1003, 1.1030, 1.1002, 1.1028),
    ]
    setup = LiquiditySetup(
        direction=Direction.BULLISH,
        breakout_time=pd.Timestamp("2023-12-31"),
        liquidity_price=1.1005,
        liquidity_time=pd.Timestamp("2023-12-31 20:00"),
        liquidity_known_at=h1[1].time,
        sweep_from=h1[1].time,
        reaction_level_candidates=[level],
        setup_id=7,
    )
    return h1, setup


def test_a_setup_can_offer_more_than_one_reaction():
    h1, setup = _two_reaction_series()
    found = _find_entry_candidates(h1, [setup])
    assert len(found) >= 2, "a rejected first pick must not be the end of the setup"
    assert all(c.setup_id == 7 for c in found)
    assert [c.index for c in found] == sorted(c.index for c in found)


def test_max_per_setup_caps_the_reactions_returned():
    h1, setup = _two_reaction_series()
    assert len(_find_entry_candidates(h1, [setup], max_per_setup=1)) == 1


def test_a_pool_is_not_swept_by_its_own_forming_candle():
    """The self-sweep bug, directly. The pool sits at 1.0990, which ONLY
    the forming candle ever traded through -- no later candle comes close.
    Scanning from liquidity_time would call that a sweep; scanning from
    liquidity_known_at correctly finds none, so there is no setup."""
    from ..key_levels import KeyLevel as KL
    h1 = [
        _h1(0, 1.1000, 1.1005, 1.0990, 1.1000),   # forms the low
        _h1(1, 1.1000, 1.1010, 1.0998, 1.1008),
        _h1(2, 1.1008, 1.1015, 1.1002, 1.1012),
        _h1(3, 1.1012, 1.1020, 1.1008, 1.1018),
    ]
    setup = LiquiditySetup(
        direction=Direction.BULLISH, breakout_time=pd.Timestamp("2023-12-31"),
        liquidity_price=1.0990, liquidity_time=h1[0].time,
        liquidity_known_at=h1[1].time,
        sweep_from=h1[1].time,   # the fix: from the pool's CLOSE
        reaction_level_candidates=[KL(pd.Timestamp("2023-12-31"), 1.1000, "V",
                                       Direction.BULLISH)],
        setup_id=1,
    )
    assert _find_entry_candidates(h1, [setup]) == []
    # And the only reason it is empty is the start of the scan: the
    # forming candle really did trade through 1.0990, nothing else did.
    assert h1[0].low <= 1.0990
    assert min(c.low for c in h1[1:]) > 1.0990


def test_the_legacy_scan_start_really_was_the_thing_causing_self_sweeps():
    """Companion to the test above: same candles, same pool, only
    `sweep_from` differs. Starting at the pool's own open (the legacy
    behavior) DOES produce a candidate off a sweep that never happened.
    Without this, the assertion that the fixed version returns nothing
    proves nothing -- an empty list can come from anywhere."""
    from ..key_levels import KeyLevel as KL
    h1 = [
        _h1(0, 1.1000, 1.1005, 1.0990, 1.1000),
        _h1(1, 1.1000, 1.1010, 1.0996, 1.1002),
        _h1(2, 1.1002, 1.1006, 1.0994, 1.1004),   # 4th man off 1.1000
        _h1(3, 1.1004, 1.1020, 1.1000, 1.1018),
    ]
    level = KL(pd.Timestamp("2023-12-31"), 1.1000, "V", Direction.BULLISH)
    common = dict(direction=Direction.BULLISH, breakout_time=pd.Timestamp("2023-12-31"),
                  liquidity_price=1.0990, liquidity_time=h1[0].time,
                  liquidity_known_at=h1[1].time,
                  reaction_level_candidates=[level], setup_id=1)

    legacy = LiquiditySetup(sweep_from=h1[0].time, **common)
    fixed = LiquiditySetup(sweep_from=h1[1].time, **common)

    assert _find_entry_candidates(h1, [legacy]), "legacy self-sweeps, by construction"
    assert _find_entry_candidates(h1, [fixed]) == []
    assert min(c.low for c in h1[1:]) > 1.0990  # nothing ever really took it


def test_swing_mode_keeps_the_legacy_scan_start_as_the_ab_baseline():
    """"swing" is not "the new path with old pools" -- it is the whole
    pre-2026-09-16 entry path, self-sweep included. A baseline carrying
    half the fix would understate what the fix is worth."""
    h4 = _liquidity_setup_h4()
    n = 2
    confs = detect_confirmations(h4, n)
    levels = detect_key_levels(h4, n)

    for s in _find_liquidity_setups(h4, confs, levels, n, liquidity_mode="swing"):
        assert s.sweep_from == s.liquidity_time
    for s in _find_liquidity_setups(h4, confs, levels, n, liquidity_mode="single_candle"):
        assert s.sweep_from == s.liquidity_known_at
        assert s.sweep_from > s.liquidity_time


# ---------------------------------------------------------------------------
# liquidity_mode="single_candle_h4" -- the sweep AND the rejection off the
# key level both read on the 4H, as the operator reads them off a chart:
# "I want to see a 4H candle come and sweep another 4H candle's low...
# price gets to a KL and on the 4H the candle starts rejecting off it as
# if it is buying. Then the 1H has to give us what we want."
# ---------------------------------------------------------------------------

def test_h4_sweep_and_rejection_needs_both_halves_on_one_candle():
    from ..runner import _h4_sweep_and_rejection
    from ..key_levels import KeyLevel as KL
    level = KL(pd.Timestamp("2023-12-31"), 1.0950, "V", Direction.BULLISH)

    # Takes the 1.1000 pool, wicks into 1.0950, closes back above it.
    good = [H4(0, 1.1050, 1.1060, 1.1010, 1.1040),
            H4(1, 1.1040, 1.1045, 1.0940, 1.1030)]
    c, lvl = _h4_sweep_and_rejection(good, 1.1000, good[0].time,
                                     Direction.BULLISH, [level])
    assert c is good[1] and lvl is level


def test_no_rejection_means_no_setup_rather_than_a_nearest_level_guess():
    """The other modes fall back to whichever level is nearest the pool,
    which is not a claim about price. Here, if no 4H candle closed back
    out of a level, there is nothing to trade."""
    from ..runner import _h4_sweep_and_rejection
    from ..key_levels import KeyLevel as KL
    level = KL(pd.Timestamp("2023-12-31"), 1.0950, "V", Direction.BULLISH)
    # Sweeps the pool and the level, but closes BELOW the level -- broke
    # through it, did not reject off it.
    broke = [H4(0, 1.1050, 1.1060, 1.1010, 1.1040),
             H4(1, 1.1040, 1.1045, 1.0900, 1.0920)]
    c, lvl = _h4_sweep_and_rejection(broke, 1.1000, broke[0].time,
                                     Direction.BULLISH, [level])
    assert c is None and lvl is None


def test_a_candle_that_never_reaches_the_pool_is_not_a_sweep():
    from ..runner import _h4_sweep_and_rejection
    from ..key_levels import KeyLevel as KL
    level = KL(pd.Timestamp("2023-12-31"), 1.0950, "V", Direction.BULLISH)
    never = [H4(0, 1.1050, 1.1060, 1.1010, 1.1040),
             H4(1, 1.1040, 1.1070, 1.1020, 1.1060)]
    c, _lvl = _h4_sweep_and_rejection(never, 1.1000, never[0].time,
                                      Direction.BULLISH, [level])
    assert c is None


def test_the_pool_is_never_swept_by_its_own_candle_on_h4_either():
    from ..runner import _h4_sweep_and_rejection
    from ..key_levels import KeyLevel as KL
    level = KL(pd.Timestamp("2023-12-31"), 1.0950, "V", Direction.BULLISH)
    # Candle 0 both forms the 1.1010 low and would "reject" off the
    # level. Scanning from its own time would return it; scanning from
    # pool_known_at (candle 1's open) cannot.
    candles = [H4(0, 1.1050, 1.1060, 1.0940, 1.1040),
               H4(1, 1.1040, 1.1050, 1.1030, 1.1045)]
    c, _lvl = _h4_sweep_and_rejection(candles, 1.1010, candles[1].time,
                                      Direction.BULLISH, [level])
    assert c is None


def test_bearish_is_the_mirror():
    from ..runner import _h4_sweep_and_rejection
    from ..key_levels import KeyLevel as KL
    level = KL(pd.Timestamp("2023-12-31"), 1.1050, "A", Direction.BEARISH)
    candles = [H4(0, 1.0950, 1.0990, 1.0940, 1.0960),
               H4(1, 1.0960, 1.1060, 1.0955, 1.0970)]
    c, lvl = _h4_sweep_and_rejection(candles, 1.1000, candles[0].time,
                                     Direction.BEARISH, [level])
    assert c is candles[1] and lvl is level


def test_the_deepest_level_actually_rejected_from_wins():
    """Two levels both reached and closed back above -- the one price ran
    furthest into is the one it reacted from."""
    from ..runner import _h4_sweep_and_rejection
    from ..key_levels import KeyLevel as KL
    shallow = KL(pd.Timestamp("2023-12-31"), 1.0980, "V", Direction.BULLISH)
    deep = KL(pd.Timestamp("2023-12-31"), 1.0950, "V", Direction.BULLISH)
    candles = [H4(0, 1.1050, 1.1060, 1.1010, 1.1040),
               H4(1, 1.1040, 1.1045, 1.0940, 1.1030)]
    _c, lvl = _h4_sweep_and_rejection(candles, 1.1000, candles[0].time,
                                      Direction.BULLISH, [shallow, deep])
    assert lvl is deep


def test_h4_mode_marks_its_setups_validated_and_carries_one_level():
    h4 = _liquidity_setup_h4()
    n = 2
    confs = detect_confirmations(h4, n)
    levels = detect_key_levels(h4, n)
    setups = _find_liquidity_setups(h4, confs, levels, n,
                                     liquidity_mode="single_candle_h4")
    for s in setups:
        assert s.h4_validated is True
        # Exactly the level price rejected from -- not a ranked list of
        # guesses for the H1 search to try in turn.
        assert len(s.reaction_level_candidates) == 1


def test_h4_mode_is_a_subset_of_single_candle():
    """Same pools, strictly more required of them. If it ever produced a
    setup single_candle does not, the two are not measuring the same
    concept and the A/B means nothing."""
    h4 = _liquidity_setup_h4()
    n = 2
    confs = detect_confirmations(h4, n)
    levels = detect_key_levels(h4, n)
    loose = {s.liquidity_price for s in _find_liquidity_setups(
        h4, confs, levels, n, liquidity_mode="single_candle", max_pools=99)}
    strict = {s.liquidity_price for s in _find_liquidity_setups(
        h4, confs, levels, n, liquidity_mode="single_candle_h4", max_pools=99)}
    assert strict <= loose


# ---------------------------------------------------------------------------
# The pool window: every 4H candle in the leg, until the trend changes.
#
# Operator, 2026-09-16: "all the 4H candles are still valid to be tested
# as the single candle liquidity low until the trend has changed -- that
# is, we now have a new 4H breakout to the downside." And on a pool being
# taken with nothing happening: "price can still do its own thing, come
# down, take that first 4H candle low and still keep selling. The setup
# is still valid. Maybe the second candle is the thing that will form the
# truly single candle liquidity."
# ---------------------------------------------------------------------------

def _legged_h4():
    """Three rising impulse/pullback cycles then a collapse, which yields
    TWO bullish breakouts (so there is a continuation break inside the
    bullish leg) followed by a bearish one (a real trend change). Both
    are needed: a fixture with only one breakout would let the
    window-boundary tests pass without exercising anything."""
    rows = []
    price = 1.1000
    for _cycle in range(3):
        for _ in range(2):   # pullback -- leaves a swing low behind
            rows.append((price, price + 0.0005, price - 0.0020, price - 0.0018))
            price -= 0.0018
        for _ in range(3):   # impulse -- closes beyond the prior swing high
            rows.append((price, price + 0.0060, price - 0.0003, price + 0.0055))
            price += 0.0055
    for _ in range(5):       # trend change, downward
        rows.append((price, price + 0.0004, price - 0.0070, price - 0.0065))
        price -= 0.0065
    return [H4(i, *r) for i, r in enumerate(rows)]


def test_the_legged_fixture_really_has_a_continuation_and_a_reversal():
    """Guards the fixture itself. Every window test below is vacuous if
    this shape ever stops holding."""
    confs = sorted(detect_confirmations(_legged_h4(), 2), key=lambda c: c.time)
    dirs = [c.direction for c in confs]
    assert dirs.count(Direction.BULLISH) >= 2, "need a continuation break"
    assert Direction.BEARISH in dirs, "need a trend change"
    assert dirs.index(Direction.BEARISH) > 1, "the reversal must come last"


def test_pools_are_unbounded_by_default():
    """A numeric cap is an experiment, not the rule. The default must arm
    every candle in the leg."""
    h4 = _legged_h4()
    n = 2
    confs = detect_confirmations(h4, n)
    levels = detect_key_levels(h4, n)
    uncapped = _find_liquidity_setups(h4, confs, levels, n,
                                       liquidity_mode="single_candle")
    capped = _find_liquidity_setups(h4, confs, levels, n,
                                     liquidity_mode="single_candle", max_pools=1)
    assert len(uncapped) > len(capped)


def test_a_continuation_breakout_does_not_close_the_window():
    """Closing at the next breakout of ANY direction discarded every pool
    formed after a same-direction continuation break."""
    h4 = _legged_h4()
    n = 2
    confs = detect_confirmations(h4, n)
    levels = detect_key_levels(h4, n)
    bull = [c for c in sorted(confs, key=lambda c: c.time)
            if c.direction == Direction.BULLISH]
    assert len(bull) >= 2, "fixture guard should have caught this"
    setups = _find_liquidity_setups(h4, confs, levels, n,
                                     liquidity_mode="single_candle")
    bullish = [s for s in setups if s.direction == Direction.BULLISH]
    # Pools exist on BOTH sides of the continuation break, from the leg
    # that started at the first bullish breakout.
    after_continuation = [s for s in bullish if s.liquidity_time >= bull[1].time]
    assert after_continuation, "pools after a continuation break were dropped"


def test_the_same_pool_is_never_emitted_twice_for_one_direction():
    """An unbounded window plus continuation breakouts would otherwise
    re-emit every pool once per breakout in the leg."""
    h4 = _legged_h4()
    n = 2
    confs = detect_confirmations(h4, n)
    levels = detect_key_levels(h4, n)
    setups = _find_liquidity_setups(h4, confs, levels, n,
                                     liquidity_mode="single_candle")
    seen = [(s.direction, s.liquidity_time) for s in setups]
    assert len(seen) == len(set(seen))


def test_a_swept_pool_with_no_reaction_does_not_retire_the_later_pools():
    """The behaviour the operator described directly: the first candle's
    low gets taken and price keeps selling, and the SECOND candle's low is
    the one that matters. Each pool is its own setup, so a dead one
    cannot consume the others."""
    h4 = _legged_h4()
    n = 2
    confs = detect_confirmations(h4, n)
    levels = detect_key_levels(h4, n)
    setups = _find_liquidity_setups(h4, confs, levels, n,
                                     liquidity_mode="single_candle")
    bullish = sorted([s for s in setups if s.direction == Direction.BULLISH],
                     key=lambda s: s.liquidity_time)
    assert len(bullish) >= 2
    assert len({s.setup_id for s in bullish}) == len(bullish)


def test_swing_mode_keeps_the_any_direction_window():
    """The baseline's bounds are part of what is being measured against."""
    h4 = _legged_h4()
    n = 2
    confs = detect_confirmations(h4, n)
    levels = detect_key_levels(h4, n)
    swing = _find_liquidity_setups(h4, confs, levels, n, liquidity_mode="swing")
    # One pool per breakout at most, exactly as before.
    assert len(swing) <= len(confs)


def test_both_mode_arms_every_pool_either_single_mode_would():
    """liquidity_mode="both" exists because the source says both forms
    count (repeating-a-system video, 04:30-05:45: "it's not all the time
    your form of liquidity is going to be a single candle... sometimes
    it's also going to be like structural liquidity... this is another
    form of liquidity right here").

    The engine only ever had the structural form, and the 2026-09-16
    single_candle mode only had the other -- replacing structural rather
    than joining it, which is the likeliest reason it measured worse.
    So the property that matters is that "both" MISSES NOTHING: every
    pool price either single-source mode finds must be armed here.
    """
    from ...engine.liquidity import single_candle_liquidity, structural_liquidity_points
    h4 = _liquidity_setup_h4()
    sc = ({p.price for p in single_candle_liquidity(h4, "low")}
          | {p.price for p in single_candle_liquidity(h4, "high")})
    swing = {p.price for p in structural_liquidity_points(h4, n=1)}

    n = 2
    confs = detect_confirmations(h4, n)
    levels = detect_key_levels(h4, n)
    both = {s.liquidity_price for s in
            _find_liquidity_setups(h4, confs, levels, n,
                                    liquidity_mode="both", max_pools=99)}

    # Every pool "both" arms must come from one of the two sources -- it
    # must not invent prices of its own.
    assert both <= (sc | swing), f"prices from nowhere: {both - (sc | swing)}"
    # And it must arm strictly more than the swing-only path, or the mode
    # is pointless.
    swing_armed = {s.liquidity_price for s in
                   _find_liquidity_setups(h4, confs, levels, n, liquidity_mode="swing")}
    assert swing_armed <= both, f"swing pools missing from both: {swing_armed - both}"
    assert len(both) > len(swing_armed)


def test_the_default_trigger_set_is_exactly_what_has_always_shipped():
    """Guard against a silent strategy change. Adding the taught trigger
    must not alter a single trade until someone asks for it explicitly --
    every backtest number on record was produced with `is_engulfing`, and
    a default flipped underneath them would make the old results
    incomparable without anyone noticing."""
    from ..runner import TRIGGERS_SHIPPED, TRIGGERS_TAUGHT
    import inspect
    from ..runner import _reaction_trigger, _find_entry_candidates, run_backtest

    assert TRIGGERS_SHIPPED == ("engulfing", "fourth_man")
    # All four Bishop enumerates, his two highest-rated first.
    assert TRIGGERS_TAUGHT == ("sweep_break", "breakout", "disrespect", "fourth_man")
    for fn in (_reaction_trigger, _find_entry_candidates, run_backtest):
        param = inspect.signature(fn).parameters.get("triggers") \
            or inspect.signature(fn).parameters.get("confirmation_triggers")
        assert param.default == TRIGGERS_SHIPPED, f"{fn.__name__} default changed"


def test_the_taught_set_does_not_fire_on_a_classic_candlestick_engulfing():
    """The whole point of the swap. A textbook engulfing is what the code
    has been looking for; it is NOT what the videos describe, and on its
    own it must no longer count as a confirmation."""
    from ..runner import TRIGGERS_TAUGHT

    prev = H1(0, 1.1020, 1.1025, 1.0995, 1.1000)
    curr = H1(1, 1.0998, 1.1040, 1.0996, 1.1030)
    assert _reaction_trigger([prev, curr], 1, Direction.BULLISH) == "engulfing"
    # Same two candles, taught set: no open-close key level was built and
    # disrespected, so nothing fires.
    assert _reaction_trigger([prev, curr], 1, Direction.BULLISH,
                             triggers=("disrespect", "open_close")) is None


def test_the_taught_set_fires_on_a_disrespected_open_close_level():
    """Two consecutive bearish candles build a bearish open-close key
    level; a later candle CLOSING above it disrespects it, which is what
    he calls an engulfing (bishop-repeating-system t=195-210)."""
    from ..runner import TRIGGERS_TAUGHT

    candles = [
        H1(0, 1.1050, 1.1055, 1.1040, 1.1042),   # bearish
        H1(1, 1.1042, 1.1044, 1.1030, 1.1032),   # bearish -> level at 1.1042
        H1(2, 1.1032, 1.1060, 1.1030, 1.1058),   # closes ABOVE it: disrespect
        H1(3, 1.1058, 1.1059, 1.1035, 1.1050),   # comes BACK to it: the entry
    ]
    assert _reaction_trigger(candles, 3, Direction.BULLISH,
                             triggers=("open_close",)) == "open_close"

    # The disrespect candle itself is not the entry -- price has not come
    # back yet. Four steps, not three; this is the step it is easiest to
    # drop, and dropping it would enter at the top of the move instead of
    # on the return to the level.
    assert _reaction_trigger(candles, 2, Direction.BULLISH,
                             triggers=("open_close",)) is None


def test_an_unknown_trigger_name_raises_rather_than_silently_doing_nothing():
    """A typo in a CLI flag must not quietly produce a backtest with one
    fewer confirmation pattern than asked for."""
    prev = H1(0, 1.1020, 1.1025, 1.0995, 1.1000)
    curr = H1(1, 1.0998, 1.1040, 1.0996, 1.1030)
    with pytest.raises(ValueError, match="unknown confirmation trigger"):
        _reaction_trigger([prev, curr], 1, Direction.BULLISH, triggers=("nonsense",))



def _leg(pullback_low, break_close):
    """A bullish reaction leg with a real swing low and a real swing
    high, so the structural sweep test has both sides to work with.

    idx 1 is the swing LOW, idx 3 the swing HIGH, idx 4 the pullback
    whose depth decides breakout vs sweep+break, idx 5 the break."""
    return [
        H1(0, 1.1025, 1.1030, 1.1020, 1.1028),
        H1(1, 1.1012, 1.1015, 1.1000, 1.1010),   # swing LOW 1.1000
        H1(2, 1.1012, 1.1025, 1.1010, 1.1022),
        H1(3, 1.1025, 1.1040, 1.1020, 1.1038),   # swing HIGH 1.1040
        H1(4, 1.1030, 1.1030, pullback_low, 1.1025),
        H1(5, 1.1035, 1.1060, 1.1035, break_close),
    ]


def test_breakout_fires_on_a_close_beyond_the_minor_swing_the_reaction_left():
    """SLK_SPEC 5.4. Price makes a low, lifts leaving a minor swing high,
    then closes back above that high."""
    from ..entries import breakout_entry

    candles = _leg(pullback_low=1.1015, break_close=1.1055)
    assert breakout_entry(candles, 5, Direction.BULLISH) is True


def test_breakout_does_not_fire_without_a_close_beyond_it():
    """A wick through is explicitly not a break -- body_closes_beyond is
    the rule the rest of the engine already uses. The break candle's
    HIGH reaches 1.1060, well past the 1.1040 swing; only its close
    decides."""
    from ..entries import breakout_entry

    candles = _leg(pullback_low=1.1015, break_close=1.1038)
    assert breakout_entry(candles, 5, Direction.BULLISH) is False


def test_the_two_triggers_are_mutually_exclusive():
    """5.4 and 5.5 differ by exactly one leg -- whether price took out
    the earlier low before breaking. He draws them as two separate
    illustrations, so one setup must not be both. Made exclusive by
    construction rather than by check order, because _reaction_trigger
    returns on the first match and the order would otherwise decide
    which label a trade gets."""
    from ..entries import breakout_entry, sweep_break_entry

    # Pullback holds above the swing low at 1.1000.
    plain = _leg(pullback_low=1.1015, break_close=1.1055)
    assert breakout_entry(plain, 5, Direction.BULLISH) is True
    assert sweep_break_entry(plain, 5, Direction.BULLISH) is False

    # Same leg, but the pullback digs BELOW that swing low first.
    swept = _leg(pullback_low=1.0990, break_close=1.1055)
    assert sweep_break_entry(swept, 5, Direction.BULLISH) is True
    assert breakout_entry(swept, 5, Direction.BULLISH) is False


def _noise_leg():
    """A reaction whose real high is 1.1080, followed by a small bump at
    idx 5 that is a 1-bar fractal high at 1.1035, and a close above THAT
    bump at idx 7.

    This is the shape the 2026-09-23 post-mortem turned up: 6,243 trades
    of which breakout and sweep+break were 2% each, while `disrespect`
    took 62% -- and the two Bishop rates highest were the only two with
    a decent win rate (34.0% and 39.7% against 19.0%)."""
    return [
        H1(0, 1.1025, 1.1030, 1.1020, 1.1028),
        H1(1, 1.1012, 1.1015, 1.1000, 1.1010),   # reaction LOW, at the level
        H1(2, 1.1015, 1.1050, 1.1010, 1.1048),
        H1(3, 1.1050, 1.1080, 1.1045, 1.1075),   # the reaction's HIGH
        H1(4, 1.1028, 1.1030, 1.1020, 1.1026),
        H1(5, 1.1026, 1.1035, 1.1025, 1.1032),   # a bump, not the reaction high
        H1(6, 1.1030, 1.1032, 1.1022, 1.1029),
        H1(7, 1.1030, 1.1050, 1.1028, 1.1040),   # closes above the BUMP only
    ]


def test_anchored_breakout_ignores_a_wiggle_that_is_not_the_reactions_high():
    """The correction of 2026-09-23, and the reason the taught system
    measured as noise.

    Unanchored, the reference is whatever 1-bar fractal is nearest --
    median three candles back on a random walk -- so closing over the
    little bump at 1.1035 counted as a breakout. Bishop's drawing is
    price coming into the KEY LEVEL, lifting, and closing back above the
    high THAT lift left: 1.1080 here, which 1.1040 does not clear.

    `since` is the index where price reached the level, so the whole
    pattern is measured from the reaction rather than from the last
    wiggle."""
    from ..entries import breakout_entry, _recent_swing

    candles = _noise_leg()
    # The old reference really is the bump, not the reaction's high.
    assert _recent_swing(candles, 7, "high") == 5

    assert breakout_entry(candles, 7, Direction.BULLISH) is True      # unanchored
    assert breakout_entry(candles, 7, Direction.BULLISH, since=1) is False


def test_anchored_break_fires_on_the_reactions_own_high():
    """The same leg, with a close that DOES clear 1.1080. Anchoring
    makes the trigger stricter, not dead -- if it never fired we would
    have swapped one wrong answer for another."""
    from ..entries import breakout_entry, sweep_break_entry

    candles = _noise_leg()
    candles[7] = H1(7, 1.1030, 1.1095, 1.1028, 1.1090)
    assert breakout_entry(candles, 7, Direction.BULLISH, since=1) is True
    # Nothing dipped under the 1.1000 reaction low, so it is 5.4 not 5.5.
    assert sweep_break_entry(candles, 7, Direction.BULLISH, since=1) is False


def test_anchored_sweep_break_needs_the_reaction_low_taken():
    """5.5 is 5.4 plus one leg: after the minor high, price runs the
    reaction low's liquidity before breaking out."""
    from ..entries import breakout_entry, sweep_break_entry

    candles = _noise_leg()
    candles[6] = H1(6, 1.1030, 1.1032, 1.0995, 1.1029)   # digs under 1.1000
    candles[7] = H1(7, 1.1030, 1.1095, 1.1028, 1.1090)
    assert sweep_break_entry(candles, 7, Direction.BULLISH, since=1) is True
    assert breakout_entry(candles, 7, Direction.BULLISH, since=1) is False


def test_the_swing_used_must_be_confirmed_by_entry_time():
    """A 1-bar fractal at j is only decidable at j+1, so j may be at most
    idx-1. Using an unconfirmed swing is the look-ahead this project
    already removed once."""
    from ..entries import _recent_swing

    candles = _leg(pullback_low=1.1015, break_close=1.1055)
    j = _recent_swing(candles, 5, "high")
    assert j is not None and j <= 4


def test_there_is_no_lookback_bound_on_the_swing():
    """Operator, 2026-09-22: "remove the 20 candle [rule], there is no
    data to that -- a breakout is a breakout." A swing far back still
    counts; padding the leg with quiet candles must not lose it."""
    from ..entries import breakout_entry

    candles = _leg(pullback_low=1.1015, break_close=1.1045)
    # 40 quiet candles between the swing high and the break, none of
    # which makes a new extreme either way.
    filler = [H1(6 + i, 1.1032, 1.1034, 1.1029, 1.1031) for i in range(40)]
    padded = candles[:5] + filler + [H1(46, 1.1035, 1.1060, 1.1033, 1.1055)]
    assert breakout_entry(padded, len(padded) - 1, Direction.BULLISH) is True


def test_the_bearish_case_mirrors():
    from ..entries import breakout_entry, sweep_break_entry

    swept = [
        H1(0, 1.1005, 1.1010, 1.1000, 1.1002),
        H1(1, 1.1015, 1.1030, 1.1012, 1.1028),   # swing HIGH 1.1030
        H1(2, 1.1020, 1.1025, 1.1010, 1.1015),
        H1(3, 1.1012, 1.1015, 1.1000, 1.1005),   # swing LOW 1.1000
        H1(4, 1.1005, 1.1035, 1.1002, 1.1010),   # 1.1035 > 1.1030: high taken
        H1(5, 1.1005, 1.1008, 1.0980, 1.0990),   # closes 1.0990 < 1.1000
    ]
    assert sweep_break_entry(swept, 5, Direction.BEARISH) is True
    assert breakout_entry(swept, 5, Direction.BEARISH) is False


def test_every_taught_trigger_has_its_own_stop_rule():
    """The stop block used to end in `else:  # candidate.trigger ==
    "fourth_man"`, which caught everything that was not "engulfing". So
    open_close, breakout and sweep_break were all silently labelled
    fourth_man and given a stop derived from a sweep extreme that, for a
    breakout, does not exist.

    Nothing would have failed. The trades would have appeared in the log
    as fourth_man and measured a stop rule nobody chose -- which is the
    exact shape of the 2026-09-02 plug-and-play A/B that measured "take
    only plug-and-play trades" and was read as a verdict on a stop."""
    import inspect
    from ..runner import TRIGGERS_SHIPPED, TRIGGERS_TAUGHT, run_backtest

    src = inspect.getsource(run_backtest)
    for name in set(TRIGGERS_SHIPPED) | set(TRIGGERS_TAUGHT):
        assert f'candidate.trigger == "{name}"' in src or f'trigger_type = "{name}"' in src \
            or f'"{name}"' in src, f"{name} has no branch in the stop block"

    # And an unknown one must raise rather than fall through.
    assert "no stop rule for trigger" in src


def test_the_touch_gate_would_silently_switch_the_new_triggers_off():
    """Regression for a bug that produced no error and no failing test.

    `breakout` closes beyond the MINOR SWING HIGH, which sits above the
    key level -- so the break candle does not span the level. Under the
    per-candle touch gate the pattern fires and the gate discards it, and
    the A/B would have read as "the taught triggers find fewer setups"
    when two of the four were switched off by a condition their geometry
    cannot satisfy."""
    from ..entries import breakout_entry
    from ..runner import resolve_reaction_gate, AWAY_FROM_LEVEL_TRIGGERS
    from ..runner import TRIGGERS_SHIPPED, TRIGGERS_TAUGHT

    leg = _leg(pullback_low=1.1015, break_close=1.1055)
    assert breakout_entry(leg, 5, Direction.BULLISH) is True

    # The key level is down at the reaction low; the break candle is not
    # anywhere near it.
    level_price = 1.1000
    prev, curr = leg[4], leg[5]
    touches_now = ((prev.low <= level_price <= prev.high)
                   or (curr.low <= level_price <= curr.high))
    assert touches_now is False, "the break candle must not span the level"

    # Which is why the gate is derived from the trigger set, not defaulted.
    assert resolve_reaction_gate(TRIGGERS_SHIPPED) == "candle"
    assert resolve_reaction_gate(TRIGGERS_TAUGHT) == "window"
    assert AWAY_FROM_LEVEL_TRIGGERS == {"breakout", "sweep_break"}


def test_the_shipped_set_keeps_the_per_candle_gate():
    """The shipped triggers are at-the-level two-candle patterns, so the
    looser gate would change their numbers. Every recorded backtest was
    produced under "candle" and must stay comparable."""
    from ..runner import resolve_reaction_gate

    assert resolve_reaction_gate(("engulfing", "fourth_man")) == "candle"
    assert resolve_reaction_gate(("disrespect", "fourth_man")) == "candle"
    # One away-from-level trigger is enough to need the window.
    assert resolve_reaction_gate(("engulfing", "breakout")) == "window"


def _flip_leg(return_low, opposite_break=False):
    """A bearish open-close level that gets disrespected upward, then
    revisited. `return_low` controls whether the return merely reaches
    the level or pokes through it."""
    c = [
        H1(0, 1.1050, 1.1055, 1.1040, 1.1042),   # bearish
        H1(1, 1.1042, 1.1044, 1.1030, 1.1032),   # bearish -> level at 1.1042
        H1(2, 1.1032, 1.1060, 1.1030, 1.1058),   # closes ABOVE it: disrespect
    ]
    if opposite_break:
        # Swing low at idx 4 (1.1044, with higher lows either side), then
        # a close beneath it at idx 6: a bearish breakout after the flip,
        # which kills the setup however nicely price then returns.
        c += [
            H1(3, 1.1058, 1.1059, 1.1048, 1.1052),
            H1(4, 1.1052, 1.1052, 1.1044, 1.1046),   # swing low 1.1044
            H1(5, 1.1046, 1.1050, 1.1046, 1.1049),
            H1(6, 1.1049, 1.1050, 1.1035, 1.1038),   # closes below 1.1044
            H1(7, 1.1041, 1.1041, return_low, 1.1039),
        ]
    else:
        c += [
            H1(3, 1.1058, 1.1059, 1.1050, 1.1052),
            # High deliberately BELOW the 1.1042 level when return_low is
            # low, so the candle does not span it -- that is the case the
            # narrow predecessor throws away.
            H1(4, 1.1041, 1.1041, return_low, 1.1039),
        ]
    return c


def test_the_disrespect_entry_takes_a_return_that_pokes_through_the_level():
    """Operator, 2026-09-22: price "can still come to the flip level too
    or even below". The predecessor required the entry candle to SPAN
    the level, which throws away every return that overshoots -- a
    common and perfectly valid case."""
    from ..entries import disrespect_entry, open_close_disrespect_entry

    through = _flip_leg(return_low=1.1035)   # well below the 1.1042 level
    assert disrespect_entry(through, 4, Direction.BULLISH) is not None
    # The narrow version cannot see it: the candle does not span 1.1042.
    assert open_close_disrespect_entry(through, 4, Direction.BULLISH) is None

    # And a return that merely reaches the level still works.
    touching = _flip_leg(return_low=1.1041)
    assert disrespect_entry(touching, 4, Direction.BULLISH) is not None


def test_a_breakout_back_the_other_way_kills_the_flipped_level():
    """"but it must not create a breakout back to the opposite
    direction". A close beneath a swing low formed after the disrespect
    invalidates the setup, however nicely price then returns."""
    from ..entries import disrespect_entry

    killed = _flip_leg(return_low=1.1035, opposite_break=True)
    assert disrespect_entry(killed, 7, Direction.BULLISH) is None


def test_the_disrespect_entry_is_not_limited_to_open_close_shapes():
    """bias-1 t=195-300 applies the flip to A, V and open-close alike.
    An A-shape closed above becomes a level to BUY from."""
    from ..entries import disrespect_entry

    # A-shape peak at idx 2 (close 1.1060 is the local max, n=2 either
    # side), disrespected upward at idx 6, returned to at idx 7.
    c = [
        H1(0, 1.1000, 1.1012, 1.0998, 1.1010),
        H1(1, 1.1010, 1.1040, 1.1008, 1.1035),
        H1(2, 1.1035, 1.1065, 1.1030, 1.1060),   # A-shape pivot, close 1.1060
        H1(3, 1.1060, 1.1062, 1.1030, 1.1035),
        H1(4, 1.1035, 1.1038, 1.1010, 1.1015),
        H1(5, 1.1015, 1.1020, 1.1008, 1.1012),
        H1(6, 1.1012, 1.1080, 1.1010, 1.1075),   # closes ABOVE 1.1060
        H1(7, 1.1075, 1.1078, 1.1055, 1.1070),   # returns to it
    ]
    level = disrespect_entry(c, 7, Direction.BULLISH)
    assert level is not None
    assert level.shape == "A", f"expected the flipped A-shape, got {level.shape}"


def test_an_unconfirmed_av_pivot_is_not_eligible():
    """An A/V pivot at i is only confirmed n bars later. Using one before
    that is the look-ahead removed on 2026-09-18."""
    import inspect
    from ..entries import disrespect_entry

    assert "i + n < idx" in inspect.getsource(disrespect_entry)


def test_the_new_gates_are_all_off_by_default():
    """Each changes which trades exist. Every recorded backtest was
    produced with them off and must stay comparable."""
    import inspect
    from ..runner import run_backtest

    params = inspect.signature(run_backtest).parameters
    for name in ("require_qmr", "require_imbalance_overlap", "bias_caveat"):
        assert params[name].default is False, name


def test_qmr_and_imbalance_overlap_are_separate_gates():
    """They were conflated once. Operator, 2026-09-22: "a QMR is a QMR,
    nothing much about it. It must NOT overlap an imbalance. Any kl can
    overlap an imbalance." QMR restricts the LEVEL POOL to Quasimodo
    left shoulders; imbalance overlap is a property any level may have
    and gates the trade."""
    import inspect
    from ..runner import run_backtest

    src = inspect.getsource(run_backtest)
    assert "detect_quasimodo_levels(h4, n) if require_qmr" in src
    assert "if require_imbalance_overlap and not imbalance_overlap" in src
    # The QMR flag must not touch the imbalance test.
    assert "require_qmr and not imbalance_overlap" not in src


def test_a_rejection_is_a_wick_through_with_a_close_back():
    """The engine had no rejection detector at all -- detect_confirmations
    only ever emits breakouts and sweep+breaks, so a timeframe that
    merely rejected was invisible to alignment. A bearish rejection is
    price wicking ABOVE a level and closing back below it."""
    from ..key_levels import KeyLevel
    from ..runner import rejection_times

    level = KeyLevel(H1_BASE, 1.1050, "A", Direction.BEARISH,
                     confirmed_at=H1_BASE)
    rejected = H1(1, 1.1040, 1.1065, 1.1038, 1.1042)   # wicks over, closes under
    broke_through = H1(2, 1.1040, 1.1070, 1.1038, 1.1068)  # closes beyond
    untouched = H1(3, 1.1010, 1.1020, 1.1005, 1.1015)

    times = rejection_times([rejected, broke_through, untouched], [level],
                            Direction.BEARISH)
    assert rejected.time in times
    assert broke_through.time not in times, "a close beyond the level is a break, not a rejection"
    assert untouched.time not in times


def test_the_caveat_requires_the_weekly_rejection_too():
    """Without it this collapses into "trade whenever H4 agrees", which
    is a far weaker system wearing the same name. The daily confirmation
    is the strictest gate in the engine and this is the only thing
    standing in for it."""
    import inspect
    from ..runner import run_backtest

    src = inspect.getsource(run_backtest)
    assert "weekly_rejections[candidate.direction]" in src
    # Both conditions, joined by and -- not either-or.
    assert src.count("_rejected_recently(") >= 2


def test_rejected_recently_respects_the_window():
    from ..runner import _rejected_recently

    t0 = pd.Timestamp("2026-01-01", tz="UTC")
    times = [t0]
    assert _rejected_recently(times, t0 + pd.Timedelta(days=10), pd.Timedelta(days=45)) is True
    assert _rejected_recently(times, t0 + pd.Timedelta(days=60), pd.Timedelta(days=45)) is False
    # Nothing before the query time.
    assert _rejected_recently(times, t0 - pd.Timedelta(days=1), pd.Timedelta(days=45)) is False
    assert _rejected_recently([], t0, pd.Timedelta(days=45)) is False


def test_a_stop_inside_the_spread_is_not_an_invalidation_zone():
    """AUDJPY 2025-09-25 18:00, from the real run: entry 97.930, stop
    97.928. Two tenths of a pip on a cross whose spread is ~1.5, so the
    trade is stopped by the spread before price moves.

    `_natural_stop_too_wide` policed one end for a year while nothing
    watched the other, and the other end is where the damage was."""
    from ..runner import stop_too_tight

    assert stop_too_tight(97.930, 97.928, 0.01, min_pips=2.0) is True
    # 7.6 pips -- the one winner among those six -- must survive.
    assert stop_too_tight(97.952, 97.876, 0.01, min_pips=2.0) is False
    # Direction must not matter.
    assert stop_too_tight(97.928, 97.930, 0.01, min_pips=2.0) is True


def test_the_tight_stop_guard_is_off_by_default():
    """0.0 is every trade this engine has ever produced. A new gate must
    not silently reprice the entire backtest history."""
    from ..runner import stop_too_tight

    assert stop_too_tight(97.930, 97.928, 0.01, min_pips=0.0) is False


def test_a_reward_floor_alone_prefers_the_broken_trades():
    """Why min_reward_r had to be paired with min_stop_pips.

    R is a RATIO. The 0.2-pip stop scores 125R against the same target
    the 7.6-pip stop scores 3.0R against -- so raising the floor to 3.0
    keeps the unplaceable trade and discards the real one. That is the
    mechanism behind both instruments measuring worse on 2026-09-23."""
    target = 98.181
    real_r = abs(target - 97.952) / abs(97.952 - 97.876)
    broken_r = abs(target - 97.930) / abs(97.930 - 97.928)

    assert real_r == pytest.approx(3.01, abs=0.01)
    assert broken_r > 100
    # The floor alone keeps the wrong one.
    assert broken_r > real_r


def test_the_setup_that_produced_a_trade_is_recorded_on_it(synthetic_cache):
    """The liquidity pool, the sweep and the H4 breakout must reach the
    trade log, not just the entry.

    Without these the rendered chart cannot show the setup at all, which
    is what made it unreadable: "I couldn't understand where single
    candle liquidity was." A blank column and a wrong column look
    identical downstream, so this asserts they arrive POPULATED rather
    than merely present."""
    records = run_backtest(SYMBOL, "conservative", source=SOURCE, pip_size=0.0001)
    assert records
    t = records[0]

    assert t.liquidity_price, "the pool price price came back for"
    assert t.liquidity_time is not None, "when that pool formed"
    assert t.sweep_time is not None, "when price took it"
    assert t.h4_breakout_time is not None, "the breakout that opened the window"

    # And in the order the strategy builds them.
    assert t.h4_breakout_time <= t.sweep_time
    assert t.liquidity_time <= t.sweep_time
    assert t.sweep_time <= t.entry_time


def test_first_presentation_only_takes_one_trade_per_breakout(synthetic_cache):
    """Operator, 2026-09-23: "it's about using it the first time it
    presented itself."

    A breakout leaves liquidity behind once and price comes back for it
    once. Making every 4H candle in the leg its own independent setup
    let one breakout produce a trade off its twentieth pool, which is no
    longer that retracement. This is a SELECTION rule, not a window --
    nothing is rejected for being late."""
    from ..runner import _find_liquidity_setups

    loose = run_backtest(SYMBOL, "conservative", source=SOURCE, pip_size=0.0001)
    strict = run_backtest(SYMBOL, "conservative", source=SOURCE, pip_size=0.0001,
                          first_presentation_only=True)

    assert len(strict) <= len(loose), "taking only the first cannot add trades"

    # At most one trade per (breakout, direction).
    seen = set()
    for t in strict:
        key = (t.h4_breakout_time, t.direction)
        assert key not in seen, f"two trades from one breakout: {key}"
        seen.add(key)


def test_first_presentation_only_is_off_by_default(synthetic_cache):
    """It changes which trades exist, so every historical backtest must
    be reproducible without it."""
    a = run_backtest(SYMBOL, "conservative", source=SOURCE, pip_size=0.0001)
    b = run_backtest(SYMBOL, "conservative", source=SOURCE, pip_size=0.0001,
                     first_presentation_only=False)
    assert [t.entry_time for t in a] == [t.entry_time for t in b]


def test_trigger_priority_ranks_confirmations_instead_of_racing_them(monkeypatch):
    """Bishop rates breakout and sweep+break above everything else, but
    they cannot form as fast as disrespect: disrespect can fire on the
    candle right after the touch, while a breakout needs a low, a lift
    and a close beyond it -- two bars at the very least.

    So whichever fires first wins, always, and the ordering in
    `confirmation_triggers` only ever broke ties inside one candle. On
    eight instruments that produced disrespect 74% of trades against
    breakout 2% -- the opposite of how the course rates them.

    The triggers are scripted here rather than coaxed out of synthetic
    price, because what is under test is the SELECTION, not the
    detectors: a fast low-rated confirmation and a slow high-rated one
    in the same reaction."""
    from .. import runner as R

    level = KeyLevel(time=H1_BASE, price=1.1000, shape="V",
                     default_bias=Direction.BULLISH, confirmed_at=H1_BASE)
    candles = [H1(i, 1.1000, 1.1010, 1.0990, 1.1005) for i in range(30)]
    setup = R.LiquiditySetup(
        direction=Direction.BULLISH, breakout_time=H1_BASE,
        liquidity_price=1.0990, liquidity_time=H1_BASE,
        liquidity_known_at=H1_BASE, sweep_from=H1_BASE,
        reaction_level_candidates=[level], setup_id=0, h4_validated=True)

    # Fast but lowest-rated at 5; slow but highest-rated at 9.
    monkeypatch.setattr(R, "_reaction_trigger",
                        lambda c, idx, d, t, since=None:
                        {5: "disrespect", 9: "breakout"}.get(idx))

    raced = R._find_entry_candidates(candles, [setup], max_per_setup=1,
                                     triggers=TRIGGERS_TAUGHT)
    assert [c.trigger for c in raced] == ["disrespect"], "fastest wins"

    ranked = R._find_entry_candidates(candles, [setup], max_per_setup=1,
                                      triggers=TRIGGERS_TAUGHT,
                                      trigger_priority=True)
    assert [c.trigger for c in ranked] == ["breakout"], "best-rated wins"
    assert ranked[0].index == 9


def test_trigger_priority_is_off_by_default(synthetic_cache):
    a = run_backtest(SYMBOL, "conservative", source=SOURCE, pip_size=0.0001)
    b = run_backtest(SYMBOL, "conservative", source=SOURCE, pip_size=0.0001,
                     trigger_priority=False)
    assert [t.entry_time for t in a] == [t.entry_time for t in b]


def test_the_weekly_is_set_aside_only_on_a_real_disagreement():
    """SLK_SPEC 1, routine t=390-435. The weekly is dropped when the
    daily contradicts it -- not when it simply has nothing to say.

    Without the rule the weekly always wins (it is first in
    TIMEFRAME_PRIORITY), so every split killed the trade outright and a
    class of setups he takes was unreachable. With it applied too
    eagerly, every early-history entry would silently become a
    reduced-target trade."""
    from ..runner import weekly_set_aside

    B, S = Direction.BULLISH, Direction.BEARISH
    assert weekly_set_aside(B, S, True) is True
    assert weekly_set_aside(S, B, True) is True
    # Agreement is not a split.
    assert weekly_set_aside(B, B, True) is False
    # Silence is not disagreement -- resolve_effective_bias already
    # falls through to the daily when the weekly has no bias.
    assert weekly_set_aside(None, B, True) is False
    assert weekly_set_aside(B, None, True) is False
    # Off by default.
    assert weekly_set_aside(B, S, False) is False


def test_the_reduced_target_is_the_dailys_own_liquidity():
    """What makes the daily-only path safe: "I probably just target a
    good liquidity" (routine t=390-435).

    The weekly was set aside for the BIAS, so it is set aside for the
    TARGET too -- and a daily extreme is nearer than a weekly one by
    construction, which IS the reduction. No fraction of R had to be
    invented for it."""
    daily = [D(i, 1.100 + i * 0.001, 1.102 + i * 0.001,
               1.098 + i * 0.001, 1.101 + i * 0.001) for i in range(6)]
    # One weekly candle whose high sits far above every daily high.
    weekly = [Candle(D(0, 0, 0, 0, 0).time, 1.100, 1.200, 1.090, 1.150, 1000)]
    at = D(9, 0, 0, 0, 0).time

    both = _nearest_erl(Direction.BULLISH, 1.1005, at, daily, weekly)
    daily_only = _nearest_erl(Direction.BULLISH, 1.1005, at, daily)
    assert both is not None and daily_only is not None
    assert daily_only <= both, "dropping the weekly cannot widen the target"


def _synthetic_walk(seed, bars=1500, n_setups=60):
    """A random walk plus overlapping setups, for equivalence checks."""
    import random
    from ..key_levels import KeyLevel
    random.seed(seed)
    px, h1 = 1.1000, []
    for i in range(bars):
        o = px
        c = px + random.gauss(0, 0.0008)
        h1.append(Candle(time=H1_BASE + pd.Timedelta(hours=i), open=o,
                         high=max(o, c) + abs(random.gauss(0, .0003)),
                         low=min(o, c) - abs(random.gauss(0, .0003)),
                         close=c, volume=1000))
        px = c
    setups = []
    for n in range(n_setups):
        i = 20 + n * 18
        lvl = KeyLevel(time=h1[i].time, price=h1[i].close, shape="V",
                       default_bias=Direction.BULLISH, confirmed_at=h1[i].time)
        setups.append(LiquiditySetup(
            direction=Direction.BULLISH, breakout_time=h1[i].time,
            liquidity_price=h1[i].low, liquidity_time=h1[i].time,
            liquidity_known_at=h1[i].time, sweep_from=h1[i].time,
            reaction_level_candidates=[lvl], setup_id=n, h4_validated=True))
    return h1, setups


def _rank_by_full_scan(h1, setups):
    """Deliberately naive: scan the whole window, pick by (rank, index).

    The reference the pruned implementation must agree with. Written
    without any of its shortcuts on purpose."""
    import bisect
    from ..runner import REACTION_LOOKAHEAD
    rank = {n: i for i, n in enumerate(TRIGGERS_TAUGHT)}
    times = [c.time for c in h1]
    seen, out = set(), []
    for s in setups:
        start = bisect.bisect_left(times, s.sweep_from)
        lvl = s.reaction_level_candidates[0]
        hits, touched, t_idx = [], False, None
        for idx in range(start + 1, min(start + 1 + REACTION_LOOKAHEAD, len(h1))):
            prev, curr = h1[idx - 1], h1[idx]
            now = ((prev.low <= lvl.price <= prev.high)
                   or (curr.low <= lvl.price <= curr.high))
            if now and t_idx is None:
                t_idx = idx - 1 if prev.low <= lvl.price <= prev.high else idx
            touched = touched or now
            if not touched or idx in seen:
                continue
            t = _reaction_trigger(h1, idx, s.direction, TRIGGERS_TAUGHT, since=t_idx)
            if t:
                hits.append((rank[t], idx, t))
        if hits:
            hits.sort()
            out.append((s.setup_id, hits[0][1], hits[0][2]))
            seen.add(hits[0][1])
    return sorted(out, key=lambda r: r[1])


@pytest.mark.parametrize("seed", [1, 2, 3, 4])
def test_rank_pruning_changes_cost_not_answers(seed):
    """Ranking without pruning scanned the entire reaction window and
    cost 20x the trigger calls of racing -- 11,952 against 640 on a
    300-setup benchmark, 1.62s against 0.08s. That is the live cycle
    budget, not a tidiness point.

    Pruning is exact: once a rank-2 confirmation has fired only ranks 0
    and 1 can improve on it, and among equal ranks the earliest already
    won. This asserts it against a naive full scan rather than trusting
    that argument."""
    h1, setups = _synthetic_walk(seed)
    got = [(c.setup_id, c.index, c.trigger) for c in
           _find_entry_candidates(h1, setups, max_per_setup=1,
                                  triggers=TRIGGERS_TAUGHT, trigger_priority=True)]
    assert got == _rank_by_full_scan(h1, setups)


def test_ranking_actually_shifts_the_mix_towards_the_rated_triggers():
    """The point of the whole exercise. On the same synthetic data,
    racing gives disrespect most of the entries; ranking gives them to
    breakout and sweep+break -- the two Bishop rates above all others."""
    from collections import Counter

    h1, setups = _synthetic_walk(11, bars=3000, n_setups=150)
    raced = Counter(c.trigger for c in _find_entry_candidates(
        h1, setups, max_per_setup=1, triggers=TRIGGERS_TAUGHT))
    ranked = Counter(c.trigger for c in _find_entry_candidates(
        h1, setups, max_per_setup=1, triggers=TRIGGERS_TAUGHT, trigger_priority=True))

    rated = lambda c: c["breakout"] + c["sweep_break"]
    assert rated(ranked) > rated(raced) * 2, (raced, ranked)
    assert ranked["disrespect"] < raced["disrespect"]
