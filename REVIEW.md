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
| 23 | slk/structure.py:5 | med | mismatch | fixed (Bias audit B2) | A swing is a fixed-order fractal on closes (`swing_pivot=2` bars each side). STRATEGY §1/§5.1 says a swing is fixed "by a later close beyond the previous opposite swing". This affects trend, point B and targets. |
| 24 | slk/story.py:67 | med | mismatch | open | M/W conflict leads to NO_TRADE only in the daily summary text (slk/live.py:225). It is not applied to stories, D-story gating or the backtest. |
| 25 | slk/story.py (no code) | med | mismatch | fixed (Bias audit B18) | The alternative start (wick sweeps the previous day/week high or low, then the close comes back inside) is not built. |
| 26 | slk/story.py:67 | low | mismatch | open | The level is whichever fresh level agreeing with the trend gets tapped first (newest if several are tapped on one bar). Kevin picks "the most recent fresh KL" first, then waits for its tap, and ignores older levels. |
| 27 | slk/story.py:106 | low | choice | fixed (Bias audit B9) | Point B = last confirm-TF fractal low/high confirmed before the touch bar. A swing made in the last 2 bars before the tap is not confirmed yet, so an older one is used. Kevin reads it in Replay. |
| 28 | slk/story.py:18 | low | choice | open | `max_retaps=3` allows 4 taps in all. Kevin skips at "4–5" taps, so `max_retaps=2` would match more closely. |
| 29 | slk/story.py:22 | low | choice | open | Stories end after `max_hold=20` origin bars. STRATEGY's third end rule (a daily KL rejected the other way plus an H4 break the other way) is not built. |
| 30 | slk/story.py:153 | low | mismatch | open | Target = nearest opposite fresh level or swing on the origin TF only. STRATEGY says "same or higher TF KL, or ERL". |
| 31 | slk/story.py (no code) | low | mismatch | open | Overlap rule (a weekly KL that is also a daily KL), alignment/continuation rule, and the CADJPY no-H4 exception are not built. |
| 32 | slk/levels.py:37 | low | choice | open | The OC level is only looked for at the first two same-colour candles leaving a close-line swing, with the line at the close of candle 1. Kevin's OC levels can appear elsewhere. |
| 33 | slk/entry.py:224 | low | mismatch | open | The entry TF is the first TF on the ladder (H4→H2→H1) that has any pattern. STRATEGY also says to choose the TF with the better R:R (EURGBP example). |
| 34 | slk/entry.py patterns() | low | choice | open | Breakout may now be c4 or any later candle up to `breakout_max_bars` (user correction, frames_E "4th+ candle"). The "internal BOS" is approximated as a close beyond the c1–c3 extremes, with body ≥ the average body of the last 10 bars. |
| 35 | slk/entry.py:38 | low | choice | open | TP1 = nearest unbroken swing between 1.5R and 3R, else 1.5R. STRATEGY says next key level / R 1.4–2. TP1 is not a key level. |
| 36 | slk/entry.py:26 | low | choice | open | Entry TFs for W (D, H4) and M (W, D) stories are not in STRATEGY, which gives only the D-story ladder. |
| 37 | slk/entry.py (no code) | low | mismatch | partly fixed | QMR (Quasimodo Reversal; Whisper: "QMRO") entry built 2026-10-13 (`entry_models`). Still open: the 0.5% max daily loss and the spread check (beyond the fixed avoid list). |
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

## Re-check 2 (commits 5236b8c..706ba7f, Render deploy readiness, workflows)

- Render (`webapp` root, `pip install -r requirements.txt`, `uvicorn app:app --host 0.0.0.0 --port $PORT`): OK.
  requirements.txt covers every import (fastapi, uvicorn, pymysql; pydantic via fastapi). Started locally in a clean
  venv with only webapp/requirements.txt and no DATABASE_URL: startup completes (schema init logs and continues),
  `/healthz` -> `{"ok":true}`, `/` -> 200, `/static/{app.js,style.css,index.html}` -> 200. `webapp/db.py` adds the repo
  root to sys.path, so `slk.db.connect` is used on Render (full clone; slk/db.py is stdlib-only); local PyMySQL
  fallback otherwise.
- DATABASE_PASSWORD fallback works in both `slk/db.parse_url` and `webapp/db._local_connect` (URL password wins,
  env value is stripped). Tests added: tests/test_recheck2.py.
- FIXED live.yml: the failure diagnostic called `db.parse_url` unguarded, so the exact case it targets (URL not
  starting with `mysql://`, e.g. leading whitespace) raised a ValueError traceback instead of the diagnostic. Now
  guarded; the DB error message also masks the DATABASE_PASSWORD value.
- FIXED ctrader-smoke.yml: passed DATABASE_URL without DATABASE_PASSWORD/DATABASE_CA, so the smoke job would fail
  to connect when the password is kept in the separate secret. Test asserts every workflow using DATABASE_URL also
  passes DATABASE_PASSWORD.
- FIXED CONTRACT.md: documented DATABASE_PASSWORD and DATABASE_CA.
- All 5 workflows parse as YAML; secret names match CONTRACT.md. backtest.yml path filter / no-cancel change: OK.
- Not fixed (out of scope / minor): webapp `_local_connect` ignores DATABASE_CA (only matters if slk import fails).

## Validation 3 (commits d22cdd8, 7716d7d: M/W filter, entry alerts, strategy settings)

| # | Where | Finding | State |
|---|---|---|---|
| V3-1 | slk/story.py:130-170, 230; slk/settings.py (old `confirm_break`) | `external_or_sweep` was NOT Kevin's "sweep and break". The code set `swept` when a confirm-TF wick went beyond **B itself** (in the trade direction) and closed back, then let a later close beyond B confirm **without** the same-day origin close. Kevin [T story-line-pt2@297-441]: on the lower TF look for "sweep and break **or** a breakout", not both; the sweep and break "is that advanced market structure" = sweep of liquidity (the highs/lows at the key level, wick beyond and close back) then BOS [notes_structure §4, T ams@1818-2060]. Frames [frames_D story-line-pt2 sheet_001-021 + Corrections]: "BMS" (sweep+break) and "BO" are both a body close through the last A/V before the tap; the CADJPY real chart labels the 4H break "bms". So both branches confirm by the same external close beyond B; the sweep is on the opposite (level) side, and nothing relaxes the same-day close [frames_G Corrections (5)]. A wick through B then a close beyond B is just a later breakout. | FIXED: option removed from story DEFAULT and settings schema (no setting can change what confirms the bias; stored/override `confirm_break` is ignored, POST of it -> 422). Story dicts get `break_kind` = `sweep_break` (a confirm-TF wick beyond the last swing high/low made before the tap, closed back inside, between tap and break) or `breakout` - label only. The V between the two peaks of a QM is after the tap = internal and is never used. Tests: tests/test_settings.py `test_break_is_always_external`, `test_break_kind_label`. |
| V3-2 | slk/live.py:146, 406, 441 | M/W conflict check silently off when settings `stories` excluded M or W (rows for them were never computed), so D stories could be traded against an M/W conflict. | FIXED: `state_stories` computes W and M for the check whenever D is watched and the filter is on; only watched stories are stored/alerted. Test added. |
| V3-3 | slk/settings.py:135 | `stories` could be saved empty (stored "" then silently meant D,W,M). | FIXED: rejected (422). |
| V3-4 | webapp/app.py:203 | Approve read raw stored `auto_trade`/`kill_switch`; an invalid stored value bypassed the defaults. | FIXED: uses `S.load` (invalid -> default off). |
| V3-5 | slk/settings.py, webapp/app.py:181-198 | Defaults equal story/entry DEFAULT (test); POST validates every key before any write (unknown key -> 422, nothing written); GET returns schema keys only (`last_summary`, cTrader tokens never returned); UI escapes all values. | OK |
| V3-6 | slk/live.py main | Settings re-read inside every run (`build_cfg(_load_settings(db))`); alert toggles applied per event (`alerts_enabled`, `alert_entry`); entries only for CONFIRMED, not-NO_TRADE stories; `continuation_entries` gates the internal-break entries; SQL in slk/db.py `upsert_entry`/`get_entries` matches db/schema.sql `entries`. No look-ahead left (the removed sweep branch confirmed at the tap-bar close, before the breakout origin bar closed). | OK |
| V3-7 | slk/backtest.py:73 | `story.apply_mw_filter` exists but the backtest does not call it, so backtest scores still include D stories during M/W conflict. | open |
| V3-8 | slk/live.py:133 | `no_trade` is not stored in `bias`; the Mini App cannot show it (summary recomputes it). | open (low) |

## Bias audit (2026-10-13)

Scope: bias only (slk/structure.py, slk/levels.py, slk/story.py, bias part of slk/live.py + its Telegram bias
messages). Each rule checked against the transcript and by opening the frame sheets. Line numbers are after this
audit. Tests: tests/test_bias_audit.py. Golden engine output (tests/golden/engine_golden.json) regenerated ONLY for
the intended logic changes B2, B9, B18 (and the entry guard B20 that the new stories exposed).

| # | Rule (Kevin) | Evidence | Code | State |
|---|---|---|---|---|
| B1 | Structure and A/V levels on the LINE chart (closes), wicks for taps/sweeps, body closes for breaks | F story-line-pt2/sheet_010 (CADJPY D line chart), sheet_015 (4H replay on line chart), weekly-recap/sheet_006 (ladder on close valleys), key-levels-pt1/sheet_018 (A/V circles on the close line) | slk/structure.py:5, 30; slk/levels.py:18 | OK |
| B2 | Swing = extreme of a main leg, fixed only when a later close breaks the previous opposite swing; the HL is the lowest point that pushed price through the high (a deeper dip replaces it); pullback wiggles are not swings | T basic-ms@456-620; F basic-ms/sheet_004 (EURUSD 1h: only L, H, HL, HH marked) | slk/structure.py:30 `structural_swings`; slk/story.py:120 `_structure` (trend, HTF trend, targets) | **fixed** (was a 2-bar close fractal: every wiggle was a swing). Candidates = order-2 close turns (OUR CHOICE, STRATEGY §5.9). No look-ahead (prefix test). |
| B3 | Trend HH+HL / LH+LL, range = no bias; first close through the protected swing (BMS) flips | T basic-ms-pt2@1590, basic-ms-pt3@875-1211 | slk/structure.py:84; slk/story.py:97 | OK |
| B4 | KL = two candles turning at the same BODY price: A (bull->bear), V (bear->bull), OC (two same-colour candles, line at close 1/open 2); thin line, no box | T key-levels-pt1@1173-1711; F key-levels-pt1/sheet_016-022, story-line-pt2/sheet_013-016 (OC 112.903) | slk/levels.py:18-39 | OK (OC only at a leg start: open #32) |
| B5 | Fresh = no wick touch since it formed; first wick touch uses it; used once | T key-levels-pt4@441-1010; F key-levels-pt4/sheet_011-016 | slk/levels.py:43-63 | OK (open #19 for `level_pivot` > 1) |
| B6 | Full-body close through = flips role, fresh again | T key-levels-pt3@296-420, 1536-1671; F key-levels-pt3/sheet_005-012 | slk/levels.py:64-65 | OK |
| B7 | Only trend-agreeing levels; the most recent fresh one | T key-levels-pt3@985-1160, story-line-pt2@897-1000 | slk/story.py:97-103, 140 `_pick` | OK / open #26 (most recent among the TAPPED ones, not chosen before the tap) |
| B8 | Tap-reject-close on the origin TF: wick in, candle closes back; wait for the close | T story-line@1314-1541; F story-line/sheet_015-021 ("TAP AND REJECT / CLOSE") | slk/levels.py:63 (a tap bar is never the break bar); slk/story.py:236 (confirmed only after origin closes) | OK |
| B9 | Point B = the last lower-TF V-shape (A for a buy) made BEFORE price first tapped; not the rejection's own swing | T story-line-pt3@1690-1790 ("it's B, not A"), pt4@1441-1461; F story-line-pt3/sheet_021 (A/B ticks), story-line-pt2/sheet_015 t=1140-1180 (CADJPY 4H line chart: ray at the last small close peak ~113.2 right before the tapping 4H bar) | slk/story.py:147 `_point_b`, 203, 351 | **fixed**: was an order-2 fractal known before the touch bar, so a turn in the last 2 bars before the tap (CADJPY's B) was skipped for an older one. Now an order-1 close turn (two-candle V/A, STRATEGY §5.10) with index < first touching bar; the touching bar's close may complete it. |
| B10 | External break = confirm-TF BODY close beyond B; "sweep and break" and "breakout" both end in it; later breaks are internal (entries only) | T story-line-pt2@297-650, pt3@594-1260; F story-line-pt2/sheet_001-007 (BMS / BO), story-line-pt3/sheet_015-018 (EXT then BOS) | slk/story.py:222-226; label `_break_kind` :289 | OK |
| B11 | Daily story: the D candle holding the H4 break must close beyond B the same day, else cancel and recheck next day | T qns-pt2@1700-2030; F qns-pt2 | slk/story.py:223-226, 236 | OK |
| B12 | Many re-taps (4-5) before the break = skip; break on day 3-5 still valid | T qns-pt2@2076-2150, story-line-pt3@360-536 | slk/story.py:218-221, `max_wait` | OK (`max_retaps` 3 = choice #28) |
| B13 | M and W stories disagree -> NO_TRADE | T class-wrok@1236-1312 | slk/story.py:50; slk/live.py:178; slk/backtest.py | OK |
| B14 | Never against the higher-TF trend | T liquidity-pt3@712-723 | slk/story.py:106, 343 (HTF trend now on structural swings) | OK |
| B15 | Target = next opposite KL of the same/higher TF or obvious liquidity (ERL) | T story-line@648, pt2@1914-1968; F story-line-pt2/sheet_025-028 (CADJPY 114.65 = previous D high) | slk/story.py:244-250 (fresh opposite origin-TF levels + structural swings = ERL) | OK for same TF; higher-TF KLs still open #30 |
| B16 | Invalidation = body close back through the origin level | T story-line-pt4@383-396; F story-line-pt2 (112.903 line) | slk/story.py:216-217, 272-273; slk/live.py:97 `_closed_through` | OK |
| B17 | Story over when a D KL on the way is rejected the other way + H4 breaks the other way | T story-line-pt2@1779-1832 | - | open #29 |
| B18 | Alternative start: wick sweep of the previous day/week high (low) + close back, then break of the last V before the sweep; the sweep candle's own swing does not count; "too far" = no | T story-line-pt3@1887-2096, pt4@1349-1500; F story-line-pt3/sheet_026-029 | slk/levels.py:70 `sweep_taps`; slk/story.py:126 `_taps`, 140 `_pick`; `sweep_start` | **fixed (built)**: pseudo level at the swept high/low, then the normal steps (B before the first touch, external close, same-day rule, invalidation through the swept price, `max_wait` = "too far"). Only where no KL was tapped on that bar (§5.12). |
| B19 | Telegram BIAS message: clearly bias (not entry), pair, story (M/W/D, origin->confirm TF), direction, origin level + type + TF, point B, target, invalidation, status, NO_TRADE reason | CONTRACT / STRATEGY §2 output | slk/live.py:352 `format_alert`, 379 `summary_line`, summary header | **fixed**: header now `BIAS | PAIR | Daily story (D->H4) | BEARISH (SELL) | status`; level type in words (A-shape/V-shape/open-close/flipped/sweep of previous day high); "Point B x (H4 body close below it confirms)"; status line: TAPPED = "NO_TRADE until the H4 breakout of point B", CONFIRMED = "bias confirmed. Not an entry", NO_TRADE reason (M/W conflict); summary: "NO_TRADE (no story)", "tapped (NO_TRADE until breakout)", "-> NO_TRADE (M/W disagree)". |
| B20 | (found by the new stories) entry stop that rounds to 0.0 pips | - | slk/entry.py:210 `_setup` | **fixed**: such a setup is skipped (a stop on the entry is no stop) |
| B21 | Overlap rule, W+D+H4 alignment for continuation, CADJPY no-H4 exception | T all-in-1@1424-1910, weekly-recap@151-282; F cadjpy-bd | - | open #31 |
| B22 | Kevin's own worked examples as replay checks | notes_storyline §3; frames above | slk/verify_examples.py -> reports/EXAMPLES.md (workflow verify-examples.yml) | built; runs on Actions (Dukascopy blocked here). Examples: CADJPY D buy (112.903 -> 114.65), GBPJPY + USDJPY D "no H4 breakout -> no trade" (Jan 20 2026), USDCAD D sell from the Friday sweep into 1.39201, EURAUD + GBPAUD sells (Feb 2026 recap), USDCHF D reject at 0.7890 with no H4 breakout. |
