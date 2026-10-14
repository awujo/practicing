"""cTrader as the primary candle source (slk/store.py + ctrader/client.py trendbar_rows). No network: a fake client
for the store, a local socket pair for the client's request loop."""
import socket
import threading

import numpy as np
import pandas as pd
import pytest

from ctrader import client as cmod
from ctrader import tokens
from ctrader.client import CTraderClient
from ctrader.framing import decode_body, encode, model, oa, read_frame
from slk import data, store


def _bar_rows(lo, hi, weekend=True):
    """Fake IC H1 bars (t, o, h, l, c, volume) in [lo, hi): every hour incl. some weekend hours, a zero-volume bar
    and a bar that is not hour-aligned (both must be dropped)."""
    out = []
    for t in range(int(lo) - int(lo) % 3600, int(hi), 3600):
        if t < lo:
            continue
        closed = store.fx_closed(pd.Timestamp(t, unit="s", tz="UTC"))
        if closed and not (weekend and pd.Timestamp(t, unit="s", tz="UTC").hour == 12):
            continue  # IC sends a stray weekend bar at 12:00 UTC (filtered by the store)
        x = 1.1 + (t % 7919) * 1e-6
        vol = 0 if t % (3600 * 97) == 0 else 10
        out.append((t, x, x + 2e-4, x - 2e-4, x + 1e-4, vol))
    out.append((int(lo) + 1800, 9.0, 9.0, 9.0, 9.0, 5)) if hi - lo > 7200 else None
    return out


class FakeClient:
    span = 35 * 7 * 86400

    def __init__(self):
        self.calls, self.closed = [], False

    def max_span(self, period="H1"):
        return self.span

    def get_symbols(self, names):
        self.calls.append(("symbols", tuple(names)))

    def trendbar_rows(self, symbol, period, lo, hi):
        assert period == "H1" and hi - lo <= self.span
        self.calls.append((symbol, lo, hi))
        return _bar_rows(lo, hi)

    def close(self):
        self.closed = True


@pytest.fixture
def ct(monkeypatch, tmp_path):
    """store.get_feed -> one FakeClient for the whole job; counts connections."""
    opened = []

    def open_client():
        c = FakeClient()
        opened.append(c)
        return c

    monkeypatch.setattr(store, "_open_client", open_client)
    monkeypatch.setenv("SLK_SOURCE", "ctrader")
    return opened


def _reqs(c, pair=None):
    return [x for x in c.calls if x[0] != "symbols" and (pair is None or x[0] == pair)]


def test_backfill_one_connection_wide_requests_final_months(ct, tmp_path):
    root = str(tmp_path / "store")
    now = pd.Timestamp("2026-10-14 10:07", tz="UTC")
    err = store.backfill(["EURUSD", "GBPJPY", "AUDCAD"], 2018, now=now, root=root)
    assert err == {}
    assert len(ct) == 1  # ONE connection for all pairs
    c = ct[0]
    assert c.calls[0] == ("symbols", ("EURUSD", "GBPJPY", "AUDCAD"))  # one symbol lookup for all pairs
    n = len(_reqs(c, "EURUSD"))
    months = (2026 - 2018) * 12 + 9  # completed months 2018-01 .. 2026-09
    assert n <= months // 7 + 2, n  # ~8 months per request (35-week API window) + the current month
    p = store.Pair("EURUSD", root)
    assert p.src == "ctrader"
    assert {"2018-01", "2026-09"} <= p.done_m and "2026-10" not in p.done_m
    t = p.df.index.to_numpy()
    cur = pd.Timestamp("2026-10-01", tz="UTC").timestamp()
    assert (p.df["q"][t < cur] == store.MONTH).all() and (p.df["q"][t >= cur] == store.CUR).all()
    assert (t % 3600 == 0).all()  # the half-hour bar was dropped
    assert not store._closed_mask(t).any()  # no weekend bars
    assert t[-1] + 3600 <= now.timestamp()  # forming bar not stored
    assert not any(9.0 in r for r in p.df[list(store.COLS)].to_numpy().tolist())
    assert store.complete(["EURUSD", "GBPJPY", "AUDCAD"], 2018, root=root, now=now, source="ctrader") == (True, [])
    assert store.complete(["EURUSD"], 2018, root=root, now=now, source="dukascopy")[0] is False
    hourly = store.hourly("EURUSD", 2018, 2025, root=root, now=now)
    assert hourly.index[0] >= pd.Timestamp("2018-01-01", tz="UTC") and hourly.index[-1].year == 2025


def test_live_update_fetches_only_last_days_and_finalises_month(ct, tmp_path):
    root = str(tmp_path / "store")
    now = pd.Timestamp("2026-09-29 10:07", tz="UTC")
    store.update_all(["EURUSD"], now, days=400, root=root)
    store.close_feed()
    ct.clear()
    now2 = now + pd.Timedelta(hours=1)
    store.update_all(["EURUSD"], now2, days=400, root=root)
    reqs = _reqs(ct[0])
    assert len(reqs) == 1  # one request: the current month's last few days
    _, lo, hi = reqs[0]
    assert hi == now2.floor("h").timestamp() and hi - lo <= (store.REFRESH + pd.Timedelta(hours=2)).total_seconds()
    store.close_feed()
    ct.clear()
    now3 = pd.Timestamp("2026-10-01 00:07", tz="UTC")  # month rollover: September becomes final
    store.update_all(["EURUSD"], now3, days=400, root=root)
    reqs = _reqs(ct[0])
    assert reqs[0][1:] == (pd.Timestamp("2026-09-01", tz="UTC").timestamp(), pd.Timestamp("2026-10-01", tz="UTC").timestamp())
    p = store.Pair("EURUSD", root)
    assert "2026-09" in p.done_m
    sep = p.df[(p.df.index >= pd.Timestamp("2026-09-01", tz="UTC").timestamp())]
    assert (sep["q"] == store.MONTH).all()
    got = store.recent("EURUSD", 30, now3, root=root)
    assert pd.Timestamp("2026-09-30 21:00", tz="UTC") <= got.index[-1] < pd.Timestamp("2026-10-01", tz="UTC")


def test_dukascopy_file_is_rebuilt_never_mixed(ct, tmp_path, monkeypatch):
    root = str(tmp_path / "store")
    old = store.Pair("EURUSD", root, source="dukascopy")
    old.put([(pd.Timestamp("2026-08-03 10:00", tz="UTC").timestamp(), 5.0, 5.0, 5.0, 5.0)], store.MONTH)
    old.done_m.add("2026-08")
    old.save()
    legacy = np.load(old.path)
    assert '"src": "dukascopy"' in str(legacy["meta"])
    now = pd.Timestamp("2026-10-14 10:07", tz="UTC")
    store.update("EURUSD", now, days=120, root=root)
    p = store.Pair("EURUSD", root)
    assert p.src == "ctrader" and 5.0 not in p.df["open"].tolist()
    assert "2026-08" in p.done_m and "2026-06" in p.done_m


def test_ctrader_failure_falls_back_to_dukascopy_overlay(monkeypatch, tmp_path, capsys):
    root = str(tmp_path / "store")
    now = pd.Timestamp("2026-10-14 10:07", tz="UTC")
    monkeypatch.setenv("SLK_SOURCE", "ctrader")
    monkeypatch.setattr(store, "_open_client", FakeClient)
    store.update_all(["EURUSD"], pd.Timestamp("2026-10-12 06:07", tz="UTC"), days=60, root=root)
    store.close_feed()
    before = store.Pair("EURUSD", root).df.copy()
    last = int(before.index[-1])

    def broken():
        raise ConnectionError("refused 1234567 secret-token-value")

    monkeypatch.setenv("CTRADER_ACCESS_TOKEN", "secret-token-value")
    monkeypatch.setattr(store, "_open_client", broken)
    store._FEED.clear()
    duka = []

    def day(pair, y, m, d):
        duka.append(("day", d))
        lo = pd.Timestamp(y, m, d, tz="UTC").timestamp()
        return [(t, 2.0, 2.1, 1.9, 2.05) for t in range(int(lo), int(lo) + 86400, 3600)
                if not store.fx_closed(pd.Timestamp(t, unit="s", tz="UTC"))]

    monkeypatch.setattr(data, "_month", lambda *a: pytest.fail("no month file needed for the gap"))
    monkeypatch.setattr(data, "_day", day)
    monkeypatch.setattr(data, "_hour", lambda pair, y, m, d, h: [
        (pd.Timestamp(y, m, d, h, tz="UTC").timestamp(), 2.0, 2.1, 1.9, 2.05)])
    err = store.update_all(["EURUSD"], now, days=60, root=root)
    assert err == {}
    out = capsys.readouterr().out
    assert "::warning title=Candles::cTrader candles failed for 1 pair(s) (EURUSD)" in out
    assert "secret-token-value" not in out and "1234567" not in out  # no secrets / account numbers in logs
    assert duka and min(d for _, d in duka) >= 11  # only the gap since the last cTrader bar (Oct 12), not the month
    p = store.Pair("EURUSD", root)
    pd.testing.assert_frame_equal(p.df, before)  # the cTrader file is untouched
    got = store.recent("EURUSD", 10, now, root=root)
    assert (got[got.index > pd.Timestamp(last, unit="s", tz="UTC")]["open"] == 2.0).all()
    assert (got[got.index <= pd.Timestamp(last, unit="s", tz="UTC")]["open"] != 2.0).all()
    assert got.index[-1] == pd.Timestamp("2026-10-14 09:00", tz="UTC")
    # next run: cTrader works again -> overlay dropped, cTrader bars only
    monkeypatch.setattr(store, "_open_client", FakeClient)
    store._FEED.clear()
    assert store.update_all(["EURUSD"], now, days=60, root=root) == {}
    assert (store.recent("EURUSD", 10, now, root=root)["open"] != 2.0).all()


def test_no_secrets_means_dukascopy(monkeypatch):
    for k in ("SLK_SOURCE", "CTRADER_CLIENT_ID", "CTRADER_CLIENT_SECRET", "CTRADER_ACCESS_TOKEN", "DATABASE_URL"):
        monkeypatch.delenv(k, raising=False)
    assert store.default_source() == "dukascopy"
    monkeypatch.setenv("CTRADER_CLIENT_ID", "a")
    monkeypatch.setenv("CTRADER_CLIENT_SECRET", "b")
    monkeypatch.setenv("DATABASE_URL", "mysql://x")
    assert store.default_source() == "ctrader"


def test_feed_not_opened_in_worker_process(monkeypatch):
    monkeypatch.setenv("SLK_FEED_OWNER", "1")  # another (parent) process owns the job's connection
    with pytest.raises(RuntimeError, match="parent"):
        store.get_feed()


def test_clean_ctrader_weekend_volume_alignment():
    ny = lambda s: int(pd.Timestamp(s, tz="America/New_York").tz_convert("UTC").timestamp())  # noqa: E731
    rows = [(ny("2026-10-16 16:00"), 1, 1, 1, 1, 3),  # Fri last bar: kept
            (ny("2026-10-16 17:00"), 1, 1, 1, 1, 3),  # Fri close: weekend
            (ny("2026-10-17 10:00"), 1, 1, 1, 1, 3),  # Saturday
            (ny("2026-10-18 17:00"), 1, 1, 1, 1, 3),  # Sunday open: kept
            (ny("2026-10-19 09:00"), 1, 1, 1, 1, 0),  # no ticks
            (ny("2026-10-19 09:00") + 60, 1, 1, 1, 1, 3)]  # not hour-aligned
    assert [r[0] for r in store.clean_ctrader(rows)] == [ny("2026-10-16 16:00"), ny("2026-10-18 17:00")]


# ---------------------------------------------------------------- client: chunks, rate limit, truncated replies
def _serve(sock, handler):
    def run():
        try:
            while True:
                msg, _, cid = decode_body(read_frame(sock))
                for reply in handler(msg) or []:
                    sock.sendall(encode(reply, cid))
        except Exception:
            pass
    threading.Thread(target=run, daemon=True).start()


def _tb(t):
    return model.ProtoOATrendbar(period=model.H1, low=110000, deltaOpen=10, deltaHigh=50, deltaClose=30,
                                 utcTimestampInMinutes=t // 60, volume=7)


def _connected_client(handler):
    a, b = socket.socketpair()
    _serve(b, handler)
    c = CTraderClient(env="demo", client_id="x", client_secret="y", settings=tokens.MemorySettings())
    c._sock = a
    threading.Thread(target=c._reader, daemon=True).start()
    c.account_id = 1
    c._symbols["EURUSD"] = {"symbol_id": 1, "name": "EURUSD", "digits": 5}
    return c, b


def test_trendbar_rows_max_window_rate_limit_and_truncation(monkeypatch):
    monkeypatch.setattr(cmod, "HIST_MIN_GAP_S", 0.0)
    sleeps = []
    monkeypatch.setattr(cmod.time, "sleep", lambda s: sleeps.append(s))
    seen, state = [], {"busy": 1}
    cap = 2000  # the fake server returns at most the newest 2000 bars of a window

    def handler(msg):
        if not isinstance(msg, oa.ProtoOAGetTrendbarsReq):
            return []
        if state["busy"]:
            state["busy"] -= 1
            return [oa.ProtoOAErrorRes(errorCode="REQUEST_FREQUENCY_EXCEEDED", description="slow down")]
        a, b = msg.fromTimestamp // 1000, msg.toTimestamp // 1000
        if b - a > 35 * 7 * 86400:
            return [oa.ProtoOAErrorRes(errorCode="INCORRECT_BOUNDARIES", description="too wide")]
        seen.append((a, b))
        ts = list(range(a - a % 3600 + (3600 if a % 3600 else 0), b, 3600))[-cap:]
        return [oa.ProtoOAGetTrendbarsRes(ctidTraderAccountId=1, period=model.H1, symbolId=1, timestamp=0,
                                          trendbar=[_tb(t) for t in ts])]

    c, b = _connected_client(handler)
    lo = int(pd.Timestamp("2025-01-01", tz="UTC").timestamp())
    hi = int(pd.Timestamp("2026-01-01", tz="UTC").timestamp())
    rows = c.trendbar_rows("EURUSD", "H1", lo, hi)
    c.close()
    b.close()
    ts = [r[0] for r in rows]
    assert ts == list(range(lo, hi, 3600))  # complete, sorted, no duplicates despite the 2000-bar cap
    assert rows[0][1:] == (1.1001, 1.1005, 1.1, 1.1003, 7)
    assert sleeps and sleeps[0] >= 1  # backed off after REQUEST_FREQUENCY_EXCEEDED, then retried
    assert max(b_ - a_ for a_, b_ in seen) == 35 * 7 * 86400  # full API window used
    assert len(seen) <= 6


def test_trendbar_rows_spaces_history_requests(monkeypatch):
    t = {"now": 100.0}
    sleeps = []
    monkeypatch.setattr(cmod.time, "monotonic", lambda: t["now"])

    def sleep(s):
        sleeps.append(s)
        t["now"] += s

    monkeypatch.setattr(cmod.time, "sleep", sleep)

    def handler(msg):
        if isinstance(msg, oa.ProtoOAGetTrendbarsReq):
            return [oa.ProtoOAGetTrendbarsRes(ctidTraderAccountId=1, period=model.H1, symbolId=1, timestamp=0,
                                              trendbar=[])]
        return []

    c, b = _connected_client(handler)
    c.timeout = 5
    lo = int(pd.Timestamp("2020-01-01", tz="UTC").timestamp())
    c.trendbar_rows("EURUSD", "H1", lo, lo + 3 * 35 * 7 * 86400)  # 3 windows
    c.close()
    b.close()
    assert len(sleeps) == 2 and all(abs(s - cmod.HIST_MIN_GAP_S) < 1e-9 for s in sleeps)  # <= 4 requests / s


def test_workflows_use_ctrader_cache_only():
    import pathlib

    import yaml
    root = pathlib.Path(__file__).resolve().parents[1] / ".github" / "workflows"
    for name in ("live", "backfill", "backtest", "verify-examples"):
        text = (root / f"{name}.yml").read_text()
        wf = yaml.safe_load(text)
        assert "candles-v2" not in text and "candles-partial-" not in text and "candles-live-" not in text, name
        steps = [s for job in wf["jobs"].values() for s in job["steps"]]
        restores = [s["with"] for s in steps if "cache/restore" in s.get("uses", "")]
        assert restores and all(str(r["restore-keys"]).split()[0] == "candles-v3-" for r in restores), name
        for s in steps:
            if "cache/save" in s.get("uses", ""):
                assert s["with"]["key"].startswith(("candles-v3-", "partial-candles-v3-")), name
        if "slk.store --check" in text:
            assert "--check --start 2018 --source ctrader" in text, name
        job = next(iter(wf["jobs"].values()))
        envs = [job["env"]] if "CTRADER_CLIENT_ID" in job["env"] else [s["env"] for s in steps if "slk." in s.get(
            "run", "") and "--check" not in s.get("run", "")]  # backtest: only on the steps that fetch (not pytest)
        assert envs, name
        for env in envs:
            assert "CTRADER_CLIENT_ID" in env and env.get("CTRADER_ENV") == "demo", name
            assert "DATABASE_URL" in env and "DATABASE_PASSWORD" in env, name  # refreshed tokens persist in the DB
    bf = yaml.safe_load((root / "backfill.yml").read_text())
    assert bf["jobs"]["backfill"]["timeout-minutes"] == 60
    assert "push" not in bf[True]  # manual only ("on" parses as True)
    assert "--notice" in (root / "backfill.yml").read_text()


def test_ctrader_bars_build_17_ny_daily_candles():
    from ctrader.client import rows_to_frame
    from slk.candles import resample
    lo = pd.Timestamp("2026-03-02", tz="UTC").timestamp()  # spans the US DST change (Mar 8)
    hi = pd.Timestamp("2026-03-21", tz="UTC").timestamp()
    h1 = rows_to_frame(store.clean_ctrader(_bar_rows(lo, hi), lo, hi))
    d = resample(h1, "D").iloc[1:]  # the first day starts mid-day (data start)
    starts = pd.to_datetime(d["start"]).dt.tz_convert("America/New_York")
    assert (pd.to_datetime(d["start"]).dt.tz_convert("America/New_York").dt.hour == 17).all()
    assert set(starts.dt.dayofweek) <= {6, 0, 1, 2, 3}  # Sun..Thu 17:00 NY opens: Mon..Fri daily candles, no weekend
    w = resample(h1, "W")
    assert len(w) == 3
