# Shared contract (all parts must follow this)

Branch: `claude-kevin-king`. Strategy: `STRATEGY.md`. Bias engine: `slk/` (do not change its public
functions without updating callers; `slk.story.find_stories(pair, h1_df, story, cfg)` returns story dicts).

## Env vars / secrets (same names everywhere: GitHub Secrets for Actions, Render env for the web app)
| Name | Use |
|---|---|
| `DATABASE_URL` | Aiven MySQL, `mysql://user:pass@host:port/db?ssl-mode=REQUIRED` |
| `DATABASE_PASSWORD` | optional; used when `DATABASE_URL` has no password (whitespace stripped) |
| `DATABASE_CA` | optional Aiven CA (path or PEM text) to verify the server cert |
| `TELEGRAM_BOT_TOKEN` | bot token |
| `TELEGRAM_CHAT_ID` | owner chat id (also the only Telegram user id allowed in the Mini App and the only chat the bot answers; default 1410229777) |
| `TELEGRAM_WEBHOOK_SECRET` | Render only: secret_token of the bot webhook `POST /telegram/webhook` (answers `/terms`); unset = webhook off |
| `CTRADER_CLIENT_ID`, `CTRADER_CLIENT_SECRET` | Open API app (app "SLK" id 43716) |
| `CTRADER_ACCESS_TOKEN`, `CTRADER_REFRESH_TOKEN`, `CTRADER_ACCOUNT_ID` | first values; refreshed tokens are stored in DB table `settings` |
| `CTRADER_ENV` | `demo` (default) or `live` |

Never print secrets. Never commit them.

## Database (MySQL 8). Schema file: `db/schema.sql` (idempotent CREATE TABLE IF NOT EXISTS)
- `bias` — one row per story: `id` PK, `pair`, `story` (M/W/D), `side` (BUY/SELL), `status`
  (TAPPED/CONFIRMED/TARGET_HIT/INVALIDATED/ENDED_FLIP/CANCELLED), `level_kind`, `level`, `point_b`, `target`, `invalidation`,
  `tap_time`, `confirm_time`, `no_trade` (0/1; 1 = do not trade, e.g. D story while M and W disagree),
  `no_trade_reason` (e.g. `M/W conflict`), `rule` (standard / sweep_start / flip / alignment / cadjpy, `+overlap`),
  `end_reason` (why the story ended), `breakout_time` (UTC open of the confirm-TF candle that broke B),
  `next_day` (1/0, NULL = no breakout or TAPPED: Next Day Rule), `retrace` (1 = closed back beyond B later on the
  breakout day, warning only), `updated_at`; UNIQUE(pair, story, tap_time). Columns added later are
  created on existing tables by `slk/db.py` `migrate()` (run by `apply_schema()`).
- `entries` — entry alerts: `id`, `bias_id` FK, `pair`, `tf`, `side`, `model` (`continuation` | `qmr`, default
  `continuation`; added to existing tables by a guarded ALTER at the end of `db/schema.sql` and by `migrate()`),
  `entry`, `stop`, `tp1`, `tp2`, `status` (PENDING/TRIGGERED/MISSED/CANCELLED), `created_at`, `alerted_at`.
- `orders` — `id`, `entry_id`, `client_order_id` UNIQUE (idempotency), `ctrader_position_id`, `volume`, `status`,
  `opened_at`, `closed_at`, `pnl`.
- `settings` — `k` PK, `v` TEXT (numbers/bools as strings, bools `on`/`off`). Strategy keys are defined ONCE in
  `slk/settings.py` (`SCHEMA`: name, type, default, min/max/choices, help; stdlib only), used by `slk/live.py`
  (`build_cfg`, re-read every run; missing/invalid -> code default = Kevin's rules) and by the Mini App
  (`GET /api/settings/schema`, `GET/POST /api/settings`, server-side validation):
  - Markets: `pairs` (CSV, empty = all 28), `stories` (D,W,M; at least one)
  - Bias rules (no key changes what confirms the bias: always the external break = confirm-TF body close beyond
    point B; internal breaks = entries only, except Kevin's CADJPY exception `cadjpy_exception`): `trend_filter`,
    `htf_filter`, `mw_conflict_filter`, `use_oc` (on/off), `max_wait` (1-20), `max_retaps` (0-10), `tap_tol_pips`
    (0-5), `most_recent_level`, `flip_end`, `htf_targets`, `overlap_rule`, `alignment_start`, `cadjpy_exception`
    (on/off, all on by default), `overlap_tol_pips` (0-20, default 3), `next_day_rule` (`flag` (default) | `require`)
  - Entry rules: `continuation_entries` (on/off = all entry alerts), `entry_models` (`continuation,qmr`; at least one),
    `entry_alignment` (`d_h4` (default) | `w_d_h4` | `off`: continuation entries only when D story + last H4 break
    (+ last W break) agree; entry cfg key `alignment`),
    `breakout_max_bars` (1-12, default 5), `skip_first_retracement` (on/off), `entry_tfs` (`D=H4,H2,H1;W=D,H4;M=W,D`),
    `max_stop_pips` (5-50), `tp1_rr` (0.5-5), `avoid_pairs` (CSV)
  - Risk & trading: `kill_switch` (on/off), `auto_trade` (off/confirm/auto), `risk_pct` (0.1-2)
  - Alerts: `alert_tapped`, `alert_confirmed` (also the RETRACE follow-up), `alert_ended`, `alert_entry`,
    `daily_summary` (on/off), `early_breakout_alert` (on/off, default off: "H4 breakout - waiting for the daily close",
    never CONFIRMED), `display_tz` (type `tz`: IANA zone name checked with zoneinfo, default `Africa/Lagos`),
    `status_updates` (each_run | every_4h (default) | off: Telegram "bot alive" message with time, pairs checked,
    active biases, pending entries, start delay, run time, errors; errors always reported unless off)
  - Internal (not in the form): `early_alerts_sent` (JSON {"PAIR|story|tap_time": ISO sent}, dedupe of early
    breakout alerts, pruned after 40 days), `last_summary`, `last_status` (ISO UTC of the last status message), `weekend_done`
    (NY date of the Friday close whose final weekend run is done), `ctrader_access_token`, `ctrader_refresh_token`,
    `ctrader_token_expiry`.
- `runs` — `id`, `job`, `planned_at`, `started_at`, `finished_at`, `ok`, `note`.

## Candles (no DB table)
H1 candles are NOT stored in MySQL (decision: HANDOVER.md log). `slk/store.py` keeps one file per pair,
`$SLK_STORE/<PAIR>.npz` (default `data/store`; arrays `t` UTC seconds of the bar start, `open`, `high`, `low`, `close`,
`q` source 3=month file / 2=day file / 1=tick file, plus `meta` JSON of finished months/days), and
`$SLK_STORE/memo/<PAIR>.pkl` (live engine output cache). The directory is kept between runs by actions/cache:
key prefix `candles-live-` (live.yml, backfill.yml, same concurrency group `slk-live`) and `candles-full-`
(backtest.yml, restores `candles-full-` then `candles-live-`). API: `store.update(pair, now, days=..)`,
`store.recent(pair, days)` (= `data.recent`), `store.hourly(pair, y0, y1)` (= `data.hourly`, month files only),
`python -m slk.store --start 2018` (backfill).

Python helper for DB access: `slk/db.py` (`connect()`, `upsert_bias(row)`, `get_setting(k, default)`,
`get_settings()`, `set_setting(k, v)`), using PyMySQL.

## Layout
- `slk/` engine (backtest, stories, entries) — `slk/live.py` live runner, `slk/entry.py` entry model
- `ctrader/` Open API client
- `webapp/` Telegram Mini App (Render web service)
- `db/` schema
