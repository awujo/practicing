"""Opt-in real MySQL8 regression. SLK_TEST_MYSQL must name a disposable test database."""
import hashlib
import hmac
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from urllib.parse import urlencode
import pytest

pytestmark = pytest.mark.skipif(not os.environ.get("SLK_TEST_MYSQL"), reason="requires disposable MySQL8")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "webapp"))


def test_real_multiuser_isolation(monkeypatch):
    from fastapi.testclient import TestClient
    from slk import db, tenancy as T
    import app
    monkeypatch.setenv("DATABASE_URL", os.environ["SLK_TEST_MYSQL"])
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "777000111")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:local-test")
    db._conn = None
    db.apply_schema()
    db.apply_schema()
    users = (int(time.time()) * 100 + 1, int(time.time()) * 100 + 2)
    def headers(uid):
        fields = {"auth_date": str(int(time.time())), "user": json.dumps({"id": uid})}
        check = "\n".join(f"{k}={v}" for k,v in sorted(fields.items()))
        secret = hmac.new(b"WebAppData", b"123:local-test", hashlib.sha256).digest()
        fields["hash"] = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
        return {"X-Telegram-Init-Data": urlencode(fields)}
    with TestClient(app.app) as client:
        for uid, pair in zip(users, ("EURJPY", "GBPCHF")):
            r = client.get("/api/settings", headers=headers(uid))
            assert r.status_code == 200 and r.json()["pairs"] == T.STARTER["pairs"]
            assert client.post("/api/settings", json={"pairs":pair,"alert_tapped":"off"}, headers=headers(uid)).status_code == 200
            with T.scope(uid):
                bid = db.upsert_bias(dict(pair=pair,story="D",side="SELL",status="CONFIRMED",tap_time=datetime(2026,10,20),confirm_time=datetime(2026,10,21)))
                db.upsert_entry(dict(bias_id=bid,pair=pair,side="SELL",tf="H4",entry=1,stop=2,tp1=.5,tp2=.3,status="PENDING"))
                db.upsert_tf_state(pair,"D","down")
                rid=db.start_run("live",datetime.now(),datetime.now()); db.finish_run(rid,True)
        with T.scope(users[0]):
            first_bias = db.get_bias("EURJPY")[0]["id"]
        with T.scope(users[1]):
            import pymysql
            with pytest.raises(pymysql.err.IntegrityError):
                db.upsert_entry(dict(bias_id=first_bias,pair="GBPCHF",side="SELL",tf="H4",entry=2,status="PENDING"))
        def read(uid):
            for _ in range(5):
                settings=client.get("/api/settings",headers=headers(uid)).json()
                biases=client.get("/api/bias",headers=headers(uid)).json()
                entries=client.get("/api/entries",headers=headers(uid)).json()
                assert len(biases)==len(entries)==1
                assert biases[0]["pair"]==entries[0]["pair"]==settings["pairs"]
                assert client.post("/api/entries/1/approve",headers=headers(uid)).status_code==403
            return settings["pairs"]
        with ThreadPoolExecutor(2) as pool:
            assert list(pool.map(read,users))==["EURJPY","GBPCHF"]
        owner=client.get("/api/settings",headers=headers(777000111)).json()
        assert owner["pairs"] not in ("EURJPY","GBPCHF")
        sent=[]
        monkeypatch.setattr(app,"send_private_digest",lambda uid,text:sent.append((uid,text)))
        for uid in users:
            assert client.post("/api/bias/send-eligible",headers=headers(uid)).status_code==200
        assert sent[0][0]==users[0] and "EURJPY" in sent[0][1] and "GBPCHF" not in sent[0][1]
        assert client.post("/api/bias/send-eligible",headers=headers(users[0])).status_code==429
        assert sent[1][0]==users[1] and "GBPCHF" in sent[1][1] and "EURJPY" not in sent[1][1]
    assert T.USER.get() is None
