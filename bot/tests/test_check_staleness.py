"""Tests for check_staleness.py -- the standalone cache-freshness watchdog."""

from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from bot.check_staleness import _expected_latest_open_time, _market_closed_for_weekend, check


def _utc(y, m, d, h, mi=0):
    return datetime(y, m, d, h, mi, tzinfo=timezone.utc)


def test_expected_latest_open_time_is_the_previous_full_hour():
    now = _utc(2026, 9, 8, 14, 37)   # mid-candle, a Tuesday
    assert str(_expected_latest_open_time(now)) == "2026-09-08 13:00:00+00:00"


def test_weekday_is_never_weekend_closed():
    assert not _market_closed_for_weekend(_utc(2026, 9, 9, 12))   # Wednesday


def test_saturday_is_weekend_closed():
    assert _market_closed_for_weekend(_utc(2026, 9, 12, 12))   # Saturday


def test_sunday_before_open_is_weekend_closed():
    assert _market_closed_for_weekend(_utc(2026, 9, 13, 10))   # Sunday morning UTC (before NY 17:00)


def test_friday_after_close_is_weekend_closed():
    # Friday 22:00 UTC = 18:00 EDT, past the 17:00 New York close.
    assert _market_closed_for_weekend(_utc(2026, 9, 11, 22))


def test_friday_afternoon_before_close_is_not_weekend_closed():
    assert not _market_closed_for_weekend(_utc(2026, 9, 11, 14))


def test_fresh_cache_is_not_reported_stale():
    now = _utc(2026, 9, 8, 14, 5)   # Tuesday
    with patch("bot.check_staleness.cache.last_cached_time", return_value="2026-09-08T13:00:00Z"):
        assert check(["EURUSD"], "dukascopy", 90.0, now=now) == []


def test_cache_older_than_the_threshold_is_reported():
    now = _utc(2026, 9, 8, 20, 0)   # expects the 19:00 bar; cache has 13:00 -> 360 min stale
    with patch("bot.check_staleness.cache.last_cached_time", return_value="2026-09-08T13:00:00Z"):
        stale = check(["EURUSD"], "dukascopy", 90.0, now=now)
    assert len(stale) == 1
    instrument, minutes, detail = stale[0]
    assert instrument == "EURUSD"
    assert minutes == pytest.approx(360.0)


def test_never_cached_instrument_is_reported_without_a_crash():
    now = _utc(2026, 9, 8, 14, 0)
    with patch("bot.check_staleness.cache.last_cached_time", return_value=None):
        stale = check(["NEWSYMBOL"], "dukascopy", 90.0, now=now)
    assert stale == [("NEWSYMBOL", None, "no cache at all")]


def test_unreadable_cache_is_reported_without_a_crash():
    now = _utc(2026, 9, 8, 14, 0)
    with patch("bot.check_staleness.cache.last_cached_time", side_effect=OSError("boom")):
        stale = check(["EURUSD"], "dukascopy", 90.0, now=now)
    assert len(stale) == 1
    assert stale[0][0] == "EURUSD"
    assert stale[0][1] is None
    assert "boom" in stale[0][2]


def test_nothing_is_reported_stale_over_a_closed_weekend_even_with_old_data():
    now = _utc(2026, 9, 13, 10, 0)   # Sunday, before reopen
    with patch("bot.check_staleness.cache.last_cached_time", return_value="2026-09-11T20:00:00Z"):
        assert check(["EURUSD"], "dukascopy", 90.0, now=now) == []


def test_one_stale_instrument_does_not_block_reporting_the_rest():
    now = _utc(2026, 9, 8, 14, 0)
    values = {"EURUSD": "2026-09-08T13:00:00Z", "GBPJPY": "2026-09-06T09:00:00Z"}
    with patch("bot.check_staleness.cache.last_cached_time", side_effect=lambda s, i, g: values[i]):
        stale = check(["EURUSD", "GBPJPY"], "dukascopy", 90.0, now=now)
    assert [s[0] for s in stale] == ["GBPJPY"]
