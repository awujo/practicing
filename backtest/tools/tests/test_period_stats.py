"""Tests for the per-period stats tool.

The bucketing is the whole tool: get a boundary wrong and a year's
numbers silently belong to the wrong year, which is not something the
output would ever look odd enough to reveal.
"""

import pandas as pd
import pytest

from ...engine.trade_log import TradeRecord
from ..period_stats import bucket, parse_periods


def _rec(entry_time, status="closed_win", r=1.0):
    return TradeRecord(trade_id=1, instrument="EURUSD",
                       entry_time=pd.Timestamp(entry_time, tz="UTC"),
                       status=status, r_multiple=r)


def test_a_bare_year_expands_to_the_whole_calendar_year():
    (label, start, end), = parse_periods("2025")
    assert label == "2025"
    assert start == pd.Timestamp("2025-01-01", tz="UTC")
    assert end == pd.Timestamp("2026-01-01", tz="UTC")


def test_an_explicit_range_is_inclusive_of_its_last_day():
    """"2025-01-01:2025-06-30" must include everything ON 30 June, not
    stop at midnight as it starts."""
    (_label, start, end), = parse_periods("2025-01-01:2025-06-30")
    assert start == pd.Timestamp("2025-01-01", tz="UTC")
    assert end == pd.Timestamp("2025-07-01", tz="UTC")
    assert bucket([_rec("2025-06-30 23:00")], start, end)


def test_year_boundaries_do_not_overlap_or_leak():
    periods = dict((lbl, (s, e)) for lbl, s, e in parse_periods("2025,2026"))
    last_of_2025 = _rec("2025-12-31 23:00")
    first_of_2026 = _rec("2026-01-01 00:00")

    s25, e25 = periods["2025"]
    s26, e26 = periods["2026"]
    assert bucket([last_of_2025], s25, e25) == [last_of_2025]
    assert bucket([last_of_2025], s26, e26) == []
    assert bucket([first_of_2026], s26, e26) == [first_of_2026]
    assert bucket([first_of_2026], s25, e25) == []


def test_naive_entry_times_are_treated_as_utc_not_crashed_on():
    """A naive/aware comparison raises in pandas, which would abort a
    25-instrument run over a formatting detail."""
    naive = TradeRecord(trade_id=1, instrument="EURUSD",
                        entry_time=pd.Timestamp("2025-05-01 12:00"),
                        status="closed_win", r_multiple=1.0)
    start, end = pd.Timestamp("2025-01-01", tz="UTC"), pd.Timestamp("2026-01-01", tz="UTC")
    assert bucket([naive], start, end) == [naive]


def test_buckets_on_entry_not_exit():
    """A trade opened in December and closed in January belongs to
    December -- the period whose conditions produced the decision."""
    r = _rec("2025-12-30 10:00")
    r.exit_time = pd.Timestamp("2026-01-05 10:00", tz="UTC")
    s25, e25 = parse_periods("2025")[0][1:]
    s26, e26 = parse_periods("2026")[0][1:]
    assert bucket([r], s25, e25) == [r]
    assert bucket([r], s26, e26) == []


def test_defaults_match_the_deployed_launch_flags():
    import argparse
    import sys
    from unittest import mock
    from ..live_flags import LIVE_LAUNCH_FLAGS
    from ..period_stats import main

    parsed = {}
    real = argparse.ArgumentParser.parse_args

    def capture(self, *a, **k):
        parsed.update(vars(real(self, *a, **k)))
        raise SystemExit(0)

    with mock.patch.object(argparse.ArgumentParser, "parse_args", capture), \
            mock.patch.object(sys, "argv", ["period_stats", "--instruments", "NONE"]):
        with pytest.raises(SystemExit):
            main()

    assert parsed["origin_kind"] == LIVE_LAUNCH_FLAGS["origin_kind"]
    assert parsed["stop_anchor"] == LIVE_LAUNCH_FLAGS["stop_anchor"]
    assert parsed["close_based_sweep_break"] is LIVE_LAUNCH_FLAGS["close_based_sweep_break"]
