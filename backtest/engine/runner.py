"""
The Phase 5 backtest runner -- wires Phases 1-4 together against cached
candles and produces real TradeRecords instead of hand-built fixtures.

BIAS CHAIN (deliberately an MVP, not the full 5-level cascade): one
instrument, one chain -- Weekly (optional, see below) -> Daily -> H4
(lower-timeframe evidence for the flip test) -> H1 (trade-management
timeframe). Monthly is still out of scope (`bias_monthly` is always
logged as None).

Weekly is wired in the same way Daily is: its own full BiasCascade, gated
by Daily confirmations for the flip test's condition (c) -- the same
relationship H4 confirmations have to Daily's cascade. Per
TIMEFRAME_PRIORITY (bias.py), Weekly outranks Daily/H4/H1 whenever it has
an active bias. Weekly is OPTIONAL, not required: if the "W" granularity
hasn't been cached yet for an instrument, `run_backtest` falls back to
the Daily->H4->H1 chain (bias_weekly logs as None).

ENTRY GATE -- Bishop's liquidity cascade, not "any engulf aligned with
bias": an earlier version of this runner fired on ANY H1 engulfing candle
that happened to align with the effective bias, with no check that a real
setup had actually formed first. That was flagged (via a live EURUSD run
that came back with a 1.6% win rate) as the dominant reason results were
bad -- the filter had none of the selectivity STRATEGY.md's Bishop
supplementary material (knowledge-base/supplementary/b_*.md) describes.
The real mechanical sequence, cross-validated across all 6 Bishop videos
plus the PDF chart examples:
    4H breakout (in the bias direction)
    -> a single-candle liquidity point forms afterward, on the
       retracement side (a swing low after a bullish breakout, a swing
       high after a bearish one)
    -> price (H1) sweeps that liquidity point
    -> price then reacts off the NEAREST same-direction H4 key level
       (an engulfing candle touching/near that level, in the bias
       direction)
    -> that reaction candle IS the entry trigger.
This is now implemented as a precomputed gate (`_find_liquidity_setups()`
+ `_find_entry_candidates()`) that runs BEFORE the main per-trade loop:
only H1 candles that are the confirmed reaction of an actual
breakout->liquidity-sweep->KL-reaction sequence are even considered as
entries. Everything downstream of that gate (Video 14's 3 execution
patterns, the 3 mechanized stop-loss rules, the 1:3 target, MAE/MFE
tracking) is unchanged from before -- only the SELECTIVITY of which
candles get evaluated, and which key level they're evaluated against
(the Bishop-validated H4 reaction level, not an ad-hoc H1-engulf-derived
one), changed.

NOT YET BUILT in this gate (explicit follow-ups, not silently skipped):
- The liquidity point is H4-only. Bishop explicitly notes it sometimes
  forms on 2H instead ("some time its the 2H that will give us a single
  candle liquidity after the 4H breakout") -- a 2H fallback isn't wired
  in yet.
- Only ENGULFING is accepted as the confirmation-entry trigger. Bishop's
  material describes 3 valid confirmation-entry types (breakout,
  engulfing, sweep+break) -- the other two aren't wired into this gate
  yet (though `detect_confirmations()` already produces breakout/
  sweep_break events for H1, so this is a bounded extension, not new
  detection logic).
- "Plug and play" is now documented
  (`knowledge-base/supplementary/b_plug_and_play_notes.md`, transcribed
  from a Bishop community call) but NOT yet implemented here. It turned
  out to be broader than the "continuation fallback" framing used
  earlier in this docstring: mostly a discipline/consistency framework,
  plus two concrete new rules worth implementing -- (1) a
  daily-confirmation FALLBACK (when Daily doesn't independently confirm
  after Weekly's bias, but Daily has tested/rejected the same weekly
  level 2+ times, drop to 4H and require only ONE of breakout/sweep+break
  instead of both), and (2) a named compound entry signature ("conservation
  sector": disrespected + FVG-overlap + nearby resting liquidity, the last
  of which isn't currently one of `ranking.py`'s 4 weighted factors). Its
  entry MECHANIC is confirmed to be the same aggressive entry style
  already implemented (`aggressive_entry_price()`), not a third style.
- Bishop's imbalance-fill-priority refinement (a farther key level with a
  larger unfilled FVG can override the nearest-liquidity preference) and
  the "elbow structure" caution (a non-single-candle liquidity shape
  should be waited out in full, not traded on first touch) are both
  documented in the knowledge base but not yet factored into
  `_find_liquidity_setups()`.

Further MVP simplifications, each flagged where it happens rather than
silently assumed:
- The initial Weekly/Daily bias is bootstrapped from the first confirmed
  structural direction in each timeframe's own data (StructureTracker's
  first valid_sweep_break), not a hand-set starting bias.
- H4 and H1 "bias" for logging/hierarchy purposes uses a simpler reading
  (direction of the most recent confirmation as of that time) rather than
  each running its own full BiasCascade flip-state-machine -- only Weekly
  and Daily get the full 3-condition treatment, since those are the ones
  that actually gate whether a trade is taken.
- Once an H4 breakout's liquidity point and reaction level are found, the
  actual H1 reaction is still classified via Video 14's 3-pattern logic
  (`classify_entry_pattern()`), reusing the Bishop-validated H4 level as
  the reference level in place of the engulf's own open -- a reasonable
  adaptation (the "what happens right after price meets this level"
  question is the same regardless of which process identified the
  level), but a judgment call worth flagging.
- trade_kind ("origin" vs "continuation") is still approximated by
  proximity to the most recent Daily bias-flip breakpoint (ORIGIN_WINDOW)
  -- STRATEGY.md doesn't give a precise cutoff, and this is orthogonal to
  the new liquidity-cascade gate (it only affects which of the 3
  mechanized stop-loss rules applies to a setup the gate already
  approved).
- QMR test-counting and imbalance-overlap for the entry's key level both
  use H1 candles/imbalances (the level's own timeframe), bounded to the
  next QMR_LOOKAHEAD candles rather than an unbounded forward scan.
- If a stop and target are both touched within the same H1 candle, the
  stop is assumed to have been hit first -- a standard, conservative
  backtesting assumption, since OHLC data alone can't reveal true
  intrabar sequencing.
"""

import bisect
import os
from dataclasses import dataclass

import pandas as pd

from .candles import Candle, load_candles
from .structure import Direction, StructureTracker
from .key_levels import KeyLevel, detect_key_levels, count_tests_before_disrespect
from .liquidity import structural_liquidity_points
from .imbalance import detect_imbalances, overlaps_level
from .bias import detect_confirmations, replay_bias, bias_at, resolve_effective_bias
from .entries import (
    is_engulfing, classify_entry_pattern, EntryPattern,
    origin_stop_loss, continuation_stop_loss, tight_stop_loss_no_irl,
    aggressive_entry_price, conservative_entry_price,
)
from .trade_management import PositionManager, primary_target
from .trade_log import TradeRecord, write_trade_log, summarize

ORIGIN_WINDOW = pd.Timedelta(days=3)
QMR_LOOKAHEAD = 30
FOLLOWING_LOOKAHEAD = 3

# How many H1 candles forward to search, after an H4 single-candle
# liquidity point forms, for price to actually sweep it. Bounded for the
# same "don't force it, and don't scan forever" reasons as
# MAX_TRADE_DURATION_CANDLES below -- STRATEGY.md doesn't give this a
# precise cutoff (Section 5B: "requires patience... don't force it before
# inducement forms" is qualitative), so ~5 days of H1 bars is a practical
# stand-in, not a rule from the source material.
LIQUIDITY_SWEEP_LOOKAHEAD = 120

# How many H1 candles forward, after the liquidity sweep, to search for a
# reaction off the nearby H4 key level (an engulfing candle touching it,
# in the setup's direction). Shorter than LIQUIDITY_SWEEP_LOOKAHEAD since
# a genuine reaction should follow the sweep fairly quickly.
REACTION_LOOKAHEAD = 40

# How many H1 candles forward to search for a stop/target hit before
# giving up and marking a trade "still_open". Two independent reasons
# this is capped rather than scanning to the end of the data: (1)
# performance -- without a cap, a trade opened early in a multi-year H1
# series scans every remaining candle (up to 100,000+) if its target is
# never hit again, and with many trades opening over that history the
# total cost multiplies badly; (2) it's also the more faithful model --
# Section 8 states the strategy is a day-trading approach ("does not
# swing trades overnight as a rule"), so a trade genuinely unresolved
# after ~3 weeks of H1 bars isn't realistic to hold open in the first
# place. 500 H1 candles is a practical stand-in for that discipline, not
# a number STRATEGY.md itself specifies.
MAX_TRADE_DURATION_CANDLES = 500

# Best-effort per-instrument pip size -- most forex pairs are 0.0001, but
# JPY crosses, metals, oil, indices, and crypto all use different scales.
# Not exhaustive (see data_pipeline/instruments.py for the full list);
# anything missing here falls back to 0.0001 and should be overridden
# explicitly via --pip-size if that's wrong for a given instrument.
DEFAULT_PIP_SIZES = {
    "USDJPY": 0.01, "EURJPY": 0.01, "GBPJPY": 0.01, "AUDJPY": 0.01, "CHFJPY": 0.01,
    "XAUUSD": 0.1, "XAGUSD": 0.001,
    "USOIL": 0.01,
    "US30": 1.0, "NAS100": 1.0, "JP225": 1.0,
    "ETHUSD": 0.1,
}


def default_pip_size(instrument: str) -> float:
    return DEFAULT_PIP_SIZES.get(instrument, 0.0001)


def _direction_lookup(confirmations):
    """Pre-sorted (times, directions) arrays for O(log n) 'last direction
    before time t' queries, built once. The naive version of this --
    filtering the whole confirmation list on every call -- turns an O(n)
    per-candle backtest loop into O(n*m) against a confirmation list that
    can itself run into the thousands for a multi-year H1/H4 series
    (EURUSD's full Dukascopy H1 history is well over 100,000 candles).
    That combination is what makes an un-optimized run of this loop
    genuinely slow rather than fast, so this exists specifically to keep
    a full-history backtest run in the seconds-to-low-minutes range
    instead of many minutes."""
    sorted_confs = sorted(confirmations, key=lambda c: c.time)
    return [c.time for c in sorted_confs], [c.direction for c in sorted_confs]


def _last_direction_at(lookup, t):
    times, directions = lookup
    idx = bisect.bisect_left(times, t) - 1
    if idx < 0:
        return None
    return directions[idx]


def _strong_extreme_snapshots(daily_candles: list[Candle], daily_events):
    """One O(n) pass building parallel (times, lows, highs) arrays of the
    running strong_low/strong_high as of each daily candle, from
    StructureTracker's already-computed events -- instead of re-running
    the tracker per candle (which would be O(n^2)). Query with `_strong_at()`,
    NOT a direct dict lookup by timestamp: callers query with H1/H4
    timestamps that will essentially never exactly match a daily candle's
    own timestamp, so this needs an as-of-time-t lookup ("look to the
    left" to the most recent daily snapshot), not an exact-key match."""
    events_sorted = sorted((e for e in daily_events if e.kind == "valid_sweep_break"), key=lambda e: e.time)
    times, lows, highs = [], [], []
    strong_low_price, strong_high_price = None, None
    idx = 0
    for c in daily_candles:
        while idx < len(events_sorted) and events_sorted[idx].time <= c.time:
            e = events_sorted[idx]
            if e.direction == Direction.BULLISH:
                strong_low_price = e.price
            else:
                strong_high_price = e.price
            idx += 1
        times.append(c.time)
        lows.append(strong_low_price)
        highs.append(strong_high_price)
    return times, lows, highs


def _strong_at(snapshots, t):
    times, lows, highs = snapshots
    idx = bisect.bisect_right(times, t) - 1
    if idx < 0:
        return None, None
    return lows[idx], highs[idx]


@dataclass(frozen=True)
class LiquiditySetup:
    """One candidate Bishop-cascade setup: an H4 breakout that produced a
    single-candle liquidity point on the retracement side, plus the
    nearest same-direction H4 key level for price to react from once
    that liquidity is swept. Not yet a trade -- `_find_entry_candidates()`
    still has to confirm the sweep actually happens and price actually
    reacts, within bounded lookahead windows."""
    direction: Direction
    breakout_time: object
    liquidity_price: float
    liquidity_time: object
    reaction_level: KeyLevel


@dataclass(frozen=True)
class EntryCandidate:
    """A confirmed Bishop-cascade reaction: the H1 index of the engulfing
    candle that reacted off `reaction_level` after `direction`'s
    liquidity was swept. This IS the entry trigger."""
    index: int
    direction: Direction
    reaction_level: KeyLevel


def _find_liquidity_setups(h4: list[Candle], h4_confirmations, h4_key_levels: list[KeyLevel],
                            n: int = 2) -> list[LiquiditySetup]:
    """For each confirmed H4 breakout, find the first single-candle
    liquidity point (structural_liquidity_points with n=1 -- Bishop's
    primary/simplest case, see the module docstring for the not-yet-built
    structural/multi-candle generalization) that forms afterward on the
    retracement side, and the nearest same-direction H4 key level for
    price to react from once that liquidity is swept. A breakout that
    never produces both simply yields no setup -- consistent with
    Section 5B's "requires patience, don't force it" guidance."""
    liquidity_points = structural_liquidity_points(h4, n=1)
    breakouts = sorted(h4_confirmations, key=lambda c: c.time)
    setups = []

    for i, brk in enumerate(breakouts):
        next_breakout_time = breakouts[i + 1].time if i + 1 < len(breakouts) else None
        retracement_side = "low" if brk.direction == Direction.BULLISH else "high"

        candidate_points = [
            p for p in liquidity_points
            if p.time > brk.time and p.kind == retracement_side
            and (next_breakout_time is None or p.time < next_breakout_time)
        ]
        if not candidate_points:
            continue
        liquidity_point = candidate_points[0]

        candidate_levels = [
            lvl for lvl in h4_key_levels
            if lvl.default_bias == brk.direction and lvl.time <= liquidity_point.time
        ]
        if not candidate_levels:
            continue
        reaction_level = min(candidate_levels, key=lambda lvl: abs(lvl.price - liquidity_point.price))

        setups.append(LiquiditySetup(
            direction=brk.direction, breakout_time=brk.time,
            liquidity_price=liquidity_point.price, liquidity_time=liquidity_point.time,
            reaction_level=reaction_level,
        ))

    return setups


def _find_entry_candidates(h1: list[Candle], setups: list[LiquiditySetup]) -> list[EntryCandidate]:
    """For each setup: bounded forward-scan H1 for the sweep of
    `liquidity_price`, then a further bounded forward-scan for an
    engulfing candle (in the setup's direction) that also touches
    `reaction_level.price` -- the confirmed reaction. At most one
    candidate per setup (the first qualifying reaction), deduped by H1
    index in case two setups converge on the same candle."""
    times = [c.time for c in h1]
    candidates: list[EntryCandidate] = []
    seen_indices: set[int] = set()

    for setup in setups:
        start_idx = bisect.bisect_left(times, setup.liquidity_time)

        sweep_idx = None
        for idx in range(start_idx, min(start_idx + LIQUIDITY_SWEEP_LOOKAHEAD, len(h1))):
            c = h1[idx]
            swept = (c.low <= setup.liquidity_price if setup.direction == Direction.BULLISH
                     else c.high >= setup.liquidity_price)
            if swept:
                sweep_idx = idx
                break
        if sweep_idx is None:
            continue

        level_price = setup.reaction_level.price
        for idx in range(sweep_idx + 1, min(sweep_idx + 1 + REACTION_LOOKAHEAD, len(h1))):
            prev, curr = h1[idx - 1], h1[idx]
            touched = (prev.low <= level_price <= prev.high) or (curr.low <= level_price <= curr.high)
            if touched and is_engulfing(prev, curr, setup.direction) and idx not in seen_indices:
                candidates.append(EntryCandidate(idx, setup.direction, setup.reaction_level))
                seen_indices.add(idx)
                break

    return sorted(candidates, key=lambda ec: ec.index)


def _stop_on_correct_side(entry_price: float, stop_loss: float, direction: Direction) -> bool:
    """A BULLISH stop must sit below entry (it protects against price
    falling); a BEARISH stop must sit above entry. If it doesn't, the
    stop-loss computation produced garbage (see the call site in
    `run_backtest` for the concrete "origin" trade scenario that triggers
    this) and the trade must be skipped rather than opened."""
    if direction == Direction.BULLISH:
        return stop_loss < entry_price
    return stop_loss > entry_price


def _resolve_trade_outcome(entry_price: float, stop_loss: float, target_price: float,
                            direction: Direction, path: list[Candle]):
    """Walk forward through `path` (candles after entry) to find whichever
    of stop/target is touched first, tracking MAE/MFE in R along the way."""
    risk = abs(entry_price - stop_loss) or 1e-9
    worst = entry_price
    best = entry_price

    for c in path:
        if direction == Direction.BULLISH:
            worst = min(worst, c.low)
            best = max(best, c.high)
            stop_hit = c.low <= stop_loss
            target_hit = c.high >= target_price
        else:
            worst = max(worst, c.high)
            best = min(best, c.low)
            stop_hit = c.high >= stop_loss
            target_hit = c.low <= target_price

        adverse = (entry_price - worst) if direction == Direction.BULLISH else (worst - entry_price)
        favorable = (best - entry_price) if direction == Direction.BULLISH else (entry_price - best)
        mae_r, mfe_r = -adverse / risk, favorable / risk

        if stop_hit:  # stop wins same-candle ties -- see module docstring
            return "stop_hit", stop_loss, c.time, mae_r, mfe_r
        if target_hit:
            return "target_hit", target_price, c.time, mae_r, mfe_r

    adverse = (entry_price - worst) if direction == Direction.BULLISH else (worst - entry_price)
    favorable = (best - entry_price) if direction == Direction.BULLISH else (entry_price - best)
    return "still_open", None, None, -adverse / risk, favorable / risk


def run_backtest(instrument: str, entry_style: str, source: str = "dukascopy",
                  pip_size: float | None = None, n: int = 2) -> list[TradeRecord]:
    """
    entry_style: "aggressive" | "conservative" (Section 5 -- run both
    separately and compare; this function doesn't mix them in one pass).
    pip_size: defaults to `default_pip_size(instrument)` when not given.
    """
    if entry_style not in ("aggressive", "conservative"):
        raise ValueError("entry_style must be 'aggressive' or 'conservative'")
    if pip_size is None:
        pip_size = default_pip_size(instrument)

    try:
        daily = load_candles(source, instrument, "D")
        h4 = load_candles(source, instrument, "H4")
        h1 = load_candles(source, instrument, "H1")
    except FileNotFoundError:
        return []  # data not fetched yet for this instrument/granularity
    if not daily or not h4 or not h1:
        return []

    try:
        weekly = load_candles(source, instrument, "W")
    except FileNotFoundError:
        weekly = []  # Weekly is optional -- see module docstring

    daily_tracker = StructureTracker(n)
    daily_structure_events = daily_tracker.run(daily)
    first_origin = next((e for e in daily_structure_events if e.kind == "valid_sweep_break"), None)
    if first_origin is None:
        return []  # no confirmed structure to bootstrap a bias from

    daily_levels = detect_key_levels(daily, n)
    daily_confirmations = detect_confirmations(daily, n)
    h4_confirmations = detect_confirmations(h4, n)
    h4_levels = detect_key_levels(h4, n)
    h1_confirmations = detect_confirmations(h1, n)
    h1_imbalances = detect_imbalances(h1)

    daily_breakpoints = replay_bias(daily, daily_levels, h4_confirmations,
                                     first_origin.direction, "Daily")

    weekly_breakpoints = []
    if weekly:
        weekly_tracker = StructureTracker(n)
        weekly_structure_events = weekly_tracker.run(weekly)
        weekly_first_origin = next(
            (e for e in weekly_structure_events if e.kind == "valid_sweep_break"), None
        )
        if weekly_first_origin is not None:
            weekly_levels = detect_key_levels(weekly, n)
            weekly_breakpoints = replay_bias(weekly, weekly_levels, daily_confirmations,
                                              weekly_first_origin.direction, "Weekly")

    strong_snapshots = _strong_extreme_snapshots(daily, daily_structure_events)
    h4_lookup = _direction_lookup(h4_confirmations)
    h1_lookup = _direction_lookup(h1_confirmations)

    liquidity_setups = _find_liquidity_setups(h4, h4_confirmations, h4_levels, n)
    entry_candidates = _find_entry_candidates(h1, liquidity_setups)

    mgr = PositionManager()
    records: list[TradeRecord] = []
    trade_id = 0

    for candidate in entry_candidates:
        i = candidate.index
        prev, curr = h1[i - 1], h1[i]

        weekly_bias = bias_at(weekly_breakpoints, curr.time) if weekly_breakpoints else None
        daily_bias = bias_at(daily_breakpoints, curr.time)
        h4_bias = _last_direction_at(h4_lookup, curr.time)
        h1_bias = _last_direction_at(h1_lookup, curr.time)
        effective, effective_tf = resolve_effective_bias(
            {"Weekly": weekly_bias, "Daily": daily_bias, "H4": h4_bias}
        )
        # The higher-timeframe bias must still align with the cascade's
        # breakout direction at actual entry time -- bias can flip in the
        # (bounded) time between the H4 breakout and the eventual H1
        # reaction, and a stale-direction setup should not be traded.
        if effective is None or effective != candidate.direction:
            continue

        new_key_level = candidate.reaction_level
        following = h1[i + 1: i + 1 + FOLLOWING_LOOKAHEAD]
        classification = classify_entry_pattern(new_key_level, following)
        if classification is None:
            continue

        entry_price = (
            aggressive_entry_price(classification.reference_level)
            if entry_style == "aggressive"
            else conservative_entry_price(curr)
        )

        last_daily_flip_time = daily_breakpoints[-1][0] if daily_breakpoints else None
        is_origin = (last_daily_flip_time is not None
                     and curr.time - last_daily_flip_time <= ORIGIN_WINDOW)
        trade_kind = "origin" if is_origin else "continuation"

        if trade_kind == "origin":
            strong_low_price, strong_high_price = _strong_at(strong_snapshots, curr.time)
            structural_extreme = strong_low_price if effective == Direction.BULLISH else strong_high_price
            if structural_extreme is None:
                continue
            stop_loss = origin_stop_loss(structural_extreme, effective, pip_size=pip_size)
            stop_kind = "origin"
        elif classification.pattern == EntryPattern.FRESH_IRL_REQUIRED:
            stop_loss = continuation_stop_loss(entry_price, effective, pip_size=pip_size)
            stop_kind = "continuation"
        else:
            engulfed_extreme = prev.low if effective == Direction.BULLISH else prev.high
            stop_loss = tight_stop_loss_no_irl(engulfed_extreme, effective, pip_size=pip_size)
            stop_kind = "tight_no_irl"

        # A stop-loss on the wrong side of entry isn't a stop at all -- it's
        # a corrupted trade. This actually happens for "origin" trades: the
        # structural extreme comes from a Daily-timeframe snapshot that can
        # be stale relative to the current H1 price (trade_kind == "origin"
        # is currently a pure TIME-proximity heuristic to the bias flip --
        # see ORIGIN_WINDOW -- with no check that price is still PRICE-close
        # to the structural extreme it's meant to stop beyond). When that
        # happens, e.g. a BULLISH trade's stop lands ABOVE entry, hitting it
        # is actually a favorable price move, so the trade closes as
        # "closed_loss" (exit_reason == "stop_hit") while its r_multiple is
        # POSITIVE -- exactly the kind of corruption that produces a
        # displayed win rate and total-R that don't mathematically agree
        # (confirmed via a synthetic stress test; see backtest/README.md).
        if not _stop_on_correct_side(entry_price, stop_loss, effective):
            continue

        target = primary_target(entry_price, stop_loss, effective)

        overlapping = [im for im in h1_imbalances if overlaps_level(im, new_key_level.price)]
        imbalance_overlap = len(overlapping) > 0
        fill_size = max((im.high - im.low for im in overlapping), default=0.0)
        test_count, _ = count_tests_before_disrespect(h1[i + 1: i + 1 + QMR_LOOKAHEAD], new_key_level)

        concurrent = len(mgr.open_positions(effective))
        pos = mgr.open_position(effective, entry_price, stop_loss, curr.time, "H1", target)

        exit_reason, exit_price, exit_time, mae_r, mfe_r = _resolve_trade_outcome(
            entry_price, stop_loss, target, effective, h1[i + 1: i + 1 + MAX_TRADE_DURATION_CANDLES]
        )
        if exit_reason == "still_open":
            status = "open"
            r_multiple = None
        else:
            risk = abs(entry_price - stop_loss)
            signed = (exit_price - entry_price) if effective == Direction.BULLISH else (entry_price - exit_price)
            r_multiple = signed / risk if risk else 0.0
            status = "closed_win" if exit_reason == "target_hit" else "closed_loss"
            mgr.close_position(pos, status)

        trade_id += 1
        records.append(TradeRecord(
            trade_id=trade_id,
            instrument=instrument,
            entry_time=curr.time,
            exit_time=exit_time,
            direction=effective,
            entry_timeframe="H1",
            entry_price=entry_price,
            entry_pattern=classification.pattern.value,
            entry_style=entry_style,
            trade_kind=trade_kind,
            bias_weekly=weekly_bias,
            bias_daily=daily_bias,
            bias_h4=h4_bias,
            bias_h1=h1_bias,
            effective_bias_timeframe=effective_tf,
            key_level_price=new_key_level.price,
            key_level_shape=new_key_level.shape,
            imbalance_overlap=imbalance_overlap,
            qmr_test_count=test_count,
            imbalance_fill_size=fill_size,
            stop_loss=stop_loss,
            stop_kind=stop_kind,
            risk_pips=abs(entry_price - stop_loss) / pip_size,
            primary_target=target,
            concurrent_open_positions_at_entry=concurrent,
            exit_price=exit_price,
            exit_reason=exit_reason,
            r_multiple=r_multiple,
            mae_r=mae_r,
            mfe_r=mfe_r,
            status=status,
        ))

    return records


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Run the SLK backtest engine against cached candles.")
    parser.add_argument("--instrument", required=True, help="Internal symbol, e.g. EURUSD (see data_pipeline/instruments.py).")
    parser.add_argument("--style", choices=("aggressive", "conservative"), required=True)
    parser.add_argument("--source", default="dukascopy")
    parser.add_argument("--pip-size", type=float, default=None, help="Overrides the per-instrument default (see DEFAULT_PIP_SIZES).")
    parser.add_argument("--out", default=None, help="Output CSV path. Defaults to backtest/results/{instrument}_{style}.csv")
    args = parser.parse_args()

    records = run_backtest(args.instrument, args.style, source=args.source, pip_size=args.pip_size)

    out_path = args.out or f"backtest/results/{args.instrument}_{args.style}.csv"
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    write_trade_log(records, out_path)

    summary = summarize(records)
    print(f"{args.instrument} ({args.style}): {summary['total_trades']} trades, "
          f"{summary['closed_trades']} closed, win_rate={summary['win_rate']}, "
          f"avg_r={summary['avg_r']}, total_r={summary['total_r']}")
    print(f"Trade log written to {out_path}")


if __name__ == "__main__":
    main()
