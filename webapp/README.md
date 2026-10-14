# SLK Telegram Mini App (`webapp/`)

FastAPI + uvicorn backend, plain HTML/JS frontend (Telegram WebApp SDK, no build step).
Tabs: **Bias** (stories from `bias`, filter by pair / story / status), **Entries** (with a *Confirm trade*
button on `PENDING` entries when `auto_trade=confirm`: sets `entries.status='APPROVED'`, the trader job places it;
a **Paper results (signals)** card on top from `GET /api/entries/summary`: closed trades, wins (TP1 reached),
losses (stop before TP1), win%, total R at TP1 exit and holding for TP2, per model; each card shows the outcome tag
TP1_HIT / TP2_HIT / SL_HIT / EXPIRED with R, filled and closed times; filter `closed` or any status. These are the
bot's signals tracked by the live job on closed H1 candles, not broker trades),
**Orders**, **Settings** (kill switch, auto_trade, risk_pct, pairs, stories → table `settings`),
**Status** (last `runs`, planned vs started delay).

## Security
Every `/api/*` call sends Telegram `initData` (header `X-Telegram-Init-Data`). The server checks the HMAC-SHA256
signature (secret = `HMAC_SHA256("WebAppData", TELEGRAM_BOT_TOKEN)`), that `auth_date` is under 24 h old, and that
the Telegram user id equals `TELEGRAM_CHAT_ID`. Anything else gets 403. Opening the URL in a normal browser shows
nothing useful. `/healthz` is the only open endpoint. cTrader tokens in `settings` are never returned.

## Env vars (Render → service → Environment)
| Name | Value |
|---|---|
| `DATABASE_URL` | Aiven MySQL URL, `mysql://user:pass@host:port/db?ssl-mode=REQUIRED` |
| `TELEGRAM_BOT_TOKEN` | bot token from @BotFather |
| `TELEGRAM_CHAT_ID` | your own Telegram user id (the only user allowed) |
| `PYTHON_VERSION` | `3.12.7` (optional, set by render.yaml) |

On startup the app runs `db/schema.sql` (or `webapp/schema.sql` if that file is missing); all statements are
`CREATE TABLE IF NOT EXISTS`, so it is safe on every restart. Set `SKIP_SCHEMA=1` to turn this off.

## Deploy on Render

### Option A: reuse the existing service `slk-backtest-viewer`
1. Render dashboard → `slk-backtest-viewer` → **Settings**.
2. **Build & Deploy → Branch**: `claude-kevin-king`.
3. **Root Directory**: `webapp`.
4. **Runtime**: Python 3. **Build Command**: `pip install -r requirements.txt`.
   **Start Command**: `uvicorn app:app --host 0.0.0.0 --port $PORT`.
5. **Health Check Path**: `/healthz`.
6. **Environment**: add the three env vars above (and remove old ones you do not need).
7. **Manual Deploy → Deploy latest commit**. Check `https://<service>.onrender.com/healthz` → `{"ok":true}`.

If the old service is a *Static Site* (not a Web Service), it cannot run Python: use option B.

### Option B: new service from `render.yaml`
1. Render dashboard → **New → Blueprint** → pick this repo, branch `claude-kevin-king`.
2. Render reads `render.yaml` (repo root) and creates the web service `slk-miniapp`.
3. It asks for the `sync: false` env vars: fill in `DATABASE_URL`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`.
4. Wait for the deploy, then open `https://slk-miniapp.onrender.com/healthz`.

Free plan note: the service sleeps after ~15 min idle; the first open takes ~30–60 s.

## Connect it to the bot (@BotFather)
Use the HTTPS URL of the service root, e.g. `https://slk-miniapp.onrender.com/`.

- **Menu button** (simplest): @BotFather → `/mybots` → your bot → **Bot Settings → Menu Button →
  Configure menu button** → send the URL → send a title, e.g. `SLK`. The button appears next to the chat input.
- **Or a named Mini App**: @BotFather → `/newapp` → pick the bot → title, description, photo (640×360),
  optional GIF (`/empty`) → the URL → a short name. Link: `https://t.me/<bot_username>/<short_name>`.

Open the bot chat in Telegram and tap the menu button. The Mini App follows Telegram's light/dark theme.

## Bot command /terms (Telegram webhook)
The service also answers `/terms` (glossary of the alert words, `slk/terms.py`) through a Telegram webhook at
`POST /telegram/webhook`. Only the owner chat (`TELEGRAM_CHAT_ID`, default 1410229777) gets an answer; the reply is
returned in the webhook response, so no outgoing call is needed. Set it up once:
1. Render → the service → Environment → add `TELEGRAM_WEBHOOK_SECRET` = a random string (letters, digits, `_`, `-`;
   e.g. `python -c "import secrets; print(secrets.token_urlsafe(32))"`). Redeploy.
2. Register the webhook (run on your own computer; replace the token, URL and secret):
   `curl "https://api.telegram.org/bot<TOKEN>/setWebhook" -d url=https://<service>.onrender.com/telegram/webhook -d secret_token=<SECRET> -d 'allowed_updates=["message"]'`
   Check with `curl "https://api.telegram.org/bot<TOKEN>/getWebhookInfo"`.
3. Optional command menu: @BotFather → `/setcommands` → `terms - What the words in an alert mean`.
Without the secret the endpoint answers 403 (off). Alerts are unaffected (they are sent by the live job). Free plan:
a sleeping service answers the first `/terms` after ~30-60 s (Telegram retries).

## Run locally
```
pip install -r webapp/requirements.txt
cd webapp && DATABASE_URL=... TELEGRAM_BOT_TOKEN=... TELEGRAM_CHAT_ID=... uvicorn app:app --reload
```
API calls only work with real `initData`, so test the UI inside Telegram. Tests: `pytest tests/test_webapp.py`.
