from pathlib import Path
import pytest
from slk import tenancy as T
from slk import live


def test_scope_isolation_and_reset(monkeypatch):
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "1")
    sql = "SELECT * FROM bias WHERE status=%s OR status=%s ORDER BY id DESC LIMIT %s"
    assert T.scoped_sql(sql) == sql
    with T.scope(2):
        scoped = T.scoped_sql(sql)
        assert "FROM tenant_bias WHERE user_id=2 AND (status=%s OR status=%s)" in scoped
        with T.scope(3):
            assert "user_id=3" in T.scoped_sql(sql)
        assert "user_id=2" in T.scoped_sql(sql)
    with T.scope(1):
        assert T.scoped_sql(sql) == sql
    assert T.USER.get() is None


def test_scoped_insert_and_update():
    with T.scope(42):
        sql = T.scoped_sql("INSERT INTO settings (k,v) VALUES (%s,%s) ON DUPLICATE KEY UPDATE v=VALUES(v)")
        assert "tenant_settings (user_id, k,v) VALUES (42, %s,%s)" in sql
        assert "ON DUPLICATE KEY UPDATE v=VALUES(v)" in sql
        assert "WHERE user_id=42 AND (id=%s)" in T.scoped_sql("UPDATE entries SET status=%s WHERE id=%s")
        for sql in ["SELECT * FROM entries JOIN bias ON entries.bias_id=bias.id", "SELECT * FROM bias; SELECT * FROM bias"]:
            with pytest.raises(ValueError):
                T.scoped_sql(sql)


def test_schema_ownership_keys_and_foreign_key():
    ddl = "\n".join(T.schema_sql(Path("db/schema.sql").read_text()))
    assert "UNIQUE KEY uq_bias (user_id, pair, story, tap_time)" in ddl
    assert "PRIMARY KEY (user_id, pair, story)" in ddl
    assert "PRIMARY KEY (user_id, k)" in ddl
    assert "CONSTRAINT fk_entries_bias" not in ddl
    assert "REFERENCES tenant_bias(user_id, id)" in ddl


def test_shared_compute_never_shares_mutable_reconciliation(monkeypatch):
    called = []
    monkeypatch.setattr(live, "compute_all", lambda jobs: called.append(jobs) or [{"rows": [{"id": 1}]} for _ in jobs])
    cache = {}
    first = live.shared_compute([("EURUSD", {"rule": 1})], cache)
    first[0]["rows"][0]["id"] = 8
    second = live.shared_compute([("EURUSD", {"rule": 1})], cache)
    assert second[0]["rows"][0]["id"] == 1 and len(called) == 1
    live.shared_compute([("EURUSD", {"rule": 2})], cache)
    assert len(called) == 2


def test_runner_only_downloads_combined_watchlists(monkeypatch):
    from argparse import Namespace
    from datetime import datetime, timezone
    from slk import db
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "1")
    profiles = {1:{"pairs":"EURUSD,GBPUSD"}, 2:{"pairs":"GBPUSD,EURJPY"}, 3:{"pairs":"USDJPY"}}
    monkeypatch.setattr(db,"apply_schema",lambda:None)
    monkeypatch.setattr(db,"query",lambda *a:[{"user_id":2},{"user_id":3}])
    monkeypatch.setattr(db,"get_setting",lambda *a:"0")
    monkeypatch.setattr(db,"get_settings",lambda:profiles[T.USER.get()])
    monkeypatch.setattr(db,"set_setting",lambda *a:None)
    downloaded, processed = [], []
    monkeypatch.setattr(live,"prepare_candles",lambda pairs,now:downloaded.append(pairs) or {})
    monkeypatch.setattr(live,"main",lambda argv,**kw:processed.append((T.USER.get(),kw["_watch_pairs"],kw["_snapshot"])) or 0)
    assert live.run_user_watchlists([],Namespace(pairs="",stories=""),datetime.now(timezone.utc))==0
    assert downloaded==[["EURJPY","EURUSD","GBPUSD","USDJPY"]]
    assert [p[0] for p in processed]==[1,2,3]
    assert processed[1][1]==["GBPUSD","EURJPY"]
    assert T.USER.get() is None


def test_telegram_uses_scoped_recipient(monkeypatch):
    import json
    import urllib.parse
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN","test-token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID","1")
    calls=[]
    class Response:
        def __enter__(self): return self
        def __exit__(self,*a): pass
        def read(self): return json.dumps({"ok":True}).encode()
    monkeypatch.setattr(live.urllib.request,"urlopen",lambda url,body,timeout:calls.append(urllib.parse.parse_qs(body.decode())) or Response())
    with T.scope(42):
        assert live.send_telegram("test")
    assert calls[0]["chat_id"]==["42"]


def test_tenant_settings_error_fails_closed(monkeypatch):
    class BrokenDB:
        @staticmethod
        def get_settings(): raise RuntimeError("unavailable")
    with T.scope(42):
        with pytest.raises(RuntimeError):
            live._load_settings(BrokenDB)
