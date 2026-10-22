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


def test_bias_shows_only_watched_stories(client):
    client.store["stories"] = "D,W"
    client.get("/api/bias", headers=hdr(make_init_data()))
    sql, args = [c for c in client.calls if "FROM bias" in c[0]][-1]
    assert "story IN (%s, %s)" in sql and args[:2] == ["D", "W"]
    client.get("/api/bias?story=M", headers=hdr(make_init_data()))
    sql, args = [c for c in client.calls if "FROM bias" in c[0]][-1]
    assert "story = %s" in sql and "story IN" not in sql and args[0] == "M"


def test_bias_state_keeps_bias_after_target(client, monkeypatch):
    rows = [{"pair": "EURCAD", "story": "D", "side": "BUY", "status": "TARGET_HIT", "tap_time": "2026-10-05 21:00:00",
             "confirm_time": "2026-10-06 21:00:00", "chain": "W1\u2192D1\u2192H4", "target": 1.627, "level": 1.587},
            {"pair": "EURGBP", "story": "D", "side": "SELL", "status": "INVALIDATED", "tap_time": "2026-10-05 21:00:00",
             "confirm_time": "2026-10-06 21:00:00"}]
    monkeypatch.setattr(webapp.db, "query", lambda sql, args=None: [] if "tf_state" in sql else rows)
    out = client.get("/api/bias/state", headers=hdr(make_init_data())).json()
    # default close_at_target (owner 2026-10-20): the story is done at its target, the next bias is a new story
    assert [(b["pair"], b["bias"], b["state"]) for b in out] == [
        ("EURCAD", "NONE", "target reached: waiting for the pullback into internal range and a new story"),
        ("EURGBP", "NONE", "invalidated")]
    monkeypatch.setattr(webapp.db, "get_settings", lambda: {"close_at_target": "off"})
    out = client.get("/api/bias/state", headers=hdr(make_init_data())).json()
    assert out[0]["bias"] == "BULLISH" and out[0]["state"] == "target reached, bias continues"


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


def test_kill_switch_blocks_approval(client):
    client.store["kill_switch"] = "on"
    r = client.post("/api/entries/5/approve", headers=hdr(make_init_data()))
    assert r.status_code == 409 and r.json()["detail"] == "kill switch is on"
    assert client.calls == []


def test_save_whole_settings_form_and_reload(client):
    headers = hdr(make_init_data())
    body = client.get("/api/settings", headers=headers).json()
    schema = client.get("/api/settings/schema", headers=headers).json()["settings"]
    # The browser sends every field, even when only one alert checkbox changed.
    for enabled in ("off", "on"):
        for field in schema:
            if field["group"] == "Alerts":
                body[field["name"]] = enabled if field["type"] == "bool" else field["default"]
        r = client.post("/api/settings", json=body, headers=headers)
        assert r.status_code == 200, r.text
        assert r.json() == body
        assert client.get("/api/settings", headers=headers).json() == body


@pytest.mark.parametrize("value", ["-1", "10001", "inf", "-inf", "NaN", "2.5"])
def test_invalid_flip_age_returns_validation_error(client, value):
    r = client.post("/api/settings", json={"flip_max_age": value}, headers=hdr(make_init_data()))
    assert r.status_code == 422


def test_every_setting_roundtrips(client):
    headers = hdr(make_init_data())
    for field in webapp.S.SCHEMA:
        values = [field["default"]]
        if field["type"] == "bool":
            values = ["off", "on"]
        elif field["type"] == "choice":
            values = field["choices"]
        elif field["type"] in ("int", "float"):
            values += [str(field["min"]), str(field["max"])]
        for value in values:
            r = client.post("/api/settings", json={field["name"]: value}, headers=headers)
            assert r.status_code == 200, (field["name"], value, r.text)
            assert r.json()[field["name"]] == webapp.S.clean(field["name"], value)


def test_schema_split():
    stmts = webapp.db.split_sql((Path(webapp.__file__).parent / "schema.sql").read_text())
    assert len(stmts) == 11 and all(s.upper().startswith("CREATE TABLE IF NOT EXISTS") for s in stmts[:6])
    assert stmts[6].upper().startswith("INSERT IGNORE INTO SETTINGS")  # same defaults as db/schema.sql
    # entries.model for tables created before it existed: guarded ALTER via a prepared statement
    assert stmts[7].startswith("SET @slk_add_model") and "ADD COLUMN model" in stmts[7]
    assert [s.split()[0] for s in stmts[8:]] == ["PREPARE", "EXECUTE", "DEALLOCATE"]
    assert "model       VARCHAR(16)  NOT NULL DEFAULT 'continuation'" in stmts[1] + stmts[2]


def test_settings_schema_endpoint(client):
    r = client.get("/api/settings/schema", headers=hdr(make_init_data()))
    assert r.status_code == 200
    j = r.json()
    assert j["groups"] == ["Markets", "Bias rules", "Entry rules", "Risk & trading", "Alerts"]
    by = {s["name"]: s for s in j["settings"]}
    assert "confirm_break" not in by  # no setting may change what confirms the bias (external break only)
    assert "Internal break = continuation entries only" in by["continuation_entries"]["help"]
    if "broker_catalogue" in j:
        assert j["broker_catalogue"]["count"] == len(by["pairs"]["choices"])
        assert {"USTEC", "US500", "UK100"} <= set(by["pairs"]["choices"])
    assert by["max_wait"]["min"] == 1 and by["max_wait"]["max"] == 20 and set(webapp.S.PAIRS) <= set(by["pairs"]["choices"])
    assert client.get("/api/settings/schema", headers=hdr(make_init_data(tamper=True))).status_code == 403


def test_settings_get_defaults_and_post_validation(client):
    client.store["max_wait"] = "junk"
    r = client.get("/api/settings", headers=hdr(make_init_data())).json()
    assert r["max_wait"] == "5" and "confirm_break" not in r and r["alert_entry"] == "on"
    assert r["auto_trade"] == "confirm" and r["entry_tfs"] == "D=H4,H2;W=D,H4;M=W,D"  # owner 2026-10-14: no H1
    body = {"max_wait": 8, "trend_filter": False, "risk_pct": 1.5,
            "entry_tfs": "D=H1", "continuation_entries": "off", "daily_summary": "off"}
    r = client.post("/api/settings", json=body, headers=hdr(make_init_data()))
    assert r.status_code == 200
    s = client.store
    assert "confirm_break" not in s and s["max_wait"] == "8" and s["trend_filter"] == "off"
    assert s["risk_pct"] == "1.5" and s["entry_tfs"] == "D=H1;W=D,H4;M=W,D" and s["continuation_entries"] == "off"
    for bad in ({"max_wait": 99}, {"risk_pct": 3}, {"confirm_break": "internal"}, {"bogus": 1},
                {"tap_tol_pips": "x"}):
        r = client.post("/api/settings", json=bad, headers=hdr(make_init_data()))
        assert r.status_code == 422, bad
    assert s["max_wait"] == "8"


# ---------------------------------------------------------------- /terms (Telegram webhook)
def upd(text, chat=OWNER):
    return {"update_id": 1, "message": {"message_id": 5, "chat": {"id": chat, "type": "private"}, "text": text}}


def test_terms_webhook_owner_only(client, monkeypatch):
    url, ok = "/telegram/webhook", {"X-Telegram-Bot-Api-Secret-Token": "s3cret"}
    monkeypatch.delenv("TELEGRAM_WEBHOOK_SECRET", raising=False)
    assert client.post(url, json=upd("/terms"), headers=ok).status_code == 403   # no secret set: webhook off
    monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET", "s3cret")
    assert client.post(url, json=upd("/terms")).status_code == 403                # header missing
    assert client.post(url, json=upd("/terms"), headers={"X-Telegram-Bot-Api-Secret-Token": "x"}).status_code == 403
    r = client.post(url, json=upd("/terms@SlkBot"), headers=ok).json()
    assert r["method"] == "sendMessage" and r["chat_id"] == OWNER
    for w in ("Point B", "External break", "Next Day Rule", "A-shape", "V-shape", "open-close", "TAPPED",
              "CONFIRMED", "TARGET_HIT", "INVALIDATED", "ENDED_FLIP", "NO_TRADE"):
        assert w in r["text"], w
    assert client.post(url, json=upd("/terms", chat=123), headers=ok).json() == {"ok": True}   # not the owner
    assert client.post(url, json=upd("hello"), headers=ok).json() == {"ok": True}
    assert client.post(url, content=b"junk", headers=ok).json() == {"ok": True}
    monkeypatch.delenv("TELEGRAM_CHAT_ID")                                          # default owner chat id
    assert webapp.bot_reply(upd("/terms", chat=1410229777))["chat_id"] == 1410229777
    assert webapp.bot_reply(upd("/terms")) is None


def test_new_settings_in_schema(client):
    s = {x["name"]: x for x in client.get("/api/settings/schema", headers=hdr(make_init_data())).json()["settings"]}
    assert s["next_day_rule"]["choices"] == ["flag", "require"] and s["next_day_rule"]["default"] == "require"
    assert s["trend_mode"]["choices"] == ["leg", "protected"] and s["trend_mode"]["default"] == "leg"
    assert s["display_tz"]["type"] == "tz" and s["display_tz"]["default"] == "Africa/Lagos"
    assert s["early_breakout_alert"]["default"] == "off"
    assert s["entry_alignment"]["choices"] == ["d_h4", "w_d_h4", "off"] and s["entry_alignment"]["default"] == "d_h4"
    r = client.post("/api/settings", json={"display_tz": "Mars/Base"}, headers=hdr(make_init_data()))
    assert r.status_code == 422 and "display_tz" in r.text
    r = client.post("/api/settings", json={"display_tz": "Europe/London", "next_day_rule": "flag"},
                    headers=hdr(make_init_data()))
    assert r.status_code == 200 and r.json()["display_tz"] == "Europe/London" and r.json()["next_day_rule"] == "flag"


def test_cron_tick(client, monkeypatch):
    """/cron/tick (hourly timer -> live workflow): refused without the secret or token; with both it dispatches
    live.yml once (tick=1) and ignores repeats within 10 minutes; the token never appears in the answer."""
    assert client.get("/cron/tick?key=x").status_code == 403  # nothing configured: off
    monkeypatch.setenv("CRON_SECRET", "s3cret")
    monkeypatch.setenv("GH_DISPATCH_TOKEN", "ghtoken")
    sent = []
    monkeypatch.setattr(webapp, "dispatch_live", lambda tok: sent.append(tok) or 204)
    monkeypatch.setitem(webapp._last_tick, "t", 0.0)
    assert client.get("/cron/tick?key=wrong").status_code == 403 and not sent
    r = client.get("/cron/tick?key=s3cret")
    assert r.status_code == 200 and r.json()["started"] is True and sent == ["ghtoken"]
    r = client.post("/cron/tick", headers={"X-Cron-Secret": "s3cret"})
    assert r.json()["started"] is False and len(sent) == 1 and "ghtoken" not in r.text


def test_dispatch_live_request():
    seen = {}

    class R:
        status = 204

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def opener(req, timeout):
        seen.update(url=req.full_url, body=json.loads(req.data), auth=req.headers["Authorization"])
        return R()
    assert webapp.dispatch_live("tok", opener) == 204
    assert seen["url"].endswith("/repos/awujo/practicing/actions/workflows/live.yml/dispatches")
    assert seen["body"] == {"ref": "claude-kevin-king", "inputs": {"tick": "1"}} and seen["auth"] == "Bearer tok"


def test_eligible_does_not_resurrect_old_or_blocked():
    vals = webapp.S.load({"pairs": "EURUSD,GBPUSD", "stories": "D"})
    rows = [dict(pair="EURUSD", story="D", status="TARGET_HIT"),
            dict(pair="EURUSD", story="D", status="CONFIRMED"),
            dict(pair="GBPUSD", story="D", status="CONFIRMED", no_trade=1),
            dict(pair="USDJPY", story="D", status="CONFIRMED")]
    assert webapp.eligible_biases(rows, vals) == []


def test_digest_private_and_filtered(client, monkeypatch):
    from datetime import datetime, timezone
    sent = []
    monkeypatch.setattr(webapp, "send_private_digest", lambda uid, text: sent.append((uid, text)))
    monkeypatch.setattr(webapp.db, "query", lambda sql, args=None:
        [{"finished_at": datetime.now(timezone.utc)}] if "FROM runs" in sql else
        [dict(pair="EURUSD", story="D", side="SELL", status="CONFIRMED", target=1.1)])
    r = client.post("/api/bias/send-eligible", headers=hdr(make_init_data()))
    assert r.status_code == 200 and r.json()["count"] == 1
    assert sent[0][0] == OWNER and "EURUSD" in sent[0][1]
    assert client.post("/api/bias/send-eligible").status_code == 403


def test_digest_refuses_stale_scan(client, monkeypatch):
    from datetime import datetime, timezone, timedelta
    monkeypatch.setattr(webapp.db, "query", lambda *a:
        [{"finished_at": datetime.now(timezone.utc) - timedelta(hours=3)}])
    monkeypatch.setattr(webapp, "send_private_digest", lambda *a: pytest.fail("must not send stale digest"))
    assert client.post("/api/bias/send-eligible", headers=hdr(make_init_data())).status_code == 409
