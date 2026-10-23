# Causal structure and price-object build contract

2026-10-23 · proposed implementation contract `close_range_v1` · offline only.
This file specifies the next build; it does not certify the old engine or any
teacher-example match. Source authority is `../STRATEGY.md` v0.2 S01–S05,
`full_course_01_08.md` F01–F12/F36–F53, `FULL_SOURCE_SYNTHESIS.md`, and
`full_study_verification.md` §§1,3,4,7. `IMPLEMENTATION_HANDOFF.md` supplies
engineering requirements. All numerical/selection policies below are ours.

## 1. Requirements and named choices

Source requirements: A/V are closing-price turns; OC is a consecutive
same-direction candle junction. They are distinct objects. Wicks record
liquidity and contact, not structural closing prices. A closed body beyond the
selected reference is a break; a wick-only excursion is a sweep. One broken
point can suffice. Advanced defined ranges start with sweep plus break; direct
breakout/retest is a separate permissible route. Major and minor ranges coexist.
A local counter-break does not automatically reverse the major range/story.
Course7's resolved case retains the OLD protected high after a weak-low wick
sweep; the NEW lower candidate is liquidity. Only the contrasting body-close
break permits its promotion. The source supplies no universal pivot order,
ATR threshold, equality tolerance, or complete reference-selection algorithm.

Defaults, frozen before teacher replay:

| Policy ID | Deterministic choice |
|---|---|
| `price_grid_v1` | Instrument tick size required; compare integer ticks. Off-grid input beyond a declared feed-rounding allowance is rejected. Default allowance zero; no floating epsilon masquerading as market tolerance. |
| `close_turn_last_plateau_v1` | Strict close-direction reversal confirms a turn; final equal-close bar is its anchor. No candle-colour gate, minimum leg length, or future right-fractal bars. |
| `oc_exact_junction_v1` | Adjacent non-doji candles of the same colour and C1=O2 on the tick grid; price C1. No synthetic level spanning an opening gap. |
| `causal_range_v1` | Confirmed local turns propose references; explicit sweep/break and range-parent relationships promote them. Never replace a major origin merely with the latest local turn. |
| `break_strict_v1` | Close at least one tick beyond reference. Equality holds; exact wick equality is a touch. No universal impulse gate. |
| `sequence_closed_v1` | Sweep bar end strictly precedes break bar end for sweep+BOS. Same-bar ordering unresolved without independently timestamped lower-resolution evidence. |
| `warmup_evidence_v1` | No arbitrary bar-count seed. Remain unknown until the needed turns, sweep and subsequent break actually exist in the supplied history. |

There is no fixture-calibrated threshold. Any later alternative changes the
policy/version and receives separate results; it does not change source facts.

## 2. Minimal immutable objects

Use timezone-aware UTC times and stable IDs derived from instrument, TF,
policy, object kind and source-bar IDs, never array offsets. All objects include
`instrument`, `timeframe`, `policy_id`, and `source_bar_ids`.

```python
Bar = {id, start, end, open_ticks, high_ticks, low_ticks, close_ticks,
       received_at, complete, segment_id}
Clock = {formed_at, available_at}  # availability includes data receipt
Turn = {id, kind: "H"|"L", price_ticks, plateau_start_bar_id,
        anchor_bar_id, confirmation_bar_id, formed_at, available_at}
KeyLevel = {id, kind: "A"|"V"|"OC", price_ticks,
            initial_role: "RESISTANCE"|"SUPPORT", turn_id: str|None,
            first_bar_id, second_bar_id, formed_at, available_at}
LiquidityRef = {id, kind: "HIGH"|"LOW", price_ticks,
                form: "TURN_LEG"|"BAR"|"SERIES"|"PRIOR_PERIOD"|"SESSION",
                source_start_bar_id, source_end_bar_id, formed_at, available_at}
Range = {id, parent_id: str|None, direction: "BUY"|"SELL",
         status: "PROVISIONAL_BREAKOUT"|"DEFINED"|"BROKEN",
         protected_turn_id, protected_liquidity_id, endpoint_turn_id,
         endpoint_liquidity_id, seed_sweep_event_id: str|None,
         seed_break_event_id, formed_at, available_at}
StructureEvent = {id, kind, side, range_id: str|None,
                  reference_id, reference_price_ticks,
                  reference_formed_at, reference_available_at,
                  occurred_at, available_at, bar_id,
                  sweep_event_id: str|None, old_origin_id: str|None,
                  new_origin_id: str|None, parent_id: str|None,
                  crossing_mode: "TRADED"|"GAP"|"UNKNOWN",
                  intrabar_order: "KNOWN"|"UNKNOWN",
                  policy_id, evidence_ids}
LevelRoleChange = {id, level_id, old_role, new_role, break_event_id,
                   impulse_assessment_id: str|None, available_at}
```

Event `kind` is one of `TOUCH`, `SWEEP`, `BREAKOUT`, `BOS`, `SWEEP_BOS`,
`EXTERNAL_SWEEP`, `EXTERNAL_BREAK`, `ORIGIN_PROMOTED`, `RANGE_BROKEN`.
`side` is the direction of the break or anticipated reaction after a sweep,
not an executable order. `reference_id` resolves to a typed Turn, KeyLevel or
LiquidityRef; callers cannot silently substitute them. `BOS` means an opposite
break at that event's stated scope. A minor BOS is not a major/story flip.

Structural references use Turn prices. Liquidity references use separately
stored actual highs/lows. Each turn leg's liquidity envelope spans the bars
from the preceding confirmed opposite turn anchor (inclusive) to this turn's
confirmation bar (inclusive); take max high for H/min low for L. No earlier
turn means no TURN_LEG envelope yet. This envelope is our conservative finite
geometry, not a teacher-drawn zone. Never use its wick price as the A/V price.
A close-line reference can be swept before the corresponding wick pool is
consumed; expose both events and their different IDs. The pool can already be consumed by the time
its leg envelope becomes available; mark `consumed_before_available` from its
source interval and exclude it from standing-liquidity selection. Do not emit
a retroactive actionable sweep for that interval.

## 3. Streaming formation, plateaus, and gaps

For a validated chronological stream, retain previous close, last nonzero
close direction, plateau start and final plateau anchor. Nonzero means strict
tick comparison. Equal closes extend the current plateau without confirming
anything. A reversal from increasing to decreasing emits H/A at the preceding
plateau price; decreasing to increasing emits L/V. Anchor/formed time is the
last plateau bar end. Availability is the reversing bar's end/receipt, whichever
is later. Preserve plateau interval and confirmation bar for auditing. With
fewer than three informative closes there can be no confirmed close turn.
Candle body colour and O2=C1 are irrelevant to this A/V procedure.

Independently scan each adjacent candle pair for OC: both C>O gives SUPPORT;
both C<O gives RESISTANCE; require C1=O2. Dojis form no OC but do not suppress
close-line A/V. A/V and OC can coexist at one price under different IDs. Do
not deduplicate away their provenance. No formation candle classifies the level
it creates. A levels start RESISTANCE; V levels start SUPPORT.

Opening price gaps across consecutive scheduled bars do not suppress A/V:
close-line geometry is defined even across an opening gap. They suppress OC
when its exact junction is absent. Record `opening_gap_ticks`; never interpolate
an entry or pretend price traded through the gap. Missing expected bars are a
data discontinuity: increment segment, reset unfinished local-turn/OC state,
and suspend range-event generation until continuity is restored or an explicit
complete checkpoint is loaded. Preserve earlier objects as historical, with
`data_gap` status for dependent eligibility. Calendar closures are not missing
bars; calendar policy belongs to the feed adapter.

## 4. Bar processing and primitive event classification

1. Snapshot objects available strictly before this bar's start, or available
   by start when availability equals start. Their forming source bars must end
   no later than start. This prevents a newly confirmed turn from classifying
   its own confirming candle or a delayed reference from claiming earlier wicks.
2. For a high reference p: close>p emits upward break; otherwise high>p and
   close<=p emits downward-reaction SWEEP; equality contact emits TOUCH. Low
   reference mirrors. Exact close=p holds. Wick must strictly exceed p.
3. `low<=p<=high` is required for TOUCH/SWEEP; a close beyond a pre-existing
   level is a break even on an opening gap. Record `crossing_mode=GAP` when
   the complete bar is beyond it; that event implies no level fill.
4. Emit primitive observations for all typed references, then derive scoped
   structural transitions from the same pre-bar snapshot. Commit state changes
   atomically. Finally publish turns/levels confirmed by this bar.

Each reference emits at most one first body-break event per direction/role
version. Repeated wick sweeps remain separate timestamped observations. Sweep
memory is per scope/reference/leg; consume it upon qualifying break or parent
invalidation, never globally erase unrelated ranges. A newer sweep replaces
the active candidate for that same leg while the old event remains immutable.

OHLC cannot establish high-before-low on a bar sweeping both boundaries. Emit
both primitive observations with `intrabar_order=UNKNOWN`; neither establishes
a sweep-then-break sequence on that bar. Known closed bars' occurrence time is
their end (the exact intrabar crossing is unknown). Availability is at least
bar end, receipt time, and every dependency's availability.

## 5. Initialization and promotion algorithm

Maintain a local candidate tape (all confirmed H/L turns), one root range per
TF, and nested child ranges. No initial direction is asserted from the first
bar. First body break of an available local H/L emits local BREAKOUT. Its
opposite-side most recent available turn is provisional origin, if one exists;
otherwise retain event without a range. This provisional range permits an
explicit direct-breakout context; it is not a source-defined advanced range.

A defined range seed requires (bullish case; mirror bearish):

1. A low reference known before the sweep bar is wicked below and held on
   close; its reference may be close structure or an actual low pool but its
   type is explicit.
2. Snapshot the latest available H before the sweep as break target. Require
   that target above the prospective low; never pick a target from future bars.
3. Store the sweep leg's running minimum close and minimum actual low. Ties
   choose the latest bar. A subsequent confirmed L at that minimum close is
   the origin candidate. A still-lower close cancels that candidate and needs
   a newly confirmed L. Thus protected structural price and sweep wick differ.
4. A later closed bar breaks the frozen H, with the candidate L already known
   at its start. Emit SWEEP_BOS (regardless of whether prior local flow was
   known), create DEFINED range, origin=candidate L, and protect the sweep
   leg's min-low pool. This is our conservative causal confirmation choice;
   source patterns lacking a known turn are unresolved under this policy,
   never retrospectively backdated.

Sweep candidates have no arbitrary age TTL. They terminate on opposite
qualifying break of their prospective origin, superseding same-scope seed, or
data discontinuity. Store the frozen target so a newer local H cannot silently
move the goalposts. A root can initialize from a defined seed, or remain a
PROVISIONAL_BREAKOUT root explicitly labelled as such. A completed defined seed supersedes
a same-scope provisional root; close the provisional object with a successor
ID instead of rewriting its earlier state. No fixed warmup count
can guarantee an already-active source range is reconstructed. Replay must
load earlier history or declare `insufficient_structure_history`.

## 6. Active endpoint, major/minor nesting, and protected migration

Range endpoints are close-line extrema in the direction of delivery, published
only after turn confirmation. Before a confirming opposite close there is a
running extreme, not a confirmed endpoint reference. A defined seed breaking
an old H uses that broken H as its initial endpoint reference until the first
post-break H is confirmed; record `endpoint_stage=SEED_REFERENCE` then
`CONFIRMED_DELIVERY`. Endpoint wick pools are separately versioned.

While an active BUY root's protected L holds, opposite-direction sweep+break
can create a SELL child. Assign it to the smallest active containing range:
its origin and broken target must lie strictly between that parent's protected
close and endpoint close at seed time. Otherwise retain the local event without
claiming a nested range. Freeze parent snapshot. The SELL child does not replace
the BUY root. Children may nest by the same rule; chronological seed identity
prevents cycles. A child exiting parent bounds is closed/reclassified; it never
retroactively changes the parent seed. Events outside a defined parent can
still support the direct-breakout route, with provisional scope explicit.

For SELL root (BUY mirrors), freeze the current external low and OLD protected
high when a retracement begins (first confirmed H after external L). NEW is
the latest confirmed retracement H strictly below OLD, known before the
external-break bar. It is a migration candidate, not protected structure.
Track its associated pullback leg and any bullish liquidity swept during the
subsequent bearish leg. Migration requires all of:

- body close below the frozen external low;
- a linked, strictly earlier high-side sweep on the candidate's retracement/
  departure leg (source's new sweep+break; no stale pre-endpoint sweep reuse);
- NEW remained unbroken on close and is known before the break bar starts.

Emit EXTERNAL_BREAK plus ORIGIN_PROMOTED OLD→NEW, with all sweep/turn IDs.
If the external low is merely wicked below and the candle closes at/above it,
emit EXTERNAL_SWEEP and retain OLD. NEW may then be swept as internal liquidity.
If body breakout occurs without the linked sweep or confirmed candidate, emit
EXTERNAL_BREAK but retain OLD and mark `migration_pending_evidence`; do not
invent a replacement. This deliberately separates continuation evidence from
our stricter advanced-range promotion requirement. The course7 contrasting
body-close case permits migration; it does not license selecting an arbitrary
local high in every market.

After body breakout, collect the next confirmed delivery endpoint and open a
new retracement epoch. No wick-only endpoint take advances the epoch or resets
the origin. At parent protected-body break emit RANGE_BROKEN, invalidate its
children for active use, and expose the opposite BOS. A separately qualifying
opposite defined seed replaces the root; absent that, state is provisional or
unknown. The broken range remains in history. Structural invalidation is not
an automatic story flip or order cancellation; those layers consume events.

## 7. Level roles and impulse scope

A body close through a KL emits raw BREAK irrespective of candle size. This
is not automatically BOS, impulse, or a confirmed story. Store initial role
and role history separately. A potential new retest role follows direction of
break (up→SUPPORT, down→RESISTANCE), with `raw_break` provenance. Entry selectors
requiring impulsive disrespect must consume a separately named impulse
assessment before treating it as qualified. No universal numerical impulse
gate belongs in these primitives: verifier §7 distinguishes small H4
confirmation from Daily continuing-direction inference. Touch/retest must be
later than role-change availability; no same-bar invented retest.

## 8. Integration, limits, and required verification

Preserve old `TurningPoint(kind,price,formed_at,available_at)` and basic
`KeyLevel(kind,price,side,formed_at,available_at)` through adapters; map SUPPORT
to BUY, RESISTANCE to SELL. Extend records with optional metadata or new types
rather than changing positional argument meaning. Existing `turning_points`
can supply local candidates after grid/plateau provenance is added. Existing
`events` defaults to latest-local-turn: retain only as explicitly named
`legacy_local` diagnostic, never as the root/major structure implementation.
Existing `price_action.levels(exact_junction)` incorrectly makes all A/V
opposite-colour body junctions for this contract; retain a named legacy mode,
make new close-turn A/V and independent OC generation explicit. Do not silently
change old results without version metadata. Existing `classify` remains a KL
primitive adapter, not a structure engine or automatic role-flip authority.

Required causal checks: replay prefixes equal the same event prefixes from a
longer replay; no timestamp/dependency before availability; gaps/late receipt
cannot create retroactive sweeps; plateau tie determinism; colour-independent
A/V; OC gaps/dojis; wick sweep versus one-tick body break; double-sided OHLC
ambiguity; unknown seed; child counter-BOS preserves root; course7 OLD retained
on wick-only endpoint take and NEW promoted only on qualified body break.
These are rule checks, not teacher-example acceptance. Preserve unresolved
cases as mismatches; do not retune references or expected values to pass them.

Residual uncertainty: this deterministic seed/pullback segmentation is an
engineering interpretation, not a uniquely demonstrated teacher algorithm.
Especially inspect running-close origin confirmation and linked-sweep migration
against independently reconstructed cases after the full build. No live broker,
alert or trading activation is authorized by this contract.

## Executable interface (v2 implementation)

`bishop/v2/structure.py` now implements `analyze(Bar[], StrategyPolicy)` and
`role_at(Level, Event[], as_of)`. Shared `types.py` overrides illustrative type
names above: `Level.side` and role queries use BUY/support or SELL/resistance;
shared `Clock` uses exact end for body closes and the full interval for wicks.
Events use `LEVEL_BREAK`, `LEVEL_ROLE_CHANGE`, `LEVEL_SWEEP`, `LEVEL_TOUCH`
for KLs, and `LIQUIDITY_BREAK`/`SWEEP`/`TOUCH` names prefixed `LIQUIDITY_`
for wick pools. Plain `BREAKOUT`, `BOS`, `SWEEP_BOS`, `SWEEP` are structural.

`StructureResult` contains immutable tuples `turns`, `levels`, `liquidity`,
`events`, `ranges`. Range state is append-only snapshots: `Range.id` identifies
the lineage; `version_id` identifies a state version. To query as-of, retain
the last available snapshot per lineage and exclude BROKEN states. `parent_id`
identifies nested ranges; no parent means root. The range exposes close-line
`origin_ticks` and `endpoint_ticks`, and separate protected/endpoint wick-pool
IDs. `details.endpoint_stage=SEED_REFERENCE` is the just-broken reference;
`CONFIRMED_DELIVERY` identifies a later confirmed delivery endpoint.
`details.endpoint_broken` means an endpoint has been body-delivered before a
new endpoint is confirmed; it must not be treated as fresh standing ERL.

The feed adapter owns missing-bar/calendar recognition and changes
`Bar.segment_id` for genuine discontinuities. The structure module does not
infer a weekend closure to be missing data from elapsed wall time. Explicit
segment changes close dependent ranges with DATA_GAP reason and reset local
formation state. Shared `oc_gap_ticks=0` preserves exact junctions; nonzero
values create explicitly different policy IDs/results.

Construction checks passed for module compile/import, last-plateau anchor,
role pre-availability, and every-prefix equality across all five result
collections on a synthetic stream. These checks are not teaching-case replay,
independent review, or measured source-fidelity acceptance.
