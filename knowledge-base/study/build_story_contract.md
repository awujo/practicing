# Bishop story contract v1 — proposed build policy

2026-10-23. Contract only: no detector changes, fixture fitting, historical acceptance or live activation. Source authority: `knowledge-base/STRATEGY.md` D01–D06/L01–L05, `knowledge-base/study/IMPLEMENTATION_HANDOFF.md`, `FULL_SOURCE_SYNTHESIS.md`, `full_bias_story_study.md`, and `full_session_study.md`. Source alternatives below remain distinct from our algorithms. Numerical primitive definitions belong to the structure/level contract; this contract consumes versioned, causal evidence rather than silently treating current local turns as major structure.

## Evidence and immutable records

Use UTC timestamp instants with instrument/calendar identity; price uses integer instrument ticks. An occurrence is an interval `[earliest, latest]` when finer timing is unavailable, not a fabricated exact time. `available_at` is when all required data are observable. Closed-bar events normally have occurrence within that bar and availability at its close. IDs are deterministic hashes of feed, symbol, model/policy version and causal evidence IDs. Never hash a later outcome into an ID.

```text
EvidenceStatus = KNOWN | UNKNOWN | UNSUPPORTED | AMBIGUOUS_ORDER
Direction = BUY | SELL
Clock = {occurred_from, occurred_to, available_at, resolution, ordering_proof_ids[]}
Evidence = {id, kind, tf, clock, reference_ids[], status, source_refs[], policy_ids[]}
Level = {id, formation_tf, price_ticks, geometry: A|V|BULL_OC|BEAR_OC,
         formed_at, available_at, definition_policy, role_events[]}
LevelRoleEvent = {id, level_id, role: SUPPORT|RESISTANCE|UNDECIDED,
                  reason: FORMATION|DIRECTIONAL_DISRESPECT,
                  break_evidence_id?, impulse_status, clock}
Reaction = {id, side, story_origin_tf, level_origin_tf?, origin_bar_id,
            origin_kind: KL_REJECTION|PRIOR_CANDLE_SWEEP|ENGULF_ORIGIN,
            level_id?, role_event_id?, prior_candle_id?, reaction_clock,
            origin_close_clock, close_evidence_id, anchor_episode_id}
Confirmation = {id, kind: BREAKOUT|SWEEP_BOS, side, tf, structure_scope,
                break_id, sweep_id?, reaction_id, reference_id,
                relation_proof_ids[], clock}
Story = {id, side, story_origin_tf, level_origin_tf?, route, source_profile,
         reaction_ids[], intermediate_engulf_ids[], confirmation_ids[],
         eligible_at, parent_story_id?, weekly_context_snapshot,
         destination_revision_ids[], lifecycle_events[], policy_version}
```

Every record carries evidence status and missing prerequisites; missing direction is `UNKNOWN`, never implicit SELL. Geometry, current usable role, reaction direction, structural direction and weekly alignment are separate fields. Source citations are attribution, not executable events. Explicitly uncertain historical facts cannot be promoted to KNOWN by this contract.

## Level history and reuse

Source: A normally sells, V normally buys; OC and A/V can be body-disrespected, retested and repeatedly flipped (B1 AUDJPY buy→sell→buy). First-touch-only is unsupported globally. Our default `reuse_until_role_changed_v1` retains every level and immutable touch/rejection/respect/break history. Reactions use the role known at the reaction, not today's role. A body close through a role generates a disrespect observation; activation of the opposite role additionally obeys the applicable source profile's impulse rule. Bishop's explicit small-break contexts use strict one-tick close-through with no impulse gate; core contexts requiring impulse consume the separately named impulse classifier. If that classifier is unavailable, opposite-role eligibility is UNKNOWN, not rejected or assumed. Exact touch is `low <= level <= high`; directional rejection closes strictly on its usable side. Equality does not reject or break. These are our price policies, not teacher-supplied tolerance rules.

A newly role-flipped level can react only after that role event is available; its breaking bar cannot retrospectively serve as a rejection of its new role without ordered finer evidence. Repeated same-role reactions create new episodes; prior confirmation cannot be copied into them. Prior respect/sponsorship is recorded by event IDs/counts and can rank a candidate only under a declared selection policy. The disputed plug sponsorship sentence never becomes a hard veto. Levels sharing price remain distinct formations; a canonical price-group ID can prevent duplicate orders while retaining provenance.

## Initial origin candidates

For each completed origin bar, independently emit:

1. `KL_REJECTION`: a previously available, currently usable level is touched and bar closes strictly on the proposed side. Store its role epoch. Level formation TF need not equal story origin TF only on an explicitly supported route such as Weekly-level/Daily fallback.
2. `PRIOR_CANDLE_SWEEP`: previous completed candle's low is strictly exceeded and current closes above that low for BUY; previous high strictly exceeded and close below for SELL. Candle colour is irrelevant. No KL is required. A close beyond the swept boundary is not this rejection model.
3. `ENGULF_ORIGIN`: only under the named earlier-course profile that explicitly permits it, with engulf primitive and source origin evidence preserved; never silently fill a missing KL price. Later structural synchronization still applies as below.

Both KL and sweep candidates may coexist. They remain separate evidence paths, with an optional shared episode group; neither is an extra universal requirement. A bar sweeping both prior extremes may yield opposite provisional candidates. Preserve both; the operating selector suspends opposing eligibility at the same scope/time until resolved by subsequent evidence. A candle-close observation cannot prove intrabar ordering.

Candidate phases: `WAIT_ORIGIN_CLOSE → WAIT_CONFIRMATION → CONFIRMED`; `UNKNOWN_EVIDENCE`, `SUPERSEDED`, and `ORIGIN_INVALIDATED` are explicit alternatives. The reaction can be observed provisionally before close, but story eligibility for these closed-origin routes always waits for the origin close. No fixed expiry is inferred from source. Our default retains candidates until role invalidation, origin-close invalidation or a newer same-direction reaction on the same level/role epoch supersedes an unconfirmed candidate. Supersession is an operating choice and never erases earlier evidence or an already confirmed story.

## Related confirmation and the two clocks

Source permits same-day and next-day confirmation (v17@1248–1272). Our `reaction_link_v1` defaults are causal, not a next-day rule:

1. Locate the first qualifying touch/sweep within the candidate's origin interval using the finest available evidence. Freeze an `anchor_episode_id` and its interval. A price range that merely contains the level proves touch occurred sometime, not its exact clock.
2. Before that episode, freeze the applicable active structural reference set supplied by the structure contract: opposite-side reference for the proposed break, its major/local scope and protected-origin lineage. A confirmation must break a reference that was observable and unbroken before the episode, or a newly formed post-reaction reference explicitly descended from this episode. Do not select the latest unrelated local high merely because it eventually breaks. Missing reference scope leaves the corresponding route UNKNOWN.
3. Accept only the first fresh directional close-through of each still-unbroken reference. The confirming crossing must occur after the episode, with causal ordering established by disjoint intervals or finer ordered observations. It may occur before origin close. If reaction and break occupy the same coarse bar with unresolved order, return AMBIGUOUS_ORDER; refine data rather than invent sequence.
4. Require no intervening origin-direction invalidation, role change against the candidate, or episode supersession before eligibility. Confirmation links explicitly to this reaction and its reference lineage. A cached BO before this reaction, including the B1 Gold latest-rejection/no-new-H4-BO case, cannot confirm it. An old reference broken and later crossed again is not a new BO; it requires a separately initialized structural range/reference.
5. `eligible_at = max(origin_close.available_at, confirmation.available_at, all reference/role/relation evidence availability)`. All dependencies must be KNOWN by `as_of`. If the directional break occurred Monday afternoon and Daily rejection closes Monday night, story becomes available Monday night, never afternoon. A Tuesday break becomes available Tuesday. Delayed structure confirmation can delay availability beyond occurrence; retain both clocks.

A `SWEEP_BOS` additionally requires a linked opposite-side liquidity sweep in the same episode/range followed by the fresh directional structural break; the sweep's reference was available before its sweep. Consume sweep association after a break/range transition. Source structural BOS and continuation BO labels come from the structure state, not the presence of any historical wick sweep. A plain valid BO does not require a retest to confirm direction. Absence of a retest concerns the limit order only.

If exact touch time is unknown but a lower bar certainly precedes the breakout bar, that bar's close is a conservative relation-availability bound; preserve its occurrence interval. If origin starts or lower coverage are absent, forbid same-origin-bar relation certification. Post-origin-close confirmation can still qualify against a known reference and witnessed later reaction relationship; do not fabricate the start from calendar arithmetic.

No universal maximum confirmation delay is source-established. Default is event invalidation/supersession, no time TTL. Optional TTL must emit `POLICY_EXPIRED` and cannot be reported as teacher invalidation.

## Cascade and fallback routing

Use an explicit route graph, not a general search for whichever TF later works:

| Route/profile | Origin / intermediate / terminal requirement | Published identity |
|---|---|---|
| `kl_structural` | KL reject+close, next selected context TF BO or sweep+BOS | Story origin TF / level formation TF / terminal confirmation TF |
| `candle_sweep_structural` | Prior-candle sweep+appropriate close, next selected context TF BO or sweep+BOS | Same three fields; level TF nullable |
| `course_early_engulf_cascade` | Explicit source-permitted origin and lower-TF engulf; descend one more declared rung for structural synchronization | Preserve intermediate engulf TF and terminal BO TF |
| `course_storyline_engulf_cascade` | W reaction+close → D engulf → H4 BO/sweep+BOS, linked to that reaction | W origin, D intermediate, H4 terminal |
| `bishop_weekly_daily_fallback` | W rejection exists without matching D structural confirmation yet; Daily reaction+close at SAME W level → H4 BO/sweep+BOS | D origin, W level, H4 confirmation |
| `plug_weekly_daily_fallback` | Same level and direction; at least TWO closed Daily rejections → linked H4 BO/sweep+BOS | D origin anchored to latest qualifying Daily reaction; W level |

Default context ladders are M→W, W→D, D→H4 and H4→H1. An engulf cascade uses the next declared rung, e.g. M→W engulf→D structure; generalized cascades are our explicit extension of the taught pattern and marked `POLICY_EXTENSION` until source-supported, not teacher replay passes. Only the directly documented W→D engulf→H4 branch is source-confirmed as this later-course cascade. Earlier sources allowing engulf alone get `ENGULF_CONTEXT` evidence/provisional direction; they do not become structural confirmation by relabelling engulf as BO. Entry engulf at H1/M30 is a different entry event and does not necessarily trigger further descent of story context.

Bishop fallback default minimum Daily rejection count is 1 (`bishop_one_or_two_v1`); plug default is 2 (`plug_at_least_two_v1`). These are profile-specific, not a universal count. For plug count consecutive completed Daily reaction bars at the exact same level ID, role epoch and direction; a nonreacting Daily bar resets this conservative count. Consecutiveness is our declared choice because the source does not uniquely specify grouping. Store all counted IDs and the latest reaction anchor. A post-first/pre-second H4 BO may qualify only if it follows the latest reaction with proven ordering; do not reuse its older relationship because the count later reaches two. Further fresh reactions supersede only unconfirmed fallback candidates by the policy above.

Create the fallback at its own eligibility time whether or not a future Daily BO eventually confirms Weekly. Weekly stays `WAIT_CONFIRMATION`; later Weekly confirmation is a new event, never backdated into earlier fallback trades. If Weekly confirmation becomes available simultaneously with fallback, preserve both causal paths and deduplicate trade opportunities by episode/entry evidence. Use source profile attached before replay; never choose 1 versus 2 after seeing whether an example wins. Missing Weekly rejection/level identity means fallback UNKNOWN, while an independently valid ordinary D story remains possible.

The v17@1133–1144 exception “unless it was engulfing that started the previous storyline” is retained as `ENGULF_STARTED_PREVIOUS_STORY_EXCEPTION_UNRESOLVED`. Do not infer an automatic engulf-only endpoint flip. Preserve the narrated alternative as an unsupported/unknown exception requiring source-specific evidence, with no trade authorization from this flag.

## Weekly context and route selection

Snapshot separate weekly structural direction, confirmed Weekly story direction, latest provisional Weekly rejection/sweep, and Monthly context; they can disagree. `weekly_relation = ALIGNED | COUNTER_WEEKLY | UNKNOWN | CONFLICTED` is relative to a declared reference, default `confirmed_weekly_story_else_known_weekly_major_structure_v1`. Record that reference ID and availability; provisional weekly candle colour/rejection is never silently substituted for a confirmed story. If confirmed Weekly story and weekly structure disagree, mark CONFLICTED with both facts and policy-chosen reference.

Source permits Daily/H4 counterweekly routes (v9, WN, DR), sometimes favours alignment and sometimes declines a reversal. Our source-coverage mode emits both with labels. Proposed owner paper selection default `allow_counterweekly_with_near_guard_v1` allows known counterweekly Daily/H4 stories only when a known nearer liquidity/KL guard is available; it holds UNKNOWN/CONFLICTED weekly cases for selection while preserving directional evidence. This is a conservative operating choice, not a rule invalidating D-only source examples such as BE EURGBP. Source-example replay applies the example's documented route, including D-only with unknown W/M, instead of this owner selector.

Counterweekly setup plans must identify the first relevant opposing liquidity/KL obstacle as a trade guard; no assumption of the full opposite Weekly-range target. If competing guard definitions cannot be resolved by the liquidity/target contract, keep plan `WAIT_TARGET_EVIDENCE`. Passing or sweeping a nearer obstacle does not automatically extend TP; a declared target amendment needs new evidence and time. A body close through the guard can be new structural evidence, assessed normally. Weekly context changes cause a new context event and selection reassessment, not rewritten historical labels or automatic filled-position exit.

Selection default: emit all causally valid story alternatives. For simultaneous same-side routes sharing reaction/confirmation use one opportunity group, deterministic primary display key `(source_profile, route, origin_tf, story_id)` without deleting alternatives. Opposite stories at same scope/time produce `DIRECTION_CONFLICT`; no new owner order until one is invalidated or later positive evidence resolves it. Cross-scope opposing stories coexist as parent/retracement rather than being forced into a single global direction. Historical source participation remains independent of owner selection.

## Destination and story lifecycle

Source: ideal destination is next opposing KL on STORY ORIGIN TF (v16@822–970); nearer ERL/fixed R are trade targets. Our default `nearest_known_opposing_origin_kl_v1` chooses at eligibility from active opposing-role levels on story origin TF, strictly ahead of the eligibility close, available by that clock; order by tick distance then formation availability then ID. Level validity consumes the level contract's known role/impulse state. Freeze selected level ID, role epoch, price and selection snapshot. A D story using W level seeks D destination, not W merely because its origin level was Weekly. Missing destination leaves `destination=UNKNOWN` and story direction can still be confirmed; owner entry selection can separately wait for target evidence. Our ranking is an implementation default, not evidence that the teacher always chooses this exact KL. Later newly formed/invalidated levels create timestamped proposed destination revisions, never change initial destination silently; default selection waits for explicit new eligible continuation/reassessment to adopt them.

Maintain orthogonal states rather than one enum:

```text
confirmation: PROVISIONAL | CONFIRMED | UNKNOWN
progress: BEFORE_DESTINATION | DESTINATION_REACHED | BEYOND_DESTINATION | UNKNOWN
origin_support: HOLDS | COMPROMISED | INVALIDATED | UNKNOWN
flow: CONTINUING | RETRACING | FLIP_PENDING | FLIPPED | UNKNOWN
selection: ELIGIBLE | PAUSED | RETIRED | UNKNOWN
```

| Observable event | Story update | New pending-order policy (ours) | Filled position |
|---|---|---|---|
| Destination touched | `DESTINATION_REACHED`; retain direction | Retire new continuation orders tied to the initial destination | No implicit exit; execute its existing TP/management plan |
| Endpoint opposite rejection+origin close | Create linked opposite origin candidate; `FLIP_PENDING` | Pause new old-direction placements at endpoint | No implicit close/stop move |
| Only lower engulf/OC disrespect | `RETRACING`; create separately labelled retracement entry evidence where allowed | Do not label full flip; old pending may be paused by its setup policy | Existing protection/management remains |
| Related new-direction structural confirmation at required scope | Confirm opposite story; old `FLIPPED`; link successor | Cancel unfilled incompatible old-story orders at evidence availability | Exit only on explicit position-management policy/event |
| Opposite lower-TF break below required story scope | Record local counterflow/retracement | Default cancel affected unfilled setup if its protected reference broke; require fresh setup | Does not itself flip major story or auto-exit |
| Origin level directional close-through/role lost | `origin_support=COMPROMISED`; invalidate unconfirmed origin | Pause/cancel orders relying on that role | Not sufficient alone to prove opposite story; no auto-exit |
| Protected story structural origin body-broken | `origin_support=INVALIDATED`, selection retired | Cancel dependent unfilled orders | Respect explicit management rule; no invented opposite trade |
| Trade stop/loss, missed retest or pending expiry | No directional flip | End that order; fresh eligibility required for any retry | Preserve realized outcome |
| Data gaps / unresolved ordering | Evidence UNKNOWN; pause selection | Do not invent fill/cancel precedence | Execution path censored until resolved |

Positive endpoint flip requires opposite reaction on the old story's origin TF (normally its next KL), proper origin close, and related next-lower structural confirmation in the opposite direction; cascade variants retain their explicit profile requirements. Mere absence of continuation, candle colour, destination touch, a stopped entry, or entry-TF OC break is insufficient. A fresh unrelated opposite story can coexist pending explicit scope reconciliation; “latest opposite candidate” is not a global flip rule. Structural invalidation can retire the old selectable story without supplying any confirmed opposite direction.

The source does not uniquely define a universal protected-story origin or numerical invalidation threshold; require a KNOWN protected structural reference from the structure contract. If unavailable, emit `PROTECTED_ORIGIN_UNKNOWN`; do not secretly substitute reaction candle wick or a local pivot. The cancellation default based on lost setup support is still permitted as an operating policy with its own reason. Continuation needs a fresh breakout/reaction/liquidity/entry evidence chain appropriate to its model; it neither requires taking the original trade nor permits automatic retry after loss.

## Pending orders, positions and event reduction

Use immutable `LifecycleEvent {id, subject_id, kind, evidence_ids, occurred_interval, available_at, policy_id, payload}`. Commands are separate: `CancelPending(order_id, reason, effective_at)`, `AmendPosition(position_id, new_stop/target/size, reason, effective_at)`, `ClosePosition(...)`. A story event alone is not a position command. Setup dependencies list exact story, role, liquidity and protected-reference IDs, so local contrary break can cancel only affected plans. Cancellation/replacement examples (T3 USDCAD) remain CANCELLED original plus fresh replacement, never moved hindsight entry.

Default owner pending handling: cancel on invalid setup dependency, confirmed incompatible same-scope flip, destination reached, or an explicitly configured expiry; pause placement on endpoint uncertainty/conflict. No universal news/session/overnight expiration or holding cap. Require a separately declared pending TTL in a run config if selected; absent TTL means no time expiry. Filled positions ignore pending expiry and pending cancellation. They continue under the initial protective stop/TP and only explicitly configured timestamped management changes. Default management supplies no automatic BE, partial or discretionary stall exit. A source replay may record a narrated manual exit without inventing its numerical algorithm.

Reducer at each observation clock: validate data/availability → append primitive facts → evaluate role/structure transitions → form/revise related reactions and confirmations → update stories/context/destinations → emit pending eligibility/cancellation decisions → evaluate entry selection. New orders cannot fill before their own availability. Execution already active over the just-observed interval is handled with chronological finer events, not retroactively canceled from a bar-close fact. Same unresolved interval containing fill and cancellation is `AMBIGUOUS_ORDER`/censored, not silently “cancellation wins”; a conservative paper estimate may report a separately labelled scenario. Equal-clock facts are all evaluated as a batch before new placement; deterministic ID ordering only stabilizes serialization, never asserts physical event order.

## Integration boundary and required checks

Existing `bishop.bias.Candidate/Story`, `find_candidates`, `find_stories` carry useful origin/availability fields but currently enforce first-use levels and limited local-turn D01/D02 routes. Migrate through explicit versioned adapters; do not represent newly supported fields as arbitrary strings squeezed into old `trigger`. `Story.target` becomes a backwards-compatible projection of the initial ORIGIN_KL destination, never nearest ERL. `level_tf`, origin TF, intermediate TFs and terminal confirmation TF must survive serialization separately.

`bishop.structure.TurningPoint/StructureEvent` provide clocks and local scope; local events cannot assert major structure without the new structure contract. Existing `bishop.engine._context_end` conflates operational retirement causes; replace later with explicit lifecycle reasons and pending commands, retaining historical outputs as old policy results. Existing `execution.Order.cancel_at` must apply to unfilled orders only; position-management events need a separate channel. Existing H1-only coverage cannot prove M45/M30/H3 intrabar sequences or unsupported instruments/calendars. Unsupported resolution/TF/feed must be reported, not mapped to the nearest available TF. No current API behavior is source authority.

Required causal checks for implementation review (not teacher fixtures):

- Prefix invariance: append future bars without changing any prior evidence, eligibility, role history, destination or order outcome known at that prefix.
- Same-day reaction then H4 BO then D close yields eligibility at D close; next-day BO yields later eligibility. Same-bar ambiguous sequence remains ambiguous.
- Old H4 BO before latest Daily rejection cannot confirm it; first crossing consumes reference; fresh new lineage may confirm later.
- Level respects twice, flips, reacts in flipped role, flips again; every reaction references its historical role epoch, with no blanket touch retirement.
- Independent KL-only and prior-sweep-only origins work; double-extreme/opposing paths remain conflicts without invented direction.
- W rejection/D engulf remains unconfirmed until related H4 structure; engulf-only endpoint retracement does not flip; unresolved spoken exception is visible.
- Bishop fallback count1 and plug count2 differ explicitly, use same W level, retain D origin; later D BO does not backdate W confirmation.
- Destination hit and entry stop do not flip; endpoint reaction plus positive opposite confirmation does. Unknown protected structure remains unknown.
- Counterweekly/D-only source routes survive source coverage despite owner selection choices; nearest guard is separate from story destination.
- Cancelled unfilled plan versus already filled position have different effects; replacement needs fresh evidence; pending expiry never creates a holding exit.

Review must inspect the contracts against source ledgers before engine edits, then review implementation independently before teacher replay. Exact teacher matching remains unresolved until verified historical evidence and causal replay exist; no speculative geometry or selection default can promote missing facts to acceptance.

## Executable interface reconciliation

The authoritative shared interface is `knowledge-base/study/build_shared_contract.md` and `bishop/v2/types.py`: snake_case, uppercase BUY/SELL, immutable common records, `policy.id`; `Event.evidence_status` carries knowledge quality while kind/details carry runtime lifecycle. The executable story layer is `bishop/v2/stories.py`, `find_stories(bars_by_tf, structures, policy=StrategyPolicy()) -> StoryResult(stories, events, reactions, support)`.

The shared operating default `pending_minutes=1440` overrides this document's proposed no-TTL default for the actual v2 owner run. It remains an explicitly configured operating expiry, never a teacher structural event. `fallback_rejections` is explicit policy; plug profiles enforce minimum two, Bishop profiles minimum one. Shared `allow_counterweekly=True` preserves counterweekly candidates with a required target guard flag; entries/selection must establish the guard rather than assuming the frozen story destination is ERL.

`structure.role_at` returns potential BUY/SELL roles from raw close breaks. The story adapter permits those raw breaks under the named Bishop source family, reflecting the session small-break contexts, and refuses raw-only flipped-role eligibility for core/plug profiles pending explicit `IMPULSE_CONFIRMED` evidence. This is a scoped engineering approximation, not a claim every Bishop level/timeframe has a teacher impulse exemption. Source-specific cases requiring impulse remain unresolved under this broad Bishop profile until narrower profiles or a named classifier are added. The raw structure observation itself never asserts impulse.

The first implementation resolves a confirmation's scope from a known range's `seed_break_event_id` or scoped event ID; only DEFINED range lineage supplies known protected structure. Local/provisional stories remain explicitly UNKNOWN for protected origin and cannot claim a major endpoint flip. `RANGE_BROKEN` yields story invalidation/cancel-dependent advice separately from opposite-story confirmation. A same-scope endpoint successor additionally requires ROOT/CHILD scope compatibility; local counterflow remains retracement evidence. Source variants not numerically established, including the engulf-started-story exception and experience-only no-Daily-structure route, remain visible unsupported support records.

Remaining implementation limitations must be visible in review: reaction relation currently freezes a reference available before the first witnessed contact; the alternative of a newly formed post-reaction reference requires explicit episode lineage and is not silently approximated. The W/D-engulf/H4 cascade uses a labelled body-engulf algorithm, whose numerical definition is our choice. Protected structural lineage can still be unknown. The broad Bishop role profile needs finer per-context impulse qualification. These are implementation coverage limits, not successful teacher matches.
