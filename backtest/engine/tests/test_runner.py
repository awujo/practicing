import pandas as pd
import pytest

from ...data_pipeline import cache
from ..candles import Candle
from ..structure import Direction
from ..bias import detect_confirmations, Confirmation, ConfirmationKind
from ..key_levels import detect_key_levels
from ..runner import (
    run_backtest, _stop_on_correct_side, _find_liquidity_setups, _find_entry_candidates,
    _aligned_timeframes,
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
        # trade_kind is now "origin" (Task 4: no earlier trade precedes this
        # one in the base fixture), so the stop anchors tightly to the
        # swept liquidity point (1.1015) rather than the old flat 10-pip
        # continuation stop -- a tighter stop means a closer-in 1:3 target,
        # needing one more candle to actually clear it than the old
        # continuation-stop version of this fixture did.
        H1(7, 1.1070, 1.1085, 1.1065, 1.1080),  # high clears the 1:3 target
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
    # precedes it) it's "origin", anchored to the swept liquidity point
    # (1.1015) rather than a fixed continuation pip stop.
    assert trade.trade_kind == "origin"
    assert trade.stop_kind == "origin"
    assert trade.stop_loss == pytest.approx(1.1014)
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
    assert trade.r_multiple == pytest.approx(3.0)
    assert trade.mfe_r is not None and trade.mfe_r >= trade.r_multiple  # ran at least as far as the close


def test_run_backtest_aggressive_style_enters_at_key_level_price(synthetic_cache):
    # This fixture's reaction level (1.1012) sits BEYOND (further in the
    # trade direction than) the swept liquidity point (1.1015) that
    # origin_stop_loss() anchors to -- fine for a conservative entry
    # (1.103, well clear of both), but an aggressive entry AT the key
    # level itself (1.1012) would land the origin stop on the WRONG side
    # of entry, and _stop_on_correct_side() correctly drops the trade
    # rather than open a corrupted one. Not what this test is actually
    # about (entry-STYLE pricing, not trade_kind), so give it an earlier
    # origin trade like the imbalance tests do, making this one
    # "continuation" (tight_no_irl/continuation stop, never origin) so it
    # exercises aggressive pricing cleanly. See Task 5 (stop-loss rebuild)
    # for properly anchoring origin stops past the FARTHEST point reached,
    # not just the liquidity point, which is the real fix for the
    # aggressive+origin combination.
    _add_earlier_origin_trade()

    records = run_backtest(SYMBOL, "aggressive", source=SOURCE, pip_size=0.0001)

    assert len(records) == 2
    assert records[0].trade_kind == "origin"
    # Aggressive enters at the key level itself (the H4 reaction level), not the confirmation close.
    # See test_run_backtest_produces_a_winning_trade_end_to_end for why this is 1.1012, the nearest
    # same-direction candidate to the swept liquidity point, not a scored pick.
    assert records[1].trade_kind == "continuation"
    assert records[1].entry_price == pytest.approx(1.1012)


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
    assert trade.stop_kind == "imbalance"
    # Far edge of the overlapping imbalance (1.1009, A's high) minus a
    # 1-pip pad -- NOT the flat 10-pip continuation default (which would
    # place the stop at 1.1010 - 0.0010 = 1.1000 instead).
    assert trade.stop_loss == pytest.approx(1.1008)


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
    # picked up, and the trade should fall through to the generic
    # continuation stop-loss rule instead.
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
    assert trade.stop_kind == "continuation"


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


def test_run_backtest_anchors_origin_stop_to_the_setup_own_liquidity_point(tmp_path, monkeypatch):
    # Same Bishop cascade as `synthetic_cache`, but with H1 candles placed
    # within ORIGIN_WINDOW (3 days) of the Daily bias flip (bootstrapped at
    # 2024-01-01 for this fixture -- see the daily series below) instead of
    # `synthetic_cache`'s deliberate 20-day-later placement, so this trade
    # is classified "origin". Before the fix, the origin stop was anchored
    # to a Daily-timeframe strong-low snapshot that hadn't been set yet
    # this early (StructureTracker's valid_sweep_break doesn't fire until
    # day 9) -- `_strong_at()` returned None and the trade was silently
    # dropped. Now it's anchored to `EntryCandidate.liquidity_price`, the
    # SAME local H4 liquidity point (1.1015, from the single-candle swing
    # low at H4 idx7) that triggered this exact entry, so the trade is
    # both produced AND stopped tightly -- matching Video 13's "stop just
    # beyond the particular high/low that was actually created" and Video
    # 4's ~9 pip worked example, not a distant Daily structural extreme.
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
        origin_H1(7, 1.1070, 1.1085, 1.1065, 1.1080),  # high clears the 1:3 target
    ]

    _write("D", daily)
    _write("H4", h4)
    _write("H1", h1)

    records = run_backtest(SYMBOL, "conservative", source=SOURCE, pip_size=0.0001)
    assert len(records) == 1
    trade = records[0]

    assert trade.trade_kind == "origin"
    assert trade.stop_kind == "origin"
    # 1.1015 (the swept liquidity point) minus a 1-pip pad -- NOT some
    # multi-hundred-pip Daily structural extreme (e.g. the 1.090 strong low
    # this fixture's daily series would otherwise produce).
    assert trade.stop_loss == pytest.approx(1.1014)
    assert trade.status == "closed_win"
    assert trade.r_multiple == pytest.approx(3.0)


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
