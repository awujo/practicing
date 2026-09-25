"""
One resting order per level; the newest confirmation replaces the older.
"""

from __future__ import annotations

import pandas as pd

from ...engine.candles import Candle
from ...engine.structure import Direction
from ..orders import Fill, OrderBook, PendingOrder

T0 = pd.Timestamp("2026-01-01")


def c(i, o, h, l, cl):
    return Candle(time=T0 + pd.Timedelta(hours=i), open=o, high=h, low=l,
                  close=cl, volume=0)


def order(key="L1", entry=1.1000, stop=1.1050, target=1.0900,
          direction=Direction.BEARISH, at=0, confirmation="engulf"):
    return PendingOrder(level_key=key, entry=entry, stop=stop, target=target,
                        direction=direction, placed_at=T0 + pd.Timedelta(hours=at),
                        confirmation=confirmation)


def test_a_second_confirmation_on_the_same_level_replaces_the_first():
    """Operator, 2026-09-25: "Replace it -- newest confirmation wins,
    one order at a time per level"."""
    book = OrderBook()
    first = order(confirmation="engulf", entry=1.1000, stop=1.1050)
    book.place(first)

    second = order(confirmation="breakout", entry=1.1020, stop=1.1070, at=5)
    displaced = book.place(second)

    assert displaced == first
    assert len(book) == 1, "one order at a time per level"
    assert book.resting() == [second]
    assert book.replaced == [(first, second)]


def test_the_replacement_brings_its_own_stop():
    """A new confirmation means a new invalidation. Keeping the old
    stop would pair a fresh entry with a stale one."""
    book = OrderBook()
    book.place(order(entry=1.1000, stop=1.1050))
    book.place(order(entry=1.1020, stop=1.1070, confirmation="breakout"))

    resting = book.resting()[0]
    assert (resting.entry, resting.stop) == (1.1020, 1.1070)


def test_a_different_level_is_untouched_by_a_replacement():
    book = OrderBook()
    a = order(key="L1", entry=1.1000)
    b = order(key="L2", entry=1.2000)
    book.place(a)
    book.place(b)

    book.place(order(key="L1", entry=1.1010, confirmation="breakout"))
    assert len(book) == 2
    assert b in book.resting(), "L2 had nothing to do with it"


def test_a_sell_fills_when_price_comes_back_up_to_the_level():
    """The entry is the RETURN. A sell rests above and fills on the
    candle's high."""
    book = OrderBook()
    book.place(order(entry=1.1000, direction=Direction.BEARISH))

    away = c(1, 1.0950, 1.0980, 1.0940, 1.0960)
    assert book.fills(away) == []
    assert len(book) == 1, "still waiting"

    back = c(2, 1.0960, 1.1005, 1.0955, 1.0990)
    filled = book.fills(back)
    assert len(filled) == 1
    assert filled[0].order.entry == 1.1000
    assert filled[0].at == back.time
    assert filled[0].same_candle_stop is False, "clean fill, no ambiguity"
    assert len(book) == 0, "a filled order is a position, not an order"


def test_a_buy_fills_on_the_low():
    book = OrderBook()
    book.place(order(entry=1.1000, stop=1.0950, target=1.1100,
                     direction=Direction.BULLISH))
    assert book.fills(c(1, 1.1030, 1.1040, 1.1010, 1.1020)) == []
    assert len(book.fills(c(2, 1.1020, 1.1025, 1.0995, 1.1000))) == 1


def test_a_candle_that_takes_the_stop_filled_first_and_lost():
    """It traded THROUGH the entry on its way to the stop. Calling that
    "never filled" would silently delete real losing trades and flatter
    every figure built on them."""
    book = OrderBook()
    book.place(order(entry=1.1000, stop=1.1050, direction=Direction.BEARISH))

    straight_through = c(1, 1.0960, 1.1080, 1.0955, 1.1070)
    filled = book.fills(straight_through)
    assert len(filled) == 1


def test_the_ambiguous_fill_is_flagged_as_its_own_event():
    """Operator, 2026-09-25: "note it as its own event."

    This is the one outcome that rests on an ASSUMPTION rather than on
    the data -- four numbers per candle cannot say whether the entry or
    the stop came first. It has to be countable, so that a result which
    leans on it can be recognised as doing so."""
    book = OrderBook()
    book.place(order(entry=1.1000, stop=1.1050, direction=Direction.BEARISH))

    both = c(1, 1.0960, 1.1080, 1.0955, 1.1070)   # reaches entry AND stop
    fill = book.fills(both)[0]
    assert fill.same_candle_stop is True

    # And a fill that only reaches the entry is not flagged, so the
    # count means something.
    book.place(order(entry=1.1000, stop=1.1050, direction=Direction.BEARISH))
    gentle = c(2, 1.0960, 1.1010, 1.0955, 1.0990)
    assert book.fills(gentle)[0].same_candle_stop is False


def test_a_buy_fill_is_flagged_on_the_same_rule_mirrored():
    book = OrderBook()
    book.place(order(entry=1.1000, stop=1.0950, target=1.1100,
                     direction=Direction.BULLISH))
    plunge = c(1, 1.1030, 1.1035, 1.0940, 1.0945)   # through entry and stop
    assert book.fills(plunge)[0].same_candle_stop is True


def test_the_analysis_changing_cancels_everything_resting():
    """video-03 t=1892-1914: "I had to go and cancel my limit order ...
    it was selling, that's why I had to go and cancel this"."""
    book = OrderBook()
    book.place(order(key="L1"))
    book.place(order(key="L2", entry=1.2000))

    gone = book.cancel_all("daily bias flipped")
    assert len(gone) == 2
    assert len(book) == 0
    assert all(reason == "daily bias flipped" for _, reason in book.cancelled)


def test_cancelling_a_level_that_holds_nothing_is_not_an_error():
    book = OrderBook()
    assert book.cancel("nothing here", "bias flipped") is None
    assert book.cancelled == []
