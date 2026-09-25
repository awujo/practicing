"""
Where the trade is going: external range liquidity.

SLK_SPEC 7, and the course is unusually consistent about this -- seven
separate statements, and the only counter-evidence is 4th man's 1:3/1:4
on the continuation specifically:

    "the target should always be external liquidity"   (entries t=330)

    "no logical reason for you holding all the way [past] this
     liquidity ... after external liquidity is taken, expect a
     reversal"                                          (bd2 t=615-645)

    "at least this liquidity should have been your target"
                                                        (bias-2 t=1665)

WHAT COUNTS AS ONE

bias-2's words are "previous weekly high/low" -- a PERIOD'S OWN
extreme, not a swing fractal drawn across several bars. The previous
week's high. The previous day's low. And it only counts while it is
still standing: once price has traded through it, that liquidity has
been taken and is not a target any more.

R MULTIPLES ARE OUTPUTS

Never inputs. The finished trades in the videos read 2.72R, 3.4R, 3.6R,
4R, 4.9R, 5R, 5.6R, 5.9R, 6R and "almost 7R", and not one of those is a
number he chose -- each is what the distance to the liquidity happened
to be worth. So there is no ratio in this module, and there will not
be one.

NO FUTURE

`untaken_extremes` is handed the candles up to now. A period still
forming is not a "previous" anything, so the last one is never a
candidate -- and its high and low in cached data are the FINAL ones,
which is precisely how a backtest reads tomorrow by accident.
"""

from __future__ import annotations

from ..engine.candles import Candle
from ..engine.structure import Direction


def untaken_extremes(periods: list[Candle], kind: str) -> list[float]:
    """Every COMPLETED period's own high (or low) that no later period
    has traded through.

    `periods` is a Daily or Weekly series ending at or before now. The
    LAST element is dropped: whichever period contains "now" is still
    forming, and a period that has not closed is not a previous high.

    "Taken" is a trade through, not a close through -- liquidity is
    taken the moment price reaches it, which is the same reading the
    sweep half of the strategy uses everywhere else.
    """
    if len(periods) < 2:
        return []
    closed = periods[:-1]

    out = []
    for i, period in enumerate(closed):
        level = period.high if kind == "high" else period.low
        later = closed[i + 1:]
        if kind == "high":
            if not any(c.high >= level for c in later):
                out.append(level)
        else:
            if not any(c.low <= level for c in later):
                out.append(level)
    return out


def target_for(entry_price: float, direction: Direction,
               *period_series: list[Candle]) -> float | None:
    """The nearest untaken external liquidity beyond entry, or None.

    "The first target" -- the nearest one in the trade's direction, not
    the furthest. bd2 t=615-645 makes the ceiling explicit: there is no
    reason to hold past it, because that is where a reversal is
    expected.

    Several series may be passed (Daily and Weekly); the nearest across
    all of them wins. None means no liquidity is standing in that
    direction, and a caller that cannot name a target should not invent
    one -- there is no R fallback here on purpose.
    """
    kind = "high" if direction == Direction.BULLISH else "low"
    candidates = []
    for series in period_series:
        for level in untaken_extremes(series, kind):
            beyond = level > entry_price if direction == Direction.BULLISH \
                else level < entry_price
            if beyond:
                candidates.append(level)
    if not candidates:
        return None
    return min(candidates) if direction == Direction.BULLISH else max(candidates)
