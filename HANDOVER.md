# HANDOVER — read this first in a new chat

Project: Kevin King "SLK" trading bot. Gives **bias** (main goal), then **entry alerts**, later **trades on
IC Markets cTrader (demo first)**. No VPS, no Docker, no MT5.

Repo `awujo/trading`, work branch **`claude-kevin-king`** (Claude). `qwen-kevin-king` = Qwen's older attempt,
ignore. `main` = old bot code, don't touch. Owner Telegram chat id: 1410229777.

**Rule for every session:** update this file (Status + Log) in the same commit as any change.

## Architecture
| Part | Where | Runs on |
|---|---|---|
| Strategy (the rules) | `STRATEGY.md` (v0.6) | — |
| Course evidence | `knowledge-base/` (transcripts, frame sheets), `knowledge-base/study/*.md` notes | — |
| Bias engine | `slk/structure.py`, `levels.py`, `story.py`, `candles.py`, `data.py` | — |
| Bias backtest | `slk/backtest.py` → `reports/REPORT.md` | GitHub Actions `backtest.yml` (on push to slk/**) |
| Entry model + backtest | `slk/entry.py`, `slk/entry_backtest.py` → `reports/ENTRY_REPORT.md` | same workflow |
| Live bias runner | `slk/live.py`, `slk/db.py`, `db/schema.sql` | Actions `live.yml`, hourly at :07 (not on the FX weekend) |
| Candle store (H1, incremental) | `slk/store.py` → `data/store/*.npz` in the Actions cache | filled by `backfill.yml` (manual, once), kept by live + backtest |
| cTrader client | `ctrader/` (README has OAuth steps) | Actions `ctrader-smoke.yml` |
| Telegram Mini App | `webapp/` (FastAPI), `render.yaml` | Render, branch claude-kevin-king, root `webapp` |
| Shared names (env vars, DB tables) | `CONTRACT.md` | — |
| Code review findings | `REVIEW.md` (incl. "Bias audit") | — |
| Kevin's worked examples replay | `slk/verify_examples.py` → `reports/EXAMPLES.md` | Actions `verify-examples.yml` (push on that file / manual) |

Data: Dukascopy free hourly candles (works from Actions; blocked from Claude's sandbox). cTrader candles later.
Candles close 17:00 New York. Secrets: `DATABASE_URL`, `TELEGRAM_BOT_TOKEN` (chat id defaults to owner).
Claude cannot read Actions logs (redirect blocked) → workflows write errors as `::error` annotations or into
`reports/run.log`, which Claude reads via the GitHub API.

## Status (2026-10-13)
- [x] Strategy studied: all 29 transcripts + all ~700 frame sheets. STRATEGY.md v0.3.
- [x] Bias engine, entry model, live runner, cTrader client, Mini App — all built, tests pass (`pytest -q tests`).
- [ ] **Backtest results on real data** — run in progress (28 pairs, 2018–2025). Read `reports/REPORT.md` when committed.
- [ ] **Live runner** — fails: Aiven `Access denied` → user must fix the password in GitHub secret `DATABASE_URL`.
- [x] Code review done (`REVIEW.md`): 9 fixed (incl. look-ahead in story backtest, HTF filter now applied), 30 open.
- [x] Default branch is `claude-kevin-king` (set 2026-10-13): hourly cron + manual Run buttons work.
- [ ] Render deploy of Mini App (user: set branch + root dir + 2 env vars).
- [ ] cTrader: app "SLK" id 43716 is *Submitted* (not active). Get tokens per `ctrader/README.md`, then run cTrader smoke workflow.
- [x] M/W conflict enforced in live runner (D stories NO_TRADE, no TAPPED/CONFIRMED alerts) and stored in
      `bias.no_trade` / `no_trade_reason` (Mini App shows a NO_TRADE tag). Backtest applies `story.apply_mw_filter`:
      NO_TRADE D stories are not scored; REPORT.md section "M/W conflict filter" shows all vs kept vs removed.
- [x] **Efficiency** (Actions minutes): candle store in the Actions cache, each hourly run downloads only the new
      bars (~1 file per pair instead of ~26-35); engine output cached per story until a new origin bar closes;
      pairs computed in a process pool; engine hot spots removed (identical output, golden test). No scheduled
      runs on the FX weekend except the final one after Friday 17:00 NY. Hourly target 1-3 min.
- [ ] **User, once:** Actions → "SLK candle backfill" → Run workflow (start 2018). Fills the candle cache for live +
      backtest (~5-15 min). Without it the first live run builds the 3-year store itself (slower, still works).
- [x] Telegram "bot alive" status (setting `status_updates` = each_run / every_4h (default) / off) + workflow
      failure alert (`if: failure()` step, curl, secrets never printed).
- [x] Entry alerts wired into live runner: CONFIRMED tradable stories -> `slk.entry` (sim=False) -> table `entries` (PENDING/TRIGGERED/MISSED) + Telegram on new PENDING and on TRIGGERED ("confirm in Mini App" note when auto_trade=confirm).
- [x] Strategy settable from the Mini App Settings tab (5 groups, help text per field) -> table `settings`, read by
      `slk/live.py` every run (fallback = code defaults). Schema: `slk/settings.py` (CONTRACT.md lists the keys).
      No setting changes what confirms the bias (external break beyond B only; `confirm_break` removed in
      Validation 3). Story dicts carry `break_kind` = breakout | sweep_break (label only).
- [x] Entry models per user correction (2026-10-13): **continuation** breakout on the 4th OR any later candle
      (`breakout_max_bars`, default 5, no close back through the line first) and **QMR** = Quasimodo Reversal
      (was "QMRO" = Whisper). Setting `entry_models` (both on), `entries.model` column (guarded ALTER), alerts and
      Mini App show the model, ENTRY_REPORT.md has "By entry model". Guessed rules = OUR CHOICE table in STRATEGY §3.
- [x] Bias audit (REVIEW.md "Bias audit" B1-B22): structural swings (close beyond the previous opposite swing)
      for trend/targets, point B = last close-line V/A before the first touch, alternative start (sweep of previous
      day/week high/low) built, Telegram bias messages say BIAS + status/NO_TRADE reason.
- [x] Bias rules v0.6 (REVIEW #26 #29 #30 #31): most recent level before the tap, story ends early by a flip
      (status ENDED_FLIP), targets on the same or a higher TF, overlap / alignment / CADJPY exceptions; all switchable
      in Mini App "Bias rules" (default on), `rule` + `end_reason` per story (DB columns, Telegram, Mini App).
- [x] SLK Radar ideas 1-6 built (compare_slk_radar.md "Worth adopting"): Next Day Rule, clearer alerts in
      `display_tz`, optional early breakout alert, retrace warning, level "formed" date, `/terms`; continuation entries
      need D+H4 alignment (`entry_alignment` d_h4, owner decision). Backtest REPORT.md "Variants" compares
      next_day_rule flag/require, cadjpy on/off, entry_alignment d_h4/w_d_h4/off: pick defaults from it.
- [ ] **User, once (for /terms):** Render env `TELEGRAM_WEBHOOK_SECRET` + `setWebhook` (steps in `webapp/README.md`
      "Bot command /terms"). Until then /terms gets no answer; everything else works.
- [ ] Read `reports/EXAMPLES.md` after the verify-examples workflow ran (Kevin's own examples PASS/FAIL).
- [ ] Ideas not built: Mini App page to paste cTrader tokens into DB;
      HTF-agreement filter in live runner.

## Next steps (in order)
0. Run "SLK candle backfill" once (see Status).
1. Fix `DATABASE_URL` → rerun "SLK live bias" (Actions → Run workflow, or Claude dispatches it via API).
2. Read backtest reports; tune `slk/story.py` DEFAULT / entry DEFAULT by results (out-of-sample years).
3. Deploy Mini App on Render, set BotFather menu button to the Render URL.
4. Entry alerts live → then demo trading with kill switch + confirm button.

## Log
- 2026-10-12/13: Kevin King course study (transcripts + frames), STRATEGY v0.1→v0.3.
- 2026-10-13: Built engine + backtest; parallel agents built entry model, live runner, cTrader client, Mini App.
  Fixed CI deps (`requirements-dev.txt`). Chat id default set. Live run blocked by Aiven password.
  User DB = `Claude-KK-SLK` (Qwen uses defaultdb). Review agent fixed 9 issues; old backtest reports invalid (look-ahead), rerun.
- 2026-10-13: REVIEW #24 (M/W conflict -> NO_TRADE for D in live; backtest helper) and #11 (entries + entry alerts in live runner, `db.upsert_entry`/`get_entries`). `DATABASE_PASSWORD` env now wins over URL password (slk/db.py). Tests `tests/test_mw_entries.py`.
- 2026-10-13: Settings from Mini App: `slk/settings.py` schema (stdlib only) -> `/api/settings/schema`, validated
  `/api/settings`, dynamic grouped form; live runner builds story/entry cfg + pairs/stories/alert toggles from DB.
  `story.DEFAULT["confirm_break"]` (external / external_or_sweep, `break_kind` in story dicts). Tests `tests/test_settings.py`.
- 2026-10-13: Validation 3 (d22cdd8, 7716d7d): `external_or_sweep` was not Kevin's sweep-and-break (it swept B itself
  and waived the same-day close) -> removed; sweep-and-break = label `break_kind`, break always external beyond B.
  Live computes M/W for the D-story check even if only D is watched; `stories` can't be empty; approve uses
  validated settings. REVIEW.md "Validation 3".
- 2026-10-13: Efficiency pass (live job took 20+ min: every run re-downloaded the current month's day files and up to
  23 hourly tick files per pair, 3 at a time). Candle store choice = **Actions cache, not MySQL**: restoring a
  ~10-40 MB archive takes seconds, while the hourly job would otherwise read ~700k candle rows from Aiven each run
  and the free DB would hold them; the store is a cache (rebuilt from Dukascopy if evicted), the DB keeps state.
  `slk/store.py`: per pair .npz with source quality (month file > day file > tick file, better replaces worse, so
  the window equals `data.recent`, tested hour by hour on a simulated feed). Live: download phase (8 threads) ->
  engine phase (process pool; `pair_state` memo in `data/store/memo`, key = sha1 of engine code + cfg + closed
  bars, so D recomputes once a day, W weekly, M monthly) -> DB/alerts phase. `backfill.yml` (manual) fills the
  store; `backtest.yml` restores the same store (prefix `candles-full-` then `candles-live-`), timeout 60 min.
  Weekend: cron skips Saturday UTC, a shell gate skips Fri 20:00 -> Sun 17:00 NY, the runner skips once
  `weekend_done` is set. Engine speed (find_stories/current_tap): SwingBook (no swings() rebuilds), vectorised
  run_levels / pivots, precomputed per-level first event and per-origin-bar confirm index; 28 pairs x 3 years
  synthetic: 20.8 s -> 12.1 s single process, 4.1 s on 4 processes, 0.5 s on a memo hit. Regression test
  `tests/test_speed.py` compares with golden output of the old engine (`tests/golden/engine_golden.json`).
  Simulated feed (0.1 s/file): download 29 s -> 1.1 s for 28 pairs. Also: `bias.no_trade(_reason)` (+ migration in
  `db.migrate`), backtest M/W filter + report section, `status_updates` setting, failure alert. Tests
  `tests/test_store.py`, `tests/test_efficiency.py`, `tests/test_speed.py`.

- 2026-10-13: Default branch switched to claude-kevin-king. Mini App live on Render (opens in Telegram; DB 503 until DATABASE_PASSWORD set on Render). Backfill + backtest queued.
- 2026-10-13: Entry models (user correction). `slk/entry.py`: continuation breakout = c4 or any later candle within
  `breakout_max_bars` (5, OUR CHOICE), a close back through the line first kills the level, stop beyond the highest
  rejection wick c3..breakout-1; new QMR model (shoulder -> neck -> higher-close head -> body close through the
  neck on the entry TF; price back in the shoulder/neck zone + 1H continuation breakout there; entry on its retest;
  stop beyond the head if <= max_stop_pips else the rejection wick); a pending QMR is not replaced by a newer
  continuation level. Settings `entry_models`, `breakout_max_bars`; `entries.model` (schema.sql guarded ALTER via
  PREPARE + `db.migrate`); alert line "PAIR | TF | SIDE | Continuation/QMR | ...". QMRO renamed QMR in docs/notes
  (raw transcripts and frame indexes keep Whisper's "QMRO"). Bias confirmation untouched (slk/story.py unchanged).
  Golden test pins the old entry output with `breakout_max_bars=1, entry_models=[continuation]`. STRATEGY v0.4.
- 2026-10-13: Bias audit (STRATEGY v0.5). `structure.structural_swings` (swing fixed by a close beyond the previous
  opposite swing; HL = lowest close that pushed through the high) now drives trend, HTF trend and targets; point B =
  last order-1 close turn on the confirm TF before the first touching bar (CADJPY 4H replay frame); `sweep_start`
  (wick sweep of the previous origin candle high/low + close back, only where no KL was tapped) via
  `levels.sweep_taps`; new story DEFAULT keys `b_pivot`, `sweep_start` (code defaults, not Mini App settings).
  Telegram bias alert/summary reworded (BIAS, story TFs, BEARISH/BULLISH, level type, status, NO_TRADE reasons).
  Entry `_setup` skips 0.0-pip stops. Golden engine output regenerated for these intended changes (backtest
  numbers change; the backtest workflow reruns on push). New `slk/verify_examples.py` + workflow
  `verify-examples.yml` replays Kevin's CADJPY/GBPJPY/USDJPY/USDCAD/EURAUD/GBPAUD/USDCHF examples on real candles.
  Tests `tests/test_bias_audit.py`.
- 2026-10-13: Bias rules v0.6 (STRATEGY v0.6, REVIEW "Bias rules v0.6"). slk/story.py refactored into `_Ctx`
  (identical v0.5 output with the new switches off, test against tests/golden/engine_golden_v05.json): #26
  `most_recent_level`, #29 `flip_end` (kevin_outcome `ended_flip`, trade outcome `flip`, the opposite story starts
  with rule `flip`), #30 `htf_targets` (W/M levels for D, M for W), #31a `overlap_rule` (+`overlap_tol_pips` 3, TP =
  next KL; v0.5 "weekly target" wording corrected from all-in-1@1599-1617), #31b `alignment_start` (W->D->H4 breaks),
  #31c `cadjpy_exception` (no H4 breakout). Live: status ENDED_FLIP (alert_ended toggle), alert lines "Rule:" and
  "Reason:", summary tags; `bias.rule`/`bias.end_reason` (db.migrate); webapp status filter + rule/end reason shown.
  Golden engine output regenerated for these intended changes (backtest numbers change). verify_examples: CADJPY
  exception + EURGBP overlap examples. Engine ~40% slower (0.55 -> 0.76 s per pair, 3 years, D+W+M). Tests
  `tests/test_bias_rules.py`.
- 2026-10-13: Validation 4 (6dda831, bias rules v0.6). Verdicts: #26 faithful (edge fixed: a newer level closed
  through on the tap bar no longer blocks the older level that held), #29 faithful, #30 partly (higher-TF caps =
  our reading), #31a faithful (TP at next KL 0.8722 confirmed on all-in-1 sheet_026), #31b partly (start, not
  filter), #31c fixed (needs the daily to have flipped first: D close through an opposite level within max_wait).
  Live look-ahead fixed: forming W/M bar treated as closed (overlap, HTF targets) -> nominal close. flip_scan speed
  fixed (memo). Golden regenerated for these three logic fixes only. REVIEW.md "Validation 4".
- 2026-10-13: Cache fix: cancelled runs had saved PARTIAL candle stores and `restore-keys` picks the newest, so jobs kept
  re-downloading and timing out. Now one prefix `candles-v2-`, and every workflow saves only when
  `python -m slk.store --check --start 2018` says the store is complete. Backfill re-runs (push trigger) starting from the
  old caches; live/backtest/examples wait for it via the shared candle cache.
- 2026-10-13: Backfill run 38423241260 finished in 51 min but `--check` said incomplete -> saved as `candles-partial-`.
  backfill.yml now prints ERROR lines and the `--check` result as annotations (logs can't be read from the sandbox); rerun resumes.
- 2026-10-13: New release `SLK-radar-video-and-other-bots-video` (developer's SLK Radar bias-bot walkthrough, Kevin mentee):
  transcribe.yml + extract-frames.yml (10 s, 1280 px) -> knowledge-base/videos|frames/kevin-devt-building-the-slk-bias-bot-*;
  then a validator agent compares its logic to STRATEGY.md -> knowledge-base/study/compare_slk_radar.md.
- 2026-10-13: SLK Radar adoption (STRATEGY v0.7, tests `tests/test_slk_radar.py`), one line per change:
  - Next Day Rule: `story.DEFAULT["next_day_rule"]` flag (default, story key `next_day`) / require (same-day breakout dropped, also in current_tap + flips); setting `next_day_rule` (Bias rules); STRATEGY §2 + §5 #21.
  - Story labels `retrace` (closed back beyond B later on the breakout day; flag only, §5 #22) and `level_time` ("formed"); golden tests compare without these labels (logic unchanged under flag).
  - Alerts rewritten: header "SELL · EURNZD · D1→H4", key level kind/price/formed, rejection candle trading day, breakout candle + B, confirmation close, "Trend aligned with W1/D1", Next Day line, retrace warning, target/invalidation/rule kept, every time labelled open/close; setting `display_tz` (type `tz`, zoneinfo-validated, default Africa/Lagos).
  - Early alert: setting `early_breakout_alert` (off): TAPPED row + closed H4 beyond B inside the open day -> "H4 breakout — waiting for the daily close"; never stored as CONFIRMED; once per story via settings key `early_alerts_sent`.
  - Retrace follow-up alert `RETRACE` when a stored CONFIRMED row turns retrace=1 (toggle `alert_confirmed`).
  - DB: `bias.breakout_time`, `next_day`, `retrace` (db/schema.sql = webapp/schema.sql, `db.migrate`); Mini App bias cards show them.
  - `/terms`: no Telegram update handler existed -> `POST /telegram/webhook` in webapp/app.py (secret header `TELEGRAM_WEBHOOK_SECRET`, owner chat only, reply in the webhook response), glossary `slk/terms.py`; owner setup in webapp/README.md.
  - Entries: setting `entry_alignment` (owner: d_h4 default = D story + last H4 structural break agree; w_d_h4 adds W; off), continuation only, checked per pattern at its breakout close (entry-4@1670-1690, entry3@696-818, weekly-recap@151-282); STRATEGY §3 OUR CHOICE.
  - Backtest: `python -m slk.backtest --variants` (backtest.yml passes it) -> REPORT.md "Variants" (trades, win%, avg R, total R per variant) + `reports/variants.csv`, plus "By story and Next Day Rule"; not run here (no Dukascopy from the sandbox).
