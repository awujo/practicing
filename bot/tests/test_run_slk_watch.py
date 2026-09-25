"""
The SLK watcher process: wiring, history trimming, and the refusal to
run deaf.
"""

from __future__ import annotations

import json

import pandas as pd
import pytest

from backtest.engine.candles import Candle

from ..run_slk_watch import _loader, _trim, _windows, main

T0 = pd.Timestamp("2020-01-01")


def bars(n, step="1h"):
    return [Candle(time=T0 + pd.Timedelta(step) * i, open=1.1, high=1.1005,
                   low=1.0995, close=1.1, volume=0) for i in range(n)]


def test_trimming_keeps_the_last_n_years_only():
    """The live side only ever sees the trimmed window, so what gets
    reported is what was measured."""
    daily = [Candle(time=T0 + pd.Timedelta(days=i), open=1.1, high=1.1,
                    low=1.1, close=1.1, volume=0) for i in range(365 * 5)]
    kept = _trim(daily, years=1)
    assert len(kept) < len(daily)
    assert (kept[-1].time - kept[0].time).days <= 367


def test_no_window_keeps_everything():
    daily = bars(100)
    assert _trim(daily, None) is daily
    assert _trim(daily, 0) is daily


def test_trimming_an_empty_series_is_not_an_error():
    assert _trim([], 2) == []


def test_an_explicit_null_window_means_full_history(tmp_path):
    """bot/history_windows.json records a null for GBPNZD, meaning
    "confirmed NOT safe to cap". Treating it as a default would silently
    cut the one instrument that must not be."""
    path = tmp_path / "windows.json"
    path.write_text(json.dumps({
        "default": {"D": 2, "H1": 1},
        "instruments": {"EURUSD": {"D": 8, "H1": 4}, "GBPNZD": None},
    }))
    got = _windows(str(path))
    assert got.for_instrument("EURUSD") == {"D": 8, "H1": 4}
    assert got.for_instrument("GBPNZD") == {}, "no cap at all, not the default"
    assert got.for_instrument("USOIL") == {"D": 2, "H1": 1}, \
        "an instrument the file has never heard of gets the default, not " \
        "twenty years"


def test_no_config_means_no_trimming():
    assert _windows(None).for_instrument("EURUSD") == {}


def test_a_missing_cache_file_costs_one_instrument_not_the_cycle(caplog):
    """25 instruments share a process; one broken file must not stop the
    other 24 being watched."""
    from ..run_slk_watch import _Windows
    load = _loader("nosuchsource", _Windows({}, {}))
    assert load("EURUSD", "H1") == []


def test_the_loader_applies_that_instruments_own_window(monkeypatch):
    from .. import run_slk_watch

    daily = [Candle(time=T0 + pd.Timedelta(days=i), open=1.1, high=1.1,
                    low=1.1, close=1.1, volume=0) for i in range(365 * 5)]
    monkeypatch.setattr(run_slk_watch, "load_candles",
                        lambda *_a, **_k: daily)

    from ..run_slk_watch import _Windows
    load = _loader("dukascopy", _Windows({}, {"EURUSD": {"D": 1}}))
    assert len(load("EURUSD", "D")) < len(daily), "EURUSD is capped"
    assert len(load("GBPJPY", "D")) == len(daily), "GBPJPY has no window"


def test_it_refuses_to_start_with_no_signal_channel(monkeypatch):
    """A watcher with nowhere to report is a process that burns CPU and
    tells nobody -- better to fail loudly at startup."""
    from .. import run_slk_watch

    monkeypatch.setattr(run_slk_watch.SignalChannel, "from_env",
                        staticmethod(lambda label="": None))
    monkeypatch.setattr("sys.argv",
                        ["run_slk_watch", "--instruments", "EURUSD", "--n", "2"])
    with pytest.raises(SystemExit) as exc:
        main()
    assert "SLK_SIGNAL_TOKEN" in str(exc.value)


def test_n_is_required(monkeypatch):
    """The course never defines a swing numerically, so the caller has to
    choose one and say which -- the same rule the whole package follows."""
    monkeypatch.setattr("sys.argv", ["run_slk_watch", "--instruments", "EURUSD"])
    with pytest.raises(SystemExit):
        main()


def test_one_cycle_runs_end_to_end_and_sends_nothing_first_time(monkeypatch):
    """--once is the wiring check. The first cycle only learns where now
    is, so a clean run is a silent one."""
    from .. import run_slk_watch

    h1 = bars(600)
    monkeypatch.setattr(run_slk_watch, "load_candles", lambda *_a, **_k: h1)

    sent = []

    class Channel:
        def note(self, text):
            sent.append(text)
            return True

    monkeypatch.setattr(run_slk_watch.SignalChannel, "from_env",
                        staticmethod(lambda label="": Channel()))
    monkeypatch.setattr("sys.argv",
                        ["run_slk_watch", "--instruments", "EURUSD,GBPJPY",
                         "--n", "2", "--once"])
    main()
    assert sent == [], "the first cycle must be silent"


def test_all_means_every_instrument_including_the_two_the_old_bots_skip(monkeypatch):
    """The old bots watch 25; instruments.py carries 27. USOIL and ETHUSD
    were never in the live list and the operator asked for them."""
    from .. import run_slk_watch

    seen = {}

    class Channel:
        def note(self, _text):
            return True

    monkeypatch.setattr(run_slk_watch, "load_candles", lambda *_a, **_k: [])
    monkeypatch.setattr(run_slk_watch.SignalChannel, "from_env",
                        staticmethod(lambda label="": Channel()))

    real = run_slk_watch.SLKWatcher

    def spy(instrument, n, channel, load):
        seen[instrument] = True
        return real(instrument, n, channel, load)

    monkeypatch.setattr(run_slk_watch, "SLKWatcher", spy)
    monkeypatch.setattr("sys.argv",
                        ["run_slk_watch", "--instruments", "ALL", "--n", "2",
                         "--once"])
    run_slk_watch.main()

    assert len(seen) == 27
    assert "USOIL" in seen and "ETHUSD" in seen
    assert "EURUSD" in seen and "XAUUSD" in seen
