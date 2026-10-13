"""M/W conflict -> NO_TRADE for D stories, and live entry alerts (fakes only, no network/DB)."""
from datetime import datetime

from slk import db
from slk.live import (entry_rows, filter_alerts, format_entry_alert, mark_mw_conflict, reconcile_entries)
from slk.story import DEFAULT, apply_mw_filter, mw_conflict


def r(story, side, status="CONFIRMED", day=1, **kw):
    x = {"pair": "EURUSD", "story": story, "side": side, "status": status, "tap_time": datetime(2026, 10, day),
         "confirm_time": datetime(2026, 10, day, 12) if status == "CONFIRMED" else None, "target": 1.07}
    x.update(kw)
    return x


def test_default_has_flag():
    assert DEFAULT["mw_conflict_filter"] is True


def test_mw_conflict_latest_only():
    assert mw_conflict([r("M", "SELL")], [r("W", "BUY")])
    assert not mw_conflict([r("M", "SELL")], [r("W", "BUY", day=1), r("W", "SELL", day=5)])
    assert not mw_conflict([], [r("W", "BUY")])
    # only stories confirmed by t count
    assert not mw_conflict([r("M", "SELL")], [r("W", "BUY", day=9)], t=datetime(2026, 10, 5))


def test_apply_mw_filter_backtest():
    d = [r("D", "SELL", day=3), r("D", "SELL", day=10)]
    out = apply_mw_filter(d, [r("M", "SELL")], [r("W", "BUY", day=8)])
    assert [x["no_trade"] for x in out] == [False, True]
    assert all("no_trade" not in x for x in apply_mw_filter(d, [r("M", "SELL")], [r("W", "BUY")],
                                                            {"mw_conflict_filter": False}))


def test_live_marks_d_and_filters_alerts():
    rows = [r("M", "SELL"), r("W", "BUY"), r("D", "BUY")]
    mark_mw_conflict(rows)
    assert rows[2]["no_trade"] and not rows[0].get("no_trade")
    alerts = [("CONFIRMED", rows[2]), ("TARGET_HIT", rows[2]), ("CONFIRMED", rows[1])]
    assert filter_alerts(alerts) == alerts[1:]
    rows2 = [r("M", "SELL"), r("W", "BUY"), r("D", "BUY")]
    mark_mw_conflict(rows2, {"mw_conflict_filter": False})
    assert not rows2[2].get("no_trade")


def fake_finder(statuses):
    def f(pair, h1, stories, cfg, story_cfg, sim=True):
        assert sim is False
        return [{"status": st, "tf": "H4", "entry": 1.08, "stop": 1.0815, "tp1": 1.0755, "tp2": 1.07,
                 "stop_pips": 15.0} for st in statuses[:len(stories)]]
    return f


def test_entry_rows_only_tradable_confirmed():
    rows = [r("D", "SELL", _story={"x": 1}), r("D", "SELL", day=2, _story={}, no_trade=True),
            r("W", "SELL", status="TAPPED", _story={})]
    out = entry_rows("EURUSD", None, rows, {("D", datetime(2026, 10, 1)): 7}, finder=fake_finder(["PENDING"]))
    assert len(out) == 1 and out[0]["bias_id"] == 7 and out[0]["status"] == "PENDING" and out[0]["side"] == "SELL"
    assert entry_rows("EURUSD", None, rows[:1], {}, finder=fake_finder(["NO_SETUP"])) == []


def test_reconcile_entries_and_alerts():
    e = {"bias_id": 7, "pair": "EURUSD", "tf": "H4", "side": "SELL", "entry": 1.08, "stop": 1.0815,
         "tp1": 1.0755, "tp2": 1.07, "status": "PENDING", "stop_pips": 15.0}
    w, a = reconcile_entries([e], [])
    assert w == [e] and a == [("ENTRY_PENDING", e)]
    stored = {**e, "id": 3}
    assert reconcile_entries([e], [stored]) == ([], [])
    w, a = reconcile_entries([{**e, "status": "TRIGGERED"}], [stored])
    assert w[0]["id"] == 3 and a[0][0] == "ENTRY_TRIGGERED"
    w, a = reconcile_entries([{**e, "status": "MISSED"}], [stored])
    assert w[0]["status"] == "MISSED" and a == []
    assert reconcile_entries([{**e, "status": "MISSED"}], [{**stored, "status": "APPROVED"}]) == ([], [])


def test_entry_alert_text():
    e = {"pair": "EURUSD", "tf": "H4", "side": "SELL", "entry": 1.08, "stop": 1.0815, "tp1": 1.0755,
         "tp2": 1.07, "stop_pips": 15.0}
    m = format_entry_alert("ENTRY_PENDING", e, "confirm")
    assert m.splitlines()[0] == "EURUSD | H4 | SELL | NEW ENTRY (pending limit)"
    assert "Entry 1.08000  Stop 1.08150 (15.0 pips)" in m and "TP1 1.07550  TP2 1.07000" in m
    assert "Confirm in Mini App" in m
    assert "Confirm" not in format_entry_alert("ENTRY_PENDING", e, "off")
    assert "TRIGGERED" in format_entry_alert("ENTRY_TRIGGERED", e)


def test_upsert_entry_sql(monkeypatch):
    calls = []
    monkeypatch.setattr(db, "query", lambda sql, a=None: calls.append(("q", sql, a)) or [])
    monkeypatch.setattr(db, "execute", lambda sql, a=None: calls.append(("x", sql, a)) or 11)
    e = {"bias_id": 7, "pair": "EURUSD", "tf": "H4", "side": "SELL", "entry": 1.08, "stop": 1.0815,
         "tp1": 1.0755, "tp2": 1.07, "status": "PENDING"}
    assert db.upsert_entry(e) == 11 and calls[-1][1].startswith("INSERT INTO entries")
    calls.clear()
    assert db.upsert_entry({**e, "id": 3, "status": "TRIGGERED"}) == 3
    assert calls[0][1].startswith("UPDATE entries") and calls[0][2][-1] == 3 and "TRIGGERED" in calls[0][2]


def test_env_password_wins(monkeypatch):
    monkeypatch.setenv("DATABASE_PASSWORD", " right ")
    assert db.parse_url("mysql://u:wrong@h/d")["password"] == "right"
    monkeypatch.setenv("DATABASE_PASSWORD", "  ")
    assert db.parse_url("mysql://u:p%40ss@h/d")["password"] == "p@ss"
