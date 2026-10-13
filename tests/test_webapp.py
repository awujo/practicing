"""Mini App auth tests: Telegram initData validation, DB mocked."""
import hashlib
import hmac
import json
import sys
import time
from pathlib import Path
from urllib.parse import urlencode

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "webapp"))

from fastapi.testclient import TestClient  # noqa: E402

import app as webapp  # noqa: E402

TOKEN = "123456:TEST-token"
OWNER = 777000111


def make_init_data(user_id=OWNER, auth_date=None, token=TOKEN, tamper=False):
    fields = {
        "query_id": "AAEtest",
        "user": json.dumps({"id": user_id, "first_name": "Owner", "username": "owner"}, separators=(",", ":")),
        "auth_date": str(int(time.time()) if auth_date is None else auth_date),
    }
    check = "\n".join(f"{k}={v}" for k, v in sorted(fields.items()))
    secret = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
    h = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    if tamper:
        h = ("0" if h[0] != "0" else "1") + h[1:]
    return urlencode({**fields, "hash": h})


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", TOKEN)
    monkeypatch.setenv("TELEGRAM_CHAT_ID", str(OWNER))
    monkeypatch.delenv("DATABASE_URL", raising=False)
    store = {"auto_trade": "confirm", "kill_switch": "off"}
    calls = []

    def fake_query(sql, args=None):
        calls.append((sql, args))
        return [{"id": 1, "pair": "EURUSD", "story": "D", "side": "SELL", "status": "CONFIRMED"}]

    def fake_execute(sql, args=None):
        calls.append((sql, args))
        return 1

    monkeypatch.setattr(webapp.db, "query", fake_query)
    monkeypatch.setattr(webapp.db, "execute", fake_execute)
    monkeypatch.setattr(webapp.db, "get_settings", lambda: dict(store))
    monkeypatch.setattr(webapp.db, "set_setting", lambda k, v: store.__setitem__(k, v))
    with TestClient(webapp.app) as c:
        c.calls, c.store = calls, store
        yield c


def hdr(init):
    return {"X-Telegram-Init-Data": init}


def test_healthz_no_auth(client):
    assert client.get("/healthz").json() == {"ok": True}


def test_valid_init_data(client):
    r = client.get("/api/bias", headers=hdr(make_init_data()))
    assert r.status_code == 200
    assert r.json()[0]["pair"] == "EURUSD"


def test_authorization_tma_header(client):
    r = client.get("/api/me", headers={"Authorization": "tma " + make_init_data()})
    assert r.status_code == 200 and r.json()["id"] == OWNER


def test_missing_init_data(client):
    assert client.get("/api/bias").status_code == 403


def test_wrong_hash(client):
    assert client.get("/api/bias", headers=hdr(make_init_data(tamper=True))).status_code == 403


def test_wrong_bot_token(client):
    assert client.get("/api/bias", headers=hdr(make_init_data(token="999:other"))).status_code == 403


def test_wrong_user(client):
    assert client.get("/api/bias", headers=hdr(make_init_data(user_id=42))).status_code == 403


def test_expired(client):
    old = int(time.time()) - 25 * 3600
    assert client.get("/api/bias", headers=hdr(make_init_data(auth_date=old))).status_code == 403


def test_forbidden_never_touches_db(client):
    client.post("/api/entries/5/approve", headers=hdr(make_init_data(user_id=42)))
    client.post("/api/settings", json={"kill_switch": "on"}, headers=hdr(make_init_data(tamper=True)))
    assert client.calls == [] and client.store["kill_switch"] == "off"


def test_approve_and_settings(client):
    r = client.post("/api/entries/5/approve", headers=hdr(make_init_data()))
    assert r.status_code == 200 and r.json()["status"] == "APPROVED"
    assert "status = 'PENDING'" in client.calls[-1][0]
    r = client.post("/api/settings", json={"kill_switch": "on", "pairs": "eurusd, gbpjpy", "stories": "M,D"},
                    headers=hdr(make_init_data()))
    assert r.status_code == 200
    assert client.store["kill_switch"] == "on" and client.store["pairs"] == "EURUSD,GBPJPY"
    assert client.store["stories"] == "D,M"
    r = client.post("/api/settings", json={"auto_trade": "yolo"}, headers=hdr(make_init_data()))
    assert r.status_code == 422


def test_approve_needs_confirm_mode(client):
    client.store["auto_trade"] = "auto"
    assert client.post("/api/entries/5/approve", headers=hdr(make_init_data())).status_code == 409


def test_schema_split():
    stmts = webapp.db.split_sql((Path(webapp.__file__).parent / "schema.sql").read_text())
    assert len(stmts) == 6 and all(s.upper().startswith("CREATE TABLE IF NOT EXISTS") for s in stmts[:5])
    assert stmts[5].upper().startswith("INSERT IGNORE INTO SETTINGS")  # same defaults as db/schema.sql
