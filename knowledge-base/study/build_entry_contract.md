# Entry build contract

2026-10-23. Specification only; no engine change or example acceptance claim.
Authority: `../STRATEGY.md` §§5–8, `IMPLEMENTATION_HANDOFF.md`,
`FULL_SOURCE_SYNTHESIS.md`, `full_entry_study.md` (E14/E15/P) and
`full_session_study.md` §§13–34 (E5/RS/BE/T3/DR). Source requirements and
**OUR CHOICE** detector conventions below are deliberately distinguishable.
Upstream structure, story and liquidity contracts supply causal objects; this
contract must not silently redefine those objects using the old partial engine.

## Typed inputs and outputs

Use instrument integer ticks, explicit pip-size metadata and UTC timestamps.
A timeframe is a calendar/alignment identifier, not merely a duration number.
All references below are immutable versioned IDs.

```ts
type Direction = 'buy' | 'sell';
type Clock = { occurredStart: Time; occurredEnd: Time;
  observedAt: Time; availableAt: Time; closedAt?: Time };
type Evidence = { sourceRefs: string[]; policyVersion: string;
  quality: 'source' | 'derived' | 'our_choice' | 'unresolved' };
type Fact<T> = { id: string; value: T; clock: Clock; evidence: Evidence };
type EntryFamily = 'direct_h4' | 'direct_h2' | 'confirmation_bo'
  | 'confirmation_sweep_bos' | 'confirmation_engulfed_oc'
  | 'confirmation_standing_extreme' | 'engulf_av_retest'
  | 'oc_break_retest' | 'engulf_irl_retest' | 'aggressive_kl_imbalance';
type EntryPhase = 'origin' | 'continuation' | 'reentry';
type Readiness = 'waiting' | 'eligible' | 'blocked' | 'unresolved';
type EntryCandidate = {
  id: string; storyId: string; direction: Direction; family: EntryFamily;
  phase: EntryPhase; entryTF: TF; reactionTF?: TF; sourceProfile: string;
  policyId: string; selectedKL: KLId; structureIds: string[];
  liquidityIds: string[]; reactionId?: string; confirmationIds: string[];
  nestingParentId?: string; occurrence: Clock; relatedInterval: Interval;
  prerequisites: { id: string; requiredAt: Time }[];
  eligibleAt?: Time; readiness: Readiness; reasons: string[];
  alternatives: CandidateId[]; riskPlanId?: string; targetPlanId?: string;
};
```

A KL carries price, A/V/OC kind, forming bar IDs, origin TF, formation and
availability clocks, current role and timestamped role changes. Liquidity
carries wick boundary, source interval, form (single/series/structural), role
(IRL/ERL), range ID and the clocks for formation/taking/role changes. Break
carries close price, referenced structural ID and TF; a sweep carries reference,
extreme, close-back evidence and TF. Reaction carries touch evidence plus
observable rejection evidence, enclosing candle ID and whether that candle is
closed. `standing` is a bounded observation through a stated time, never a
promise that an extreme remains untouched later.

Output separate candidate, order intent, accepted pending order and fill.
An eligibility event alone never implies teacher participation or execution.

## Causal clocks and general evaluation

1. At each new observation ingest facts with `availableAt <= now`; evaluate
   only enabled families and predeclared timeframe/model policy. Unknown
   initialization or unavailable required data yields `unresolved`, not false
   evidence and not permission to trade.
2. Join a lower pattern to its reaction by explicit story/range/KL lineage and
   intersecting reaction/formation interval. **OUR CHOICE relation policy v1:**
   require the completing directional break/engulf close at or after the
   reaction's first observed touch, with formation allowed to start earlier.
   Do not attach an arbitrary older break merely because its direction agrees.
   Patterns observable during the origin/reaction candle can be retained;
   eligibility waits for every model-specific closure prerequisite.
3. `eligibleAt = max(prerequisite.availableAt)`; preserve occurrence separately.
   A reaction-confirmation shape's own break/engulf bar must be closed. H4
   breakout closure and H4 reaction closure are different fields. A closed H1
   bar cannot close its containing H4 candle. Broker publication latency counts.
4. A buy limit must still be below the observable executable ask (sell above
   bid) when submitted. **OUR CHOICE:** if already crossed, emit
   `missed_before_submission`, never a historical fill or automatic market
   conversion. Market replacement requires a separately authorized model.
5. No same-bar retrospective retest: a limit becomes fillable only after actual
   order acceptance. OHLC unable to order eligibility/touch, sweep/touch or
   stop/target yields an ambiguity interval; require finer data or censor the
   exact result. A future pivot confirmation cannot authorize an earlier limit.

## Family algorithms and readiness

Each row also requires an active admissible story/context, relevant selected KL,
valid stop/target plan and supported data. Context can be explicitly Daily/H4
counterweekly or local H4 course context; no universal weekly veto is added.

| Family | Required facts and order | Earliest readiness / entry |
|---|---|---|
| `direct_h4` | Directional H4 BO (or source-permitted sweep+BOS), formed H4 IRL pool, relevant H4 KL in its retracement path. | BO and liquidity formation observable; **OUR CHOICE default closed-bar structural facts**, therefore BO close and pool formation close. Submit H4 KL limit while sweep/reaction is still anticipated. Never require future pool sweep. E5 156.9–221.2. |
| `direct_h2` | Explicit closed H4 BO; related H2 BO or sweep+BOS; H2 single/series/structural liquidity and relevant H2 KL. | Max of H4 BO close, own H2 structure close, liquidity/KL availability. Submit H2 KL limit directly. No required H4 reaction and no extra lower confirmation after H2 eligibility. H2 facts may form inside the H4 BO candle but cannot authorize an earlier order. E5 85.8–135.5,225.9–291.1. |
| `confirmation_bo` | H4 directional structure + liquidity; liquidity taken/reaction at relevant H4 KL; related lower-TF positive BO; selected lower KL, with lower liquidity if the selected source profile requires it. | Lower BO close plus reaction availability; H4 reaction close only in the chosen closed-reaction policy. Limit at lower KL. E5 293.6–453.1. |
| `confirmation_sweep_bos` | Same reaction prerequisites; related lower sweep followed by positive body-close structural break. | Both sweep and BOS causally known; select lower KL and place limit. A wick excursion alone is insufficient. |
| `confirmation_engulfed_oc` | Same reaction prerequisites; two consecutive counterdirection candles create OC; directional close disrespects that OC. | OC and disrespect close known; limit at broken OC. Do not require engulfing both bodies or a separate structural BO. E5 470–541. |
| `confirmation_standing_extreme` | Same reaction prerequisites; explicit source reference candle, swept side, opposite standing side, and directional A/V KL mapping. | Completed mapped sweep/standing sequence and new KL known; limit at A/V. See bounded automation below. |
| `engulf_av_retest` | Course HTF IRL/KL reaction and profile-specific closure; directional engulf creates new A/V. | Engulf close and new KL availability; direct A/V retest limit. No universal new-IRL or FVG condition. E14 426–533; course12 exception in STRATEGY. |
| `oc_break_retest` | Course reaction/context; consecutive counterdirection OC; directional candle engulfs final opposite body and closes through OC. | Compound event close known; broken OC limit. Source E14 533–666 is stricter than session OC-disrespect variant; retain distinct subtype. |
| `engulf_irl_retest` | Engulf creates A/V; immediately following candle approaches without touching it; that closed candle supplies IRL; later sweep into KL. | At following candle close place anticipatory KL limit; ordinary LIMIT is then active. Expected future IRL sweep is explanatory, never a retrospective fill veto; preserve gap/sequence uncertainty. No order on engulf alone under this family. E14 666–753. |
| `aggressive_kl_imbalance` | Valid contextual KL overlaps valid imbalance; aggressive policy explicitly selected. | KL + imbalance + context available; limit at KL without new inducement or lower confirmation. Approximate 10–11p source preference is separate risk policy, not universal geometry. Course3 1002–1078. |

**Reaction policy:** Bishop source-permitted default `intrabar_observed` allows
lower confirmation before H4 reaction closes; require an actual observed touch
and observable move back to intended side, not a future H4 wick. Alternative
`closed_reaction` waits for H4 close on intended side. **OUR CHOICE:** on OHLC-only
input, intrabar reaction becomes known only at the smallest supplied closed bar
that establishes touch and rejection, and any unknown ordering is censored.
Core E14/E15 closed-reaction teaching uses `closed_reaction`; aligned provisional
course15 entries must carry `provisional_htf`, with later close-through risk
visible. These execution permissions do not confirm an unclosed Daily story.

## Numerical definitions — OUR CHOICE v1, never teacher constants

The following defaults make synthetic behavior reproducible; historical source
cases can fail or remain unresolved. Change only through versioned policy and
independent review, never to fit a source fixture.

- Equality is exact integer-tick equality; strict breaks require at least one
  tick beyond the reference. KL touches include equality. Wick sweep requires
  strict extreme passage and close back inside/equal. Upstream structural
  breaks remain separate from any optional impulse test: small closes qualify
  where source permits (DR AUDCAD).
- `body_engulf_v1`: bullish current body contains the immediately preceding
  bearish body's endpoints and closes strictly above its open; bearish mirror.
  This is **OUR CHOICE** for core engulfing, not a replacement for OC disrespect.
  Dojis do not supply counterdirection bodies. A/V comes from upstream causal
  closing-price turns; if unavailable at engulf close, eligibility waits.
- OC pairs are consecutive same-direction non-doji candles. **OUR CHOICE gap
  policy:** require junction distance exactly zero ticks (shared default), choose first candle close;
  nonzero gaps yield unresolved OC rather than arbitrary midpoint. Session OC
  disrespect uses close beyond OC without full-body engulf. E14 compound route
  additionally applies `body_engulf_v1` to the final counterdirection candle.
- `fvg_wick3_v1`: bullish gap `[high(i-2), low(i)]` when low(i)>high(i-2),
  bearish mirror `[high(i), low(i-2)]`. Minimum width one tick; known at bar i
  close. KL overlap includes boundaries, zero extra tolerance. Invalidate for
  new orders after first subsequent touch of the far edge; partial fills do not
  invalidate. Gaps do not automatically define source imbalance or a stop.
- `near_v1`: maximum distance 0.25 times arithmetic mean true range of the last
  20 closed entry-TF candles before pattern completion; no completed warmup
  means unresolved. This proximity/volatility convention is **OUR CHOICE**.
  For near-nontouch buy, next bar low must be above KL by 1 tick through this
  threshold and below preceding bar low; sell mirrors. This extra approach
  inequality is our operational reading, not stated teacher mathematics.
- Lower standing-extreme v1 is a **restricted, OUR CHOICE E5 geometry**: reference
  bar r; next closed bar s has low(s)<low(r), high(s)<high(r), close(s)>low(r)
  for buy; sell mirror. Require separately known direction/context and mapped
  V/A; source candle colour is unrestricted. The opposite extreme remains
  standing through confirmation completion. This deliberately incomplete
  adjacent-pair detector cannot claim all session/PDF shapes. Nonadjacent source
  mapping remains explicit data/contract work, not an inferred fourth model.
- PDF p8 EURGBP LONG says high-swept/low-standing/V; its reference pair remains
  unresolved. Emit `unresolved_source_referent` for that route/case. Never infer
  buy solely from swept-side labels or invent a fourth-man algorithm from
  attribution. No mandatory same-TF or half-TF engulf condition is added (DR
  CADCHF explicitly lacks the lower engulf).

## Continuation, re-entry, timeframe and level competition

Continuation is a phase, not a universal fifth confirmation algorithm. Require
fresh directional structure/role-change evidence appropriate to the selected
profile, former relevant KL now disrespected by directional body close, and
applicable liquidity/imbalance conditions. Plug role-flip continuation prefers
prior sponsored movement plus imbalance and IRL; core E14 continuation describes
shallow retracement/new IRL and overlap. Evaluate its direct or confirmation
entry family as declared. Prior sponsorship is an annotated preference unless
that selected profile explicitly requires it; disputed plug 2049–2053 negation
cannot create a filter. Prior level reuse is allowed; no universal first-touch
or freshness limit.

A missed origin may lead to a fresh continuation; prior participation is not a
prerequisite. A stopped position does not invalidate the story or authorize an
automatic retry. `reentry` requires a new eligibility episode: new structural
break/reaction/confirmation IDs under the chosen family. Do not repeatedly
submit the same consumed setup after stop or move an old missed order to a
later attractive KL. Contrary H4 evidence can cancel a pending entry without
reversing Daily; require explicit lifecycle decision and fresh nested evidence
when that profile demands it (T3 USDCAD). No profitable eventual path may erase
the earlier loss, cancellation or miss.

**OUR CHOICE deterministic selection v1:** enumerate relevant KLs from the
same active range and directional role, linked to the chosen structure and
liquidity episode; reject wrong-side/no-path candidates. Enumerate before the
retest. Rank overlap (when relevant to family), prior sponsorship, distance
from current executable price, then newest availability and stable ID; nearest
is a tie-break, not a teacher universal rule. Store every score and rejected
alternative. Source-specific extreme/QM/reused-OC selections override only in a
predeclared source profile, not by consulting future touches. Do not require
FVG where E14 complete AMS/near-IRL OC allows its absence.

Profiles declare supported TFs and priority at session start. Provide full
source-capable set H4,H3,H2,H1,M45,M30,M15,M5 (plus explicitly configured
M3/M2 refinements); unsupported TF/feed/calendar is unresolved scope. H4→H3→H2
scan and H2-over-H1 are named source selection profiles. **OUR CHOICE default:**
first eligible observation wins; candidates becoming eligible in the same
observation batch rank higher TF first, then declared family order, then stable
ID. Do not delay a valid H1 waiting for future H2 and do not retroactively
replace an executed H1. Persist selection before subsequent price information.

`nesting=off` is **OUR CHOICE default**. Optional `nesting=declared_chain`
requires a configured ordered chain (e.g. H1 break→reaction→standing extreme→
M30 engulf), with parent IDs and independently causal clocks at each stage.
A universal nested confirmation gate would reject taught direct alternatives.
Optional stacking uses new candidates and portfolio permission; **OUR CHOICE
paper default** portfolio selection delegated to engine; optional one active position per instrument, additional eligibility
still logged as `blocked_exposure`, not absent signal or failed source model.

## Risk and targets

```ts
type RiskPlan = {
  id: string; policy: 'source_structural' | 'teacher_source_stop'
    | 'owner_fixed11' | 'zone_edge_experiment';
  entryTicks: number; stopTicks: number; protectedIds: string[];
  protectionBoundaryTicks?: number; protectedAllRequired: boolean;
  warnings: string[]; availableAt: Time; sourceRefs: string[];
};
type TargetPlan = {
  id: string; mode: 'entry_erl' | 'source_explicit' | 'fixed_r'
    | 'story_destination'; entryTF: TF; rangeId?: string;
  targetRef?: string; priceTicks: number; storyDestinationRef?: string;
  nearerObstacleIds: string[]; availableAt: Time;
};
```

For structural protection collect the selected pattern wick, associated IRL
sweep extreme, protected structural extreme and relevant nearby KL/liquidity
which may normally be swept before expansion. **OUR CHOICE v1 nearby set:**
objects linked to the same range/reaction episode on the adverse side of entry
within `near_v1`, plus explicitly designated protected structural objects even
outside that distance. Record each membership reason. Buy boundary is minimum
of their price/extreme boundaries, sell maximum. Place stop beyond that boundary
with configured 0.5 pip padding (**OUR CHOICE shared default**, source discusses 0.5/1 pip
but does not prescribe this for every session). If geometry lacks a boundary,
mark unresolved; never equate a KL body price with an unseen sweep extreme.
Explicit source-protected next KL/H4 liquidity overrides the proximity cutoff
and remains in `protectedIds`. A narrowly protected engulf wick is insufficient
where the selected source model protects another liquidity/KL.

`teacher_source_stop` preserves an independently documented source price/reason;
a position box does not independently establish an FVG far edge.
`zone_edge_experiment` requires separately identified zone geometry and is a
separate experiment. Structural and fixed-stop runs never overwrite one another.

Owner preset `owner_aggressive_fixed11_v1` uses direct/aggressive enabled routes
with exact 11 pip risk (**OUR CHOICE exact value within the owner's approximate
10–11p preference**), rounded outward to instrument tick grid. It reports which
nearby protection objects lie beyond that stop; it must not claim structural
protection or teacher-stop fidelity. **OUR CHOICE:** preserve the fixed stop
rather than silently widen; an optional `require_full_protection` switch blocks
these orders and is a different policy run. Fixed11 requires explicit pip-size
metadata; non-FX units without a declared mapping are unsupported, not guessed.
Default paper sizing and exposure belong to the execution contract.

`entry_erl` selects nearest valid unswept external liquidity in the intended
direction of the selected entry-TF range, known before placement. **OUR CHOICE
v1:** ties use stable ID, no front-run offset. Counter-structural/retracement
plans cap at nearer opposing liquidity/KL obstacle instead of assuming full
opposite-range travel. If the selected target policy cannot resolve range or
nearer obstacle, do not invent an ERL. A sweep/rejection there versus later
body close-through is new observable evidence for a later amendment, not an
initial far target backfilled from outcome.

Story-origin next KL remains `storyDestinationRef` (Daily story→Daily KL;
H4 story→H4 KL even when H1 entry). It is never silently substituted for entry
ERL. Core fixed-R profile explicitly uses 3R (**OUR CHOICE default among stated
3/4R routines**). Owner fixed11 target policy must be named; **OUR CHOICE paper
default** `entry_erl`, with fixed3R a separate run. Risk/reward is derived from
entry/stop/target, not an invented universal 3R in source ERL examples. Manual
exits, BE, partials and front-running require timestamped specified instructions;
no MFE is realized profit and no automatic BE rule is inferred.

## Persistent event schema and deterministic order policy

Every event has `id, schemaVersion, instrument, tf?, observedAt, effectiveAt,
inputFactIds, storyId?, candidateId?, orderId?, policyId, sourceProfile,
evidenceRefs, payload`. Events append; corrections supersede by ID. Stable IDs
are hashes of instrument/alignment/family/phase/causal input IDs/policy version,
not evaluation time or future outcome.

Required event kinds:

- `entry_waiting`, `entry_unresolved`, `entry_eligible`, `candidate_selected`,
  `candidate_blocked` (reason, missing prerequisites and available alternatives).
- `order_intended`, `order_accepted`, `order_rejected`, `order_cancelled`,
  `order_replaced` (old/new ID and reason), `order_missed`, `order_expired`,
  `order_filled` (execution clock precision and bid/ask evidence).
- `risk_planned`, `target_planned`, `plan_amended` (old/new values and newly
  observable reason), `position_closed` (stop/target/manual/BE/ambiguous),
  `entry_consumed`, `new_episode_detected`.

**OUR CHOICE default:** shared paper default expiry is 1440 minutes, an OUR CHOICE operating setting (None disables it); cancel
on explicit story/entry invalidation, consumed setup, protection/target no longer
valid before fill, or explicit user/session cancellation. A new independent
candidate does not silently mutate the old order. No universal night ban or
news blackout. Offline/paper only; no broker execution or owner alerts activated.
Chronological execution fills cannot precede order acceptance; no limit fill
is inferred merely because a later chart contains its price. Preserve source
statuses (watch-only, missed, hypothetical, passed, cancelled, actual loss,
manual close and open) separately from automated policy outcomes.

## Build checks and limits

Before integration, independently review causal tests for H2 facts formed before
H4 close, H4 direct pool known but sweep future, intrabar reaction with later
H4 close-through, same-day lower confirmation, eligible-before-retest and
retest-before-eligible, IRL near-nontouch equality, OC partial-body disrespect,
standing-pattern reference ambiguity, simultaneous H1/H2 versus delayed H2,
optional nesting, wider protected KL, fixed11 shortfall, nearest ERL versus
story destination, miss→fresh continuation and loss→fresh setup without retry.
These are meaningful rule checks, not copies of fixtures or historical passes.

The restricted standing-extreme detector and selected engulf/FVG/proximity/KL
policies are reproducible automation choices with known coverage limits.
PDF p8 referent and missing historical clocks/feed mapping remain unresolved;
the build must expose them and cannot declare all-example fidelity until
independent source reconstruction and subsequent replay actually support it.

Executable alignment: bishop/v2/types.py uses uppercase BUY/SELL and snake_case; the conceptual TS names above project to those records. Shared defaults (exact OC=0, stop buffer=0.5 units, pending=1440min) override any earlier illustrative prose. source_all emits diagnostic alternatives, not a selected portfolio. Entry ERL requires the active entry-range confirmed delivery endpoint wick pool; arbitrary same-TF highs/lows are not ERL.

## Implemented optional nesting refinement

`nested_confirmation` is an optional named source profile and a diagnostic
alternative under `source_all`. The restricted T3-style implementation links
H4 positive structure, known IRL taken at H4 KL, H1 body break, subsequent H1 KL
reaction, H1 standing-extreme sequence and then M30/M15/M5 engulf into a causal
A/V limit. Every link carries IDs; no half-TF engulf gate applies to the standing
family itself. Missing lower A/V produces unresolved support. This is our
explicit chain geometry, not a claim that every taught nested refinement has
this one sequence. Default Bishop procedure remains unnested. Shared BAR,
PRIOR_PERIOD and SESSION liquidity records do not automatically qualify as IRL;
entry-layer single/series formation records carry explicit IRL lineage and are
exposed in EntryResult support. Counterweekly owner selection and nearer-target
guard use the story's initial relation and guard flag, not later weekly facts.
