"""Test isolation: never touch the network for candles. The candle store defaults to Dukascopy (whose download
functions the store tests replace), and opening a real cTrader connection fails loudly."""
import pytest


@pytest.fixture(autouse=True)
def _no_live_candle_sources(monkeypatch):
    from slk import store
    monkeypatch.setenv("SLK_SOURCE", "dukascopy")
    monkeypatch.delenv("SLK_FEED_OWNER", raising=False)
    monkeypatch.setattr(store, "_FEED", {})

    def no_network():
        raise RuntimeError("tests must not open a cTrader connection")

    monkeypatch.setattr(store, "_open_client", no_network)
