"""Efficiency work: engine memo, parallel pairs, weekend skip, status updates, no_trade column, backtest M/W filter."""
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import pytest

from slk import backtest, db, live, settings as S
from test_engine import walk

ROOT = Path(__file__).resolve().parents[1]
NOW = pd.Timestamp("2026-10-14 12:30", tz="UTC")  # a Wednesday


# ------------------------------------------------------------------ memo: recompute only on a new origin bar
def test_pair_state_memo_reuses_engine_output(monkeypatch):
    h1 = walk(24 * 500, seed=3)
    now = h1.index[-1] + pd.Timedelta(hours=1)
    plain = live.pair_state("EURUSD", h1, now, ["D", "W", "M"], live.DEFAULT)
    calls = []
    real = live.find_stories
    monkeypatch.setattr(live, "find_stories", lambda *a, **k: calls.append(a[2]) or real(*a, **k))
    memo = {}
    first = live.pair_state("EURUSD", h1, now, ["D", "W", "M"], live.DEFAULT, memo)
    assert sorted(calls) == ["D", "M", "W"] and set(memo) == {"D", "W", "M"}
    calls.clear()
    # one more closed H1 hour inside the same D bar: no story type recomputed, identical rows
    again = live.pair_state("EURUSD", h1, now + pd.Timedelta(minutes=5), ["D", "W", "M"], live.DEFAULT, memo)
    assert calls == []
    strip = lambda rows: [{k: v for k, v in r.items() if k != "_story"} for r in rows]  # noqa: E731
    assert strip(first) == strip(plain) == strip(again)
    # a changed cfg or new closed D bar -> recomputed
    live.pair_state("EURUSD", h1, now, ["D"], {**live.DEFAULT, "max_wait": 6}, memo)
    assert calls == ["D"]


def test_compute_all_pool_equals_sequential(monkeypatch, tmp_path):
    monkeypatch.setattr(live, "recent", lambda p, days: walk(24 * 400, seed=3 if p == "EURUSD" else 4))
    monkeypatch.setattr(live.candles_store, "DIR", str(tmp_path))
    now = walk(24 * 400, seed=3).index[-1] + pd.Timedelta(hours=1)
    jobs = [(p, now, ["D", "W", "M"], ["D", "W", "M"], live.DEFAULT, None, True) for p in ("EURUSD", "GBPUSD")]
    seq = live.compute_all(jobs, workers=1)
    par = live.compute_all(jobs, workers=2)
    strip = lambda res: [[{k: v for k, v in r.items() if k != "_story"} for r in x["rows"]] for x in res]  # noqa
    assert [x["pair"] for x in par] == ["EURUSD", "GBPUSD"] and strip(seq) == strip(par)
    assert (tmp_path / "memo" / "EURUSD.pkl").exists()
    assert all("_key" in e for x in par for e in x["entries"])


# ------------------------------------------------------------------ status updates / weekend
def test_status_setting_in_schema():
    s = S.BY_NAME["status_updates"]
    assert s["default"] == "every_4h" and s["choices"] == ["each_run", "every_4h", "off"] and s["group"] == "Alerts"
    assert S.load({})["status_updates"] == "every_4h" and S.load({"status_updates": "bad"})["status_updates"] == "every_4h"
    assert S.clean("status_updates", "each_run") == "each_run"


def test_status_due():
    assert live.status_due("each_run", NOW.isoformat(), NOW)
    assert not live.status_due("off", None, NOW, ["x"])
    assert live.status_due("every_4h", None, NOW)
    assert not live.status_due("every_4h", (NOW - pd.Timedelta(hours=1)).isoformat(), NOW)
    assert live.status_due("every_4h", (NOW - pd.Timedelta(hours=1)).isoformat(), NOW, ["EURUSD: boom"])
    assert live.status_due("every_4h", (NOW - pd.Timedelta(minutes=235)).isoformat(), NOW)  # late cron still sends


def test_format_status():
    t = live.format_status(NOW, NOW.replace(minute=7), NOW.replace(minute=11), 42.4, 27, 28, 5, 1, 2, ["GBPJPY: x"])
    for part in ("bot alive", "Pairs checked: 27/28", "Active biases: 5 (1 NO_TRADE)", "Pending entries: 2",
                 "Start delay: 4 min", "Run time: 42 s", "Errors (1): GBPJPY: x"):
        assert part in t
    assert "Errors: none" in live.format_status(NOW, NOW, NOW, 1, 1, 1, 0, 0, None, [])


def test_weekend_close_day():
    ny = lambda s: pd.Timestamp(s, tz="America/New_York").tz_convert("UTC")  # noqa: E731
    assert live.weekend_close_day(ny("2026-10-16 16:30")) is None
    assert live.weekend_close_day(ny("2026-10-16 17:07")) == "2026-10-16"
    assert live.weekend_close_day(ny("2026-10-17 09:00")) == "2026-10-16"
    assert live.weekend_close_day(ny("2026-10-18 16:07")) == "2026-10-16"
    assert live.weekend_close_day(ny("2026-10-18 17:07")) is None


def _fake_db(monkeypatch, settings):
    store, runs, sent = {}, {}, []
    monkeypatch.setenv("DATABASE_URL", "mysql://u:p@h/db")
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.setattr(db, "apply_schema", lambda: None)
    monkeypatch.setattr(db, "start_run", lambda job, pl, st: runs.setdefault(len(runs) + 1, {}) is not None and len(runs))
    monkeypatch.setattr(db, "finish_run", lambda i, ok, note: runs[i].update(ok=ok, note=note))
    monkeypatch.setattr(db, "get_setting", lambda k, d=None: settings.get(k, d))
    monkeypatch.setattr(db, "get_settings", lambda: dict(settings))
    monkeypatch.setattr(db, "set_setting", lambda k, v: settings.__setitem__(k, v))
    monkeypatch.setattr(db, "upsert_bias", lambda r: store.__setitem__((r["pair"], r["story"], r["tap_time"]), dict(r)))
    monkeypatch.setattr(db, "get_bias", lambda p, s=None: [r for k, r in store.items() if k[0] == p])
    monkeypatch.setattr(db, "get_entries", lambda p: [])
    monkeypatch.setattr(db, "upsert_entry", lambda e: 1)
    monkeypatch.setattr(db, "count_entries", lambda st: 3)
    monkeypatch.setattr(live, "send_telegram", lambda t: sent.append(t) or True)
    monkeypatch.setattr(live, "recent", lambda p, days: walk(24 * 400, seed=3))
    return store, runs, sent


class _Clock(datetime):
    T = None

    @classmethod
    def now(cls, tz=None):
        return cls.T


def test_main_weekend_skip_and_status(monkeypatch, tmp_path):
    settings = {"pairs": "EURUSD", "status_updates": "each_run"}
    store, runs, sent = _fake_db(monkeypatch, settings)
    downloads = []
    monkeypatch.setattr(live, "prepare_candles", lambda pairs, now: downloads.append(list(pairs)) or {})
    monkeypatch.setattr(live.candles_store, "DIR", str(tmp_path))
    monkeypatch.setattr(live, "datetime", _Clock)
    monkeypatch.setenv("GITHUB_EVENT_NAME", "schedule")
    ny = lambda s: pd.Timestamp(s, tz="America/New_York").tz_convert("UTC").to_pydatetime()  # noqa: E731

    _Clock.T = ny("2026-10-16 17:09")  # first run after the Friday close: full run + "last run" note
    assert live.main([]) == 0 and downloads == [["EURUSD"]] and settings["weekend_done"] == "2026-10-16"
    assert "bot alive" in sent[-1] and "Market closed" in sent[-1] and "Pending entries: 3" in sent[-1]
    n = len(sent)
    _Clock.T = ny("2026-10-17 10:07")  # Saturday: skipped before any download, no message
    assert live.main([]) == 0 and len(downloads) == 1 and len(sent) == n and "weekend" in runs[2]["note"]
    _Clock.T = ny("2026-10-18 17:07")  # Sunday open: runs again
    assert live.main([]) == 0 and len(downloads) == 2
    monkeypatch.setenv("GITHUB_EVENT_NAME", "workflow_dispatch")  # manual run on a weekend is never skipped
    _Clock.T = ny("2026-10-17 11:00")
    assert live.main([]) == 0 and len(downloads) == 3


def test_main_status_every_4h_and_download_errors(monkeypatch, tmp_path):
    settings = {"pairs": "EURUSD,GBPUSD"}
    store, runs, sent = _fake_db(monkeypatch, settings)
    monkeypatch.setattr(live, "prepare_candles", lambda pairs, now: {"GBPUSD": "RuntimeError: download failed"})
    monkeypatch.setattr(live.candles_store, "DIR", str(tmp_path))
    assert live.main([]) == 0  # EURUSD worked
    assert any("Errors (1): GBPUSD: download" in t for t in sent) and "last_status" in settings
    assert runs[1]["ok"] is False and "pairs ok 1" in runs[1]["note"]
    monkeypatch.setattr(live, "prepare_candles", lambda pairs, now: {})
    n = len(sent)
    assert live.main([]) == 0
    assert not any("bot alive" in t for t in sent[n:])  # every_4h: sent less than 4 h ago, no errors


# ------------------------------------------------------------------ no_trade stored in table bias
def test_mw_conflict_reason_and_change_detection():
    r = lambda st, side: {"story": st, "side": side, "status": "CONFIRMED", "confirm_time": datetime(2026, 10, 1)}  # noqa
    rows = live.mark_mw_conflict([r("M", "SELL"), r("W", "BUY"), r("D", "BUY")])
    assert rows[2]["no_trade"] is True and rows[2]["no_trade_reason"] == "M/W conflict"
    base = {"status": "CONFIRMED", "side": "BUY", "level": 1.0, "point_b": 1.0, "target": 1.1, "invalidation": 1.0}
    assert live._same({**base, "no_trade": True}, {**base, "no_trade": 1})
    assert not live._same({**base, "no_trade": True}, {**base, "no_trade": 0})


def test_upsert_bias_writes_no_trade(monkeypatch):
    got = []
    monkeypatch.setattr(db, "execute", lambda sql, args=None: got.append((sql, args)) or 5)
    row = {"pair": "EURUSD", "story": "D", "side": "BUY", "status": "CONFIRMED", "tap_time": datetime(2026, 10, 1)}
    db.upsert_bias({**row, "no_trade": True, "no_trade_reason": "M/W conflict"})
    db.upsert_bias(row)
    cols = db.BIAS_COLS
    a1, a2 = dict(zip(cols, got[0][1])), dict(zip(cols, got[1][1]))
    assert a1["no_trade"] == 1 and a1["no_trade_reason"] == "M/W conflict"
    assert a2["no_trade"] == 0 and a2["no_trade_reason"] is None
    assert "no_trade=VALUES(no_trade)" in got[0][0]


def test_migrate_adds_missing_columns(monkeypatch):
    have, ddl = {"no_trade"}, []
    monkeypatch.setattr(db, "query", lambda sql, args: [{"n": int(args[1] in have)}])
    monkeypatch.setattr(db, "execute", lambda sql, args=None: ddl.append(sql))
    db.migrate()
    assert ddl == ["ALTER TABLE bias ADD COLUMN no_trade_reason VARCHAR(64) NULL AFTER no_trade",
                   "ALTER TABLE bias ADD COLUMN rule VARCHAR(32) NULL AFTER no_trade_reason",
                   "ALTER TABLE bias ADD COLUMN end_reason VARCHAR(200) NULL AFTER rule",
                   "ALTER TABLE bias ADD COLUMN breakout_time DATETIME NULL AFTER end_reason",
                   "ALTER TABLE bias ADD COLUMN next_day TINYINT(1) NULL AFTER breakout_time",
                   "ALTER TABLE bias ADD COLUMN retrace TINYINT(1) NULL AFTER next_day",
                   "ALTER TABLE entries ADD COLUMN model VARCHAR(16) NOT NULL DEFAULT 'continuation' AFTER side"]
    schema = (ROOT / "db" / "schema.sql").read_text()
    assert "no_trade      TINYINT(1)" in schema and "no_trade_reason VARCHAR(64)" in schema


def test_webapp_shows_no_trade():
    assert '"SELECT * FROM bias"' in (ROOT / "webapp" / "app.py").read_text()
    assert "no_trade" in (ROOT / "webapp" / "static" / "app.js").read_text()


# ------------------------------------------------------------------ backtest: M/W filter applied and reported
def test_backtest_applies_mw_filter(monkeypatch, tmp_path):
    h1 = walk(24 * 1500, seed=7)
    monkeypatch.setattr(backtest.store, "hourly", lambda pair, s, e: h1)
    cfg = {**backtest.DEFAULT, "trend_filter": False, "htf_filter": False}
    rows = backtest.pair_rows("EURUSD", 2020, 2030, ["D"], cfg)  # M and W computed for the filter, not returned
    assert rows and {r["story"] for r in rows} == {"D"} and all("no_trade" in r for r in rows)
    df = pd.DataFrame(rows)
    df.loc[df.index[:3], "no_trade"] = True  # make sure both groups exist
    backtest.report(df.copy(), cfg, tmp_path / "R.md")
    text = (tmp_path / "R.md").read_text()
    assert "## M/W conflict filter (D story)" in text and "NO_TRADE: M/W conflict" in text
    assert "all D stories (filter off)" in text and "tradable (filter on)" in text
    by_story = text.split("## By story\n")[1].split("##")[0]
    d_line = [ln for ln in by_story.splitlines() if ln.startswith("| D ")][0]
    assert int(d_line.split("|")[2]) == int((~df["no_trade"].astype(bool)).sum())  # NO_TRADE rows not scored
    off = backtest.pair_rows("EURUSD", 2020, 2030, ["D"], {**cfg, "mw_conflict_filter": False})
    assert not any(r.get("no_trade") for r in off)


def test_backtest_run_pairs_parallel_order():
    assert backtest.run_pairs(abs, [-3, 1, -2], workers=2) == [3, 1, 2]
