# HANDOVER — read this first in a new chat

Project: Kevin King "SLK" trading bot. Gives **bias** (main goal), then **entry alerts**, later **trades on
IC Markets cTrader (demo first)**. No VPS, no Docker, no MT5.

Repo **`awujo/practicing`** (renamed from `awujo/trading` on 2026-10-15 and made **public** so Actions
minutes are free; owner plans to make it private again after the billing reset on Nov 1), work branch **`claude-kevin-king`** (Claude). `qwen-kevin-king` = Qwen's older attempt,
ignore. `main` = old bot code, don't touch. Owner Telegram chat id: 1410229777.

**Rule for every session:** update this file (Status + Log) in the same commit as any change.

## Architecture
| Part | Where | Runs on |
|---|---|---|
| Strategy (the rules) | `STRATEGY.md` (v0.9) | — |
| Course evidence | `knowledge-base/` (transcripts, frame sheets), `knowledge-base/study/*.md` notes | — |
| Bias engine | `slk/structure.py`, `levels.py`, `story.py`, `candles.py`, `data.py` | — |
| Bias backtest | `slk/backtest.py` → `reports/REPORT.md` | GitHub Actions `backtest.yml` (on push to slk/**) |
| Entry model + backtest | `slk/entry.py`, `slk/entry_backtest.py` → `reports/ENTRY_REPORT.md` | same workflow |
| Live bias runner | `slk/live.py`, `slk/db.py`, `db/schema.sql` | Actions `live.yml`, hourly at :07 (not on the FX weekend) |
| Candle store (H1, incremental) | `slk/store.py` → `data/store/*.npz` in the Actions cache (key `candles-v3-`) | IC Markets cTrader; filled by `backfill.yml` (manual, minutes), kept by live + backtest |
| cTrader client | `ctrader/` (README has OAuth steps) | Actions `ctrader-smoke.yml` |
| Telegram Mini App | `webapp/` (FastAPI), `render.yaml` | Render, branch claude-kevin-king, root `webapp` |
| Shared names (env vars, DB tables) | `CONTRACT.md` | — |
| Code review findings | `REVIEW.md` (incl. "Bias audit") | — |
| Kevin's worked examples replay | `slk/verify_examples.py` → `reports/EXAMPLES.md` | Actions `verify-examples.yml` (push on that file / manual) |

Data: **IC Markets cTrader H1 candles** (bid, UTC; demo account, one connection per job) since 2026-10-14;
Dukascopy only as the fallback when cTrader secrets are missing or cTrader fails (both blocked from Claude's sandbox).
Candles close 17:00 New York. Secrets: `DATABASE_URL`, `TELEGRAM_BOT_TOKEN` (chat id defaults to owner).
Claude cannot read Actions logs (redirect blocked) → workflows write errors as `::error` annotations or into
`reports/run.log`, which Claude reads via the GitHub API.

## Status (2026-10-23)
- [x] Settings full-form save now uses one database connection and one transaction rather than reconnecting/committing for every field. Failed writes roll back the entire form; owner/tenant scopes preserved. Added Deriv full-form save/reload and atomic failure regressions, plus real MySQL owner/tenant coverage. Exact earlier user save error is unconfirmed.
- [x] Investigated Deriv selection error: run39767418604 loaded DVR25 but DVR75 failed with public API RateLimit. Feed now spaces requests3.1s and retries explicit throttles at10/20/40s within300s budget. Settings instrument selector groups brokers and markets into searchable collapsible sections; chosen markets retain selection and counts update. IC categories inferred from symbols; Deriv market categories use API metadata.
- [x] Deriv real-feed and MySQL isolation Actions passed; production live run39757696620 succeeded. News fallback deployment schema now matches canonical schema; legacy regression fixtures updated for multiuser discovery/auth and weekend no-work behavior.
- [x] User explicitly requested public calendar integration: News tab + personal currency/impact filters, daily local-hour summary and ~60min reminders, configurable shared FF weekly JSON cache. Independent5min news.yml and secret-protected /cron/news endpoint; same-secret external1–5min timer recommended because GH schedules are best-effort. Atomic per-user delivery claims, stale/week-coverage safeguards,80s fair batch budget,30day receipt retention, preview-only manual runs. Owner defaults enabled; new users opt in. No AI calls or live strategy rule changes.
- [x] Deriv public feed integrated into selected-only hourly bias+entry pipeline:89 human-labelled choices, DV keys/files and source/pip metadata, UTC closed candles + seven-day week, continuous synthetic/crypto weekend scanning, no cross-provider fallback or broker order approval. Bounded366day warmup uses actual history. Read DERIV.md.
- [x] Future research publication is opt-in: study/history defaults and automatic queue keep research results out of MySQL unless explicitly requested.
- 2026-10-22: Future study workflow defaults and automatic research queue now keep MySQL publication off. Historical replay only launches DB finalization when publish is explicitly selected. This prevents unattended research re-filling user database capacity after archival.
- [x] Archive publication synchronizes the branch before recording its manifest, avoiding handover append conflicts during concurrent documentation updates.
- [x] Requested research DB evacuation: research-archive.yml exports only research_records into per-experiment SQL.gz files + hashes/counts, restores and field-compares in disposable MySQL8, publishes to GitHub BEFORE hash-guarded deletion, preserves unarchived/changed rows, reclaims empty table storage. Publisher/pruner share MySQL advisory lock and workflow concurrency. No user/live data archived/deleted. See research/archive/README.md for source archive coverage and restore instructions.
- [x] Multiuser Mini App: any correctly signed Telegram user can register on opening. New users default EURUSD/GBPUSD/USDJPY, D/W, alerts only; isolated tenant_* tables in same database, independent preferences/biases/entries/trends/runs/notification dedupe. Owner retains legacy tables/history/settings. Nonowners cannot approve broker orders or enable auto_trade; watchlists capped30, empty restores three starter markets.
- [x] Hourly multiuser runner snapshots preferences, downloads combined selected watchlists once, reuses identical strategy calculations, then independently reconciles/sends to each user ID. Manual pair overrides are intersected for nonowners. Owner first; other accounts rotate after12min budget. Existing workflow15min runner/20min job bounds remain; newly selected markets may require initial history warmup. Tenant interruption cleanup and future-column migrations included.
- [x] Multiuser verification: real local disposable MySQL8 idempotent DDL and concurrent signed-API isolation, composite FK cross-user rejection, private digest routing/cooldown; deterministic union-download/cache/settings-failure/SQL-scope tests. No live Telegram test messages sent. Independent reviewer checked isolation and runner design; identified issues resolved before push.
- [x] Mini App private eligible-bias digest button: authenticated recipient only; saved pairs/stories, avoid-pair and NO_TRADE filters, latest-story selection, successful-scan timestamp and two-hour freshness limit. Existing owner-only authentication/shared settings remain; no multiuser preference claim.
- [x] Manual broker-catalogue.yml exports enabled IC Markets demo-account cTrader symbols and broker metadata into data/broker_symbols.json; Mini App pair choices use catalogue when present. Empty selection remains default 28; discovery does not enable every market. Deriv remains a future separate adapter, not connected.
- [x] EURCAD NO_TRADE/target diagnostic: initial1.57728 taken before confirmation; displayed1.57184 is replacement. Preserve target provenance and label alert warning/replacement clearly, without changing entry eligibility. Read research/diagnostics/EURCAD_2026-10-21.md.
- [ ] **Trend entries / Kevin gap / lower-TF discovery** (owner 2026-10-20): plan + results + next steps in
  `research/TREND_LTF_PLAN.md` (start there to continue). Code: slk/trend_study.py, ltf_features.py,
  ltf_discovery.py, kevin_gap.py; research-only story TF `H4` (H4 -> H1) in slk/story.py STORIES. 8-pair local
  result confirmed on 28 pairs 2018-2025: no edge after costs; H1-close confirmation after the touch beats the
  blind limit (about -0.12R vs -0.2..-0.58R); trend filters add nothing; the only "held" rule is a rollover-hour
  (21-22 UTC) artefact. Independent verifier: no look-ahead, outcomes recomputed OK. Nothing live changed.
- [x] Successive bias-target measurement: research/results/2026-10-20-bias-targets/ANALYSIS.md. Direct frozen target-1: D806/1393, W114/243; after another completed continuation break, target-2 D457/626 selected, W30/62. Missing target/confirmation and unfinished paths are separate; these are a native-derived research ladder, not previously broadcast target forecasts.
- [x] Full-history review completed: research/results/2026-10-20/ANALYSIS.md. All 28 archives/560 ledgers analyzed; 30,760 events. Daily direction near neutral; post-stop recovery common, but no profitable tested entry variant. Weekly 24-real-hour entry clock misses next session; tiny-stop/rollover gap assumptions materially affect R. No live promotion.
- [x] All 28 full-history studies succeeded in run 39296129468; only monolithic 60-minute database publication timed out. Resumable finalization now saves combined analysis first and self-dispatches short checkpointed publication slices, reusing saved archives and skipping existing records.
- [x] Expanded research scenarios and full frozen-history workflow implemented: post-stop 24/72h paths, re-entry, old/new native Daily/Weekly stories, confirmation delay, stops/targets/exits/cost/context alternatives. See research/SCENARIOS.md for actual coverage, limits and budgets. No M5 reconstruction/live changes.
- [x] All 28 FX research pairs completed; full evidence review in research/results/2026-10-19/ANALYSIS.md. 828 events, 200 distinct completed baseline units, 18 new entry confirmations; negative descriptive directional results, all per-pair discovery screens insufficient. No winning policy/live change.
- [x] Research automatic queue: manually start research-queue.yml to process all 28 FX pairs in batches up to four, two attempts per pair maximum, 150-minute coordinator budget, completion artifact. No AI calls or live strategy changes.
- [x] Next research phases: manual bounded multi-pair history/replay workflow, lifecycle alternatives, experimental prefix-only entry variants, shallow training-only screening and research_records MySQL persistence. Read research/STATUS.md for scope/limits; no live trading changes, no ANN or validated edge claims.
- [x] Research phase 1: manual offline infrastructure workflow, bounded frozen-input diagnostics, integrity-checked local checkpoints, planned study catalogue. No strategy evaluation/ANN/DB writes/broker calls. See research/README.md and research/DESIGN.md.
- [x] Continuation alerts exclude forming confirmation-timeframe candles (closed H1 does not imply closed H4). Candle completion clock now uses actual New York shifted wall time, including DST.
- [x] Missing cTrader symbols no longer trigger multi-year fallback rebuilds in hourly jobs. Interrupted jobs are finalized by workflow cleanup; old unfinished runs display interrupted after 30 minutes. Runner step has 15-minute timeout inside 20-minute job budget; failure alerts include cancellations.
- [x] Mini App settings save fixed: flip_max_age now has numeric bounds; all fields and alert toggles covered by API regression tests. Non-finite numeric input returns 422.
- [x] Repo public as `awujo/practicing`; live run works again (minutes were exhausted). Render: check the repo link
      shows `awujo/practicing`. Back to private on/after Nov 1, then hourly live costs minutes again.
- [ ] **Entry model re-test** (owner asked): fills/exits on M5 instead of H1 (34% same-H1-bar stops), Kevin's own
      trades in the example check (entry/stop/TP R), break-even after TP1, H4 level + H1 breakout entries, drop the
      misleading bias "trade view" R (0.34R target vs tap-wick stop is not a Kevin trade).
- [x] **Data source = IC Markets cTrader** (store, backfill, live, backtest, verify-examples); Dukascopy = fallback.
- [ ] **User, once:** Actions → "SLK candle backfill" → Run workflow (start 2018, pairs empty). Expected a few minutes;
      per-pair bar counts appear as `::notice::` annotations, the store check as "Store check". Old Dukascopy caches
      (`candles-v2-`) are not used any more.
- [x] Strategy studied: all 29 transcripts + all ~700 frame sheets. STRATEGY.md v0.3.
- [x] Bias engine, entry model, live runner, cTrader client, Mini App — all built, tests pass (`pytest -q tests`).
- [ ] **Backtest results on real data** — run in progress (28 pairs, 2018–2025). Read `reports/REPORT.md` when committed.
- [ ] **Live runner** — fails: Aiven `Access denied` → user must fix the password in GitHub secret `DATABASE_URL`.
- [x] Code review done (`REVIEW.md`): 9 fixed (incl. look-ahead in story backtest, HTF filter now applied), 30 open.
- [x] Default branch is `claude-kevin-king` (set 2026-10-13): hourly cron + manual Run buttons work.
- [ ] Render deploy of Mini App (user: set branch + root dir + 2 env vars).
- [x] cTrader: IC Markets demo works (ctrader-smoke green; secrets CTRADER_*; tokens refresh into DB `settings`).
- [x] M/W conflict enforced in live runner (D stories NO_TRADE, no TAPPED/CONFIRMED alerts) and stored in
      `bias.no_trade` / `no_trade_reason` (Mini App shows a NO_TRADE tag). Backtest applies `story.apply_mw_filter`:
      NO_TRADE D stories are not scored; REPORT.md section "M/W conflict filter" shows all vs kept vs removed.
- [x] **Efficiency** (Actions minutes): candle store in the Actions cache, each hourly run downloads only the new
      bars (~1 file per pair instead of ~26-35); engine output cached per story until a new origin bar closes;
      pairs computed in a process pool; engine hot spots removed (identical output, golden test). No scheduled
      runs on the FX weekend except the final one after Friday 17:00 NY. Hourly target 1-3 min.
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
- [x] **Entry diagnosis (cTrader data)** (REVIEW.md): 3 entry bugs fixed (stop inside the level zone, entries after a
      flip-ended story, QMR head look-ahead) + `spread_pips` option. After the fixes the entry model is ~random
      (8 offline pairs: TP1 29% / −0.21R vs random entries 32% / −0.15R): **no edge, do not trade entries live yet**.
- [x] Kevin's examples diagnosed on offline cTrader candles (`python -m slk.verify_examples --data data/examples`):
      6/9 -> **8/9 PASS** after the owner decisions of 2026-10-14 (next_day_rule require, trend_mode leg); open:
      USDCAD (on IC the W closed above its last A-shape, so W is up under the leg rule). REVIEW.md "Examples
      diagnosis (cTrader data)" + "Owner decisions 2026-10-14". Owner: check `pullback_levels` and `trend_mode` in
      the backtest Variants.
- [x] Owner decisions 2026-10-14: `next_day_rule` = require, D-story entry TFs = H4,H2 (no H1, alert-only),
      `trend_mode` = leg (Kevin's weekly BOS = close beyond the last V/A of the leg, all TFs).
- [x] **Paper results of entries** (2026-10-14): the live job tracks every filled entry on closed H1 candles with the
      entry backtest's rules (`slk.entry.paper_track` = `simulate` code) -> `entries` TP1_HIT / TP2_HIT / SL_HIT /
      EXPIRED + `filled_at`, `result_r` (TP1 exit), `result_r_tp2` (hold for TP2), `hit_price`, `closed_at`
      (`db.migrate`); Telegram "✅ TP1 hit · EURUSD H4 BUY · +1.6R" / "❌ Stop hit · … · -1R" once each; Mini App
      Entries "Paper results (signals)" summary (`/api/entries/summary`). Signals only, not broker trades (`orders`).
      **Owner:** Render redeploy (Manual Deploy) to get the new Entries tab; the columns appear on the next live run.
- [ ] Ideas not built: Mini App page to paste cTrader tokens into DB;
      HTF-agreement filter in live runner.

## Next steps (in order)
0. Run "SLK candle backfill" once (see Status; cTrader now, minutes).
1. Fix `DATABASE_URL` → rerun "SLK live bias" (Actions → Run workflow, or Claude dispatches it via API).
2. Read backtest reports; tune `slk/story.py` DEFAULT / entry DEFAULT by results (out-of-sample years).
3. Deploy Mini App on Render, set BotFather menu button to the Render URL.
4. Entry alerts live → then demo trading with kill switch + confirm button.

## Log

### 2026-10-20 — trend entries, Kevin gap, lower-TF discovery
- Owner: test trend entries, find why the bot misses Kevin's trades, and let an agent look for a
  lower-TF confirmation that raises the win rate / reward; write it down so other agents can continue.
  research/TREND_LTF_PLAN.md (plan, results, next steps), research/KEVIN_LTF_CUES.md (study agent: Kevin's
  lower-TF cues with sources; M15/M5 not needed, "90% of entries from 4H/2H", no sessions / FVG). New
  slk/trend_study.py (H4 stories + every Kevin continuation level on H4/H2/H1, limit vs H1-close confirmation,
  1/2/3/5R + MFE), slk/ltf_features.py (entry features from closed candles only), slk/ltf_discovery.py
  (train-chosen / test-checked screening), slk/kevin_gap.py -> reports/KEVIN_GAP.md. backtest.yml step runs the
  28-pair version. tests/test_trend_study.py.
- 28-pair results + verifier-agent audit in research/TREND_LTF_PLAN.md. Fixes: h1_confirm stop cap 25 pips,
  stricter "holds", chance-level shuffles in LTF_DISCOVERY.md.

### 2026-10-19 — next-phase research verified on GitHub
- Corrected run 39251591881 succeeded end to end: frozen input restore, 55 tests, two-pair replay, entry experiments, artifacts and batched MySQL publication (575 records). Reports inspected: USDCHF 45 events and GBPCHF 36 over 90 H4 decision points each; one eligible confirmation each, four entry variants each. Discovery returned insufficient_data (8/11 baseline development units, below 30), no selected rule. These small exploratory results do not establish an edge. Run URL: https://github.com/awujo/practicing/actions/runs/39251591881 .

### 2026-10-19 — research pending adapter and bounded publication
- Initial real two-pair run 39250967333 succeeded: USDCHF 45 events/90 H4 observations, GBPCHF 36/90; 575 research records published. Follow-up replaces the full-history finder terminal-horizon assumption with a prefix-only prospective pending adapter; a real pattern fixture confirms pending detection before retest, with consistent 1-pip ask/bid treatment. Publication batches 100 records with immutable hash verification. Fresh replay can reuse frozen inputs after code changes without reusing incompatible ledgers.

### 2026-10-19 — next research phases
- Owner requested next phases. Added separate study workflow with shared broker acquisition lock, standard 28-pair queue in 1..4 batches, 1200-day exports/21-day evaluation, resumable exact artifacts and optional research-only publication. Offline as-of replay uses code-default config, not Mini App settings, at H4 closes. Four lifecycle alternatives, conservative H1 execution of four entry variants, exploratory chronological screening. SQLite transaction checkpoints and immutable/versioned MySQL research records.
- Independent reviewer caught/fixed actual confirmation-close timestamp semantics, fresh-story eligibility, resource/manifest validation, incomplete entry-search censoring and mutable discovery publication. Coverage and assumptions in research/STATUS.md. No production strategy/alert logic changes. Validation: 55 focused research checks passed, including real-engine timestamp/prefix fixtures, conservative execution/censoring and idempotent research-only publication.

### 2026-10-19 — research infrastructure pilot
- Owner approved reviewed staged design and independent review agent. Added slk/research.py, manual-only research.yml and research docs. Strict OHLC/UTC/size/window validation, H4/D/W completion diagnostics (including DST), atomic local checkpoints tied to data/code/runtime identity, explicit insufficient-evidence status. No live strategy/settings changes, secret access, trading, data acquisition, schedules or LLM calls. Strategy/lifecycle studies remain planned until prefix-replay validation.
- Tests: 22 research checks passed; independent reviewer inspected logic and workflow. Artifacts expire after 30 days; local checkpoints are not durable cross-run storage. Hard-kill lock recovery documented.

### 2026-10-19 — continuation alert before candle close
- Owner received a continuation at 09 WAT describing a 10 WAT H4 close. Filter continuation inputs by the confirmation timeframe, and correct drop_forming shifted-clock calculation. Regression coverage checks before/exactly at/after H4 close in summer and winter, plus pair_state integration. Validation: 36 live/continuation/efficiency tests passed.

### 2026-10-19 — hourly runs timing out
- Actions logs: NAS100/SPX500 unavailable on account, Dukascopy history rebuild exceeded 20 minutes before engine/alerts. Skip unavailable symbols with explicit pair errors, continue supported pairs. Workflow records interrupted run IDs and alerts on cancellation; UI labels stale runs interrupted. Validation: 67 tests passed (cTrader store, efficiency, webapp, live); JS syntax checked.

- 2026-10-18: Telegram wording only: SELL rejection closes back below the level, BUY above (headline and story step). PLAN distinguishes waiting for the lower-TF external break from waiting for the origin-TF confirmation close. Existing sections and strategy rules unchanged.
- 2026-10-18: Settings save feedback moved beside sticky Save button (saving/saved/error/unsaved states). Disable native form validation (server validates all fields), retain unsaved edits across tabs, verify saved values with a fresh GET, and version static asset URLs to refresh Telegram caches.
- 2026-10-18: Owner still saw settings-save 500 at slk-backtest-viewer.onrender.com after 638db9c. First fix changed only shared slk code/tests/docs; Render root is webapp, so auto-deploy may have skipped it. Added public /version with RENDER_GIT_COMMIT and settings validation marker to identify deployed code and trigger a webapp deploy. /healthz unchanged.
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
- 2026-10-13: Validation 5 (SLK Radar adopt, 7cba861): fixed entry alignment counting a still-forming H4 bar in live and `breakout_time` missing from the row compare (CADJPY rows); rest OK (REVIEW.md "Validation 5"); 180 tests pass.
- 2026-10-13: Backfill 38430625294 got 0 bars for all 28 pairs: Dukascopy 503/timeouts and one failed month threw away the
  whole pair. store.update now skips a failed month (retried next run), saves every 6 months and in `finally`;
  data._get honours SLK_MIN_GAP (backfill: 1 s, 2 threads), backoff capped at 60 s. Test tests/test_store_progress.py.
- 2026-10-13: Commits 7cba861 (SLK Radar adopt: next_day_rule, alert format, display_tz, early alert, retrace, /terms,
  entry_alignment d_h4 default, backtest --variants) + 52102a7 (Validation 5 fixes). Backtests cancelled until the store is complete.
- 2026-10-14: **cTrader = primary candle source.** Dukascopy throttled runners (a 4h45m backfill got 3/28 pairs); the
  IC Markets cTrader demo works (smoke OK). `slk/store.py`: source per file (`meta.src`, a file of another source is
  rebuilt, never mixed; v2 files = Dukascopy), one `CTraderClient` per job for all pairs (`get_feed`, symbols in one
  request, worker processes never connect), completed months fetched in as few requests as possible (consecutive
  missing months grouped up to the 35-week H1 window, saved after each request) and tagged final (MONTH), current
  month refreshed (CUR, last 3 days re-fetched). Bars: hour-aligned, volume > 0, outside the FX weekend. Fallback:
  cTrader failure (or no secrets) -> Dukascopy per pair with a `::warning::`; for a cTrader file only the gap after
  its last bar, into `data/store-fallback/` (this run only, read by `store.recent`). `ctrader/client.py`:
  `trendbar_rows` (API-max windows, INCORRECT_BOUNDARIES halving, truncated-reply completion, 0.25 s spacing +
  backoff on REQUEST_FREQUENCY_EXCEEDED). Cache key `candles-v3-` everywhere, `--check --source ctrader`, backfill
  progress `partial-candles-v3-`; v2/partial Dukascopy caches never restored. backfill.yml: manual only (push
  trigger removed), 60 min, cTrader + DB secrets, per-pair `::notice::` (7 pairs per notice: GitHub shows 10 per
  step). live/backtest/verify get the cTrader + DB secrets (refreshed tokens persist in DB). New setting
  `level_tol_pips` (0-5, default 0 = unchanged, golden-tested): extra wick tolerance for broker differences (IC vs
  FOREX.com vs OANDA), wick tests only, never closes / B breaks (STRATEGY §5 #25). Tests `tests/test_ctrader_store.py`,
  `tests/test_level_tol.py`, `tests/conftest.py` (no network: Dukascopy fakes, cTrader connections blocked).
- 2026-10-14: Entry diagnosis (REVIEW.md "Entry diagnosis (cTrader data)", STRATEGY §3 steps 5-6 + OUR CHOICE rows).
  Reproduced ENTRY_REPORT's 21-23% TP1 on the 8 offline pairs, inspected 17 trades bar by bar. Fixed in slk/entry.py:
  E1 stop beyond the whole invalidation zone c1..breakout-1 (was c3.. only: stops inside the A/V shape, median 5.9 pips,
  down to 0.2), rejection candle only when the zone > max_stop_pips (`stop_at`); E2 no entry after the story's
  `end_time` (flip #29 was ignored: 14% of fills); E3 QMR known only once the head pivot is confirmed (`qm_known`);
  E4 `spread_pips` (default 0). ENTRY_REPORT gets `fillbar_stop%` and a stop-placement section. 8 pairs: TP1 21.4% /
  −0.42R → 29.4% / −0.21R; random-entry baseline 32.4% / −0.15R → model has no edge (losses = the fill bar, 39% of
  fills stopped within the filling H1 bar). Golden entry test pinned with `stop_at=rejection, story_end=False`
  (golden JSON unchanged). Tests in tests/test_entry.py.
- 2026-10-14: Examples diagnosis (STRATEGY v0.8, REVIEW "Examples diagnosis (cTrader data)"): verify_examples `--data`
  (offline CSVs in data/examples); 3/9 -> 6/9 PASS. Rule changes: `pullback_levels` (D against W = retracement, W-side
  levels; setting + backtest variant), `cadjpy_zone` (exception only for the OC level of the zone the daily just
  flipped: 22% -> 2.5% of D stories), `tap_tol_pips` 1 -> 0 (wick must reach the line), `align_retap_ends`. Specs:
  EURAUD window after the W BOS (Jan 24), CADJPY exception example accepts the H4 path, NO_TRADE check also fails a
  story confirmed inside the window. Golden regenerated for these four only (`engine_golden_v07.json` = before,
  reproduced with `PRE_EXAMPLES`). Tests `tests/test_examples.py`; 207 pass. entry files untouched.
- 2026-10-14: Owner decisions (STRATEGY v0.9, REVIEW "Owner decisions 2026-10-14"): (1) `next_day_rule` default
  require (backtest: next-day breakouts +43.6 R vs same-day −188.3 R; require −33.2 R vs flag −160.4 R); (2) D-story
  entry TFs H4, H2 only, no H1 (entry-2@668-713, entry3@2011-2016; TP1 H4 −0.01 / H2 −0.15 / H1 −0.24 R), alert-only;
  (3) new setting `trend_mode` (default leg): structural swings from V/A-shape turns (order level_pivot 1) instead of
  order 2, on all TFs, ERL targets unchanged (weekly-recap@343-376, F sheet_005/008; basic-ms-pt3@875-1211). Examples
  offline 6/9 -> 7/9 (require) -> 8/9 (leg: EURAUD/GBPAUD sells pass, USDCAD fails). 8 offline pairs (require):
  leg −10.6 R vs protected −40.4 R. Backtest variants + `trend_mode`, `entry_tfs`. Goldens pinned via config
  (tests/engine_golden.py PIN / OLD_ENTRY), no golden regenerated. 213 tests pass.
- 2026-10-14: Owner decisions live (3e78108): CI backtest D 5186 stories 80.1% win, kevin_target 82.5%; examples 8/9 on CI (USDCAD fails under trend_mode leg). verify-examples now reruns when the bias engine changes.
- 2026-10-14: Gold alert check (REVIEW "Gold alert check" G1-G4): cTrader client raises error replies without our
  clientMsgId / disconnect events instead of timing out, timeout text lists what arrived, exact symbol name +
  candidate ids, NO_TRENDBARS_REPLY on a live link; smoke prints symbol ids/pip and probes; per-symbol pip and
  decimals `slk/instruments.py` (cTrader pipPosition, else XAUUSD 0.1, XAGUSD 0.01, indices 1.0; STRATEGY §5 #28);
  Dukascopy XAGUSD/indices scale + names; `python -m slk.debug_pair` (debug-pair.yml: cTrader, else Dukascopy +
  point B explanation). B 4171.50 = Dukascopy feed × "last A before the FIRST touch" (rule unchanged); target =
  nearest rule. Dispatch: ctrader-smoke symbol XAUUSD, debug-pair XAUUSD.
- 2026-10-14: Paper results for entries. `slk/entry.py`: `simulate` split into `_horizon` / `_leg` / `_close_r`
  (identical output, golden tests) + `paper_track` (live outcome of one filled entry, same rules: closed H1 bars
  from the fill bar, same-bar stop+TP = loss, fill bar stop-only, no breakeven, `max_trade_bars` entry-TF bars).
  `slk/live.py`: entry rows carry `filled_at` (engine `fill_time`; old TRIGGERED rows get it on the next run),
  `cancel_entries` (PENDING of an ended story -> CANCELLED, entry `story_end` rule), `track_entries` (TRIGGERED /
  open TP1_HIT rows only, events already implied by the stored status dropped), `format_result_alert`; main writes
  each outcome with `db.update_entry_result` (guarded `WHERE status=old AND closed_at IS NULL`) BEFORE sending, so
  an alert is never repeated. Schema: 5 `entries` columns (db/schema.sql = webapp/schema.sql, `db.migrate`).
  Mini App: `/api/entries/summary` (owner auth; SELECT * so it works before the migration), status filter with the
  new statuses + `closed`, outcome tags, R, filled/closed times, "Paper results (signals)" card. Win = TP1 reached,
  so win% and total R match the backtest's TP1 row; TP2 R shown separately. Tests `tests/test_paper_results.py`.
- 2026-10-15: Repo renamed `trading` -> `practicing` and made public (free Actions minutes until Nov 1). Live run
  dispatched and succeeded. Owner challenged entry results (0.34R bias trade view, break-even entries): plan = M5 sim,
  Kevin-trade check, BE after TP1, H1 trigger entries.
- 2026-10-15: Entry stop diagnosis (REVIEW "Stop size"): tiny stops (<=5 pips) lose in the fill hour. New
  `entry.DEFAULT["min_stop_pips"]` (0 = off) and `entry_backtest --variants` -> reports/ENTRY_VARIANTS.md
  (backtest workflow runs it). Earlier claim "34% fill-hour stops = H1 too coarse" was wrong: those are real losses.
- 2026-10-15: Owner: "until the backtest gets Kevin's stop/entry and reproduces his examples, the system is not
  modeled". min_stop 8 default NOT adopted (reverted; option stays, default 0). ENTRY_VARIANTS.md: min stop 8 helps
  a little, every variant still <= 0 R with 1-pip spread. New `tests/kevin_trades.json` = Kevin's dated trades
  (EURAUD H4 sell 17 Feb 2026, GBPAUD 2H sell 19 Feb, USDCHF 1H buy 21 Jan, EURGBP 4H sell 2 Feb / buy 15 Jan,
  USDJPY 1H buy 12 Dec 2025). Bot vs Kevin, EURAUD: story level 1.68095 = Kevin's A-level (ok), B 1.67396 break
  17 Feb 18:00 (ok) but story TARGET 1.67211 (5 pips past the break) is hit 18 Feb 02:00 -> story ends -> NO entry.
  Kevin's TP = 1.6620, "this low before I target the weekly key level" (the low the pullback started from).
  Open question to owner: target = that leg low (ERL) instead of the nearest small level?
- 2026-10-15: `story.DEFAULT["target_mode"]` = leg (Kevin's ERL target), Mini App setting + backtest variant.
  Examples 7/9 (CADJPY Feb 2 = same BUY bias from the Jan 26 story). REVIEW "Targets vs Kevin". Next: QMR entry
  = limit at the H4 neck (Kevin's EURAUD 17-18 Feb), stop 15-20 pips; `slk/verify_trades` vs tests/kevin_trades.json.
- 2026-10-15: Friendly dates (owner request): Telegram `live.fmt_time` and Mini App `dt()` show "Today, Thu 15 Oct
  10:00", "Yesterday, ...", "Monday, 12 Oct 22:00", "Last week Monday, 5 Oct 22:00", far away "Mon 28 Sep 22:00"
  (+ year if not this year). DB sessions forced to UTC (`SET time_zone = '+00:00'`). Render needs a redeploy.
- 2026-10-15: `entry.DEFAULT` qmr_entry (trigger | neck) + qmr_stop_pips 18 (Mini App "Entry rules"); entry
  variants "qmr neck". `slk/verify_trades.py` -> reports/KEVIN_TRADES.md (trigger 0/6) and reports/neck/ (1/6:
  EURAUD exact). REVIEW "Kevin's trades replay" lists why the other 5 fail. Test test_kevin_euraud_qmr_neck_trade.
- 2026-10-15: Live check: (1) every live run since 14 Oct processes only XAUUSD ("pairs ok 1") = Mini App setting
  Markets → Pairs is "XAUUSD"; owner to clear it (empty = all 28). (2) GitHub "hourly" cron fired only every 4-5 h
  (13-15 Oct), up to 56 min late. Fix: Render endpoint `/cron/tick` (CRON_SECRET) dispatches live.yml with
  GH_DISPATCH_TOKEN (fine-grained, Actions r/w on this repo); cron-job.org calls it hourly. Steps: webapp/README.md
  "Hourly tick". live.yml input tick=1 obeys FX hours. Entry alerts stay on (alert_entry) + paper outcome tracking.
- 2026-10-15: Owner checked EURGBP on the chart: "tap Tuesday" but no KL there. Findings: (1) the D candle that opens
  Tue 22:00 WAT is Wednesday's; the Mini App now shows "Tap candle: Wed 14 Oct (D1 candle)" (NY 17:00 trading day,
  `candleDay` in app.js). (2) The level 0.84614 "flip" was a Jun-2024 OC level on its 7th flip: new `flip_max_age`
  (default 100 bars of the level's TF, 0 = old no-limit; Mini App Bias rules; examples 7/9 unchanged; backtest
  variant added). (3) The owner's line 0.84738 (A, candle Thu 8 Oct) IS the bot's level for Thursday's tap, but an
  H4 closed below point B 0.84547 the same day, so `next_day_rule` require drops it (Kevin's Next Day Rule).
  New stored labels (db MIGRATIONS + schema): `level_src` (A/V/OC, kept by flips; "V-shape KL (flipped)"),
  `level_candle`, `chain` ("W1→D1→H4" when the higher-TF trend agrees, used in the alert header and card title).
  `/api/bias` shows only the watched story TFs (Settings → Markets → Stories); old M rows stay in the table.
- 2026-10-15: Standing bias (owner: "a bias remains a bias until proven otherwise", validated in Kevin's transcripts,
  STRATEGY row 16c). `slk/standing.py` (stdlib): bias per pair + story TF from stored rows; TARGET_HIT / CANCELLED
  keep it, an opposite confirmed story changes it, INVALIDATED / ENDED_FLIP end it. Alerts get a line
  (continuation / BIAS CHANGE / "Bias stays BULLISH" on target / no bias after invalidation, `live.bias_notes`),
  daily summary lists it, Mini App Bias tab "Current bias" (`/api/bias/state`). M stays a setting (Markets →
  Stories). Not yet: entries during a standing bias after the story's target (needs a new level/target rule).
- 2026-10-15: GBPJPY had W BUY + D SELL both CONFIRMED (owner). `htf_filter` only checks the W swing trend; new
  `htf_bias_filter` (default on, Mini App Bias rules) = D against the standing W bias (W against M) -> NO_TRADE,
  chain label from the standing bias (`live.mark_htf_bias`; `state_stories` adds the higher TF). Examples 7/9 same.
  Stale CONFIRMED rows the engine stopped reporting (e.g. CADCHF flip after flip_max_age) -> CANCELLED quietly
  (`standing.DROPPED`, no bias).
- 2026-10-15: Owner disagreed (GBPJPY weekly is bearish; a D->H4 sell under a W buy is a retracement, show D1->H4,
  don't block). Fixed: `htf_bias_filter` default OFF; chain label back to the W structure trend; new `trend` column
  (origin-TF structure at the tap) -> "Pullback" label in alert + card; pullback stories don't set the standing bias;
  standing bias uses the TF structure trend now (`story.tf_trend`, table `tf_state`, written each live run, read by
  `/api/bias/state`). GBPJPY: W BEARISH (structure) + W BUY pullback active, D SELL W1->D1->H4.
- 2026-10-16: EURCHF (owner chart): only "TARGET HIT" arrived (runs every 4-5 h until the cron-job.org tick is set;
  confirmed + target between two runs) -> reconcile now sends CONFIRMED ("_late") before the outcome. Target bug:
  target set beyond the confirmation close although a wick had already traded through it -> `target_unswept`
  (default on, backtest variant). New continuation breaks (STRATEGY 16e): `live.continuation_breaks`, column
  `bias.cont_breaks` ('level@time;...'), CONTINUATION alert (`alert_continuation`), Mini App card list.
- 2026-10-16: NZDJPY (owner): one H4 close through 4 small V's was listed as 4 "NEW" breaks (read as a repeat) -> one break per candle ("cleared 4: 88.501 → 88.428"); the same break on two stories of a TF is sent once. After TARGET HIT the story is watched (STRATEGY 16f): breaks beyond the target = continuation (next liquidity), an origin close back through the level = "STORY LINE ENDED" (new column bias.line_end, migration; standing bias ends). TARGET HIT alert says what is next. Mini App card shows it. First run after deploy may send a few post-target continuation alerts (fresh breaks only, last 36 h).
- 2026-10-16: owner unticked M but alerts still used the monthly (M/W conflict NO_TRADE on D stories, M trend
  filter / pullback / MN1 chain for W stories, M levels as higher-TF targets). New cfg `use_monthly` (= "M" in
  settings `stories`, set by live.build_cfg): off -> M is not computed (state_stories), no M/W conflict, W stories
  have no higher TF in the engine (story._Ctx htf None, no M in HIGHER_ALL). Engine digest changes, so W stories
  are recomputed on the next run; a W story kept only by the M filter can now appear.
- 2026-10-16: owner: bias messages unreadable (one long block, every break listed). `format_alert` rewritten in
  sections: headline + one plain sentence / KEY LEVEL (A / V / OC named and explained, line candle, flipped) /
  STORY SO FAR (numbered: rejected, external break, confirmed, continuation, target, after the target, line end;
  times on their own line) / CONTEXT (higher-TF trend, own structure / pullback, Next Day Rule, retrace, rule) /
  PLAN (target, invalidation, what next). New setting `alert_detail` short (default: breaks as count + latest) /
  full (every break, candle open+close).
- 2026-10-16: owner (AUDUSD): selling after the external range liquidity (the target) was already taken is late.
  Backtest split (target_unswept=off): 1611 such stories (wick took the target between breakout and confirmation).
  target_unswept=on -110R, skip -80R -> new `erl_taken_no_trade` (on): story flag `erl_taken`, live row
  NO_TRADE (reason live.ERL_TAKEN), still alerted as bias with "NO_TRADE: ... late", no entries.

- 2026-10-18: Fixed settings-save HTTP 500: the browser submits all fields, but flip_max_age lacked min/max, causing KeyError during validation even when only alerts changed. Added bounds 0–10000 (0 still means unlimited), rejected non-finite numbers before integer conversion, and added full-form save/reload plus every-setting roundtrip tests. Kill switch verified to remain a string choice (off/on).

- 2026-10-19: Added deterministic research queue coordinator and workflow, correlated dispatch IDs, explicit completion tracking and bounded retries. Existing first four-pair run can be adopted. Publication failure leaves pairs unfinished. GitHub Actions minutes apply; no resident AI checker.

- 2026-10-19: Inspected all seven batch artifacts and 28 SQLite ledgers; committed combined analysis, pair table and descriptive JSON. Continuations dominate (154/200 canonical units post-target), H1 entry variants each six closed cases with four ambiguous hourly stop/target bars; no reliable timeframe/policy selection. No extra run dispatched.

- 2026-10-19: Owner authorized adding the scenario catalogue and testing. Added sidecar immutable scenario ledgers, full ~835-day native D/W replay in <=10 windows per pair, bounded two-worker workflow, seven-day compressed archives, research-only publication payload cap and deterministic combined analysis. Independent review corrections tested; full-history results must be checked before conclusions.

- Validation: 80 research tests passed, independent checker completed; real 90-day EURUSD native replay completed in ~41s (189 events), expanded sidecar in ~18s (243 records). Historical full-run completion/results are pending; do not infer all scenarios profitable or every date gap-free.

- 2026-10-20: Owner noticed cancellation. Confirmed all 28 study matrix jobs succeeded, 28 archives saved; persist job hit configured 60-minute timeout, not a four-hour overall GitHub limit. Replaced monolithic finalizer with research-finalize.yml (15-minute jobs, 420-second/four-ledger work slices, immutable checkpoints, automatic next dispatch, two-error retry bound, storage-cap stop). Combined analysis is uploaded before DB work. Publisher now validates/skips existing hashes instead of reinserting every record. No studies rerun, no live changes.

- 2026-10-20: Reviewed complete ~835-day D/W study independently of incomplete DB copying (406/560 at payload cap). Downloaded all archives, checked matched stops, post-stop paths, re-entry returns, ambiguity, calendar-year behaviour and every pair. Committed evidence and reproducible analyzer; no new study/live-rule changes.
- 2026-10-20: `close_at_target` (default on, STRATEGY 16g): story done at its target, standing bias ends
  (standing.TARGET_DONE), no post-target continuation / LINE_END alerts, TARGET HIT text says wait for the pullback
  and a new story. standing(..., close_at_target) also used by summary, bias notes, mark_htf_bias, /api/bias/state.
  Backtest REPORT adds "new story after a target, same / other side" under next_day_rule=require.

- 2026-10-20: Owner requested bias targets and continuation, not entry TP1. Added causal native-derived target ladder up to five stages, two timing modes, gap/ambiguity/window censoring and direct primary target checks. Measured all28 frozen inputs offline. Preserved per-story records and denominators; no live rules or DB budget changes.
- 2026-10-20: `slk.leg_backtest` (backtest.yml step, reports/LEG_REPORT.md + leg_trades.csv): D stories traded with
  H4 swing stops (6/12 bars, min width) vs the tap-wick stop; and the 1st / every H4 continuation break after the
  target (entry H4 close, next target by the native ladder rule). 1.2 pip cost, stop first, 20-day cap.

- 2026-10-21: Checked Claude pushes (close_at_target, leg/target research, trend studies), fast-forwarded branch and exported fresh EURCAD cTrader history. Reproduced owner story at 20Oct21UTC: initialtarget1.57728, preconfirmationlow1.57404, replacement1.57184. Fixed contradictory alert wording using label-only metadata. Existing erl_taken_no_trade rule remains; no live strategy change. Added BUY/SELL formatting and real EURCAD regressions; golden comparisons ignore only new metadata fields.

- Validation for EURCAD warning fix: 57 targeted live/continuation/bias/golden/target tests passed, including the real exported EURCAD case. Strategy outcomes unchanged; only target provenance and alert wording added.

- 2026-10-22: Added requested private eligible-bias snapshot button and IC Markets symbol catalogue exporter/workflow. No manual Telegram message sent during implementation; delivery happens only on authenticated button POST. 69 web/settings tests passed, including recipient isolation, stale-scan rejection and no resurrection of ended/blocked stories. Broker discovery is account-specific, not an assurance every listed instrument has sufficient candle history or validated strategy performance.

- 2026-10-22: Added broker-symbol search to keep expanded settings usable on phones. Catalogue refresh workflow also records its publication in this log.

- 2026-10-22: First catalogue export authenticated and completed; publication hit ignored data/ path. Fixed publication to explicitly stage only the generated catalogue file.

- Broker catalogue refresh: exported enabled cTrader account symbols; saved selections and live strategy unchanged.

- 2026-10-22: Broker refresh run39746126675 succeeded, exporting177 account symbols (USTEC/US500/UK100 confirmed). Updated former fixed28-choice UI regression to check catalogue count and preserved FX choices; web/settings suite passes with actual catalogue installed.

- 2026-10-22: Owner requested multiuser access with independent watchlists, not scanning all177 symbols. Added slk/tenancy.py and scoped same-DB tenant tables alongside untouched legacy owner tables; signed async request scope, user registration and independent settings. Three starter pairs for new users; private digest30s cooldown, tenant entries/paper outcomes and status; broker actions stay owner-only. Live runner fetches union once, snapshots settings and memoizes identical strategy results, preserves per-user alert dedupe and recipient IDs. Independent review caught composite-FK, cleanup, fairness and failure-fallback concerns; fixed and verified using disposable MySQL8 with concurrent users. Token/API keys remain server-side; no Deriv integration.

- Validation: 103 tests passed, including real MySQL8 concurrent tenant endpoints and foreign-key rejection. multiuser-check.yml repeats these checks in GitHub Actions against a disposable MySQL service, without production secrets or Telegram sends.

- 2026-10-22: User authorized archiving experiments to GitHub then removing only their DB copies to reserve user capacity. Added research_archive.py + manual bounded archive workflow, independent reviewer, SQL-byte-preserving hex dumps and disposable-MySQL roundtrip proof, remote commit barrier before any prune, immutable row SHA guards and shared publication lock. Calendar/Deriv request researched only: Forex Factory weekly exports exist but redistribution requires written consent; per-user calendar summaries/reminders need licensed source and frequent timer. Public Deriv symbol/candle data generally requires no private token; market choice/API surface still to identify.

- Research SQL archive research/archive/database-39749790360: 440 experiments, 196161 records, 134194219 payload bytes. SQL fully restored/verified in disposable MySQL before publication; pruning is a separate subsequent workflow step.

- Research archive cleanup completed: 196161 archived records removed; 0 research rows remain. Live/user tables untouched. Empty research table file reclaimed: True.

- 2026-10-22: Owner directed building news from public calendar rather than blocking on source permission. Added slk/news.py, shared news_cache and per-user news_deliveries, authenticated News tab/API, news preference schema, 5min workflow and /cron/news using existing secret. Public feed fetched successfully (86 events). Independent reviewer checked time zones, tenants, dedupe, stale data, sender import/threading, receipt retention and bounded current-time checks. Tests mock all message delivery; manual production verification uses refresh-only mode. Deriv has not been added to live scanning.

- Validation 2026-10-22: 112 tests passed in Actions39753974934, including real MySQL concurrent news delivery claims and per-user API filtering. Preview run39754008857 loaded86 public events, covered current week, fresh cache, no messages. Render/version confirmed commit11bcb4b with news=true and News navigation deployed. Deriv public WS probe returned89 symbols and3 H1 candles for1HZ100V without a token; diagnostic only, live Deriv adapter remains pending.

- 2026-10-22: User explicitly ordered Deriv scanner integration and requested cron-job.org URL. Added slk/deriv.py public WS feed and89-symbol catalogue, isolated DV namespace/store/source, bounded small historical requests, broker units, full UTC market scope through bias/entry/reconciliation/paper tracking/alerts. Selected watchlist union only, existing defaults preserved. Continuous Deriv weekend scans; FX/noncontinuous markets retain closure filter. Real public endpoint probe found1000-response cap and old-range fallback behaviour; fixed request sizing/range/partial-hour/gap/freshness checks. Local validation:8759 closed H1 bars without gaps, full D/W/M bias+entry pipeline ran, UTC H4 OHLC exactly matched native API over same aligned range. No DB writes/Telegram in probe. Human labels and signal-only order block in Mini App. News timer URL documented with existing private cron secret placeholder.

- Deriv cache hardening: continuous hourly-gap check spans month boundaries; affected final months are unmarked for repair on the next run. Missing latest closed hours and gaps skip scans rather than emitting stale confirmations.

- 2026-10-22: Full-suite validation caught missing news tables in webapp fallback schema and stale single-user test fixtures. Synchronized schema, mocked user discovery in fake DB, corrected migration metadata mock, retained invalid-signature rejection and weekend no-download assertion. Added explicit cron-job.org GET URL/setup to README.

- Preserved manual workflow scans during FX weekends; only scheduled runs filter closed markets from the shared watchlist union.

- Final local regression suite:432 passed,3 skipped (77.62s). Dedicated Actions public-feed and real MySQL checks passed before final schema/manual-weekend cleanup.

- 2026-10-23: User reported Deriv failures and requested grouped pair selector. Confirmed live run39767418604 DVR75 RateLimit, DVR25 successful; added bounded throttling recovery and conservative pacing. Added broker/category schema metadata and collapsible searchable selector, live selection counts and cache version bump. Targeted regression48 tests passed; cold two-market public validation runs bias+entry without DB or Telegram.

- Public cold probe reproduced throttling with1.1s pacing; preserved5285H1 DVR75 history and retry completed8759bars. Increased to3.1s/request and10/20/40s throttle cooldown. Independent reviewer48passed and found unmapped-group fallback; fixed consistent Other markets filtering and dynamic selection counts.

- Validation: full suite434passed3skipped before connection recovery addition; final focused49passed with reconnect test. Chromium phone viewport390x844 verified16groups, search, checkbox toggle, retained selections. Real cold probe also exposed remote WebSocket closure during warmup; added bounded reconnect for connection/timeout errors preserving requested historical range, permanent API errors still fail closed.

- Final public validation after pacing/reconnect: DVR25 and DVR75 each8759closedH1; D/W/M bias+entry pipelines succeeded (33/29stories), no DB or Telegram. Independent reconnect reviewer caught empty close-frame case; fixed/tested alongside exception-based disconnect. Final focused50tests passed.

- 2026-10-23: User additionally reported failure while saving Deriv selections. Deriv keys pass validation and full-form save/reload regression; found per-field fresh MySQL connection/commit path causing many TLS round trips and partial persistence on failure. Batched validated settings in one scoped executemany transaction, rollback on error. No production preferences modified for testing. Focused46tests passed.
