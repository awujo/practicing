"""SLK Telegram Mini App (FastAPI). Every /api call must carry Telegram WebApp initData."""
import hashlib
import hmac
import json
import logging
import os
import time
import threading
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import parse_qsl

from fastapi import Body, Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool

import db  # also puts the repo root on sys.path
from slk import settings as S  # stdlib only (no pandas)
from slk import standing  # stdlib only
from slk import tenancy
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
    if auth_date <= 0 or now - auth_date > max_age or auth_date > now + 60:
        raise ValueError("expired")
    try:
        user = json.loads(data.get("user", "{}"))
    except json.JSONDecodeError:
        raise ValueError("bad user") from None
    if allowed_user_id != "*" and str(user.get("id")) != str(allowed_user_id).strip():
        raise ValueError("user not allowed")
    if not isinstance(user.get("id"), int) or isinstance(user["id"], bool) or user["id"] <= 0:
        raise ValueError("invalid user id")
    return user


async def require_user(request: Request) -> dict:
    init_data = request.headers.get("X-Telegram-Init-Data", "")
    if not init_data:
        auth = request.headers.get("Authorization", "")
        if auth.lower().startswith("tma "):
            init_data = auth[4:]
    try:
        user = validate_init_data(init_data, os.environ.get("TELEGRAM_BOT_TOKEN", ""), "*")
    except ValueError as e:
        raise HTTPException(status_code=403, detail=f"forbidden: {e}") from None
    if os.environ.get("DATABASE_URL"):
        # Registration is global; all subsequent DB operations run inside the authenticated scope.
        with tenancy.scope(None):
            await run_in_threadpool(_db, db.execute, "INSERT IGNORE INTO app_users (user_id) VALUES (%s)", (user["id"],))
    with tenancy.scope(user["id"]):
        yield user



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


@app.get("/version")
def version():
    return {"commit": os.environ.get("RENDER_GIT_COMMIT", "unknown"),
            "settings_validation": "flip-age-bounds-v1", "multiuser": True, "news": True}


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


@app.get("/api/news")
def news_calendar(user=Depends(require_user)):
    from slk import news
    from datetime import datetime, timezone
    from zoneinfo import ZoneInfo
    vals=S.load(_db(db.get_settings))
    data=_db(news.calendar,db)
    tz=ZoneInfo(vals["display_tz"])
    today=datetime.now(timezone.utc).astimezone(tz).date()
    data["events"]=[e for e in news.selected(data["events"],vals)
                    if datetime.fromisoformat(e["time"]).astimezone(tz).date()==today]
    data["timezone"]=vals["display_tz"]
    data["alerts_enabled"]=vals["news_enabled"]
    return data


@app.get("/api/bias")
def bias(pair: str = "", story: str = "", status: str = "active", limit: int = 200, user=Depends(require_user)):
    vals = S.load(_db(db.get_settings))
    pairs = vals["pairs"] or S.PAIRS
    where, args = ["pair IN (" + ",".join(["%s"] * len(pairs)) + ")"], list(pairs)
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


def eligible_biases(rows, vals):
    """Newest confirmed story per market/timeframe; never resurrect an older ended story."""
    watched = set(vals["pairs"] or S.PAIRS)
    seen, out = set(), []
    for row in rows:
        key = (row["pair"], row["story"])
        if key in seen:
            continue
        seen.add(key)
        if (row["pair"] in watched and row["story"] in vals["stories"]
                and row["pair"] not in vals["avoid_pairs"]
                and row["status"] == "CONFIRMED" and not row.get("no_trade")):
            out.append(row)
    return out


def send_private_digest(chat_id, text):
    import urllib.request
    req = urllib.request.Request(
        "https://api.telegram.org/bot" + os.environ["TELEGRAM_BOT_TOKEN"] + "/sendMessage",
        data=json.dumps({"chat_id": chat_id, "text": text}).encode(),
        headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=20) as response:
            if not json.load(response).get("ok"):
                raise ValueError("Telegram refused message")
    except Exception:
        raise HTTPException(502, "Telegram delivery failed. Please try again.") from None


@app.post("/api/bias/send-eligible")
def send_eligible(user=Depends(require_user)):
    from datetime import datetime, timezone
    vals = S.load(_db(db.get_settings))
    completed = _db(db.query, "SELECT finished_at FROM runs WHERE job = 'live' AND ok = 1 "
                    "AND finished_at IS NOT NULL ORDER BY finished_at DESC LIMIT 1")
    if not completed:
        raise HTTPException(409, "No completed live scan yet.")
    stamp = completed[0]["finished_at"]
    if isinstance(stamp, str):
        stamp = datetime.fromisoformat(stamp)
    stamp = stamp.replace(tzinfo=timezone.utc) if stamp.tzinfo is None else stamp
    if (datetime.now(timezone.utc) - stamp).total_seconds() > 7200:
        raise HTTPException(409, "Latest completed scan is over two hours old. Wait for a fresh scan.")
    rows = _db(db.query, "SELECT * FROM bias WHERE confirm_time IS NOT NULL "
               "ORDER BY confirm_time DESC, id DESC")
    rows = eligible_biases(rows, vals)
    lines = ["Eligible confirmed biases", f"Scan: {stamp:%Y-%m-%d %H:%M} UTC",
             "Based on your saved pairs and story timeframes. Bias only; wait for an entry signal."]
    for row in rows:
        lines.append(f"{row['side']} {row['pair']} · {row['story']} · Target {row.get('target') or '—'}")
    if not rows:
        lines.append("No eligible confirmed biases in this scan.")
    # Keep each Telegram message below its limit, including for large watchlists.
    chunks, text = [], ""
    for line in lines:
        if len(text) + len(line) + 1 > 3500:
            chunks.append(text)
            text = ""
        text += line + "\n"
    chunks.append(text)
    cooldown = int(time.time())
    _db(db.execute, "INSERT IGNORE INTO settings (k,v) VALUES (%s,%s)", ("digest_last_sent", "0"))
    claimed = _db(db.execute, "UPDATE settings SET v=%s WHERE k=%s AND CAST(v AS UNSIGNED) < %s",
                  (str(cooldown), "digest_last_sent", cooldown - 30))
    if not claimed:
        raise HTTPException(429, "Please wait 30 seconds before requesting another digest.")
    for text in chunks:
        send_private_digest(user["id"], text)
    return {"ok": True, "count": len(rows), "scan_at": stamp.isoformat()}


@app.get("/api/bias/state")
def bias_state(user=Depends(require_user)):
    """Standing bias per pair and watched story TF (slk.standing): the direction stays after a target is reached and
    ends only on a confirmed opposite story or an invalidation. Strongest first: M, W, D."""
    vals = S.load(_db(db.get_settings))
    watched = [x for x in vals["stories"] if x in ("D", "W", "M")] or ["D", "W", "M"]
    rows = _db(db.query, "SELECT * FROM bias WHERE confirm_time IS NOT NULL AND story IN ("
               + ", ".join(["%s"] * len(watched)) + ")", watched)
    by_pair, trends = {}, {}
    for r in rows:
        if r["pair"] in (vals["pairs"] or S.PAIRS):
            by_pair.setdefault(r["pair"], []).append(r)
    try:  # structure trend per pair/TF from the last live run (table added 2026-10-15)
        for t in _db(db.query, "SELECT pair, story, trend FROM tf_state", ()):
            trends[(t["pair"], t["story"])] = t["trend"]
    except HTTPException:
        pass
    out = []
    for pair in sorted(by_pair):
        for st in [x for x in ("M", "W", "D") if x in watched]:
            b = standing.standing(by_pair[pair], st, trends.get((pair, st)), vals["close_at_target"])
            if b["state"] == "none":
                continue
            last = b["last"] or {}
            out.append({"pair": pair, "story": st, "side": b["side"], "bias": standing.WORD.get(b["side"], "NONE"),
                        "since": b["since"], "stories": b["stories"], "state": b["state"],
                        "chain": last.get("chain"), "last_status": last.get("status"),
                        "last_target": last.get("target"), "last_level": last.get("level"),
                        "last_confirm": last.get("confirm_time"),
                        "pullback": (b.get("pullback") or {}).get("side")})
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
    schema = S.schema_json()
    catalogue = Path(__file__).resolve().parents[1] / "data" / "broker_symbols.json"
    if catalogue.exists():
        data = json.loads(catalogue.read_text())
        choices = sorted({r["key"] for r in data["symbols"] if 3 <= len(r["key"]) <= 12})
        for field in schema["settings"]:
            if field["name"] == "pairs":
                field["choices"] = choices
                field["help"] = ("IC Markets account symbols. Select markets you want scanned. "
                                 + ("Empty = default 28 FX pairs." if user["id"] == tenancy.owner_id() else "Up to 30 markets. Empty restores your three starter pairs."))
        schema["broker_catalogue"] = {"updated_at": data["updated_at"], "count": len(choices)}
    if user["id"] != tenancy.owner_id():
        for field in schema["settings"]:
            if field["name"] == "auto_trade":
                field["choices"] = ["off"]
                field["help"] = "Alerts and paper tracking only. Broker trading is unavailable for this account."
    return schema


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
    if user["id"] != tenancy.owner_id():
        if changes.get("auto_trade", "off") != "off":
            raise HTTPException(422, "Broker trading is unavailable for this account; leave auto_trade off.")
        if "pairs" in changes and len(changes["pairs"].split(",")) > 30:
            raise HTTPException(422, "Select up to 30 markets per watchlist.")
        # Empty = no surprise expansion to the legacy owner's 28-market watchlist.
        if "pairs" in changes and not changes["pairs"]:
            changes["pairs"] = tenancy.STARTER["pairs"]
    for k, v in changes.items():
        _db(db.set_setting, k, v)
    return get_settings(user)


@app.post("/api/entries/{entry_id}/approve")
def approve(entry_id: int, user=Depends(require_user)):
    if user["id"] != tenancy.owner_id():
        raise HTTPException(403, "Broker order approval is available only to the account owner.")
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


_news_lock = threading.Lock()


@app.api_route("/cron/news", methods=["GET", "POST"])
def news_tick(request: Request):
    secret=os.environ.get("CRON_SECRET", "")
    got=request.headers.get("X-Cron-Secret") or request.query_params.get("key") or ""
    if not secret or not hmac.compare_digest(got.encode(),secret.encode()):
        raise HTTPException(403,"forbidden")
    # Run in-process on Render; no need to start a GitHub job for each external tick.
    from slk import news
    if not _news_lock.acquire(blocking=False):
        return {"ok":True,"skipped":"news tick already running"}
    try:
        return _db(news.tick)
    finally:
        _news_lock.release()
