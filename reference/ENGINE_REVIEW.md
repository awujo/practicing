# Initial causal engine review and remaining scope

Baseline: `6fb133e`, Bishop branch. This milestone is an offline engineering
implementation, not completed teacher acceptance, paper deployment, or a
profitability result. The independent agents saved their changes and tests
before reaching their usage limit. A separate final reviewer subsequently
reviewed the combined runner, reproduced two integration defects, and verified
their fixes with seven new regressions. See `FINAL_ENGINE_REVIEW.md`; the final
full suite passes 204 tests.

## Independent review performed

`tests/test_engine_review.py` was written by the separate reviewer, exercising
prefix-stable structure, reference availability, invalid pre-broken references,
origin-candle closure, frozen targets, stop-profile separation, exact-vs-close
reference policy, forming-bar fills, bid/ask costs, gap stops, ambiguous fill
bars, missing hours and subhour order availability.

Corrections made while that review was active:

- A reference already broken before the origin touch cannot confirm the new
  story just because subsequent closes remain beyond it. Require a new crossing
  beyond an unbroken, known pre-touch reference.
- A KL wick excursion alone is not a structural liquidity sweep. Structure
  events identify their own explicit local-turn references.
- A setup available halfway through an H1 bar is censored for H1 execution;
  skipping that partial active hour could falsely invent a later fill or miss.
- The exact-open/close interpretation omits most actual feed junctions.
  `close_reference` is a separate, explicit first-close policy, not a fitted
  pip tolerance or silent change of defaults.

## Primary-agent integration corrections and tests

- Destination selection retires an opposing role after a known body close
  through it. Targets use prices observable when the context becomes eligible.
  A regression case proves an invalidated resistance is not reused as a target.
- Each order keeps setup availability, fill observation time, fill-bar interval
  and current observation clock separate. No exact intrabar fill is invented.
- Pending TTL expiry and story cancellation are distinct. Earlier expiry wins;
  an already filled position retains its own stop/target exits.
- Missing active H1 hours censor execution; full runner coverage failure blocks
  all observations. A later endpoint cannot prove the cache is complete.
- Bid/ask execution accounts for spread once; declared round-trip commission is
  deducted once. Opening-gap stops and declared stop slippage are adverse.
  Ambiguous stop/target bars use a labelled stop-first assumption. A target in
  an intrabar fill candle remains censored if its sequence cannot be established.
- Batch execution reuses one validated feed/calendar. Regression tests require
  identical results to separate simulations.
- Actual frozen-feed prefix tests compare historical setup events and known
  fills at several earlier clocks. Outcomes may develop later; earlier fills
  and setup prices must not change.
- Acceptance can ignore an unrelated unfilled order with a null fill time;
  it cannot replace a missing filled-trade timestamp with the observation clock.
  Pending orders still block an observed no-trade decision.

## What has not been certified

The structural reference policy is provisional latest-local-close-turn logic,
not a verified major-swing detector. The supported engine uses initial KL
rejection/prior-candle-sweep routes and two confirmation entry paths. Its target
is a known unbroken opposing origin-TF KL, not automatically Bishop's nearest
ERL. Simultaneous patterns are unranked candidates, not a portfolio or mandated
position stacking.

Role-flipped/reused origins, weekly-level/Daily fallback, multi-level engulfing
cascades, full storyline lifecycle and weekly alignment policy, direct H4/H2,
aggressive imbalance entries, H3/M30 execution, and live alerts remain open.
The conservative retirement policy is explicit; retiring a trading context is
not a claim that a structural bias flip occurred.

The saved EURGBP teaching window is an unresolved diagnostic. Its source is
FOREXCOM, while the frozen candles are IC Markets BID. Source timestamps and
documented execution states remain unknown. The forty source observations are
unchanged and no exact teacher match has been promoted or claimed. Do not widen
tolerances or select a profitable rule to make this diagnostic pass.
