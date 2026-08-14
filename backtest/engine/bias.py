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

from dataclasses import dataclass
from enum import Enum

from .candles import Candle
from .structure import Direction, StructureTracker, body_closes_beyond, is_swing_high, is_swing_low
from .key_levels import KeyLevel, is_disrespected


class ConfirmationKind(Enum):
    BREAKOUT = "breakout"
    SWEEP_BREAK = "sweep_break"


@dataclass(frozen=True)
class Confirmation:
    time: object
    direction: Direction
    kind: ConfirmationKind
    price: float


def detect_confirmations(candles: list[Candle], n: int = 2) -> list[Confirmation]:
    """Merge plain breakouts and sweep+break-of-structure events into one
    confirmation stream, each tagged with which visual pattern it was."""
    tracker = StructureTracker(n)
    sweep_events = [e for e in tracker.run(candles) if e.kind == "valid_sweep_break"]
    sweep_break_keys = {(e.time, e.direction) for e in sweep_events}

    confirmations = [
        Confirmation(e.time, e.direction, ConfirmationKind.SWEEP_BREAK, e.price)
        for e in sweep_events
    ]

    swing_high_idxs = {i for i in range(len(candles)) if is_swing_high(candles, i, n)}
    swing_low_idxs = {i for i in range(len(candles)) if is_swing_low(candles, i, n)}

    last_swing_high = None
    last_swing_low = None
    claimed_high = False
    claimed_low = False

    for i, c in enumerate(candles):
        if i in swing_high_idxs:
            last_swing_high = candles[i]
            claimed_high = False
        if i in swing_low_idxs:
            last_swing_low = candles[i]
            claimed_low = False

        if (last_swing_low is not None and not claimed_low
                and body_closes_beyond(c, last_swing_low.low, Direction.BEARISH)):
            if (c.time, Direction.BEARISH) not in sweep_break_keys:
                confirmations.append(Confirmation(c.time, Direction.BEARISH, ConfirmationKind.BREAKOUT, c.close))
            claimed_low = True

        if (last_swing_high is not None and not claimed_high
                and body_closes_beyond(c, last_swing_high.high, Direction.BULLISH)):
            if (c.time, Direction.BULLISH) not in sweep_break_keys:
                confirmations.append(Confirmation(c.time, Direction.BULLISH, ConfirmationKind.BREAKOUT, c.close))
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
                    lower_tf_confirmations_after_rejection: list[Confirmation]) -> bool:
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
