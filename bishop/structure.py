"""Causal close-line structure observations, not a certified major-swing model.

Source STRATEGY S03/S04 (v3@48-170,298-323,427-642): body closure breaks,
wick-only excursion sweeps. Numerical major/local reference selection remains
unsettled. This module's explicit provisional policy is the latest strict
close-direction turn, with the LAST equal close of a plateau as the extremum.
No n-right fractal or future bar is used. Changing this policy requires source
example verification, not tuning the expected examples.
"""
from dataclasses import dataclass
import pandas as pd
from .price_action import validated_bars


@dataclass(frozen=True)
class TurningPoint:
    kind: str
    price: float
    formed_at: pd.Timestamp
    available_at: pd.Timestamp


@dataclass(frozen=True)
class StructureEvent:
    kind: str
    side: str
    reference: float
    reference_formed_at: pd.Timestamp
    reference_available_at: pd.Timestamp
    occurred_at: pd.Timestamp
    available_at: pd.Timestamp
    sweep_at: pd.Timestamp | None = None
    policy: str = "latest_close_turn"


def turning_points(bars, *, as_of=None):
    """Strict close-line turns, observable only on the reversing close.

    Ties do not reverse direction; the final tied close is the point. These
    are local reference candidates, not retrospectively declared major swings.
    """
    frame = validated_bars(bars, as_of=as_of)
    closes, times = frame.close.to_numpy(), frame.index
    out, direction = [], 0
    for i in range(1, len(frame)):
        change = int(closes[i] > closes[i-1]) - int(closes[i] < closes[i-1])
        if not change:
            continue
        if direction and change != direction:
            out.append(TurningPoint("H" if direction > 0 else "L", float(closes[i-1]), times[i-1], times[i]))
        direction = change
    return out


def events(bars, *, as_of=None):
    """Observe first breaks of local turns and wick sweeps, causally.

    A first directional break initializes flow; a later opposite break is BOS.
    A strictly EARLIER opposite-extreme sweep followed by a break is SWEEP_BOS.
    Same-candle wick ordering cannot establish sweep-before-break. Sweep memory
    is consumed on any structure break, preventing stale sweeps being reused.
    """
    frame = validated_bars(bars, as_of=as_of)
    points = turning_points(frame, as_of=as_of)
    by_time = {}
    for point in points:
        by_time.setdefault(point.available_at, []).append(point)
    active, broken, swept, flow, out = {}, set(), {}, None, []
    for at, row in frame.iterrows():
        breaks, sweeps = [], []
        for kind, point in active.items():
            key = (point.kind, point.formed_at)
            if key in broken:
                continue
            if kind == "H":
                side, is_break = "BUY", row.close > point.price
                is_sweep = row.high > point.price and row.close <= point.price
            else:
                side, is_break = "SELL", row.close < point.price
                is_sweep = row.low < point.price and row.close >= point.price
            if is_break:
                prior_sweep = swept.get(side)
                name = "SWEEP_BOS" if prior_sweep is not None else "BOS" if flow and flow != side else "BREAKOUT"
                breaks.append(StructureEvent(name, side, point.price, point.formed_at,
                                             point.available_at, at, at, prior_sweep))
                broken.add(key)
            elif is_sweep:
                sweep_side = "SELL" if kind == "H" else "BUY"
                sweeps.append(StructureEvent("SWEEP", sweep_side, point.price, point.formed_at,
                                             point.available_at, at, at))
        out.extend(sweeps)
        out.extend(breaks)
        if breaks:
            # Valid OHLC cannot close above a high and below a low simultaneously.
            flow, swept = breaks[-1].side, {}
        else:
            for event in sweeps:
                swept[event.side] = at
        # A newly known turn cannot classify the candle that reveals it.
        for point in by_time.get(at, []):
            active[point.kind] = point
    return out
