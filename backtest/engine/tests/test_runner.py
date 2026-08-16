import pandas as pd
import pytest

from ...data_pipeline import cache
from ..candles import Candle
from ..structure import Direction
from ..bias import detect_confirmations, Confirmation, ConfirmationKind
from ..key_levels import detect_key_levels
from ..runner import (
    run_backtest, _stop_on_correct_side, _find_liquidity_setups, _find_entry_candidates,
    _aligned_timeframes, _reaction_trigger, _natural_stop_too_wide, _nearest_erl, _unswept_period_extremes,
)

SOURCE = "test"
SYMBOL = "RUNNERPAIR"


def D(i, o, h, l, c):
    return Candle(pd.Timestamp("2024-01-01") + pd.Timedelta(days=i), o, h, l, c, 1000)


def H4(i, o, h, l, c):
    return Candle(pd.Timestamp("2024-01-01") + pd.Timedelta(hours=4 * i), o, h, l, c, 1000)


def W(i, o, h, l, c):
    return Candle(pd.Timestamp("2023-01-01") + pd.Timedelta(weeks=i), o, h, l, c, 1000)


H1_BASE = pd.Timestamp("2024-01-01") + pd.Timedelta(days=20)  # well past the daily series' own
# last internal bias flip (day 9) -- comfortably within ALIGNMENT_LOOKBACK, but note that
# trade_kind is now sequence-based (Task 4), not time-window-based: on its own, an entry
# built from this base is "origin" (nothing precedes it in the fixture); see
# _add_earlier_origin_trade() for tests that specifically need a "continuation" trade.


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
        # more extreme of H1(2)'s/H1(3)'s own lows, 1.1005), not to
        # trade_kind -- a tighter, closer-to-entry stop than the old
        # liquidity-point-anchored "origin" rule, which in turn needs one
        # more candle than before to actually clear the closer-in target.
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
    # This is the ONLY trade in the whole series, so by Task 4's literal
    # sequence rule ("first instance vs. repeated instance" -- nothing
    # precedes it) it's "origin" -- but trade_kind no longer determines
    # the stop-loss rule (Task 5): it's keyed to the trigger instead
    # (here, engulfing -- the more extreme of H1(2)'s low, 1.1008, and
    # H1(3)'s own low, 1.1005 -- 1.1005 wins, stop = 1.1005 - 1 pip).
    assert trade.trade_kind == "origin"
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


def test_run_backtest_date_filtering_does_not_corrupt_origin_continuation_tracking(synthetic_cache):
    # The earlier, unrelated cascade (day 10) still claims "origin" for
    # its leg even when the reporting window excludes it -- the later
    # (day 20) trade must still come out "continuation", not get
    # incorrectly promoted to "origin" just because its true predecessor
    # was filtered out of the OUTPUT. Narrowing the reported window must
    # never narrow what claimed_origins bookkeeping actually sees.
    _add_earlier_origin_trade()

    full = run_backtest(SYMBOL, "conservative", source=SOURCE, pip_size=0.0001)
    assert [r.trade_kind for r in full] == ["origin", "continuation"]

    filtered = run_backtest(SYMBOL, "conservative", source=SOURCE, pip_size=0.0001,
                             start_date=H1_BASE.normalize())
    assert len(filtered) == 1
    assert filtered[0].trade_kind == "continuation"  # NOT "origin"


def test_run_backtest_respects_a_custom_rr(synthetic_cache):
    default_run = run_backtest(SYMBOL, "conservative", source=SOURCE, pip_size=0.0001)
    rr4_run = run_backtest(SYMBOL, "conservative", source=SOURCE, pip_size=0.0001, rr=4.0)

    assert len(default_run) == len(rr4_run) == 1
    entry, stop = default_run[0].entry_price, default_run[0].stop_loss
    assert default_run[0].raw_target == pytest.approx(entry + 3 * (entry - stop))
    assert rr4_run[0].raw_target == pytest.approx(entry + 4 * (entry - stop))


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


def _add_earlier_origin_trade():
    """trade_kind is now sequence-based (Task 4: literal "first instance
    vs. repeated instance" since the effective bias's own origin event --
    see runner.py's `claimed_origins` bookkeeping), not a fixed time
    window -- so a fixture with only ONE trade in the whole series is
    always "origin" by construction (nothing precedes it). Tests that
    specifically want to exercise "continuation" stop-loss behavior need a
    genuine EARLIER trade in the same (Daily-effective, BULLISH) leg to
    claim "origin" first. This appends a second, independent H4
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
    _add_earlier_origin_trade()

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
    assert records[0].trade_kind == "origin"  # the earlier, unrelated cascade claims it
    trade = records[1]

    assert trade.trade_kind == "continuation"
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
    _add_earlier_origin_trade()

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
    assert records[0].trade_kind == "origin"  # the earlier, unrelated cascade claims it
    trade = records[1]

    assert trade.trade_kind == "continuation"
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
    # deliberate 20-day-later placement, so this trade is classified
    # "origin" (Task 4: it's the first entry since the effective bias's
    # own origin event). Historically (before an early fix) the origin
    # stop was anchored to a Daily-timeframe strong-low snapshot that
    # hadn't been set yet this early (StructureTracker's valid_sweep_break
    # doesn't fire until day 9) -- `_strong_at()` returned None and the
    # trade was silently dropped; this regression-tests that an origin
    # trade this early in the series still gets produced at all. Stop-loss
    # itself is now keyed to the TRIGGER (Task 5), not trade_kind -- see
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

    assert trade.trade_kind == "origin"
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
