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
| 26 | slk/story.py:67 | low | mismatch | fixed (v0.6, `_Ctx.most_recent_ok`) | The level is whichever fresh level agreeing with the trend gets tapped first (newest if several are tapped on one bar). Kevin picks "the most recent fresh KL" first, then waits for its tap, and ignores older levels. |
| 27 | slk/story.py:106 | low | choice | fixed (Bias audit B9) | Point B = last confirm-TF fractal low/high confirmed before the touch bar. A swing made in the last 2 bars before the tap is not confirmed yet, so an older one is used. Kevin reads it in Replay. |
| 28 | slk/story.py:18 | low | choice | open | `max_retaps=3` allows 4 taps in all. Kevin skips at "4–5" taps, so `max_retaps=2` would match more closely. |
| 29 | slk/story.py:22 | low | choice | fixed (v0.6, flip end built: `_Ctx.flip_scan`, status ENDED_FLIP; `max_hold` stays) | Stories end after `max_hold=20` origin bars. STRATEGY's third end rule (a daily KL rejected the other way plus an H4 break the other way) is not built. |
| 30 | slk/story.py:153 | low | mismatch | fixed (v0.6, `_Ctx.target`: same or higher TF + ERL) | Target = nearest opposite fresh level or swing on the origin TF only. STRATEGY says "same or higher TF KL, or ERL". |
| 31 | slk/story.py (no code) | low | mismatch | fixed (v0.6: `overlap_rule`, `alignment_start`, `cadjpy_exception`) | Overlap rule (a weekly KL that is also a daily KL), alignment/continuation rule, and the CADJPY no-H4 exception are not built. |
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
| B7 | Only trend-agreeing levels; the most recent fresh one | T key-levels-pt3@985-1160, story-line-pt2@897-1000 | slk/story.py `_Ctx.choose`, `most_recent_ok` | OK / **fixed #26** |
| B8 | Tap-reject-close on the origin TF: wick in, candle closes back; wait for the close | T story-line@1314-1541; F story-line/sheet_015-021 ("TAP AND REJECT / CLOSE") | slk/levels.py:63 (a tap bar is never the break bar); slk/story.py:236 (confirmed only after origin closes) | OK |
| B9 | Point B = the last lower-TF V-shape (A for a buy) made BEFORE price first tapped; not the rejection's own swing | T story-line-pt3@1690-1790 ("it's B, not A"), pt4@1441-1461; F story-line-pt3/sheet_021 (A/B ticks), story-line-pt2/sheet_015 t=1140-1180 (CADJPY 4H line chart: ray at the last small close peak ~113.2 right before the tapping 4H bar) | slk/story.py:147 `_point_b`, 203, 351 | **fixed**: was an order-2 fractal known before the touch bar, so a turn in the last 2 bars before the tap (CADJPY's B) was skipped for an older one. Now an order-1 close turn (two-candle V/A, STRATEGY §5.10) with index < first touching bar; the touching bar's close may complete it. |
| B10 | External break = confirm-TF BODY close beyond B; "sweep and break" and "breakout" both end in it; later breaks are internal (entries only) | T story-line-pt2@297-650, pt3@594-1260; F story-line-pt2/sheet_001-007 (BMS / BO), story-line-pt3/sheet_015-018 (EXT then BOS) | slk/story.py:222-226; label `_break_kind` :289 | OK |
| B11 | Daily story: the D candle holding the H4 break must close beyond B the same day, else cancel and recheck next day | T qns-pt2@1700-2030; F qns-pt2 | slk/story.py:223-226, 236 | OK |
| B12 | Many re-taps (4-5) before the break = skip; break on day 3-5 still valid | T qns-pt2@2076-2150, story-line-pt3@360-536 | slk/story.py:218-221, `max_wait` | OK (`max_retaps` 3 = choice #28) |
| B13 | M and W stories disagree -> NO_TRADE | T class-wrok@1236-1312 | slk/story.py:50; slk/live.py:178; slk/backtest.py | OK |
| B14 | Never against the higher-TF trend | T liquidity-pt3@712-723 | slk/story.py:106, 343 (HTF trend now on structural swings) | OK |
| B15 | Target = next opposite KL of the same/higher TF or obvious liquidity (ERL) | T story-line@648, pt2@1914-1968, class-wrok@480-620; F story-line-pt2/sheet_025-028 (CADJPY 114.65 = previous D high) | slk/story.py `_Ctx.target` | **fixed #30** (higher-TF levels as of their last closed candle) |
| B16 | Invalidation = body close back through the origin level | T story-line-pt4@383-396; F story-line-pt2 (112.903 line) | slk/story.py:216-217, 272-273; slk/live.py:97 `_closed_through` | OK |
| B17 | Story over when a D KL on the way is rejected the other way + H4 breaks the other way | T story-line-pt2@1779-1869; F story-line-pt2/sheet_023 | slk/story.py `_Ctx.flip_scan`, `finish` | **fixed #29**: status ENDED_FLIP + `end_reason`; opposite story (rule `flip`) may start |
| B18 | Alternative start: wick sweep of the previous day/week high (low) + close back, then break of the last V before the sweep; the sweep candle's own swing does not count; "too far" = no | T story-line-pt3@1887-2096, pt4@1349-1500; F story-line-pt3/sheet_026-029 | slk/levels.py:70 `sweep_taps`; slk/story.py:126 `_taps`, 140 `_pick`; `sweep_start` | **fixed (built)**: pseudo level at the swept high/low, then the normal steps (B before the first touch, external close, same-day rule, invalidation through the swept price, `max_wait` = "too far"). Only where no KL was tapped on that bar (§5.12). |
| B19 | Telegram BIAS message: clearly bias (not entry), pair, story (M/W/D, origin->confirm TF), direction, origin level + type + TF, point B, target, invalidation, status, NO_TRADE reason | CONTRACT / STRATEGY §2 output | slk/live.py:352 `format_alert`, 379 `summary_line`, summary header | **fixed**: header now `BIAS | PAIR | Daily story (D->H4) | BEARISH (SELL) | status`; level type in words (A-shape/V-shape/open-close/flipped/sweep of previous day high); "Point B x (H4 body close below it confirms)"; status line: TAPPED = "NO_TRADE until the H4 breakout of point B", CONFIRMED = "bias confirmed. Not an entry", NO_TRADE reason (M/W conflict); summary: "NO_TRADE (no story)", "tapped (NO_TRADE until breakout)", "-> NO_TRADE (M/W disagree)". |
| B20 | (found by the new stories) entry stop that rounds to 0.0 pips | - | slk/entry.py:210 `_setup` | **fixed**: such a setup is skipped (a stop on the entry is no stop) |
| B21 | Overlap rule, W+D+H4 alignment for continuation, CADJPY no-H4 exception | T all-in-1@1424-1620, weekly-recap@151-282, 626-670, 2098-2160, cadjpy-bd@400-995; F all-in-1/sheet_020-027, weekly-recap/sheet_003-008, cadjpy-bd/sheet_008-009 | slk/story.py `_Ctx.overlap`, `align_starts`, `cadjpy` | **fixed #31** (all switchable, default on; `rule` label) |
| B22 | Kevin's own worked examples as replay checks | notes_storyline §3; frames above | slk/verify_examples.py -> reports/EXAMPLES.md (workflow verify-examples.yml) | built; runs on Actions (Dukascopy blocked here). Examples: CADJPY D buy (112.903 -> 114.65), GBPJPY + USDJPY D "no H4 breakout -> no trade" (Jan 20 2026), USDCAD D sell from the Friday sweep into 1.39201, EURAUD + GBPAUD sells (Feb 2026 recap), USDCHF D reject at 0.7890 with no H4 breakout. |

## Bias rules v0.6 (REVIEW #26, #29, #30, #31) — 2026-10-13

Each rule was checked against the transcript and by opening the frame sheets; numbers Kevin does not give are in
STRATEGY.md §5 rows 14-20 (OUR CHOICE). Code: slk/story.py (`_Ctx`), switches in slk/settings.py ("Bias rules",
all default on), labels `rule` / `end_reason` in every story dict, `bias.rule` / `bias.end_reason` columns
(migration in slk/db.py), status ENDED_FLIP in the live runner, Telegram and Mini App. Tests: tests/test_bias_rules.py
(hand-built H4/D candles + walk properties); with all six switches off the engine still reproduces the v0.5 golden
output (tests/golden/engine_golden_v05.json), so the regenerated tests/golden/engine_golden.json differs only by
these rules. Replay checks added to slk/verify_examples.py: `cadjpy-d-buy-no-h4-exception` (#31c) and
`eurgbp-d-buy-overlap` (#31a/#30). No concrete flip (#29) example exists in the course (story-line-pt2 sheet_023 is
a "what if" drawing), so none was added; alignment (#31b) is covered by the EURAUD/GBPAUD SIDE examples.

| # | Rule | Evidence | Built |
|---|---|---|---|
| 26 | Most recent fresh KL formed before the tap | T story-line-pt2@897-1000; F story-line-pt2/sheet_013-016 | `most_recent_ok`, `choose` |
| 29 | Story ends early: D KL on the way rejected + H4 break of its own B the other way | T story-line-pt2@1779-1869; F story-line-pt2/sheet_023 | `flip_scan`, `finish` (ENDED_FLIP, outcome `flip`), forced opposite start in `find_stories` |
| 30 | Target = next opposite fresh KL of same or higher TF, or ERL; weaker TF caps | T story-line@648, class-wrok@480-620; F story-line-pt2/sheet_025-028 | `target` |
| 31a | Overlap W=D level -> daily reject daily, TP at the next KL, W judged after its close | T all-in-1@1424-1620, cadjpy-bd@811-905; F all-in-1/sheet_020-027 | `overlap` (rule `+overlap`) |
| 31b | Alignment W BOS -> D BOS -> H4 BOS, else no continuation | T weekly-recap@151-282, 626-670, 2098-2160; F weekly-recap/sheet_003-008 | `align_starts` (rule `alignment`) |
| 31c | CADJPY: W bullish + D sweep of PDL into D OC level, close back -> no H4 needed | T cadjpy-bd@400-760, 940-995, 1380-1600; F cadjpy-bd/sheet_008-009 | `cadjpy` (rule `cadjpy`, break_kind `none`) |

Correction found while checking #31a: the v0.5 text "the weekly target becomes the TP" does not match the class.
Kevin: "instead of swing it to here, we take our profit at this key level, because we now have daily reject daily"
[T all-in-1@1599-1617], and the frame TP is the next key level 0.8722 [F all-in-1/sheet_025-027]. Built that way
(next opposite KL), STRATEGY.md updated.

## Validation 4 (commit 6dda831: bias rules v0.6, #26 #29 #30 #31) — 2026-10-13

Each rule re-read in the transcript and checked on the frame sheets (opened). Bias stays separate from entries:
none of these rules creates or changes an entry. With the six switches off the engine still gives the v0.5 output
(test passes), so the external break (confirm-TF body close beyond point B + same-day origin close) is untouched for
normal stories; only #31c skips it, as Kevin does. Golden output regenerated ONLY for V4-1, V4-3, V4-4 (each one
switched back alone reproduces the 6dda831 golden exactly; checked).

| # | Rule | Evidence re-checked | Verdict | Finding / change |
|---|---|---|---|---|
| V4-1 | #26 most recent fresh level | T story-line-pt2@880-1000 ("you place your mark at the most recent one ... price tap this guy first ... this one already abused ... not fresh. The nearest fresh key level is this one ... remove everything and mark that last one"); F story-line-pt2/sheet_012-013 (CADJPY D: 112.903 / 112.746 / 112.730 stacked, the top = most recent kept) | faithful (edge fixed) | `most_recent_ok` counted a newer level that the tap candle CLOSED THROUGH as still fresh, so the deeper older level that held was rejected. Price ran through it ("abused") before reaching the older one; Kevin takes "the nearest fresh key level". FIXED: only a newer level first touched by a TAP on that bar outranks (`_LevelSet.first_tap`). Test `test_newer_level_closed_through_on_the_tap_bar_does_not_block`. |
| V4-2 | #29 flip end (ENDED_FLIP) | T story-line-pt2@1740-1870 ("price will now reject here on daily and close below it ... if we go to four hours ... breakout to the downside ... ended that daily storyline ... if we don't get a rejection and a breakout to the downside ... still bullish"); F story-line-pt2/sheet_023 (CADJPY D replay: 113.946 / 113.49 between origin 112.903 and target ~114.65, drawn rejection + drop) | faithful | D KL on the way (between origin and target), tap-reject-close, then its own H4 point B broken with the same external-break rules; only closed bars (tap events, H4 closes, conf_index). Opposite story starts from that level (rule `flip`). Open (choice, STRATEGY §5.16): only fresh levels count although Kevin says "we treat all key level as valid". |
| V4-3 | #30 targets | T story-line@610-690 (M story: "the first step we are going to target is the monthly fresh level"), class-wrok@470-625 (H4 story: TP at the next H4 level, "we cannot swing it"); F class-wrok/sheet_008 (USDCHF 1h, "tp1" at the next H4 level) | partly | Same TF + ERL is what Kevin shows. Adding W/M levels as caps for a D story is our reading of STRATEGY's "same or higher TF" (no frame shows a D TP capped by a W level): listed as a judgement call. Bug FIXED: in live the last W/M bar is still forming (data cut at the last closed D bar), its `end` = the last hour seen, so `closed_upto` treated it as closed and used levels of a half-built weekly candle; backtest did not (live != backtest). `_LevelSet` now uses the bar's nominal close for the last D/W/M bar (`candles.nominal_end`, Friday 17:00 NY for W, as `live.drop_forming`). Test `test_forming_weekly_bar_is_not_closed`. |
| V4-4 | #31a overlap | T all-in-1@1420-1760 ("two timeframes overlap ... becomes daily reject daily ... this place will not be our final profit. Instead of ... swing it to here, we take our profit at this key level"); F all-in-1/sheet_020-021 (EURGBP D: line at 0.87228 drawn at t=1580; at t=1600 the cursor is on the far swing high 0.88617 = "swing it to here"), sheet_025 t=1920 (0.87228 line on H4), sheet_026 t=2000 (long position box: TP top 0.87233) | faithful | Builder's claim CONFIRMED by transcript AND frames: the TP is the next key level 0.8722, not the swing 0.8862. Same look-ahead as V4-3 FIXED: "weekly judged after its close" was true in live for a still-forming weekly candle whenever the confirmation was at the latest D close. Note: in the bot the D story exists anyway, so overlap mostly changes the target choice (KL before a nearer ERL) and the label. |
| V4-5 | #31b alignment | T weekly-recap@145-285 ("a simple BOS on weekly and then it should happen on daily and then ... on the four hours"), 620-675, 2090-2165 ("if weekly does this, wait for daily to do it"); F weekly-recap/sheet_003 (EURAUD W: three drawn BOS legs W -> D -> H4) | partly | W BOS -> D BOS -> H4 BOS, causal (W break closed before the D bar; H4 turns known at k-1; same-day D close). Kevin presents alignment mainly as a condition for trading ("no alignment, no trade"), the bot builds it as an extra D story start and does NOT filter standard stories by it: judgement call, left as built. |
| V4-6 | #31c CADJPY exception | T cadjpy-bd@380-760 ("after the bullish close above this guy, price did a sweep of previous day low ... weekly is bullish and now daily has flipped the zone ... sweep of previous day low into the daily open close level"), 930-1000 ("you really do not need to be waiting for this breakout again"), 1380-1600; F cadjpy-bd/sheet_008 (big bull D candle Jan 29 closes above the D sell zone, sweep 1-2 candles later), sheet_009 ("target" 114.466) | partly -> fixed | Missing precondition: the daily must ALREADY have flipped that way (a D close above the daily seller) — that is why no H4 breakout is needed "again". The code took any OC/flip tap with W trend + previous-day sweep, i.e. it waived the external break for ordinary taps. FIXED: `_Ctx.flipped_before`: a D body close through an opposite key level within `max_wait` D bars before the sweep (window = our choice). Confirmed only at the closed D bar. Test updated (`test_cadjpy_exception_conditions`). |
| V4-7 | Live runner / Telegram / Mini App | slk/live.py ALERT_ON, STATUS_OF, HEAD, RULE_NAME, format_alert, summary_line, reconcile; webapp BIAS_STATUSES, filter option, app.js Rule + "Ended:" | OK | ENDED_FLIP stored, alerted once (from an active status), shown with reason; CADJPY message says "No point B". |
| V4-8 | Schema | db/schema.sql == webapp/schema.sql (test); `bias.rule` / `end_reason` in CREATE TABLE and in `db.migrate()` (checks information_schema first: idempotent) | OK | As for `no_trade`, the bias columns are added by `migrate()` only (the webapp reads `SELECT *`, so it works before and after). |
| V4-9 | Speed | 2500 synthetic days, D+W+M find_stories + current_tap: v0.5 0.9-1.2 s, 6dda831 2.1-3.6 s (flip_scan re-ran break_search; `_point_b` scanned all swings) | fixed | `break_search` memoised per (level, bar), `_point_b` scans backwards: 1.3-1.7 s (~1.4x v0.5), identical output. |

Judgement calls left open (not changed):
- `cadjpy_exception` default on: on the synthetic walk it still makes 16-26% of D stories (3 seeds), with fewer trade wins
  than standard stories (57-66% vs 72-79%). Kevin shows one example; the user may prefer it off or stricter (e.g. only
  `flip` levels, or the flipped zone = the swept level).
- #30 higher-TF levels capping a D target (not shown by Kevin); #31b alignment as a start, not as a filter;
  `overlap_tol_pips` = 3; flip uses fresh levels only.

## Validation 5 (SLK Radar adopt, commit 7cba861) — 2026-10-13

Checked against STRATEGY.md §2/§3/§5 #21-#22, knowledge-base/study/compare_slk_radar.md (#17, adopt 1-6) and
notes_entry.md (D reject D + H4 BO, same-day cancel, entries from the next day).

| # | Area | Verdict | Finding / change |
|---|---|---|---|
| V5-1 | Next Day Rule definition | OK | `next_day` = confirm-TF breakout candle opens after the origin (rejection) candle (`c2o[brk] > bar`), Kevin story-line-pt3@1358-1401 / qns-pt2@1946-1962. `require` drops a story whose first valid breakout is inside the rejection candle (documented OUR CHOICE §5 #21); a same-day H4 break cancelled by the D close still lets a next-day break count. Alignment stories always break after D bar d; CADJPY `None`. Causal (indices only). |
| V5-2 | Retrace flag look-ahead | OK | Uses confirm-TF closes up to the end of the origin bar holding the breakout = the confirmation time (`same_bar_close` True, not a setting), so the backtest label uses no later bar. Consequence: a CONFIRMED row's `retrace` is final when it is first written, so the RETRACE follow-up alert practically never fires (the CONFIRMED alert already carries the warning). Harmless, left. |
| V5-3 | Entry alignment uses a forming H4 | FIXED | `_Pair.last_break` gave the still-forming last D/W/M bar its nominal close, but not H4/H2: live entries get h1 cut at the last closed HOUR, so the forming H4 bar's partial close could count as "the last H4 structural break" at an H1 pattern's breakout (reproduced on the walk: a 1-hour-old H4 flipped the answer up -> down). Now the last intraday bar also ends at start + TF hours. Test `test_entry_alignment_ignores_forming_h4` (fails before the fix). Backtest unaffected (last bar of the data only). |
| V5-4 | Alignment semantics | OK | d_h4 = the confirmed origin story (D reject D) + last H4 structural break (close beyond the last close-line structural swing, not an internal pattern line) the same way, checked at the pattern's `active` time (breakout close / confirmation, no later bars); w_d_h4 adds W (forming W bar not counted). QMR untouched. For W/M stories the same H4(/W) check is applied (owner setting, documented). |
| V5-5 | Early breakout alert | OK | Only TAPPED, tradable rows; only CLOSED confirm-TF candles inside the open origin candle (`drop_forming`); point B = external break level; never stored, never CONFIRMED; once per story (`early_alerts_sent`, pruned after 40 days). Note: a key is marked sent even if Telegram fails (no token) -> no retry; acceptable for an optional alert. |
| V5-6 | DB migrate / one-time rewrite | OK + FIXED | `ALTER TABLE bias ADD COLUMN ... AFTER ...` is valid MySQL 8, guarded by information_schema (idempotent), applied in order. Old CONFIRMED rows (next_day NULL) are rewritten once with no alert: status unchanged and RETRACE needs stored `retrace` = 0, not NULL (test). FIXED: `_same` did not compare `breakout_time`, so CADJPY rows (next_day/retrace NULL) stored before the migration never got their `breakout_time`; now compared (one silent rewrite). Test in `test_retrace_followup_and_row_compare`. |
| V5-7 | Alerts with None fields / tz | OK | format_alert run with DB-shaped rows (Decimal prices, point_b/target None, no level_time/trend) for M/W/D, every event: no crash; times converted with DST (`WAT`, `EDT`, `UTC`), each labelled open/close. `_aligned` would KeyError on an M row with `htf_trend`, but M stories never carry it (HIGHER["M"] is None). |
| V5-8 | /telegram/webhook security | OK | Secret header compared with `hmac.compare_digest`, endpoint off (403) without `TELEGRAM_WEBHOOK_SECRET`, wrong/missing header 403, only the owner chat gets a reply, only `/terms`, no token use, secret never logged. Mini App `require_user` unchanged (initData HMAC + TELEGRAM_CHAT_ID). |
| V5-9 | Settings consistency | OK | New settings in slk/settings.py, CONTRACT.md (all schema names present), Mini App (`tz` falls back to a text field; server validates with zoneinfo; `tzdata` in webapp requirements); story_cfg/entry_cfg map next_day_rule / entry_alignment -> alignment. db/schema.sql == webapp/schema.sql (test). |
| V5-10 | Backtest variants / workflow | OK | Story variants run `{**cfg, **override}` (memoised per cfg, base reused), entry variants `find_entries(..., {**ecfg, **override}, cfg)` on the base tradable stories; test checks the numbers equal a direct engine run. backtest.yml parses (`IN_ENTRY_CFG` defaults to `{}`). |

Tests: 180 passed (179 + new `test_entry_alignment_ignores_forming_h4`; breakout_time asserts added to
`test_retrace_followup_and_row_compare`).

## Entry diagnosis (cTrader data) — 2026-10-14

Question: ENTRY_REPORT.md (IC Markets cTrader H1, 2018–2026, 28 pairs) shows TP1 (next swing, ≥ 1.5R) winning ~23%
at −0.39R and TP2 (story target) ~7% at ~0R. Bug or weak model? Reproduced offline on the 8 pairs in
`data/examples/` (IC bid, 2022→2026-10, D + W stories, entry DEFAULT, story engine of HEAD 48e7f2e): **234 fills, TP1 21.4%,
−0.42R** = the same picture. 17 trades were printed bar by bar (entry-TF c1..breakout, H1 bars from the setup to the
exit) and checked against §3.

**Checked and correct:** direction (A-shape for sells, V for buys, stop above/below), pip size (JPY 0.01, e.g. USDJPY
13.0 pips = 0.130), fill order (a sell limit fills when the bid high reaches the line; the fill bar can only stop
out, which is right because the entry must be touched before a stop beyond it; a bar opening beyond the entry fills
at the line, 8 of 234 cases), TP1 measured from the entry line (R_tp1 = |entry − tp1| / risk, 1.5R fallback),
retest window (12 entry-TF bars), no look-ahead in the pattern / first-retracement / TP1 swings.

**Bugs found and fixed (slk/entry.py, tests in tests/test_entry.py):**
| # | Bug | Effect | Fix (Kevin) | Test |
|---|---|---|---|---|
| E1 | **Stop inside the level.** Stop = c3..(breakout−1) wick + 1 pip only; the c1/c2 wicks of the A/V shape were ignored. With the 1-pip touch tolerance c3's wick can even stay *under* the line, so stops of 0.2–0.5 pips appeared (EURGBP 2022-03-17: c2 wick +4.3 pips above the line, stop +0.5; USDCHF 2026-09-25: stop 0.4 pips; USDJPY 2025-01-13: c2 wick 16 pips below the line, stop 12). | Median stop 5.9 pips, 26% under 3 pips; 53% of fills stopped out on the very H1 bar that filled them. | Stop beyond the **invalidation zone** = all wicks c1..(breakout−1) + 1 pip; only if that is wider than `max_stop_pips` the rejection candle (the old rule) [T entry3@247-385, qns-pt1@1497-1660; F entry-2/sheet_005-009, qns-pt1/sheet_021, entry3/sheet_010-013]. QMR: head, else the trigger line's own zone/rejection stop. Row key `stop_at` (zone / rejection / head). | `test_stop_covers_level_zone`, `test_stop_never_inside_the_pattern_random_walk` |
| E2 | **Entries after the story ended.** `_story_end` knew the target touch, the origin close back through the level and `max_hold`, but not the flip end (#29): the story was over, the entry model kept taking setups. | 33 of 234 fills (14%) came after a flip, 24 of them lost. | Also stop at the story's own `end_time` (`story_end`, default on). | `test_no_entry_after_story_end` |
| E3 | **QMR look-ahead (one QM-TF bar).** A QM counted from the neck-break close even when the break came on the bar right after the head, before the head pivot (order 2) was confirmed; an H4 QM could then trigger H1 entries 1–2 hours early. | None measurable on the 8 pairs (identical rows), fixed for correctness. | QM known at max(neck break, head + `pivot`) (`qm_known`). | `test_qm_known_waits_for_head_pivot` |
| E4 | **No spread on bid candles** (not a cause of the losses: it makes results *better* than real). | — | `spread_pips` (default 0 = unchanged): BUY fills and SELL stops/TPs on the ask. | `test_spread_on_bid_candles` |

The golden test (`tests/test_speed.py`, `tests/engine_golden.py`) pins the old entry output with
`stop_at=rejection, story_end=False`; `tests/golden/engine_golden.json` is unchanged.

**Before / after on the 8 offline pairs** (D + W stories, DEFAULT entry cfg):
| run | filled | TP1 win% | TP1 avg R | TP2 win% | TP2 avg R | median stop | stops < 3 pips | stopped on the fill bar |
|---|---|---|---|---|---|---|---|---|
| before (HEAD) | 234 | 21.4 | −0.42 | 6.4 | +0.21 | 5.9 | 26% | 53% |
| after (E1–E3) | 221 | 29.4 | −0.21 | 8.1 | −0.20 | 9.1 | 7% | 39% |
| after, `spread_pips` 1.0 | 214 | 25.2 | −0.31 | 7.9 | −0.43 | 9.5 | 6% | 45% |
Per pair TP1 avg R after: CADJPY +0.16, USDJPY / USDCHF / USDCAD / EURAUD / GBPJPY −0.21..−0.22, EURGBP −0.42,
GBPAUD −0.58 (19–36 fills each: noise-level samples). TP2 (story target, median 9R / mean 13R away after the fix)
wins 8%, about what chance gives at that distance; its +0.21R before the fix came from four 23–63R "wins" on 0.5–4
pip stops (USDCHF 1.0 pip → +63R, EURGBP 0.5 pip → +23R).

**Verdict: after the fixes the logic matches §3, and the model has no edge. It is not worse than random any more;
it is about random.** Baselines with the same simulator (same-bar stop+TP = loss):
- random market entries at random H1 bars, same side, same stop and TP1 distances as each filled trade (20 per
  trade): TP1 **32.4%, −0.15R** (with the old tiny stops: 28.6%, −0.26R). The "40% at 1.5R" coin-flip figure does not
  hold at H1 resolution with 5–10 pip stops: one H1 bar often spans both stop and target.
- after the fill bar, the trade's own side vs the mirrored side (same distances from the fill-bar close): 34.8% vs
  31.9% TP1 wins. So no direction edge after the fill.
- TP1 at fixed 1R / 1.5R / 2R / 3R: −0.30 / −0.23 / −0.13 / −0.08R. A loss that shrinks as the target grows = a fixed
  cost per trade with no edge behind it; the cost is the fill bar (39% of fills are stopped on it: the retest that
  fills a limit at the line usually comes with momentum and runs through a 5–10 pip stop within the hour).

**Which part loses** (8 pairs, after the fixes; one variant at a time, small samples, not used to tune anything):
| part | variants (TP1 win%, avg R) | reading |
|---|---|---|
| model | continuation 27.1%, −0.30 · QMR 32.0%, −0.10 | QMR is the less bad half (Kevin ranks it higher, [T entry-4@1420-1440]); neither is positive. |
| entry TF | H1 148 fills, −0.23 · H2 29, −0.12 · H4 43, −0.17 · D ladder H4+H2 only: 32.4%, −0.18 · H4 only: 35.7%, −0.09 (28 fills) | Two thirds of the fills come from the H1 fallback. Kevin goes H4 → 2H and "if you don't find it in 2 hours ... price is not giving you any entry" [T entry-2@668-713], "90% of my entries are from four hours or two hours" [T entry3@2011-2016]; he shows a 1H level only after H4/2H had none and price had already reacted [T entry-2@1258-1326]. Our unconditional H1 rung is wider than Kevin; dropping it does not make the model positive. |
| stop size | rejection-only stop (old) −0.38 · zone stop −0.21 · `max_stop_pips` 15: −0.23 · 30: −0.16 | The old tiny stop was the main bug; beyond that, wider stops help a little, none is positive. |
| TP1 definition | swing TP1 −0.20, 1.5R fallback −0.21; fixed 1R/2R/3R above | Not the cause: the result follows the R multiple, as a no-edge entry does. |
| retest window | `retest_bars` 3: −0.20 · 12 (default): −0.21 · 48: −0.24 | No effect. |
| alignment / skip-first / breakout | `alignment` off −0.22, w_d_h4 −0.19; `skip_first` off −0.14; `breakout_max_bars` 1: −0.18 | No effect beyond noise. |

**What this means:** the bias part decides direction; this entry layer (limit at an H1/H2/H4 line, stop just beyond
a small zone, 1.5R) does not add an edge on IC data and loses its costs. Kevin's own claim is 40–50% winners at
good R:R [T entry-4@171-199] with entries picked by eye (fresh, impulsive breakouts, overlap, "very clear" levels);
the bot's mechanical A/V + 3rd-candle filter finds many more, weaker lines (any two opposite candles, bodies down to
0.7 pip). Recommendations (owner decisions, not applied): (1) do not trade entries live on this model; keep the bias
alerts; (2) run the full 28-pair backtest again (ENTRY_REPORT.md now shows `stop_at` and `fillbar_stop%`), and set
`spread_pips` ~1 for realistic numbers; (3) if the entry layer is kept, test Kevin's tighter scope first: D story
entries only on H4/2H (no unconditional H1), QMR only — on years not used here.
