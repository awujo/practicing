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
from slk import standing  # stdlib only
from slk import terms as T  # stdlib only

log = logging.getLogger("slk.webapp")
STATIC = Path(__file__).resolve().parent / "static"
MAX_AGE = 24 * 3600

BIAS_STATUSES = {"TAPPED", "CONFIRMED", "TARGET_HIT", "INVALIDATED", "ENDED_FLIP", "CANCELLED"}
ACTIVE_BIAS = ("TAPPED", "CONFIRMED")
PUBLIC_SETTINGS = tuple(s["name"] for s in S.SCHEMA)
DEFAULTS = dict(S.DEFAULTS)
OWNER_CHAT_ID = "1410229777"  # default owner chat (as the workflows); TELEGRAM_CHAT_ID wins


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
    else:  # only the story timeframes the owner watches (Settings > Markets > Stories); rows of a story turned off
        # stay in the table but are not shown (owner 2026-10-15: "I removed M ... still seeing M bias")
        watched = [x for x in S.load(_db(db.get_settings))["stories"] if x in ("D", "W", "M")] or ["D", "W", "M"]
        where.append(f"story IN ({', '.join(['%s'] * len(watched))})")
        args += watched
    if status == "active":
        where.append("status IN (%s, %s)")
        args += list(ACTIVE_BIAS)
    elif status.upper() in BIAS_STATUSES:
        where.append("status = %s")
        args.append(status.upper())
    sql = (
        "SELECT * FROM bias"  # * so it works before and after the no_trade columns are added
        + (" WHERE " + " AND ".join(where) if where else "")
        + " ORDER BY COALESCE(confirm_time, tap_time) DESC LIMIT %s"
    )
    return _db(db.query, sql, args + [_clamp(limit)])


@app.get("/api/bias/state")
def bias_state(user=Depends(require_user)):
    """Standing bias per pair and watched story TF (slk.standing): the direction stays after a target is reached and
    ends only on a confirmed opposite story or an invalidation. Strongest first: M, W, D."""
    watched = [x for x in S.load(_db(db.get_settings))["stories"] if x in ("D", "W", "M")] or ["D", "W", "M"]
    rows = _db(db.query, "SELECT * FROM bias WHERE confirm_time IS NOT NULL AND story IN ("
               + ", ".join(["%s"] * len(watched)) + ")", watched)
    by_pair = {}
    for r in rows:
        by_pair.setdefault(r["pair"], []).append(r)
    out = []
    for pair in sorted(by_pair):
        for st in [x for x in ("M", "W", "D") if x in watched]:
            b = standing.standing(by_pair[pair], st)
            if b["state"] == "none":
                continue
            last = b["last"] or {}
            out.append({"pair": pair, "story": st, "side": b["side"], "bias": standing.WORD.get(b["side"], "NONE"),
                        "since": b["since"], "stories": b["stories"], "state": b["state"],
                        "chain": last.get("chain"), "last_status": last.get("status"),
                        "last_target": last.get("target"), "last_level": last.get("level"),
                        "last_confirm": last.get("confirm_time")})
    return out


PAPER_CLOSED = ("TP1_HIT", "TP2_HIT", "SL_HIT", "EXPIRED")  # paper outcome known (slk.entry.paper_track)
PAPER_LABEL = "Paper results (signals)"


def _stats(rows):
    closed = [r for r in rows if r.get("status") in PAPER_CLOSED and r.get("result_r") is not None]
    wins = sum(r["status"] in ("TP1_HIT", "TP2_HIT") for r in closed)
    losses = sum(r["status"] == "SL_HIT" for r in closed)
    tp2 = [r for r in closed if r.get("result_r_tp2") is not None]
    return {"closed": len(closed), "wins": wins, "losses": losses,
            "expired": sum(r["status"] == "EXPIRED" for r in closed),
            "tp2_hits": sum(r["status"] == "TP2_HIT" for r in closed),
            "win_pct": round(100.0 * wins / len(closed), 1) if closed else None,
            "total_r": round(sum(float(r["result_r"]) for r in closed), 2),
            "total_r_tp2": round(sum(float(r["result_r_tp2"]) for r in tp2), 2), "closed_tp2": len(tp2)}


def entries_summary_of(rows):
    """Paper-result summary of entry rows: closed = TP1_HIT / TP2_HIT / SL_HIT / EXPIRED (TP1-variant R final),
    win = TP1 reached, loss = stop before TP1; total_r = TP1 variant, total_r_tp2 = TP2 variant (resolved rows);
    by_model continuation / qmr. Bot signals tracked on closed H1 candles, not broker trades (table orders)."""
    out = {"label": PAPER_LABEL, **_stats(rows), "open": sum(r.get("status") == "TRIGGERED" for r in rows),
           "by_model": {}}
    for m in ("continuation", "qmr"):
        out["by_model"][m] = _stats([r for r in rows if (r.get("model") or "continuation") == m])
    return out


@app.get("/api/entries/summary")
def entries_summary(user=Depends(require_user)):
    # SELECT * (not the result columns by name): works before the live job's db.migrate() added them
    rows = _db(db.query, "SELECT * FROM entries WHERE status IN (%s, %s, %s, %s, %s)", ["TRIGGERED", *PAPER_CLOSED])
    return entries_summary_of(rows)


@app.get("/api/entries")
def entries(status: str = "", limit: int = 100, user=Depends(require_user)):
    sql = "SELECT * FROM entries"
    args = []
    if status.lower() == "closed":
        sql += " WHERE status IN (%s, %s, %s, %s)"
        args += list(PAPER_CLOSED)
    elif status:
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


# ---------------------------------------------------------------- Telegram bot commands (webhook)
def owner_chat_id() -> str:
    return (os.environ.get("TELEGRAM_CHAT_ID", "").strip() or OWNER_CHAT_ID)


def bot_reply(update: dict):
    """Webhook reply for one Telegram update, or None. Only the owner's chat gets an answer; only /terms is known.
    The reply goes back in the webhook response body (Telegram runs it as a sendMessage call), so the web service
    needs no outbound request and never handles the bot token here."""
    msg = update.get("message") or update.get("edited_message") or {}
    chat = (msg.get("chat") or {}).get("id")
    if chat is None or str(chat) != owner_chat_id() or not T.is_terms(msg.get("text")):
        return None
    return {"method": "sendMessage", "chat_id": chat, "text": T.TERMS, "disable_web_page_preview": True}


@app.post("/telegram/webhook")
async def telegram_webhook(request: Request):
    """Telegram setWebhook target (HANDOVER.md: owner sets TELEGRAM_WEBHOOK_SECRET on Render and registers the URL
    with that secret_token). Requests without the matching X-Telegram-Bot-Api-Secret-Token header are refused;
    with no secret configured the endpoint is off."""
    secret = os.environ.get("TELEGRAM_WEBHOOK_SECRET", "")
    got = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
    if not secret or not hmac.compare_digest(got.encode(), secret.encode()):
        raise HTTPException(status_code=403, detail="forbidden")
    try:
        update = await request.json()
    except Exception:  # noqa: BLE001 - junk body: acknowledge so Telegram does not retry
        return {"ok": True}
    reply = bot_reply(update if isinstance(update, dict) else {})
    return reply or {"ok": True}


# ------------------------------------------------------------------ hourly tick (GitHub cron is unreliable)
# GitHub's own "hourly" schedule fired only every 4-5 hours (Oct 2026). An outside timer (cron-job.org, free) calls
# /cron/tick every hour with the CRON_SECRET; this server then starts the live workflow through the GitHub API with
# GH_DISPATCH_TOKEN (fine-grained token: this one repo, Actions read/write only). Both live on Render only.
GH_REPO = os.environ.get("GH_REPO", "awujo/practicing")
GH_WORKFLOW = os.environ.get("GH_WORKFLOW", "live.yml")
GH_REF = os.environ.get("GH_REF", "claude-kevin-king")
TICK_MIN_GAP = 10 * 60  # seconds: repeated ticks inside this window start nothing
_last_tick = {"t": 0.0}


def dispatch_live(token, opener=None):
    """POST workflow_dispatch for the live workflow (inputs tick=1 = obey FX hours like a scheduled run). Returns
    the HTTP status (204 = started)."""
    import urllib.request
    req = urllib.request.Request(
        f"https://api.github.com/repos/{GH_REPO}/actions/workflows/{GH_WORKFLOW}/dispatches",
        data=json.dumps({"ref": GH_REF, "inputs": {"tick": "1"}}).encode(), method="POST",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
                 "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "slk-miniapp"})
    with (opener or urllib.request.urlopen)(req, timeout=20) as r:
        return r.status


@app.api_route("/cron/tick", methods=["GET", "POST"])
def cron_tick(request: Request):
    """Start the live bias run. Needs ?key=<CRON_SECRET> (or header X-Cron-Secret); off when CRON_SECRET or
    GH_DISPATCH_TOKEN is not set."""
    secret, token = os.environ.get("CRON_SECRET", ""), os.environ.get("GH_DISPATCH_TOKEN", "")
    got = request.headers.get("X-Cron-Secret") or request.query_params.get("key") or ""
    if not secret or not token or not hmac.compare_digest(got.encode(), secret.encode()):
        raise HTTPException(status_code=403, detail="forbidden")
    now = time.time()
    if now - _last_tick["t"] < TICK_MIN_GAP:
        return {"ok": True, "started": False, "note": "already started in the last 10 minutes"}
    try:
        status = dispatch_live(token)
    except Exception as e:  # noqa: BLE001 - never echo the token
        log.warning("tick dispatch failed: %s", type(e).__name__)
        raise HTTPException(status_code=502, detail=f"GitHub dispatch failed ({type(e).__name__})")
    if status != 204:
        raise HTTPException(status_code=502, detail=f"GitHub answered {status}")
    _last_tick["t"] = now
    return {"ok": True, "started": True}
