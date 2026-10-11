#!/usr/bin/env python3
"""Stage 1 skeleton runner for the Kevin King SLK bot.

What it does (and nothing more):
  1. connects to Aiven MySQL over SSL, applies stage1/schema.sql (idempotent),
  2. records start-delay + minutes-used in the `runs` table,
  3. sends ONE Telegram message with the results.

Long-running mode (--minutes N): loops every 60s doing a cheap DB heartbeat so we
can measure real GitHub Actions wall-clock behaviour. The next run is handed over
by an external timer firing `workflow_dispatch` (cron alone drifts 4-8h).

Secrets come only from env vars (GitHub Secrets). Never printed.
"""
import argparse
import json
import os
import re
import sys
import time
import urllib.request
from datetime import datetime, timezone

import pymysql


def env(name, required=True):
    v = os.environ.get(name, "").strip()
    if required and not v:
        sys.exit(f"missing env var {name}")
    return v


def utcnow():
    return datetime.now(timezone.utc)


def get_conn():
    url = env("DB_URL")  # mysql://user:pass@host:port/defaultdb?ssl-mode=REQUIRED
    m = re.match(r"mysql://([^:]+):([^@]*)@([^:]+):(\d+)/([^?]+)", url)
    if not m:
        sys.exit("DB_URL must look like mysql://user:pass@host:port/db?ssl-mode=REQUIRED")
    user, pw, host, port, db = m.groups()
    return pymysql.connect(
        host=host, port=int(port), user=user, password=pw, database=db,
        ssl={"ssl": {}}, charset="utf8mb4", autocommit=True, connect_timeout=15,
    )


def apply_schema(cur, path):
    with open(path, encoding="utf-8") as f:
        sql = f.read()
    lines = [ln for ln in sql.splitlines() if not ln.strip().startswith("--")]
    stmts = [s.strip() for s in "\n".join(lines).split(";") if s.strip()]
    applied = 0
    for s in stmts:
        cur.execute(s)
        applied += 1
    return applied


def resolve_chat_id(token, configured):
    """If TG_CHAT_ID is unset/placeholder, discover it from getUpdates (first chat that
    messaged the bot). Owner only needs to DM the bot /start once."""
    if configured and configured.lower() not in ("", "auto", "0"):
        return configured
    try:
        with urllib.request.urlopen(
            f"https://api.telegram.org/bot{token}/getUpdates?timeout=5", timeout=15
        ) as r:
            data = json.loads(r.read())
        for up in data.get("result", []):
            msg = up.get("message") or up.get("edited_message") or up.get("my_chat_member") or {}
            cid = (msg.get("chat") or {}).get("id")
            if cid:
                print(f"TG_CHAT_ID auto-discovered: {cid}")
                return str(cid)
    except Exception as e:
        print(f"chat-id discovery failed: {type(e).__name__}", file=sys.stderr)
    return configured


def send_telegram(text):
    token = env("TG_BOT_TOKEN")
    chat = resolve_chat_id(token, env("TG_CHAT_ID", required=False))
    if not chat:
        print("no TG_CHAT_ID and none discovered (has owner sent /start to the bot?)", file=sys.stderr)
        return False
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data=json.dumps({"chat_id": chat, "text": text, "disable_web_page_preview": True}).encode(),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            body = json.loads(r.read())
        return bool(body.get("ok"))
    except Exception as e:  # never log the token
        print(f"telegram send failed: {type(e).__name__}", file=sys.stderr)
        return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--minutes", type=float, default=0.0, help="long-running heartbeat minutes (0 = single pass)")
    ap.add_argument("--planned", default="", help="ISO time the external timer dispatched this run")
    args = ap.parse_args()

    started = utcnow()
    planned = None
    if args.planned:
        planned = datetime.fromisoformat(args.planned.replace("Z", "+00:00"))
    delay = (started - planned).total_seconds() if planned else None

    conn = get_conn()
    cur = conn.cursor()
    schema_path = os.path.join(os.path.dirname(__file__) or ".", "schema.sql")
    if not os.path.exists(schema_path):  # workflow may inline the script without the repo file
        print(f"schema file not found at {schema_path}, skipping apply")
        applied = 0
    else:
        applied = apply_schema(cur, schema_path)
    cur.execute("SELECT COUNT(*) FROM information_schema.tables WHERE table_schema=DATABASE()")
    tables = cur.fetchone()[0]

    ticks = 0
    end = started.timestamp() + args.minutes * 60
    while True:
        ticks += 1
        cur.execute(
            "INSERT INTO runs (run_id, started_planned, started_actual, delay_seconds, minutes_used, ok, note) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s) "
            "ON DUPLICATE KEY UPDATE minutes_used=VALUES(minutes_used)",
            (env("GITHUB_RUN_ID", required=False) or f"local-{int(started.timestamp())}",
             planned.strftime("%Y-%m-%d %H:%M:%S.%f") if planned else None,
             started.strftime("%Y-%m-%d %H:%M:%S.%f"),
             delay, round((utcnow() - started).total_seconds() / 60, 2), 1,
             f"stage1 skeleton; {applied} stmts; tick {ticks}"),
        )
        if utcnow().timestamp() >= end:
            break
        time.sleep(max(1, min(60, end - utcnow().timestamp())))

    minutes_used = round((utcnow() - started).total_seconds() / 60, 2)
    delay_txt = f"{delay/60:.1f} min late" if delay is not None else "n/a (no --planned)"
    msg = (
        "SLK bot | Stage 1 OK\n"
        f"DB: connected, schema applied ({applied} stmts, {tables} tables)\n"
        f"Run: {env('GITHUB_RUN_ID', required=False) or 'local'} | start delay: {delay_txt}\n"
        f"Heartbeat: {ticks} tick(s), {minutes_used} min used\n"
        "Next: owner confirms defaults -> Stage 2 candles."
    )
    ok = send_telegram(msg)
    print(msg)  # msg contains no secrets; TG_BOT_TOKEN/TG_CHAT_ID never interpolated
    print(f"telegram delivered: {ok}")
    conn.close()


if __name__ == "__main__":
    main()
