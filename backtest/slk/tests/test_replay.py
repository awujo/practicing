"""
The driver: forward only, and it must not be able to cheat.
"""

from __future__ import annotations

import pandas as pd

from ...engine.candles import Candle
from ...engine.structure import Direction
from ..replay import _EngulfBook, replay
from ..confirmation import OpenCloseLevel

T0 = pd.Timestamp("2026-01-01")


def bar(t, o, h, l, c):
    return Candle(time=t, open=o, high=h, low=l, close=c, volume=0)


def h1s(specs, start=T0):
    return [bar(start + pd.Timedelta(hours=i), *s) for i, s in enumerate(specs)]


def test_the_engulf_book_consumes_a_level_exactly_once():
    """Each level is engulfed once, which is what keeps the whole run
    O(levels) instead of O(bars x levels)."""
    book = _EngulfBook()
    sell = OpenCloseLevel(T0, 1.1000, Direction.BEARISH, 1.1000, 1.1040)
    book.add(sell)

    assert book.consume(1.1010) == [], "a close above does not engulf a sell level"
    assert book.consume(1.0990) == [sell], "closing below engulfs it"
    assert book.consume(1.0900) == [], "and it is gone -- not engulfed twice"


def test_a_close_consumes_every_level_it_passed_and_no_others():
    book = _EngulfBook()
    near = OpenCloseLevel(T0, 1.1000, Direction.BEARISH, 1.1000, 1.1040)
    far = OpenCloseLevel(T0, 1.1200, Direction.BEARISH, 1.1200, 1.1240)
    below = OpenCloseLevel(T0, 1.0800, Direction.BEARISH, 1.0800, 1.0840)
    for lvl in (near, far, below):
        book.add(lvl)

    got = book.consume(1.0950)
    assert set(got) == {near, far}, "both sit above the close"
    assert book.consume(1.0700) == [below]


def test_buy_levels_are_engulfed_by_a_close_above():
    book = _EngulfBook()
    buy = OpenCloseLevel(T0, 1.1000, Direction.BULLISH, 1.1000, 1.0960)
    book.add(buy)
    assert book.consume(1.0990) == []
    assert book.consume(1.1010) == [buy]


def test_a_quiet_market_produces_no_trades_rather_than_an_error():
    flat = h1s([(1.10, 1.1005, 1.0995, 1.10)] * 200)
    d = [bar(T0 + pd.Timedelta(days=i), 1.10, 1.1005, 1.0995, 1.10)
         for i in range(20)]
    h4 = [bar(T0 + pd.Timedelta(hours=4 * i), 1.10, 1.1005, 1.0995, 1.10)
          for i in range(60)]
    assert replay([], d, h4, flat, n=2) == []


def test_missing_series_returns_nothing_rather_than_guessing():
    assert replay([], [], [], [], n=2) == []
    one = h1s([(1.10, 1.101, 1.099, 1.10)])
    assert replay([], [], [], one, n=2) == []


def test_the_driver_never_indexes_past_the_bar_it_is_on():
    """The property the whole package exists for. Running on a
    truncated series must produce a prefix of the fuller run -- if a
    trade only appears once later candles exist, the engine looked
    forward."""
    import random
    random.seed(5)
    px = 1.1000
    h1_bars = []
    for i in range(1200):
        o = px
        px += random.gauss(0, 0.0009)
        h1_bars.append(bar(T0 + pd.Timedelta(hours=i), o,
                           max(o, px) + 0.0004, min(o, px) - 0.0004, px))

    def agg(bars, hours):
        out = []
        for i in range(0, len(bars) - hours + 1, hours):
            chunk = bars[i:i + hours]
            out.append(bar(chunk[0].time, chunk[0].open,
                           max(c.high for c in chunk),
                           min(c.low for c in chunk), chunk[-1].close))
        return out

    cut = 800
    full = replay(agg(h1_bars, 168), agg(h1_bars, 24), agg(h1_bars, 4),
                  h1_bars, n=2)
    early = replay(agg(h1_bars[:cut], 168), agg(h1_bars[:cut], 24),
                   agg(h1_bars[:cut], 4), h1_bars[:cut], n=2)

    cutoff = h1_bars[cut - 1].time
    from_full = [(t.entry_time, t.entry, t.stop) for t in full
                 if t.exit_time is not None and t.exit_time <= cutoff]
    from_early = [(t.entry_time, t.entry, t.stop) for t in early
                  if t.exit_time is not None and t.exit_time <= cutoff]
    assert from_early == from_full, "truncating changed a settled trade"


def _random_series(seed=5, bars=1200):
    import random
    random.seed(seed)
    px = 1.1000
    out = []
    for i in range(bars):
        o = px
        px += random.gauss(0, 0.0009)
        out.append(bar(T0 + pd.Timedelta(hours=i), o,
                       max(o, px) + 0.0004, min(o, px) - 0.0004, px))
    return out


def _agg(bars, hours):
    out = []
    for i in range(0, len(bars) - hours + 1, hours):
        chunk = bars[i:i + hours]
        out.append(bar(chunk[0].time, chunk[0].open,
                       max(c.high for c in chunk),
                       min(c.low for c in chunk), chunk[-1].close))
    return out


def test_one_h4_level_produces_one_trade_not_one_per_engulf():
    """The old engine's overtrading, arriving in the new one by a
    different door.

    Orders were first keyed on the H1 open-close level, so three small
    levels inside one reaction became three setups -- three trades on
    the same bar at entries three pips apart. The H4 level is the
    SETUP; the H1 engulf is only permission to enter it, and a later
    engulf inside the same reaction REPLACES the order rather than
    adding one.

    Keying the orders correctly took the same data from 143 trades to
    75, with no bar holding more than one entry. Adding the liquidity
    gate (sweep.py) then took the same fixture from 75 to 2: a random
    walk almost never tells the story the setup requires, which is the
    result one would hope for."""
    h1_bars = _random_series()
    trades = replay(_agg(h1_bars, 168), _agg(h1_bars, 24),
                    _agg(h1_bars, 4), h1_bars, n=2)

    assert trades, "the fixture must actually trade, or this proves nothing"

    per_bar = {}
    for t in trades:
        per_bar[t.entry_time] = per_bar.get(t.entry_time, 0) + 1
    assert max(per_bar.values()) == 1, \
        f"{sum(v - 1 for v in per_bar.values() if v > 1)} duplicate entries"


def test_every_trade_can_name_the_liquidity_it_was_taken_on():
    """The L in SLK, enforced at the driver rather than only in the unit
    tests.

    An entry that cannot name the internal range liquidity whose taking
    entitled it is not an SLK entry -- it is "price touched a level",
    which is what the old engine did and why it took everything. The
    liquidity price is carried all the way onto the Trade so this is
    checkable here and printable next to a chart."""
    for seed in (2, 3, 4, 6):
        h1_bars = _random_series(seed=seed)
        trades = replay(_agg(h1_bars, 168), _agg(h1_bars, 24),
                        _agg(h1_bars, 4), h1_bars, n=2)
        assert trades, f"seed {seed} must trade or this proves nothing"
        for t in trades:
            assert t.liquidity is not None, "entitled by nothing"
            assert t.setup_price is not None, "no key level being played"
            assert t.form in {"engulf", "inducement", "breakout",
                              "sweep_break"}, f"unknown form {t.form!r}"
            if t.direction == Direction.BULLISH:
                assert t.stop < t.entry, "a buy stops below its entry"
            else:
                assert t.stop > t.entry, "a sell stops above its entry"


def test_the_ambiguous_fill_is_carried_onto_the_trade():
    """It has to survive as far as the report, or it cannot be counted
    -- which was the whole point of making it an event.

    Seed 4 rather than the 5 used elsewhere: with the liquidity gate in
    place the default fixture takes only 2 trades and neither is
    ambiguous, so it cannot demonstrate this. Picking a seed that does
    is honest; asserting that a random walk must produce one is not."""
    h1_bars = _random_series(seed=4)
    trades = replay(_agg(h1_bars, 168), _agg(h1_bars, 24),
                    _agg(h1_bars, 4), h1_bars, n=2)

    flagged = [t for t in trades if t.same_candle_stop]
    assert flagged, "this fixture does produce them -- 2 of 6"
    assert all(t.outcome == "stop" for t in flagged), \
        "filled then stopped, by assumption, on the same bar"


def test_every_confirmation_form_is_reachable_through_the_driver():
    """A form that is wired but never fires is dead code that looks
    alive, and three of these four were added in one go.

    Seeds chosen because they produce the rare ones: the engulf has by
    far the most opportunities (any two same-direction candles leave a
    level that can be engulfed), so the others need looking for. This is
    a reachability test, not a frequency claim -- the split on a random
    walk says nothing about the split on a market."""
    seen = set()
    for seed in (5, 16, 18):
        h1_bars = _random_series(seed=seed, bars=6000)
        for t in replay(_agg(h1_bars, 168), _agg(h1_bars, 24),
                        _agg(h1_bars, 4), h1_bars, n=2):
            seen.add(t.form)

    wanted = {"engulf", "breakout", "sweep_break", "inducement"}
    assert seen == wanted, f"unreachable: {sorted(wanted - seen)}"


def test_a_setup_ends_when_its_own_liquidity_is_taken_without_us():
    """What gives a setup a lifetime without inventing a candle count
    for one. The premise was an expansion to the next external
    liquidity; if price gets there and we never entered, the move
    happened -- "after external liquidity is taken, expect a reversal"
    (bd2 t=615-645)."""
    from ..orders import OrderBook

    reasons = []
    original = OrderBook.cancel

    def spy(self, key, reason):
        reasons.append(reason)
        return original(self, key, reason)

    OrderBook.cancel = spy
    try:
        h1_bars = _random_series(seed=5, bars=4000)
        replay(_agg(h1_bars, 168), _agg(h1_bars, 24), _agg(h1_bars, 4),
               h1_bars, n=2)
    finally:
        OrderBook.cancel = original

    assert "external liquidity taken without us" in reasons, \
        "the expiry never fired, so setups have no lifetime at all"
    assert "level disrespected" in reasons, "the taught invalidation too"
