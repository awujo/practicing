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


@dataclass(frozen=True)
class SingleCandleLiquidity:
    """One candle's high or low, resting as a liquidity pool in its own right.

    Deliberately NOT a SwingPoint, and deliberately not produced by
    `structural_liquidity_points()`. See that function's note for the
    conceptual error this type exists to correct.

    `time` is the forming candle's open time; `known_at` is the next
    candle's open time -- i.e. when the forming candle CLOSED and the
    pool became a real, tradeable level. Nothing may treat this pool as
    swept before `known_at`: the candle that FORMS a low cannot also be
    the candle that takes it.
    """
    time: object
    known_at: object
    price: float
    kind: str  # "low" | "high"


def single_candle_liquidity(candles: list[Candle], kind: str, start: int = 0,
                             limit: int | None = None) -> list[SingleCandleLiquidity]:
    """Every candle's low (kind="low") or high (kind="high") from `start`,
    each one a resting pool.

    This is the SLK "single candle liquidity" concept, and it is a
    DIFFERENT thing from "sweep of liquidity + break of structure". The
    latter is structural -- price runs a swing point and breaks structure,
    which sets directional bias, and `structure.py`'s StructureTracker
    owns it. This one is about entry timing: after a breakout, individual
    candles leave highs and lows behind, those sit as pools, and price
    coming back to take one is what delivers it into a key level.

    The distinction is not academic. A single candle low is USUALLY NOT a
    swing low -- during a post-breakout pullback every candle can make a
    higher low than the last, so a fractal swing detector (which needs
    low <= both neighbours) finds nothing at all, and whatever it does
    eventually find is the turning candle, not the pool price actually
    took. Worked example, GBPUSD H4 10 Aug 2026: breakout candle 12:00
    (high 1.35303), the candle after it leaves low 1.35050, price returns
    at 20:00 to 1.35012 and closes back up at 1.35105. That 1.35050 is
    the level -- and `is_swing_low` cannot see it, because 1.35050 is not
    <= the breakout candle's own low of 1.34899.

    `limit` caps how many candles from `start` may supply a pool; None
    means every candle in the list. The cap exists because the pools that
    matter sit close behind the breakout (every chart sample studied had
    the level within a few candles of it), while an uncapped window makes
    the downstream sweep/reaction search proportionally more expensive
    for pools nobody would ever have drawn.
    """
    if kind not in ("low", "high"):
        raise ValueError("kind must be 'low' or 'high'")
    end = len(candles) if limit is None else min(start + limit, len(candles))
    points = []
    for i in range(max(start, 0), end):
        c = candles[i]
        # known_at is the NEXT candle's open time -- the pool is not real
        # until the candle that formed it has closed. For the final candle
        # in the series there is no next one yet, so carry the bar's own
        # width forward; the pool is still unusable until that time.
        if i + 1 < len(candles):
            known_at = candles[i + 1].time
        elif i > 0:
            known_at = c.time + (c.time - candles[i - 1].time)
        else:
            known_at = c.time
        points.append(SingleCandleLiquidity(
            time=c.time, known_at=known_at,
            price=c.low if kind == "low" else c.high, kind=kind,
        ))
    return points


def structural_liquidity_points(candles: list[Candle], n: int = 2) -> list[SwingPoint]:
    """
    Generalized liquidity-pool candidates (Bishop, "Repeating System"):
    not every liquidity pool reduces to one candle's high/low -- a
    multi-candle swing point plays the identical functional role. `n`
    controls how broad a swing point has to be.

    WARNING -- do NOT use this for single candle liquidity. An earlier
    version of this docstring claimed n=1 "recovers something close to
    per-candle (SCF) detection". It does not, and that sentence is how a
    real bug got into the entry path for months. At n=1 `is_swing_low`
    still requires the low to be <= BOTH neighbours, so it only ever
    returns local extremes; a candle that simply leaves a low behind
    during a pullback never registers. Use `single_candle_liquidity()`
    for that concept. This function is for structural swing points

    Larger n captures broader structural swing points
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
