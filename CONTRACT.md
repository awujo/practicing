# Shared contract (all parts must follow this)

Branch: `claude-kevin-king`. Strategy: `STRATEGY.md`. Bias engine: `slk/` (do not change its public
functions without updating callers; `slk.story.find_stories(pair, h1_df, story, cfg)` returns story dicts).

## Env vars / secrets (same names everywhere: GitHub Secrets for Actions, Render env for the web app)
| Name | Use |
|---|---|
| `DATABASE_URL` | Aiven MySQL, `mysql://user:pass@host:port/db?ssl-mode=REQUIRED` |
| `TELEGRAM_BOT_TOKEN` | bot token |
| `TELEGRAM_CHAT_ID` | owner chat id (also the only Telegram user id allowed in the Mini App) |
| `CTRADER_CLIENT_ID`, `CTRADER_CLIENT_SECRET` | Open API app (app "SLK" id 43716) |
| `CTRADER_ACCESS_TOKEN`, `CTRADER_REFRESH_TOKEN`, `CTRADER_ACCOUNT_ID` | first values; refreshed tokens are stored in DB table `settings` |
| `CTRADER_ENV` | `demo` (default) or `live` |

Never print secrets. Never commit them.

## Database (MySQL 8). Schema file: `db/schema.sql` (idempotent CREATE TABLE IF NOT EXISTS)
- `bias` — one row per story: `id` PK, `pair`, `story` (M/W/D), `side` (BUY/SELL), `status`
  (TAPPED/CONFIRMED/TARGET_HIT/INVALIDATED/CANCELLED), `level_kind`, `level`, `point_b`, `target`, `invalidation`,
  `tap_time`, `confirm_time`, `updated_at`; UNIQUE(pair, story, tap_time).
- `entries` — entry alerts: `id`, `bias_id` FK, `pair`, `tf`, `side`, `entry`, `stop`, `tp1`, `tp2`, `status`
  (PENDING/TRIGGERED/MISSED/CANCELLED), `created_at`, `alerted_at`.
- `orders` — `id`, `entry_id`, `client_order_id` UNIQUE (idempotency), `ctrader_position_id`, `volume`, `status`,
  `opened_at`, `closed_at`, `pnl`.
- `settings` — `k` PK, `v` TEXT. Keys: `kill_switch` (on/off), `auto_trade` (off/confirm/auto), `risk_pct` (0.5),
  `pairs` (CSV), `stories` (D,W,M), `ctrader_access_token`, `ctrader_refresh_token`, `ctrader_token_expiry`.
- `runs` — `id`, `job`, `planned_at`, `started_at`, `finished_at`, `ok`, `note`.

Python helper for DB access: `slk/db.py` (`connect()`, `upsert_bias(row)`, `get_setting(k, default)`,
`set_setting(k, v)`), using PyMySQL.

## Layout
- `slk/` engine (backtest, stories, entries) — `slk/live.py` live runner, `slk/entry.py` entry model
- `ctrader/` Open API client
- `webapp/` Telegram Mini App (Render web service)
- `db/` schema
