"""Paper outcome of filled entries (bot signals, no broker): slk.entry.paper_track, live tracking + alerts, the
entries migration and the Mini App summary. Synthetic bars only (no network, no DB)."""
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from slk import db, live
from slk.entry import DEFAULT, _Pair, paper_track, simulate
from slk.story import DEFAULT as STORY_DEFAULT

P = 0.0001
T0 = pd.Timestamp("2026-10-12 00:00", tz="UTC")  # Monday
FILL = datetime(2026, 10, 12, 2)                  # fill on H1 bar 2


def bars(rows):
    """rows of (open, high, low, close) in pips above 1.1000 -> H1 frame from T0."""
    idx = pd.date_range(T0, periods=len(rows), freq="h")
    return pd.DataFrame(1.1 + np.array(rows, dtype=float) * P, index=idx, columns=["open", "high", "low", "close"])


FLAT = (1, 2, 0, 1)  # inside the range: hits nothing


def buy(**kw):
    """BUY limit at 1.1000, stop 10 pips, TP1 +16 pips (1.6R), TP2 +30 pips (3R), H1 entry TF."""
    r = {"id": 5, "pair": "EURUSD", "tf": "H1", "side": "BUY", "model": "continuation", "entry": 1.1,
         "stop": 1.1 - 10 * P, "tp1": 1.1 + 16 * P, "tp2": 1.1 + 30 * P, "status": "TRIGGERED",
         "filled_at": FILL, "closed_at": None}
    r.update(kw)
    return r


def pre():
    # bars 0-1 are BEFORE the fill: a low through the stop and a high through TP2 there must not count
    return [(1, 40, -20, 1), (1, 2, 0, 1)]


def test_tp1_then_open():
    t = paper_track(buy(), bars(pre() + [(1, 2, 0, 1), (1, 17, 0, 15), FLAT]))
    assert t["status"] == "TP1_HIT" and t["result_r"] == 1.6 and t["result_r_tp2"] is None
    assert t["closed_at"] is None and t["tp1_at"] == datetime(2026, 10, 12, 3) and t["events"] == ["TP1"]
    assert t["hit_price"] == pytest.approx(1.1016)


def test_tp2():
    t = paper_track(buy(), bars(pre() + [FLAT, (1, 17, 0, 15), (15, 31, 14, 30)]))
    assert t["status"] == "TP2_HIT" and t["result_r"] == 1.6 and t["result_r_tp2"] == 3.0
    assert t["closed_at"] == datetime(2026, 10, 12, 4) and t["events"] == ["TP1", "TP2"]


def test_sl_before_tp1():
    t = paper_track(buy(), bars(pre() + [FLAT, (1, 5, -11, -9), FLAT]))
    assert t["status"] == "SL_HIT" and t["result_r"] == -1.0 and t["result_r_tp2"] == -1.0
    assert t["hit_price"] == pytest.approx(1.099) and t["closed_at"] == datetime(2026, 10, 12, 3)
    assert t["events"] == ["SL"]


def test_same_bar_stop_and_tp_is_a_loss():
    t = paper_track(buy(), bars(pre() + [FLAT, (1, 31, -11, 5)]))
    assert t["status"] == "SL_HIT" and t["result_r"] == -1.0


def test_fill_bar_only_stops_out():
    t = paper_track(buy(), bars(pre() + [(1, 31, 0, 25)]))  # TP2 inside the fill bar: not counted
    assert t["status"] == "TRIGGERED"
    assert paper_track(buy(), bars(pre() + [(1, 5, -11, 0)]))["status"] == "SL_HIT"


def test_stop_after_tp1():
    t = paper_track(buy(), bars(pre() + [FLAT, (1, 17, 0, 15), (15, 15, -11, -10)]))
    assert t["status"] == "TP1_HIT" and t["result_r"] == 1.6 and t["result_r_tp2"] == -1.0
    assert t["closed_at"] == datetime(2026, 10, 12, 4) and t["events"] == ["TP1", "SL_AFTER_TP1"]


def test_expiry():
    cfg = {"max_trade_bars": 3}  # H1 entry TF: fill bar + 2 more
    t = paper_track(buy(), bars(pre() + [FLAT, FLAT, (1, 6, 0, 5), (5, 40, 4, 35)]), cfg)
    assert t["status"] == "EXPIRED" and t["result_r"] == 0.5 and t["result_r_tp2"] == 0.5
    assert t["closed_at"] == datetime(2026, 10, 12, 4) and t["events"] == [] and t["hit_price"] == pytest.approx(1.1005)
    assert paper_track(buy(), bars(pre() + [FLAT, FLAT]), cfg)["status"] == "TRIGGERED"  # holding time not over yet
    t = paper_track(buy(), bars(pre() + [FLAT, (1, 17, 0, 15), (15, 16, 14, 15), FLAT]), cfg)  # TP1, then time out
    assert t["status"] == "TP1_HIT" and t["result_r_tp2"] == 1.5 and t["closed_at"] == datetime(2026, 10, 12, 4)


def test_entry_tf_sets_holding_time():
    # H4 entry: max_trade_bars 1 = 4 H1 bars from the fill
    h = bars(pre() + [FLAT, FLAT, FLAT, FLAT, (1, 40, 0, 35)])
    assert paper_track(buy(tf="H4"), h, {"max_trade_bars": 1})["status"] == "EXPIRED"
    assert paper_track(buy(tf="H4"), h, {"max_trade_bars": 2})["status"] == "TP2_HIT"  # 8 hours: bar 6 counts


def test_sell_mirror_and_spread():
    s = buy(side="SELL", stop=1.1 + 10 * P, tp1=1.1 - 16 * P, tp2=1.1 - 30 * P)
    t = paper_track(s, bars(pre() + [FLAT, (0, 1, -16.5, -15), FLAT]))
    assert t["status"] == "TP1_HIT" and t["result_r"] == 1.6
    # spread 1 pip: a SELL's TP triggers on the ask (bid + spread), so -16.5 bid is not enough any more
    assert paper_track(s, bars(pre() + [FLAT, (0, 1, -16.5, -15), FLAT]), {"spread_pips": 1.0})["status"] == "TRIGGERED"


def test_same_rules_as_backtest_simulate():
    """paper_track = the backtest's simulate (TP1 / TP2 variants) on the same bars and fill bar."""
    rng = np.random.default_rng(7)
    rows, c = pre(), 0.0
    for _ in range(80):
        o, c = c, c + rng.normal(0, 4)
        rows.append((o, max(o, c) + abs(rng.normal(0, 2)), min(o, c) - abs(rng.normal(0, 2)), c))
    h = bars(rows)
    for stop, tp1, tp2 in ((-10, 16, 30), (-6, 9, 12), (-15, 20, 45)):
        row = buy(stop=1.1 + stop * P, tp1=1.1 + tp1 * P, tp2=1.1 + tp2 * P)
        cfg = {**DEFAULT, "max_trade_bars": 20, "story_cfg": STORY_DEFAULT}
        sim = simulate({**row, "status": "TRIGGERED", "_fill": 2}, _Pair("EURUSD", h, cfg))
        t = paper_track(row, h, cfg)
        assert t["result_r"] == sim["tp1_R"]
        assert t["result_r_tp2"] == sim["tp2_R"]
        exp = {"loss": "SL_HIT", "timeout": "EXPIRED"}.get(sim["tp1_outcome"], "TP2_HIT" if sim["tp2_outcome"] == "win"
                                                                             else "TP1_HIT")
        assert t["status"] == exp


# ------------------------------------------------------------------ live: reconcile, tracking, alerts
def test_entry_rows_carry_fill_time_and_legacy_fill_gets_stored():
    def finder(pair, h1, stories, cfg, story_cfg, sim=True):
        return [{"status": "TRIGGERED", "tf": "H4", "entry": 1.1, "stop": 1.099, "tp1": 1.1016, "tp2": 1.103,
                 "fill_time": "2026-10-12 02:00"}]
    rows = [{"pair": "EURUSD", "story": "D", "side": "BUY", "status": "CONFIRMED", "tap_time": datetime(2026, 10, 1),
             "_story": {"x": 1}}]
    e = live.entry_rows("EURUSD", None, rows, {("D", datetime(2026, 10, 1)): 7}, finder=finder)[0]
    assert e["filled_at"] == FILL
    w, a = live.reconcile_entries([e], [{**e, "id": 3, "filled_at": None}])
    assert w == [{**e, "id": 3}] and a == []
    assert live.reconcile_entries([e], [{**e, "id": 3}]) == ([], [])
    # a tracked row is never touched again by the engine rows
    assert live.reconcile_entries([e], [{**e, "id": 3, "status": "TP1_HIT"}]) == ([], [])


def test_track_entries_no_duplicate_alerts():
    h = [FLAT, (1, 17, 0, 15), FLAT]
    stored = buy()
    out = live.track_entries([stored], bars(pre() + h))
    assert len(out) == 1 and out[0][1]["status"] == "TP1_HIT" and out[0][2] == ["TP1"]
    stored = {**stored, **out[0][1]}                       # what the DB now holds
    assert live.track_entries([stored], bars(pre() + h)) == []          # next hour, nothing new: no alert
    assert live.track_entries([stored], bars(pre() + h + [FLAT])) == []
    out = live.track_entries([stored], bars(pre() + h + [(1, 31, 0, 30)]))
    assert out[0][1]["status"] == "TP2_HIT" and out[0][2] == ["TP2"]  # TP1 is not announced again
    stored = {**stored, **out[0][1]}
    assert live.track_entries([stored], bars(pre() + h + [(1, 31, 0, 30), (1, 2, -30, -20)])) == []  # closed
    # not trackable: pending, no fill time, other statuses
    assert live.track_entries([buy(status="PENDING"), buy(filled_at=None), buy(status="SL_HIT")],
                              bars(pre() + [FLAT, (1, 5, -11, -9)])) == []


def test_cancel_entries_when_story_ended():
    ents = [buy(id=1, status="PENDING", bias_id=7), buy(id=2, status="PENDING", bias_id=8),
            buy(id=3, status="APPROVED", bias_id=7), buy(id=4, status="TRIGGERED", bias_id=7)]
    got = live.cancel_entries(ents, {7: "TARGET_HIT", 8: "CONFIRMED"})
    assert [(e["id"], f["status"]) for e, f in got] == [(1, "CANCELLED")]


def test_result_alert_text():
    e = buy(tf="H4")
    assert live.format_result_alert("TP1", e, {"result_r": 1.6}).splitlines()[0] == \
        "✅ TP1 hit · EURUSD H4 BUY · +1.6R"
    assert live.format_result_alert("TP2", e, {"result_r": 1.6, "result_r_tp2": 3.0}).splitlines()[0] == \
        "✅ TP2 hit · EURUSD H4 BUY · +3R"
    m = live.format_result_alert("SL", e, {"result_r": -1.0})
    assert m.splitlines()[0] == "❌ Stop hit · EURUSD H4 BUY · -1R" and "not a broker trade" in m
    assert "Stop hit after TP1" in live.format_result_alert("SL_AFTER_TP1", e, {"result_r": 1.6, "result_r_tp2": -1})


def test_update_entry_result_is_guarded(monkeypatch):
    calls = []

    class Cur:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def execute(self, sql, args):
            calls.append((sql, args))
            return 1

    monkeypatch.setattr(db, "_c", lambda: type("C", (), {"cursor": lambda self: Cur()})())
    assert db.update_entry_result(5, "TRIGGERED", {"status": "SL_HIT", "result_r": -1.0, "closed_at": FILL}) == 1
    sql, args = calls[0]
    assert sql == ("UPDATE entries SET status=%s, result_r=%s, closed_at=%s "
                   "WHERE id=%s AND status=%s AND closed_at IS NULL")
    assert args == ["SL_HIT", -1.0, FILL, 5, "TRIGGERED"]


def test_main_tracks_and_alerts_once(monkeypatch, tmp_path):
    """Full live run with an in-memory DB: a stored TRIGGERED entry hits TP1 -> one alert, stored; second run: none."""
    from tests.test_efficiency import _fake_db
    settings = {"pairs": "EURUSD"}
    store, runs, sent = _fake_db(monkeypatch, settings)
    ents = {5: buy()}
    monkeypatch.setattr(db, "get_entries", lambda p: [dict(e) for e in ents.values()])

    def upd(eid, old, f):  # same guard as the SQL
        e = ents[eid]
        if e["status"] != old or e.get("closed_at") is not None:
            return 0
        e.update(f)
        return 1
    monkeypatch.setattr(db, "update_entry_result", upd)
    monkeypatch.setattr(live, "prepare_candles", lambda pairs, now: {})
    monkeypatch.setattr(live.candles_store, "DIR", str(tmp_path))
    rows = pre() + [FLAT, (1, 17, 0, 15)] + [FLAT] * 3
    monkeypatch.setattr(live, "recent", lambda p, days: bars(rows))
    monkeypatch.setattr(live, "compute_all", lambda jobs: [{"pair": "EURUSD", "rows": [], "entries": []}])
    monkeypatch.setattr(live, "datetime", type("D", (datetime,), {"now": classmethod(
        lambda cls, tz=None: datetime(2026, 10, 12, 8, 7, tzinfo=tz))}))
    assert live.main([]) == 0 and runs[1]["ok"]
    assert ents[5]["status"] == "TP1_HIT" and ents[5]["result_r"] == 1.6
    hits = [t for t in sent if "TP1 hit" in t]
    assert len(hits) == 1 and hits[0].startswith("✅ TP1 hit · EURUSD H1 BUY · +1.6R")
    assert live.main([]) == 0 and len([t for t in sent if "TP1 hit" in t]) == 1


def test_main_ignores_forming_hour(monkeypatch, tmp_path):
    """Look-ahead: the still-forming H1 bar (here the one that would hit the stop) is not used."""
    from tests.test_efficiency import _fake_db
    store, runs, sent = _fake_db(monkeypatch, {"pairs": "EURUSD"})
    ents = {5: buy()}
    monkeypatch.setattr(db, "get_entries", lambda p: [dict(e) for e in ents.values()])
    monkeypatch.setattr(db, "update_entry_result", lambda eid, old, f: ents[eid].update(f) or 1)
    monkeypatch.setattr(live, "prepare_candles", lambda pairs, now: {})
    monkeypatch.setattr(live.candles_store, "DIR", str(tmp_path))
    monkeypatch.setattr(live, "recent", lambda p, days: bars(pre() + [FLAT, FLAT, (1, 2, -20, -15)]))  # bar 4 forming
    monkeypatch.setattr(live, "compute_all", lambda jobs: [{"pair": "EURUSD", "rows": [], "entries": []}])
    monkeypatch.setattr(live, "datetime", type("D", (datetime,), {"now": classmethod(
        lambda cls, tz=None: datetime(2026, 10, 12, 4, 30, tzinfo=tz))}))
    assert live.main([]) == 0 and ents[5]["status"] == "TRIGGERED" and not any("Stop hit" in t for t in sent)


# ------------------------------------------------------------------ migration
def test_migrate_paper_columns_idempotent(monkeypatch):
    have = {("bias", c) for c in ("no_trade", "no_trade_reason", "rule", "end_reason", "breakout_time", "next_day",
                                  "retrace")} | {("entries", "model")}
    ddl = []
    monkeypatch.setattr(db, "query", lambda sql, args: [{"n": int(tuple(args) in have)}])

    def ex(sql, args=None):
        ddl.append(sql)
        parts = sql.split()
        have.add((parts[2], parts[5]))
    monkeypatch.setattr(db, "execute", ex)
    db.migrate()
    assert ddl == ["ALTER TABLE entries ADD COLUMN filled_at DATETIME NULL AFTER alerted_at",
                   "ALTER TABLE entries ADD COLUMN result_r DOUBLE NULL AFTER filled_at",
                   "ALTER TABLE entries ADD COLUMN result_r_tp2 DOUBLE NULL AFTER result_r",
                   "ALTER TABLE entries ADD COLUMN hit_price DOUBLE NULL AFTER result_r_tp2",
                   "ALTER TABLE entries ADD COLUMN closed_at DATETIME NULL AFTER hit_price"]
    db.migrate()
    assert len(ddl) == 5  # second run: nothing to add


def test_schema_has_paper_columns():
    root = Path(__file__).resolve().parents[1]
    for f in ("db/schema.sql", "webapp/schema.sql"):
        s = (root / f).read_text()
        for c in ("filled_at   DATETIME", "result_r    DOUBLE", "result_r_tp2 DOUBLE", "hit_price   DOUBLE",
                  "closed_at   DATETIME"):
            assert c in s, (f, c)


# ------------------------------------------------------------------ Mini App summary
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "webapp"))


def test_api_entries_summary(monkeypatch):
    from fastapi.testclient import TestClient
    import app as webapp
    from tests.test_webapp import OWNER, TOKEN, hdr, make_init_data
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", TOKEN)
    monkeypatch.setenv("TELEGRAM_CHAT_ID", str(OWNER))
    monkeypatch.delenv("DATABASE_URL", raising=False)
    rows = [{"status": "TP2_HIT", "model": "continuation", "result_r": 1.6, "result_r_tp2": 3.0},
            {"status": "TP1_HIT", "model": "qmr", "result_r": 2.0, "result_r_tp2": None},
            {"status": "SL_HIT", "model": "continuation", "result_r": -1.0, "result_r_tp2": -1.0},
            {"status": "SL_HIT", "model": "qmr", "result_r": -1.0, "result_r_tp2": -1.0},
            {"status": "EXPIRED", "model": "continuation", "result_r": 0.25, "result_r_tp2": 0.25},
            {"status": "TRIGGERED", "model": "continuation", "result_r": None}]
    calls = []
    monkeypatch.setattr(webapp.db, "query", lambda sql, args=None: calls.append((sql, args)) or rows)
    with TestClient(webapp.app) as c:
        assert c.get("/api/entries/summary").status_code == 403
        assert c.get("/api/entries/summary", headers=hdr(make_init_data(user_id=42))).status_code == 403
        assert calls == []
        s = c.get("/api/entries/summary", headers=hdr(make_init_data())).json()
        assert s["label"] == "Paper results (signals)"
        assert (s["closed"], s["wins"], s["losses"], s["expired"], s["open"]) == (5, 2, 2, 1, 1)
        assert s["win_pct"] == 40.0 and s["total_r"] == 1.85 and s["total_r_tp2"] == 1.25 and s["closed_tp2"] == 4
        assert s["by_model"]["continuation"]["closed"] == 3 and s["by_model"]["qmr"]["closed"] == 2
        assert s["by_model"]["qmr"]["wins"] == 1 and s["by_model"]["qmr"]["total_r"] == 1.0
        c.get("/api/entries?status=closed", headers=hdr(make_init_data()))
        assert "status IN" in calls[-1][0] and calls[-1][1][:4] == ["TP1_HIT", "TP2_HIT", "SL_HIT", "EXPIRED"]
        c.get("/api/entries?status=sl_hit", headers=hdr(make_init_data()))
        assert calls[-1][1][0] == "SL_HIT"
    assert webapp.entries_summary_of([])["win_pct"] is None


def test_ui_shows_paper_results():
    root = Path(__file__).resolve().parents[1] / "webapp" / "static"
    html, js = (root / "index.html").read_text(), (root / "app.js").read_text()
    for st in ("TP1_HIT", "TP2_HIT", "SL_HIT", "EXPIRED"):
        assert f"<option>{st}</option>" in html
    assert 'id="entries-summary"' in html and "/api/entries/summary" in js and "Paper results (signals)" in js
