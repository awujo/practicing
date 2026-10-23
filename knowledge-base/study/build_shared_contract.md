# Shared executable contract for the v2 build

The source pass is complete. These are our explicit numerical/data choices,
not additional teacher facts. The new implementation is isolated in
`bishop/v2/`; the bounded legacy runner and its historical reports remain
available without silently changing their meaning.

## Common records and decisions

`bishop/v2/types.py` is the executable interface. Use its immutable `Instrument`,
`Bar`, `Clock`, `Event`, `Turn`, `Level`, `Liquidity`, `Story`, `Setup`, `Order`
and `StrategyPolicy`. All directions are uppercase BUY/SELL, field names use
snake_case, and times are aware UTC. Class-specific helper records may extend
these contracts, but must not redefine their fields independently.

- Prices use integer instrument ticks. Declared tick/distance units are required
  by feed manifests; off-grid data is rejected, not silently rounded to improve
  a match. Negative prices are possible. Cost hypotheses may use decimal ticks.
- `Clock` preserves occurrence bounds and first availability. A completed body
  close occurs exactly at close; wick contact/sweep retains its bar interval.
  Availability is the maximum of receipt/close and dependency clocks.
- `Event.evidence_status` describes knowledge quality. Event kind/details carry
  lifecycle state. `Story.state` and `Setup.status` are distinct runtime states.
  A source citation is attribution, not proof of numerical geometry.
- IDs hash causal inputs and policy identity, never later outcomes. A policy's
  ID includes all parameters. Bar IDs include source identity, time and OHLC;
  appending input preserves old IDs, while corrected candles change identity.
- Default OC policy is exact same-direction junction, `oc_gap_ticks=0`. A
  nonzero alternative is an explicit different policy result; no implicit
  one-tick broadening. A/V uses close turns independently of candle colour.
- Range initialization/promotion follows the structure contract's disclosed
  conservative policy; major/provisional/local scope remains visible. Unknown
  source initialization does not become a confident direction.
- Default proximity is 0.25 of the prior20 closed entry bars' arithmetic ATR;
  `fvg_wick3_v1` is the explicit three-candle wick-gap experiment, not a proven
  universal source imbalance definition. Both remain named policy choices.
- An engulf/near-nontouch order is an ordinary anticipatory LIMIT once its past
  formation conditions qualify. Its expected future sweep is not a retrospective
  veto on actual fills. Record gap/sequence uncertainty; do not invent an order
  that can decline a past touch. A future contingent-intent mode would require
  its own activation events and execution contract.
- The default paper expiry of1440minutes is an operating policy, not teacher
  invalidation. Story cancellation is an append-only action, not a future
  cancellation time silently embedded in the original order.
- The source model profile, risk profile and target profile remain independent.
  Bishop context-liquidity protection/nearest-ERL is separate from the owner's
  aggressive fixed11-unit preset. Source risk boxes are not fed into detectors.

## Module interfaces

`structure.analyze(bars, policy)` returns a result with `turns`, `levels`,
`liquidity`, `events` and `ranges`. Scoped events expose their reference ID,
reference availability, root/child/local scope and frozen origin lineage.
Level-role changes are events; querying a prior time never uses today's role.
The structure module supplies `role_at(level, events, as_of)`.

`stories.find_stories(bars_by_tf, structures, policy)` returns `stories`,
`events`, `reactions` and `support`. Confirmations link a witnessed related
reaction to positive structure. Occurrence may precede origin closure; readiness
still waits for all required facts. Scope-blind opposite breaks do not flip
major stories. Fallback and engulf cascades retain their route identities.

`entries.detect_setups(bars_by_tf, structures, stories, instrument, policy,
story_events=())` returns `setups`, `events`, `support` and `imbalances`.
Missing stop/ERL/data produces an explicitly unresolved candidate, not a false
eligible order. Inputs are complete causal bars; there is no fixture lookup.

`feed.load_feed(path, manifest, as_of, history_start=None)` returns instrument,
base bars, coverage and source hashes. `aggregate` supplies complete bars at
requested TFs with nominal bounds and coverage diagnostics. H1 cannot support
M45/M30/etc. Calendars/anchors come from explicit manifests; provider-native
exceptions must not be guessed from asset names or desired outcomes.

`simulation.simulate(orders, bars, instrument, costs, as_of, actions=())`
returns append-only `events`, `observations` and `positions`. Its observations
preserve fill intervals, initial plan, management, costs and censoring. No
automatic break-even/partial/manual close is invented. Strict unresolved
ordering is censored; legacy stop-first remains a separate diagnostic policy.

The root integrates `engine.run` and the v2 CLI. Reports include instrument/input
and policy hashes, coverage and per-route support; stories, setups, orders,
execution observations/events and summaries. Successful computation is not an
all-teacher-match certificate. The paper application consumes this JSON result;
no broker-order adapter or external activation belongs to this build.

## Work ownership

Root owns shared types/policies, engine assembly and CLI. Other builders own
structure, stories, entries/risk, feed/aggregation/simulation, and paper/app
modules respectively. A separate reviewer checks integration as files arrive.
Complete the source-route build before historical teacher replay. Necessary
engineering checks remain separate from example acceptance and may identify
bugs during construction. No expected fixture or tolerance may be changed to
obtain a pass.
