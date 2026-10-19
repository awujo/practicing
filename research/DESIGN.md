# SLK research system — proposed design

Status: phase-one implementation authorized; not yet deployed. Research never changes live strategy settings or places orders.

## Purpose and limits

Evaluate the existing strategy, alternatives, and new measurable hypotheses. The goal is robust improvement under specified conditions, not a guarantee of a universal optimum. An extensible registry holds studies; finite budgets constrain each run. All alternatives below are catalogued even when their evaluator is not implemented. Reports explicitly distinguish planned, implemented, tested, insufficient-data, and unsupported studies.

## Study registry

Each study has a stable ID, rationale, baseline, candidate values, required data, decision-time features, evaluation horizon, metric, compute estimate, and implementation status.

| Family | Candidate comparisons |
|---|---|
| Story lifecycle | Keep until existing invalidation; retire at target; require renewed structural confirmation; replace with qualified fresh story; age-based expiry; pause after deep retracement |
| Age and distance | Origin-bar age; elapsed time; distance since level/tap/confirmation in volatility units; target multiples travelled; time since last meaningful break |
| Fresh story quality | Level age; prior touches; freshness of rejection; distance to entry; fresh story versus incumbent; overlap and conflicting stories |
| Repeated breaks | First versus later break; minimum spacing; tiny pivot versus structural swing; break size versus spread and volatility; repeated breaks after target |
| Bias and alignment | W/D/H4 agreement; pullbacks; conflicts; strength and age of higher-timeframe state; reassessment after structural changes |
| Tap and rejection | Wick versus body; rejection size; level overshoot; close location; repeated taps; time to confirmation |
| Confirmation | Required timeframe; external versus internal reference; close margin; failed breaks; additional confirmation; delay and opportunity cost |
| Entry | H4/H2/H1 choices within higher-timeframe setup; existing continuation/QMR patterns; immediate versus retest; entry expiry; first versus later opportunity |
| Stop | Existing structural stop; rejection wick; broader structural level; volatility buffer; minimum and maximum width; post-stop path; re-entry policies |
| Targets and exits | Existing target; alternative qualified liquidity; fixed R baselines; partial exits; break-even; trailing; expiry; post-target continuation and reversal |
| Market context | Pair; session; weekday; volatility; trend/range; spread; gaps; liquidity proxies; scheduled news only with timestamped licensed data |
| Risk and abstention | No-trade baseline; exposure overlap; correlated pairs; position caps; drawdown; opportunity frequency; skipped/missed trades |
| Data sensitivity | Broker/feed; H1 versus M5 execution; ambiguous intrabar order; missing candles; timestamp/DST correctness; cost stress |
| Discovery | Training-only feature screening and interpretable shallow rules; later clustering/models/ANN; explicit trial accounting and independent validation |

Do not form the full Cartesian product. Screen a few predeclared candidates within each family first, then test limited interactions. Count every attempted trial, including discarded and failed candidates.

## Architecture

1. Input manifests reference immutable candle snapshots with SHA-256, source, symbol metadata, coverage and gaps. Research consumes cached/exported data first; no automatic multi-year downloads during a routine evaluation. Missing data fails the study with a clear reason.
2. A chronological replay produces decision snapshots using only candles closed at that time. Record candle open, expected close, decision and event times in UTC; display WAT separately. Actual observation/arrival times exist only for forward collection. Historical replay uses explicitly labelled simulated availability and cannot reconstruct past feed delays or revisions. Historical final-state stories are not decision snapshots.
3. Event ledger covers taps, breaks, confirmations, targets, structural changes, expiry and invalidation. Candidate opportunities include no-trade and failed/unfilled signals to avoid survivor bias.
4. Evaluators run versioned baseline/candidate policies, save outcomes separately from decision-time features, and reuse invariant computations. Lifecycle alternatives require replay adapters; filtering final backtest rows is insufficient.
5. Trial ledger stores configuration, code SHA, input hash, split, seed, status, runtime and outputs. Resume only when all identity fields match. Deterministic IDs and atomic completion prevent duplicate results.
6. Reports compare matched opportunities and portfolio effects, include sample sizes and exclusions, and label findings exploratory or independently tested. No automatic promotion to live.

## Storage

Existing MySQL can hold new research-only tables: research_runs, research_trials, research_events, research_observations and research_findings. No extra database initially. Version schema and use a research credential restricted to research tables where feasible. Keep raw candles and bulky trial exports outside MySQL. Database size and retention must be measured before enabling continuous collection.

The first pilot uses a small immutable, versioned input snapshot plus JSON/CSV outputs uploaded as Actions artifacts (30-day retention). It makes no MySQL connection and receives no production/broker credentials. Before the first run, archive the input snapshot and run manifest outside an expiring cache. Phase-one resumption is within a run or by explicitly supplying a verified previous artifact; cross-run automatic durable resumption is not yet promised. A cancelled run may lose its last local checkpoint. Before recurring or long-running research, add the research-only database ledger, idempotent completed-trial writes, and a tested backup/export procedure. Checkpoint loss and retention expiry must be visible in reports. Do not silently delete unresolved trials or overwrite datasets.

## GitHub Actions operation

- Start workflow_dispatch only. No paid APIs, OpenAI calls, ANN training or recurring schedule by default.
- Bounded initial pilot: one pair, one study family, at most four candidates, one worker. Expose finite trial and runtime caps. A 10-minute runner budget inside a 15-minute job budget leaves cleanup time. Profiling may lower these limits. Begin with at most a 90-day window; insufficient events is an acceptable feasibility result. Use a workflow hard timeout as well as cooperative deadlines; stop between small units. A hard timeout can lose in-progress work.
- Split acquisition, baseline snapshot/replay and evaluation. The pilot consumes an explicit IC Markets export, without fallback feeds or broker access. Later acquisition needs a shared broker-token coordination mechanism used by every acquiring workflow; a research-only concurrency group alone cannot prevent cross-workflow refresh races. Keep offline research compute separate from the live concurrency group.
- Checkpoint completed trials locally during the pilot and attempt uploads after failures. Do not claim uploads are guaranteed after cancellation or hard termination. Require durable incremental records before long studies.
- Skip exact previously completed trials; bound retries; no unbounded discovery loop. Record wall time, trials attempted/completed and data/storage sizes.
- Use contents:read unless an explicitly chosen durable publication method needs write permission. Pass user inputs through env/validated CLI, never interpolate them into shell code.
- Automated checks validate schema, closed-candle chronology, trial budgets, deterministic resumption, split boundaries and failures. A separate reviewer agent audits during development; no resident ChatGPT agent is required in production.
- Scheduling, retention and larger batches follow a measured pilot. Public/private repository billing and account limits must be checked; free operation is not guaranteed.

## Evaluation safeguards

Separate chronological development, validation and untouched final test periods. Purge observations whose outcome windows cross split boundaries; account for overlapping stories/trades and correlated pairs. Fit thresholds/scalers/models on training only. Use rolling forward tests and paired comparisons where suitable. Confidence estimates must account for dependence; bar count is not independent sample count.

Track net expectancy, drawdown under explicit sizing/exposure assumptions, trade frequency, fill/miss rate, MAE/MFE, post-stop and post-target paths, and stability across periods/pairs. Spread, commission and slippage assumptions must be stated. H1 cannot resolve all fill/stop/target ordering; use conservative rules and label ambiguity until M5/tick data are available. Unrealized/unfinished outcomes stay censored and are not counted as wins or losses prematurely. Outcome-based explanations are associations, not proven causes.

The final holdout cannot be repeatedly mined. New hypotheses discovered from it require a new future evaluation period. Predeclare minimum sample and practical effect thresholds per study; small samples produce inconclusive findings, not a best-policy recommendation.

## Delivery sequence

1. Registry, manifests, bounded offline runner, local checkpoint/artifact ledger, tests and manual workflow; establish a feasibility baseline and measured runtime on available data. No profitability conclusion at this stage.
2. Research-only durable database ledger and chronological event/replay records; verify prefix-only results and source timestamps, then evaluate lifecycle alternatives.
3. Entry/stop/target evaluators and execution resolution/cost sensitivity; compare matched opportunities.
4. Training-only discovery and forward shadow evaluation; model/ANN experiments only when samples and validation justify them.

Each phase has runnable acceptance checks and a clear coverage report. Catalogue coverage is not implementation coverage. User retains control over live rule changes.

## Independent review findings

The requested reviewer inspected the current repository without edits. Existing entry_backtest finds stories without the same M/W filtering used in the bias backtest; research must explicitly record and reconcile population eligibility rather than inherit inconsistent samples. HANDOVER flags negative entry expectancy on a limited eight-pair study and pending M5 validation. These are starting limitations, not conclusions about every market. Financial comparisons must use actual entry simulation, not the acknowledged misleading bias tap-wick pseudo-trade R. Research must restore production candle caches read-only and never publish incomplete research data under live cache keys.


## Review verdict and first acceptance gate

The architecture is feasible, but the earlier draft left persistence, first-study scope and candidate selection too open. The following replaces those ambiguities; no live deployment has occurred.

### First study: story freshness and small-break diagnostics

Begin with one pair, D stories and H4 observations, and an explicit frozen configuration. Baseline is the current deployed decision policy at a recorded code/config version, not whatever code happens to be latest. Capture a union of raw eligible events before applying candidate policies, including suppressed and no-trade events; differences in event populations are reported rather than silently matched away.

First compare baseline continuation eligibility with exactly one registered alternative: require a new qualifying story after target before treating subsequent breaks as renewed actionable context. In this first study, this is an event-quality comparison, not a trade recommendation. Record story age, time since target, retracement depth, close-line pivot prominence, level distance versus spread/volatility, and agreement/conflict of structure at decision time. A standalone closed-candle break does not prove trend continuation. Define "qualifying story" and actionable-context labels by versioned existing rules before running; do not invent a favourable fresh-story definition after seeing outcomes.

Use a predeclared 24-hour follow-up window to measure signed price change and favourable/adverse excursion from the decision close, normalized by trailing volatility available at decision time. These are descriptive price-path measures, not executable entry returns or proof of edge. An alternative emitting fewer events must show both common-event comparisons and total eligible/emitted/suppressed counts. Non-emitted opportunities are not omitted from the evaluation universe. Distinct lifecycle trading policies require a later entry/exposure simulator; do not attribute zero financial return to a hypothetical suppressed trade without defining capital allocation.

Pilot acceptance is operational: inputs verified, chronology tests pass, exact repeated run produces identical semantic results, missing data is rejected, 10-minute budget respected, timeout/failure reported, and output is readable with an explicit insufficient-data state. A 90-day single-pair pilot cannot certify broad statistical or financial improvement.

### Statistical decision protocol before broader search

For each later study, freeze the primary metric, population, horizon, cost assumptions, candidate list and practical improvement threshold before evaluation. Use training/validation for candidate selection, then one independent test. Account for multiple candidate comparisons through a predeclared procedure (for example Holm correction for confirmatory comparisons); large exploratory screens are labelled exploratory and need new data to confirm. Derive sample requirements from a minimally useful effect and dependence-aware uncertainty/power estimates rather than assigning a universal trade count. Account for censored observations without comparing only conveniently completed samples.

Story-retirement, fresh-story and re-entry policies require a documented transition table with priority when target, invalidation and replacement coincide. Ambiguous H1 event ordering is conservative or explicitly unresolved. Break event time is the candle close, distinct from its stored candle-open timestamp. Original versus fixed code versions are separate baselines to distinguish bug corrections from strategy improvement.

No model, minimum-size threshold, volatility normalization, feature selection or execution assumption may use future candles. Policy decisions must be invariant when later candles are appended, except for separately stored outcomes. Research changes to confirmation rules are hypothetical alternatives, not permission to change the live strategy.

### Resource and monitoring limits

Measure end-to-end job time (setup, input loading, replay, evaluation and uploads), runner class, downloaded bytes, artifact size and MySQL growth when enabled. Initial 15-minute job and manual-only triggers limit exposure but do not constitute a currency spending cap. GitHub minutes/storage pricing and quota depend on account and repository visibility; verify them before schedules or paid resources. Reject oversized windows/candidate counts at input validation. Run no nested strategy Cartesian products.

A future scheduled system uses deterministic health checks for stalled/failed trials, stale data, budget overruns and schema errors. Those checks can annotate Actions and produce a dashboard/report without AI tokens. They do not prove research correctness. Human review and session-scoped independent agent review remain separate from any optional, separately billed LLM analysis service. No external messages are enabled by this design.

### Concrete implementation acceptance checklist

- Phase 1 is infrastructure only: synthetic/hand-checked fixtures and runtime measurements, no historical performance baseline. The first real-data study above starts only after phase 2's as-of replay gate passes.
- Initial limits: one pair, at most 90 calendar days, one family, baseline plus one candidate (runner hard ceiling baseline plus four), one worker; combined compressed inputs at most 25 MiB, input rows at most 5,000 H1 bars, outputs at most 10 MiB per run. Limits are checked before work and during output writes. Larger budgets require an explicit configuration revision.
- No automatic workflow retry; at most one retry for a transient checkpoint/artifact transfer, within the existing time budget. Do not retry invalid data or deterministic evaluator failures. Phase-one lost local work is rerun explicitly.
- Outputs before a cutoff must be semantically identical when later candles are appended. Only outcome records may change. Test H4/D1/W1 closes, summer/winter and DST-transition boundaries, forming bars and missing component hours.
- Hand-check at least one BUY and SELL fixture, a target followed by a tiny internal break, an invalidated story and a competing fresh story. Each candidate's accepted/rejected events must reconcile to these fixtures.
- Validate supplied resume artifacts against complete manifest identity and file checksums; resume cannot duplicate completed trials. Simulated interruption tests cover a partial write, a completed write before acknowledgement and failed uploads.
- No performance claim without explicit chronological splits and sufficient independent data. A short pilot may produce only operational and descriptive findings.
- Before financial/portfolio studies, specify bid/ask treatment, commission, slippage, gap fills, stop/limit semantics, partial exits, fixed sizing, simultaneous positions, correlated exposure limits, mark-to-market of open trades and liquidation at evaluation end. Compute portfolio drawdown from the resulting timestamped equity path, not cumulative closed-trade R.
