"""Live runner parts that need no network or DB."""
import lzma
import struct
from datetime import datetime, timedelta

import pandas as pd
import pytest

from slk import data
from slk.candles import resample
from slk.db import parse_url
import slk.live as live_mod
from slk.live import (drop_forming, fmt_time, format_alert, format_summary, pair_state, planned_time, reconcile,
                      summary_due, summary_line)
from slk.story import DEFAULT, current_tap, find_stories
from tests.test_engine import walk

UTC = "UTC"


def row(**kw):
    r = {"pair": "EURUSD", "story": "D", "side": "SELL", "status": "CONFIRMED", "level_kind": "A",
         "level": 1.0845, "point_b": 1.0812, "target": 1.076, "invalidation": 1.0845,
         "tap_time": datetime(2026, 10, 11, 21), "confirm_time": datetime(2026, 10, 12, 21)}
    r.update(kw)
    return r


# ------------------------------------------------------------- messages
def test_flipped_level_names_its_shape(monkeypatch):
    """Owner 2026-10-15: say which KL (A / V / OC) a flipped level was, and the candle that drew it."""
    monkeypatch.setattr(live_mod, "CLOCK", lambda: pd.Timestamp("2026-12-31", tz="UTC"))
    m = format_alert("TAPPED", row(status="TAPPED", level_kind="flip", level_src="V",
                                   level_candle=datetime(2026, 10, 4, 21), level_time=datetime(2026, 10, 8, 21)))
    assert "V-shape key level at 1.08450 (D1)" in m and "What it is: a bottom" in m
    assert "Line from: D1 candle Mon 5 Oct (its close)" in m and "Flipped: broken Fri 9 Oct" in m
    assert live_mod.chain("D", "BUY", "up") == "W1\u2192D1\u2192H4" and live_mod.chain("D", "BUY", "down") == "D1\u2192H4"
    assert live_mod.chain("W", "SELL", "down") == "MN1\u2192W1\u2192D1" and live_mod.chain("M", "SELL", "down") == "MN1\u2192W1"


def test_alert_format(monkeypatch):
    monkeypatch.setattr(live_mod, "CLOCK", lambda: pd.Timestamp("2026-12-31", tz="UTC"))  # far away: plain dates
    m = format_alert("CONFIRMED", row(breakout_time=datetime(2026, 10, 12, 5), next_day=True, level_time=datetime(2026, 10, 1, 21),
                                      trend="down", htf_trend="down"))
    L = m.splitlines()
    # owner 2026-10-16: sections (headline / KEY LEVEL / STORY SO FAR / CONTEXT / PLAN), blank line between them
    assert L[0] == "\u2705 SELL EURUSD \u00b7 Daily story \u00b7 W1\u2192D1\u2192H4" and L[1] == "BIAS CONFIRMED (external break)"
    assert "The D1 is now bearish" in L[2]
    for sec in ("\U0001f4cd KEY LEVEL", "\U0001f4d6 STORY SO FAR", "\U0001f9ed CONTEXT", "\U0001f3af PLAN"):
        assert "\n\n" + sec + "\n" in m
    # default display_tz Africa/Lagos (WAT = UTC+1)
    assert "A-shape key level at 1.08450 (D1)\n\u2022 What it is: a top" in m and "Formed: D1 candle Fri 2 Oct" in m
    assert "1. Rejected: D1 candle Mon 12 Oct, it touched the level and closed back below it" in m
    assert "2. External break: H4 closed below point B 1.08120\n   \U0001f552 H4 candle close Mon 12 Oct 10:00 WAT" in m
    assert "3. Confirmed: the D1 candle also closed below point B\n   \U0001f552 D1 candle close Mon 12 Oct 22:00 WAT" in m
    assert "W1 trend: bearish (agrees)" in m and "D1 structure: bearish (agrees)" in m
    assert "Next Day Rule \u2705" in m and "Retrace" not in m
    assert "Target: 1.07600" in m and "Invalid if the D1 closes above 1.08450" in m and "Rule: key level tap" in m
    assert "Not an entry signal" in m and "Times WAT" in m
    f = format_alert("CONFIRMED", row(breakout_time=datetime(2026, 10, 12, 5)), detail="full")
    assert "Rejected: D1 candle Mon 12 Oct" in f and "open Sun 11 Oct 22:00 WAT, close Mon 12 Oct 22:00 WAT" in f
    assert "open Mon 12 Oct 06:00 WAT, close Mon 12 Oct 10:00 WAT" in f
    u = format_alert("CONFIRMED", row(next_day=False, retrace=1, trend="down", htf_trend="up"), "UTC")
    assert "Next Day Rule \u26a0" in u and "Retrace \u26a0 a later H4 candle" in u
    assert "W1 trend: bullish (against this story)" in u and "D1 candle close Mon 12 Oct 21:00 UTC" in u
    j = format_alert("TAPPED", row(pair="GBPJPY", side="BUY", level=190.123, point_b=191.5, target=None,
                                   invalidation=190.123, confirm_time=None, status="TAPPED"))
    assert "TAPPED" in j and "190.123" in j and "Target: set when the story confirms" in j and "below" in j
    assert "Confirmed" not in j
    assert j.startswith("\U0001f440 BUY GBPJPY") and "NO_TRADE: wait for a H4 body close above point B, then the D1 confirmation close above point B" in j
    assert "Next Day" not in j and "same-day" not in j
    w = format_alert("CONFIRMED", row(story="W", level_kind="sweep", side="BUY", no_trade=True,
                                      no_trade_reason="M/W conflict"))
    assert "W1\u2192D1" in w and "Weekly story" in w and "Sweep of previous week low" in w
    assert "NO_TRADE: M/W conflict" in w and "W1 candle week of Mon 12 Oct" in w
    assert fmt_time(datetime(2026, 10, 12, 21)) == "2026-10-12 21:00 UTC"
    now = datetime(2026, 12, 31)
    assert fmt_time(datetime(2026, 10, 12, 21), "Europe/London", now) == "Mon 12 Oct 22:00 BST"
    # owner request 2026-10-15: friendly day near now, the date always shown; year when not this year
    now = datetime(2026, 10, 15, 12)  # Thursday
    assert fmt_time(datetime(2026, 10, 15, 9), "Africa/Lagos", now) == "Today, Thu 15 Oct 10:00 WAT"
    assert fmt_time(datetime(2026, 10, 14, 21), "Africa/Lagos", now) == "Yesterday, Wed 14 Oct 22:00 WAT"
    assert fmt_time(datetime(2026, 10, 16, 21), "Africa/Lagos", now) == "Tomorrow, Fri 16 Oct 22:00 WAT"
    assert fmt_time(datetime(2026, 10, 12, 21), "Africa/Lagos", now) == "Monday, 12 Oct 22:00 WAT"
    assert fmt_time(datetime(2026, 10, 5, 21), "Africa/Lagos", now) == "Last week Monday, 5 Oct 22:00 WAT"
    assert fmt_time(datetime(2026, 9, 28, 21), "Africa/Lagos", now) == "Mon 28 Sep 22:00 WAT"
    assert fmt_time(datetime(2025, 9, 29, 21), "Africa/Lagos", now) == "Mon 29 Sep 2025 22:00 WAT"


def test_summary():
    assert summary_line("EURUSD", []) == "EURUSD: NO_TRADE (no story)"
    assert summary_line("EURUSD", [row(status="TARGET_HIT")]) == \
        "EURUSD: D BEARISH bias (target reached, bias continues)"
    assert summary_line("EURUSD", [row(status="INVALIDATED")]) == "EURUSD: NO_TRADE (no story)"
    s = summary_line("EURUSD", [row(), row(story="W", status="TAPPED", side="BUY")])
    assert s.startswith("EURUSD: W BUY tapped (NO_TRADE until breakout), D SELL B 1.08120")
    c = summary_line("EURUSD", [row(story="M", side="BUY"), row(story="W")])
    assert c.endswith("NO_TRADE (M/W disagree)")
    txt = format_summary(pd.Timestamp("2026-10-13 21:10", tz=UTC), {"EURUSD": [row()], "USDJPY": []}, "on")
    assert "kill switch" in txt and "USDJPY: NO_TRADE" in txt


def test_summary_due_and_planned():
    # 17:05 New York = 21:05 UTC in October (EDT)
    assert not summary_due(pd.Timestamp("2026-10-13 21:04", tz=UTC), None)
    assert summary_due(pd.Timestamp("2026-10-13 21:07", tz=UTC), "2026-10-12")
    assert not summary_due(pd.Timestamp("2026-10-13 22:07", tz=UTC), "2026-10-13")
    assert not summary_due(pd.Timestamp("2026-10-17 22:07", tz=UTC), None)  # Saturday
    now = datetime(2026, 10, 13, 9, 31)
    assert planned_time(now, "schedule") == datetime(2026, 10, 13, 9, 7)
    assert planned_time(datetime(2026, 10, 13, 9, 3), "schedule") == datetime(2026, 10, 13, 8, 7)
    assert planned_time(now, "workflow_dispatch") == now


# ------------------------------------------------------------- still-forming bars
def test_drop_forming():
    h1 = walk(24 * 60)
    last = h1.index[-1]
    now = last + pd.Timedelta(minutes=30)       # last hour still forming
    assert drop_forming(h1, "H1", now).index[-1] == last - pd.Timedelta(hours=1)
    now = last + pd.Timedelta(hours=1)          # last hour just closed
    assert drop_forming(h1, "H1", now).index[-1] == last

    # mid-day (New York): today's D bar is forming and goes; the H4 bar of 12:00-16:00 NY is closed and stays
    h = walk(24 * 60)
    now = pd.Timestamp("2020-02-12 18:00", tz=UTC)  # 13:00 New York (EST)
    h = h[h.index < now]
    d = resample(drop_forming(h, "D", now), "D")
    assert d["end"].iloc[-1] <= now and d["end"].iloc[-1] == pd.Timestamp("2020-02-11 22:00", tz=UTC)
    assert drop_forming(h, "H4", now).index[-1] == pd.Timestamp("2020-02-12 17:00", tz=UTC)  # 09-13 NY bar closed
    h = walk(24 * 60)
    now = pd.Timestamp("2020-02-12 19:00", tz=UTC)  # 14:00 NY: the 13-17 NY H4 bar is forming
    h = h[h.index < now]
    assert drop_forming(h, "H4", now).index[-1] == pd.Timestamp("2020-02-12 17:00", tz=UTC)
    # just after the daily close nothing is dropped
    now = pd.Timestamp("2020-02-12 22:00", tz=UTC)
    h = walk(24 * 60)
    h = h[h.index < now]
    assert drop_forming(h, "D", now).index[-1] == h.index[-1]
    # the week closes Friday 17:00 New York: on Saturday the weekly bar is closed
    sat = pd.Timestamp("2020-02-15 12:00", tz=UTC)
    h = walk(24 * 60)
    h = h[h.index < sat]
    assert drop_forming(h, "W", sat).index[-1] == h.index[-1]
    wed = pd.Timestamp("2020-02-12 12:00", tz=UTC)
    w = resample(drop_forming(h[h.index < wed], "W", wed), "W")
    assert w["end"].iloc[-1] <= pd.Timestamp("2020-02-08 00:00", tz=UTC)  # synthetic data trades Fri 22-24 UTC


# ------------------------------------------------------------- current state (TAPPED, no breakout yet)
def test_current_tap_matches_engine():
    h1 = walk(24 * 500, seed=1)
    found = 0
    for end in pd.date_range(h1.index[24 * 300], h1.index[-1], freq="1D")[:40]:
        h = drop_forming(h1[h1.index < end], "D", end)
        t = current_tap("EURUSD", h, "D")
        if not t:
            continue
        found += 1
        ob = resample(h, "D")
        tap = pd.Timestamp(t["tap_time"], tz=UTC)
        k = int((ob["start"] == tap).to_numpy().argmax())
        assert 0 <= len(ob) - 1 - k <= DEFAULT["max_wait"] and t["bars_left"] >= 0
        assert t["status"] == "TAPPED"
        assert (t["B"] < t["level"]) if t["side"] == "SELL" else (t["B"] > t["level"])
        lo, hi, c = ob["low"].iat[k], ob["high"].iat[k], ob["close"].iat[k]
        tol = DEFAULT["tap_tol_pips"] * 0.0001
        if t["side"] == "SELL":  # wick into the level, close back below
            assert hi >= t["level"] - tol and c <= t["level"]
            assert (ob["close"].iloc[k + 1:] <= t["level"]).all()
        else:
            assert lo <= t["level"] + tol and c >= t["level"]
            assert (ob["close"].iloc[k + 1:] >= t["level"]).all()
        assert t["tap_time"] not in {s["tap_time"] for s in find_stories("EURUSD", h, "D")}  # not confirmed
    assert found > 0


def test_pair_state_statuses():
    h1 = walk(24 * 500, seed=2)
    now = h1.index[-1] + pd.Timedelta(hours=1)
    rows = pair_state("EURUSD", h1, now, ["D", "W"], DEFAULT)
    assert rows and {r["status"] for r in rows} <= {"TAPPED", "CONFIRMED", "TARGET_HIT", "INVALIDATED", "ENDED_FLIP", "CANCELLED"}
    assert sum(r["status"] == "TAPPED" for r in rows) <= 2
    for r in rows:
        assert r["invalidation"] == r["level"] and isinstance(r["tap_time"], datetime)


# ------------------------------------------------------------- DB sync decisions
def test_reconcile_alerts():
    now = datetime(2026, 10, 13, 9)
    fresh = row(confirm_time=now - timedelta(hours=10))
    w, a = reconcile([fresh], [], now)
    assert w == [fresh] and a == [("CONFIRMED", fresh)]
    w, a = reconcile([fresh], [dict(fresh, id=1)], now)            # unchanged: nothing to do
    assert w == [] and a == []
    old = row(confirm_time=now - timedelta(days=30))                  # first seen but old: store, stay quiet
    w, a = reconcile([old], [], now)
    assert w == [old] and a == []
    w, a = reconcile([row(status="TARGET_HIT")], [], now)             # finished before we saw it
    assert a == []
    tapped = row(status="TAPPED", confirm_time=None)
    conf = row(confirm_time=now - timedelta(days=30))
    w, a = reconcile([conf], [tapped], now)                           # TAPPED -> CONFIRMED is news
    assert a == [("CONFIRMED", conf)]
    hit = row(status="TARGET_HIT")
    w, a = reconcile([hit], [row()], now)
    assert a == [("TARGET_HIT", hit)]
    w, a = reconcile([row(status="CANCELLED")], [row()], now)         # expiry is stored, not alerted
    assert len(w) == 1 and a == []


def test_reconcile_stale_tapped():
    h1 = walk(24 * 60)
    ob = resample(h1, "D")
    k = len(ob) - 3
    tap = ob["start"].iat[k].to_pydatetime().replace(tzinfo=None)
    now = h1.index[-1] + pd.Timedelta(hours=1)
    level = float(ob["close"].iloc[k + 1:].max()) + 0.01         # nothing closed above it since
    t = row(status="TAPPED", tap_time=tap, level=level, invalidation=level, confirm_time=None)
    w, a = reconcile([], [t], now, h1, DEFAULT)
    assert w == [] and a == []                                    # still waiting (within max_wait)
    level = float(ob["close"].iloc[k + 1:].min()) + 1e-6          # a later close went above it
    t = row(status="TAPPED", tap_time=tap, level=level, invalidation=level, confirm_time=None)
    w, a = reconcile([], [t], now, h1, DEFAULT)
    assert a and a[0][0] == "INVALIDATED"


# ------------------------------------------------------------- helpers
def test_parse_url():
    p = parse_url("mysql://avnadmin:p%40ss@mysql-x.aivencloud.com:12345/defaultdb?ssl-mode=REQUIRED")
    assert p == {"host": "mysql-x.aivencloud.com", "port": 12345, "user": "avnadmin", "password": "p@ss",
                 "database": "defaultdb", "ssl_mode": "REQUIRED"}
    assert parse_url("mysql://u:p@h/db")["ssl_mode"] == "REQUIRED"


def test_decoders():
    p = data.point("EURUSD")
    rec = b"".join(struct.pack(">5if", 60 * i, 110000 + i, 110001 + i, 109990, 110010 + i, 1.0) for i in range(120))
    rows = data._to_h1(data._bars(rec, 0, p))
    assert len(rows) == 2 and rows[0][0] == 0 and rows[1][0] == 3600
    assert abs(rows[0][1] - 1.1) < 1e-9 and abs(rows[0][4] - 1.10060) < 1e-9 and abs(rows[0][2] - 1.10069) < 1e-9
    ticks = lzma.decompress(lzma.compress(b"".join(struct.pack(">3i2f", 1000 * i, 110005, 110000 + i, 1, 1)
                                                  for i in range(10))))
    t = data._to_h1(data._ticks(ticks, 7200, p))
    assert t == [(7200, 1.1, 1.10009, 1.1, 1.10009)]


def test_main_flow_with_fake_db(monkeypatch, capsys, tmp_path):
    """Whole run with an in-memory DB and synthetic candles: writes rows, logs the run, no exceptions."""
    from slk import db, live
    store, runs, settings, sent = {}, {}, {"pairs": "EURUSD,GBPJPY"}, []
    monkeypatch.setenv("DATABASE_URL", "mysql://u:p@h/db")
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.setattr(db, "apply_schema", lambda: None)
    monkeypatch.setattr(db, "start_run", lambda job, pl, st: runs.setdefault(1, {"job": job, "planned": pl, "started": st}) and 1)
    monkeypatch.setattr(db, "finish_run", lambda i, ok, note: runs[i].update(ok=ok, note=note))
    monkeypatch.setattr(db, "get_setting", lambda k, d=None: settings.get(k, d))
    monkeypatch.setattr(db, "get_settings", lambda: dict(settings))
    monkeypatch.setattr(db, "set_setting", lambda k, v: settings.__setitem__(k, v))
    monkeypatch.setattr(db, "upsert_bias", lambda r: store.__setitem__((r["pair"], r["story"], r["tap_time"]), dict(r)))
    monkeypatch.setattr(db, "upsert_tf_state", lambda *a: None)
    monkeypatch.setattr(db, "get_bias", lambda p, s=None: [r for k, r in store.items() if k[0] == p])
    monkeypatch.setattr(db, "get_entries", lambda p: [])
    monkeypatch.setattr(db, "upsert_entry", lambda e: 1)
    monkeypatch.setattr(live, "send_telegram", lambda t: sent.append(t) or True)
    monkeypatch.setattr(live, "recent", lambda p, days: walk(24 * 500, seed=3 if p == "EURUSD" else 4))
    monkeypatch.setattr(live, "prepare_candles", lambda pairs, now: {})
    monkeypatch.setattr(live.candles_store, "DIR", str(tmp_path))
    monkeypatch.setattr(db, "count_entries", lambda st: 0)
    assert live.main([]) == 0
    assert runs[1]["ok"] and runs[1]["job"] == "live" and "pairs ok 2" in runs[1]["note"]
    assert {k[0] for k in store} == {"EURUSD", "GBPJPY"}
    n, m = len(store), len(sent)
    assert live.main([]) == 0 and len(store) == n and len(sent) == m   # second run: nothing new, nothing re-alerted


@pytest.mark.parametrize("date", ["2026-10-19", "2026-01-19"])
def test_h4_only_available_at_actual_close(date):
    # New York 17:00 alignment: summer closes at 10 WAT, winter at 11 WAT.
    close = pd.Timestamp(date + " 09:00", tz="UTC")
    if "01-19" in date:
        close += pd.Timedelta(hours=1)
    h = walk(24 * 60)
    h.index = pd.date_range(end=close - pd.Timedelta(hours=1), periods=len(h), freq="h", tz="UTC")
    for delta in [-60, -1, 0, 60]:
        now = close + pd.Timedelta(seconds=delta)
        cb = resample(drop_forming(h, "H4", now), "H4")
        assert all(live_mod.candle_end(t, "H4") <= now for t in cb["start"])
        assert (cb["start"].iloc[-1] == close - pd.Timedelta(hours=4)) == (delta >= 0)
