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
    -> price then reacts off a same-direction H4 key level -- tried
       nearest-to-extreme in order, whichever one actually produces a real
       reaction first (an engulfing candle touching/near that level, in
       the bias direction), not a scored pick (see the reaction-level
       SELECTION paragraph below)
    -> that reaction candle IS the entry trigger.
This is now implemented as a precomputed gate (`_find_liquidity_setups()`
+ `_find_entry_candidates()`) that runs BEFORE the main per-trade loop:
only H1 candles that are the confirmed reaction of an actual
breakout->liquidity-sweep->KL-reaction sequence are even considered as
entries. Everything downstream of that gate (Video 14's 3 execution
patterns, the 1:3 target, MAE/MFE tracking) is unchanged from before --
only the SELECTIVITY of which candles get evaluated, and which key level
they're evaluated against (the Bishop-validated H4 reaction level, not an
ad-hoc H1-engulf-derived one), changed. The stop-loss rules (see
entries.py's module docstring) are now 4, not 3 -- see the "plug and
play" note below.

Reaction-level SELECTION among multiple same-direction candidates is NOT
a ranking/scoring problem -- an earlier version of this gate scored every
candidate via `ranking.py`'s 4-factor `score_candidates()` and picked the
best-scored one, but that's not how the source material actually works:
"we don't predict, we react." `_find_liquidity_setups()` now orders every
same-direction H4 key level still in play (bounded to the current
structural leg) nearest-to-extreme by distance from the swept liquidity
point, and `_find_entry_candidates()` tries them in that order, taking
whichever one is the first to actually produce a genuine reaction
(touched + engulfing) within the bounded lookahead window -- falling
through to the next candidate if the nearer one never holds. The extreme
(farthest) candidate is the LAST RESORT, not a scored pick, and a deep
retracement through the breakout point does NOT disqualify a candidate
from being reacted off. `ranking.py` and its tests still exist as
standalone domain logic but are no longer wired into this gate;
`ranking_score` stays at its `0.0` default on `TradeRecord`.

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
- "Plug and play" is documented
  (`knowledge-base/supplementary/b_plug_and_play_notes.md`, transcribed
  from a Bishop community call). It turned out to be broader than the
  "continuation fallback" framing used earlier in this docstring: mostly
  a discipline/consistency framework, plus concrete rules -- its STOP-LOSS
  mechanic is now implemented (`imbalance_stop_loss()`, used whenever a
  continuation trade's key level overlaps an imbalance -- see the
  stop-loss selection block below), user-verified against a real GBPUSD
  chart. Its entry MECHANIC is confirmed to be the same aggressive entry
  style already implemented (`aggressive_entry_price()`), not a third
  style. Still NOT yet implemented: (1) a daily-confirmation FALLBACK
  (when Daily doesn't independently confirm after Weekly's bias, but
  Daily has tested/rejected the same weekly level 2+ times, drop to 4H
  and require only ONE of breakout/sweep+break instead of both), and (2)
  a named compound entry signature ("conservation sector": disrespected +
  FVG-overlap + nearby resting liquidity, the last of which isn't
  currently one of `ranking.py`'s 4 weighted factors).
- Bishop's imbalance-fill-priority refinement (a farther key level with a
  larger unfilled FVG can override the nearest-liquidity preference) is
  NOT separately modeled now that selection is sequential/reactive rather
  than scored -- in practice a farther level only gets tried once nearer
  ones fail to produce a genuine reaction, which is a different mechanism
  than an outright override, not a strict replacement for it. The "elbow
  structure" caution (a non-single-candle liquidity shape should be
  waited out in full, not traded on first touch) is still documented in
  the knowledge base but not yet factored in.

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
- trade_kind ("origin" vs "continuation") is classified by literal
  sequence, not a fixed time window: the FIRST entry taken since the
  effective bias's own origin event is "origin", every subsequent entry
  within that same still-active leg is "continuation" -- "position in the
  move (first instance vs. repeated instance)", independent of which of
  the 4 confirmation-entry trigger types actually fired (see the
  `claimed_origins` bookkeeping in the main loop below; replaces the old
  `ORIGIN_WINDOW` fixed-day-proximity heuristic, which could misclassify
  a trade purely because it happened to fall inside/outside an arbitrary
  window rather than by whether an earlier trade had already been taken
  in that leg). This is orthogonal to the liquidity-cascade gate (it only
  affects which of the mechanized stop-loss rules applies to a setup the
  gate already approved). Origin stops used to anchor to a Daily-timeframe
  structural-extreme snapshot that
  could be stale (PRICE-far from the origin's own structural extreme) by
  the time an H1 entry actually fired, producing stops (and therefore 3R
  targets) far wider than anything in the source material ever
  describes -- the leading cause of trades that never resolved within
  MAX_TRADE_DURATION_CANDLES. Fixed by anchoring `origin_stop_loss()` to
  `EntryCandidate.liquidity_price` instead (see `origin_stop_loss()`'s
  call site above) -- the SAME local H4 liquidity point that triggered
  this specific entry, i.e. the "particular high/low that was actually
  created" Bishop's mentor describes placing stops beyond (Video 13's
  origin stop-loss Q&A), and visually confirmed against Video 4's
  worked example (a fixed ~9 pip stop, not a distant swing).
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
from .bias import detect_confirmations, replay_bias, bias_at, origin_time_at, resolve_effective_bias
from .entries import (
    is_engulfing, classify_entry_pattern, EntryPattern,
    origin_stop_loss, continuation_stop_loss, tight_stop_loss_no_irl, imbalance_stop_loss,
    aggressive_entry_price, conservative_entry_price,
)
from .trade_management import PositionManager, primary_target
from .trade_log import TradeRecord, write_trade_log, summarize

QMR_LOOKAHEAD = 30
FOLLOWING_LOOKAHEAD = 3

# How far back a tier's OWN breakout/sweep+break can be and still count as
# "aligned" with the current H1 entry candidate. Bounded for the same
# reason candidate_levels/imbalance matching got bounded elsewhere in this
# file (an unboundedly old confirmation isn't really "aligned" with what's
# happening right now). Chosen generously per tier's own timescale -- not
# a specific number given in the source material, which only states the
# qualitative rule: more tiers aligned via their own breakout/sweep+break
# = higher-probability trade; "4H can't stand alone if at least the Daily
# isn't aligned to it" (direct guidance) -- Daily+H4 is the practical
# minimum, Weekly is a bonus when it's there too.
ALIGNMENT_LOOKBACK = {
    "Weekly": pd.Timedelta(days=120),
    "Daily": pd.Timedelta(days=45),
    "H4": pd.Timedelta(days=21),
}

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


def _last_time_at(lookup, t):
    """H4/H1's origin-time counterpart to `origin_time_at()` (bias.py):
    H4 and H1 don't get a full BiasCascade replay (see the module
    docstring's MVP-simplifications list), so there's no breakpoints list
    to query -- the most recent confirmation's own time before `t` stands
    in as that tier's origin event instead."""
    times, directions = lookup
    idx = bisect.bisect_left(times, t) - 1
    if idx < 0:
        return None
    return times[idx]


def _aligned_timeframes(direction: Direction, as_of_time, weekly_confirmations,
                         daily_confirmations, h4_confirmations) -> list[str]:
    """Which of Weekly/Daily/H4 currently show THEIR OWN breakout or
    sweep+break confirming `direction`, within a bounded recency window
    (ALIGNMENT_LOOKBACK) of `as_of_time` -- never satisfied by an
    open-close break or plain engulf, since detect_confirmations() never
    produces those events. This is the multi-timeframe ALIGNMENT check
    (more tiers aligned = higher-probability trade), a different question
    from resolve_effective_bias()'s "which single highest-priority
    timeframe has an active bias reading right now". Returns the aligned
    subset in TIMEFRAME_PRIORITY order, e.g. ["Daily", "H4"]."""
    aligned = []
    for label, confirmations in (("Weekly", weekly_confirmations),
                                  ("Daily", daily_confirmations),
                                  ("H4", h4_confirmations)):
        lookback = ALIGNMENT_LOOKBACK[label]
        recent = [c for c in confirmations if c.time <= as_of_time and as_of_time - c.time <= lookback]
        if recent and max(recent, key=lambda c: c.time).direction == direction:
            aligned.append(label)
    return aligned


@dataclass(frozen=True)
class LiquiditySetup:
    """One candidate Bishop-cascade setup: an H4 breakout that produced a
    single-candle liquidity point on the retracement side, plus every
    same-direction H4 key level price COULD react from once that
    liquidity is swept, ordered nearest-to-extreme. Not a prediction of
    which one wins -- "we don't predict, we react": `_find_entry_candidates()`
    tries them in that order and uses whichever one actually produces a
    real reaction (a genuine touch-and-confirm, not just proximity or a
    score), falling through to the next candidate if the nearer one never
    holds. The extreme (last) candidate is the last resort, not the
    default."""
    direction: Direction
    breakout_time: object
    liquidity_price: float
    liquidity_time: object
    reaction_level_candidates: list[KeyLevel]


@dataclass(frozen=True)
class EntryCandidate:
    """A confirmed Bishop-cascade reaction: the H1 index of the engulfing
    candle that reacted off `reaction_level` after `direction`'s
    liquidity was swept. This IS the entry trigger.

    `liquidity_price` carries over the setup's own swept liquidity point --
    the "particular high/low that was actually created" by this specific
    setup's sweep (Video 13's origin stop-loss Q&A), used as the origin
    stop-loss anchor instead of a daily-timeframe snapshot that may be
    stale relative to this exact entry (see `origin_stop_loss()`'s call
    site in `run_backtest`)."""
    index: int
    direction: Direction
    reaction_level: KeyLevel
    liquidity_price: float


def _find_liquidity_setups(h4: list[Candle], h4_confirmations, h4_key_levels: list[KeyLevel],
                            n: int = 2) -> list[LiquiditySetup]:
    """For each confirmed H4 breakout, find the first single-candle
    liquidity point (structural_liquidity_points with n=1 -- Bishop's
    primary/simplest case, see the module docstring for the not-yet-built
    structural/multi-candle generalization) that forms afterward on the
    retracement side, and every same-direction H4 key level price still in
    play once that liquidity is swept, ordered nearest-to-extreme so
    `_find_entry_candidates()` can try them in that order ("we don't
    predict, we react" -- see LiquiditySetup's docstring). A breakout that
    never produces both simply yields no setup -- consistent with Section
    5B's "requires patience, don't force it" guidance."""
    liquidity_points = structural_liquidity_points(h4, n=1)
    breakouts = sorted(h4_confirmations, key=lambda c: c.time)
    setups = []

    for i, brk in enumerate(breakouts):
        prev_breakout_time = breakouts[i - 1].time if i > 0 else None
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

        # Bounded to the CURRENT structural leg (since the previous breakout,
        # any direction), not "every same-direction level in the whole
        # series" -- a level from years before the market's last major
        # direction change was never really "still in play" for this
        # setup. This also keeps the reaction-level search in
        # `_find_entry_candidates()` bounded to a single inter-breakout
        # span instead of, in the worst case, decades of H4 candles --
        # across a multi-year backtest that unbounded version turns into a
        # hang, not just a slowdown (see backtest/README.md's changelog).
        candidate_levels = [
            lvl for lvl in h4_key_levels
            if lvl.default_bias == brk.direction and lvl.time <= liquidity_point.time
            and (prev_breakout_time is None or lvl.time >= prev_breakout_time)
        ]
        if not candidate_levels:
            continue

        reaction_level_candidates = sorted(
            candidate_levels, key=lambda lvl: abs(lvl.price - liquidity_point.price)
        )

        setups.append(LiquiditySetup(
            direction=brk.direction, breakout_time=brk.time,
            liquidity_price=liquidity_point.price, liquidity_time=liquidity_point.time,
            reaction_level_candidates=reaction_level_candidates,
        ))

    return setups


def _find_entry_candidates(h1: list[Candle], setups: list[LiquiditySetup]) -> list[EntryCandidate]:
    """For each setup: bounded forward-scan H1 for the sweep of
    `liquidity_price`, then -- "we don't predict, we react" -- try each of
    `reaction_level_candidates` in nearest-to-extreme order, each scanning
    the same bounded REACTION_LOOKAHEAD window from the sweep for a
    genuine touch-and-engulf. The first candidate that actually produces
    one wins; if the nearest candidate never gets touched-and-confirmed,
    price may still run to the next one down the list, with the extreme
    candidate as the last resort. At most one candidate per setup (the
    first qualifying reaction), deduped by H1 index in case two setups
    converge on the same candle."""
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

        for level in setup.reaction_level_candidates:
            level_price = level.price
            found_idx = None
            for idx in range(sweep_idx + 1, min(sweep_idx + 1 + REACTION_LOOKAHEAD, len(h1))):
                prev, curr = h1[idx - 1], h1[idx]
                touched = (prev.low <= level_price <= prev.high) or (curr.low <= level_price <= curr.high)
                if touched and is_engulfing(prev, curr, setup.direction) and idx not in seen_indices:
                    found_idx = idx
                    break
            if found_idx is not None:
                candidates.append(EntryCandidate(found_idx, setup.direction, level, setup.liquidity_price))
                seen_indices.add(found_idx)
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
    weekly_confirmations = detect_confirmations(weekly, n) if weekly else []
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

    h4_lookup = _direction_lookup(h4_confirmations)
    h1_lookup = _direction_lookup(h1_confirmations)

    liquidity_setups = _find_liquidity_setups(h4, h4_confirmations, h4_levels, n)
    entry_candidates = _find_entry_candidates(h1, liquidity_setups)

    mgr = PositionManager()
    records: list[TradeRecord] = []
    trade_id = 0
    # Tracks which (effective_tf, direction, origin_time) legs have
    # already had a trade taken -- the FIRST entry_candidate to claim a
    # given leg is "origin", every later one in the same still-active leg
    # is "continuation". entry_candidates is already time-sorted, so a
    # plain set membership check is enough.
    claimed_origins: set[tuple[str, Direction, object]] = set()

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

        # Multi-timeframe ALIGNMENT gate -- separate from (and stricter
        # than) the effective-bias check above. "4H can't stand alone if
        # at least the Daily isn't aligned to it": require Daily and H4 to
        # each show their OWN breakout/sweep+break confirming this
        # direction, not just whichever single highest-priority timeframe
        # resolve_effective_bias() picked. Weekly, when it also aligns, is
        # logged but not required -- it's a probability booster, not a
        # gate by itself.
        aligned = _aligned_timeframes(candidate.direction, curr.time,
                                       weekly_confirmations, daily_confirmations, h4_confirmations)
        if not ("Daily" in aligned and "H4" in aligned):
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

        # trade_kind by literal position in the move, not a time window:
        # the FIRST entry since the effective bias's own origin event
        # claims "origin" for that (timeframe, direction, origin_time)
        # leg; every subsequent entry in the same still-active leg is
        # "continuation". H4 has no BiasCascade breakpoints (see the
        # module docstring), so its own most recent confirmation time
        # stands in for the origin event there. Only PEEK at
        # claimed_origins here -- actually claiming it happens below,
        # after the trade is confirmed to survive the stop-on-correct-side
        # guard, so a setup that gets rejected there doesn't burn the
        # "origin" slot for the real first trade in that leg.
        if effective_tf == "Weekly":
            origin_time = origin_time_at(weekly_breakpoints, curr.time)
        elif effective_tf == "Daily":
            origin_time = origin_time_at(daily_breakpoints, curr.time)
        else:
            origin_time = _last_time_at(h4_lookup, curr.time)
        origin_key = (effective_tf, effective, origin_time)
        trade_kind = "origin" if (origin_time is not None and origin_key not in claimed_origins) else "continuation"

        # Computed before the stop-loss selection below (not just for the
        # imbalance_overlap/fill_size stats further down) because "plug and
        # play" -- a continuation trade whose key level overlaps an
        # imbalance -- gets a different, imbalance-anchored stop-loss rule
        # in preference to the generic continuation rules. See
        # entries.py's module docstring for why this takes priority.
        #
        # Bounded to imbalances formed between the key level's own
        # formation and this entry -- NOT "any imbalance ever detected in
        # h1_imbalances (the WHOLE H1 history) that happens to overlap
        # this price," which is what this used to be. h1_imbalances is
        # computed once over the full multi-year series, so an unbounded
        # price-only match can pull in a gap from years earlier or later
        # that has nothing to do with this setup -- confirmed directly via
        # the trade-chart viewer: a real trade got an 83-pip "plug and
        # play" stop anchored to a spuriously-matched 114-pip imbalance,
        # nowhere near the tight 5-15 pip stops every video example shows.
        # The bound below scopes it to "did an imbalance form while THIS
        # level was being made and price coming back to react off it,"
        # which is what "plug and play" actually describes.
        overlapping = [
            im for im in h1_imbalances
            if overlaps_level(im, new_key_level.price) and new_key_level.time <= im.time <= curr.time
        ]
        imbalance_overlap = len(overlapping) > 0
        widest_imbalance = max(overlapping, key=lambda im: im.high - im.low, default=None)
        fill_size = widest_imbalance.high - widest_imbalance.low if widest_imbalance else 0.0

        if trade_kind == "continuation" and imbalance_overlap:
            stop_loss = imbalance_stop_loss(
                widest_imbalance.low, widest_imbalance.high, effective, pip_size=pip_size
            )
            stop_kind = "imbalance"
        elif trade_kind == "origin":
            stop_loss = origin_stop_loss(candidate.liquidity_price, effective, pip_size=pip_size)
            stop_kind = "origin"
        elif classification.pattern == EntryPattern.FRESH_IRL_REQUIRED:
            stop_loss = continuation_stop_loss(entry_price, effective, pip_size=pip_size)
            stop_kind = "continuation"
        else:
            engulfed_extreme = prev.low if effective == Direction.BULLISH else prev.high
            stop_loss = tight_stop_loss_no_irl(engulfed_extreme, effective, pip_size=pip_size)
            stop_kind = "tight_no_irl"

        # A stop-loss on the wrong side of entry isn't a stop at all -- it's
        # a corrupted trade. This used to actually happen for "origin"
        # trades, back when the structural extreme came from a
        # Daily-timeframe snapshot picked by pure TIME-proximity to the
        # bias flip (the old ORIGIN_WINDOW heuristic) with no check that
        # price was still PRICE-close to it by the time an H1 entry
        # actually fired -- a
        # BULLISH trade's stop could land ABOVE entry, so hitting it was
        # actually a favorable price move, closing as "closed_loss"
        # (exit_reason == "stop_hit") with a POSITIVE r_multiple (confirmed
        # via a synthetic stress test; see backtest/README.md). Origin
        # stops are now anchored to `candidate.liquidity_price` -- the same
        # local sweep point that triggered this specific entry -- which by
        # construction sits on the correct side, but this guard stays as a
        # defensive check for all stop kinds.
        if not _stop_on_correct_side(entry_price, stop_loss, effective):
            continue
        if trade_kind == "origin":
            claimed_origins.add(origin_key)

        target = primary_target(entry_price, stop_loss, effective)

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
            aligned_timeframes=",".join(aligned),
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
