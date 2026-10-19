Expanded full-history/scenario workflow: see [SCENARIOS.md](SCENARIOS.md). The earlier pilot coverage below describes the original 21-day workflow, not the full scenario expansion.

# Research implementation coverage

## Available now

- Phase 1: offline input validation and completed-candle diagnostics.
- Phase 2: prefix-only D-story observation at completed H4 boundaries; W/M context comes from the same prefix. SQLite transactions save events, policy decisions and the latest progress snapshot together. No pickle. Historical event time and first observation are separate. This studies **pair_state event eligibility**, not the complete Telegram reconciliation/standing-bias population.
- Lifecycle baseline plus four alternatives: keep eligibility; retire at target; require a close margin of at least 0.5 trailing mean H1 range after target; admit only the latest eligible fresh story before its target; expire eligibility 10 calendar days after the tap. The margin alternative is **not renewed structural confirmation**. Remaining lifecycle rules are still planned.
- Event outcomes: 24 real elapsed hours of signed movement, favourable/adverse excursion normalized by trailing mean H1 range. Missing endpoints/gaps are censored. These are price-path observations, not returns.
- Phase 3: four experimental entry variants (H4 zone, H2 zone, H1 zone, H1 rejection stop), using existing entry-pattern code with a research-only prospective pending-order adapter on closed prefixes and recording only setups observable while pending. At most the first 12 eligible confirmations per pair, reported explicitly. Already-ended-at-observation confirmations are excluded. This is not live entry-policy replication: alignment is explicitly off; entry searches last 24h. Incomplete searches are censored.
- Entry execution: H1 limit-order approximation, fixed assumed 1-pip spread, 0.2-pip slippage, zero commission; stop before target on ambiguous bars, no fill-bar target win, adverse opening gap stops, 24h pending expiry/holding. Pending orders cancel at first H4-observed lifecycle end; filled trades keep their own exits. Fixed assumptions are not measured broker execution. No portfolio return/drawdown or validated edge is claimed.
- Phase 4 starter: four predeclared shallow groups; choose only on the earlier chronological half and inspect the selected group on the later half. Purge outcomes crossing split. Require at least 30 distinct pair/time/side samples per period, but that count alone does not establish independence or adequate power. Canonical event features use the latest confirmation/tap. Report insufficient data instead of choosing a best strategy. This is exploratory screening, not an ANN or untouched confirmatory result.
- MySQL: optional isolated publication to `research_records` in the existing database. Immutable event/decision/outcome records; aggregate discovery/checkpoint snapshots are content-versioned. No live schema migration or trading setting writes. Broker authentication during collection may refresh existing cTrader tokens as usual.

## Run it

Actions → **SLK research storyline study** → Run workflow on `claude-kevin-king`.

Empty `pairs` selects the standard **28 FX pairs**, not Mini App database settings. Explicit CSV selects your chosen symbols. `limit` is 1..4 (default 2), `offset` starts at zero. `batch-report.json` lists requested/selected pairs, failures, retry pairs and `next_offset`. A batch does not imply the rest of the queue was studied. No recurring schedule is enabled. For automatic batch progression, manually start **SLK research automatic queue** on `claude-kevin-king`. It processes all 28 standard FX pairs in batches of four with at most two attempts per pair and a 150-minute coordinator budget. Optional `existing_run_id` adopts the first standard four-pair batch. It waits for each study and publication, records completed/unfinished pairs and run links in `research-queue.json`, and stops after success or bounded failures. It uses Actions minutes while waiting, with no OpenAI calls. Cancellation stops the coordinator; an already dispatched child may finish. The queue artifact is an operational summary, not a pooled statistical analysis.

Collection uses IC Markets directly, no fallback. Default: 1,200 calendar days of warmup+history and the latest 21 days for evaluation. Phase-two profile permits <=1,500 total days, <=30,000 H1 rows per pair and <=90 evaluation days; actual history must include at least 365 days before evaluation. This explicitly extends phase-one's 90-day/5,000-row infrastructure profile. Actual first/last timestamps and historical gap counts are recorded. Recent missing market hours fail replay closed; older gaps and warmup differences limit comparability with live.

Acquisition shares `slk-live` concurrency with live/backfill, so it waits its turn and releases the lock before offline compute. Manual batch acquisition can briefly delay a live job; research itself does not trade. Other existing workflows not using that shared lock remain a token-refresh coordination limitation.

Offline batch: at most 600 seconds cooperative budget and 140 seconds per pair inside a 15-minute job. SQLite has a 3 MiB page cap (with rollback journal/temp space within the per-pair 10 MiB envelope); combined batch JSON budget is 40 MiB. Publication is capped at 20,000 records per pair. Runtime includes separate setup/acquisition/publication overhead; this is not a currency spending cap.

Artifacts contain frozen inputs, ledgers, reports and logs and expire after 30 days. With `publish=true` (default), immutable records and progress snapshots also persist in MySQL. No database retention deletion/backup automation is implemented: establish a measured retention/backup policy before recurring operation. Growth is bounded per batch but not across unlimited manual runs.

To resume a partial study, supply `resume_run_id` from a previous study run. It downloads that run's exact frozen inputs and SQLite ledgers; no new broker acquisition occurs. Resume requires identical computation code, config, runtime versions and dataset identity. Changed code requires a fresh study identity/output: set `resume_run_id` to reuse the frozen inputs and `fresh_replay=true` to discard old ledgers. Artifact expiry prevents this automated restoration; MySQL stores records/checkpoint snapshots, but automatic reconstruction of a full ledger from MySQL is not implemented. Never assume an expired raw input is recoverable from the database.

## Still planned

Full live-policy reconciliation/standing-bias replication; deeper lifecycle transitions and structural-renewal rules; W/M storyline experiments; complete multi-year forward folds; calibrated costs/M5 execution; independent portfolio risk evaluation; multiple-comparison-adjusted confirmatory tests; automatic database retention/backups; larger data-driven discovery and ANN models. All live rule promotion remains under owner control.

Publication inserts/verifies records in batches of 100 to limit database round trips. Pending detection and execution both use the same assumed 1-pip spread.

## Verification

GitHub run [39251591881](https://github.com/awujo/practicing/actions/runs/39251591881) passed all three jobs, including 55 focused tests, frozen-input restoration and MySQL publication. Generated reports were inspected: USDCHF 45 events/90 decision points, GBPCHF 36/90, one eligible confirmation and four entry trials per pair. Shallow discovery reported insufficient data and selected no rule. This verifies operation on two pairs; it does not mean all 28 pairs or all planned studies have completed.
