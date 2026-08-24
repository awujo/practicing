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
    client = MT5Client(fake, login=1, password="pw", server="Demo")

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
    client = MT5Client(fake, login=1, password="pw", server="Demo")

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
    client = MT5Client(fake, login=1, password="pw", server="Demo")

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
    client = MT5Client(fake, login=1, password="pw", server="Demo")

    sync_recent_from_mt5(client, "EURUSD", source="dukascopy", lookback_count=10)

    raw = cache_module.cache_path("dukascopy", "EURUSD", "H1")
    with open(raw) as f:
        content = f.read()
    assert "+00:00" not in content
    assert content.count("Z") >= 1
