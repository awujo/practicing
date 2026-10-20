"""Independent final integration review: warmup boundaries are not complete bars.

Synthetic calendar cases and retained actual-feed plumbing are engineering
checks, never teacher-example acceptance fixtures.
"""
from pathlib import Path

import pandas as pd

from bishop import bias, coverage, engine
from bishop.execution import Costs

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data/examples/EURGBP_pdf_p08_icmarkets_bid_H1.csv.gz"


def sample(hours):
    return pd.DataFrame({"open": 1.1, "high": 1.2, "low": 1., "close": 1.15}, index=hours)


def config():
    return dict(pair="EURGBP", as_of="2026-07-24T00:00Z", history_start="2026-06-01T00:00Z",
                scan_start="2026-06-01T00:00Z", origin_tf="D", entry_tf="H2",
                level_mode="close_reference", stop_profile="structural_wick",
                costs=Costs(1., .2, .5), pending_hours=24)


def test_complete_requested_warmup_cannot_send_truncated_day_or_h4_into_bias(monkeypatch):
    data, _ = coverage.load_csv(DATA, as_of=config()["as_of"])
    seen = {}
    def inspect(origin, confirmation, **kwargs):
        seen["origin"] = origin
        seen["confirmation"] = confirmation
        return []
    monkeypatch.setattr(bias, "find_stories", inspect)
    result = engine.run(data, **config())
    assert result["coverage"]["status"] == "COMPLETE"
    # June1 00UTC is three hours into the NewYork day and three hours
    # into the H4 bin which began May31 21UTC. Closed partial bins cannot
    # define early turning points or targets.
    assert seen["origin"].iloc[0].start == pd.Timestamp("2026-06-01T21:00Z")
    assert seen["confirmation"].iloc[0].start == pd.Timestamp("2026-06-01T01:00Z")


def test_leading_partial_day_and_two_hour_bar_are_discarded_independently():
    times = coverage.expected_hours("2026-06-01T00:00Z", "2026-06-03T21:00Z")
    data = sample(times)
    daily = coverage.completed_from_complete_history(data, "D", as_of="2026-06-03T21:00Z")[0]
    h2 = coverage.completed_from_complete_history(data, "H2", as_of="2026-06-03T21:00Z")[0]
    assert daily.iloc[0].start == pd.Timestamp("2026-06-01T21:00Z")
    assert h2.iloc[0].start == pd.Timestamp("2026-06-01T01:00Z")
    assert list(daily.end) == list(pd.to_datetime(["2026-06-02T21:00Z", "2026-06-03T21:00Z"]))


def test_closed_weekend_hours_do_not_falsely_make_a_month_incomplete_across_dst():
    # Nov2026 starts on Sunday. Its nominal monthly boundary falls on a
    # closed Saturday; first actual market hour is Sunday17NY after DST.
    times = coverage.expected_hours("2026-10-31T21:00Z", "2026-11-30T22:00Z")
    assert times[0] == pd.Timestamp("2026-11-01T22:00Z")
    monthly = coverage.completed_from_complete_history(sample(times), "M", as_of="2026-11-30T22:00Z")[0]
    assert len(monthly) == 1
    assert monthly.iloc[0].start == times[0]
    assert monthly.iloc[0].end == pd.Timestamp("2026-11-30T22:00Z")


def test_only_incomplete_aggregate_yields_no_usable_higher_timeframe_bar():
    times = pd.date_range("2026-06-01T00:00Z", periods=4, freq="h")
    assert coverage.completed_from_complete_history(sample(times), "D", as_of="2026-06-01T21:00Z")[0].empty


def test_complete_hourly_bar_does_not_require_previous_day_warmup():
    times = pd.date_range("2026-06-01T00:00Z", periods=3, freq="h")
    bars = coverage.completed_from_complete_history(sample(times), "H1", as_of="2026-06-01T03:00Z")[0]
    assert len(bars) == 3 and bars.iloc[0].start == times[0]


def test_later_observation_cannot_hide_an_order_issued_inside_no_trade_window():
    from bishop.replay import check_example
    from test_replay import candidate, example
    ex = example()
    ex.update(kind="no_trade", entry=None, stop=None, target=None)
    no_trade = candidate(status="NO_TRADE", entry=None, stop=None, target=None)
    pending = candidate(status="PENDING", time=None, setup_time="2026-01-02T10:15:00Z",
                        observed_at="2026-01-02T12:00:00Z")
    assert check_example(ex, [no_trade, pending])["status"] == "FAIL"


def test_later_fill_cannot_hide_an_order_issued_inside_no_trade_window():
    from bishop.replay import check_example
    from test_replay import candidate, example
    ex = example()
    ex.update(kind="no_trade", entry=None, stop=None, target=None)
    no_trade = candidate(status="NO_TRADE", entry=None, stop=None, target=None)
    filled = candidate(setup_time="2026-01-02T10:15:00Z", time="2026-01-02T12:00:00Z")
    assert check_example(ex, [no_trade, filled])["status"] == "FAIL"
