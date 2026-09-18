import os

import pandas as pd
import pytest

from backtest.engine.bias import Confirmation, ConfirmationKind
from backtest.engine.structure import Direction

from ..live_strategy import (
    HUNTING, WAITING, HTFContext, build_htf_context, needs_rebuild, storyline_at,
)

DATA_ROOT = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), "backtest", "data", "dukascopy")


def T(days):
    return pd.Timestamp("2026-01-01", tz="UTC") + pd.Timedelta(days=days)


def conf(t, direction):
    return Confirmation(t, direction, ConfirmationKind.BREAKOUT, 1.0)


def make_ctx(daily_confs=(), h4_confs=(), weekly_confs=(), daily_breakpoints=None,
              weekly_breakpoints=None):
    """A hand-built context, so the gate's decision rules can be tested
    without needing real cached history."""
    from backtest.engine.runner import _direction_lookup
    return HTFContext(
        instrument="TEST",
        weekly_breakpoints=weekly_breakpoints or [],
        daily_breakpoints=daily_breakpoints if daily_breakpoints is not None else [(T(0), Direction.BULLISH)],
        weekly_confirmations=list(weekly_confs),
        daily_confirmations=list(daily_confs),
        h4_confirmations=list(h4_confs),
        h4_lookup=_direction_lookup(list(h4_confs)),
        latest_weekly_time=T(0), latest_daily_time=T(0), latest_h4_time=T(0),
    )


# ---- the decision rules ----

def test_hunting_when_daily_and_h4_both_confirm_the_bias_direction():
    ctx = make_ctx(daily_confs=[conf(T(1), Direction.BULLISH)],
                    h4_confs=[conf(T(2), Direction.BULLISH)])
    s = storyline_at(ctx, T(2.5))
    assert s.stage == HUNTING
    assert s.direction == Direction.BULLISH
    assert "Daily" in s.aligned and "H4" in s.aligned


def test_waiting_when_h4_has_not_come_round_to_the_daily_yet():
    # The exact case a manual trader sits in: Daily is set, 4H hasn't
    # aligned to it. No H1 work is warranted here.
    ctx = make_ctx(daily_confs=[conf(T(1), Direction.BULLISH)],
                    h4_confs=[conf(T(2), Direction.BEARISH)])
    s = storyline_at(ctx, T(2.5))
    assert s.stage == WAITING
    assert s.direction is None
    assert "disagree" in s.reason


def test_waiting_when_there_is_no_recent_daily_confirmation_at_all():
    ctx = make_ctx(daily_confs=[], h4_confs=[conf(T(2), Direction.BULLISH)])
    assert storyline_at(ctx, T(2.5)).stage == WAITING


def test_waiting_when_the_higher_timeframe_bias_opposes_the_aligned_direction():
    # Daily/H4 both confirm bullish, but the effective (Daily cascade)
    # bias is bearish -- the induced-move trap, deliberately not traded.
    ctx = make_ctx(daily_confs=[conf(T(1), Direction.BULLISH)],
                    h4_confs=[conf(T(2), Direction.BULLISH)],
                    daily_breakpoints=[(T(0), Direction.BEARISH)])
    s = storyline_at(ctx, T(2.5))
    assert s.stage == WAITING
    assert "induced-move trap" in s.reason


def test_weekly_is_recorded_when_it_aligns_but_is_not_required():
    aligned_wk = make_ctx(daily_confs=[conf(T(1), Direction.BULLISH)],
                           h4_confs=[conf(T(2), Direction.BULLISH)],
                           weekly_confs=[conf(T(0.5), Direction.BULLISH)])
    assert storyline_at(aligned_wk, T(2.5)).aligned[0] == "Weekly"

    # Weekly silent -- still hunting, just without the booster.
    no_wk = make_ctx(daily_confs=[conf(T(1), Direction.BULLISH)],
                      h4_confs=[conf(T(2), Direction.BULLISH)])
    s = storyline_at(no_wk, T(2.5))
    assert s.stage == HUNTING
    assert "Weekly" not in s.aligned


def test_a_confirmation_older_than_the_alignment_lookback_does_not_count():
    ctx = make_ctx(daily_confs=[conf(T(1), Direction.BULLISH)],
                    h4_confs=[conf(T(2), Direction.BULLISH)])
    # Far enough past both confirmations that neither is "recent" anymore.
    assert storyline_at(ctx, T(400)).stage == WAITING


def test_confirmations_after_the_query_time_are_never_used():
    # The gate must not see the future -- a live check at time t only
    # knows what had confirmed by t.
    ctx = make_ctx(daily_confs=[conf(T(10), Direction.BULLISH)],
                    h4_confs=[conf(T(11), Direction.BULLISH)])
    assert storyline_at(ctx, T(5)).stage == WAITING


# ---- rebuild scheduling ----

def test_needs_rebuild_only_when_a_w_d_or_h4_candle_has_closed():
    ctx = make_ctx()
    assert needs_rebuild(ctx, T(0), T(0), T(0)) is False          # nothing closed
    assert needs_rebuild(ctx, T(0), T(0), T(1)) is True           # new H4
    assert needs_rebuild(ctx, T(0), T(1), T(0)) is True           # new Daily
    assert needs_rebuild(ctx, T(1), T(0), T(0)) is True           # new Weekly
    assert needs_rebuild(None, T(0), T(0), T(0)) is True          # never built


# ---- the safety property, against real cached history ----

def _has_data(instrument):
    return all(os.path.exists(os.path.join(DATA_ROOT, instrument, f"{g}.csv"))
               for g in ("D", "H4", "H1", "W"))


@pytest.mark.parametrize("instrument", ["EURUSD", "GBPJPY", "GBPNZD"])
@pytest.mark.parametrize("style", ["conservative", "aggressive"])
def test_gate_never_suppresses_a_trade_the_real_backtest_produces(instrument, style):
    """THE property this gate lives or dies by: it may only ever be a
    performance filter, never a strategy change. Every trade
    `run_backtest()` actually produces must fall inside a window where
    the gate said HUNTING -- otherwise the live loop would skip the H1
    search at exactly the moment a real signal existed.

    Runs against real multi-year cached history rather than fixtures,
    because the failure mode being guarded against is a subtle
    disagreement with the real alignment rules, which a hand-built
    fixture would be too kind to expose. Skips when the cache isn't
    present (it is gitignored); the data-fetch workflows provide it in
    CI, and it was run manually over 3,328 trades before shipping.

    FIXED 2026-09-18 (review finding 8). Both calls below used to be made
    on DEFAULTS -- `build_htf_context(instrument)` and
    `run_backtest(instrument, style)` -- so this test proved the gate
    agreed with an engine configured `origin_kind="sweep_break"`,
    wick-based sweep breaks, no rollover filter and no `min_reward_r`.
    Production runs none of those. The test passed; the deployed pairing
    was never checked, and finding 2 (the gate computing a different bias
    from the engine) lived behind it.

    Both sides now take the deployed flags from `live_flags.py`. A test
    of a configuration nobody runs is worse than no test: it reports
    safety for a system that is not the one flying."""
    if not _has_data(instrument):
        pytest.skip(f"no cached {instrument} data -- run the fetch-data workflow")

    from backtest.engine.runner import run_backtest
    from backtest.tools.live_flags import LIVE_FIXED_FLAGS, LIVE_LAUNCH_FLAGS

    ctx = build_htf_context(
        instrument,
        origin_kind=LIVE_LAUNCH_FLAGS["origin_kind"],
        close_based_sweep_break=LIVE_LAUNCH_FLAGS["close_based_sweep_break"])
    assert ctx is not None, "real history should always bootstrap a context"

    records = run_backtest(instrument, style, **LIVE_FIXED_FLAGS,
                           origin_kind=LIVE_LAUNCH_FLAGS["origin_kind"],
                           close_based_sweep_break=LIVE_LAUNCH_FLAGS["close_based_sweep_break"],
                           stop_anchor=LIVE_LAUNCH_FLAGS["stop_anchor"])
    suppressed = [
        (r.entry_time, storyline_at(ctx, r.entry_time).reason)
        for r in records
        if storyline_at(ctx, r.entry_time).stage != HUNTING
    ]
    assert suppressed == [], (
        f"{len(suppressed)} real {instrument}/{style} signals would be suppressed by the "
        f"gate, first: {suppressed[:3]}"
    )
