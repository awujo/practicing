import pandas as pd
import pytest

from ...data_pipeline import cache
from ..candles import Candle
from ..structure import Direction
from ..bias import detect_confirmations
from ..key_levels import detect_key_levels
from ..runner import (
    run_backtest, _stop_on_correct_side, _find_liquidity_setups, _find_entry_candidates,
)

SOURCE = "test"
SYMBOL = "RUNNERPAIR"


def D(i, o, h, l, c):
    return Candle(pd.Timestamp("2024-01-01") + pd.Timedelta(days=i), o, h, l, c, 1000)


def H4(i, o, h, l, c):
    return Candle(pd.Timestamp("2024-01-01") + pd.Timedelta(hours=4 * i), o, h, l, c, 1000)


def W(i, o, h, l, c):
    return Candle(pd.Timestamp("2023-01-01") + pd.Timedelta(weeks=i), o, h, l, c, 1000)


H1_BASE = pd.Timestamp("2024-01-01") + pd.Timedelta(days=20)  # well past ORIGIN_WINDOW (3 days) and
# past the daily series' own last internal bias flip (day 9), so this scenario exercises the
# "continuation" trade_kind branch rather than "origin" -- see the daily candles below.


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
        H1(5, 1.1040, 1.1060, 1.1035, 1.1055),  # high clears the 1:3 target
        H1(6, 1.1055, 1.1075, 1.1050, 1.1070),
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
    assert trade.trade_kind == "continuation"  # H1 data starts well past ORIGIN_WINDOW
    assert trade.stop_kind == "continuation"
    assert trade.key_level_price == pytest.approx(1.1012)  # the H4 "V" reaction level, not an ad-hoc H1 level
    assert trade.key_level_shape == "V"
    assert trade.entry_price == pytest.approx(1.1030)  # conservative -> engulf candle's close
    assert trade.status == "closed_win"
    assert trade.exit_reason == "target_hit"
    assert trade.r_multiple == pytest.approx(3.0)
    assert trade.mfe_r is not None and trade.mfe_r >= trade.r_multiple  # ran at least as far as the close


def test_run_backtest_aggressive_style_enters_at_key_level_price(synthetic_cache):
    records = run_backtest(SYMBOL, "aggressive", source=SOURCE, pip_size=0.0001)

    assert len(records) == 1
    # Aggressive enters at the key level itself (the H4 reaction level), not the confirmation close.
    assert records[0].entry_price == pytest.approx(1.1012)


def test_run_backtest_uses_imbalance_stop_for_plug_and_play_continuation_trades(synthetic_cache):
    # Append 3 H1 candles -- well after the entry trigger at index 3, so the
    # sweep/reaction/engulf sequence from `synthetic_cache` is untouched --
    # forming a bullish FVG that brackets the H4 reaction level (1.1012):
    # A.high=1.1008, C.low=1.1020. detect_imbalances() scans the whole H1
    # series regardless of position relative to entry, so this becomes the
    # key level's overlapping imbalance and should override the generic
    # continuation stop-loss rule with the "plug and play" imbalance one.
    extra = [
        H1(7, 1.1002, 1.1008, 1.0998, 1.1000),
        H1(8, 1.1000, 1.1025, 1.0995, 1.1022),
        H1(9, 1.1022, 1.1028, 1.1020, 1.1024),
    ]
    _write("H1", extra)

    records = run_backtest(SYMBOL, "conservative", source=SOURCE, pip_size=0.0001)
    assert len(records) == 1
    trade = records[0]

    assert trade.trade_kind == "continuation"
    assert trade.imbalance_overlap is True
    assert trade.stop_kind == "imbalance"
    # Far edge of the overlapping imbalance (1.1008, the older candle's
    # high) minus a 1-pip pad -- NOT the flat 10-pip continuation default
    # (which would place the stop at 1.1020 instead).
    assert trade.stop_loss == pytest.approx(1.1007)


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
    assert setup.reaction_level.price == pytest.approx(1.1012)
    assert setup.reaction_level.shape == "V"


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
