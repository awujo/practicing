from unittest.mock import patch

import pandas as pd

from backtest.data_pipeline import cache as cache_module

from .fake_mt5 import FakeMT5, make_rate
from ..live_cache_sync import bootstrap_historical_cache, sync_recent_from_mt5
from ..mt5_data import MT5Client

DAY = 86400


def test_bootstrap_historical_cache_delegates_to_data_access(tmp_path):
    with patch("bot.live_cache_sync.data_access.ensure_instrument_cache", return_value=str(tmp_path)) as mock:
        result = bootstrap_historical_cache("EURUSD", source="dukascopy")
    mock.assert_called_once_with("EURUSD", source="dukascopy")
    assert result == str(tmp_path)


def test_sync_recent_from_mt5_appends_candles_readable_via_the_normal_cache_load(tmp_path, monkeypatch):
    monkeypatch.setattr(cache_module, "DATA_ROOT", str(tmp_path))

    fake = FakeMT5()
    # Row 0 is the still-forming bar (skipped by fetch_candles), the rest closed.
    fake.rates_by_symbol_timeframe[("EURUSD", "H1")] = [
        make_rate(4 * DAY, 1.12, 1.14, 1.11, 1.13),
        make_rate(2 * DAY, 1.10, 1.12, 1.09, 1.11),
        make_rate(3 * DAY, 1.11, 1.13, 1.10, 1.12),
    ]
    fake.rates_by_symbol_timeframe[("EURUSD", "D1")] = [make_rate(4 * DAY, 1.12, 1.14, 1.11, 1.13)]
    fake.rates_by_symbol_timeframe[("EURUSD", "H4")] = [make_rate(4 * DAY, 1.12, 1.14, 1.11, 1.13)]
    fake.rates_by_symbol_timeframe[("EURUSD", "W1")] = [make_rate(4 * DAY, 1.12, 1.14, 1.11, 1.13)]
    client = MT5Client(fake, login=1, password="pw", server="Demo", server_utc_offset=pd.Timedelta(0))

    appended = sync_recent_from_mt5(client, "EURUSD", source="dukascopy", lookback_count=10)
    assert appended["H1"] == 2

    df = cache_module.load("dukascopy", "EURUSD", "H1")
    assert len(df) == 2
    assert list(df["close"]) == [1.11, 1.12]


def test_sync_recent_from_mt5_dedupes_on_repeated_calls(tmp_path, monkeypatch):
    monkeypatch.setattr(cache_module, "DATA_ROOT", str(tmp_path))
    fake = FakeMT5()
    fake.rates_by_symbol_timeframe[("EURUSD", "H1")] = [
        make_rate(4 * DAY, 1.12, 1.14, 1.11, 1.13),
        make_rate(2 * DAY, 1.10, 1.12, 1.09, 1.11),
    ]
    fake.rates_by_symbol_timeframe[("EURUSD", "D1")] = []
    fake.rates_by_symbol_timeframe[("EURUSD", "H4")] = []
    fake.rates_by_symbol_timeframe[("EURUSD", "W1")] = []
    client = MT5Client(fake, login=1, password="pw", server="Demo", server_utc_offset=pd.Timedelta(0))

    sync_recent_from_mt5(client, "EURUSD", source="dukascopy", lookback_count=10)
    sync_recent_from_mt5(client, "EURUSD", source="dukascopy", lookback_count=10)  # same data again

    df = cache_module.load("dukascopy", "EURUSD", "H1")
    assert len(df) == 1  # not duplicated


def test_sync_recent_from_mt5_merges_onto_existing_bootstrapped_history(tmp_path, monkeypatch):
    monkeypatch.setattr(cache_module, "DATA_ROOT", str(tmp_path))
    # Simulate a prior bootstrap: some older history already on disk.
    cache_module.append("dukascopy", "EURUSD", "H1", [
        {"time": pd.Timestamp(1 * DAY, unit="s", tz="UTC").isoformat().replace("+00:00", "Z"),
         "open": 1.08, "high": 1.09, "low": 1.07, "close": 1.085, "volume": 500.0},
    ])

    fake = FakeMT5()
    fake.rates_by_symbol_timeframe[("EURUSD", "H1")] = [
        make_rate(4 * DAY, 1.12, 1.14, 1.11, 1.13),  # forming
        make_rate(3 * DAY, 1.11, 1.13, 1.10, 1.12),  # new, closed
    ]
    fake.rates_by_symbol_timeframe[("EURUSD", "D1")] = []
    fake.rates_by_symbol_timeframe[("EURUSD", "H4")] = []
    fake.rates_by_symbol_timeframe[("EURUSD", "W1")] = []
    client = MT5Client(fake, login=1, password="pw", server="Demo", server_utc_offset=pd.Timedelta(0))

    sync_recent_from_mt5(client, "EURUSD", source="dukascopy", lookback_count=10)

    df = cache_module.load("dukascopy", "EURUSD", "H1")
    assert len(df) == 2  # the old bootstrapped row + the new MT5 row, merged


def test_sync_recent_from_mt5_writes_time_in_the_same_iso_format_as_the_rest_of_the_pipeline(tmp_path, monkeypatch):
    # Confirmed live: writing plain isoformat() (keeps "+00:00") instead of
    # the "Z"-suffixed format every other writer in the data pipeline uses
    # (dukascopy_client.py, fetch_crypto.py, resample.py) mixes two ISO
    # variants in one CSV column. pandas then partially fails to parse it,
    # leaving some rows as real Timestamps and others as raw strings --
    # which crashed run_backtest() with a real TypeError comparing them,
    # taking down the live bot entirely. This checks the raw file content,
    # not just that pandas can eventually make sense of it.
    monkeypatch.setattr(cache_module, "DATA_ROOT", str(tmp_path))
    fake = FakeMT5()
    fake.rates_by_symbol_timeframe[("EURUSD", "H1")] = [
        make_rate(4 * DAY, 1.12, 1.14, 1.11, 1.13),  # forming
        make_rate(2 * DAY, 1.10, 1.12, 1.09, 1.11),
    ]
    fake.rates_by_symbol_timeframe[("EURUSD", "D1")] = []
    fake.rates_by_symbol_timeframe[("EURUSD", "H4")] = []
    fake.rates_by_symbol_timeframe[("EURUSD", "W1")] = []
    client = MT5Client(fake, login=1, password="pw", server="Demo", server_utc_offset=pd.Timedelta(0))

    sync_recent_from_mt5(client, "EURUSD", source="dukascopy", lookback_count=10)

    raw = cache_module.cache_path("dukascopy", "EURUSD", "H1")
    with open(raw) as f:
        content = f.read()
    assert "+00:00" not in content
    assert content.count("Z") >= 1


# ---------------------------------------------------------------------------
# H4/D/W must never come from MT5 again.
#
# They used to. MT5 anchors bars to broker midnight (UTC+3, so H4 on
# 01/05/09/13/17/21 UTC, D on 21:00, W on Saturday 21:00); Dukascopy
# anchors to UTC midnight. Appending one series onto the other produced
# bars covering overlapping spans, and cache.append()'s dedupe-by-
# timestamp could not see it. Undetected 2026-08-19 to 2026-09-16.
# ---------------------------------------------------------------------------

def _seed_h1(tmp_path, symbol="EURUSD", start="2026-08-03", days=30):
    idx = pd.date_range(start, periods=24 * days, freq="h", tz="UTC")
    rows = [{"time": t.isoformat().replace("+00:00", "Z"), "open": 1.10,
             "high": 1.11, "low": 1.09, "close": 1.105, "volume": 1.0}
            for t in idx]
    cache_module.append("dukascopy", symbol, "H1", rows)


def test_only_h1_is_ever_fetched_from_the_broker(tmp_path, monkeypatch):
    monkeypatch.setattr(cache_module, "DATA_ROOT", str(tmp_path))
    _seed_h1(tmp_path)

    fake = FakeMT5()
    fake.rates_by_symbol_timeframe[("EURUSD", "H1")] = [
        make_rate(4 * DAY, 1.12, 1.14, 1.11, 1.13),
        make_rate(2 * DAY, 1.10, 1.12, 1.09, 1.11),
    ]
    client = MT5Client(fake, login=1, password="pw", server="Demo",
                       server_utc_offset=pd.Timedelta(0))
    fetched = []
    real = client.fetch_candles

    def spy(instrument, granularity, count):
        fetched.append(granularity)
        return real(instrument, granularity, count=count)

    client.fetch_candles = spy
    sync_recent_from_mt5(client, "EURUSD", source="dukascopy", lookback_count=10)

    assert fetched == ["H1"], f"H4/D/W must not be fetched from MT5, got {fetched}"


def test_derived_h4_lands_on_the_utc_grid_not_the_broker_grid(tmp_path, monkeypatch):
    monkeypatch.setattr(cache_module, "DATA_ROOT", str(tmp_path))
    _seed_h1(tmp_path)

    fake = FakeMT5()
    fake.rates_by_symbol_timeframe[("EURUSD", "H1")] = [
        make_rate(4 * DAY, 1.12, 1.14, 1.11, 1.13),
        make_rate(2 * DAY, 1.10, 1.12, 1.09, 1.11),
    ]
    client = MT5Client(fake, login=1, password="pw", server="Demo",
                       server_utc_offset=pd.Timedelta(0))
    sync_recent_from_mt5(client, "EURUSD", source="dukascopy", lookback_count=10)

    h4 = cache_module.load("dukascopy", "EURUSD", "H4")
    hours = sorted(pd.to_datetime(h4["time"], utc=True).dt.hour.unique())
    assert hours == [0, 4, 8, 12, 16, 20]
    assert 1 not in hours and 21 not in hours  # the broker grid, specifically

    d = cache_module.load("dukascopy", "EURUSD", "D")
    assert sorted(pd.to_datetime(d["time"], utc=True).dt.hour.unique()) == [0]
    w = cache_module.load("dukascopy", "EURUSD", "W")
    wt = pd.to_datetime(w["time"], utc=True)
    assert sorted(wt.dt.hour.unique()) == [0]
    assert sorted(wt.dt.dayofweek.unique()) == [0]


def test_repeated_syncs_never_accumulate_overlapping_bars(tmp_path, monkeypatch):
    """The failure mode in one assertion: the old path grew the file on
    every call because each new grid's timestamps looked new. Derived
    bars are rewritten in place, so the row count must stay put."""
    monkeypatch.setattr(cache_module, "DATA_ROOT", str(tmp_path))
    _seed_h1(tmp_path)

    fake = FakeMT5()
    fake.rates_by_symbol_timeframe[("EURUSD", "H1")] = [
        make_rate(4 * DAY, 1.12, 1.14, 1.11, 1.13),
        make_rate(2 * DAY, 1.10, 1.12, 1.09, 1.11),
    ]
    client = MT5Client(fake, login=1, password="pw", server="Demo",
                       server_utc_offset=pd.Timedelta(0))

    sync_recent_from_mt5(client, "EURUSD", source="dukascopy", lookback_count=10)
    first = len(cache_module.load("dukascopy", "EURUSD", "H4"))
    for _ in range(3):
        sync_recent_from_mt5(client, "EURUSD", source="dukascopy", lookback_count=10)
    after = cache_module.load("dukascopy", "EURUSD", "H4")

    assert len(after) == first
    t = pd.to_datetime(after["time"], utc=True).sort_values()
    gaps = t.diff().dropna().dt.total_seconds() / 3600
    assert (gaps >= 4).all(), "no H4 bar may sit closer than 4h to the previous"


# ---------------------------------------------------------------------------
# A derived bar must never be written before its period has finished.
#
# Found live 2026-09-16 from the Telegram feed: JP225 reported
# "H4 (bullish) ... H4@2026-09-15 20:00" and then, 19 seconds later from
# the same process, "aligned bearish ... H4@2026-09-14 08:00" -- the
# confirmation moved BACKWARDS in time and flipped direction. _derive_tail
# dropped the first derived bar but not the last, so the in-progress 4H
# bin was being written as though complete and rewritten with different
# OHLC on every sync as its remaining hours arrived.
#
# The MT5 path this replaced fetched with start=1, which skips the
# forming bar. Deriving has to do the equivalent explicitly.
# ---------------------------------------------------------------------------

def _sync_with_h1_ending(tmp_path, monkeypatch, last_hour):
    """Seed H1 up to and including `last_hour`, then sync."""
    monkeypatch.setattr(cache_module, "DATA_ROOT", str(tmp_path))
    idx = pd.date_range("2026-08-03", last_hour, freq="h", tz="UTC")
    cache_module.append("dukascopy", "EURUSD", "H1",
                        [{"time": t.isoformat().replace("+00:00", "Z"), "open": 1.10,
                          "high": 1.11, "low": 1.09, "close": 1.105, "volume": 1.0}
                         for t in idx])
    fake = FakeMT5()
    fake.rates_by_symbol_timeframe[("EURUSD", "H1")] = [
        make_rate(4 * DAY, 1.12, 1.14, 1.11, 1.13),
        make_rate(2 * DAY, 1.10, 1.12, 1.09, 1.11),
    ]
    client = MT5Client(fake, login=1, password="pw", server="Demo",
                       server_utc_offset=pd.Timedelta(0))
    sync_recent_from_mt5(client, "EURUSD", source="dukascopy", lookback_count=10)
    h4 = cache_module.load("dukascopy", "EURUSD", "H4")
    return pd.to_datetime(h4["time"], utc=True).max()


def test_an_unfinished_h4_bin_is_not_written(tmp_path, monkeypatch):
    """H1 ends at 21:00, which covers through 22:00 -- so the 20:00 4H bin
    (20:00-00:00) is only half done and must not appear."""
    newest = _sync_with_h1_ending(tmp_path, monkeypatch, "2026-08-20 21:00")
    assert newest < pd.Timestamp("2026-08-20 20:00", tz="UTC")


def test_a_finished_h4_bin_is_written(tmp_path, monkeypatch):
    """H1 ends at 23:00, covering through 00:00, so the 20:00 bin is
    complete and must appear -- the guard has to stop at incomplete bars,
    not at recent ones."""
    newest = _sync_with_h1_ending(tmp_path, monkeypatch, "2026-08-20 23:00")
    assert newest == pd.Timestamp("2026-08-20 20:00", tz="UTC")


def test_the_newest_derived_bar_stops_changing_once_written(tmp_path, monkeypatch):
    """The actual failure: the same bar meaning something different on
    each sync. Sync at 21:00 and again at 23:00; any bar present in both
    must be byte-identical."""
    monkeypatch.setattr(cache_module, "DATA_ROOT", str(tmp_path))

    def seed_and_sync(last_hour):
        idx = pd.date_range("2026-08-03", last_hour, freq="h", tz="UTC")
        cache_module.append("dukascopy", "EURUSD", "H1",
                            [{"time": t.isoformat().replace("+00:00", "Z"),
                              "open": 1.10 + i * 1e-5, "high": 1.11 + i * 1e-5,
                              "low": 1.09 + i * 1e-5, "close": 1.105 + i * 1e-5,
                              "volume": 1.0} for i, t in enumerate(idx)])
        fake = FakeMT5()
        fake.rates_by_symbol_timeframe[("EURUSD", "H1")] = [
            make_rate(4 * DAY, 1.12, 1.14, 1.11, 1.13),
            make_rate(2 * DAY, 1.10, 1.12, 1.09, 1.11),
        ]
        client = MT5Client(fake, login=1, password="pw", server="Demo",
                           server_utc_offset=pd.Timedelta(0))
        sync_recent_from_mt5(client, "EURUSD", source="dukascopy", lookback_count=10)
        df = cache_module.load("dukascopy", "EURUSD", "H4")
        df["time"] = pd.to_datetime(df["time"], utc=True)
        return df.set_index("time")

    first = seed_and_sync("2026-08-20 21:00")
    second = seed_and_sync("2026-08-20 23:00")

    shared = first.index.intersection(second.index)
    assert len(shared) > 0
    pd.testing.assert_frame_equal(first.loc[shared], second.loc[shared])
