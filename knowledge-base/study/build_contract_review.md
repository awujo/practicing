# Independent build contract review

2026-10-23. Review baseline: STRATEGY.md, IMPLEMENTATION_HANDOFF.md and FULL_SOURCE_SYNTHESIS.md; existing engine/API inspected independently. This is a rolling contract review, not source-example acceptance or an all-matches guarantee. No engine edits or external calls performed.

## Initial integration findings

1. **Major/local blocker:** `bishop/structure.py:events` replaces each active high/low with every latest local close turn; `bias.py:find_stories` confirms against `refs[-1]`. Labelling this OUR CHOICE does not implement protected major-reference retention. New build must preserve local candidates separately and test course7's old protected high through a wick-only weak-low sweep, then migration after body break (STRATEGY §11 / synthesis structural language).
2. **Lifecycle blocker:** `engine.py:_context_end` retires on origin-level close or any later opposite confirmed story, without scope/retracement association. This is currently disclosed operating retirement, not L02 story-flip implementation. New story contract must distinguish parent/origin scope, entry invalidation, retracement and positively confirmed major reversal; expiry/cancellation remains OUR CHOICE where source does not dictate it.
3. **Coverage blocker:** engine supports 28 FX pairs, H1 base resolution, only engulf/OC entry routes and origin-KL targets. `COMPUTED_SUPPORTED_ROUTES` is appropriately bounded today; replacement API must retain route/instrument/resolution support results rather than upgrading successful computation into complete-method or teacher-match status. H3/M45/M30/M15/M5 and non-FX examples require explicit support or unresolved replay status.
4. **Execution fidelity:** `execution.py` explicitly marks fill-bar TP as censored but assumes stop-first and requested-price fills, with H1 observed clocks. These are OUR CHOICE simulation policies, not historical facts. Teacher replay must not accept inferred stop-first outcome or hour-end fill as exact source execution when sequence is unresolved.
5. **Shared tokens:** `ctrader/tokens.py` defaults shared `settings` tokens to borrowed/read-only, blocks refresh before network request, and preserves this in memory fallback. No active shared-token mutation found. `store.py:_open_client` comments misleadingly describe token refresh; update comments when implementing. Empty `CTRADER_TOKEN_TABLE` enables separately owned refresh and must not be silently selected by paper/offline defaults. `bishop/db.py` generic SQL helpers do not enforce namespaces themselves: audit every new write and migration; existing comments alone are not enforcement.
6. **Causal strengths to preserve:** input validators reject future/forming bars; point availability occurs at reversal close; simultaneous local sweeps cannot prove sweep-before-break; same-day origin/confirmation eligibility waits for both closes. New finer-resolution paths must preserve these invariants while permitting source-authorized reaction intrabar entry separately from direct-H2's closed-H4-breakout prerequisite.

## Contracts reviewed so far

- `study/build_story_contract.md` (initial partial draft through initial candidates): evidence clocks, separate origin/level TFs, historical role epochs, no copied old confirmations, no universal sponsorship veto, explicit candidate supersession choices are appropriate. Remaining confirmation/lifecycle sections not yet present, therefore not certified.
- Structure, entry, data/execution and paper/app contracts: not yet present at initial review; no certification implied.

## Actionable questions for story draft

- Explicitly label strict-one-tick touch/break/rejection and fallback supersession as **OUR CHOICE**, including version IDs. The current prose identifies them as price/operating policies, but the source does not provide numeric thresholds.
- Scope Bishop small-break exception to evidenced contexts; a blanket no-impulse rule for every Bishop role flip would exceed the specific small-H4-break evidence. Preserve profile/source context and unknown status elsewhere.
- Ensure the pending confirmation section permits related same-day patterns without requiring every constituent to start after origin close, while disallowing unrelated old breaks. Test event-prefix invariance.

## Second pass: structure, entry, data/execution drafts

Reviewed `build_structure_contract.md`, `build_entry_contract.md`, and `build_data_execution_contract.md` as present on disk. Source check: `full_entry_study.md:59–63` supports the course14 compound OC route's final-body engulf plus OC break; retaining that separately from session OC disrespect is appropriate.

**Resolve before implementation:**

1. **Shared schema mismatch:** story uses uppercase directions, snake_case clocks and status enums; entry uses lowercase/camelCase and quality enums; structure Clock lacks occurrence interval. Establish one executable evidence/clock/type module plus explicit adapters. A source citation/`quality=source` cannot turn numerical derived geometry into a teacher fact.
2. **OC policy disagreement:** structure `oc_exact_junction_v1` requires C1=O2, entry permits distance <=1 tick and chooses C1. Both are OUR CHOICE; choose a shared default or expose separately named profiles and preserve results. Do not implement different OC definitions by importing whichever module happens to run.
3. **Occurrence precision:** structure §4 states all closed-bar occurrence=end. That is correct for the completed body-close assertion, but wick touch/sweep occurred somewhere within the interval. Preserve `[bar.start,bar.end]` for intrabar contact and end/receipt for availability. Do not manufacture exact sweep timing for replay.
4. **Near-nontouch execution:** entry `engulf_irl_retest` places an anticipatory limit but adds sweep-before-KL-touch as a fill prerequisite. An accepted ordinary limit cannot retrospectively decline an actual touch. Either prove the ordered crossing from the known geometry/quotes, retain ambiguity, or explicitly use a contingent monitored intent and record its activation. Gap jumps must remain distinct from an observed traded sweep.
5. **Bounded route coverage:** entry's adjacent standing-pair policy is openly restricted and PDFp8 remains unresolved. Keep those limitations in support matrices and final completeness claims. An unresolved original referent cannot be counted as implemented full example mapping.
6. **OUR CHOICE migration restriction:** structure requires linked earlier high-side sweep for protected-high migration. This is labelled a conservative choice, not proven universal doctrine; replay must distinguish unavailable sweep evidence from source contradiction. Local child containment based on close endpoints is also chosen and can exclude wick-contained cases. Keep both explicit policy IDs and unresolved cases.

**Positive contract properties, not implementation certification:** structure now freezes major references and keeps child counter-BOS separate; data contract requires instrument/calendar/price-basis manifests, M1 for lower TFs, missing-path censoring, strict ordering, append-only management, and unsupported requests as non-success. This directly addresses initial integration blockers. Preserve exact teacher-profile fidelity versus owner-preset performance separation.

Remaining at this pass: story confirmation/lifecycle sections and paper/app contract not yet available. No absent section certified.

## Executable shared contract and first modules

Reviewed `build_shared_contract.md` and `bishop/v2/types.py`: shared uppercase/snake_case records, exact-OC default, occurrence intervals and ordinary anticipatory near-nontouch limits resolve the corresponding second-pass contract disagreements. Immutable nested evidence and causal price identity have independent regression coverage in `tests/test_v2_review.py` (3 passed). These tests exercise price-grid rejection, negative prices, policy identity, correction identity, delayed publication and deep immutability; they are not teacher replay.

Reviewed paper/app contract: proposed namespace, transaction/outbox/revision boundaries, Telegram owner authentication, no-network defaults and explicit activation separation are appropriate. Its complete implementation remains to be reviewed.

**New implementation blocker:** `bishop/v2/risk.py:plan` selects nearest target from every same-TF HIGH/LOW Liquidity object, without active range/ERL-role qualification. A pool's form/side alone is not its IRL/ERL role (STRATEGY S03/S07/L05). Require a causal external-role/scope relation; absent classification returns unresolved. Keep prior-extreme/fixed-R/story-KL alternatives separately named.

**Boundary validation:** StrategyPolicy currently accepts unknown profile strings and bool/fractional values in integer-count fields. Reject invalid configuration at the settings/policy boundary; do not silently turn an invalid profile into a legitimate unresolved market condition. Shared price records other than Bar also lack explicit integer-tick validation, so feed and module boundaries must ensure no fractional/bool prices enter causal objects.

`stories.py` was partially written through `_destination` during inspection; no conclusion on complete lifecycle yet. Its confirmation search deliberately rejects unresolved touch/BO ordering and uses historical role lookup, which should be preserved. Review actual major/local event scope once structure and full storyline implementation are saved.

## Feed/aggregation first implementation review

Independent regression `test_aggregation_reports_completely_missing_nominal_bin` currently fails: complete M1 data for hours0 and2, absent hour1, aggregates into H1 with `coverage.status=COMPLETE`. Grouping only existing rows omits wholly empty nominal bins. Enumerate expected bins over the evaluated range and expose missing active intervals; never let a disappeared bar silently bridge structure or execution state. Latest targeted run: **1 failed, 3 passed**; failure intentionally records an unresolved blocker.

Other actionable checks: aggregation should reject duplicate base intervals, mixed instruments and unexpected closed-calendar rows if callable beyond validated load_feed input. `utc_epoch_v1` currently floors arbitrary-duration bins from midnight rather than epoch, differing for non-day-divisor TFs (H5/M7); either reject unsupported refinements or implement the declared anchor. Feed metadata currently validates a minimal required subset, not the full frozen-manifest contract (calendar versions/hashes, provider identity, asset class and declared file hash). Verify an expected content hash when supplied; do not market minimal manifests as complete historical feed provenance.

## Structure first implementation review

Actual structure now emits separate close-turn A/V and exact OC, causal wick clocks and frozen major-range versions. Remaining scope concern: sweep seeds use global `(None, side)` keys; nested same-side seeds can overwrite each other despite the per-scope/reference/leg contract. Review and retain independent scoped seeds before claiming nested coverage. At inspection the only emitted liquidity form was TURN_LEG; BAR/SERIES/prior-period/session forms were absent, therefore full source-liquidity coverage was not demonstrated. Builders may add them subsequently; this is a point-in-time finding, not a final unsupported declaration.

## Subsequent actual integration review

The missing-whole-bin regression now passes (implementation updated by builder). Risk target code now requires the active range endpoint liquidity ID, addressing the prior nearest-any-pool concern.

Latest targeted suite after new independent checks: **8 failed, 4 passed**. Confirmed integration failures:

- Story lifecycle emits `STORY_DESTINATION_REACHED`; entry active-state filter recognizes `DESTINATION_REACHED` instead. Later entries remain allowed after the emitted destination event.
- Story output uses `initial_weekly_relation=COUNTER_WEEKLY` and `counterweekly_target_guard_required`; risk checks unrelated `counterweekly`/`retracement` keys. The nearer opposing-KL target guard does not activate on actual story records.
- Policy accepts unknown source/risk/target profile strings, boolean/fractional ATR periods, and string-valued weekly toggle. Six parametrized failure cases demonstrate invalid configuration accepted before market evaluation. Public settings validation is stronger but direct engine/CLI policy creation must enforce the same contract.
- `allow_counterweekly=False` currently sets a story `owner_selection=BLOCKED_COUNTERWEEKLY` annotation; entries do not inspect it. Engine selection must enforce the prohibition before orders.

Additional entry relation concern: direct-H2 parent matching uses only `p.occurred_to >= br.occurred_from OR p.available_at <= br.available_at`; this admits nearly any earlier H4 break or arbitrarily later H4 break, without explicit same reaction/range lineage. Same-clock eligibility alone does not establish relatedness. Retain relation evidence or mark unsupported/unresolved rather than borrowing unrelated old direction.

## Paper/app implementation review

Inspected settings, paper_store, runner and webapp. Actual HMAC uses Telegram's WebAppData derivation and constant-time comparison, duplicate fields/age/owner checks; authenticated APIs use it. All observed SQL writes target allowlisted bishop_ tables. No network activation found.

**Material scope gaps:** persistence currently stores complete report snapshots/projections, without loading ongoing order/position state into the runner, aggregate version checks, leases or resumable checkpoints. An earlier-as_of report under another slot can overwrite a newer order/story projection. This is an offline report store, not yet the durable ongoing paper reconciliation promised in the app contract. Require chronological projection guards and prior-state reconciliation before claiming restart-safe paper operation.

API jobs queue requests but no observed worker executes them; ranges/as_of are not semantically validated. `/api/bias/state`, authenticated artifact retrieval and cursor pagination are not implemented at inspection. HTTP request size check trusts Content-Length and does not limit chunked body bytes; missing rate limiting remains an app-contract gap. These limitations should remain explicit while builders finish; none is a basis for live-readiness claims.

## Integration re-review after fixes

Latest independent suite: **18 passed**. Regressions now cover malformed policies; entirely missing aggregate bin; actual destination-event state; counterweekly guard caps a known active ERL without fabricating ERL when absent; boundary cancellation precedence; stale projection protection; engine rejection of invalid mapping duration; partial empty/unsupported-resolution status; and engine STORY_FLIPPED cancellation through actual simulation.

A deterministic nonempty full pipeline (48 versus72 H1 bars, predeclared seed41, source_all/fixed-stop/fixed3R synthetic policy) preserves complete prefixes of stories, setups, orders, story events and execution events. This proves that engineering example only, not all data/model cases or historical source fidelity.

Root engine re-review confirms pending_action/STORY_FLIPPED cancellation, direct-mapping validation and missing-slot segment resets, causal exposure cap, explicit independent-alternatives mode, and PARTIAL_UNVALIDATED for missing/empty/unsupported resolution. Entry builder replaced broad H2 temporal OR with enclosing-H4 or latest-preceding episode association, and included delayed prerequisite clocks in nested/series readiness.

Optional impulse assessment uses preceding ATR only, never globally gates raw breaks, and defaults to unknown without the optional policy. An independently added delayed predecessor-close test now passes: no unpublished ATR predecessor can qualify impulse. Synthetic test is not calibration of the optional fraction.

**Measured performance concern:** 180 H1 bars source_all probe exceeded60 seconds and was terminated. A bounded5-second stack sample found `structure.role_at → entries._role → select_level → detect_setups` repeatedly sorting/scanning role history. 72 H1 bars took approximately0.48 seconds. Root notified to index role histories before historical-scale claims. This is measured usability debt, not a trading-rule mismatch.

App agent added stale-asof guards and merges observations/positions into order cards; schema_version compatibility is addressed. Runner replay adapter now joins actual order/setup/story metadata and preserves interval-fill exact time as null. Its risk→legacy-mode map is explicitly an implementation mapping, not demonstrated source-stop equivalence; interval fills still cannot receive exact-time acceptance. Ongoing runtime remains a full-recompute snapshot importer/manual queued worker, not an incremental live/paper runtime certificate.

## Final added-layer review

Independent session regression verifies that a wholly missing required base slot and an unpublished constituent prevent publication of session highs/lows; once complete, both extrema use all source bars and max constituent availability. Session boundaries are explicit, DST ambiguity is rejected without fold, and structure filters supplemental pools by their own availability before classifying bars. No new causal/gap blocker found in this layer.

RoleIndex now has independent equivalence coverage versus the reference historical query, including unborn levels and same-clock opposing role events. The specified `(available_at,id)` ordering is preserved. This checks optimization equivalence, not teacher authority for tie policy.

Optional `zone_edge` checks pass for BUY and SELL outward far-boundary stops and missing-geometry unresolved behavior. The geometry remains the explicitly labelled fvg_wick3 experiment; it is not a universal teacher stop rule.

New management-input regressions initially failed: terminal AMEND accepted NaN stop; terminal MANUAL_CLOSE raised Decimal.InvalidOperation after attempting close instead of rejecting invalid input at the boundary. Data builder notified for finite numeric validation in both event-loop and terminal-action paths. Materialize management action input before multiple passes, or document/reject non-sequence inputs; generators otherwise lose unknown-order validation and cannot hash cleanly.

## Root verification after final corrections

Management nonfinite validation is fixed before ledger writes; both independent
regressions pass. Engine materializes management inputs and validates causal
order references. Final complete repository suite: **228 passed** (including
24 independent v2 checks). The 180-H1 synthetic full pipeline now takes2.027s
after RoleIndex integration; the earlier >60s finding is addressed for this
measured case, without claiming historical-scale bounds. See
`BUILD_VERIFICATION.md` for exact engineering scope and remaining acceptance.

## Continued causal-risk audit — 2026-10-24

New independent `tests/test_v2_risk_review.py` initially demonstrates six failures and one positive range-version check:

- BUY entry100 with selected protected pool110 returns ELIGIBLE/stop109; SELL mirror returns stop91. Wrong-side pool must not become invalid directional geometry or crash Setup construction.
- Proximity ATR includes pre-gap segment history instead of requiring current contiguous warmup.
- A level explicitly formed in the old segment becomes current stop protection after a gap.
- An already-consumed nearby liquidity pool remains labelled protection without fresh intact liquidity evidence.
- A target touched in a completed bar overlapping delayed pool availability is treated as known intact because the implementation ignores bars whose start precedes availability. Unknown touch ordering must remain unresolved.
- Positive check passes: latest known BROKEN range is not revived by a future version.

Root owns risk fixes. These are independent causal/integrity defects, not teacher-price fitting, and no expected historical values changed.

Entry/native-gap checks in `tests/test_v2_entry_episode_review.py` pass (four tests): role flip-back does not revive a retired reaction; segment change/new same-scope break retire pairing without global child/simultaneous veto; pool-taking is observed before reaction and does not consume future information; native LEVEL_UNAVAILABLE retirement preserves prefix history, waits for delayed observation, agrees with RoleIndex, and remains terminal after later role changes. This review does not certify cross-TF gap propagation or all historical examples.

Risk fixes independently inspected after saving: wrong-side selected pools excluded, directional result geometry checked, segment-local ATR/protection used, consumed/overlapping pools excluded, and exclusions documented. All six original failure cases now pass. Native/entry suites also pass.

One additional delayed-publication boundary remains demonstrated by `test_unpublished_internal_bar_cannot_be_skipped_to_complete_atr_warmup`: a bar unavailable at the historical decision clock is filtered out, allowing the available bars on either side to count as a complete ATR window. The original segment_id has not changed because the delayed row physically exists in the frozen feed. The risk warmup must stop across that unavailable observation rather than silently bridge it. This is not an ordinary calendar closure. Root notified; no production edit by reviewer.

## Protection-link refinement review — 2026-10-24

Independent risk/entryepisode suites now **14 passed**. The delayed internal-publication gap no longer supplies a false completed ATR warmup. Added explicit no-link versus linked protection checks: with entry100/local pattern low95 and an older containing range pool80, no causal link gives stop94; an explicit range-ID link permits stop79. This tests relevance evidence, not a teacher-specified universal stop distance. Wrong-side range-pool regressions now supply that explicit link, so geometry validation is still tested rather than bypassed by absent evidence. The overlap-target regression now requires target None specifically.

Source and numerical fixture prices remain untouched; policy version distinguishes changed protection semantics. Cross-TF gap propagation remains outside this particular signoff.

## Cross-TF gap propagation and late-publication review

New `tests/test_v2_continuity_review.py` confirms that a base gap makes an old Weekly level unavailable before the next Weekly candle close, but only at the post-gap bar receipt clock; old story suspension is UNKNOWN, cancels dependent pending orders and leaves positions unchanged; a fresh later origin is not suspended. Gap event availability now includes both hashed source-bar dependency receipt times. These three checks pass.

A fourth full-engine check confirms unresolved retrospective history loss when an internal bar first arrives after later bars: early available bars0–1 and2–3 create a gap known at3h, but adding the delayed1–2bar (first available5h) makes the final chronological batch erase that earlier gap. This is first publication, not a corrected price. An explicit correction/rebuild mode can have different semantics, but must not be represented as availability-causal event-prefix replay. Acceptable remedies are receipt-ordered knowledge/gap-resolution events or explicit rejection of unsupported nonmonotone publication; the regression allows fail-closed rejection. Root notified while frozen receipt=end feeds continue unchanged. No production or fixture changes by reviewer.
