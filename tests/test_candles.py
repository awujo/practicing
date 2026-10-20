"""Calendar completion must not depend on the final sample present in a feed."""
import pandas as pd
import pytest

from bishop.candles import completed, nominal_end, resample


def bars(start, periods):
    index = pd.date_range(start, periods=periods, freq="h")
    return pd.DataFrame({"open": 1., "high": 2., "low": .5, "close": 1.5}, index=index)


@pytest.mark.parametrize("tf,end", [
    ("H1", "2026-10-20T22:00:00Z"), ("H2", "2026-10-20T23:00:00Z"),
    ("H4", "2026-10-21T01:00:00Z"), ("D", "2026-10-21T21:00:00Z"),
    ("W", "2026-10-23T21:00:00Z"), ("M", "2026-10-31T21:00:00Z"),
])
def test_all_timeframe_calendar_closes(tf, end):
    assert nominal_end("2026-10-20T21:00:00Z", tf) == pd.Timestamp(end)


def test_partial_daily_bar_reports_nominal_not_observed_end():
    h1 = bars("2026-10-20T21:00:00Z", 2)
    daily = resample(h1, "D")
    assert daily.iloc[0]["end"] == pd.Timestamp("2026-10-21T21:00:00Z")
    assert completed(h1, "D", "2026-10-20T23:00:00Z").empty


def test_hour_completion_and_higher_timeframe_completion_both_required():
    h1 = bars("2026-10-20T21:00:00Z", 5)
    before = completed(h1, "H4", "2026-10-21T00:59:59Z")
    assert before.empty
    at_close = completed(h1, "H4", "2026-10-21T01:00:00Z")
    assert len(at_close) == 1
    # The 01:00 H1 bar is still forming and must not contaminate the first H4.
    h1.loc[pd.Timestamp("2026-10-21T01:00:00Z"), "high"] = 999
    assert completed(h1, "H4", "2026-10-21T01:00:00Z").iloc[0]["high"] == 2


@pytest.mark.parametrize("start,tf,end", [
    ("2026-01-20T22:00Z", "D", "2026-01-21T22:00Z"),
    ("2026-07-20T21:00Z", "D", "2026-07-21T21:00Z"),
    ("2026-03-08T06:00Z", "H4", "2026-03-08T09:00Z"),
    ("2026-11-01T05:00Z", "H4", "2026-11-01T10:00Z"),
    ("2026-11-01T06:00Z", "H4", "2026-11-01T10:00Z"),
    ("2026-10-31T21:00Z", "H4", "2026-11-01T01:00Z"),
    ("2026-03-01T22:00Z", "M", "2026-03-31T21:00Z"),
    ("2026-10-01T21:00Z", "M", "2026-10-31T21:00Z"),
    ("2026-11-01T22:00Z", "W", "2026-11-06T22:00Z"),
])
def test_session_clock_handles_dst_and_calendar_edges(start, tf, end):
    assert nominal_end(start, tf) == pd.Timestamp(end)


def test_missing_opening_hours_do_not_move_bin_close():
    h1 = bars("2026-10-20T23:00Z", 2)
    assert resample(h1, "H4").iloc[0]["end"] == pd.Timestamp("2026-10-21T01:00Z")


def test_empty_completed_input_retains_expected_columns():
    h1 = bars("2026-10-20T21:00Z", 1)
    result = completed(h1, "H4", "2026-10-20T21:00Z")
    assert result.empty
    assert list(result.columns) == ["open", "high", "low", "close", "start", "end"]


def test_naive_clocks_and_unknown_timeframes_rejected():
    with pytest.raises(ValueError, match="timezone"):
        nominal_end("2026-10-20 21:00", "H4")
    with pytest.raises(ValueError, match="timezone"):
        completed(bars("2026-10-20T21:00Z", 1), "D", "2026-10-21")
    with pytest.raises(ValueError):
        nominal_end("2026-10-20T21:00Z", "H3")
