"""
Trade management -- STRATEGY.md Section 6.

Four pieces:

1. `PositionManager` -- trade stacking (Video 14): additional qualifying
   setups on a LOWER timeframe, same direction, while an original
   position is still live, are traded as ADDITIONAL stacked positions
   rather than skipped. Whether stacking applies to origin trades too, or
   continuation setups only, is an explicitly OPEN QUESTION in
   STRATEGY.md (Section 9) -- this class doesn't restrict it either way;
   it's up to the caller which setups get fed in as new positions.

2. `primary_target()` -- the 1:3 risk-reward baseline ("the repeatable
   bread-and-butter target... take the 1:3 when it's there"), ERL-capped:
   3:1/4:1 is the DEFAULT, not a fixed target -- a direct user correction
   that a straight R:R target overshooting the real external range
   liquidity should be capped there instead (`erl_price` parameter,
   computed by runner.py's `_nearest_erl()` from Daily/Weekly period
   extremes -- NOT H4 or a generic swing fractal; an earlier version used
   both and, on real EURUSD data, ended up capping 96% of trades since a
   dense H4 series always has SOME nearby swing point, which isn't the
   same thing as genuine external liquidity).

3. `tiered_exit_targets()` -- Video 16's major exit-targeting rule: a
   storyline built from a given timeframe's key level is expected to
   conclude at ANOTHER key level on that SAME timeframe, not the
   lower-timeframe level the entry trigger actually came from. Two tiers:
   a nearer partial target at the entry timeframe's own ERL, and the
   ultimate target at the next key level on the bias's origin timeframe.

4. `conservative_countertrend_target()` -- Bishop's risk-management
   refinement: a short-term countertrend/retracement trade taken off a
   swept breakout-candle extreme should cap its target at the nearest
   liquidity point, not the full opposite-structure extreme, since the
   dominant bias may resume before ever reaching a more distant target.
"""

from dataclasses import dataclass

from .structure import Direction

RISK_REWARD_PRIMARY = 3.0  # 1:3


@dataclass
class Position:
    id: int
    direction: Direction
    entry_price: float
    stop_loss: float
    entry_time: object
    entry_timeframe: str
    target_price: float | None = None
    status: str = "open"  # "open" | "closed_win" | "closed_loss" | "closed_breakeven"


class PositionManager:
    def __init__(self):
        self._next_id = 1
        self.positions: list[Position] = []

    def open_position(self, direction: Direction, entry_price: float, stop_loss: float,
                       entry_time, entry_timeframe: str, target_price: float | None = None) -> Position:
        pos = Position(self._next_id, direction, entry_price, stop_loss, entry_time, entry_timeframe, target_price)
        self._next_id += 1
        self.positions.append(pos)
        return pos

    def open_positions(self, direction: Direction | None = None) -> list[Position]:
        open_ = [p for p in self.positions if p.status == "open"]
        if direction is not None:
            open_ = [p for p in open_ if p.direction == direction]
        return open_

    def close_position(self, position: Position, status: str):
        if status not in ("closed_win", "closed_loss", "closed_breakeven"):
            raise ValueError("status must be closed_win, closed_loss, or closed_breakeven")
        position.status = status


def primary_target(entry_price: float, stop_loss: float, direction: Direction,
                    rr: float = RISK_REWARD_PRIMARY, erl_price: float | None = None) -> float:
    """The plain rr (default 1:3) target, ERL-capped when `erl_price` is
    given: "price wants to go from internal range liquidity to external"
    -- not beyond it (direct user correction; STRATEGY.md's flat 1:3
    baseline never accounted for this). `erl_price` should be the nearest
    untaken external range liquidity point currently visible on
    4H/Daily/Weekly, in the trade direction (see runner.py's
    `_nearest_erl()`). If the plain rr target would overshoot it, the
    target is capped there instead -- effectively reducing the realized
    R:R rather than the fixed 1:3 ratio itself, since the ratio isn't a
    separately tracked quantity here."""
    risk = abs(entry_price - stop_loss)
    raw_target = entry_price + risk * rr if direction == Direction.BULLISH else entry_price - risk * rr
    if erl_price is None:
        return raw_target
    return min(raw_target, erl_price) if direction == Direction.BULLISH else max(raw_target, erl_price)


@dataclass(frozen=True)
class TieredTarget:
    partial_target: float   # entry-timeframe's own ERL -- nearer
    ultimate_target: float  # next key level on the bias's ORIGIN timeframe


def tiered_exit_targets(entry_timeframe_erl: float, origin_timeframe_next_key_level: float) -> TieredTarget:
    return TieredTarget(entry_timeframe_erl, origin_timeframe_next_key_level)


def conservative_countertrend_target(nearest_liquidity: float, opposite_structure_extreme: float,
                                      is_countertrend: bool) -> float:
    """Trades aligned with the dominant bias aren't capped this way --
    only short-term countertrend/retracement trades taken off a swept
    breakout-candle extreme."""
    return nearest_liquidity if is_countertrend else opposite_structure_extreme
