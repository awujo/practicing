# Video 16: Storyline 1

## Content type
Dense, foundational video explicitly combining "storyline and entries" —
introduces several genuinely new, codeable rules rather than just
reinforcing prior material: a precise **breakout vs. sweep+break-of-
structure distinction**, the **"storyline starts and ends on the same
timeframe's key level"** exit-targeting rule, and a **bias-flip
confirmation state machine** (don't reverse bias on a single higher-
timeframe reaction alone). This is one of the most implementation-critical
videos processed so far.

## Minimalist charting philosophy (minor, process note)
States the end-goal chart should have only 2 tools visible: (1) a
vertical/horizontal line tool for marking key levels, (2) a long/short
tool for direction. Explicitly permits more markup as a personal learning
aid ("might be what best works for you") — not a rule that markup itself
is wrong, just a stated end-state goal of simplification over time. Not a
mechanical rule, no code implication beyond confirming the No-POI
philosophy (Section 5) — no boxes/order-block zones, just levels + bias.

## NEW: "Breakout" vs. "Sweep + Break of Structure" (BOS) — precise
distinction (important, previously conflated)
Prior videos used "sweep+break" as the general confirmation mechanism.
This video draws an explicit visual/structural distinction between two
sub-patterns that BOTH confirm the same directional bias but look
different on the chart:

- **Sweep + Break of Structure (BOS)**: the "textbook"/cleaner pattern —
  price sweeps a prior swing point (wicks through), then reverses and
  breaks/closes through a structural point, producing a visible
  lower-high-then-lower-low (or higher-low-then-higher-high) sequence.
  Explicitly stated to be the LESS common of the two on higher timeframes
  ("many times you're NOT going to see price giving you a breakout like
  this").
- **Breakout**: the MORE common pattern actually observed — price gives a
  more direct, continuous move through the external range liquidity /
  prior low (or high) WITHOUT first sweeping and reversing — a steadier,
  less choppy directional push. This is described as "many times... going
  to be like this" — the default expectation, not sweep+break.

**Both are valid confirmation signals for order-flow direction/timeframe
sync** — they are not different conclusions, just different visual
shapes of the same underlying "is this timeframe in sync with the higher
one" check. Implementation implication: the confirmation-detection
function should accept EITHER shape as valid, not require the stricter
sweep-then-reverse BOS pattern exclusively — treat "breakout" (a plain
directional break of the relevant range extreme) as an equally valid,
in fact statistically more common, confirmation.

### Cascade mapping rule (new): breakout on TF(n) -> sweep+break on TF(n-1)
When a higher timeframe (e.g. 4H) shows the plain "breakout" pattern
(rather than a clean sweep+break), the NEXT timeframe down (e.g. 1H) will
typically show the standard liquidity-sweep-and-break-of-structure
pattern. i.e. a "breakout" one level up commonly resolves into a proper
sweep+break one level down. Useful as a expected-pattern lookup when
cascading down timeframes for confirmation.

## NEW: "Storyline starts and ends on the SAME timeframe's key level"
(major exit-targeting rule)
The single most important new rule in this video. If a directional bias
(storyline) originates from a reaction at a key level on a given
timeframe, the expectation is that the SAME storyline will conclude
(reverse) at ANOTHER key level on that SAME timeframe — not at a lower-
timeframe key level, even though entries and intermediate reactions
happen on lower timeframes throughout the move.

- Example given: bias built from a **daily** A-shape key level -> 4H gives
  a breakout -> 1H gives sweep+break of structure -> entry taken on 1H.
  The IDEAL exit target is the NEXT **daily** key level — not the 1H or 4H
  key level the entry was taken from.
- Explicit cautionary trade narrative: a trader who takes profit /
  breakeven at a lower-timeframe (e.g. 1H or 4H) key level, reasoning that
  price "looks like it's reacting there," often watches price continue on
  toward the real (daily/weekly) target afterward — described directly:
  "your entry was right but your exit was wrong." This is presented as a
  common, specific mistake to avoid, not a hypothetical.
- Applies recursively at every scale: a storyline built from the 4H ends
  at the next 4H key level; one built from the weekly ends at the next
  weekly key level; one built from the daily ends at the next daily key
  level — exit-target selection must match the timeframe the ORIGINAL
  bias/storyline was built from, not the timeframe of the entry trigger.
- **Refinement — first take-profit priority within that**: even when
  targeting the correct higher-timeframe key level, the standard IRL->ERL
  liquidity progression (Section 3) still applies at the ENTRY timeframe
  first: e.g. if the entry came from a 4H setup, the first natural
  take-profit point is that same 4H timeframe's own external range
  liquidity (ERL) — price may retrace from there before continuing on
  toward the ultimate higher-timeframe (daily/weekly) target. So exit
  planning has (at least) two tiers: a nearer partial/first-target at the
  entry-timeframe's ERL, and the ultimate target at the next same-
  timeframe-as-the-bias key level.

## NEW: Bias-flip confirmation state machine (don't reverse on one
higher-timeframe reaction alone)
Directly specifies exactly when a higher-timeframe bias should be
considered to have flipped (e.g. bearish -> bullish), which is stricter
than "price rejected the other way at a key level":
1. Price trades into the NEXT key level on the storyline's origin
   timeframe (e.g. next weekly key level, if the storyline was built from
   weekly).
2. Price rejects from it AND closes in the new (opposite) direction
   (candle closure/R&C, per Section 4).
3. **AND** — critically — the NEXT LOWER timeframe (e.g. daily) must ALSO
   fail to give any further continuation confirmation (no breakout, no
   sweep+break of structure) in the ORIGINAL bias direction.
Only when ALL of these hold is the bias considered flipped. If the higher
timeframe rejects/closes the new way but the lower timeframe still shows
a valid continuation confirmation in the OLD direction, the rule
explicitly says: keep trading the original direction until the lower
timeframe stops confirming it. This directly resolves a real ambiguity
(a higher-timeframe candle closing the "wrong way" does NOT by itself
flip the bias) — a precise, codeable state machine rather than a single-
condition check.

## Reconfirmed
- Full top-down cascade mechanics (weekly -> daily -> 4H -> 1H) walked
  through in detail again, consistent with Video 9/10's storyline process.
- IRL -> ERL sequential liquidity progression (Section 3) reused directly
  in the exit-tiering discussion above.
- Engulfing as the standard 1H/lower-timeframe confirmation trigger,
  creating a fresh A/V-shape key level to play (consistent with Videos
  11-15).
- Stop-loss sizing again mentioned casually as ~10-12 pips ("it doesn't
  matter" — precise number treated as flexible/non-critical, consistent
  with Video 13's "personal preference" framing).
- "Repeat the same process consistently" and "your own business is the
  process, not the pip count" — reconfirms the process-over-outcome
  philosophy already implicit in earlier videos, now stated very directly.

## Open items
- No new terminology introduced (no new "QMR key level" mentions).
- The breakout/sweep+break distinction and same-timeframe exit rule are
  significant enough that the backtester's core state machine needs both:
  (1) a confirmation-detection function accepting EITHER breakout OR
  sweep+break shapes, and (2) an exit-target selector keyed to the
  timeframe the ACTIVE bias/storyline originated from, not the entry
  timeframe.
