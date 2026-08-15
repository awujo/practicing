"""
Entry triggers -- STRATEGY.md Section 5.

Four pieces:

1. `is_engulfing()` -- standard engulfing-candle detection. Section 5:
   "An engulfing candle consuming one/both of [a V/A-shape's candles] is
   functionally equivalent to a body-close break of a V/A-shape level."

2. `classify_entry_pattern()` -- Video 14's 3 execution-facing patterns
   (a restatement of Video 13's exhaustive 4-branch decision tree):
     - DIRECT_MITIGATION: the very next candle taps the new key level
       directly and continues [Video 13 branches 1 and 3].
     - FRESH_IRL_REQUIRED: the next candle approaches but doesn't tap the
       new level -- that candle becomes fresh internal range liquidity
       that must be swept before continuing [branch 2].
     - NESTED_DISRESPECT: instead of respecting the new level, two more
       candles form ANOTHER open-close that then gets disrespected
       [branch 4] -- triggers the ~70% "return to the closer level" rule
       (Phase 2's key-level ranking already captures that preference).

3. `irl_required()` -- Video 12: IRL formation is NECESSARY for an ORIGIN
   trade but OPTIONAL for a CONTINUATION trade.

4. Stop-loss placement (Video 13, direct student Q&A, plus a user-supplied
   Bishop-supplementary chart cross-check) -- four distinct mechanized
   rules, not one formula:
     - continuation, key level overlapping an imbalance ("plug and play"):
       stop just past the FAR edge of that specific imbalance (the side
       price would have to fully clear to invalidate the "came here to
       sweep liquidity and rebalance THIS gap" thesis) plus a small pip
       buffer. Visually confirmed against a real GBPUSD plug-and-play
       chart: SL sat just beyond the imbalance candle's far extreme, not
       at a fixed pip distance or a distant structural point. Takes
       priority over the two continuation rules below when an overlapping
       imbalance exists -- this is what "plug and play" actually is.
     - continuation (IRL formed, no overlapping imbalance): fixed ~10 pip
       stop -- the aggressive default, trading faster 1:3 realization
       against a real, acknowledged risk of getting stopped by a
       liquidity-hunt sweep first.
     - continuation (no IRL formed, Video 12's optional-IRL variant): a
       TIGHTER stop, just past the engulfed candle's own extreme plus a
       small pip buffer -- not the usual 10-11 pip continuation stop.
     - origin: stop beyond the structural extreme (strong high/low) plus
       a small pip-padding buffer. NOTE (see runner.py): this reference
       point is currently found via a pure time-proximity heuristic to
       the daily bias flip, with no check that price is still price-close
       to that structural extreme -- a known gap, deliberately left
       out of scope for the imbalance-stop fix above (origin trades were
       explicitly not touched by that change; still using the wide
       structural-extreme stop until revisited separately).

5. Entry style (Section 5, "both sanctioned -- build/test both"):
   Aggressive enters directly off the key-level+imbalance setup;
   Conservative waits for the lower-timeframe confirmation candle's close.
"""

from dataclasses import dataclass
from enum import Enum

from .candles import Candle
from .structure import Direction
from .key_levels import KeyLevel, detect_open_close_level, is_disrespected


def is_engulfing(prev: Candle, curr: Candle, direction: Direction) -> bool:
    if direction == Direction.BULLISH:
        return (prev.close < prev.open and curr.close > curr.open
                and curr.open <= prev.close and curr.close >= prev.open)
    return (prev.close > prev.open and curr.close < curr.open
            and curr.open >= prev.close and curr.close <= prev.open)


class EntryPattern(Enum):
    DIRECT_MITIGATION = "direct_mitigation"
    FRESH_IRL_REQUIRED = "fresh_irl_required"
    NESTED_DISRESPECT = "nested_disrespect"


@dataclass(frozen=True)
class EntryClassification:
    pattern: EntryPattern
    reference_level: KeyLevel               # the level to actually enter against
    fresh_irl_price: float | None = None    # set only for FRESH_IRL_REQUIRED


def classify_entry_pattern(new_key_level: KeyLevel, following: list[Candle]) -> EntryClassification | None:
    """`following`: the candles immediately after the engulfing candle
    that created `new_key_level`. Returns None if there's nothing to
    classify yet (no candles after the engulf)."""
    if not following:
        return None

    first = following[0]
    if first.low <= new_key_level.price <= first.high:
        return EntryClassification(EntryPattern.DIRECT_MITIGATION, new_key_level)

    if len(following) >= 3:
        nested = detect_open_close_level(following[0], following[1])
        if nested is not None and is_disrespected(following[2], nested):
            return EntryClassification(EntryPattern.NESTED_DISRESPECT, nested)

    fresh_irl_price = first.low if new_key_level.default_bias == Direction.BULLISH else first.high
    return EntryClassification(EntryPattern.FRESH_IRL_REQUIRED, new_key_level, fresh_irl_price)


def irl_required(trade_kind: str) -> bool:
    """Video 12: IRL is necessary to validate an ORIGIN trade, optional for a CONTINUATION trade."""
    if trade_kind not in ("origin", "continuation"):
        raise ValueError("trade_kind must be 'origin' or 'continuation'")
    return trade_kind == "origin"


def origin_stop_loss(structural_extreme: float, direction: Direction,
                      padding_pips: float = 1.0, pip_size: float = 0.0001) -> float:
    pad = padding_pips * pip_size
    return structural_extreme - pad if direction == Direction.BULLISH else structural_extreme + pad


def continuation_stop_loss(entry_price: float, direction: Direction,
                            pips: float = 10.0, pip_size: float = 0.0001) -> float:
    dist = pips * pip_size
    return entry_price - dist if direction == Direction.BULLISH else entry_price + dist


def tight_stop_loss_no_irl(engulfed_candle_extreme: float, direction: Direction,
                            padding_pips: float = 1.0, pip_size: float = 0.0001) -> float:
    """Video 12's optional-IRL continuation variant: tighter than the
    usual 10-11 pip continuation stop -- just past the engulfed candle's
    own extreme plus a small buffer."""
    pad = padding_pips * pip_size
    return engulfed_candle_extreme - pad if direction == Direction.BULLISH else engulfed_candle_extreme + pad


def imbalance_stop_loss(imbalance_low: float, imbalance_high: float, direction: Direction,
                         padding_pips: float = 1.0, pip_size: float = 0.0001) -> float:
    """"Plug and play" continuation stop, scoped to trades whose key level
    overlaps a specific imbalance (FVG): price is expected to sweep
    liquidity and rebalance THAT gap, and has no logical reason to trade
    beyond its far edge to do so. Stop sits just past the far edge (the
    side away from current price -- the side price would have to fully
    clear to invalidate the fill-the-gap thesis) plus a small pip buffer,
    mirroring `origin_stop_loss`'s/`tight_stop_loss_no_irl`'s padding
    convention. `imbalance_low`/`imbalance_high` bound the gap itself
    (an `Imbalance`'s `low`/`high` fields), not the wider displacement
    candle's own range."""
    pad = padding_pips * pip_size
    return imbalance_low - pad if direction == Direction.BULLISH else imbalance_high + pad


class EntryStyle(Enum):
    AGGRESSIVE = "aggressive"
    CONSERVATIVE = "conservative"


def aggressive_entry_price(key_level: KeyLevel) -> float:
    """Enter directly once the key-level+imbalance setup is fully formed, without waiting for confirmation."""
    return key_level.price


def conservative_entry_price(confirmation_candle: Candle) -> float:
    """Wait for the full lower-timeframe confirmation trigger (e.g. an engulfing candle) before entering."""
    return confirmation_candle.close
