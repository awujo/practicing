# Offline research pilot

Phase 1 is implemented: input validation, completed-candle diagnostics, resource caps, an extensible study catalogue and checkpoint integrity checks. **No strategy alternatives, discovery model, ANN or financial performance evaluation are implemented yet.** Their catalogue/status is in `DESIGN.md` and the generated `catalog.json`.

Run **Actions → SLK research infrastructure → Run workflow** on `claude-kevin-king`. Defaults use the frozen GBPCHF IC Markets export already in the repository, through 19 October 2026 09:00 UTC (10:00 WAT). This does not fetch current market data. Input filenames must match the selected pair. Source and symbol are operator declarations; the CSV itself cannot authenticate broker origin.

The job has no broker/database/OpenAI credentials, does not trade or send alerts, and does not change live settings. It installs pinned pandas/pytest, runs research tests, then evaluates data diagnostics offline. Only manual triggers are enabled. Job budget: 15 minutes, runner step: 11 minutes, cooperative budget: 10 minutes. There are three bounded diagnostic tasks (H4, D, W), **zero strategy candidates**. Inputs: <=25 MiB compressed, <=50 MiB expanded, <=5,000 total H1 rows, requested window <=90 days. Outputs: <=10 MiB JSON allocation, with an additional small workflow log. No automatic retry or data-source fallback.

Artifacts (30-day retention) include manifest, diagnostic results, checkpoint, planned catalogue, status and runner log. GitHub's job summary displays manifest and status. Download the artifact before expiry if it needs keeping; caches/artifacts are not permanent research storage. This manual pilot may lose local progress when a runner is killed. Recurring research requires the later research-only database ledger and backup implementation.

Local example (run from repository root):

```bash
python -m slk.research --input data/debug/GBPCHF_H1_ctrader.csv.gz --pair GBPCHF --source ctrader --start 2026-09-01T00:00:00Z --end 2026-10-19T09:00:00Z --out /tmp/slk-research
```

An identical local invocation resumes completed tasks only when input hash, code/revision, runtime versions and window agree. To inspect a previous artifact locally, restore its JSON files into a fresh output directory and use the same checkout/dependencies/input. Automatic cross-run artifact retrieval is not implemented. A changed identity requires a different output directory.

The exclusive `.lock` prevents concurrent writes. A hard kill can leave it behind. Verify that no process is using that output directory before manually removing `.lock`; never delete a live writer's lock. A fresh output directory is the simpler recovery path. Failed/partial trials may be rerun; completed result checksums are validated. No pickle or executable checkpoint format is used.

`complete` means all three diagnostic tasks finished, not that strategy research succeeded. `data_adequacy` distinguishes no complete bins; `strategy_evidence` remains insufficient. Missing component hours cause a bin exclusion and are counted; the code never invents candles. Closed-bin clocks account for DST. Historical arrival times are unknown and marked simulated. Results do not determine whether a structural break occurred or justify a BUY/SELL.

Before phase 2: independently validate chronological storyline replay and policy population consistency, then implement lifecycle alternatives and durable research tables. Before return/drawdown comparisons: define execution/cost/exposure assumptions and implement the simulator. See `DESIGN.md` for gates and all planned study families.

## Next-phase storyline workflow

The separate **SLK research storyline study** workflow now supports IC Markets history collection, bounded multi-pair replay, lifecycle alternatives, experimental entry comparisons, exploratory screening and optional research-only database publication. See [STATUS.md](STATUS.md) for exact implemented scope, remaining work, assumptions, batch offsets and resume instructions. The infrastructure workflow above remains available as its smaller offline smoke test.
