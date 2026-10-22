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
| `SLK_SOURCE` | optional: candle source `ctrader` / `dukascopy`; unset = `ctrader` when `CTRADER_CLIENT_ID`, `CTRADER_CLIENT_SECRET` and (`CTRADER_ACCESS_TOKEN` or `DATABASE_URL`) are set, else `dukascopy` |

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
  `entry`, `stop`, `tp1`, `tp2`, `status` (PENDING/APPROVED/TRIGGERED/MISSED/CANCELLED, then the paper outcome
  TP1_HIT/TP2_HIT/SL_HIT/EXPIRED), `created_at`, `alerted_at`, and the **paper result** of the bot signal (not a
  broker trade; real cTrader trades stay in `orders`): `filled_at` (UTC start of the H1 bar that filled the limit),
  `result_r` (R of the TP1 variant: exit at TP1 / stop / timeout close), `result_r_tp2` (R of the TP2 variant, NULL
  until that leg is resolved), `hit_price` (stop / TP1 / TP2 / timeout close), `closed_at` (UTC start of the H1 bar
  where tracking ended; NULL while open). These five columns are added to existing tables by `migrate()`.
  Rules = the entry backtest (`slk.entry.paper_track` shares `simulate`'s code): closed H1 bars after the fill only,
  same bar stop + target = loss, the fill bar can only stop out, no breakeven, held `max_trade_bars` entry-TF bars.
  SL_HIT = stop before TP1 (−1R both legs); TP1_HIT = TP1 reached (TP2 leg still open, or stopped / timed out
  after TP1); TP2_HIT = both; EXPIRED = nothing hit in the holding time (closed at market). A PENDING entry whose
  bias row has ended (TARGET_HIT/INVALIDATED/ENDED_FLIP/CANCELLED) becomes CANCELLED (entry `story_end` rule).
  Outcome updates are guarded (`WHERE status = old AND closed_at IS NULL`) and written before the Telegram alert
  (TP1 / TP2 / stop / stop after TP1, toggle `alert_entry`), so each is sent once.
- `orders` (real broker trades only) — `id`, `entry_id`, `client_order_id` UNIQUE (idempotency), `ctrader_position_id`, `volume`, `status`,
  `opened_at`, `closed_at`, `pnl`.
- `settings` — `k` PK, `v` TEXT (numbers/bools as strings, bools `on`/`off`). Strategy keys are defined ONCE in
  `slk/settings.py` (`SCHEMA`: name, type, default, min/max/choices, help; stdlib only), used by `slk/live.py`
  (`build_cfg`, re-read every run; missing/invalid -> code default = Kevin's rules) and by the Mini App
  (`GET /api/settings/schema`, `GET/POST /api/settings`, server-side validation):
  - Markets: `pairs` (CSV, empty = all 28; metals XAUUSD/XAGUSD and IC index names allowed), `stories` (D,W,M; at least one)
  - Every `*_pips` key is in the symbol's pips (STRATEGY §5 #28: XAUUSD 0.1, XAGUSD 0.01, indices 1.0, or the cTrader
    `pipPosition`)
  - Bias rules (no key changes what confirms the bias: always the external break = confirm-TF body close beyond
    point B; internal breaks = entries only, except Kevin's CADJPY exception `cadjpy_exception`): `trend_filter`,
    `htf_filter`, `pullback_levels`, `mw_conflict_filter`, `use_oc` (on/off), `max_wait` (1-20), `max_retaps` (0-10), `tap_tol_pips`
    (0-5), `level_tol_pips` (0-5, default 0: broker tolerance in pips added to `tap_tol_pips` for wick touches only
    (tap, fresh check, first touch, re-taps); never for closes, a break of point B is a real close; STRATEGY §5 #25),
    `most_recent_level`, `flip_end`, `htf_targets`, `overlap_rule`, `alignment_start`, `cadjpy_exception`
    (on/off, all on by default), `overlap_tol_pips` (0-20, default 3), `next_day_rule` (`require` (default since 2026-10-14) | `flag`),
    `trend_mode` (`leg` (default since 2026-10-14: a close beyond the last V/A-shape of the current leg flips the
    trend) | `protected` (the older protected order-2 swing; before 2026-10-14))
  - Entry rules: `continuation_entries` (on/off = all entry alerts), `entry_models` (`continuation,qmr`; at least one),
    `entry_alignment` (`d_h4` (default) | `w_d_h4` | `off`: continuation entries only when D story + last H4 break
    (+ last W break) agree; entry cfg key `alignment`),
    `breakout_max_bars` (1-12, default 5), `skip_first_retracement` (on/off), `entry_tfs` (`D=H4,H2;W=D,H4;M=W,D` since 2026-10-14: D story H4/2H only, no 1H),
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
H1 candles are NOT stored in MySQL (decision: HANDOVER.md log). Source: **IC Markets cTrader** Open API H1
trendbars (bid, UTC, hour-aligned; zero-volume and FX-weekend bars dropped), Dukascopy only as the fallback when the
cTrader secrets are missing or cTrader fails. `slk/store.py` keeps one file per pair, `$SLK_STORE/<PAIR>.npz`
(default `data/store`; arrays `t` UTC seconds of the bar start, `open`, `high`, `low`, `close`, `q` quality
3 = final month / 2 = current cTrader month (refreshed) or Dukascopy day file / 1 = Dukascopy tick file, plus `meta`
JSON `{"m": final months, "d": Dukascopy days, "src": "ctrader" | "dukascopy"}`; one source per file, a file of
another source is rebuilt), and `$SLK_STORE/memo/<PAIR>.pkl` (live engine output cache). Dukascopy fallback bars for
a pair whose file is cTrader go to `$SLK_STORE-fallback/<PAIR>.npz` (this run only, not cached). One cTrader
connection per job (`store.get_feed()`), <= 4 history requests/s, ~8 months per H1 request.
The directory is kept between runs by actions/cache, key prefix **`candles-v3-`** (cTrader store) in live.yml,
backfill.yml, backtest.yml, verify-examples.yml; backfill saves unfinished progress as `partial-candles-v3-` (only
backfill restores it). A store is saved only when `python -m slk.store --check --start 2018 --source ctrader`
passes. Old `candles-v2-` / `candles-partial-` (Dukascopy) caches are never restored. API:
`store.update(pair, now, days=..)`, `store.update_all(pairs, now, days)`, `store.recent(pair, days)`,
`store.hourly(pair, y0, y1)` (final months only), `python -m slk.store --start 2018 [--notice]` (backfill).
A cTrader file's meta also carries `"sym": {symbol_id, name, digits, pip_position}`; loading it registers the pip
size / decimals in `slk/instruments.py` (pip = 10^-pipPosition; else the static table: FX 0.0001, JPY 0.01, XAUUSD
0.1, XAGUSD 0.01, indices 1.0). Non-FX Dukascopy names / scale: `slk/instruments.DUKASCOPY` (XAUUSD, XAGUSD 1e3;
US500 -> USA500IDXUSD ...). Debug: `python -m slk.debug_pair --pair XAUUSD` (workflow `debug-pair.yml`) writes
`data/debug/<PAIR>_H1_<source>.csv.gz` + `<PAIR>_explain.txt`.

Python helper for DB access: `slk/db.py` (`connect()`, `upsert_bias(row)`, `get_setting(k, default)`,
`get_settings()`, `set_setting(k, v)`), using PyMySQL.

## Layout
- `slk/` engine (backtest, stories, entries) — `slk/live.py` live runner, `slk/entry.py` entry model
- `ctrader/` Open API client
- `webapp/` Telegram Mini App (Render web service)
- `db/` schema


## Research isolation

Manual `research-study.yml` uses `research_records` (created only by `slk.research_publish`) in the existing MySQL instance: composite PK `(run_id,kind,record_id)`, SHA-256 payload checksum, LONGTEXT JSON payload, creation time. Kinds include manifest, events, observations, decisions, entry_trials, discovery and checkpoint. Per-event records are immutable; aggregate/checkpoint IDs are content hashes, so partial/resumed snapshots append without overwriting. It never calls live apply_schema or modifies bias/entries/orders/settings. Broker collection can refresh cTrader auth tokens using the existing client. Raw candles remain in expiring artifacts, not MySQL. See research/STATUS.md before enabling recurring research or relying on backup/retention.

## Multiuser scope (2026-10-22)

Telegram initData identifies the user; never accept a client-supplied recipient/tenant ID. Owner ID is
TELEGRAM_CHAT_ID (fallback1410229777), and keeps existing tables. Other users use tenant_bias,
tenant_entries, tenant_orders, tenant_tf_state, tenant_settings, tenant_runs keyed/scoped by user_id.
app_users records authenticated registrations. slk.tenancy.ContextVar scopes SQL in both DB adapters;
async auth dependency resets it after each request. Composite bias/entry foreign keys enforce ownership.
Run schema installation outside user scopes. Never issue raw tenant-table queries in request code.
New users start EURUSD,GBPUSD,USDJPY / D,W / auto_trade=off. Each watchlist supports30 selected markets;
empty restores starter selection. Preferences and notification clocks are private. Broker approvals and
non-off auto_trade remain owner-only; no shared brokerage authority is granted by Mini App access.
Hourly downloads use union of saved pairs, not the complete broker catalogue. Computations with identical
inputs/configs share immutable cached results; reconciliation receives independent copies. Owner processes
first, other users rotate after12min budget; UI/digests show completed-scan freshness rather than promise
an account scan every hour under overload. Each profile's settings snapshot stays fixed during a batch.
Run local integration only against a disposable database via SLK_TEST_MYSQL; tests/test_multiuser_mysql.py
checks MySQL8 DDL/FKs, concurrent API reads/settings isolation and digest routing without sending messages.
