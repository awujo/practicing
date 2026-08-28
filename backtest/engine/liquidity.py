"""
Liquidity framework -- STRATEGY.md Section 3.

Two pieces implemented here:

1. SCF (Single Candle Formation, Video 18) IRL/ERL tagging, generalized to
   "structural liquidity" (Bishop, "Repeating System"): any swing point --
   a single candle at n=0/1, or a broader local extreme at higher n -- can
   supply both an IRL and ERL reference depending on the prevailing
   bullish/bearish direction. Reuses structure.py's fractal swing detector
   so the single-candle case is just the n=0 special case of the same
   function, per Section 3's explicit generalization.

2. SequentialLiquidityTracker: once one side of a timeframe category's
   liquidity (daily/weekly/monthly/Asian high-low) is taken, the next
   target flips to the OPPOSITE side of that SAME category.
"""

from dataclasses import dataclass

from .candles import Candle
from .structure import Direction, is_swing_high, is_swing_low, SwingPoint


@dataclass(frozen=True)
class LiquidityTag:
    time: object
    irl_price: float
    erl_price: float
    direction: Direction


def scf_tag(candle: Candle, direction: Direction) -> LiquidityTag:
    """
    A single candle's high/low each serve a distinct liquidity role
    simultaneously: bullish structure -> low=IRL, high=ERL; bearish ->
    reversed. Applies at every timeframe -- pass in whichever candle/
    granularity you're tagging.
    """
    if direction == Direction.BULLISH:
        return LiquidityTag(candle.time, candle.low, candle.high, direction)
    return LiquidityTag(candle.time, candle.high, candle.low, direction)


def structural_liquidity_points(candles: list[Candle], n: int = 2) -> list[SwingPoint]:
    """
    Generalized liquidity-pool candidates (Bishop, "Repeating System"):
    not every liquidity pool reduces to one candle's high/low -- a
    multi-candle swing point plays the identical functional role. `n`
    controls the granularity: n=1 recovers something close to per-candle
    (SCF) detection; larger n captures broader structural swing points
    (including the "elbow structure" shape Bishop flags as needing the
    WHOLE shape swept, not just the first touch -- this function surfaces
    the candidate points, treating that caution as a downstream filtering
    decision rather than baking it in here).
    """
    points = []
    for i in range(len(candles)):
        if is_swing_high(candles, i, n):
            points.append(SwingPoint(candles[i].time, candles[i].high, "high",
                                      confirmed_at=candles[i + n].time))
        if is_swing_low(candles, i, n):
            points.append(SwingPoint(candles[i].time, candles[i].low, "low",
                                      confirmed_at=candles[i + n].time))
    return sorted(points, key=lambda p: p.time)


class SequentialLiquidityTracker:
    """
    Per-timeframe-category alternating target (STRATEGY.md Section 3):
    previous daily high taken -> next target = previous daily low, and
    vice versa. One instance per category (e.g. one for "daily", one for
    "weekly", one for "monthly", one for "asian") -- the category itself
    is just a label for the caller's bookkeeping, this class doesn't infer
    it from the data.
    """

    def __init__(self, category: str, high: float, low: float):
        self.category = category
        self.high = high
        self.low = low
        self.next_target: str | None = None  # "high" | "low" | None (neither side taken yet)

    def on_new_period(self, high: float, low: float):
        """Call when a new period's (day/week/month/session) extremes are known."""
        self.high, self.low = high, low
        self.next_target = None

    def on_sweep(self, side_taken: str):
        """side_taken: 'high' or 'low' -- whichever side of THIS category just got swept."""
        if side_taken not in ("high", "low"):
            raise ValueError("side_taken must be 'high' or 'low'")
        self.next_target = "low" if side_taken == "high" else "high"

    def target_price(self) -> float | None:
        if self.next_target == "high":
            return self.high
        if self.next_target == "low":
            return self.low
        return None
