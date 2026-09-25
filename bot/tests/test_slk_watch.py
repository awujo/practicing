"""
The SLK watcher: it reports, and it never trades.
"""

from __future__ import annotations

import random

import pandas as pd

from backtest.engine.candles import Candle
from backtest.engine.structure import Direction

from ..slk_watch import SLKWatcher, _Collector

T0 = pd.Timestamp("2026-01-01")


class Channel:
    def __init__(self):
        self.messages = []

    def note(self, text):
        self.messages.append(text)
        return True


def series(bars=6000, seed=5):
    random.seed(seed)
    px, out = 1.1000, []
    for i in range(bars):
        o = px
        px += random.gauss(0.00002, 0.0009)
        out.append(Candle(time=T0 + pd.Timedelta(hours=i), open=o,
                          high=max(o, px) + 0.0004, low=min(o, px) - 0.0004,
                          close=px, volume=0))
    return out


def agg(h1, hours):
    out = []
    for i in range(0, len(h1) - hours + 1, hours):
        chunk = h1[i:i + hours]
        out.append(Candle(time=chunk[0].time, open=chunk[0].open,
                          high=max(c.high for c in chunk),
                          low=min(c.low for c in chunk),
                          close=chunk[-1].close, volume=0))
    return out


def loader_for(h1):
    data = {"H1": h1, "H4": agg(h1, 4), "D": agg(h1, 24), "W": agg(h1, 168)}
    return lambda _instrument, code: data[code]


# --- the watermark ------------------------------------------------------

def test_the_first_cycle_sends_nothing_and_only_learns_where_now_is():
    """Years of history are all "new" on the first pass. Reporting them
    would be a flood, and every one of them is already in the past."""
    channel = Channel()
    watcher = SLKWatcher("EURUSD", 2, channel, loader_for(series()))

    assert watcher.check() == 0
    assert channel.messages == []
    assert watcher.watermark is not None


def test_a_second_cycle_with_no_new_candles_stays_silent():
    """The normal case. A cycle that sends nothing must send nothing."""
    channel = Channel()
    watcher = SLKWatcher("EURUSD", 2, channel, loader_for(series()))
    watcher.check()
    assert watcher.check() == 0
    assert channel.messages == []


def test_events_after_the_watermark_are_reported():
    h1 = series()
    channel = Channel()
    watcher = SLKWatcher("EURUSD", 2, channel, loader_for(h1[:4000]))
    watcher.check()

    # the rest of the history arrives
    watcher.load = loader_for(h1)
    watcher.check()
    assert channel.messages, "nothing was reported from 2000 new candles"


def test_the_watermark_advances_so_nothing_is_sent_twice():
    h1 = series()
    channel = Channel()
    watcher = SLKWatcher("EURUSD", 2, channel, loader_for(h1[:4000]))
    watcher.check()
    watcher.load = loader_for(h1)
    watcher.check()
    first = len(channel.messages)
    watcher.check()
    assert len(channel.messages) == first, "the same events were sent again"


# --- what the messages say ----------------------------------------------

def test_messages_carry_the_story_not_just_a_direction():
    """The whole request: "just add english ... I'm reading it and I will
    understand"."""
    h1 = series()
    channel = Channel()
    watcher = SLKWatcher("EURUSD", 2, channel, loader_for(h1[:4000]))
    watcher.check()
    watcher.load = loader_for(h1)
    watcher.check()

    joined = "\n".join(channel.messages)
    assert "EURUSD" in joined
    assert "SLK" in joined, "which engine spoke"
    vocabulary = ("swept", "rejected", "broke structure",
                  "single candle liquidity", "key level")
    assert any(word in joined for word in vocabulary), \
        "no structural English in any message"


def test_a_bias_with_nothing_to_describe_is_not_sent():
    """A message with no story is exactly what was asked against."""
    channel = Channel()
    watcher = SLKWatcher("EURUSD", 2, channel, lambda *_: [])
    sent = watcher._send_bias({"direction": Direction.BULLISH, "was": None,
                                "upper": None, "lower": None, "at": T0})
    assert sent is False
    assert channel.messages == []


# --- the collector ------------------------------------------------------

def test_the_collector_keeps_only_what_is_newer_than_the_watermark():
    c = _Collector(since=T0 + pd.Timedelta(hours=10))
    c.on_setup(at=T0 + pd.Timedelta(hours=5), setup=object())
    c.on_setup(at=T0 + pd.Timedelta(hours=20), setup=object())
    assert len(c.setups) == 1


def test_a_collector_with_no_watermark_keeps_everything():
    c = _Collector(since=None)
    c.on_setup(at=T0, setup=object())
    assert len(c.setups) == 1


def test_a_bias_event_with_no_direction_is_not_an_event():
    c = _Collector(since=None)
    c.on_bias(at=T0, direction=None)
    assert c.bias == []


# --- it cannot trade -----------------------------------------------------

def test_the_watcher_has_no_route_to_an_execution_client():
    """Not an omission -- the design. There is no import in this module
    that could reach MT5 execution, and this test fails if one appears."""
    import inspect

    from .. import slk_watch

    source = inspect.getsource(slk_watch)
    for forbidden in ("mt5_execution", "MT5Execution", "order_send",
                      "place_market_order", "place_limit"):
        assert forbidden not in source, f"{forbidden} reached the watcher"


def test_a_broken_channel_never_stops_the_watching():
    class Exploding:
        def note(self, _text):
            raise RuntimeError("telegram is down")

    h1 = series()
    watcher = SLKWatcher("EURUSD", 2, Exploding(), loader_for(h1[:4000]))
    watcher.check()
    watcher.load = loader_for(h1)
    try:
        watcher.check()
    except RuntimeError:
        raise AssertionError("a dead channel took down the watcher")


def test_each_instrument_gets_its_own_story_not_a_one_line_badge():
    """Operator, 2026-09-25: "it shouldn't even be coming as a badge ...
    it should be coming individual ... it's not even saying what the
    daily did, it's not saying what the weekly did."

    A one-liner cannot say any of that, and because it has to pick ONE
    thing to name, the version this replaced named the Daily route every
    time -- reporting "key level rejected" for all 27 instruments
    regardless of what had actually carried the bias."""
    h1 = series()
    watcher = SLKWatcher("EURUSD", 2, Channel(), loader_for(h1))
    watcher.check()

    story = watcher.standing_story()
    assert story, "no story at all"
    assert "EURUSD" in story
    assert "says" in story, "which rung said what"
    assert "Next:" in story, "and what to watch for now"
    assert story.count("\n") > 3, "a story, not a line"


def test_the_story_always_accounts_for_the_weekly():
    """"How is Daily leading in all of the pairs? It shows the Weekly
    isn't factored in."

    Whether the two agree is what separates a high-probability setup from
    one that may be nothing but a retracement inside the Weekly, so the
    Weekly is named either way -- with its own story when it has one, and
    saying so plainly when it does not."""
    h1 = series()
    watcher = SLKWatcher("EURUSD", 2, Channel(), loader_for(h1))
    watcher.check()
    story = watcher.standing_story()

    assert "Weekly" in story, "the Weekly is never silently omitted"
    states = ("ALIGNED", "NOT ALIGNED", "no Weekly bias yet",
              "Daily has not confirmed")
    assert any(state in story for state in states), \
        f"no alignment state in the headline: {story.splitlines()[0]}"


def test_no_bias_means_no_story_rather_than_an_empty_shell():
    watcher = SLKWatcher("EURUSD", 2, Channel(), lambda *_: [])
    assert watcher.standing_story() == ""
