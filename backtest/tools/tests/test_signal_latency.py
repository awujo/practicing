"""Tests for the signal-latency tool's truncation.

Everything the tool concludes rests on one thing: that the candle set it
hands run_backtest() is the set that genuinely existed at the as-of
instant. Leak a single unclosed bar and the measurement quietly acquires
the look-ahead it was built to detect, and reports "the signal existed
immediately" for a signal that did not.
"""

import pandas as pd
import pytest

from ...engine.candles import Candle
from ...tools.signal_latency import truncating_loader, parse_targets, BAR_LENGTH


def _c(t):
    return Candle(time=pd.Timestamp(t, tz="UTC"), open=1.0, high=1.1,
                  low=0.9, close=1.05, volume=1.0)


@pytest.fixture
def patched(monkeypatch):
    def install(series):
        def fake(source, symbol, granularity):
            return list(series[granularity])
        monkeypatch.setattr("backtest.tools.signal_latency.real_load_candles", fake)
    return install


def test_a_bar_still_forming_is_excluded(patched):
    """The Daily bar stamped 09-09 00:00 does not exist as a candle at
    09-09 15:00 -- including it would show the replay a full day's high
    and low nine hours before the day ends."""
    patched({"D": [_c("2026-09-08"), _c("2026-09-09"), _c("2026-09-10")]})
    got = truncating_loader(pd.Timestamp("2026-09-09 15:00", tz="UTC"))("x", "y", "D")
    assert [c.time for c in got] == [pd.Timestamp("2026-09-08", tz="UTC")]


def test_a_bar_closing_exactly_at_the_as_of_instant_is_included(patched):
    patched({"H1": [_c("2026-09-09 13:00"), _c("2026-09-09 14:00")]})
    got = truncating_loader(pd.Timestamp("2026-09-09 15:00", tz="UTC"))("x", "y", "H1")
    assert [c.time for c in got] == [pd.Timestamp("2026-09-09 13:00", tz="UTC"),
                                     pd.Timestamp("2026-09-09 14:00", tz="UTC")]


def test_each_granularity_uses_its_own_bar_length(patched):
    """At 17:30 the 16:00 H1 bar has closed and the 16:00 H4 bar has
    not -- same timestamp, opposite answers, which is the whole reason
    truncation is per granularity rather than one global cut."""
    at = pd.Timestamp("2026-09-09 17:30", tz="UTC")
    patched({"H4": [_c("2026-09-09 16:00")], "H1": [_c("2026-09-09 16:00")]})
    assert truncating_loader(at)("x", "y", "H4") == []
    assert len(truncating_loader(at)("x", "y", "H1")) == 1


def test_weekly_needs_a_full_week(patched):
    patched({"W": [_c("2026-09-07"), _c("2026-09-14")]})
    got = truncating_loader(pd.Timestamp("2026-09-16", tz="UTC"))("x", "y", "W")
    assert [c.time for c in got] == [pd.Timestamp("2026-09-07", tz="UTC")]


def test_an_unknown_granularity_falls_back_to_the_timestamp(patched):
    """M15 and friends have no entry in BAR_LENGTH. Dropping them
    entirely would be worse than a one-bar-optimistic cut, but the
    fallback must still cut somewhere rather than returning everything."""
    assert "M15" not in BAR_LENGTH
    patched({"M15": [_c("2026-09-09 12:00"), _c("2026-09-09 18:00")]})
    got = truncating_loader(pd.Timestamp("2026-09-09 15:00", tz="UTC"))("x", "y", "M15")
    assert [c.time for c in got] == [pd.Timestamp("2026-09-09 12:00", tz="UTC")]


def test_nothing_is_available_before_the_first_bar_closes(patched):
    patched({"H1": [_c("2026-09-09 14:00")]})
    assert truncating_loader(pd.Timestamp("2026-09-09 14:30", tz="UTC"))("x", "y", "H1") == []


def test_targets_parse_to_utc_timestamps():
    got = parse_targets("chfjpy@2026-09-09T14:00, AUDUSD@2026-09-11T10:00")
    assert got == [("CHFJPY", pd.Timestamp("2026-09-09 14:00", tz="UTC")),
                   ("AUDUSD", pd.Timestamp("2026-09-11 10:00", tz="UTC"))]


def test_a_target_without_a_time_is_rejected_loudly():
    with pytest.raises(SystemExit):
        parse_targets("CHFJPY")
