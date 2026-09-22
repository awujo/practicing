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
from .timeframes import bar_length, closes_at
from .key_levels import KeyLevel, detect_key_levels, count_tests_before_disrespect, known_at as level_known_at
from .liquidity import single_candle_liquidity, structural_liquidity_points
from .imbalance import detect_imbalances, overlaps_level
from .bias import (detect_confirmations, replay_bias, bias_at, resolve_effective_bias,
                    confirmation_known_at)
from .entries import (
    is_engulfing, fourth_man_confirmation_level, classify_entry_pattern, EntryPattern,
    open_close_disrespect_entry, breakout_entry, sweep_break_entry,
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

# How many post-breakout H4 candles may each supply a single candle
# liquidity pool (liquidity_mode="single_candle"). Every chart sample
# studied had the pool that mattered within a few candles of the
# breakout, and more than one could be live at once -- the JP225 sample
# had two drawn simultaneously. The cap is what keeps the downstream
# sweep/reaction search from growing without bound over pools no trader
# would ever have marked.
SINGLE_CANDLE_LIQUIDITY_MAX_POOLS = 6

# How many qualifying reactions off a setup's winning key level
# `_find_entry_candidates()` may return. More than one because the
# downstream gates (rollover window, alignment, IRL/ERL, zone fill, R:R)
# all run after the pick, so the first reaction being rejected must not
# silently kill the setup. The trade loop still opens at most one trade
# per setup_id.
MAX_CANDIDATES_PER_SETUP = 3

# How many 4H candles after a pool forms to wait for the sweep-and-
# rejection that liquidity_mode="single_candle_h4" requires. 30 H4
# candles is about a trading week -- past that the breakout that created
# the pool is stale enough that a return is a different story.
H4_SWEEP_LOOKAHEAD = 30

# How long a resting entry at a zone's near edge stays live waiting for
# price to come back to it (stop_anchor="zone_entry"). Bishop's deck
# shows the retest happening within the same local move, so this is
# deliberately short -- an order still unfilled well after the setup
# formed is a setup that did not play out, not one still waiting.
ZONE_FILL_LOOKAHEAD = 24

# How long a resting limit is given to fill before it is treated as
# expired, in H1 candles. 48 = two days, comfortably longer than the live
# bot's own 24h staleness window so the backtest is not the tighter of the
# two and cannot make limits look worse than they are.
LIMIT_FILL_LOOKAHEAD = 48

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


def _reaction_leg_extreme(h1, entry_idx: int, direction: Direction, key_level_time,
                           max_lookback: int = REACTION_LOOKAHEAD) -> float | None:
    """The extreme price THIS setup's own reaction leg actually reached --
    the highest high (bearish) / lowest low (bullish) between the key
    level forming and the entry candle inclusive.

    This is the mentor's "the strong high that was actually created"
    (video-13's stop-placement Q&A) expressed as something computable:
    the last structural point holding the idea up. For a short taken on
    a retracement, price closing back above the high that retracement
    made means the "impulsive move continues" thesis is dead; anywhere
    below it, nothing has gone wrong yet.

    Deliberately NOT a pip budget, and deliberately not compared against
    one -- see OPERATIONS_LOG.md 2026-09-01/02. The stop's WIDTH is an
    output of picking this point correctly, never an input: a genuine
    invalidation point is further away on a volatile instrument and
    closer on a quiet one, and both are correct. What is validated
    instead is that the anchor belongs to THIS setup (bounded to the
    key level's own formation, and to `max_lookback` candles) rather
    than to older, unrelated structure -- which is exactly how CHFJPY's
    stop ended up at 198.101 on 2026-09-01, up at the 28 Aug highs,
    while the entire session traded 197.1-197.7."""
    start = max(0, entry_idx - max_lookback)
    window = h1[start: entry_idx + 1]
    if key_level_time is not None:
        scoped = [c for c in window if c.time >= key_level_time]
        if scoped:
            window = scoped
    if not window:
        return None
    if direction == Direction.BULLISH:
        return min(c.low for c in window)
    return max(c.high for c in window)


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
    # "Has this period finished" asked of the period itself, not of
    # whether a SUCCESSOR happens to exist in the data yet.
    #
    # The old test was `series[i + 1].time > as_of_time: break`, using the
    # next bar's existence as a proxy for this one having closed. That is
    # right on full history and wrong at the edge of it: truncate the
    # series at the entry and the last COMPLETE period drops out, because
    # its successor has not started. So an ERL candidate that genuinely
    # existed at entry time was invisible, the target was capped
    # differently, and `min_reward_r` rejected trades that later
    # reappeared once more data arrived.
    #
    # Measured (2026-09-18, synthetic 3-year series): a trade stamped
    # 2025-03-24 15:00 did not exist at T+8h and appeared at exactly
    # T+9h -- midnight, when the entry day's own Daily bar closed and
    # the PREVIOUS day's extreme finally became visible to this function.
    # That is nine hours of a signal's life spent not existing for a
    # reason that has nothing to do with the market.
    #
    # Not a look-ahead -- this direction is over-conservative -- but the
    # same root confusion as review finding 1: a bar's usability is a
    # property of its own close, never of what came after it.
    length = bar_length(series)

    extremes = []
    for i in range(n):
        if closes_at(series[i].time, length) > as_of_time:
            break  # still forming at as_of_time -- not a fixed "previous" reference
        # The SWEEPING period must have closed too, not merely opened.
        #
        # This read `series[sweep_index[i]].time <= as_of_time`, i.e. the
        # sweeper's OPEN. On a Weekly series that lets a sweep be claimed
        # up to seven days before it could possibly be known, and -- worse
        # -- it is not stable: the sweeper does not exist in the data at
        # all until later, so the candidate is present at one moment and
        # retroactively withdrawn at the next.
        #
        # Measured (2026-09-18): weekly extreme 1.68915 was a valid ERL
        # candidate for the 2025-03-24 15:00 entry at T+24h and gone at
        # T+168h, taken by the weekly bar stamped 2025-03-24 -- a bar
        # that opens before the entry and does not close until 03-31.
        # That alone moved the trade's ERL and flipped it through the
        # min_reward_r gate, so the signal kept changing its mind about
        # existing for a week after its own candle.
        #
        # Third instance of review finding 1 in this one function: a
        # period's usability is a property of its own close.
        swept_by = sweep_index[i]
        if swept_by is not None and closes_at(series[swept_by].time, length) <= as_of_time:
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
    """Pre-sorted (known_at times, directions) arrays for O(log n) 'last
    direction KNOWN before time t' queries, built once.

    Keyed on `known_at`, not `.time`: a confirmation belongs to a bar
    that closes after it opens, and every query here comes from a LOWER
    timeframe asking what the higher one had already established. Keying
    on the bar's open is what let an H1 entry at 13:00 be confirmed by an
    H4 bar closing at 16:00 (2026-09-18 review, finding 1).

    The naive version of this --
    filtering the whole confirmation list on every call -- turns an O(n)
    per-candle backtest loop into O(n*m) against a confirmation list that
    can itself run into the thousands for a multi-year H1/H4 series
    (EURUSD's full Dukascopy H1 history is well over 100,000 candles).
    That combination is what makes an un-optimized run of this loop
    genuinely slow rather than fast, so this exists specifically to keep
    a full-history backtest run in the seconds-to-low-minutes range
    instead of many minutes."""
    sorted_confs = sorted(confirmations, key=confirmation_known_at)
    return ([confirmation_known_at(c) for c in sorted_confs],
            [c.direction for c in sorted_confs])


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
    default.

    `liquidity_known_at` is the earliest moment the pool can legitimately
    be swept -- the close of the candle that FORMED it. Scanning for the
    sweep from `liquidity_time` instead (which is that candle's OPEN)
    lets the forming candle count as sweeping its own low, which is not a
    sweep at all: nobody came back for anything. That bug made setups
    look instantly-triggered and burned them before price ever returned.

    `setup_id` identifies the breakout+pool this candidate came from, so
    the trade loop can let a REJECTED candidate fall through to the next
    qualifying reaction from the same setup while still opening at most
    one trade per setup.

    `sweep_from` is where the sweep scan actually starts, which is NOT
    always `liquidity_known_at`. In liquidity_mode="single_candle" it is
    -- that is the fix. In liquidity_mode="swing" it is deliberately set
    back to `liquidity_time`, self-sweep and all, because that mode's
    only job is to reproduce the pre-2026-09-16 entry path exactly so
    the corrected one has an honest baseline to be measured against. A
    baseline that quietly carries half the fix measures nothing."""
    direction: Direction
    breakout_time: object
    liquidity_price: float
    liquidity_time: object
    liquidity_known_at: object
    sweep_from: object
    reaction_level_candidates: list[KeyLevel]
    setup_id: int = 0
    # True when the sweep AND the rejection off the key level were both
    # already confirmed on the 4H (liquidity_mode="single_candle_h4").
    # `_find_entry_candidates()` then skips its own H1 sweep scan and
    # goes straight to looking for the confirmation, because the thing
    # that scan was approximating has already happened, on the timeframe
    # it is actually read on.
    h4_validated: bool = False


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
    setup_id: int = 0


def _pool_known_at(point):
    """When a liquidity pool becomes usable, for either pool type.

    SingleCandleLiquidity carries `known_at` (its forming candle's close);
    a SwingPoint carries `confirmed_at` (formation + n bars), which is
    what `point_known_at()` reads."""
    known = getattr(point, "known_at", None)
    return known if known is not None else point_known_at(point)



def _h4_sweep_and_rejection(h4: list[Candle], pool_price: float, pool_known_at,
                             direction: Direction, levels: list[KeyLevel],
                             lookahead: int = H4_SWEEP_LOOKAHEAD,
                             until=None):
    """Find the 4H candle that sweeps `pool_price` AND rejects off a key
    level, as the operator reads it off the chart.

    "I want to see a 4H candle come and sweep another 4H candle's low...
    and I want to see it react from a key level" -- and separately, on
    what "react" means: "price gets to a KL and on the 4H the candle
    starts rejecting off it as if it is buying. Then the 1H has to give
    us what we want." (2026-09-16, voice, plus a hand drawing of the 4H
    picture beside a zoomed lower-timeframe one.)

    So both events are 4H events, and they are the SAME candle: it wicks
    through the resting low, trades into the level, and closes back out
    of it. Bullish: low <= pool, low <= level, close > level. Bearish
    mirrored.

    The pre-existing path tested neither on 4H. It scanned H1 for any
    hour whose wick dipped below the pool, then for any H1 candle merely
    TOUCHING the level while an engulfing/4th-man fired. "Some hour
    touched this level" is a far weaker claim than "a 4H candle rejected
    off it", and fusing the touch into the confirmation meant the 4H
    rejection was never required at all.

    Returns (sweep_candle, level) or (None, None). The level returned is
    the one price actually rejected from -- not a guess, not the nearest
    by distance."""
    start = bisect.bisect_left([c.time for c in h4], pool_known_at)
    for idx in range(start, min(start + lookahead, len(h4))):
        c = h4[idx]
        if until is not None and c.time >= until:
            # Past the trend change this pool belonged to. A sweep after
            # the 4H has broken the other way is not this setup's sweep.
            break
        if direction == Direction.BULLISH:
            if c.low > pool_price:
                continue  # the resting low is still untouched
            rejected = [lvl for lvl in levels
                        if c.low <= lvl.price and c.close > lvl.price]
            # Deepest level actually reached and closed back above -- the
            # one price ran furthest into before turning.
            best = min(rejected, key=lambda lvl: lvl.price, default=None)
        else:
            if c.high < pool_price:
                continue
            rejected = [lvl for lvl in levels
                        if c.high >= lvl.price and c.close < lvl.price]
            best = max(rejected, key=lambda lvl: lvl.price, default=None)
        if best is not None:
            return c, best
    return None, None


def _find_liquidity_setups(h4: list[Candle], h4_confirmations, h4_key_levels: list[KeyLevel],
                            n: int = 2, liquidity_mode: str = "single_candle",
                            max_pools: int | None = None
                            ) -> list[LiquiditySetup]:
    """For each confirmed H4 breakout, find the single candle liquidity
    that forms afterward on the retracement side, and every
    same-direction H4 key level price could react from once that
    liquidity is swept, ordered nearest-to-extreme so
    `_find_entry_candidates()` can try them in that order ("we don't
    predict, we react" -- see LiquiditySetup's docstring). A breakout that
    never produces both simply yields no setup -- consistent with Section
    5B's "requires patience, don't force it" guidance.

    `liquidity_mode` selects where the pools come from:

      "single_candle" (default) -- `single_candle_liquidity()`: every
          post-breakout candle leaves its low (bullish) or high (bearish)
          behind as a pool. This is the concept SLK actually means.

      "swing" -- the legacy path, `structural_liquidity_points(h4, n=1)`.
          Kept only so the two can be A/B'd on real history. It is a
          fractal SWING detector, which is a different concept: it needs
          low <= both neighbours, so during a post-breakout pullback of
          higher lows it finds nothing and falls back to the breakout
          candle's own extreme -- a level price has no reason to revisit.
          See `single_candle_liquidity()`'s docstring for the worked
          GBPUSD case where this provably armed the wrong level.

    In "single_candle" mode a breakout yields up to `max_pools` setups,
    not one: the trader's own charts mark several unswept lows at once
    (the JP225 sample had two), and which one price comes back for is not
    knowable in advance. Each gets its own `setup_id` so the trade loop
    can still open at most one trade per pool."""
    if liquidity_mode in ("single_candle", "single_candle_h4"):
        liquidity_points = (single_candle_liquidity(h4, "low")
                            + single_candle_liquidity(h4, "high"))
    elif liquidity_mode == "swing":
        liquidity_points = structural_liquidity_points(h4, n=1)
    elif liquidity_mode == "both":
        # Both forms, because the source says both count.
        #
        # From the "repeating a system that works" video, at 04:30-05:45,
        # while drawing them:
        #
        #   "that's where the fact that I prefer to use single candle
        #    liquidity. You need to know that it's NOT ALL THE TIME your
        #    form of liquidity is going to be a single candle... you can
        #    have another candle like this here as well... a series, not
        #    always the immediate candle... Sometimes it's also going to
        #    be like STRUCTURAL LIQUIDITY... this particular point might
        #    be a V shape K level... this is another form of liquidity
        #    right here."
        #
        # The engine has only ever implemented the structural form, and
        # the 2026-09-16 "single_candle" mode implemented only the other
        # one -- REPLACING structural rather than joining it. That is the
        # likeliest reason it measured worse and got parked: it did not
        # add the missing pools, it swapped one valid set for another.
        #
        # Deliberately a third mode rather than a change to either, so
        # the A/B compares three defined things and the existing numbers
        # stay meaningful.
        liquidity_points = (single_candle_liquidity(h4, "low")
                            + single_candle_liquidity(h4, "high")
                            + structural_liquidity_points(h4, n=1))
    else:
        raise ValueError(f"unknown liquidity_mode: {liquidity_mode!r}")
    breakouts = sorted(h4_confirmations, key=lambda c: c.time)
    setups = []
    next_setup_id = 0
    # (direction, pool candle time) already turned into a setup. Without
    # this, an unbounded window plus continuation breakouts re-emits the
    # same pools once per breakout in the leg.
    emitted_pools: set = set()

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
    points_sorted = sorted(liquidity_points, key=lambda p: _pool_known_at(p))
    point_known_ats = [_pool_known_at(p) for p in points_sorted]
    levels_sorted = sorted(h4_key_levels, key=lambda lvl: level_known_at(lvl))
    level_known_ats = [level_known_at(lvl) for lvl in levels_sorted]

    for i, brk in enumerate(breakouts):
        prev_breakout_time = breakouts[i - 1].time if i > 0 else None
        # The pool window closes when the TREND CHANGES, not at the next
        # breakout of any direction. Operator, 2026-09-16: "all the 4H
        # candles are still valid to be tested as the single candle
        # liquidity low until the trend has changed -- that is, we now
        # have a new 4H breakout to the downside."
        #
        # A same-direction breakout is a continuation of this leg, not
        # the end of it, so it must not close the window. Closing on the
        # next breakout of ANY direction (the previous behavior) threw
        # away every pool formed after a continuation break. Kept as-is
        # for "swing", whose bounds are part of the A/B baseline.
        if liquidity_mode == "swing":
            next_breakout_time = breakouts[i + 1].time if i + 1 < len(breakouts) else None
        else:
            next_breakout_time = next(
                (b.time for b in breakouts[i + 1:] if b.direction != brk.direction), None)
        retracement_side = "low" if brk.direction == Direction.BULLISH else "high"

        # Collect the pools this breakout left behind, oldest first,
        # capped at `max_pools`. In "swing" mode the cap is 1, preserving
        # the legacy first-qualifying-point-only behavior exactly.
        # None = unbounded, which is the rule as stated: every 4H candle
        # in this leg is a candidate, and one being swept without a KL
        # reaction or an H1 confirmation retires that candle, not the
        # setup -- "price can still do its own thing, come down, take
        # that first 4H candle low and still keep selling. The setup is
        # still valid. Maybe the second candle is the thing that will
        # form the truly single candle liquidity." A numeric cap is kept
        # only so the A/B can ask whether bounding it helps.
        if liquidity_mode in ("single_candle", "single_candle_h4", "both"):
            cap = max_pools
        else:
            cap = 1
        breakout_pools = []
        for idx in range(bisect.bisect_right(point_known_ats, brk.time), len(points_sorted)):
            p = points_sorted[idx]
            if next_breakout_time is not None and _pool_known_at(p) >= next_breakout_time:
                break
            if p.kind != retracement_side:
                continue
            # The BREAKOUT CANDLE'S OWN LOW COUNTS. An earlier version of
            # this loop excluded it, on my reasoning that "price has no
            # reason to return to the extreme it just broke away from."
            # That reasoning was wrong, and the operator corrected it
            # directly (2026-09-16): "it must not be the next candle
            # after the breakout -- it might even be the breakout candle
            # low. All we just want to see is, after the breakout, do we
            # have a 4H single liquidity sweep."
            #
            # It was also expensive. The swing path's first qualifying
            # point is very often exactly that low -- on GBPUSD 2026-08-10
            # it was the ONLY low the fractal detector could return --
            # so excluding it meant "single_candle" was not the superset
            # of "swing" I claimed it was. It was a DIFFERENT set with the
            # most-traded pool removed, which is the likeliest reason it
            # scored 0.25 R/trade against swing's 0.79 at every cap.
            if (brk.direction, p.time) in emitted_pools:
                # Same leg reached through a continuation breakout. The
                # pool is the same pool; emitting it twice would multiply
                # the setup count by the number of continuation breaks
                # without adding a single new candidate.
                continue
            emitted_pools.add((brk.direction, p.time))
            breakout_pools.append(p)
            if cap is not None and len(breakout_pools) >= cap:
                break
        if not breakout_pools:
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

        for liquidity_point in breakout_pools:
            known = _pool_known_at(liquidity_point)
            hi = bisect.bisect_right(level_known_ats, known)
            candidate_levels = [
                lvl for lvl in levels_sorted[lo:hi] if lvl.default_bias == brk.direction
            ]
            if not candidate_levels:
                continue

            if liquidity_mode == "single_candle_h4":
                # Both halves must be visible on the 4H: the candle that
                # takes the resting low is the same candle that trades
                # into a key level and closes back out of it. No 4H
                # rejection, no setup -- rather than falling back to
                # "whichever level is nearest", which is what the other
                # modes do and is not a claim about price at all.
                sweep_candle, level = _h4_sweep_and_rejection(
                    h4, liquidity_point.price, known, brk.direction, candidate_levels,
                    until=next_breakout_time)
                if sweep_candle is None:
                    continue
                setups.append(LiquiditySetup(
                    direction=brk.direction, breakout_time=brk.time,
                    liquidity_price=liquidity_point.price,
                    liquidity_time=liquidity_point.time,
                    liquidity_known_at=known,
                    # The confirmation is looked for from the START of the
                    # rejecting 4H candle, not after it closes: the whole
                    # point of dropping to a lower timeframe is to catch
                    # the turn as it happens, and the operator's own
                    # drawing puts the 4H picture and the zoomed one side
                    # by side, not one after the other.
                    sweep_from=sweep_candle.time,
                    reaction_level_candidates=[level],
                    setup_id=next_setup_id,
                    h4_validated=True,
                ))
                next_setup_id += 1
                continue

            reaction_level_candidates = sorted(
                candidate_levels, key=lambda lvl: abs(lvl.price - liquidity_point.price)
            )

            setups.append(LiquiditySetup(
                direction=brk.direction, breakout_time=brk.time,
                liquidity_price=liquidity_point.price,
                liquidity_time=liquidity_point.time,
                liquidity_known_at=known,
                # From the pool's CLOSE, so the candle that FORMS a low
                # cannot also count as taking it. "swing" keeps the pivot
                # time only because it is the frozen pre-2026-09-16
                # baseline; "both" mixes pool sources and so must use the
                # correct rule rather than the grandfathered one.
                sweep_from=(known if liquidity_mode in ("single_candle", "both")
                            else liquidity_point.time),
                reaction_level_candidates=reaction_level_candidates,
                setup_id=next_setup_id,
            ))
            next_setup_id += 1

    return setups


# The trigger set that has always shipped. "engulfing" here is
# `is_engulfing()`, a classic candlestick engulfing.
TRIGGERS_SHIPPED = ("engulfing", "fourth_man")

# What the videos actually teach. "engulfing" in the source material is
# not a candlestick engulfing at all -- it is a key level that price has
# CLOSED THROUGH, which then flips polarity and is traded from the other
# side. Three independent statements, and the operator confirmed the
# reading in his own words:
#
#   "You also have your engulfed open close key level. You want to see
#   price close above this key level. And then you now want to see price
#   come into this level and then buy to the upside."
#                                     bishop-repeating-system t=195-210
#
#   "You can also use an engulfing, that's an engulfed open close key
#   level."                                   bishop-what-next t=390
#
# See knowledge-base/STRATEGY_VS_IMPLEMENTATION.md, "Confirmation entry
# triggers", for the full citation list.
#
# All four Bishop enumerates, in the order he rates them. The breakout
# and sweep+break come first because he puts them there: "if you ask me
# which ones are likely best, personally I would tell you these two ...
# if you have these two, [missing it] is a missed entry"
# (bishop-entries-part5 t=420-435).
#
# They were specified off the full-resolution frames where he draws both
# side by side -- see SLK_SPEC.md 5.4 and 5.5. The reference broken is
# the MINOR SWING the reaction created, not the key level; that is only
# visible in the frame, where he marks it at 1.86789 against a key level
# at 1.86700.
#
# Entry timeframe stays H1. The ladder written on his chart is
# H3/H2/H1/M45/M30/M5, but H1 only is a deliberate scope decision
# (operator, 2026-09-19: "for now we can use only 1H"), not an
# oversight.
TRIGGERS_TAUGHT = ("sweep_break", "breakout", "open_close", "fourth_man")


def _reaction_trigger(candles: list[Candle], idx: int, direction: Direction,
                      triggers: tuple[str, ...] = TRIGGERS_SHIPPED) -> str | None:
    """Which confirmation-entry trigger, if any, fires at `idx`.

    Checked in the order `triggers` lists them, so the caller's ordering
    is the priority for the (rare) case two patterns' conditions coexist
    on the same candle pair. Returns None if none fires.

    Takes the whole series rather than a (prev, curr) pair because
    `open_close_disrespect_entry()` needs to look BACK for the key level
    that was disrespected -- the pattern spans more than two candles by
    definition."""
    prev, curr = candles[idx - 1], candles[idx]
    for name in triggers:
        if name == "engulfing":
            if is_engulfing(prev, curr, direction):
                return "engulfing"
        elif name == "open_close":
            if open_close_disrespect_entry(candles, idx, direction) is not None:
                return "open_close"
        elif name == "breakout":
            if breakout_entry(candles, idx, direction):
                return "breakout"
        elif name == "sweep_break":
            if sweep_break_entry(candles, idx, direction):
                return "sweep_break"
        elif name == "fourth_man":
            fourth_man = fourth_man_confirmation_level(prev, curr)
            if fourth_man is not None and fourth_man.default_bias == direction:
                return "fourth_man"
        else:
            raise ValueError(f"unknown confirmation trigger {name!r}")
    return None


# Triggers whose geometry puts the confirmation AWAY from the key level,
# so a per-candle touch test cannot see them.
AWAY_FROM_LEVEL_TRIGGERS = frozenset({"breakout", "sweep_break"})


def resolve_reaction_gate(triggers: tuple[str, ...]) -> str:
    """Which touch gate a trigger set needs, when the caller has not said.

    Derived rather than defaulted, because the wrong pairing fails
    SILENTLY: `breakout` under a per-candle gate simply never produces a
    trade, and the A/B would have read as "the taught triggers find
    fewer setups" when the truth is that two of them were switched off
    by a condition their own geometry cannot satisfy."""
    return "window" if AWAY_FROM_LEVEL_TRIGGERS & set(triggers) else "candle"


def _find_entry_candidates(h1: list[Candle], setups: list[LiquiditySetup],
                            max_per_setup: int = MAX_CANDIDATES_PER_SETUP,
                            triggers: tuple[str, ...] = TRIGGERS_SHIPPED,
                            reaction_gate: str | None = None
                            ) -> list[EntryCandidate]:
    """For each setup: bounded forward-scan H1 for the sweep of
    `liquidity_price`, then -- "we don't predict, we react" -- try each of
    `reaction_level_candidates` in nearest-to-extreme order, each scanning
    the same bounded REACTION_LOOKAHEAD window from the sweep for a
    genuine touch-and-react (`_reaction_trigger()`: engulfing or 4th-man
    confirmation). The first LEVEL that actually produces a reaction wins;
    if the nearest level never gets touched-and-confirmed, price may still
    run to the next one down the list, with the extreme level as the last
    resort.

    From that winning level this returns up to `max_per_setup` reactions,
    not just the first. The first one is not necessarily the one that
    gets traded: every downstream gate in the trade loop (bias re-check
    at entry time, alignment, IRL/ERL, the rollover window, zone fill,
    R:R) runs AFTER this function has already picked, so a rejected first
    pick used to kill the whole setup even when price went on to give
    another clean reaction off the same pool minutes later. USDCHF
    2026-09-15 is the case that exposed it: the single candidate was an
    engulfing at 22:00, thrown out by `avoid_rollover_entries` because
    22:00 is the rollover hour, while two genuine 4th-man reactions off
    the same 0.81842 level followed at 04:00->05:00 and 05:00->06:00 the
    next morning -- inside the window, never looked at.

    Every candidate carries its `setup_id`, and the trade loop opens at
    most one trade per setup_id. So this widens WHICH reaction a setup
    may be traded on; it does not let one setup produce several trades.

    Deduped by H1 index so two setups converging on the same candle
    cannot both claim it."""
    times = [c.time for c in h1]
    if reaction_gate is None:
        reaction_gate = resolve_reaction_gate(triggers)
    candidates: list[EntryCandidate] = []
    seen_indices: set[int] = set()

    for setup in setups:
        # From the pool's CLOSE, not its open. Starting at
        # `liquidity_time` puts the scan inside the very candle that
        # formed the low, so that candle trivially "sweeps" its own low
        # and the setup fires on a sweep that never happened -- nobody
        # came back for anything. Verified on USDCHF 2026-09-15: a pool
        # at 0.81781 formed by the 21:00 candle was recorded as swept by
        # that same 21:00 candle, while the next 18 candles never got
        # closer than 0.81791.
        start_idx = bisect.bisect_left(times, setup.sweep_from)

        if setup.h4_validated:
            # The sweep and the rejection off the level were both already
            # established on the 4H. Re-deriving the sweep from H1 here
            # would only re-approximate what is already known, and could
            # disagree with it.
            sweep_idx = start_idx
        else:
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
            found: list[EntryCandidate] = []
            touched_yet = False
            for idx in range(sweep_idx + 1, min(sweep_idx + 1 + REACTION_LOOKAHEAD, len(h1))):
                prev, curr = h1[idx - 1], h1[idx]
                touches_now = ((prev.low <= level_price <= prev.high)
                               or (curr.low <= level_price <= curr.high))
                touched_yet = touched_yet or touches_now
                # "candle": the trigger candle itself must span the level.
                # "window": price must have REACHED the level at some point
                # in this window, and the confirmation may come later.
                #
                # The distinction is not cosmetic, and getting it wrong
                # silently disables triggers rather than failing. A
                # breakout (SLK_SPEC 5.4) closes beyond the minor swing
                # high, which is ABOVE the key level -- so the break
                # candle does not span the level and never will. Under
                # "candle" the pattern fires and the gate throws it away:
                # measured on a synthetic leg, breakout_entry() returned
                # True at the break while the gate returned False.
                #
                # The taught sequence is reach the level, react, THEN
                # confirm on the lower timeframe. "window" is that
                # reading. "candle" stays the default so the shipped
                # two-candle triggers, which are at-the-level patterns by
                # construction, measure exactly as they always have.
                gate = touched_yet if reaction_gate == "window" else touches_now
                if not gate or idx in seen_indices:
                    continue
                trigger = _reaction_trigger(h1, idx, setup.direction, triggers)
                if trigger is not None:
                    found.append(EntryCandidate(idx, setup.direction, level,
                                                setup.liquidity_price, trigger,
                                                setup.setup_id))
                    seen_indices.add(idx)
                    if len(found) >= max_per_setup:
                        break
            if found:
                candidates.extend(found)
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


def _entry_zone(imbalances, imbalance_times, key_level_time, entry_time,
                 entry_price: float, direction: Direction):
    """The imbalance zone THIS entry is taken from -- the one whose NEAR
    edge the entry sits at, per Bishop's chart deck (every example:
    entry at the zone's near edge, stop at its far edge).

    Selection, not invention:
    - bounded in time to this setup's own window (key level formation ->
      entry candle), the same bound the plug-and-play imbalance search
      already uses;
    - the zone must lie BEHIND entry (below it for a long, above for a
      short) -- that is the risk side, the pink zone in the deck;
    - among those, the one whose near edge is closest to entry_price,
      since the deck consistently shows entry sitting ON that edge.

    Deliberately NOT `overlaps_level(im, new_key_level.price)`. That is
    what the first version of this reused, and it silently reduced the
    whole rule to plug-and-play: an imbalance overlapping the KEY LEVEL
    is exactly the condition that already labels a trade
    "plug_and_play", so the A/B (2026-09-02, run 33574694823) came back
    with `{'plug_and_play_zone': 533}` and 80.2% of setups skipped --
    measuring "take only plug-and-play trades", not the deck's rule. In
    the deck the zone sits at the ENTRY, which need not overlap the
    level at all."""
    lo = bisect.bisect_left(imbalance_times, key_level_time)
    hi = bisect.bisect_right(imbalance_times, entry_time)
    best = None
    best_distance = None
    for im in imbalances[lo:hi]:
        if direction == Direction.BULLISH:
            if im.low > entry_price:      # zone must sit below a long's entry
                continue
            near_edge = min(im.high, entry_price)
        else:
            if im.high < entry_price:     # zone must sit above a short's entry
                continue
            near_edge = max(im.low, entry_price)
        distance = abs(near_edge - entry_price)
        if best_distance is None or distance < best_distance:
            best, best_distance = im, distance
    return best


def _zone_edges(zone, direction: Direction) -> tuple[float, float]:
    """(near_edge, far_edge) of a zone for a trade in `direction`.

    Per Bishop's deck the entry rests on the near edge -- the one price
    reaches first coming back into the zone -- and the stop sits just
    past the far edge. For a long the zone is below entry, so its near
    edge is its HIGH and its far edge its LOW; mirrored for a short."""
    if direction == Direction.BULLISH:
        return zone.high, zone.low
    return zone.low, zone.high


def _first_touch(h1, from_idx: int, price: float, direction: Direction,
                  max_lookahead: int) -> int | None:
    """Index of the first candle after `from_idx` whose range reaches
    `price` -- i.e. where a resting order at that price would fill.

    Wick-based, matching `_first_sweep_of()`: taking a level is price
    trading through it, which is what the sweep half of this strategy
    means everywhere else."""
    end = min(from_idx + 1 + max_lookahead, len(h1))
    for j in range(from_idx + 1, end):
        c = h1[j]
        if direction == Direction.BULLISH:
            if c.low <= price:
                return j
        elif c.high >= price:
            return j
    return None


def _resting_limit_outcome(h1, trigger_idx: int, entry_price: float, stop_loss: float,
                            target: float, direction: Direction, max_lookahead: int,
                            cancel_at_target_fraction: float | None,
                            min_departure_r: float = 0.0):
    """Simulate a limit resting at `entry_price` from the trigger candle on.

    Returns (fill_idx, cancel_reason). Exactly one is set: an int index
    where the order filled, or a string saying why it never did.

    This is what the live bot actually does under
    `--entry-order-type limit`, and modelling it is what lets the
    cancellation threshold be measured rather than guessed. Without it the
    engine opens every position at the exact computed price on the trigger
    candle, which is neither the market orders nor the limit orders that
    live code sends, and which flatters tight stops throughout.

    Order of checks inside one candle matters. The fill is tested FIRST:
    for a correctly-ordered long the entry sits above the stop, so a
    candle falling far enough to touch the stop has already traded through
    the entry, and treating that as "cancelled" would silently drop trades
    that really did fill and then lose. Resolving the loss is the honest
    outcome; `_resolve_trade_outcome()` then handles it with the same
    stop-before-target convention used everywhere else.
    """
    reward = abs(target - entry_price)

    # `min_departure_r`: price must first travel this many R AWAY from the
    # entry (in the trade's favour) before a touch counts as a fill.
    #
    # Straight from the source material. Page 6 of Bishop's deck is a
    # broker screenshot of a resting BUY LIMIT at 0.93193 while the market
    # reads 0.93330 -- the order sits ~14 pips BELOW price, unfilled,
    # waiting for a pullback to a level price has already left. Ours rests
    # at the key level the confirmation just formed at, where price still
    # is: measured, 93% of fills land on the very next candle after a
    # median departure of under 2 pips. That is not a retest, it is a
    # market order with a limit's label.
    #
    # 0.0 (default) keeps the old behavior: any touch fills.
    risk = abs(entry_price - stop_loss)
    departed = min_departure_r <= 0 or not risk
    departure_level = (entry_price + min_departure_r * risk
                       if direction == Direction.BULLISH
                       else entry_price - min_departure_r * risk)

    achieved_at = None
    if cancel_at_target_fraction is not None and reward:
        achieved_at = (entry_price + cancel_at_target_fraction * reward
                       if direction == Direction.BULLISH
                       else entry_price - cancel_at_target_fraction * reward)

    end = min(trigger_idx + 1 + max_lookahead, len(h1))
    for j in range(trigger_idx + 1, end):
        c = h1[j]
        if direction == Direction.BULLISH:
            if not departed and c.high >= departure_level:
                departed = True
            if departed and c.low <= entry_price:
                return j, None
            if achieved_at is not None and c.high >= achieved_at:
                return None, "target_achieved_unfilled"
        else:
            if not departed and c.low <= departure_level:
                departed = True
            if departed and c.high >= entry_price:
                return j, None
            if achieved_at is not None and c.low <= achieved_at:
                return None, "target_achieved_unfilled"
    return None, "never_filled"


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


def _trim_to_recent_years(candles: list, years: float | None) -> list:
    """The production version of what
    backtest/tools/compare_history_window.py's windowed_loader() only ever
    did to a monkeypatch for testing -- here it's the real behavior.
    Deliberately simpler than the test tool's version: that one added a
    `recent_days` runway specifically so a comparison against full history
    stayed fair for trades near the edge of the tested period. Live
    replay has no such "tested period" to protect -- it always wants the
    trailing `years` ending at the newest candle actually available,
    continuously, forever. `years` of 0/None is a no-op (unbounded)."""
    if not years or not candles:
        return candles
    cutoff = candles[-1].time - pd.Timedelta(days=years * 365)
    return [c for c in candles if c.time >= cutoff]


def _bootstrap_origin(structure_events: list, confirmations: list, origin_kind: str):
    """The first confirmed direction to seed BiasCascade's initial state
    from. See run_backtest()'s own origin_kind docstring for the two
    modes and why "any" exists -- kept as a free function, shared between
    the Daily and Weekly bootstraps, so there is exactly one definition
    of "first confirmed origin," not two that could quietly drift apart."""
    if origin_kind == "any":
        return confirmations[0] if confirmations else None
    return next((e for e in structure_events if e.kind == "valid_sweep_break"), None)


def run_backtest(instrument: str, entry_style: str, source: str = "dukascopy",
                  pip_size: float | None = None, n: int = 2,
                  start_date=None, end_date=None, rr: float = RISK_REWARD_PRIMARY,
                  erl_cap: bool = True, erl_mode: str = "cap",
                  confirmation_triggers: tuple[str, ...] = TRIGGERS_SHIPPED,
                  close_based_breakout: bool = True,
                  confirmation_window: int = BIAS_CONFIRMATION_WINDOW,
                  irl_mode: str = "ignore",
                  avoid_rollover_entries: bool = False,
                  min_reward_r: float | None = None,
                  stop_anchor: str = "trigger_wick",
                  entry_fill: str = "instant",
                  cancel_at_target_fraction: float | None = None,
                  limit_lookahead: int = LIMIT_FILL_LOOKAHEAD,
                  min_departure_r: float = 0.0,
                  origin_kind: str = "sweep_break",
                  close_based_sweep_break: bool = False,
                  liquidity_mode: str = "swing",
                  single_candle_max_pools: int | None = None,
                  max_history_years: dict | None = None) -> list[TradeRecord]:
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
    erl_mode: how the ERL is used when `erl_cap` is on. "cap" (default,
    what ships) takes the nearer of the rr target and the ERL. "target"
    takes the ERL ITSELF, falling back to the rr target when no ERL
    qualifies -- the course's own rule, and the difference only shows on
    trades whose ERL is further than rr, which "cap" truncates to 3R.
    See trade_management.primary_target() for the evidence and
    knowledge-base/STRATEGY_VS_IMPLEMENTATION.md for the citations.
    Measure it against "cap" before promoting it; the `erl_capped` count
    in the trade log says how many trades the choice can possibly touch.
    confirmation_triggers: which confirmation-entry patterns count as a
    reaction at the key level, checked in the order given. Defaults to
    TRIGGERS_SHIPPED, which is what has always run. TRIGGERS_TAUGHT
    swaps the classic candlestick engulfing for the engulfed open-close
    key level the videos actually describe. See those two constants for
    the citations, and note that neither set yet contains the breakout
    and sweep+break confirmations he rates highest.
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
    stop_anchor: which structural point the stop-loss is anchored to.
    "trigger_wick" (default) is the long-standing per-trigger behavior --
    engulfing/4th-man candle wicks, imbalance far edge for plug-and-play,
    with `_natural_stop_too_wide()` swapping in a key-level fallback when
    the result looks wide.
    "zone" is the rule derived from Bishop's own 60-page chart deck (every
    page studied 2026-09-02; ~35 measured trades; zero exceptions): the
    stop is the FAR EDGE OF THE IMBALANCE ZONE the entry is taken from, so
    the stop distance is simply that zone's own height on that instrument
    and timeframe. Applies to EVERY trigger rather than only plug-and-play;
    no width test (observed stops span 3.0-518.9 pips and are all correct);
    and a setup with no identifiable zone is SKIPPED rather than handed a
    meaningless fallback anchor. See the block at the call site.
    "structural" anchors instead to the setup's own reaction-leg extreme
    (`_reaction_leg_extreme()`).
    VERDICT REVISED 2026-09-02. It was first marked "FAILED -- do not
    enable" on median stop widening 9.4 -> 24.3 pips and total R
    2671 -> 2392. Widening was the WRONG criterion to judge it on: the
    operator's standing correction is that pip width is an output, never
    a target, and a separate sweep that same day confirmed wide stops are
    not lower-quality (skipping oversized-confirmation setups lowered
    average R, which is already width-normalized -- see OPERATIONS_LOG).
    Re-measured against the standard actually visible in Bishop's own
    charts -- does the stop clear the whole leg that made the turn, not
    merely the confirmation candle's own wick -- "structural" is the only
    mode that places stops where he places them:

        mode           win%   totalR   avgR   medStop  clears 5-bar leg
        trigger_wick   63.2%   3235.0  1.512     7.3        40.5%
        trigger_only   65.2%   3372.4  1.576     9.9        48.6%
        trigger_skip   67.5%   3122.2  1.692     8.2        46.0%
        structural     64.4%   2929.3  1.364    23.5        92.1%

    (3 locally-cached instruments, aggressive style.) So the placement
    that matches the source material earns ~9% less R here than the
    default. That gap is NOT yet evidence the rule is wrong, because this
    engine is a poor judge of it: entries fill at the exact computed price
    with no fill test (`open_position()` at the trigger candle), and
    targets are a multiple of the stop, so a wider stop is forced to chase
    a proportionally more distant target. Both confounds favour tight
    stops. Resolve the fill model before treating this comparison as
    decisive.
    Direct 2026-09-01/02 correction, from studying the source material
    (see OPERATIONS_LOG.md): SLK stops are not small because small is the
    goal, they are small because a correctly-read invalidation point is
    genuinely close -- the pip count is an OUTPUT, never a target or a
    cap. The default's wick anchors have no structural meaning, and its
    fallback anchors to the level being entered at (on aggressive style,
    the entry price itself -- a 1-pip stop). Live evidence for both:
    CHFJPY stopped at 198.101 while the session traded 197.1-197.7, and
    EURGBP rejected with INVALID_STOPS at a 1-pip stop, same day.
    Compare against the default before trusting it -- and note this
    changes the unit R is measured in, so trade count, win rate and
    average R all move together and none can be read alone.
    close_based_breakout: when True (default), a plain breakout's
    reference level is the swing candle's own CLOSE (line chart), not its
    wick -- direct user correction, matching how A/V-shape key levels
    already work. When False, uses the wick instead (pre-correction
    behavior) -- kept only for comparing the two against each other.
    origin_kind: how the FIRST Daily/Weekly bias direction is bootstrapped,
    before BiasCascade's own flip logic ever runs.
    "sweep_break" (default) requires StructureTracker's specific
    reversal signature -- sweep a prior low/high, then close back through
    the structural level on the other side. Matches every behavior before
    2026-09-13.
    "any" instead accepts the FIRST entry of detect_confirmations()'s own
    merged stream -- a plain breakout (a direct close beyond a prior
    swing extreme, no sweep required) OR a sweep+break, whichever comes
    first. Direct operator question (2026-09-13): SLK's own confirmation
    rule (this module's docstring, point 1) already says "EITHER a plain
    breakout... OR a sweep+break... both are valid" for confirming
    ongoing bias -- run_backtest()'s bootstrap was requiring the stricter
    one for the FIRST bias only, an inconsistency with the engine's own
    stated rule rather than a considered choice (nothing in this file's
    "further MVP simplifications" notes justifies it). A plain breakout
    needs only one swing pivot to exist before it can fire, versus a full
    sweep-then-reversal cycle -- expected to find a confirmed origin much
    more recently for instruments whose current structural leg began as a
    clean breakout rather than a textbook reversal (see
    compare_history_window.py's GBPJPY finding, 2026-09-13: zero trades
    at up to several years of trailing Daily/Weekly history under
    "sweep_break" alone). Compare against the default before trusting it
    as the new normal -- same as every other experimental variant here.
    close_based_sweep_break: a second, separate line-chart-vs-wick
    question found while investigating the one above -- see
    StructureTracker's own close_based_break docstring for the full
    reasoning. False (default) reads the level a sweep+break must close
    beyond off the swing candle's WICK, matching every behavior before
    2026-09-13. True reads it off the swing candle's CLOSE instead,
    matching how close_based_breakout already treats the plain-breakout
    half and the source material's own stated preference for verifying a
    break off the line chart. The sweep itself is unaffected either way
    -- it stays wick-based, since a sweep is legitimately a wick event.
    Compare against the default before trusting it as the new normal.
    liquidity_mode: which ENTRY PATH to run. Two bundles, not one knob.

    "swing" (default) is the path as it ran live before 2026-09-16, kept
    byte-for-byte so the corrected path has an honest baseline: pools
    from `structural_liquidity_points(h4, n=1)`, the sweep scan starting
    at the pool's own open (so the candle that forms a low can "sweep"
    it), and one reaction per setup.

    "single_candle" is the correction, and all three parts of it move
    together because measuring them apart is meaningless -- the
    self-sweep only matters once the pools are the right pools:
      * pools from `single_candle_liquidity()`: the breakout candle and
        every candle after it leaves its low (bullish) or high (bearish)
        behind. The breakout candle's own extreme counts -- operator,
        2026-09-16: "it must not be the next candle after the breakout,
        it might even be the breakout candle low. All we just want to
        see is, after the breakout, do we have a 4H single liquidity
        sweep." This is what SLK's "single candle liquidity" means. The
        swing detector cannot express it -- `is_swing_low` needs the low
        <= both neighbours, so a post-breakout pullback of higher lows
        registers nothing and the search falls back to the breakout
        candle's own extreme, a level price has no reason to revisit.
        See `single_candle_liquidity()` for the worked GBPUSD case.
      * the sweep scan starts at the pool's CLOSE, so a candle can no
        longer take its own low.
      * a setup may offer up to MAX_CANDIDATES_PER_SETUP reactions, so a
        candidate rejected by a downstream gate (rollover window,
        alignment, IRL/ERL, zone fill, R:R) does not kill the setup.
        Still at most one trade per setup.

    The default stays "swing" deliberately. The live bots call this
    function, so flipping the default flips live trading; it flips when
    `backtest/tools/compare_liquidity_modes.py` says the corrected path
    is actually better on real history, and not before.

    MEASURED 2026-09-16, USDCHF, conservative, full history, on the
    REPAIRED cache and with the rule as the operator finally stated it
    (breakout candle counts, no pool cap, leg runs to the opposite
    breakout, sweep and key-level rejection both read on the 4H):

        swing              736 trades  43.2% win  469.8R  0.64 R/trade
        single_candle/all 2290 trades  32.4% win  546.0R  0.24 R/trade
        sc_h4/all         1428 trades  35.2% win  501.1R  0.35 R/trade

    The 4H rejection requirement does real work: against single_candle
    it cut trades 2290 -> 1428 and lifted R/trade 0.24 -> 0.35. It is
    still well short of swing.

    Both new modes beat swing on TOTAL R, and that is the number not to
    be fooled by. This engine does not model spread. USDCHF stops in
    these runs are ~8-15 pips against a ~1.5 pip spread, so roughly
    0.12R per round trip is uncharged. Applying it:

        swing              469.8 - 736*0.12  = 382
        single_candle/all  546.0 - 2290*0.12 = 271
        sc_h4/all          501.1 - 1428*0.12 = 330

    A fixed per-trade cost takes 19% of the edge at 0.64 R/trade and 50%
    at 0.24, so the high-frequency modes' total-R advantage is the most
    fragile figure in the table. The default stays "swing".

    Read this as a measurement of the liquidity rule ON TOP OF the
    current leg structure, not of the rule alone. detect_confirmations
    produces ~11 breakouts in 8 days on EURCHF, including three
    direction changes inside twelve hours on 2026-09-16. Every mode
    inherits that. Swing's advantage may be that arming one pool per
    breakout is accidentally conservative when the leg direction is
    unreliable -- the modes that commit harder to the leg lose more when
    it is wrong. Fix the breakout frequency before trusting any of these
    numbers as a verdict on the liquidity concept.

    single_candle_max_pools: how many post-breakout candles may supply a
    pool in "single_candle" mode. The default of 6 is what produced the
    numbers above and is almost certainly too loose; 1 (the candle
    immediately after the breakout) is what three of the four annotated
    chart samples actually show. Sweep it before concluding anything
    about the mode itself -- an over-permissive cap and a wrong concept
    look identical in a summary row, and only one of them is true here.
    max_history_years: optional {"D": years, "W": years, "H4": years,
    "H1": years} trailing-window cap applied to each granularity's loaded
    candles before any replay begins. None (default) loads everything
    the cache has -- unchanged behavior, and every value on record before
    2026-09-13.

    DO NOT set this from a guess. Each entry must come from
    backtest/tools/compare_history_window.py's escalation search actually
    confirming, for THAT SPECIFIC instrument, that the capped window
    reproduces every trade full history produces in a recent comparison
    period -- confirmed live 2026-09-13 that this varies enormously
    per instrument (2 years for US30/USDJPY/EURJPY/JP225; 8-11 years for
    EURUSD/GBPAUD/GBPJPY/NAS100; GBPNZD never fully converged even at 15
    years and should not be capped at all). See bot/history_windows.json
    for the live values and bot/OPERATIONS_LOG.md (2026-09-13) for the
    full methodology.

    THESE NUMBERS ARE NOT PERMANENT. They were measured against real
    history up to 2026-09-13 and must be re-escalated periodically --
    market structure that develops after that date could plausibly need
    more trailing history than what was confirmed safe on this date, the
    same way GBPJPY needed more than a naive first guess. Re-run the
    escalation search (recommended: every 6 months, or immediately after
    any change to the strategy logic this file implements) rather than
    assuming a value confirmed once stays safe forever.
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

    if max_history_years:
        daily = _trim_to_recent_years(daily, max_history_years.get("D"))
        weekly = _trim_to_recent_years(weekly, max_history_years.get("W"))
        h4 = _trim_to_recent_years(h4, max_history_years.get("H4"))
        h1 = _trim_to_recent_years(h1, max_history_years.get("H1"))

    daily_tracker = StructureTracker(n, close_based_break=close_based_sweep_break)
    daily_structure_events = daily_tracker.run(daily)
    daily_confirmations = detect_confirmations(daily, n, close_based_breakout=close_based_breakout,
                                                close_based_sweep_break=close_based_sweep_break)
    first_origin = _bootstrap_origin(daily_structure_events, daily_confirmations, origin_kind)
    if first_origin is None:
        return []  # no confirmed structure to bootstrap a bias from

    daily_levels = detect_key_levels(daily, n)
    weekly_confirmations = detect_confirmations(
        weekly, n, close_based_breakout=close_based_breakout,
        close_based_sweep_break=close_based_sweep_break) if weekly else []
    h4_confirmations = detect_confirmations(h4, n, close_based_breakout=close_based_breakout,
                                             close_based_sweep_break=close_based_sweep_break)
    h4_levels = detect_key_levels(h4, n)
    h1_confirmations = detect_confirmations(h1, n, close_based_breakout=close_based_breakout,
                                             close_based_sweep_break=close_based_sweep_break)
    # One inference for the whole run rather than per candidate.
    h1_bar_length = bar_length(h1)
    h1_imbalances = detect_imbalances(h1)
    h1_imbalance_times = [im.time for im in h1_imbalances]

    daily_breakpoints = replay_bias(daily, daily_levels, h4_confirmations,
                                     first_origin.direction, "Daily",
                                     confirmation_window=confirmation_window)

    weekly_breakpoints = []
    if weekly:
        weekly_tracker = StructureTracker(n, close_based_break=close_based_sweep_break)
        weekly_structure_events = weekly_tracker.run(weekly)
        weekly_first_origin = _bootstrap_origin(weekly_structure_events, weekly_confirmations, origin_kind)
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

    liquidity_setups = _find_liquidity_setups(h4, h4_confirmations, h4_levels, n,
                                               liquidity_mode=liquidity_mode,
                                               max_pools=single_candle_max_pools)
    # "swing" is the A/B baseline and must behave exactly as the live
    # path did before 2026-09-16, which included taking only the FIRST
    # reaction per setup. The fall-through fix ships with the corrected
    # mode, not with the thing it is being measured against.
    entry_candidates = _find_entry_candidates(
        h1, liquidity_setups,
        max_per_setup=1 if liquidity_mode == "swing" else MAX_CANDIDATES_PER_SETUP,
        triggers=confirmation_triggers,
    )

    mgr = PositionManager()
    records: list[TradeRecord] = []
    trade_id = 0
    # setup_ids that already produced a trade. A setup may now offer
    # several reactions so a rejected one falls through to the next (see
    # `_find_entry_candidates()`), but only the first that survives every
    # gate below is traded -- the rest of that setup's candidates are
    # skipped here.
    traded_setups: set[int] = set()

    for candidate in entry_candidates:
        if candidate.setup_id in traded_setups:
            continue
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
        # When this decision could first have been MADE. classify_entry_
        # pattern() reads up to FOLLOWING_LOOKAHEAD candles past the entry
        # and its answer changes with how many have arrived (one candle
        # gives FRESH_IRL_REQUIRED, three can give NESTED_DISRESPECT, with
        # a different reference level and therefore a different stop and
        # target), so the classification is not settled until the last of
        # them closes. At the end of the series there may be fewer, and
        # then it is settled as soon as what exists has closed.
        #
        # Everything else this loop consults is already bounded at or
        # before the entry candle by the known_at work, so this is the
        # binding constraint. Captured here rather than at the record
        # because `i` can be re-anchored below (irl_mode="wait"), and it
        # is THIS index the classification was read from.
        _settled_idx = min(i + FOLLOWING_LOOKAHEAD, len(h1) - 1)
        signal_known_at = closes_at(h1[_settled_idx].time, h1_bar_length)

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

        # stop_anchor="zone_entry": the COMPLETE mechanism from Bishop's
        # deck, entry and stop taken from the SAME zone rather than one
        # of them in isolation.
        #
        # Run 2 (33575395100) moved only the stop to the zone's far edge
        # and win rate fell 51.7% -> 38.0% while stops genuinely improved
        # (median 9.4 -> 7.7 pips). That is the expected symptom of half
        # a mechanism: a tight stop is only survivable from the entry it
        # was designed around. In every example in the deck the entry
        # RESTS ON THE ZONE'S NEAR EDGE and the stop sits just past the
        # far edge -- one geometry, not two independent choices.
        #
        # So here: entry moves to the near edge, the stop comes from the
        # far edge of that same zone, and the entry must actually FILL --
        # a resting order at the near edge only becomes a trade if price
        # returns to it, so `_first_touch()` gates that and the setup is
        # abandoned if it never does. (The reverted retest-fill work,
        # c662961/3e10422, failed for the mirror-image reason: limit-style
        # entry WITHOUT the matching zone stop.)
        zone_stop = None
        zone_fill_idx = None
        if stop_anchor == "zone_entry":
            zone = _entry_zone(h1_imbalances, h1_imbalance_times,
                                new_key_level.time, curr.time, entry_price, effective)
            if zone is None:
                continue
            near_edge, _far_edge = _zone_edges(zone, effective)
            zone_fill_idx = _first_touch(h1, i, near_edge, effective, ZONE_FILL_LOOKAHEAD)
            if zone_fill_idx is None:
                continue  # price never came back to the zone -- no trade
            entry_price = near_edge
            zone_stop = imbalance_stop_loss(zone.low, zone.high, effective, pip_size=pip_size)

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
        elif candidate.trigger == "open_close":
            # SLK_SPEC 5.2. The stop goes on the wick of the candle that
            # DISRESPECTED the level -- video-14: "stop loss is just
            # going to be a little bit above this particular high" --
            # which is the confirming candle's own extreme, not a
            # two-candle span.
            trigger_type = "open_close"
            natural = origin_stop_loss(
                curr.low if effective == Direction.BULLISH else curr.high,
                effective, pip_size=pip_size)
            natural_stop_loss = natural
            if _natural_stop_too_wide(entry_price, natural, pip_size):
                stop_loss = origin_stop_loss(new_key_level.price, effective, pip_size=pip_size)
                stop_kind = "open_close_kl_fallback"
                stop_fallback_used = True
            else:
                stop_loss = natural
                stop_kind = "open_close"
                stop_fallback_used = False
        elif candidate.trigger in ("breakout", "sweep_break"):
            # SLK_SPEC 5.4/5.5. These two have no candle-wick anchor of
            # their own -- what invalidates them is price going back
            # through the leg the break came out of. That is exactly
            # `_reaction_leg_extreme()`, i.e. the operator's rule:
            # "we are placing it at invalidation zones -- setup
            # invalidation zones" (2026-09-19), Bishop's placement
            # rather than 4th man's fixed pip count.
            trigger_type = candidate.trigger
            anchor = _reaction_leg_extreme(h1, i, effective, new_key_level.time)
            if anchor is None:
                continue
            natural = origin_stop_loss(anchor, effective, pip_size=pip_size)
            natural_stop_loss = natural
            stop_loss = natural
            stop_kind = trigger_type
            stop_fallback_used = False
        elif candidate.trigger == "fourth_man":
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
        else:
            # Loud, not silent. This block used to end in
            # `else:  # candidate.trigger == "fourth_man"`, which caught
            # everything that was not "engulfing" -- so the three
            # triggers added on 2026-09-19/22 were all being labelled
            # fourth_man and given a fourth-man stop derived from a
            # sweep extreme that, for a breakout, does not exist. The
            # trades would have looked fine in the log and measured a
            # stop rule nobody chose.
            raise ValueError(f"no stop rule for trigger {candidate.trigger!r}")

        # stop_anchor="structural": replace whichever anchor the branches
        # above picked with the setup's own reaction-leg extreme, and drop
        # the width test entirely. See `_reaction_leg_extreme()` and
        # OPERATIONS_LOG.md's source study -- the per-trigger wick rules
        # above have no structural meaning (a two-candle wick extreme is
        # not "the strong high that was actually created"), and the
        # `_natural_stop_too_wide()` fallback they lean on anchors to the
        # key level being ENTERED AT, which on aggressive style is the
        # entry price itself and collapses to a 1-pip stop (the live
        # EURGBP INVALID_STOPS rejection, 2026-09-01).
        if stop_anchor == "structural":
            anchor = _reaction_leg_extreme(h1, i, effective, new_key_level.time)
            if anchor is None:
                continue
            stop_loss = origin_stop_loss(anchor, effective, pip_size=pip_size)
            stop_kind = f"{trigger_type}_structural"
            natural_stop_loss = stop_loss
            stop_fallback_used = False

        # stop_anchor="zone": the rule derived from Bishop's own 60-page
        # chart deck (2026-09-02, all 60 pages studied, ~35 measured
        # trades, zero exceptions -- see OPERATIONS_LOG.md). Every example
        # annotates a risk-side zone (pink; grey for one other trader)
        # behind entry and a teal target zone in front. Entry sits at the
        # zone's NEAR edge as a resting limit order, the stop at its FAR
        # edge, the target at the teal zone's far edge -- so the stop
        # distance is simply THE ZONE'S OWN HEIGHT, measured on that
        # instrument and timeframe. Confirmed to the pip by the one page
        # pairing a chart with its broker screenshot (EURCHF: pink zone
        # 0.93147-0.93193, order BUY LIMIT 0.93193 / SL 0.93147).
        #
        # That zone is the imbalance/FVG price returned to rebalance, and
        # `imbalance_stop_loss()` already implements exactly this -- its
        # own docstring even states the invalidation logic ("no logical
        # reason to trade beyond its far edge"). The defect this fixes is
        # SCOPE, not logic: the branches above only reach it via
        # `imbalance_overlap` ("plug_and_play"), leaving every other
        # trigger on candle-wick anchors that have no structural meaning.
        # The deck shows the zone rule applying to engulfing, breakout,
        # breakout-with-idm and 4th-man alike -- it is trigger-independent.
        #
        # No width test: observed stops run 3.0 to 518.9 pips (~170x) and
        # are all correct, because each is just its own zone's height.
        # No zone => no defined invalidation => SKIP the setup rather
        # than substitute a meaningless anchor.
        # stop_anchor="trigger_only": keep each trigger's OWN structural
        # anchor -- engulfing's / 4th-man's candle extreme -- and never
        # substitute the key-level fallback, no width test at all.
        #
        # Added 2026-09-02 after re-reading page 8 of the deck, whose
        # annotation reads "H2 High swept, Low standing V-shaped kl
        # 4thman's CE" with the stop sitting just below that standing
        # low. That is a CANDLE extreme, not a gap edge -- the mentor's
        # own "just below the low, below this particular low" (video-13).
        # Which means the per-trigger anchors already in this file were
        # closer to correct than the zone rule built on top of them, and
        # the real defect is `_natural_stop_too_wide()` swapping in
        # `origin_stop_loss(new_key_level.price)` -- an anchor that on
        # aggressive style IS the entry price (the live EURGBP 1-pip
        # INVALID_STOPS rejection). This isolates exactly that.
        if stop_anchor == "trigger_only":
            stop_loss = natural_stop_loss
            stop_kind = f"{trigger_type}_natural"
            stop_fallback_used = False

        # stop_anchor="trigger_skip": same natural anchor as "trigger_only",
        # but a setup whose anchor comes out too wide is SKIPPED rather than
        # traded on a substituted stop. The substitution has no structural
        # meaning at any width, so the choice when the real anchor is
        # unusable is to decline the setup -- the same stance `zone` already
        # takes when no zone can be identified.
        if stop_anchor == "trigger_skip":
            if _natural_stop_too_wide(entry_price, natural_stop_loss, pip_size):
                continue
            stop_loss = natural_stop_loss
            stop_kind = f"{trigger_type}_natural"
            stop_fallback_used = False

        if stop_anchor == "zone_entry":
            stop_loss = zone_stop
            stop_kind = f"{trigger_type}_zone_entry"
            natural_stop_loss = stop_loss
            stop_fallback_used = False

        if stop_anchor == "zone":
            zone = _entry_zone(h1_imbalances, h1_imbalance_times,
                                new_key_level.time, curr.time, entry_price, effective)
            if zone is None:
                continue
            stop_loss = imbalance_stop_loss(
                zone.low, zone.high, effective, pip_size=pip_size
            )
            stop_kind = f"{trigger_type}_zone"
            natural_stop_loss = stop_loss
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
        target = primary_target(entry_price, stop_loss, effective, rr=rr, erl_price=erl_price,
                                erl_mode=erl_mode)
        erl_capped = target != raw_target

        if min_reward_r is not None:
            risk_distance = abs(entry_price - stop_loss)
            reward_distance = abs(target - entry_price)
            reward_r = (reward_distance / risk_distance) if risk_distance else 0.0
            if reward_r < min_reward_r:
                continue

        test_count, _ = count_tests_before_disrespect(h1[i + 1: i + 1 + QMR_LOOKAHEAD], new_key_level)

        # A zone_entry trade opens when its resting order actually fills,
        # which is a LATER candle than the trigger -- so the trade's own
        # timeline (when it opened, and from where stop/target are
        # resolved) starts there, not at the trigger. Every other mode
        # keeps entry_idx == i and behaves exactly as before.
        # entry_fill="limit": the order rests at entry_price and the trade
        # only exists if price comes back to it -- the live bot's own
        # behavior under --entry-order-type limit. A setup whose move
        # happened without us, or which never returned, produces NO trade
        # rather than a free fill at a price nobody could have got.
        # entry_fill="market_close": what a real market order actually
        # gets -- the trigger candle's close, not the level the strategy
        # named. The default "instant" fills at entry_price itself, which
        # for aggressive style is the KEY LEVEL: price has usually just
        # reacted away from it by the time the confirmation candle closes,
        # so that fill was never obtainable by any order type. Comparing
        # limits against it is comparing them against a fantasy.
        if entry_fill == "market_close":
            entry_price = curr.close
            if not _stop_on_correct_side(entry_price, stop_loss, effective):
                continue
            risk_distance = abs(entry_price - stop_loss)
            if not risk_distance:
                continue
            target = (entry_price + rr * risk_distance if effective == Direction.BULLISH
                      else entry_price - rr * risk_distance)
            if erl_cap and erl_price is not None:
                # `erl_price` was found relative to the PRE-shift entry, so
                # after moving the entry to the trigger's close it can land
                # behind us. Capping handles that harmlessly (min/max keeps
                # the nearer of two points ahead); using it AS the target
                # would put the target on the wrong side of the entry, so
                # fall back to the plain rr target when it is no longer
                # beyond us.
                still_ahead = (erl_price > entry_price if effective == Direction.BULLISH
                               else erl_price < entry_price)
                if erl_mode == "target":
                    target = erl_price if still_ahead else target
                else:
                    target = (min(target, erl_price) if effective == Direction.BULLISH
                              else max(target, erl_price))

        limit_cancel = None
        if entry_fill == "limit":
            fill_idx, limit_cancel = _resting_limit_outcome(
                h1, i, entry_price, stop_loss, target, effective,
                limit_lookahead, cancel_at_target_fraction, min_departure_r)
            if limit_cancel is not None:
                continue
            zone_fill_idx = fill_idx

        entry_idx = i if zone_fill_idx is None else zone_fill_idx
        entry_candle = h1[entry_idx]

        traded_setups.add(candidate.setup_id)
        concurrent = len(mgr.open_positions(effective))
        pos = mgr.open_position(effective, entry_price, stop_loss, entry_candle.time, "H1", target)

        exit_reason, exit_price, exit_time, mae_r, mfe_r = _resolve_trade_outcome(
            entry_price, stop_loss, target, effective,
            h1[entry_idx + 1: entry_idx + 1 + MAX_TRADE_DURATION_CANDLES]
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
            entry_time=entry_candle.time,
            signal_time=curr.time,
            signal_known_at=signal_known_at,
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
    parser.add_argument("--taught-triggers", action="store_true",
                         help="use the confirmation triggers the videos describe "
                              "(engulfed open-close key level + 4th man) instead of the "
                              "classic candlestick engulfing that has always shipped. "
                              "A strategy change: measure it before trusting it.")
    parser.add_argument("--erl-as-target", action="store_true",
                         help="Use the external range liquidity point AS the target rather than as a cap on "
                              "--rr, falling back to --rr only when no ERL qualifies. This is what the course "
                              "videos teach; the shipped default truncates those trades to --rr.")
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
                  "erl_mode": "target" if args.erl_as_target else "cap",
                  "confirmation_triggers": TRIGGERS_TAUGHT if args.taught_triggers else TRIGGERS_SHIPPED,
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
    if args.erl_as_target:
        suffix += "_erltarget"
    if args.taught_triggers:
        suffix += "_taughttriggers"
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
