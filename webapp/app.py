"""SLK Telegram Mini App (FastAPI). Every /api call must carry Telegram WebApp initData."""
import hashlib
import hmac
import json
import logging
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import parse_qsl

from fastapi import Body, Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

import db  # also puts the repo root on sys.path
from slk import settings as S  # stdlib only (no pandas)

log = logging.getLogger("slk.webapp")
STATIC = Path(__file__).resolve().parent / "static"
MAX_AGE = 24 * 3600

BIAS_STATUSES = {"TAPPED", "CONFIRMED", "TARGET_HIT", "INVALIDATED", "CANCELLED"}
ACTIVE_BIAS = ("TAPPED", "CONFIRMED")
PUBLIC_SETTINGS = tuple(s["name"] for s in S.SCHEMA)
DEFAULTS = dict(S.DEFAULTS)


# ---------------------------------------------------------------- auth
def validate_init_data(init_data: str, bot_token: str, allowed_user_id: str, max_age: int = MAX_AGE, now=None) -> dict:
    """Return the Telegram user dict, or raise ValueError. Algorithm from core.telegram.org/bots/webapps."""
    if not init_data or not bot_token or not allowed_user_id:
        raise ValueError("missing initData or server config")
    pairs = parse_qsl(init_data, keep_blank_values=True, strict_parsing=False)
    data = dict(pairs)
    received = data.pop("hash", None)
    if not received:
        raise ValueError("no hash")
    check = "\n".join(f"{k}={v}" for k, v in sorted(data.items()))
    secret = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    expected = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, received):
        raise ValueError("bad hash")
    try:
        auth_date = int(data.get("auth_date", "0"))
    except ValueError:
        raise ValueError("bad auth_date") from None
    now = time.time() if now is None else now
    if auth_date <= 0 or now - auth_date > max_age:
        raise ValueError("expired")
    try:
        user = json.loads(data.get("user", "{}"))
    except json.JSONDecodeError:
        raise ValueError("bad user") from None
    if str(user.get("id")) != str(allowed_user_id).strip():
        raise ValueError("user not allowed")
    return user


def require_user(request: Request) -> dict:
    init_data = request.headers.get("X-Telegram-Init-Data", "")
    if not init_data:
        auth = request.headers.get("Authorization", "")
        if auth.lower().startswith("tma "):
            init_data = auth[4:]
    try:
        return validate_init_data(
            init_data, os.environ.get("TELEGRAM_BOT_TOKEN", ""), os.environ.get("TELEGRAM_CHAT_ID", "")
        )
    except ValueError as e:
        raise HTTPException(status_code=403, detail=f"forbidden: {e}") from None


# ---------------------------------------------------------------- app
def _init_schema():
    if os.environ.get("SKIP_SCHEMA") == "1" or not os.environ.get("DATABASE_URL"):
        return
    try:
        db.ensure_schema()
        log.info("schema ok (%s)", db.schema_path())
    except Exception as e:  # noqa: BLE001 - keep serving
        log.error("schema init failed: %s", type(e).__name__)


@asynccontextmanager
async def lifespan(_app):
    _init_schema()
    yield


app = FastAPI(title="SLK Mini App", docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)


@app.get("/healthz")
def healthz():
    return {"ok": True}


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html", headers={"Cache-Control": "no-store"})


app.mount("/static", StaticFiles(directory=STATIC), name="static")


def _db(fn, *a, **kw):
    try:
        return fn(*a, **kw)
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        log.error("db error: %s", type(e).__name__)
        raise HTTPException(status_code=503, detail="database unavailable") from None


def _clamp(limit: int, hi: int = 500) -> int:
    return max(1, min(int(limit), hi))


@app.get("/api/me")
def me(user: dict = Depends(require_user)):
    return {"id": user.get("id"), "first_name": user.get("first_name"), "username": user.get("username")}


@app.get("/api/bias")
def bias(pair: str = "", story: str = "", status: str = "active", limit: int = 200, user=Depends(require_user)):
    where, args = [], []
    if pair:
        where.append("pair = %s")
        args.append(pair.upper())
    if story:
        where.append("story = %s")
        args.append(story.upper())
    if status == "active":
        where.append("status IN (%s, %s)")
        args += list(ACTIVE_BIAS)
    elif status.upper() in BIAS_STATUSES:
        where.append("status = %s")
        args.append(status.upper())
    sql = (
        "SELECT id, pair, story, side, status, level_kind, level, point_b, target, invalidation, "
        "tap_time, confirm_time, updated_at FROM bias"
        + (" WHERE " + " AND ".join(where) if where else "")
        + " ORDER BY COALESCE(confirm_time, tap_time) DESC LIMIT %s"
    )
    return _db(db.query, sql, args + [_clamp(limit)])


@app.get("/api/entries")
def entries(status: str = "", limit: int = 100, user=Depends(require_user)):
    sql = "SELECT * FROM entries"
    args = []
    if status:
        sql += " WHERE status = %s"
        args.append(status.upper())
    sql += " ORDER BY created_at DESC LIMIT %s"
    return _db(db.query, sql, args + [_clamp(limit)])


@app.get("/api/orders")
def orders(limit: int = 100, user=Depends(require_user)):
    return _db(db.query, "SELECT * FROM orders ORDER BY id DESC LIMIT %s", [_clamp(limit)])


@app.get("/api/runs")
def runs(limit: int = 30, user=Depends(require_user)):
    rows = _db(db.query, "SELECT * FROM runs ORDER BY id DESC LIMIT %s", [_clamp(limit, 200)])
    for r in rows:
        p, s, f = r.get("planned_at"), r.get("started_at"), r.get("finished_at")
        r["delay_s"] = (s - p).total_seconds() if p and s and hasattr(s, "__sub__") else None
        r["duration_s"] = (f - s).total_seconds() if s and f and hasattr(f, "__sub__") else None
    return rows


@app.get("/api/settings/schema")
def settings_schema(user=Depends(require_user)):
    return S.schema_json()


@app.get("/api/settings")
def get_settings(user=Depends(require_user)):
    return S.as_strings(_db(db.get_settings))


def clean_settings(body) -> dict:
    try:
        return S.clean_all(body)
    except ValueError as e:
        raise HTTPException(422, str(e)) from None


@app.post("/api/settings")
def post_settings(body: dict = Body(...), user=Depends(require_user)):
    changes = clean_settings(body)
    for k, v in changes.items():
        _db(db.set_setting, k, v)
    return get_settings(user)


@app.post("/api/entries/{entry_id}/approve")
def approve(entry_id: int, user=Depends(require_user)):
    st = S.load(_db(db.get_settings))  # invalid stored values -> defaults (off)
    if st["auto_trade"] != "confirm":
        raise HTTPException(409, "auto_trade is not 'confirm'")
    if st["kill_switch"] == "on":
        raise HTTPException(409, "kill switch is on")
    n = _db(db.execute, "UPDATE entries SET status = 'APPROVED' WHERE id = %s AND status = 'PENDING'", (entry_id,))
    if not n:
        raise HTTPException(409, "entry not found or not PENDING")
    return {"id": entry_id, "status": "APPROVED"}
