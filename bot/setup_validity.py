"""Is a signal still worth acting on, given what price did since it fired?

Why this exists (2026-09-02, from the live audit): the bot is essentially
never prompt. Zero entry attempts in its whole history happened within 5
minutes of the candle closing; the distribution runs 5-30m (5), 30-60m
(9), 1-2h (6), 2h+ (22). The 2h+ group is catch-up after MT5 reconnect
storms, during which `run_once()` fail-closes and processes nothing.

That lateness -- not stop placement -- caused 41 of the bot's 42 failed
entry attempts: 22 declined as stale, 12 rejected by the broker because
the stop had ended up on the wrong side of a price that moved while the
order sat unsent, 2 declined by the drift guard, plus the CHFJPY fill 50
pips from its computed entry.

The old handling was binary and both branches were wrong. Under
STALE_ENTRY_CUTOFF a stale signal became a MARKET order at whatever price
had become of it; over the cutoff it was thrown away entirely. But an SLK
entry is a PREDEFINED LEVEL, so age alone says nothing -- what matters is
whether the setup's own thesis still holds. A level price has not yet
returned to is not a dead setup; it is a setup waiting.

So this answers the only question that actually matters, and it answers
it from price rather than from the clock:

  - stop already breached           -> dead, the thesis is invalidated
  - most of the target already made -> dead, the move happened without us
  - entry never revisited           -> ALIVE, rest a limit and wait
  - entry revisited                 -> ALIVE, and it would have filled

Deliberately pure: candles in, verdict out, no MT5 and no clock. Every
branch is a unit test.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from backtest.engine.structure import Direction


class Validity(Enum):
    ALIVE = "alive"
    STOP_BREACHED = "stop_breached"
    TARGET_ACHIEVED = "target_achieved"
    NO_CANDLES = "no_candles"


# How much of the run to the target can happen before the setup is
# considered spent. Direct operator description of their own rule
# (2026-09-01): the order "gets canceled once our target has been
# restored or almost eighty percent of our target has been achieved."
# Taking the remaining 20% means accepting the full original risk for a
# fifth of the original reward -- an R:R the setup was never sized for.
TARGET_ACHIEVED_FRACTION = 0.8


@dataclass(frozen=True)
class ValidityVerdict:
    validity: Validity
    reason: str
    entry_revisited: bool = False

    @property
    def alive(self) -> bool:
        return self.validity is Validity.ALIVE


def check_setup(entry_price: float, stop_loss: float, target: float,
                direction: Direction, candles_since,
                target_fraction: float = TARGET_ACHIEVED_FRACTION) -> ValidityVerdict:
    """Judge a signal against the candles that have closed since it fired.

    `candles_since` is every candle AFTER the signal candle, oldest first
    (empty when the signal is fresh, in which case the setup is trivially
    alive). Only highs and lows are read, so it works equally on cached
    candles and on bars pulled live from MT5.

    Order of checks matters: the stop is tested before the target, so a
    candle that spans both is treated as the loss. That is the
    conservative reading and matches how `_resolve_trade_outcome()`
    already resolves the same ambiguity in the backtest -- the two must
    not disagree about the same price action.
    """
    if not candles_since:
        return ValidityVerdict(Validity.ALIVE, "fresh signal, no candles since")

    bullish = direction == Direction.BULLISH
    reward = abs(target - entry_price)
    # A degenerate setup (target at entry) can never "achieve" anything;
    # treat the threshold as unreachable rather than dividing by zero.
    achieved_at = (entry_price + target_fraction * reward) if bullish else \
                  (entry_price - target_fraction * reward)

    revisited = False
    for candle in candles_since:
        if bullish:
            if candle.low <= stop_loss:
                return ValidityVerdict(
                    Validity.STOP_BREACHED,
                    f"price traded to {candle.low} at {candle.time}, through the stop "
                    f"at {stop_loss} -- the setup's own invalidation point",
                    revisited)
            if candle.low <= entry_price:
                revisited = True
            if reward and candle.high >= achieved_at:
                return ValidityVerdict(
                    Validity.TARGET_ACHIEVED,
                    f"price reached {candle.high} at {candle.time}, "
                    f"{target_fraction:.0%} of the way to target {target} -- "
                    f"the move happened without us",
                    revisited)
        else:
            if candle.high >= stop_loss:
                return ValidityVerdict(
                    Validity.STOP_BREACHED,
                    f"price traded to {candle.high} at {candle.time}, through the stop "
                    f"at {stop_loss} -- the setup's own invalidation point",
                    revisited)
            if candle.high >= entry_price:
                revisited = True
            if reward and candle.low <= achieved_at:
                return ValidityVerdict(
                    Validity.TARGET_ACHIEVED,
                    f"price reached {candle.low} at {candle.time}, "
                    f"{target_fraction:.0%} of the way to target {target} -- "
                    f"the move happened without us",
                    revisited)

    where = "entry level was revisited and would have filled" if revisited else \
            "price has not returned to the entry level yet"
    return ValidityVerdict(Validity.ALIVE, f"setup intact -- {where}", revisited)
