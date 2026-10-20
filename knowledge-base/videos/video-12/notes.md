# Video 12: Bias Continuation Part 1

## Content type
Deep-dive on building bias mechanically, with a real EURUSD trade walkthrough. Explicitly frames the whole system as an IF-THEN mechanized algorithm — the closest thing to executable pseudocode we've gotten yet. Also resolves an important nuance: whether inducement liquidity is strictly required for continuation trades (answer: no, only for origin trades).

## "No POI" philosophy (explicit, important for implementation)
States directly: **"I don't drop POIs [Points of Interest]"** — he does NOT pre-mark anticipated reaction zones in advance the way typical ICT/order-block traders draw boxes ahead of time. Instead, key levels are identified **reactively**, based on realized candle closes as they happen. Implication for our backtester: level detection logic should be based on confirmed historical closes, not speculative forward-looking zones.

## "Reject and Close" (R&C) — formal shorthand introduced
Names the two-part confirmation criterion explicitly: price must (1) **reject** from a key level and (2) **close** beyond it (in the relevant direction). Shorthand: "R&C". This is the same mechanism as "candle closure" from earlier videos, now given a concise, reusable label.

## THE MECHANIZED ALGORITHM (explicit IF-THEN framing — closest thing to pseudocode given so far)
States the entire system as: **"if A, B, C happens, we do X, Y, Z"**:
- **ABC** = price taps a key level (any timeframe) -> rejects -> closes beyond it (R&C) in a direction.
- **XYZ** = scale one timeframe down -> look for EITHER (a) a liquidity sweep + break of structure, OR (b) an engulfing candle, confirming the same direction.
- Then: expect the next candle at that lower timeframe to serve as inducement/IRL -> gets swept -> the key level (ideally overlapping an imbalance) gets tapped -> price continues in the bias direction.

## IMPORTANT nuance: IRL is necessary for ORIGIN, optional for CONTINUATION
Directly answers a student question ("is internal range liquidity absolutely necessary to validate entry?"):
- For the **origin** of a trade (the very first entry establishing a new trend), IRL formation is effectively necessary to validate the setup.
- For a **continuation** trade (re-entering in an already-established direction), IRL is **not strictly necessary** — sometimes price taps a key level after an engulfing and continues immediately, without ever forming a subsequent IRL first.
- **Practical rule when IRL doesn't form on a continuation**: enter directly off the engulfing candle at the key level anyway, using a **tighter stop** (just past the engulfed candle's extreme + 1 pip, rather than the usual 10-11 pip default). This is a distinct, well-specified continuation variant worth implementing separately.

## Building bias doesn't always require the full top-down cascade
Clarifies Video 9's process isn't mandatory in full every time: sometimes it's sufficient to read "what the current structure is saying" on a **single relevant timeframe** (e.g. just 4H) without walking the entire Monthly->Weekly->Daily->4H cascade. The full cascade is the thorough/careful method; a single-timeframe read is a valid, faster alternative when structure on that timeframe is already clear.

## Disrespected-level priority refinement
When an open-close key level is disrespected (closed through) even after an engulfing seemingly confirms reversal, price will often still return specifically to that SAME disrespected level first — not jump straight to a more distant "extreme" level. Refines Video 11's "two-target strategy": **prefer the closer/more recently disrespected level over a distant extreme when both exist as candidates.**

## Real trade walkthrough (EURUSD)
Full multi-timeframe drill: 4H structure showed sweep + break above two structural points (closed above as body) -> A-shaped key level overlapping an imbalance -> price swept liquidity and rebalanced at that specific price -> confirmation entry on 1H showed a disrespect-with-impulsive-move (no IRL formed) -> entered anyway using the "no-IRL continuation" variant with a tighter stop just above the recent high -> traded to roughly 1:3.

## Reconfirmed
- Key levels remain dual-purpose (entries and exits).
- Explicit humility: "the market has a mind of its own" — acknowledged probabilistic, not deterministic; useful framing to carry into backtester expectations (this is an edge, not a certainty).

## Open items
- "QMR key level" still not explicitly defined, but its usage pattern across videos now looks like he just uses it interchangeably with generic "key level" in examples where the specific type (A/V/open-close) isn't the point being made — may not be a distinct concept at all, just a habitual placeholder term. Treat "QMR key level" as equivalent to "key level" going forward unless a clearer definition surfaces.
- Still pending: premium & discount, "10 trade rule".
