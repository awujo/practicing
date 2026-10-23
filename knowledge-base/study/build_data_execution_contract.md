# Build contract: feed, execution and offline reporting

2026-10-23. Proposed implementation contract following `IMPLEMENTATION_HANDOFF.md`
and `../STRATEGY.md`; this document does not certify implementation or replay.
All policies named below are engineering choices, not newly discovered teacher
rules. Existing H1 behaviour remains available as `legacy_h1_v1` with its
limitations reported. No download, broker, live delivery or Kevin state changes
are authorized by this contract.

## 1. Frozen feed and instrument identity

A run consumes local immutable bars plus a hashed manifest. Required manifest:
`schema_version`, provider/source description, venue and exact symbol, canonical
instrument ID, asset class, quote currency, price basis (`bid`, `ask`, `mid`, or
paired bid/ask), base duration, UTC start/end semantics, original timezone,
calendar ID/version/hash, aggregation-anchor ID/version, tick size, display
digits, explicit strategy distance unit and its price multiplier. Contract size,
quantity step/minimum, P&L currency and FX conversion sources are required for
cash/account returns; otherwise report only price/R outcomes. Include file hash,
coverage bounds, known corrections, timestamp of snapshot, and availability
convention. A symbol alias must not merge distinct CFD, futures, spot or broker
synthetic products. Preserve original provider identifiers.

Rows represent half-open `[start,end)` intervals; timestamps must be aware UTC,
strictly ordered and unique per instrument/basis. Require finite valid OHLC,
`low <= open,close <= high`, positive duration, aligned boundaries, explicit
source `available_at >= end`, and no overlapping bars. Do not require positive
prices universally (some oil contracts have traded below zero). Reject conflicting
duplicates; exact duplicates may be deduplicated only with a logged transform.
Validate the entire frozen input before selecting its historical prefix.
Volume is optional and cannot be invented or treated as liquidity evidence.

Primary build input is M1. It supports M5/M15/M30/M45/H1/H2/H3/H4 and calendar
D/W/monthly `M` (use internal `MN1` to disambiguate M1). A source may explicitly
request additional integer-minute refinements such as M2/M3/M10/M20, provided
its calendar boundaries can be represented by the base rows. H1 remains a valid
input for H1/H2/H3/H4/D/W/M only. H1 cannot produce M45/M30/M15/M5. Neither M1
nor H1 proves tick order. Subminute examples require declared finer bars/ticks;
otherwise label the relevant fields `UNRESOLVED_RESOLUTION`. Never synthesize
lower candles, forward-fill prices or upsample to claim example coverage.

## 2. Calendar and completed aggregation

Store a canonical nominal start/end independently of first/last observed rows.
Expected slots come from the instrument's versioned trading calendar, including
holidays, daily maintenance, half days and DST. Planned market closure is not a
missing row. Provider “no trades” omission is not automatically a closed session;
accept it only with an explicit source guarantee/recorded empty-slot policy.
Unknown calendar boundaries remain unresolved.

Named default choice `ny17_wall_v2`: shift local America/New_York wall time by
7 hours; intraday bins floor shifted minutes from each shifted midnight;
D is shifted calendar day; W runs from Monday shifted midnight to that
Monday plus five shifted calendar days (Sunday 17:00 through Friday 17:00
New York); monthly bins are shifted calendar months. Convert the computed
boundaries back to aware UTC. Thus H3 begins 17:00/20:00/23:00… New York and
M45 begins 17:00/17:45/18:30… rather than an unspecified UTC epoch. DST ambiguous
boundaries choose the first fold; nonexistent boundaries shift forward to the
first valid instant. Remove duplicate boundaries, preserve strict UTC order,
and record variable-duration bins explicitly. This intentionally declares the
inherited wall-clock convention; DST tests are mandatory. Alternative
`utc_epoch_v1` uses UTC epoch-minute multiples, UTC D, Monday UTC W and UTC
calendar month. A provider-native calendar/anchor can be configured from
independently established metadata; never infer it from desired replay results.
A teacher chart with an unknown anchor cannot receive an exact timing pass.

Each aggregate uses first open, maximum high, minimum low, last close, and lists
its expected/present constituent counts, nominal bounds, source interval/hash
and availability. Membership is by source interval wholly contained in nominal
bounds; a crossing source interval is unsupported rather than split. Aggregate
availability is max(nominal end, all constituent availability times). A bar is
signal-eligible only after that clock and complete expected-slot coverage.
Forming bars may be exposed for display with `FORMING` state, never passed as
closed evidence. Calendar closures can create an empty nominal bin; omit it
from price-pattern sequences and preserve its calendar record. Incomplete first
or last aggregates remain explicitly incomplete, not shortened candles.

For non-FX assets choose the instrument calendar explicitly: metals CFDs often
have daily maintenance; cash indices, index CFDs and futures differ; oil contracts
need expiry/roll metadata and continuous adjustment provenance; crypto can use
`24x7_utc_v1` only when the actual venue supports it; synthetics require provider
specifications and may be 24/7. Apply no FX weekend rule by asset-name guess.
Pip defaults from `instruments.py` are compatibility assumptions: FX 0.0001,
JPY quote 0.01, XAU 0.1, XAG 0.01, indices 1 point. Oil/crypto/synthetics and
unknown symbols must provide units rather than fall through to FX defaults.
Tick rounding uses decimal/integer-tick arithmetic; record requested and rounded
prices, rounding direction and any rejected geometry. A fixed 11-pip FX owner
preset does not silently become an 11-unit cross-asset teacher rule.

## 3. Missingness and causal clocks

Track occurrence interval, first observed/available clock and eligibility clock
separately throughout bars, structures, stories, setups and orders. No pivot,
closing breakout or context can be consumed before its own availability. All
same-clock facts are processed as a batch before deterministic selection; model
ranking and exposure rules are frozen before outcomes are read.

A missing required slot invalidates affected aggregates and dependent detection
state. Mark `CENSORED_DATA` at the first unresolved active interval before any
later apparent fill/exit; do not jump the gap. Preserve pre-gap facts, but no
outcome may be inferred through it. Resumption requires declared sufficient
warmup and rebuilt complete state; do not carry unknown structural references
as valid. Calendar-closed slots do not censor. Unsupported TF, absent warmup,
unknown calendar and uncertain sequencing have distinct reason codes. The
strict compatibility run may still stop its entire window on any missing H1;
v2 may continue independent instruments/complete segments while reporting every
excluded span and its denominator.

## 4. Execution event ledger

Immutable IDs link evidence → setup → order → fills → position → exits. Persist
append-only events with `occurred_window`, `available_at`, stable sequence,
parent/replacement ID, source/model/profile, reason, quantity and prices. Derived
current state is replayed from events. Minimum order events: candidate eligible,
selected/rejected, submitted pending, canceled, expired/missed, replaced,
partially/fully filled and rejected. Position events: opened, quantity changed,
stop/target amended, partial exited, break-even amended, manually closed,
stopped, target exited and open/censored observation. Source-reported status and
simulation status are separate fields. A missed H3 limit followed by M30
replacement remains two linked orders; it is never rewritten as one filled H3.

Orders explicitly declare `MARKET` or `LIMIT`, side, submission/eligibility clock,
requested price, quantity, initial stop/target and protected-object reasons,
expiry and selection policy. A market order uses the first executable quote
at/after submission (or next bar open when submitted on its exact boundary);
never the just-closed signal price by assumption. A limit buys when ask <= limit
and sells when bid >= limit; under `requested_limit_v1` fill at the limit without
favourable gap improvement. Stops/targets for longs observe bid, shorts ask.
Declare alternative quote/order conventions in a different profile.

With one-sided bid OHLC, `constant_spread_bid_v1` derives ask by adding the
explicit spread in price units. Spread, entry/stop slippage, commission (per side
or round trip, quantity basis), financing and conversion assumptions are mandatory;
zero is permitted only when explicitly declared. Do not double-charge spread
already represented by bid/ask execution. Adverse stop gaps execute at the worse
of stop and executable open plus adverse slippage. Limit-target gap improvement
is disabled in this profile. Stop rounding and slippage may exceed initial 1R.
Report initial requested risk and actual fill risk separately; realized R uses
a declared frozen denominator, default actual fill-to-initial-stop price risk,
with cash costs converted consistently. Reject zero risk.

Coarse OHLC establishes only an observation window, not an exact fill time.
Default `strict_sequence_v2` censors any material unresolved ordering: entry and
exit in one bar, stop and target in one bar, intrabar cancel/replacement/amendment
versus touch, or submission/expiry inside a base interval. Finer data may resolve
it. Optional `legacy_stop_first_v1` reproduces conservative stop-first estimates
with conspicuous assumed flags; such results cannot pass exact source timing.
At a known bar boundary, process completed-close evidence and resulting
cancel/replace/amend events before the next interval's executable open. Intra-bar
prices before an amendment cannot trigger the amended stop. Pending expiry ends
pending exposure only; it does not close an already filled position. Replacement
requires an actual cancel/replace event and fresh documented eligibility; neither
a stop nor cancellation creates an automatic retry. Partial fills require real
quantity evidence or a named liquidity model; OHLC alone uses all-or-none.

Initial targets may be ERL, prior extreme, story KL or fixed-R according to named
model. Later break-even, partial and manual management requires explicit causal
events; favourable excursion is a diagnostic, never realized return. Historical
manual exits without a reproducible automated rule stay source observations,
not silently invented automation. Open positions remain open at the data end;
optional terminal mark-to-market is separate from realized results.

## 5. Incremental computation and offline reports

Validate/hash each immutable partition once. Cache completed bars by instrument,
source hashes, base resolution, calendar+anchor hashes, TF, availability policy
and code version; cache detector state by those keys plus full numerical policy
hash. Maintain expected-slot indexes and rolling open bins; publish aggregates
once, consume each close once, and maintain monotone event cursors. Do not
resample/re-run every historical prefix for each setup. Corrections invalidate
all affected descendants from the earliest changed slot; record a new run rather
than mutate old reports. Checkpoints include state version and event watermark;
a cold chronological replay and restart replay must produce identical events.

Offline CLI preserves existing H1 `--data`, `--source`, `--pair`, clocks and cost
arguments through a documented `legacy_h1_v1` adapter. New manifest/base-TF,
calendar/anchor, instrument and execution-profile options are explicit; old
choices keep their meaning. Remove the fixed FX universe restriction only when
metadata validates the added instrument. Requested unsupported models/TFs return
non-success status with reasons, never a successful empty trade list. Local
read/write only; Bishop output/cache namespace is isolated from Kevin storage.

Each report contains run/code/config/input hashes, runtime versions, frozen
history/scan/as-of clocks, instrument and feed metadata, coverage per TF, warmup,
model support matrix, all named choices, counts by eligibility/selection/order
state, event history, fills/position amendments, realized net and gross results,
open/mark-to-market exposure, costs, censoring/ambiguity counts and skipped spans.
Portfolio results require predeclared sizing/exposure, currency conversions and
chronological simultaneous-order policy. Otherwise label observations as
independent candidate outcomes, not an investable portfolio or equity curve.
Show closed-trade denominator, pending/missed/loss/retry/replacement counts and
censored/unresolved exclusions alongside any win rate or expectancy. Report
teacher-profile fidelity separately from owner aggressive-policy performance.

Teacher replay runs only after the system build and independent review. Preserve
independently verified expected instrument/TF/model/context/status/entry/stop/
target/timing, fixed tolerances and source uncertainty. Full pass requires all
required fields; unresolved feed/anchor/manual timing is unresolved, never pass.
No parameter selection, tolerance widening or expected-value edits to fit replay.

Required verification before implementation acceptance: prefix-causality;
M1→M45/H3 and H1 resolution rejection; DST folds/gaps and calendar holidays;
partial-leading aggregates; unknown units; missing data before fills/exits;
market versus limit quotes/costs; cancellation/replacement windows; ambiguous
fill-bar outcomes; exit amendments; restart/cache equivalence; and preservation
of legacy H1 CLI outputs under its explicitly pinned compatibility profile.
