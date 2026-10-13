"""Candle store (slk/store.py): incremental updates give exactly what data.recent / data.hourly download."""
from datetime import datetime, timezone

import pandas as pd
import pytest

from slk import data, store

CLOCK = {"now": None}


def _price(t, src):
    # distinct per source so a wrong source mix is visible; month file = the reference value
    return 1.1 + (t % 7919) * 1e-6 + {"month": 0, "day": 2e-7, "tick": 4e-7}[src]


def _rows(lo, hi, src):
    out = []
    for t in range(int(lo), int(hi), 3600):
        if store.fx_closed(pd.Timestamp(t, unit="s", tz="UTC")):
            continue
        x = _price(t, src)
        out.append((float(t), x, x + 1e-4, x - 1e-4, x + 5e-5))
    return out


@pytest.fixture
def fake_feed(monkeypatch, tmp_path):
    calls = []

    def month(pair, y, m):
        calls.append(("month", y, m))
        lo = pd.Timestamp(y, m, 1, tz="UTC")
        hi = lo + pd.offsets.MonthBegin(1)
        if CLOCK["now"] < hi + pd.Timedelta(days=2):  # published two days after the month ends
            return []
        return _rows(lo.timestamp(), hi.timestamp(), "month")

    def day(pair, y, m, d):
        calls.append(("day", y, m, d))
        lo = pd.Timestamp(y, m, d, tz="UTC")
        if CLOCK["now"] < lo + pd.Timedelta(hours=27):  # published 3 h after the day ends
            return []
        return [r for r in _rows(lo.timestamp(), lo.timestamp() + 86400, "day")]

    def hour(pair, y, m, d, h):
        calls.append(("hour", y, m, d, h))
        lo = pd.Timestamp(y, m, d, h, tz="UTC")
        if CLOCK["now"] < lo + pd.Timedelta(hours=1):
            return []
        return _rows(lo.timestamp(), lo.timestamp() + 3600, "tick")

    monkeypatch.setattr(data, "_month", month)
    monkeypatch.setattr(data, "_day", day)
    monkeypatch.setattr(data, "_hour", hour)
    monkeypatch.setattr(data, "CACHE", str(tmp_path / "legacy"))
    return calls


def test_incremental_store_equals_recent(fake_feed, tmp_path):
    root = str(tmp_path / "store")
    days = 75
    start = pd.Timestamp(2026, 2, 26, 10, 7, tz="UTC")  # crosses a month end, weekends, publication delays
    for i in range(0, 24 * 9, 5):
        now = start + pd.Timedelta(hours=i)
        CLOCK["now"] = now
        fake_feed.clear()
        store.update("EURUSD", now, days=days, root=root)
        n_fetch = len(fake_feed)
        got = store.recent("EURUSD", days, now, root=root)
        want = data.recent("EURUSD", days, now.to_pydatetime())
        pd.testing.assert_frame_equal(got, want, check_freq=False)
        if i > 48:
            assert n_fetch <= 12, (now, fake_feed)  # only the new hour(s) / a day or month file not out yet
    assert store.load("EURUSD", root).done_m  # finished months came from month files


def test_hourly_from_store_equals_month_files(fake_feed, tmp_path):
    CLOCK["now"] = pd.Timestamp(2026, 3, 20, tz="UTC")
    root = str(tmp_path / "store")
    got = store.hourly("EURUSD", 2025, 2026, root=root, now=CLOCK["now"])
    rows = [r for y in (2025, 2026) for m in range(1, 13) if (y, m) < (2026, 3) for r in data._month("EURUSD", y, m)]
    want = pd.DataFrame(rows, columns=["t", "open", "high", "low", "close"])
    want.index = pd.to_datetime(want.pop("t"), unit="s", utc=True)
    pd.testing.assert_frame_equal(got, want, check_freq=False)
    fake_feed.clear()
    store.hourly("EURUSD", 2025, 2026, root=root, now=CLOCK["now"])
    assert not [c for c in fake_feed if c[0] == "month" and (c[1], c[2]) < (2026, 2)]  # stored months reused


def test_fx_closed_weekend():
    ny = lambda s: pd.Timestamp(s, tz="America/New_York").tz_convert("UTC")  # noqa: E731
    assert not store.fx_closed(ny("2026-10-16 16:59"))   # Friday before the close
    assert store.fx_closed(ny("2026-10-16 17:00"))       # Friday close
    assert store.fx_closed(ny("2026-10-17 12:00"))       # Saturday
    assert store.fx_closed(ny("2026-10-18 16:59"))
    assert not store.fx_closed(ny("2026-10-18 17:00"))   # Sunday open
    assert not store.fx_closed(datetime(2026, 10, 14, 12, tzinfo=timezone.utc))


def test_store_file_roundtrip(tmp_path):
    p = store.Pair("EURUSD", str(tmp_path))
    p.put([(3600.0, 1.0, 2.0, 0.5, 1.5), (7200.0, 1.1, 2.1, 0.6, 1.6)], store.TICK)
    p.done_m.add("1970-01")
    assert p.save() and not p.save()  # nothing changed -> no rewrite
    q = store.Pair("EURUSD", str(tmp_path))
    assert q.done_m == {"1970-01"} and list(q.df.index) == [3600, 7200] and q.df["q"].tolist() == [1, 1]
    q.put([(3600.0, 9.0, 9.0, 9.0, 9.0)], store.DAY, 0, 86400)  # better source replaces the range
    assert list(q.df.index) == [3600] and q.df["open"].iat[0] == 9.0
