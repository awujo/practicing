# Bishop paper runner and owner application integration contract

2026-10-23. Design contract for the complete build following
`IMPLEMENTATION_HANDOFF.md`; this document is not an implementation or acceptance
certificate. The full sampled-source study is complete with its recorded limits.
The existing engine remains partial and all 40 historical observations unresolved.
No activation, deployment, data acquisition, broker request or message is authorized
by this document. All defaults are offline/paper and external delivery is disabled.

## Boundaries and useful Kevin infrastructure

Read-only review of `/workspace/kevin-review` covered `slk/live.py`, `slk/db.py`,
`slk/settings.py`, `webapp/app.py`, `webapp/schema.sql`, `webapp/README.md` and workflow
inventory. Reuse the architecture: one typed settings catalogue shared by runner
and API; cached candle preparation; independent pair computation; explicit
reconciliation; paginated FastAPI reads; small static HTML/JS frontend; run timing
and planned-versus-started observability. Adapt the DB connection/TLS utility,
Telegram HMAC verification and pure text formatting after review.

Do not inherit Kevin strategy rules, next-day filters, status semantics, entry
approval-to-broker wiring, automatic schema changes at web startup, inline sends
inside reconciliation, dry-run network acquisition, or process-local cron
throttling as sufficient correctness controls. Bishop needs durable event/outbox
transactions and durable schedule deduplication. Kevin's runtime default fallback
must not silently replace corrupt stored strategy settings for an active run.

All writable tables, indexes, migrations and runtime state belong to `bishop_*`.
Kevin tables and `/workspace/kevin-review` remain untouched. A separately scoped DB
principal should permit Bishop writes and, only if needed later, explicit SELECT
on the existing shared cTrader token table. Shared token values are strictly
read-only, including in-memory fallback: never refresh, rotate, persist, expose or
log them. Expiry produces a data-unavailable result; it does not trigger token
refresh or a fallback broker call. Independent token ownership is a separate,
explicit configuration and future review. No broker execution adapter is needed
for this paper build.

## Minimal module boundaries

| Module | Responsibility |
| --- | --- |
| `bishop/settings.py` | Versioned typed catalogue, validation, source/policy labels, immutable effective snapshot and hash. |
| `bishop/runner.py` | Fixed as-of clock, input validation, compute/reconcile transaction, resumable incremental orchestration. |
| Existing detector + execution modules | Pure causal events and paper execution; no SQL, HTTP, messaging or source-fixture lookup. |
| `bishop/db.py` + Bishop migrations | Isolated repositories, transactions, unique identities, optimistic transitions, run leases and checkpoints. |
| `bishop/alerts.py` | Pure owner-readable text rendering and transactional delivery intent construction. |
| `bishop/delivery.py` | Separately enabled outbox consumer; disabled/no-network default. |
| `bishop/jobs.py` or workflow entry points | Offline hourly simulation, manual scan, backtest, replay and artifact manifests. |
| Bishop `webapp/` | Authenticated reads, validated settings revisions, durable job requests, static Mini App. No engine computation in requests. |

Keep the candle/store layer separate from acquisition. An offline command must
fail with a coverage report when local input is insufficient; `--dry-run` alone
must never imply permission to download. Future acquisition needs its own explicit
capability gate and approved network execution context.

## Persistent model and transaction contract

Use UTC occurrence/availability/observation timestamps distinctly; preserve fill
interval bounds and resolution when exact clocks are unknown. Record symbol units,
calendar, source-feed ID and source-model/policy version. Monetary/price fields
use decimal values with instrument precision, never display-rounded floats.
Immutable evidence/event payloads may use versioned JSON alongside indexed keys.

| Table | Minimum contents and uniqueness |
| --- | --- |
| `bishop_settings` | Validated public key/value, revision, changed-at/actor; no secrets. Retain existing foundation table compatibly. |
| `bishop_runs` | Job/slot/request ID, code/settings/input hashes, as-of and planned/started/finished times, counts, coverage/error state and artifact reference. Unique automatic job+slot; explicit child attempts for retries. |
| `bishop_bias` | Stable story ID; pair, story/level/confirm TF, side, context state, source model, origin/level/target references, reason, availability, last event sequence and version. |
| `bishop_tf_state` | Pair/TF/profile checkpoint: protected/local references, initialization/coverage, last consumed close, input-prefix hash and engine/settings version. |
| `bishop_entries` | Stable causal setup ID, bias ID, model/profile, eligibility clocks, entry/initial stop/target plan, protected objects, current setup decision and reason. Unique causal identity within evaluation namespace. |
| `bishop_orders` | Paper order ID, entry ID, attempt, side/type/price, quantity/risk plan, submitted/eligible/expiry times, lifecycle, fill interval, initial costs and paper result. `execution_mode=paper` only; no broker IDs or approval dispatch. |
| `bishop_events` | Append-only ordered aggregate events: event ID/type, aggregate ID/version, occurrence/available/observed clocks, run ID, reason, provenance and payload. Unique event ID and aggregate+version. |
| `bishop_outbox` | Event+channel+template-version uniqueness, rendered payload hash, disabled/queued/delivered/failed/unknown state, attempts, next retry, receipt and error class. |
| `bishop_job_requests` | Durable owner request or cron slot, allowlisted job type, validated input/settings snapshot, queued/running/terminal state and lease. |

A separate `bishop_settings_history` table is optional if revision events retain
the full immutable settings snapshots. Similarly order amendments/partials/exits
can be events rather than extra tables, provided the current projection is
rebuildable. Artifact paths must be immutable, authorized and content-hashed.
Index pair/status/availability for active cards, entry/order foreign keys, event
aggregate+sequence, outbox state+next-attempt and job state+lease expiry.

Compute from a fixed validated snapshot, then atomically compare aggregate
versions, append events, update projections/checkpoint and enqueue disabled
outbox intents. Advance a pair checkpoint only after all these writes commit.
Concurrent runners acquire durable bounded leases; stale workers cannot commit
without matching lease/version. Restart resumes from the committed checkpoint;
unique causal IDs prevent duplicate orders and alerts. One failed pair is marked
failed without retiring its stories or advancing its watermark. The run reports
partial success explicitly. A disappeared candidate is not itself cancellation.

Keep setup state distinct from paper-order state. A setup can be provisional,
eligible, blocked, superseded or invalidated; an order can be pending, canceled,
expired, missed, filled, partially closed or closed. Loss and stopped entry do not
automatically invalidate the story or authorize retry. Each retry needs a new
causal eligibility event and a new attempt linked to its predecessor. Unknown
intrabar ordering stays censored/ambiguous and cannot become a booked exact fill
or realized return. Source-observation categories remain separate from paper
operating outcomes; manual management creates timestamped amendments only.

## Settings, source models and product experience

One schema supplies defaults, types, bounds, dependencies, choices, help text,
source citations and automation-choice labels to CLI and API. Every automated
rule has an exposed documented setting or explicit non-adjustable semantic
contract; unsupported choices are visible and rejected rather than ignored.
Defaults not uniquely prescribed by teaching are named implementation policies.
Do not fabricate a universal course default across different source routes.

Separate source-model profiles from the owner's aggressive operating preset.
Profiles describe H4/H2 direct, lower-confirmation and the supported entry route
families; the operating preset chooses routes/timeframes prospectively, fixed or
structural stop policy, target/management plan, pending expiry and exposure caps.
Do not select the winning model retrospectively. Teacher-measured stops remain
independent of an aggressive 10–11-pip preference. Display supported instruments,
base resolution, calendars and any unavailable model honestly.

Mandatory defaults: `execution_mode=paper`, `network_acquisition=false`,
`telegram_delivery=false`, `external_dispatch=false`, `scheduled_execution=false`.
Broker mode is absent/rejected. Alert switches cannot override a disabled global
delivery gate. Settings never contain tokens. Invalid saved configuration halts
the affected run; missing newly introduced settings can use versioned documented
defaults. Apply edits atomically with expected revision, reject unknown fields and
cross-field conflicts, and retain actor/time/previous revision. Changes affect
future eligible processing; existing paper orders retain their plan unless an
explicit timestamped amendment is requested and supported. Recompute previews
use a separate namespace and cannot rewrite historical paper results.

Owner flow: Bias shows each story's direction, key level, story so far, context,
plan, freshness and evidence limitations. Entry cards name the source model,
why it is eligible or blocked, entry/stop/target, risk and paper status. Paper
results distinguish realized, unrealized and unresolved outcomes, costs, exposure
and coverage. History shows story/order changes with understandable reasons.
Settings explain teaching defaults versus experiments. Status shows the latest
successful data time, delayed/partial runs and missing inputs. Backtests and
teaching replay have separate results and acceptance labels. Technical IDs,
checkpoint hashes and queue mechanics belong in expandable diagnostics.

## Owner-only API

All `/api/*` endpoints require server-side Telegram initData HMAC verification,
constant-time hash comparison and the configured owner user ID (1410229777 in
handover). Reject missing credentials, malformed/duplicate signed fields,
expired dates and unreasonable future dates. Never trust client user JSON alone.
Use a short documented auth lifetime, same-origin policy, bounded request sizes,
rate limits and no cache on authenticated data. No auth bypass outside isolated
offline fixtures. Public health exposes only liveness; static shell exposes no
account data. Redact secrets/initData from all logs and errors.

Minimal endpoints:

- `GET /api/me`, `/api/status`, `/api/bias`, `/api/bias/{id}` and `/api/bias/state`.
- `GET /api/entries`, `/api/orders`, `/api/history`, `/api/results/summary`;
  cursor pagination, bounded limits, allowlisted filters and explicit as-of time.
- `GET /api/settings/schema`, `/api/settings`; `PATCH /api/settings` with expected
  revision and validated change set. Source profile/supported-model catalogue is
  part of the schema; no separate strategy rules in frontend code.
- `GET /api/runs`, `/api/runs/{id}` and authenticated artifact retrieval.
- `POST /api/jobs` for allowlisted offline scan/backtest/replay requests;
  idempotency key, bounded ranges and immutable settings/input reference required.
  `GET /api/jobs/{id}` reports progress; long computation never blocks a request.

No trade approval, broker submission or live-enable endpoint in this phase.
Future `/cron/tick` is a separate machine-authenticated POST with a header secret,
not owner initData or a query-string secret; durable slot deduplication and branch/
workflow allowlists required. It returns disabled until separately enabled.
Creating a paper job must not dispatch GitHub or acquire inputs implicitly.

## Alerts and delivery

Render previews locally and store intents while disabled. Prefix every message
`BISHOP · PAPER`; use headline / key level / story so far / context / plan. Name
pair/side/model/TF, event time and display timezone; distinguish provisional bias,
eligible setup, pending order and observed fill. Add costs/result R only when
supported. Updates state the changed fact and reason; an invalidated entry must
not be described as an automatic story reversal. Link to owner-only details when
an approved Mini App URL later exists. Escape Telegram formatting, chunk at safe
boundaries and avoid leaking tokens in URLs/errors.

Delivery is to the configured owner only, never a request-provided chat ID.
Outbox retries use capped backoff and retain failures. Telegram lacks an
application idempotency guarantee: timeout-after-send is delivery-unknown, so do
not claim exactly-once messages or blindly resend ambiguous deliveries. Persist
receipts on confirmed success. Old disabled preview intents are not automatically
flushed when delivery is enabled; require an explicit bounded future delivery
policy. No Telegram calls or webhook registration belong to offline validation.

## Efficient hourly/manual/backtest/replay workflows

The default hourly workflow is manual-only/offline; its future schedule can be
present as disabled configuration. Later, an hourly fixed slot plus separately
enabled external tick may request the same job. Deduplicate durably, use Actions
concurrency and DB leases, and retain planned/start delay. Both paths target only
this Bishop branch/workflow. No credentials are needed for offline CI.

Within each run, read settings once, freeze as-of, load changed input partitions
once per pair and aggregate each required TF once. Process all missed completed
bars chronologically, not just the newest hour. Recompute higher-TF structure
only on its close, and evaluate entry/paper-order transitions at each model's
required base resolution. Hourly polling can batch M5/M15 events from retained
input but must not call them real-time notifications. Do not downsample all routes
to H1 merely because the scheduler is hourly. Treat forming bars explicitly.

Checkpoints include code/settings/calendar/feed/input-prefix versions; a mismatch
or revised historical candle requires deterministic rebuild from a validated
snapshot plus overlap, not blind continuation. Initial/changed profiles require
adequate warmup and unknown-state gating. Bound parallel pair workers and batch
SQL writes; reports measure input/compute/DB durations. Skip only unchanged pairs
with no due expiry, management or calendar event. FX weekend skipping must use
instrument calendars; crypto and other weekend sessions cannot inherit it.

Manual scans use explicit as-of and evaluation namespace; promotion into ongoing
paper tracking is an explicit validated action, never a side effect of viewing.
Backtest jobs freeze instrument/range/timeframes/policies/costs/input hashes and
validate actual coverage before reporting metrics. Supported-pair 2018+ testing
is a target, not a claim when history is unavailable. Separate overlapping model
alternatives from an actual exposure-constrained portfolio; retain ambiguity,
unresolved outcomes, drawdown, costs and all tested choices without curve fitting.

Teaching replay invokes the actual complete detector and exports observations
independently of the fixture. Preserve demonstrated plan/pending/missed/fill
states, source stop profiles and source-supported tolerances. Unresolved clocks,
feed geometry or unsupported routes remain unresolved; empty coverage and any
mismatch fail acceptance. Artifacts include code/settings/input/source hashes,
coverage, manifest, observations and mismatch report. Offline engineering CI may
pass while historical acceptance remains unresolved; label both separately.

## Review and completion gates

Before implementation completion: independently review isolation/migrations,
shared-token no-refresh paths, transactional restart/idempotency, settings
revision boundaries, owner auth, event chronology and no-network defaults.
Validate with offline fakes: duplicate ticks, crash before/after commit, failed
pair, missing/revised input, settings changes, ambiguous fills and delivery
unknown. Confirm paginated cards reflect the same stored plans/events as reports.
Use existing source/causal contract tests for strategy semantics rather than
encoding fixtures into integration logic. A full paper build is complete only
when all source routes are wired and unsupported scope is explicit, with review
findings resolved; teaching replay and later historical/paper validation remain
separate gates. Any delivery, hosting, scheduler, acquisition or broker activation
requires a subsequent explicit owner instruction and its own concrete review.

## Implemented offline interface and practical usage (2026-10-23)

The first paper integration is a local result snapshot store/manual worker, not
an incremental continuously running trading service. The causal detector runs
from complete declared local input each time. Durable slots, append-only causal
events, disabled outbox previews and monotone projection as-of guards prevent
repeated imports or late historical runs from regressing current cards. Orders
join execution observations and positions for current status/fills/results.
Job namespaces keep historical experiments separate. Checkpoints, optimized
indexed projections and ongoing prior-plan reconciliation remain later runtime
work; this implementation does not claim those properties yet.

SQLite works without credentials. Use the installed development requirements.
Import an engine-produced local result:

```bash
python -m bishop.runner --result reports/local-result.json --database bishop-paper.sqlite
```

Serve locally with `BISHOP_PAPER_DB` pointing to that SQLite file:

```bash
BISHOP_PAPER_DB=bishop-paper.sqlite uvicorn bishop.webapp:create_app --factory --host 127.0.0.1
```

Authenticated remote-style requests need valid owner Telegram initData in
`X-Telegram-Init-Data`; reading a configured bot token for HMAC does not send a
message. For isolated local development, construct `create_app(store,
local_api_key=...)` explicitly and send `X-Bishop-Owner-Key` from a loopback peer.
There is no environment-enabled authentication bypass. Ordinary browser opening
shows only the static shell. No hosting or Telegram registration is performed.

To queue a job, owner-authenticated `POST /api/jobs` uses `Idempotency-Key` and
an object such as:

```json
{
  "kind": "backtest",
  "input_reference": "data/EURUSD.csv",
  "manifest_reference": "data/EURUSD.manifest.json",
  "as_of": "2026-10-23T00:00:00+00:00",
  "history_start": "2026-01-01T00:00:00+00:00",
  "scan_start": "2026-02-01T00:00:00+00:00",
  "costs": {
    "spread_ticks": "10",
    "entry_slippage_ticks": "0",
    "stop_slippage_ticks": "2",
    "commission_ticks": "5",
    "financing_ticks": "0"
  }
}
```

Numbers above illustrate explicit cost declarations; they are not prescribed
costs or a source claim. The CSV/manifest must already exist. Manifest fields
include symbol, tick_size, distance_unit, calendar_id, anchor_id, price_basis,
source_id, venue and base_tf. Jobs snapshot current settings when queued. Run
one queued job manually, restricting all references to a declared local root:

```bash
python -m bishop.runner --database bishop-paper.sqlite --work-one --input-root /workspace/practicing
```

`--job-id` selects a specific request. No worker starts with the API. Jobs have
durable lease tokens and completion/error states; long jobs exceeding the
bounded lease need retry/review rather than an unfenced completion. Error output
stores exception class only. `GET /api/jobs/{id}` returns status/result reference;
`GET /api/runs/{id}` returns the engine result, coverage and limitations.
Partial or unvalidated engine statuses remain visible and are not converted to
successful teaching acceptance.

Use `kind: "scan"` for the same offline detector/paper evaluation at a selected
clock. Use `kind: "replay"` plus `examples_reference` for an independently
reconstructed teaching-case document within the allowed root. Replay joins actual
orders, setups, stories and instrument ticks with actual execution observations;
it never constructs observations from expectations. The disclosed legacy mode
mapping is an implementation export policy: context_liquidity/source_structural
maps to teacher_source_stop and owner_fixed11 to aggressive_fixed_pips. Original
risk profile, planned entry, actual fill and fill interval are retained. A bar
interval never becomes an exact fill time: `time` stays null unless the interval
is truly exact, and such uncertain fills cannot pass the legacy exact-time
checker. Replay reports include exported observations and this limitation.

Settings include `nested_confirmation` among the source profile choices, source
versus owner fixed-11 risk, numerical policies and prospective exposure caps.
Runner translates the stored settings to the immutable shared StrategyPolicy
and passes max_open_orders explicitly. Explicit caller policy overrides remain
possible for separate experiments. The manual `bishop-paper.yml` workflow only
imports an already committed local JSON into a downloadable SQLite artifact;
it is not hourly execution, durable hosted storage or activation.

Explicit MySQL use is `Store(mysql_url=..., migrate=True)` after reviewed migration;
ordinary app startup uses SQLite and never implicitly touches MySQL. The compact
JSON schema lives in `db/paper_schema.sql`, with namespaced `bishop_paper_runs`
and `bishop_paper_settings` distinct from the earlier foundation tables. Avoid
simultaneous legacy-schema and new-store assumptions when configuring a service.

Offline jobs may additionally declare `management_actions`, a bounded list of
explicit actions on stable engine order IDs. Each action supplies `order_id`,
`kind` and an aware `available_at` clock; supported kinds are CANCEL, REPLACE,
AMEND, BREAK_EVEN, PARTIAL and MANUAL_CLOSE. Amendments declare their tick prices;
manual/partial exits declare price and quantity as required by the simulator.
API/worker validate the shape and finite numeric values, then the engine validates
selected-order ownership and causal execution. Unknown/unselected orders fail.
No action is inferred from chart examples or sends a broker request. This is
historical paper management input, not an interactive live-trading control.

The impulse experiment exposes `impulse_atr_fraction` (null/blank by default) and
`impulse_atr_period` (20). Null preserves unknown impulse qualification; a positive
fraction is a named owner experiment, not an invented universal teaching cutoff.

## Owner operating preset correction

New paper-store defaults use `source_profile=owner_aggressive` and
`risk_profile=owner_aggressive_fixed11`, honoring the owner's aggressive ~11-unit
preference. This is an explicit owner operating preset, not a universal course
rule. `source` remains selectable for contextual structural protection.
`zone_edge` is a separate selectable risk experiment, mapped directly to the
engine's zone_edge profile; it requires actual detected FVG bounds and otherwise
remains unresolved. A source position box never substitutes for detected bounds.
Existing persisted settings are not overwritten by this default correction.
