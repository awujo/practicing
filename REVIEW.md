# Code review: correctness and fidelity to STRATEGY.md

Scope: `slk/`, `ctrader/`, `webapp/`, `db/schema.sql`, `.github/workflows/*.yml`, `tests/`, checked against
STRATEGY.md v0.3 and CONTRACT.md. Each fix has a regression test in `tests/test_review_fixes.py`, and each
of those tests fails on the code as it was before the fix.

**Backtest numbers change.** Fix #1 removes look-ahead from story confirmation, so the reports in `reports/` are
out of date. Re-run the backtest workflow to get new ones.

Kind: **bug** means the code is wrong whatever the strategy says. **mismatch** means the code differs from STRATEGY.md.
**choice** means the code differs from STRATEGY.md through an OUR CHOICE default, or through a default that is
not written down. A choice is listed but not changed.

## Fixed (9)

| # | File:line | Sev | Kind | Status | Note |
|---|---|---|---|---|---|
| 1 | slk/story.py:136 | high | bug (look-ahead) | fixed | With `same_bar_close`, the breakout is accepted only if the origin bar holding it (D for the daily story) closes beyond B. The story was still confirmed, with entry_ref, at the earlier H4 close, before that close was known. It now confirms when that origin bar closes. |
| 2 | slk/story.py:142 | low | bug (look-ahead) | fixed | Targets used levels and swings "known at" the origin bar of the confirm bar, which may not have closed yet. They now use the last origin bar that has closed. |
| 3 | slk/story.py:180 | low | bug (off-by-one) | fixed | The timeout result (and `busy_until`) used the first confirm bar *after* the `max_hold` window. |
| 4 | slk/story.py:69, 234 | med | mismatch | fixed | "Never against the higher-timeframe trend" was not applied: `htf_trend` was only reported. New `htf_filter` (default on) drops taps against the W trend (D story) or M trend (W story), in `find_stories` and `current_tap`. A range trend is not treated as against. |
| 5 | slk/entry.py:253 | low | bug (off-by-one) | fixed | `simulate` held trades for `max_trade_bars` plus one H1 bar. |
| 6 | slk/data.py:68 | med | bug | fixed | The H1 cache was accepted when its last year was ≥ end_year, so a cache saved early in the running year was reused forever. This includes the Actions cache, whose key is fixed. It must now reach Dec 20 of end_year, or one week ago. |
| 7 | .github/workflows/backtest.yml (Backtest, Entry backtest) | med | bug (hidden failure) | fixed | `set +e` without exiting with the real code kept the job green when the backtest crashed. Both steps now exit with the real code. The entry step still runs after a failed story step, and the report is still committed. |
| 8 | .github/workflows/backtest.yml (env) | low | security | fixed | `inputs.cfg/pairs/...` were pasted into the shell script, which allowed shell injection. They are now passed through job `env`. |
| 9 | webapp/schema.sql | low | bug (schema drift) | fixed | The fallback schema differed from db/schema.sql: no indexes, `level_kind` VARCHAR(16), no default settings. It is now an exact copy, and a test keeps the two equal. |

## Open: bugs, security and ops (13)

| # | File:line | Sev | Kind | Status | Note |
|---|---|---|---|---|---|
| 10 | .github/workflows/live.yml:6 | high | bug (ops) | open | `schedule` runs only from the default branch (`qwen-kevin-king`), and that branch has no live.yml. The hourly live bias never runs on its own. Merge live.yml into the default branch, or make claude-kevin-king the default. |
| 11 | slk/live.py (whole), slk/entry.py | med | missing | open | Stage 2 is not connected: nothing writes `entries` or sends entry alerts, and the entry model runs only in the backtest. |
| 12 | webapp/app.py:234 | low | contract | open | Approve sets `entries.status='APPROVED'`, which is not in the CONTRACT list (PENDING/TRIGGERED/MISSED/CANCELLED). Add it to CONTRACT.md or use another column. |
| 13 | slk/live.py:339 | low | hidden failure | open | The job exits 0 when only some pairs fail. The failure is recorded in `runs.ok=0`, but Actions shows green. This is deliberate: "red only when nothing worked". |
| 14 | .github/workflows/live.yml:12 | low | ops | open | A push to slk/live.py starts a real live run, with DB writes and Telegram alerts. |
| 15 | .github/workflows/live.yml:24, render.yaml | low | contract | open | `TELEGRAM_CHAT_ID` falls back to a hard-coded owner id. CONTRACT.md lists it as a secret. |
| 16 | slk/db.py:46, webapp/db.py:42 | low | security | open | TLS to MySQL does not check the certificate unless `DATABASE_CA` is set (this is documented). Set `DATABASE_CA` on GitHub and Render. |
| 17 | ctrader/tokens.py:62 | low | safety | open | Without a DB (MemorySettings), the kill switch cannot be on. Order paths use `strict=True` (smoke `--test-order`, client default). Note this for the future trader job. |
| 18 | ctrader/client.py:130 | low | bug | open | When more than 2000 messages queue up, the oldest 500 are dropped, and a pending reply could be among them (then the request times out). |
| 19 | slk/levels.py:28 | low | mismatch | open | Wick touches between candle 2 and `born` are not counted as "used". This does nothing with `level_pivot=1` (born = c2+1), but makes stale levels look fresh if `level_pivot>1`. |
| 20 | slk/live.py:51 | low | fragile | open | `now_shift` mixes a NY-shifted 4h floor with a UTC 4h remainder. The result is correct only because every D/W/M/H4 boundary is a multiple of 4 shifted hours. `now.tz_convert(NY)+7h` would be clearer. |
| 21 | slk/story.py:97 (backtests) | low | bug | open | At the end of the data, a still-forming last origin bar is treated as closed in backtests (live drops it with `drop_forming`). This only affects the last few stories of a run. |
| 22 | slk/data.py:83 | low | robustness | open | A month that fails twice to download raises an error and stops the whole multi-pair backtest. |

## Open: strategy fidelity (17)

| # | File:line | Sev | Kind | Status | Note |
|---|---|---|---|---|---|
| 23 | slk/structure.py:5 | med | mismatch | open | A swing is a fixed-order fractal on closes (`swing_pivot=2` bars each side). STRATEGY §1/§5.1 says a swing is fixed "by a later close beyond the previous opposite swing". This affects trend, point B and targets. |
| 24 | slk/story.py:67 | med | mismatch | open | M/W conflict leads to NO_TRADE only in the daily summary text (slk/live.py:225). It is not applied to stories, D-story gating or the backtest. |
| 25 | slk/story.py (no code) | med | mismatch | open | The alternative start (wick sweeps the previous day/week high or low, then the close comes back inside) is not built. |
| 26 | slk/story.py:67 | low | mismatch | open | The level is whichever fresh level agreeing with the trend gets tapped first (newest if several are tapped on one bar). Kevin picks "the most recent fresh KL" first, then waits for its tap, and ignores older levels. |
| 27 | slk/story.py:106 | low | choice | open | Point B = last confirm-TF fractal low/high confirmed before the touch bar. A swing made in the last 2 bars before the tap is not confirmed yet, so an older one is used. Kevin reads it in Replay. |
| 28 | slk/story.py:18 | low | choice | open | `max_retaps=3` allows 4 taps in all. Kevin skips at "4–5" taps, so `max_retaps=2` would match more closely. |
| 29 | slk/story.py:22 | low | choice | open | Stories end after `max_hold=20` origin bars. STRATEGY's third end rule (a daily KL rejected the other way plus an H4 break the other way) is not built. |
| 30 | slk/story.py:153 | low | mismatch | open | Target = nearest opposite fresh level or swing on the origin TF only. STRATEGY says "same or higher TF KL, or ERL". |
| 31 | slk/story.py (no code) | low | mismatch | open | Overlap rule (a weekly KL that is also a daily KL), alignment/continuation rule, and the CADJPY no-H4 exception are not built. |
| 32 | slk/levels.py:37 | low | choice | open | The OC level is only looked for at the first two same-colour candles leaving a close-line swing, with the line at the close of candle 1. Kevin's OC levels can appear elsewhere. |
| 33 | slk/entry.py:224 | low | mismatch | open | The entry TF is the first TF on the ladder (H4→H2→H1) that has any pattern. STRATEGY also says to choose the TF with the better R:R (EURGBP example). |
| 34 | slk/entry.py:81, 87 | low | choice | open | The c4 "internal BOS" is approximated as a close beyond the c1–c3 extremes, with body ≥ the average body of the last 10 bars. |
| 35 | slk/entry.py:38 | low | choice | open | TP1 = nearest unbroken swing between 1.5R and 3R, else 1.5R. STRATEGY says next key level / R 1.4–2. TP1 is not a key level. |
| 36 | slk/entry.py:26 | low | choice | open | Entry TFs for W (D, H4) and M (W, D) stories are not in STRATEGY, which gives only the D-story ladder. |
| 37 | slk/entry.py (no code) | low | mismatch | open | QMRO reversal entry, the 0.5% max daily loss, and the spread check (beyond the fixed avoid list) are not built. |
| 38 | slk/story.py:11-22 | low | choice | open | Defaults not written in STRATEGY §5: `swing_pivot=2`, `level_pivot=1`, `max_hold=20`, `stop_buffer_pips=2`, `max_retaps=3`, `same_bar_close` (the last two do follow written rules). Add them to the OUR CHOICE table. |
| 39 | slk/story.py:16-17 | — | choice (documented) | ok | Tap tolerance of 1 pip (§5.6) and max wait of 5 origin bars (§5.7) are documented OUR CHOICE defaults and are built as written. |

## Checked and found correct

- **Candles:** D/W/M/H4/H2 close at 17:00 New York, and weeks close Friday at 17:00 New York (`candles._key`, `live.BAR_LEN`).
- **Pip sizes:** 0.01 for JPY pairs and 0.0001 otherwise. Dukascopy point scale is 1e3 for JPY and 1e5 otherwise. Month index is 0-based. Record order is t, o, c, l, h.
- **Rules built as written:**
  - Structure on closes, and A/V levels at the body price.
  - A tap is the first wick touch and uses the level. A body close through the level flips it.
  - Story chain: tap → reject → close on the origin TF, then a body close beyond B on the confirm TF.
  - The same-day close back through B cancels the story.
  - The entry pattern (c1–c4), retest limit, stop beyond c3, ≤20 pips, TP2 = story target.
- **Database:** SQL in slk/db.py and webapp/ matches db/schema.sql.
- **Telegram:** initData HMAC check, 24 h expiry and owner-only access are correct. The bot token is never printed.
- **cTrader:** live trading needs `allow_live=True` and a live account. The kill switch blocks every order path and does not block closes. Orders are idempotent through `client_order_id`.
