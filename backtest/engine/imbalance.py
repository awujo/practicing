"""
Imbalance / fair value gap (FVG) detection.

STRATEGY.md uses "imbalance"/"FVG" constantly (as a quality signal for key
levels, an entry-trigger component, and a target-selection factor) but
never once gives a precise definition anywhere in the 18 core videos or
Bishop's material -- the one genuine definitional gap in the whole
document (flagged during the STRATEGY.md review). The header does name
the methodology family as "Smart Money Concepts / ICT-style price action
(market structure, liquidity, imbalance/FVG, sessions)", so this module
uses the standard ICT 3-candle FVG definition: for candles A, B, C in
sequence, a gap exists between A's high/low and C's low/high (B is the
displacement candle in between) that price never traded through. This is
a stated assumption, not something confirmed against the source
material -- worth revisiting if it ever conflicts with how the videos
visually mark imbalances.
"""

from dataclasses import dataclass

from .candles import Candle
from .structure import Direction


@dataclass(frozen=True)
class Imbalance:
    time: object       # time of the middle (displacement) candle
    low: float
    high: float
    direction: Direction  # BULLISH gap (untraded zone below price) or BEARISH (above price)


def detect_imbalances(candles: list[Candle]) -> list[Imbalance]:
    """Standard 3-candle FVG scan across the whole series."""
    out = []
    for i in range(1, len(candles) - 1):
        a, b, c = candles[i - 1], candles[i], candles[i + 1]
        if a.high < c.low:
            out.append(Imbalance(b.time, a.high, c.low, Direction.BULLISH))
        elif a.low > c.high:
            out.append(Imbalance(b.time, c.high, a.low, Direction.BEARISH))
    return out


def overlaps_level(imbalance: Imbalance, price: float) -> bool:
    """Section 5's 'quality signal': whether a key level price sits inside this imbalance."""
    return imbalance.low <= price <= imbalance.high
