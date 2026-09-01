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
       reaction first (an engulfing OR 4th-man confirmation touching that
       level, in the bias direction -- `_reaction_trigger()`), not a
       scored pick (see the reaction-level SELECTION paragraph below)
    -> that reaction candle IS the entry trigger.
This is now implemented as a precomputed gate (`_find_liquidity_setups()`
+ `_find_entry_candidates()`) that runs BEFORE the main per-trade loop:
only H1 candles that are the confirmed reaction of an actual
breakout->liquidity-sweep->KL-reaction sequence are even considered as
entries. Everything downstream of that gate (Video 14's 3 execution
patterns, the 1:3 target, MAE/MFE tracking) is unchanged from before --
only the SELECTIVITY of which candles get evaluated, and which key level
they're evaluated against (the Bishop-validated H4 reaction level, not an
ad-hoc H1-engulf-derived one), changed. Stop-loss selection is keyed to
WHICH TRIGGER fired -- plug and play / engulfing / 4th-man, plus a
universal fallback -- not to any origin/continuation classification (see
entries.py's module docstring point 5 and the stop-loss selection block
below).

Reaction-level SELECTION among multiple same-direction candidates is NOT
a ranking/scoring problem -- an earlier version of this gate scored every
candidate via `ranking.py`'s 4-factor `score_candidates()` and picked the
best-scored one, but that's not how the source material actually works:
"we don't predict, we react." `_find_liquidity_setups()` now orders every
same-direction H4 key level still in play (bounded to the current
structural leg) nearest-to-extreme by distance from the swept liquidity
point, and `_find_entry_candidates()` tries them in that order, taking
whichever one is the first to actually produce a genuine reaction
(touched + engulfing or 4th-man confirmation) within the bounded
lookahead window -- falling
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
- ENGULFING and 4TH-MAN CONFIRMATION are both wired as reaction triggers
  now (`_reaction_trigger()`, engulfing checked first); a direct
  breakout/sweep+break of the reaction level itself is the one
  remaining confirmation-entry trigger type NOT wired into this gate
  (though `detect_confirmations()` already produces breakout/sweep_break
  events for H1, so this is a bounded extension, not new detection
  logic) -- its stop-loss rule (`breakout_leg_stop_loss()`, the low of
  the whole leg that produced the breakout) isn't added yet either,
  since nothing would call it.
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
- Stop-loss (see entries.py's module docstring point 5 for the full
  per-trigger breakdown): "must also clear any other nearby same-type KL
  price could still reach, not just the nearest one" is NOT yet
  implemented -- the trigger-keyed stop rules only account for the
  SINGLE reaction level/candle currently in play, not other close-by
  same-shape candidates from `reaction_level_candidates`.
- Target: `_nearest_erl()` (revised -- see the "ERL redefinition" entry
  in backtest/README.md's changelog) sources candidates from Daily/Weekly
  period extremes only, excludes the still-forming current period, and
  excludes anything already swept by a later period before entry. It
  does NOT distinguish 4:1 from the flat 3:1 default (`RISK_REWARD_
  PRIMARY` in trade_management.py) -- STRATEGY.md's "3:1 or 4:1" isn't
  given a precise selection rule between the two, so this keeps the
  existing 3:1 baseline and only adds the ERL cap on top of it. And even
  a genuinely correct ERL doesn't always cause a reversal when swept
  (direct user correction) -- that's inherently probabilistic and not
  something a deterministic cap can model; this only fixes the
  false-positive rate of what counts as a candidate in the first place.

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
- There is deliberately NO origin/continuation classification. Three
  successive versions of this file tried one -- an `ORIGIN_WINDOW`
  fixed-day-proximity heuristic, then a `claimed_origins` "first trade
  since the effective bias's origin event" rule -- and both were retired
  by direct user correction. The reason is not that the labels were
  computed badly but that a single global label cannot be right at all:
  markets are fractal, so the same trade is an origin on one timeframe
  and a continuation on another at the same moment. The second version
  in particular resolved to "first trade since the WEEKLY bias last
  flipped" for 100% of trades, which is not what the source material
  means by either word. And operationally it changed nothing -- "even if
  it's origin or not it doesn't change the thought process towards a
  trade". Stop-loss selection is keyed to WHICH TRIGGER fired instead
  (see the "Stop-loss selection" paragraph above and entries.py's module
  docstring point 5).

  Retiring the origin-specific stop rule also incidentally fixed a real
  bug it had introduced: an aggressive entry AT a reaction key level that
  sits beyond the swept liquidity point (in the trade's own direction)
  could land that old origin stop on the WRONG side of entry --
  `_stop_on_correct_side()` caught it defensively, but the trade was
  silently dropped. The engulfing/4th-man stop rules derive from price
  actually near entry, not a separate liquidity-point reference, so this
  can no longer happen for those two triggers.
- IRL->ERL, on the other hand, IS enforced (optionally): "price always
  moves from IRL to ERL" is a core concept, and unlike origin/
  continuation it is a statement about sequence that applies to every
  trade. `irl_mode` decides what to do with an entry whose internal
  range liquidity formed but hasn't been swept yet -- see the gate in
  the main loop below.
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
from .structure import Direction, StructureTracker, known_at as point_known_at
from .key_levels import KeyLevel, detect_key_levels, count_tests_before_disrespect, known_at as level_known_at
from .liquidity import structural_liquidity_points
from .imbalance import detect_imbalances, overlaps_level
from .bias import detect_confirmations, replay_bias, bias_at, resolve_effective_bias
from .entries import (
    is_engulfing, fourth_man_confirmation_level, classify_entry_pattern, EntryPattern,
    origin_stop_loss, imbalance_stop_loss, engulfing_stop_loss, fourth_man_stop_loss,
    aggressive_entry_price, conservative_entry_price,
)
from .trade_management import PositionManager, primary_target, RISK_REWARD_PRIMARY
from .trade_log import TradeRecord, write_trade_log, summarize

QMR_LOOKAHEAD = 30
FOLLOWING_LOOKAHEAD = 3

# STRATEGY.md Section 8: "Avoid holding into very late hours -- spread
# widens sharply around session rollover (~10pm reference)." Confirmed
# live 2026-08-31: a GBPAUD entry at 22:00 UTC filled 54 points worse
# than requested (Market Execution mode gives no slippage cap), turning
# an intended $1,000 risk into a realized -$1,530.32 loss when it hit
# its stop -- the exact failure mode this window exists to avoid. Hours
# are UTC, matching every candle timestamp in this codebase; 21:00-23:00
# centers on the actual NY-close/rollover point with an hour of padding
# either side, per direct 2026-09-01 correction (not literally just "10
# pm" -- the doc's own wording is a loose reference, not a precise bound).
ROLLOVER_WINDOW_START_HOUR_UTC = 21
ROLLOVER_WINDOW_END_HOUR_UTC = 23  # exclusive -- blocks the 21:00 and 22:00 H1 candles

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
# How many of the lower timeframe's next confirmations are checked for
# the bias-flip test's condition (c) -- "the lower timeframe also stops
# confirming the old direction". 1 = Bishop's actual rule as stated
# directly by the user: you look at the lower timeframe's MOST RECENT
# breakout, and if it points the new way, the bias has flipped. 2 is the
# stated tolerance when that breakout isn't clean.
#
# This was 5 -- never sourced, and it silently vetoed ~98% of otherwise
# valid flips, leaving the daily bias unchanged for years at a time. See
# replay_bias()'s docstring in bias.py for the measurements.
BIAS_CONFIRMATION_WINDOW = 1

# How far past the reaction candle an origin trade's fresh IRL may take
# to be swept before the setup is treated as never having completed
# (irl_mode="wait"). 24 H1 candles = one trading day.
IRL_SWEEP_LOOKAHEAD = 24

LIQUIDITY_SWEEP_LOOKAHEAD = 120

# How many H1 candles forward, after the liquidity sweep, to search for a
# reaction off the nearby H4 key level (an engulfing or 4th-man candle
# touching it, in the setup's direction). Shorter than
# LIQUIDITY_SWEEP_LOOKAHEAD since a genuine reaction should follow the
# sweep fairly quickly.
REACTION_LOOKAHEAD = 40

# Judgment call, not a number from the source material: how many pips a
# trigger's own natural stop-loss anchor (engulfing/4th-man's own wick)
# can sit from entry before it's "too wide" and the universal 4H-KL
# fallback (the reaction level itself) takes over instead -- "if the
# logic is correct and price shouldn't come back to it... The probability
# is like 1 or 2 out of 10" (direct user quote). STRATEGY.md's own worked
# examples run 5-15 pips; picked generously above that so genuinely tight
# setups are never second-guessed, while a blown-out anchor (e.g. an
# unusually wide sweep-candle wick) still gets caught.
MAX_NATURAL_STOP_PIPS = 30.0


def _natural_stop_too_wide(entry_price: float, stop_loss: float, pip_size: float,
                            max_pips: float = MAX_NATURAL_STOP_PIPS) -> bool:
    return abs(entry_price - stop_loss) / pip_size > max_pips


def _sweep_indices(series: list[Candle], kind: str) -> list:
    """For each period, the index of the first LATER period that took its
    high (kind="high") / low (kind="low"), or None if never taken.
    Monotonic stack, O(n).

    Cached per (series, kind): the result depends only on the series, NOT
    on any `as_of_time`, but `_unswept_period_extremes()` is called twice
    per trade and used to rebuild this from scratch every time -- ~7.7s of
    a single run_backtest, over 1,480 calls against an 8,000-candle daily
    series. Keyed by id() with the series itself held alongside, so a
    recycled id can't return another series' answer; scoped to one
    run_backtest via _reset_sweep_cache()."""
    key = (id(series), kind)
    hit = _SWEEP_CACHE.get(key)
    if hit is not None and hit[0] is series:
        return hit[1]

    n = len(series)
    sweep_index: list = [None] * n
    stack: list[int] = []
    if kind == "high":
        for i in range(n):
            while stack and series[stack[-1]].high <= series[i].high:
                sweep_index[stack.pop()] = i
            stack.append(i)
    else:
        for i in range(n):
            while stack and series[stack[-1]].low >= series[i].low:
                sweep_index[stack.pop()] = i
            stack.append(i)

    _SWEEP_CACHE[key] = (series, sweep_index)
    return sweep_index


_SWEEP_CACHE: dict = {}


def _reset_sweep_cache():
    """Dropped at the start of every run_backtest so a long-lived live
    process doesn't retain candle series from previous iterations."""
    _SWEEP_CACHE.clear()


def _unswept_period_extremes(series: list[Candle], as_of_time, kind: str) -> list[float]:
    """Every COMPLETED period's own high (kind="high") or low (kind="low")
    in `series` that hasn't been touched/exceeded by any LATER period in
    the same series before `as_of_time` -- Section 3's actual ERL
    definition (`SequentialLiquidityTracker`): "previous daily/weekly
    high/low," a period's own extreme, not an arbitrary multi-candle
    swing fractal. The LAST period (whichever one `as_of_time` itself
    falls inside) is always excluded -- a still-forming period isn't a
    fixed "previous" reference yet.

    O(n) per call via a monotonic stack (the standard "next greater/
    smaller-or-equal element" problem) to find each period's own sweep
    point, not an O(n^2) rescan per candidate -- this runs once per
    trade, and a Daily series alone is ~8,000+ candles across a full
    multi-year backtest."""
    n = len(series)
    sweep_index = _sweep_indices(series, kind)

    extremes = []
    for i in range(n - 1):
        if series[i + 1].time > as_of_time:
            break  # period i+1 hasn't started yet -- period i is still the CURRENT one, excluded
        if sweep_index[i] is not None and series[sweep_index[i]].time <= as_of_time:
            continue  # already swept by a later period before entry -- not real untaken liquidity anymore
        extremes.append(series[i].high if kind == "high" else series[i].low)
    return extremes


def _nearest_erl(direction: Direction, entry_price: float, as_of_time,
                  *period_series: list[Candle]) -> float | None:
    """The nearest untaken external range liquidity point, in the trade
    direction, across whichever PERIOD candle series are passed (Daily/
    Weekly -- NOT H4: H4 is the entry cascade's own internal working
    timeframe, not external relative to it). "Price wants to go from
    internal range liquidity to external," not beyond it (direct user
    correction; see trade_management.py's `primary_target()`, which uses
    this to cap the default 1:3/4:1 R:R rather than let it overshoot a
    real, already-visible structural point).

    Deliberately NOT "any nearby swing high/low" -- an earlier version of
    this function used a generic 2-candle fractal detector across H4/
    Daily/Weekly, which on real EURUSD data capped 96% of trades (a
    swing point every few H4 candles isn't external liquidity, it's
    noise) and flipped a backtest from solidly positive total R to
    negative despite a much higher win rate. See `_unswept_period_
    extremes()` for the corrected definition. Even a genuinely correct
    ERL doesn't always cause a reversal when swept -- that's inherently
    probabilistic and not something a deterministic cap can model; this
    only fixes the false-positive rate, not that deeper limitation.
    Returns None if nothing qualifies on any series passed (the caller
    then falls back to the plain, uncapped rr target)."""
    kind = "high" if direction == Direction.BULLISH else "low"
    candidates = []
    for series in period_series:
        if not series:
            continue
        for price in _unswept_period_extremes(series, as_of_time, kind):
            beyond = price > entry_price if direction == Direction.BULLISH else price < entry_price
            if beyond:
                candidates.append(price)
    if not candidates:
        return None
    return min(candidates) if direction == Direction.BULLISH else max(candidates)

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


def _aligned_timeframes(direction: Direction, as_of_time, weekly_confirmations,
                         daily_confirmations, h4_confirmations, lookups=None) -> list[str]:
    """Which of Weekly/Daily/H4 currently show THEIR OWN breakout or
    sweep+break confirming `direction`, within a bounded recency window
    (ALIGNMENT_LOOKBACK) of `as_of_time` -- never satisfied by an
    open-close break or plain engulf, since detect_confirmations() never
    produces those events. This is the multi-timeframe ALIGNMENT check
    (more tiers aligned = higher-probability trade), a different question
    from resolve_effective_bias()'s "which single highest-priority
    timeframe has an active bias reading right now". Returns the aligned
    subset in TIMEFRAME_PRIORITY order, e.g. ["Daily", "H4"].

    `lookups` is an optional pre-built {label: _direction_lookup(...)}
    mapping. This runs once per timeframe per entry candidate --
    thousands of candidates against confirmation lists thousands long --
    so re-deriving those arrays per call, as the original list
    comprehension effectively did, is a multi-million-operation scan
    buried inside the entry loop, and one of the reasons a single
    run_backtest took ~8 minutes on the live VPS. run_backtest builds
    them once and passes them in; callers that don't care (tests) omit
    it and get the same answer, just more slowly."""
    if lookups is None:
        lookups = {
            "Weekly": _direction_lookup(weekly_confirmations),
            "Daily": _direction_lookup(daily_confirmations),
            "H4": _direction_lookup(h4_confirmations),
        }

    aligned = []
    for label in ("Weekly", "Daily", "H4"):
        times, directions = lookups[label]
        if not times:
            continue
        # Only the MOST RECENT confirmation at or before `as_of_time` can
        # win the `max(...)` this used to do, so bisect straight to it.
        idx = bisect.bisect_right(times, as_of_time) - 1
        if idx < 0:
            continue
        if as_of_time - times[idx] > ALIGNMENT_LOOKBACK[label]:
            continue
        if directions[idx] == direction:
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
    """A confirmed Bishop-cascade reaction: the H1 index of the candle
    that reacted off `reaction_level` after `direction`'s liquidity was
    swept. This IS the entry trigger.

    `trigger` -- which of the confirmation-entry trigger types actually
    fired at `index`: "engulfing" or "fourth_man" (checked in that
    priority order at each candle -- see `_find_entry_candidates()`). NOT
    yet "plug_and_play" or "breakout" here: plug-and-play is a promotion
    applied downstream once an overlapping imbalance is confirmed (run_
    backtest's `overlapping=` computation, which needs h1_imbalances --
    not available at this point in the pipeline), and breakout-as-its-
    own-trigger isn't wired into this search yet (see the module
    docstring's NOT-YET-BUILT list).

    `liquidity_price` carries over the setup's own swept liquidity point --
    the "particular high/low that was actually created" by this specific
    setup's sweep (Video 13's origin stop-loss Q&A)."""
    index: int
    direction: Direction
    reaction_level: KeyLevel
    liquidity_price: float
    trigger: str


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

    # Pre-indexed, time-sorted views so each breakout's searches below are
    # bisect lookups into a bounded slice rather than a linear scan of the
    # whole multi-year history. Measured at ~71% of a single
    # run_backtest's total runtime before this: with ~4,000 breakouts each
    # scanning every liquidity point AND every H4 key level, the two
    # comprehensions below were tens of millions of comparisons per call.
    # Pure performance change -- the selection semantics are unchanged
    # (verified bit-identical against the pre-optimization output).
    #
    # Sorted/bisected on known_at, not .time -- a liquidity point or H4
    # key level isn't actually usable until n bars after it forms
    # (2026-08-28 fix; see OPEN_QUESTIONS.md's lookahead-bias entry).
    # known_at == time + a constant n-bar offset within each of these two
    # lists (one n per structural_liquidity_points/detect_key_levels
    # call), so sorting by it preserves the same relative order as .time.
    points_sorted = sorted(liquidity_points, key=lambda p: point_known_at(p))
    point_known_ats = [point_known_at(p) for p in points_sorted]
    levels_sorted = sorted(h4_key_levels, key=lambda lvl: level_known_at(lvl))
    level_known_ats = [level_known_at(lvl) for lvl in levels_sorted]

    for i, brk in enumerate(breakouts):
        prev_breakout_time = breakouts[i - 1].time if i > 0 else None
        next_breakout_time = breakouts[i + 1].time if i + 1 < len(breakouts) else None
        retracement_side = "low" if brk.direction == Direction.BULLISH else "high"

        # Only the FIRST qualifying point is ever used, so stop at it
        # rather than materializing every match first.
        liquidity_point = None
        for idx in range(bisect.bisect_right(point_known_ats, brk.time), len(points_sorted)):
            p = points_sorted[idx]
            if next_breakout_time is not None and point_known_at(p) >= next_breakout_time:
                break
            if p.kind == retracement_side:
                liquidity_point = p
                break
        if liquidity_point is None:
            continue

        # Bounded to the CURRENT structural leg (since the previous breakout,
        # any direction), not "every same-direction level in the whole
        # series" -- a level from years before the market's last major
        # direction change was never really "still in play" for this
        # setup. This also keeps the reaction-level search in
        # `_find_entry_candidates()` bounded to a single inter-breakout
        # span instead of, in the worst case, decades of H4 candles --
        # across a multi-year backtest that unbounded version turns into a
        # hang, not just a slowdown (see backtest/README.md's changelog).
        lo = (bisect.bisect_left(level_known_ats, prev_breakout_time)
              if prev_breakout_time is not None else 0)
        hi = bisect.bisect_right(level_known_ats, point_known_at(liquidity_point))
        candidate_levels = [
            lvl for lvl in levels_sorted[lo:hi] if lvl.default_bias == brk.direction
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


def _reaction_trigger(prev: Candle, curr: Candle, direction: Direction) -> str | None:
    """Which confirmation-entry trigger, if any, fires on this (prev, curr)
    pair: engulfing checked first, then 4th-man confirmation -- an
    arbitrary but documented priority for the (rare) case both patterns'
    conditions could coexist on the same candle pair. Returns None if
    neither fires."""
    if is_engulfing(prev, curr, direction):
        return "engulfing"
    fourth_man = fourth_man_confirmation_level(prev, curr)
    if fourth_man is not None and fourth_man.default_bias == direction:
        return "fourth_man"
    return None


def _find_entry_candidates(h1: list[Candle], setups: list[LiquiditySetup]) -> list[EntryCandidate]:
    """For each setup: bounded forward-scan H1 for the sweep of
    `liquidity_price`, then -- "we don't predict, we react" -- try each of
    `reaction_level_candidates` in nearest-to-extreme order, each scanning
    the same bounded REACTION_LOOKAHEAD window from the sweep for a
    genuine touch-and-react (`_reaction_trigger()`: engulfing or 4th-man
    confirmation). The first candidate that actually produces one wins;
    if the nearest candidate never gets touched-and-confirmed, price may
    still run to the next one down the list, with the extreme candidate
    as the last resort. At most one candidate per setup (the first
    qualifying reaction), deduped by H1 index in case two setups converge
    on the same candle."""
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
            found_trigger = None
            for idx in range(sweep_idx + 1, min(sweep_idx + 1 + REACTION_LOOKAHEAD, len(h1))):
                prev, curr = h1[idx - 1], h1[idx]
                touched = (prev.low <= level_price <= prev.high) or (curr.low <= level_price <= curr.high)
                if not touched or idx in seen_indices:
                    continue
                trigger = _reaction_trigger(prev, curr, setup.direction)
                if trigger is not None:
                    found_idx, found_trigger = idx, trigger
                    break
            if found_idx is not None:
                candidates.append(EntryCandidate(found_idx, setup.direction, level,
                                                  setup.liquidity_price, found_trigger))
                seen_indices.add(found_idx)
                break

    return sorted(candidates, key=lambda ec: ec.index)


def _first_sweep_of(h1, from_idx: int, irl_price: float, direction: Direction) -> int | None:
    """Index of the first H1 candle after `from_idx` that actually takes
    the fresh IRL at `irl_price`, or None within IRL_SWEEP_LOOKAHEAD.

    "Swept" is a wick touch, not a close: taking liquidity is price
    trading through the level, which is what the sweep half of the
    strategy means everywhere else (structure.py's sweep detection is
    likewise wick-based -- only the BREAK half is close-based)."""
    end = min(from_idx + 1 + IRL_SWEEP_LOOKAHEAD, len(h1))
    for j in range(from_idx + 1, end):
        c = h1[j]
        if direction == Direction.BULLISH:
            if c.low <= irl_price:
                return j
        elif c.high >= irl_price:
            return j
    return None


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
            stop_hit = c.low <= stop_loss
            target_hit = c.high >= target_price
            # On the candle that actually triggers the stop, cap the adverse
            # excursion at the stop price itself rather than the candle's raw
            # low: a single wide-range (or gapping) candle can undershoot the
            # stop by many multiples of R, but the position is closed the
            # instant the stop is touched, so MAE beyond that point is
            # unobservable, not real -- without this cap mae_r can read as
            # -10R, -28R etc. on a trade whose realized loss is exactly -1R.
            worst = min(worst, stop_loss if stop_hit else c.low)
            best = max(best, c.high)
        else:
            stop_hit = c.high >= stop_loss
            target_hit = c.low <= target_price
            worst = max(worst, stop_loss if stop_hit else c.high)
            best = min(best, c.low)

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
                  pip_size: float | None = None, n: int = 2,
                  start_date=None, end_date=None, rr: float = RISK_REWARD_PRIMARY,
                  erl_cap: bool = True, close_based_breakout: bool = True,
                  confirmation_window: int = BIAS_CONFIRMATION_WINDOW,
                  irl_mode: str = "ignore",
                  avoid_rollover_entries: bool = False,
                  min_reward_r: float | None = None) -> list[TradeRecord]:
    """
    entry_style: "aggressive" | "conservative" (Section 5 -- run both
    separately and compare; this function doesn't mix them in one pass).
    pip_size: defaults to `default_pip_size(instrument)` when not given.
    start_date/end_date: optional pd.Timestamp bounds (inclusive) on which
    trades get RECORDED, by entry time -- NOT a data-loading window. All
    cached history still loads and still drives bias-building, alignment,
    and stacking context (`concurrent_open_positions_at_entry`); open
    positions from before the window still count toward stacking for a
    2026 entry. Narrowing the loaded data itself would silently break all
    of that context, not just trim the output.
    rr: the target risk:reward ratio (STRATEGY.md's "3:1 or 4:1" --
    `trade_management.RISK_REWARD_PRIMARY`, 3.0, by default), still
    ERL-capped on top exactly as at the default ratio.
    erl_cap: when True (default), the target is capped at the nearest
    Daily/Weekly external range liquidity point (see `_nearest_erl()`),
    per the direct user correction recorded in trade_management.py. When
    False, every trade targets a flat `rr` with no cap at all -- for
    comparing the two approaches against each other, not a claim that the
    cap was wrong.
    avoid_rollover_entries: when True, skips any entry whose FINAL candle
    (after any IRL-sweep re-anchoring) falls in the 21:00-23:00 UTC
    session-rollover window (see ROLLOVER_WINDOW_START_HOUR_UTC's
    comment). Defaults to False -- this is a 2026-09-01 candidate fix,
    not yet validated against history; compare against the default
    before trusting it as the new normal, same as irl_mode's other
    experimental variants.
    min_reward_r: when set, skips any entry whose ERL-capped target is
    less than this many R away from entry (reward:risk ratio below the
    threshold) -- direct 2026-09-01 question: "a trade of less than 1R
    doesn't make sense to hold." None (default) applies no minimum,
    matching every trade this engine has ever produced; compare against
    the default before trusting a given threshold as the new normal,
    same as avoid_rollover_entries above.
    close_based_breakout: when True (default), a plain breakout's
    reference level is the swing candle's own CLOSE (line chart), not its
    wick -- direct user correction, matching how A/V-shape key levels
    already work. When False, uses the wick instead (pre-correction
    behavior) -- kept only for comparing the two against each other.
    """
    _reset_sweep_cache()
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
    daily_confirmations = detect_confirmations(daily, n, close_based_breakout=close_based_breakout)
    weekly_confirmations = detect_confirmations(weekly, n, close_based_breakout=close_based_breakout) if weekly else []
    h4_confirmations = detect_confirmations(h4, n, close_based_breakout=close_based_breakout)
    h4_levels = detect_key_levels(h4, n)
    h1_confirmations = detect_confirmations(h1, n, close_based_breakout=close_based_breakout)
    h1_imbalances = detect_imbalances(h1)
    h1_imbalance_times = [im.time for im in h1_imbalances]

    daily_breakpoints = replay_bias(daily, daily_levels, h4_confirmations,
                                     first_origin.direction, "Daily",
                                     confirmation_window=confirmation_window)

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
                                              weekly_first_origin.direction, "Weekly",
                                              confirmation_window=confirmation_window)

    h4_lookup = _direction_lookup(h4_confirmations)
    # Built once here, not per entry candidate -- see _aligned_timeframes().
    alignment_lookups = {
        "Weekly": _direction_lookup(weekly_confirmations),
        "Daily": _direction_lookup(daily_confirmations),
        "H4": h4_lookup,
    }
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

        # Multi-timeframe ALIGNMENT gate -- separate from (and stricter
        # than) the effective-bias check above. "4H can't stand alone if
        # at least the Daily isn't aligned to it": require Daily and H4 to
        # each show their OWN breakout/sweep+break confirming this
        # direction, not just whichever single highest-priority timeframe
        # resolve_effective_bias() picked. Weekly, when it also aligns, is
        # logged but not required -- it's a probability booster, not a
        # gate by itself.
        aligned = _aligned_timeframes(candidate.direction, curr.time,
                                       weekly_confirmations, daily_confirmations, h4_confirmations,
                                       lookups=alignment_lookups)
        if not ("Daily" in aligned and "H4" in aligned):
            continue

        new_key_level = candidate.reaction_level
        following = h1[i + 1: i + 1 + FOLLOWING_LOOKAHEAD]
        classification = classify_entry_pattern(new_key_level, following)
        if classification is None:
            continue

        # "Price moves from IRL to ERL" -- the core of the strategy, and
        # the reason this gate exists at all.
        # FRESH_IRL_REQUIRED means price did NOT come back and tap the
        # level; a fresh internal-range-liquidity candle formed in front
        # of it instead, which per the source "must be swept before
        # continuing". Until that sweep happens the internal liquidity is
        # still sitting there unclaimed, so the move to external liquidity
        # has not actually begun.
        #
        # This used to be gated additionally on an "origin" classification.
        # That gating is gone (direct user correction): markets are
        # fractal, an origin exists inside a continuation, and the label
        # this code computed was really "first trade since the WEEKLY bias
        # last flipped" -- not what the source means, and not something a
        # trader consults before taking the setup. The IRL->ERL sequence,
        # by contrast, applies to EVERY trade, so the gate now does too.
        #
        # The source doesn't state operationally what "must be swept"
        # requires of an entry that hasn't seen it yet, so the response is
        # selectable and the modes are compared on real history:
        #   "ignore" -- take it anyway (the long-standing behavior)
        #   "skip"   -- no formed IRL, no trade
        #   "wait"   -- valid, but only once that IRL is actually swept;
        #               entry shifts to the sweep candle, bounded by
        #               IRL_SWEEP_LOOKAHEAD, and is abandoned if it never
        #               sweeps.
        if (irl_mode != "ignore"
                and classification.pattern is EntryPattern.FRESH_IRL_REQUIRED
                and classification.fresh_irl_price is not None):
            if irl_mode == "skip":
                continue
            swept_idx = _first_sweep_of(h1, i, classification.fresh_irl_price, effective)
            if swept_idx is None:
                continue  # the IRL never got taken -- the setup never completed
            # Re-anchor the entry to the sweep candle. Everything
            # downstream keys off i/curr (stop, target, ERL, imbalance
            # bounds, outcome resolution), so moving them here moves the
            # whole trade rather than just its price.
            i = swept_idx
            prev, curr = h1[i - 1], h1[i]

        if (avoid_rollover_entries
                and ROLLOVER_WINDOW_START_HOUR_UTC <= curr.time.hour < ROLLOVER_WINDOW_END_HOUR_UTC):
            continue

        entry_price = (
            aggressive_entry_price(classification.reference_level)
            if entry_style == "aggressive"
            else conservative_entry_price(curr)
        )

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
        # Bisect the time bound FIRST, then price-test only that slice.
        # Testing every imbalance in the whole H1 history and filtering by
        # time afterwards meant 20.3 MILLION overlaps_level() calls in a
        # single run_backtest -- the largest single cost in the entry loop.
        # The window here (key-level formation -> this entry) is a handful
        # of candles, so the slice is tiny.
        lo_im = bisect.bisect_left(h1_imbalance_times, new_key_level.time)
        hi_im = bisect.bisect_right(h1_imbalance_times, curr.time)
        overlapping = [
            im for im in h1_imbalances[lo_im:hi_im]
            if overlaps_level(im, new_key_level.price)
        ]
        imbalance_overlap = len(overlapping) > 0
        widest_imbalance = max(overlapping, key=lambda im: im.high - im.low, default=None)
        fill_size = widest_imbalance.high - widest_imbalance.low if widest_imbalance else 0.0

        # Stop-loss is keyed to WHICH TRIGGER fired. An earlier version
        # keyed it to an origin/continuation classification instead; see
        # entries.py's module docstring point 5 for the full rationale and
        # the direct user correction this replaced.
        if imbalance_overlap:
            # Plug and play takes priority over the trigger-specific rules
            # below whenever an overlapping imbalance exists, regardless
            # of which trigger geometry also fired on the same candle --
            # this is what "plug and play" actually is. No fallback
            # concept applies here -- the imbalance-anchored stop IS the
            # rule, not a "natural" value that could be overridden.
            stop_loss = imbalance_stop_loss(
                widest_imbalance.low, widest_imbalance.high, effective, pip_size=pip_size
            )
            stop_kind = "plug_and_play"
            trigger_type = "plug_and_play"
            natural_stop_loss = stop_loss
            stop_fallback_used = False
        elif candidate.trigger == "engulfing":
            trigger_type = "engulfing"
            engulfing_extreme = curr.low if effective == Direction.BULLISH else curr.high
            engulfed_extreme = prev.low if effective == Direction.BULLISH else prev.high
            natural = engulfing_stop_loss(engulfing_extreme, engulfed_extreme, effective, pip_size=pip_size)
            natural_stop_loss = natural
            if _natural_stop_too_wide(entry_price, natural, pip_size):
                stop_loss = origin_stop_loss(new_key_level.price, effective, pip_size=pip_size)
                stop_kind = "engulfing_kl_fallback"
                stop_fallback_used = True
            else:
                stop_loss = natural
                stop_kind = "engulfing"
                stop_fallback_used = False
        else:  # candidate.trigger == "fourth_man"
            trigger_type = "fourth_man"
            sweep_extreme = curr.low if effective == Direction.BULLISH else curr.high
            natural = fourth_man_stop_loss(sweep_extreme, effective, pip_size=pip_size)
            natural_stop_loss = natural
            if _natural_stop_too_wide(entry_price, natural, pip_size):
                stop_loss = origin_stop_loss(new_key_level.price, effective, pip_size=pip_size)
                stop_kind = "fourth_man_kl_fallback"
                stop_fallback_used = True
            else:
                stop_loss = natural
                stop_kind = "fourth_man"
                stop_fallback_used = False

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
        # Target is ERL-capped, not a fixed 3:1 (direct user correction --
        # "price wants to go from internal range liquidity to external",
        # capped by the REAL external range liquidity -- Daily/Weekly's own
        # period extremes, not an unconditional ratio). H4 deliberately
        # excluded (it's the cascade's own internal timeframe, not external
        # relative to it -- see _nearest_erl()'s docstring). Weekly may be [].
        raw_target = primary_target(entry_price, stop_loss, effective, rr=rr)
        erl_price = _nearest_erl(effective, entry_price, curr.time, daily, weekly) if erl_cap else None
        target = primary_target(entry_price, stop_loss, effective, rr=rr, erl_price=erl_price)
        erl_capped = target != raw_target

        if min_reward_r is not None:
            risk_distance = abs(entry_price - stop_loss)
            reward_distance = abs(target - entry_price)
            reward_r = (reward_distance / risk_distance) if risk_distance else 0.0
            if reward_r < min_reward_r:
                continue

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

        # Date-range filtering happens HERE, on the finished record, not
        # earlier -- everything above (bias, alignment, IRL sweeps,
        # stacking) must still see the full history regardless of what's
        # actually being reported (see the start_date/end_date docstring
        # above).
        if start_date is not None and curr.time < start_date:
            continue
        if end_date is not None and curr.time > end_date:
            continue

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
            trigger_type=trigger_type,
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
            natural_stop_loss=natural_stop_loss,
            stop_fallback_used=stop_fallback_used,
            raw_target=raw_target,
            erl_price=erl_price,
            erl_capped=erl_capped,
            concurrent_open_positions_at_entry=concurrent,
            exit_price=exit_price,
            exit_reason=exit_reason,
            r_multiple=r_multiple,
            mae_r=mae_r,
            mfe_r=mfe_r,
            status=status,
        ))

    return records


def _utc(ts: pd.Timestamp) -> pd.Timestamp:
    """Cached candle timestamps are tz-aware UTC (the CSV's own ISO
    strings carry a "+00:00" offset, which pandas parses as such) --
    comparing a tz-naive start_date/end_date against curr.time raises
    TypeError (`Cannot compare tz-naive and tz-aware timestamps`), so
    every CLI-supplied date bound must be coerced to UTC before being
    passed to `run_backtest()`. A real bug the first --year run hit:
    `pd.Timestamp(year=..., month=..., day=...)` is naive by default, and
    this codebase's own test fixtures are ALSO naive throughout (see
    test_runner.py), so nothing caught it locally -- only a real
    tz-aware production run did."""
    return ts.tz_localize("UTC") if ts.tzinfo is None else ts.tz_convert("UTC")


def _resolve_date_range(year: int | None, start: str | None, end: str | None):
    """CLI --year/--start/--end -> (start_date, end_date) UTC bounds for
    `run_backtest()`. --year is shorthand for the whole calendar year;
    --end (bare date) is widened to end-of-day so the whole day is
    included, not just its first instant."""
    if year is not None:
        start_date = _utc(pd.Timestamp(year=year, month=1, day=1))
        end_date = _utc(pd.Timestamp(year=year, month=12, day=31, hour=23, minute=59, second=59))
    else:
        start_date = _utc(pd.Timestamp(start)) if start else None
        end_date = _utc(pd.Timestamp(end) + pd.Timedelta(hours=23, minutes=59, seconds=59)) if end else None
    return start_date, end_date


def _parse_rr(value: str) -> float:
    """Accepts a plain multiple ("4") or STRATEGY.md-style ratio notation
    ("3:1", "4:1") -- traders naturally write R:R as a ratio, and GitHub's
    manual workflow_dispatch UI has no input validation to stop it, so a
    bare `type=float` here rejects exactly the input people actually type."""
    text = value.strip()
    if ":" in text:
        left, _, right = text.partition(":")
        return float(left) / float(right)
    return float(text)


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Run the SLK backtest engine against cached candles.")
    parser.add_argument("--instrument", required=True, help="Internal symbol, e.g. EURUSD (see data_pipeline/instruments.py).")
    parser.add_argument("--style", choices=("aggressive", "conservative"), required=True)
    parser.add_argument("--source", default="dukascopy")
    parser.add_argument("--pip-size", type=float, default=None, help="Overrides the per-instrument default (see DEFAULT_PIP_SIZES).")
    parser.add_argument("--out", default=None, help="Output CSV path. Defaults to backtest/results/{instrument}_{style}.csv")
    parser.add_argument("--year", type=int, default=None,
                         help="Only report trades entered in this calendar year. Shorthand for --start YYYY-01-01 --end YYYY-12-31.")
    parser.add_argument("--start", default=None, help="Only report trades entered on/after this date (YYYY-MM-DD).")
    parser.add_argument("--end", default=None, help="Only report trades entered on/before this date (YYYY-MM-DD, inclusive of the whole day).")
    parser.add_argument("--rr", type=_parse_rr, default=None,
                         help=f"Target risk:reward multiple, as a bare number or ratio (STRATEGY.md's '3:1 or 4:1', "
                              f"either '4' or '4:1' both work). Defaults to {RISK_REWARD_PRIMARY:g}.")
    parser.add_argument("--no-erl-cap", action="store_true",
                         help="Disable the external range liquidity target cap -- every trade targets a flat "
                              "--rr instead. For comparing against the (default) ERL-capped behavior.")
    parser.add_argument("--wick-based-breakout", action="store_true",
                         help="Use the swing candle's wick (high/low) as a plain breakout's reference level "
                              "instead of its close (line chart, the default). For comparing against each other.")
    parser.add_argument("--irl-mode", choices=("ignore", "skip", "wait"), default="ignore",
                         help="What to do with an entry whose internal range liquidity formed but hasn't been "
                              "swept yet ('price moves from IRL to ERL'): 'ignore' takes it anyway (default, and "
                              "by a wide margin the best-performing -- see backtest/README.md), 'skip' drops it, "
                              "'wait' re-anchors the entry to the candle that finally sweeps that IRL.")
    args = parser.parse_args()

    start_date, end_date = _resolve_date_range(args.year, args.start, args.end)

    run_kwargs = {"source": args.source, "pip_size": args.pip_size, "start_date": start_date, "end_date": end_date,
                  "erl_cap": not args.no_erl_cap, "close_based_breakout": not args.wick_based_breakout,
                  "irl_mode": args.irl_mode}
    if args.rr is not None:
        run_kwargs["rr"] = args.rr
    records = run_backtest(args.instrument, args.style, **run_kwargs)

    suffix = ""
    if args.year is not None:
        suffix += f"_{args.year}"
    elif args.start or args.end:
        suffix += f"_{args.start or 'start'}_{args.end or 'end'}"
    if args.rr is not None:
        suffix += f"_rr{args.rr:g}"
    if args.no_erl_cap:
        suffix += "_noerlcap"
    if args.wick_based_breakout:
        suffix += "_wickbreakout"
    if args.irl_mode != "ignore":
        suffix += f"_irl{args.irl_mode}"
    out_path = args.out or f"backtest/results/{args.instrument}_{args.style}{suffix}.csv"
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    write_trade_log(records, out_path)

    summary = summarize(records)
    print(f"{args.instrument} ({args.style}): {summary['total_trades']} trades, "
          f"{summary['closed_trades']} closed, win_rate={summary['win_rate']}, "
          f"avg_r={summary['avg_r']}, total_r={summary['total_r']}")
    print(f"Trade log written to {out_path}")


if __name__ == "__main__":
    main()
