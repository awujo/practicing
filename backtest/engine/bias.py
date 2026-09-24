"""
Top-down bias cascade + bias-flip state machine -- STRATEGY.md Section 2,
the master algorithm everything else in the strategy hangs off of.

Two pieces:

1. `detect_confirmations()` -- Video 16's confirmation-detection rule:
   scaling down from a higher-timeframe key-level reaction, EITHER a
   plain breakout (a direct close beyond a prior swing extreme, no prior
   sweep-and-reverse -- the MORE common pattern) OR a sweep+break of
   structure (Phase 1's StructureTracker: sweep first, then close-through
   -- the LESS common, "textbook" pattern) confirms directional order
   flow. Both are valid; a confirmation check should accept either shape.

2. `BiasCascade` -- the 3-condition bias-flip state machine (Video 16,
   completed by Video 17). A bias is considered FLIPPED only when ALL of:
     (a) price trades into the next key level on the bias's ORIGIN
         timeframe,
     (b) price rejects from it and closes in the NEW (opposite)
         direction,
     (c) AND the next lower timeframe ALSO stops confirming the ORIGINAL
         direction (no further breakout or sweep+break in the old
         direction).
   If (b) happens but the lower timeframe still confirms the OLD
   direction, the bias is NOT flipped -- this is Video 16's resolved
   ambiguity: a single higher-timeframe reaction never flips a bias by
   itself. Critically (Video 17): condition (c) can ONLY be satisfied by
   a breakout or sweep+break -- an open-close break or plain engulfing
   (Phase 2's key_levels.py disrespect logic) NEVER counts toward a bias
   flip, no matter how convincing it looks. Those remain valid ENTRY
   triggers within the still-active bias (Section 5), just not
   bias-change signals.

Also implements the strict priority hierarchy confirmed at every level:
Weekly > Daily > 4H > lower timeframes. A lower timeframe's bias that
conflicts with a higher one isn't a reversal -- it's the "induced-move
trap": treated as retracement/inducement to fade, not adopted.
"""

import bisect
from dataclasses import dataclass
from enum import Enum

from .candles import Candle
from .structure import Direction, StructureTracker, body_closes_beyond, is_swing_high, is_swing_low
from .key_levels import KeyLevel, is_disrespected, known_at as level_known_at
from .timeframes import bar_length, closes_at


class ConfirmationKind(Enum):
    BREAKOUT = "breakout"
    SWEEP_BREAK = "sweep_break"


@dataclass(frozen=True)
class Confirmation:
    """`time` is the OPEN of the candle that produced the confirmation.
    `known_at` is when that candle CLOSED, which is the first moment this
    confirmation can legitimately influence anything.

    The two are not interchangeable and conflating them was the engine's
    single largest bug (2026-09-18 review, finding 1): an H1 entry at
    13:00 was being confirmed by an H4 bar stamped 12:00 that did not
    close until 16:00, a Daily bar that closed at midnight, and a Weekly
    bar that closed the following Monday. Any consumer asking "was this
    confirmed by now" must read `known_at`; `.time` remains the
    confirmation's identity and what you point at on a chart."""
    time: object
    direction: Direction
    kind: ConfirmationKind
    price: float
    known_at: object = None


def confirmation_known_at(confirmation: Confirmation):
    """When a confirmation becomes usable. Falls back to `.time` for
    Confirmations built without a `known_at` -- hand-built test fixtures,
    mostly -- which is the pre-fix reading and deliberately the unsafe
    one, so production paths must always populate it."""
    return confirmation.known_at if confirmation.known_at is not None else confirmation.time


def detect_confirmations(candles: list[Candle], n: int = 2, close_based_breakout: bool = True,
                          close_based_sweep_break: bool = False) -> list[Confirmation]:
    """Merge plain breakouts and sweep+break-of-structure events into one
    confirmation stream, each tagged with which visual pattern it was.

    close_based_breakout: when True (default), a plain breakout's
    reference level is the swing candle's own CLOSE, matching how SLK
    reads breakouts off the line chart throughout (direct user
    correction) -- the same convention A/V-shape key levels already use.
    When False, the level is the swing candle's wick extreme instead (the
    pre-correction behavior) -- kept only so the two can be compared
    against each other, not because the wick-based reading is preferred.

    close_based_sweep_break: the SAME line-chart-vs-wick question, but
    for the sweep+break half instead of the plain-breakout half -- see
    StructureTracker's own close_based_break docstring. False (default)
    matches every behavior before 2026-09-13."""
    # Every confirmation below is produced BY a candle, and is knowable
    # only once that candle closes -- see Confirmation's docstring.
    length = bar_length(candles)

    tracker = StructureTracker(n, close_based_break=close_based_sweep_break)
    sweep_events = [e for e in tracker.run(candles) if e.kind == "valid_sweep_break"]
    sweep_break_keys = {(e.time, e.direction) for e in sweep_events}

    confirmations = [
        Confirmation(e.time, e.direction, ConfirmationKind.SWEEP_BREAK, e.price,
                     known_at=closes_at(e.time, length))
        for e in sweep_events
    ]

    swing_high_idxs = {i for i in range(len(candles)) if is_swing_high(candles, i, n)}
    swing_low_idxs = {i for i in range(len(candles)) if is_swing_low(candles, i, n)}

    last_swing_high = None
    last_swing_low = None
    claimed_high = False
    claimed_low = False

    for i, c in enumerate(candles):
        # A pivot at (i - n) only becomes fractally confirmable HERE, at
        # index i -- not at (i - n) itself, which is what `i in
        # swing_high_idxs` did before (2026-08-28 fix; a real ~n-bar
        # lookahead, see OPEN_QUESTIONS.md). The reference level is still
        # the pivot candle's own price; only when it becomes usable moves.
        if i - n in swing_high_idxs:
            last_swing_high = candles[i - n]
            claimed_high = False
        if i - n in swing_low_idxs:
            last_swing_low = candles[i - n]
            claimed_low = False

        # Direct user correction: SLK reads breakouts off the LINE CHART
        # (closing prices) throughout -- the reference level is the swing
        # candle's own CLOSE by default, matching how A/V-shape key levels
        # already work, not its wick.
        if (last_swing_low is not None and not claimed_low
                and body_closes_beyond(c, last_swing_low.close if close_based_breakout else last_swing_low.low,
                                        Direction.BEARISH)):
            if (c.time, Direction.BEARISH) not in sweep_break_keys:
                confirmations.append(Confirmation(c.time, Direction.BEARISH, ConfirmationKind.BREAKOUT,
                                                  c.close, known_at=closes_at(c.time, length)))
            claimed_low = True

        if (last_swing_high is not None and not claimed_high
                and body_closes_beyond(c, last_swing_high.close if close_based_breakout else last_swing_high.high,
                                        Direction.BULLISH)):
            if (c.time, Direction.BULLISH) not in sweep_break_keys:
                confirmations.append(Confirmation(c.time, Direction.BULLISH, ConfirmationKind.BREAKOUT,
                                                  c.close, known_at=closes_at(c.time, length)))
            claimed_high = True

    return sorted(confirmations, key=lambda x: x.time)


class BiasCascade:
    """Tracks the currently-held bias for one origin timeframe and applies
    the 3-condition flip test."""

    def __init__(self, origin_timeframe: str):
        self.origin_timeframe = origin_timeframe
        self.direction: Direction | None = None
        self.origin_time = None

    def set_initial_bias(self, direction: Direction, time):
        self.direction = direction
        self.origin_time = time

    def check_flip(self, origin_tf_next_key_level: KeyLevel, rejection_candle: Candle,
                    lower_tf_confirmations_after_rejection: list[Confirmation],
                    require_confirmation: bool = False) -> bool:
        """
        Evaluates conditions (b) and (c) of the flip test -- the caller is
        responsible for condition (a) (confirming price has actually
        traded into `origin_tf_next_key_level` before calling this).
        `origin_tf_next_key_level.default_bias` must equal the CURRENT
        bias direction, so a "disrespect" of it correctly means "closed
        in the new direction". Returns True (and updates self.direction)
        if the bias flips; False otherwise.
        """
        if self.direction is None:
            return False
        if origin_tf_next_key_level.default_bias != self.direction:
            raise ValueError(
                "origin_tf_next_key_level.default_bias must match the current bias direction"
            )

        # Condition (b): reject-and-close in the new (opposite) direction.
        if not is_disrespected(rejection_candle, origin_tf_next_key_level):
            return False

        # Condition (c): the lower timeframe must ALSO stop confirming the
        # OLD direction -- and per Video 17, only breakout/sweep_break
        # confirmations count here (Confirmation objects from
        # detect_confirmations() never include open-close/engulfing).
        still_confirms_original = any(
            c.direction == self.direction for c in lower_tf_confirmations_after_rejection
        )
        if still_confirms_original:
            return False  # Video 16's resolved ambiguity: not flipped yet

        # AN EMPTY WINDOW IS NOT A CONFIRMATION.
        #
        # The test above is a negative, and video-16 does state it that
        # way -- "the next lower timeframe must ALSO fail to give any
        # further continuation confirmation in the original direction".
        # An empty window satisfies that literally, so the bias flips on
        # NO EVIDENCE AT ALL, which is not what BIAS_CONFIRMATION_WINDOW's
        # own comment describes: "you look at the lower timeframe's MOST
        # RECENT breakout, and if it points the new way, the bias has
        # flipped." No breakout does not point the new way.
        #
        # The 2026-09-22 audit recorded this as real but harmless,
        # reasoning that the window is empty only when the rejection
        # falls after the last confirmation in the series -- the tail of
        # the data, not mid-history. That reasoning was incomplete:
        # THE TAIL OF THE DATA IS WHERE LIVE ALWAYS RUNS. It cannot move
        # a historical backtest and can absolutely flip a live bias on
        # nothing.
        #
        # Off by default so every recorded number reproduces.
        if require_confirmation and not lower_tf_confirmations_after_rejection:
            return False

        self.direction = Direction.BULLISH if self.direction == Direction.BEARISH else Direction.BEARISH
        self.origin_time = rejection_candle.time
        return True


# Highest priority first. Confirmed as a strict, uniform hierarchy at
# every level (Section 2) -- Weekly beats Daily the same way Daily beats
# 4H, per the Bishop PDF's explicit written trader reasoning.
TIMEFRAME_PRIORITY = ["Monthly", "Weekly", "Daily", "H4", "H1"]


def resolve_effective_bias(biases: dict[str, Direction | None]) -> tuple[Direction | None, str | None]:
    """
    Pick the effective bias by strict timeframe priority. Returns
    (direction, which_timeframe_it_came_from), or (None, None) if no
    timeframe in `biases` has an active bias. A lower timeframe's bias
    that conflicts with a higher one is intentionally ignored here --
    that's the induced-move trap, not a reversal.
    """
    for tf in TIMEFRAME_PRIORITY:
        if biases.get(tf) is not None:
            return biases[tf], tf
    return None, None


def replay_bias(candles: list[Candle], levels: list[KeyLevel], confirmations: list[Confirmation],
                 initial_direction: Direction, timeframe_label: str,
                 confirmation_window: int = 1,
                 require_confirmation: bool = False) -> list[tuple[object, Direction]]:
    """
    Backtest driver for BiasCascade: walks `candles` forward, applying
    check_flip() whenever price trades into the next same-direction key
    level that hasn't already been tested for a flip. Returns a list of
    (time, direction) breakpoints -- the bias is `direction` from that
    point until the next breakpoint (or end of data). Use `bias_at()`
    below to query it for a specific time.

    `confirmation_window` bounds how many of the next lower-timeframe
    confirmations after a rejection candle get checked for condition (c)
    ("the lower timeframe also stops confirming the old direction").

    DEFAULT IS 1, per a direct user statement of Bishop's actual rule:
    you look at the lower timeframe's MOST RECENT breakout, and if it
    points the new way the bias has flipped -- "Bishop himself uses just
    the most recent breakout". 2 is the stated tolerance when that
    breakout isn't clean; more than that is not the rule.

    This default was 5, which was never sourced -- an earlier version of
    this docstring said outright that STRATEGY.md gives no limit and the
    number was "a practical modeling choice". It turned out to be doing
    almost all the work in the whole cascade: because the lower timeframe
    emits confirmations in BOTH directions continuously, requiring five
    consecutive ones to avoid the old direction vetoed ~98% of otherwise
    valid flips (measured: EURUSD 854 of 874, GBPJPY 804 of 817). The
    daily bias then changed roughly once every 14-21 months -- GBPJPY sat
    bearish from 2003-08 to 2013-12 without a single flip -- which is not
    a daily bias in any meaningful sense.

    Measured across EURUSD/GBPJPY/GBPNZD x both styles, moving 5 -> 1
    gives +17.6% trades (3,328 -> 3,912) and +12.4% total R (3,747 ->
    4,213), at a slightly lower win rate (54.6% -> 53.5%) and avg R
    (1.126 -> 1.077): more opportunities, marginally lower quality each,
    more compounding return overall.

    Note this reads breakouts off CLOSES (line chart), not wicks -- see
    detect_confirmations()'s close_based_breakout, the other half of the
    same correction from the same source.
    """
    if not candles:
        return []

    # A bias breakpoint is created BY a candle of this timeframe, so it is
    # knowable only once that candle closes. Carried as a third tuple
    # element so `bias_at()` can answer "what did we know at time t"
    # rather than "what happened by time t" -- see Confirmation's
    # docstring for the bug this closes.
    length = bar_length(candles)

    cascade = BiasCascade(timeframe_label)
    cascade.set_initial_bias(initial_direction, candles[0].time)
    breakpoints = [(candles[0].time, initial_direction, closes_at(candles[0].time, length))]

    levels_sorted = sorted(levels, key=lambda lvl: lvl.time)
    tested_level_times = set()

    # Pre-indexed time arrays so the per-candle searches below are bisect
    # lookups rather than full scans of every level / every confirmation.
    # This is a pure performance change -- the semantics below are
    # identical to the original nested-scan version, which was measured
    # at ~21% of a single run_backtest's total runtime (and the
    # confirmation-window slice alone built a full list of every future
    # confirmation, thousands of entries, just to take the first five of
    # it, once per level tested).
    # Ordered and bisected on when each confirmation became KNOWN, not
    # when its candle opened. The lower timeframe's bars close on a
    # different grid from this one's, so "the next confirmation after
    # this rejection" is only meaningful in known_at terms.
    confirmations_sorted = sorted(confirmations, key=confirmation_known_at)
    confirmation_times = [confirmation_known_at(conf) for conf in confirmations_sorted]

    # Indexed by PRICE, not time. The dominant filter per candle is
    # `c.low <= level.price <= c.high`, and a single candle's range spans
    # a tiny slice of the whole series' price history -- so bisecting the
    # price axis turns the inner loop from "every level so far" into "the
    # handful this candle actually touches". Time-ordering the eligible
    # subset afterwards preserves the original's semantics exactly: it
    # walked levels in time order and stopped at the first qualifying
    # one, which is the earliest-by-time match.
    #
    # This matters far more than it looks: on the live VPS the previous
    # time-only version left build_htf_context() at 131s per instrument
    # (~55 min per pass per bot), because levels that never qualify are
    # never marked tested, so the scan kept re-walking all of them.
    by_price = sorted(levels_sorted, key=lambda lvl: lvl.price)
    level_prices = [lvl.price for lvl in by_price]

    for c in candles:
        lo = bisect.bisect_left(level_prices, c.low)
        hi = bisect.bisect_right(level_prices, c.high)
        if lo == hi:
            continue
        eligible = None
        for idx in range(lo, hi):
            level = by_price[idx]
            # known_at, not .time -- an A/V-shape level isn't actually
            # usable until n bars after it forms (2026-08-28 fix; see
            # OPEN_QUESTIONS.md's lookahead-bias entry). Dedup key stays
            # on .time -- that's the level's identity, not its usability.
            if level_known_at(level) >= c.time or level.time in tested_level_times:
                continue
            if level.default_bias != cascade.direction:
                continue
            if eligible is None or level_known_at(level) < level_known_at(eligible):
                eligible = level
        if eligible is None:
            continue
        tested_level_times.add(eligible.time)
        # Boundary deliberately left at the rejection candle's OPEN, not
        # its close. A lower-timeframe confirmation landing inside this
        # candle's own span IS knowable before this candle finishes, so
        # including it is causal, not a look-ahead. Moving the boundary
        # to the close would change which flips happen -- that question
        # belongs to finding 5 (making condition (c) look backwards
        # instead of forwards), not to the known_at fix, and a test here
        # correctly caught the attempt to smuggle it in.
        start = bisect.bisect_right(confirmation_times, c.time)
        window = confirmations_sorted[start:start + confirmation_window]
        if cascade.check_flip(eligible, c, window,
                              require_confirmation=require_confirmation):
            breakpoints.append((c.time, cascade.direction, closes_at(c.time, length)))

    return breakpoints


def breakpoint_known_at(bp) -> object:
    """When a breakpoint became knowable: its third element when present,
    otherwise its own time. Two-element breakpoints come from hand-built
    test fixtures; `replay_bias()` has emitted three since 2026-09-18."""
    return bp[2] if len(bp) > 2 and bp[2] is not None else bp[0]


def bias_at(breakpoints: list[tuple], t) -> Direction | None:
    """The bias KNOWN at time `t` -- filtered on each breakpoint's
    known_at, not the candle time that produced it.

    The difference is the whole of finding 1 for the bias path: a Weekly
    breakpoint stamped Monday is not knowable until the following Monday,
    and answering with it in between let an H1 entry inherit a bias from
    a week it had not lived through yet."""
    applicable = [bp for bp in breakpoints if breakpoint_known_at(bp) <= t]
    if not applicable:
        return None
    return max(applicable, key=breakpoint_known_at)[1]
