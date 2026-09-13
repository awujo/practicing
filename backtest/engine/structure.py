"""
Structure-break detection -- STRATEGY.md Section 4.

Two rules from Section 4 get implemented precisely here because they're
the most unambiguous, directly-quoted rules in the whole document:

1. CRITICAL rule (wick-sweep vs body-close-break): a level is only
   validly broken when the candle's CLOSE trades beyond it. A wick
   through the level without a close beyond it is treated as
   inconclusive (~90% probability, per Video 13, that price returns to
   use it as further internal range liquidity) -- NOT a structural break.

2. A range/swing point is only valid once BOTH: (a) a prior swing
   high/low is SWEPT (wicked through), AND (b) a subsequent candle's body
   CLOSES beyond a structural point in that direction. The swept
   extreme becomes the new strong low (bullish case) or strong high
   (bearish case) -- STRATEGY.md's ABC "A leg" origin point.

One thing STRATEGY.md does NOT give a precise algorithm for: how to
identify "a prior swing point" in the first place ("look to the left" is
qualitative, not a formula). This module uses a standard n-bar fractal
(a swing high/low is the local extreme over n bars on each side) and
exposes `n` as a parameter specifically so it's a tunable backtest input,
not something hardcoded as if it were part of the taught rule.
"""

from dataclasses import dataclass
from enum import Enum

from .candles import Candle


class Direction(Enum):
    BULLISH = "bullish"
    BEARISH = "bearish"


@dataclass(frozen=True)
class SwingPoint:
    """`confirmed_at`: when this point first becomes knowable in a live,
    candle-by-candle replay. None means "same as `time`" (no fractal lag --
    a sweep/reaction point read directly off one already-closed candle). A
    point built from a fractal swing test (is_swing_high/is_swing_low)
    genuinely cannot be known until `n` bars after `time` -- see those
    functions' own docstrings ("only decidable n bars after idx") -- so a
    caller that filters/bisects candidates by time for ELIGIBILITY (not
    just identity/display) must use `known_at()` below, not `.time`
    directly. Added 2026-08-28 -- see OPEN_QUESTIONS.md's "Backtest replay
    may have a small (~n-bar) lookahead bias" entry for the incident this
    fixes."""
    time: object
    price: float
    kind: str  # "high" | "low"
    confirmed_at: object = None
    # The pivot candle's own CLOSE, distinct from `price` (its wick
    # extreme). Only populated where it's actually needed (StructureTracker's
    # last_swing_high/low, used as a sweep+break's structural level) --
    # see StructureTracker's close_based_break for why the two must be
    # tracked separately: a sweep is legitimately a wick event, but
    # SLK reads the level it's tested against off the line chart.
    close: float | None = None


def known_at(point: SwingPoint) -> object:
    """The time a SwingPoint's existence is actually usable in a
    candle-by-candle replay -- see `SwingPoint`'s own docstring."""
    return point.confirmed_at if point.confirmed_at is not None else point.time


@dataclass(frozen=True)
class StructureEvent:
    time: object
    kind: str  # "sweep" | "valid_sweep_break"
    direction: Direction
    price: float


def is_swing_high(candles: list[Candle], idx: int, n: int = 2) -> bool:
    """Fractal swing high: candles[idx].high is the local max over n bars each side.
    Only decidable n bars after idx -- i.e. this necessarily lags real time by n bars."""
    if idx < n or idx + n >= len(candles):
        return False
    pivot = candles[idx].high
    return (all(candles[idx - i].high <= pivot for i in range(1, n + 1))
            and all(candles[idx + i].high <= pivot for i in range(1, n + 1)))


def is_swing_low(candles: list[Candle], idx: int, n: int = 2) -> bool:
    if idx < n or idx + n >= len(candles):
        return False
    pivot = candles[idx].low
    return (all(candles[idx - i].low >= pivot for i in range(1, n + 1))
            and all(candles[idx + i].low >= pivot for i in range(1, n + 1)))


def body_closes_beyond(candle: Candle, level: float, direction: Direction) -> bool:
    """The CRITICAL rule: compare CLOSE, not the high/low wick, against the level."""
    if direction == Direction.BULLISH:
        return candle.close > level
    return candle.close < level


def wick_sweeps_without_close(candle: Candle, level: float, direction: Direction) -> bool:
    """Wick trades through the level but the body does not close beyond it --
    the ~90%-probability-of-no-break case (Video 13), not a confirmed structural break."""
    if direction == Direction.BULLISH:
        return candle.high > level and candle.close <= level
    return candle.low < level and candle.close >= level


class StructureTracker:
    """
    Forward-processes a candle series and emits `sweep` / `valid_sweep_break`
    events per Section 4's two-stage rule, tracking the current strong
    low/high as it goes (each updates forward on every new valid
    sweep+break -- "look to the left" to the most recent one).

    Usage:
        tracker = StructureTracker(n=2)
        events = tracker.run(candles)
        tracker.strong_low, tracker.strong_high   # current values after the run

    close_based_break: the swing high/low a sweep must close back through
    to confirm a "valid_sweep_break" is, by default (False), that swing
    candle's own WICK extreme -- matches every behavior before 2026-09-13.
    When True, the level is the swing candle's CLOSE instead (line chart),
    matching how detect_confirmations()'s plain-breakout half already
    reads breakouts (close_based_breakout) and the source material's own
    stated preference: "line chart specifically to verify break/no-break
    of a level (candlestick wicks can visually mislead)" (video-07's
    notes). The SWEEP itself stays wick-based either way -- a sweep is
    legitimately a wick event ("a mere sweep without a close-through does
    not invalidate it," video-07) -- only the level the BREAK is measured
    against changes. Direct operator question (2026-09-13), raised after
    the origin_kind fix surfaced the same class of inconsistency here:
    compare against the default before trusting it as the new normal,
    same as every other experimental variant in this engine.
    """

    def __init__(self, n: int = 2, close_based_break: bool = False):
        self.n = n
        self.close_based_break = close_based_break
        self.strong_low: SwingPoint | None = None
        self.strong_high: SwingPoint | None = None

    def run(self, candles: list[Candle]) -> list[StructureEvent]:
        events: list[StructureEvent] = []

        swing_high_idxs = {i for i in range(len(candles)) if is_swing_high(candles, i, self.n)}
        swing_low_idxs = {i for i in range(len(candles)) if is_swing_low(candles, i, self.n)}

        last_swing_high: SwingPoint | None = None
        last_swing_low: SwingPoint | None = None

        pending_sweep_low: SwingPoint | None = None
        structural_high_at_sweep: SwingPoint | None = None
        pending_sweep_high: SwingPoint | None = None
        structural_low_at_sweep: SwingPoint | None = None

        for i, c in enumerate(candles):
            # A pivot at index (i - n) only becomes fractally confirmable
            # here, at index i -- NOT at index (i - n) itself, which is
            # what checking `i in swing_high_idxs` did before (2026-08-28
            # fix; see OPEN_QUESTIONS.md's lookahead-bias entry). The
            # point's own `.time` still correctly reports where it formed;
            # only WHEN this loop starts treating it as known moves.
            if i - self.n in swing_high_idxs:
                p = candles[i - self.n]
                last_swing_high = SwingPoint(p.time, p.high, "high", close=p.close)
            if i - self.n in swing_low_idxs:
                p = candles[i - self.n]
                last_swing_low = SwingPoint(p.time, p.low, "low", close=p.close)

            # --- Bullish sequence: sweep a prior low, then close back above the
            # structural high that was in place when the sweep happened. ---
            # The SWEEP test always reads the wick (last_swing_low.price) --
            # a sweep is a wick event regardless of close_based_break.
            if pending_sweep_low is None and last_swing_low is not None and c.low < last_swing_low.price:
                pending_sweep_low = SwingPoint(c.time, c.low, "low")
                structural_high_at_sweep = last_swing_high
                events.append(StructureEvent(c.time, "sweep", Direction.BULLISH, c.low))
            elif pending_sweep_low is not None and c.low < pending_sweep_low.price:
                pending_sweep_low = SwingPoint(c.time, c.low, "low")  # deeper sweep before confirmation

            _high_break_level = (structural_high_at_sweep.close if self.close_based_break
                                 else structural_high_at_sweep.price) if structural_high_at_sweep else None
            if (pending_sweep_low is not None and structural_high_at_sweep is not None
                    and body_closes_beyond(c, _high_break_level, Direction.BULLISH)):
                self.strong_low = pending_sweep_low
                events.append(StructureEvent(c.time, "valid_sweep_break", Direction.BULLISH, self.strong_low.price))
                pending_sweep_low = None
                structural_high_at_sweep = None

            # --- Bearish sequence: mirror image. ---
            if pending_sweep_high is None and last_swing_high is not None and c.high > last_swing_high.price:
                pending_sweep_high = SwingPoint(c.time, c.high, "high")
                structural_low_at_sweep = last_swing_low
                events.append(StructureEvent(c.time, "sweep", Direction.BEARISH, c.high))
            elif pending_sweep_high is not None and c.high > pending_sweep_high.price:
                pending_sweep_high = SwingPoint(c.time, c.high, "high")

            _low_break_level = (structural_low_at_sweep.close if self.close_based_break
                                else structural_low_at_sweep.price) if structural_low_at_sweep else None
            if (pending_sweep_high is not None and structural_low_at_sweep is not None
                    and body_closes_beyond(c, _low_break_level, Direction.BEARISH)):
                self.strong_high = pending_sweep_high
                events.append(StructureEvent(c.time, "valid_sweep_break", Direction.BEARISH, self.strong_high.price))
                pending_sweep_high = None
                structural_low_at_sweep = None

        return events
