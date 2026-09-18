"""How long a bar lasts, and therefore when it becomes knowable.

The bug this exists to fix (2026-09-18 review, finding 1). Candles are
stamped at their OPEN -- `resample.py` uses `label="left", closed="left"`,
and Dukascopy's native series follow the same convention. So the H4 row
`2026-09-17T12:00Z` is the candle covering 12:00-16:00. It does not
exist, and cannot be known, until 16:00.

Every consumer in the engine compared that stamp directly against the
entry candle's time, as though the bar were available at its own open.
An H1 entry at 13:00 was therefore allowed to be confirmed by an H4 bar
closing at 16:00, a Daily bar closing at midnight, and a Weekly bar
closing the following Monday. Measured on a synthetic 3-year series, that
put 4 of 7 sampled signals past the live bot's 3-hour stale cutoff at the
moment they first became computable, with the worst at 96 hours -- which
is why the live bot declined almost everything it saw as stale.

The codebase already had the right idea in `SwingPoint.confirmed_at` and
`KeyLevel.confirmed_at`, but applied it only to the n-bar FRACTAL lag
(a pivot needs n bars either side before it can be called). This module
supplies the other half: the BAR-CLOSE lag, which applies to every bar
on every timeframe, fractal or not.

`infer_bar_length()` reads the length off the data rather than taking it
on trust. Every caller in the engine receives a bare candle list with no
label attached, and a wrong label passed by hand would reintroduce
exactly the bug being fixed -- silently, and in the direction of
optimism. The modal gap is robust to the gaps that real series contain
(weekends on Daily, holidays, feed outages): those make some gaps LONGER,
never shorter, so they cannot outvote the true bar length.
"""

from __future__ import annotations

from collections import Counter

import pandas as pd

# Only used to sanity-check an inferred value and to let callers that DO
# know their timeframe say so. Not the primary path -- see the module
# docstring on why inference is preferred over a hand-passed label.
NAMED_BAR_LENGTHS = {
    "M15": pd.Timedelta(minutes=15),
    "M45": pd.Timedelta(minutes=45),
    "H1": pd.Timedelta(hours=1),
    "H2": pd.Timedelta(hours=2),
    "H3": pd.Timedelta(hours=3),
    "H4": pd.Timedelta(hours=4),
    "D": pd.Timedelta(days=1),
    "W": pd.Timedelta(days=7),
}

_ZERO = pd.Timedelta(0)


def infer_bar_length(candles) -> pd.Timedelta | None:
    """The modal gap between consecutive candle opens, which is the bar
    length of a series stamped at its opens.

    Returns None for a series too short to tell (fewer than two candles),
    and callers must treat that as "no bar-close adjustment available"
    rather than substituting a guess.

    Robust to the gaps real data has -- a weekend on a Daily series
    produces a 3-day gap, a feed outage produces a longer one -- because
    every such gap is a multiple of the bar length or larger, so the true
    length always stays the most common value. It is NOT robust to a
    series that interleaves two different grids, but that is a corrupt
    cache (the 2026-09-16 broker-midnight incident), not a case to paper
    over here."""
    if candles is None or len(candles) < 2:
        return None
    gaps = Counter()
    for prev, curr in zip(candles, candles[1:]):
        gap = curr.time - prev.time
        if gap > _ZERO:
            gaps[gap] += 1
    if not gaps:
        return None
    return gaps.most_common(1)[0][0]


def bar_length(candles, timeframe: str | None = None) -> pd.Timedelta | None:
    """The bar length for this series: inferred from the data, falling
    back to `timeframe`'s named length only when the data cannot say
    (a series of one candle, typically in a unit test)."""
    inferred = infer_bar_length(candles)
    if inferred is not None:
        return inferred
    return NAMED_BAR_LENGTHS.get(timeframe) if timeframe else None


def closes_at(candle_time, length: pd.Timedelta | None):
    """When the bar stamped `candle_time` finishes and becomes knowable.

    A None `length` returns the open time unchanged -- the pre-2026-09-18
    behavior. That is deliberately the no-op rather than an error so a
    caller with a one-candle series degrades to the old reading instead
    of crashing, but it IS the unsafe reading and callers should pass a
    real length wherever they can."""
    if length is None:
        return candle_time
    return candle_time + length
