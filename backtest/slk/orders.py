"""
The resting order: one per level, newest confirmation wins.

Operator, 2026-09-25, answering the case the source does not cover:

    "Replace it -- newest confirmation wins, one order at a time per
     level."

WHAT THE SOURCE DOES SAY, AND WHERE THIS FILLS THE GAP

The three confirmation forms are a FALLBACK SEQUENCE on one key level,
not competing setups. video-14 t=521-564: price should play a direct
mitigation of the A-shape level, and *"if price doesn't do this, the
second thing that we are most likely going to see price do"* is the
two-candle open-close that then gets engulfed. The level is the setup;
the confirmation is only how you are allowed in.

And an order dies when the ANALYSIS dies, not when a rival signal
appears -- video-03 t=1892-1914: *"I had to go and cancel my limit
order ... because [I] was analyzing this from the three hours, it was
selling, that's why I had to go and cancel this."*

What neither course states is which order stands when a SECOND
confirmation fires on the same level before the first has filled. That
is the operator's call above, and it is recorded as theirs rather than
dressed up as a citation.

NO FUTURE

`fills` is handed one candle. It cannot see the next one, so it cannot
decide a fill on what happens afterwards.

A CANDLE THAT REACHES BOTH ENTRY AND STOP FILLS, AND THEN LOSES. Price
that fell far enough to take the stop has already traded through the
entry on its way, so calling that "never filled" would quietly delete
real losing trades and flatter every figure downstream.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from ..engine.candles import Candle
from ..engine.structure import Direction


@dataclass(frozen=True)
class Fill:
    """An order that filled, and whether this candle was ambiguous.

    `same_candle_stop` marks the one case where the result depends on
    an assumption rather than on the data: price reached BOTH the entry
    and the stop inside one candle, and four numbers per candle cannot
    say which came first. We assume filled-then-stopped, because a
    resting order that price traded through is filled in reality and
    calling it "never filled" would delete exactly the fastest, ugliest
    losses.

    Flagged as its own event, per the operator on 2026-09-25, rather
    than folded in as an ordinary loss. It has to be COUNTABLE: if
    these are a large share of losses, the result rests on the
    assumption and anyone reading it deserves to know that. If they are
    rare, it does not matter and the count says so.
    """
    order: "PendingOrder"
    at: object
    same_candle_stop: bool


@dataclass(frozen=True)
class PendingOrder:
    """An order resting at a level, waiting for price to come back.

    `level_key` is what "one at a time per level" is counted on. Two
    orders sharing it are the same level being re-confirmed, and the
    newer one replaces the older.

    `liquidity` is the price of the internal range liquidity whose
    taking entitled the setup (sweep.py). It is carried purely so it
    reaches the report: an order that cannot name the liquidity it was
    taken on is an order that is not SLK, and the only way to see that
    is to print it next to the chart.
    """
    level_key: object
    entry: float
    stop: float
    target: float | None
    direction: Direction
    placed_at: object
    confirmation: str          # which form let this one in
    liquidity: float = None    # the liquidity whose taking entitled it


class OrderBook:
    """At most one resting order per level."""

    def __init__(self):
        self._orders: dict[object, PendingOrder] = {}
        self.replaced: list[tuple[PendingOrder, PendingOrder]] = []
        self.cancelled: list[tuple[PendingOrder, str]] = []

    def __len__(self):
        return len(self._orders)

    def resting(self) -> list[PendingOrder]:
        return list(self._orders.values())

    def place(self, order: PendingOrder) -> PendingOrder | None:
        """Rest `order`, displacing any order already on that level.

        Returns whatever it replaced, so a caller can report it rather
        than have orders vanish silently. Replacement is the whole
        rule: the newest confirmation is the one being traded, and the
        older entry, stop and target go with it -- a new confirmation
        means a new invalidation, so keeping the old stop would pair a
        fresh entry with a stale one.
        """
        previous = self._orders.get(order.level_key)
        self._orders[order.level_key] = order
        if previous is not None:
            self.replaced.append((previous, order))
        return previous

    def cancel(self, level_key, reason: str) -> PendingOrder | None:
        order = self._orders.pop(level_key, None)
        if order is not None:
            self.cancelled.append((order, reason))
        return order

    def cancel_all(self, reason: str) -> list[PendingOrder]:
        """Every resting order, gone. This is the bias-flip case --
        "trust your analysis" cuts both ways, and when the analysis
        changes the orders it justified are no longer justified."""
        out = []
        for key in list(self._orders):
            out.append(self.cancel(key, reason))
        return [o for o in out if o is not None]

    def fills(self, candle: Candle) -> list[Fill]:
        """Which resting orders this candle fills. Filled orders leave
        the book -- a level holds at most one order, and a filled order
        is a position now, not an order.

        Each fill says whether the same candle also reached the stop,
        so that ambiguous case can be counted rather than disappearing
        into the loss column."""
        hit = []
        for key, order in list(self._orders.items()):
            if _reaches(candle, order):
                hit.append(Fill(order=order, at=candle.time,
                                same_candle_stop=_reaches_stop(candle, order)))
                del self._orders[key]
        return hit


def _reaches_stop(candle: Candle, order: PendingOrder) -> bool:
    """Did this same candle also reach the stop? See `Fill`."""
    if order.direction == Direction.BULLISH:
        return candle.low <= order.stop
    return candle.high >= order.stop


def _reaches(candle: Candle, order: PendingOrder) -> bool:
    """Did price trade to the entry during this candle?

    A buy rests BELOW price and fills when the candle's low reaches it;
    a sell rests above and fills on the high. Deliberately not "did it
    also survive the stop" -- see the module note: a candle that took
    the stop traded through the entry first, and that is a losing trade
    rather than an absent one.
    """
    if order.direction == Direction.BULLISH:
        return candle.low <= order.entry
    return candle.high >= order.entry
