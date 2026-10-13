"""A failed month download must not throw away the months that did download (backfill progress)."""
import pandas as pd
import pytest

from slk import data, store


def test_failed_month_keeps_others(tmp_path, monkeypatch):
    def fake_month(pair, y, m):
        if (y, m) == (2020, 3):
            raise RuntimeError("download failed: 503")
        t0 = pd.Timestamp(y, m, 2, tz="UTC").timestamp()
        return [(t0 + h * 3600, 1.0, 1.1, 0.9, 1.05) for h in range(5)]

    monkeypatch.setattr(data, "_month", fake_month)
    monkeypatch.setattr(data, "_day", lambda *a: [])
    monkeypatch.setattr(data, "_hour", lambda *a: [])
    now = pd.Timestamp("2020-06-10", tz="UTC")
    with pytest.raises(RuntimeError, match="1 month file"):
        store.update("EURUSD", now, since=pd.Timestamp("2020-01-01", tz="UTC"), root=str(tmp_path))
    p = store.Pair("EURUSD", str(tmp_path))
    assert {"2020-01", "2020-02", "2020-04", "2020-05"} <= p.done_m
    assert "2020-03" not in p.done_m
    assert len(p.df) == 20
