"""Input integrity checks; a partial cache cannot certify historical coverage."""
import pandas as pd
import pytest

from bishop.coverage import coverage, expected_hours, validate_hourly, load_csv


def frame():
    return pd.DataFrame({"open": [1., 1.1], "high": [1.2, 1.3], "low": [.9, 1.], "close": [1.1, 1.2]},
                        index=pd.date_range("2026-01-05T10:00Z", periods=2, freq="h"))


def test_missing_hour_is_not_proved_complete_by_later_endpoint():
    data = frame()
    data.index = pd.to_datetime(["2026-01-05T10:00Z", "2026-01-05T12:00Z"])
    result = coverage(data, "2026-01-05T10:00Z", "2026-01-05T13:00Z")
    assert result["status"] == "INCOMPLETE" and result["missing_hours"] == 1
    assert result["missing_first_100"] == ["2026-01-05T11:00:00+00:00"]


def test_weekend_calendar_tracks_dst_in_elapsed_utc_hours():
    wanted = expected_hours("2026-03-06T21:00Z", "2026-03-08T23:00Z")
    assert list(wanted) == list(pd.to_datetime(["2026-03-06T21:00Z", "2026-03-08T21:00Z", "2026-03-08T22:00Z"]))


@pytest.mark.parametrize("kind", ["duplicate", "unordered", "geometry", "forming", "half_hour_utc"])
def test_malformed_or_forming_hourly_data_fails_closed(kind):
    data = frame()
    if kind == "duplicate": data.index = [data.index[0], data.index[0]]
    if kind == "unordered": data = data.iloc[::-1]
    if kind == "geometry": data.loc[data.index[0], "high"] = .8
    if kind == "half_hour_utc": data.index = data.index + pd.Timedelta(minutes=30)
    with pytest.raises(ValueError):
        validate_hourly(data, as_of="2026-01-05T11:30Z" if kind == "forming" else "2026-01-06T00:00Z")


def test_csv_prefix_excludes_future_candles_and_retains_input_hash(tmp_path):
    path = tmp_path / "frozen.csv"
    frame().to_csv(path)
    prefix, digest = load_csv(path, as_of="2026-01-05T11:00Z")
    full, same = load_csv(path, as_of="2026-01-05T12:00Z")
    assert len(prefix) == 1 and len(full) == 2 and digest == same and len(digest) == 64
