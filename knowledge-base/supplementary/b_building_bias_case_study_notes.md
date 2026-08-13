# Bishop Supplementary: "Building Bias Part 2 - Case Study" (Liquidity)

## Content type
Second installment of Bishop's "building bias" series (Part 1 covered key
levels, referenced but not itself in our video set). This one covers
"building bias with liquidity" — largely a restatement of the core
mentor cascade (sweep -> candle closure -> breakout/sweep+break on the
next lower timeframe, repeated recursively weekly->daily->4H) already
extensively documented in Sections 2-4. One genuinely new and valuable
risk-management nuance is introduced via a real EURCAD case study.

## Reconfirmed (no new mechanics)
- The core 3-part confirmation cascade, stated explicitly and generally:
  (1) sweep of liquidity at a higher timeframe, (2) candle closure
  confirming the reaction, (3) breakout OR sweep+break on the next lower
  timeframe. Applied recursively weekly -> daily -> 4H, identical in
  structure to Sections 2's storyline process.
- IRL/ERL cyclical framing ("price moves internal to external, back to
  internal, back to external") — same as Section 3.
- Bullish/bearish role reversal of a given high/low as IRL vs. ERL
  depending on prevailing structure — same logic as Video 18's Single
  Candle Formation concept, applied here at the weekly/breakout-candle
  level rather than named explicitly as "single candle liquidity" (though
  the phrase is used once too — "price give us what's a single candle,
  which is liquidity").

## NEW: Caution against over-extending countertrend targets when a
sweep runs opposite to structural bias (valuable risk-management nuance)
The case study's key point: after a bullish breakout, the breakout
candle's own HIGH can later get swept by price — which superficially
looks bearish (a high liquidity sweep) and might tempt a trader to target
the full opposite-side low. But since the OVERALL structure is still
bullish, price has "every right" to sweep that high and then CONTINUE
upward without ever reaching the low — the sweep does not override the
higher-timeframe bias (directly consistent with Video 16/17's bias-flip
state machine: a single sweep/reaction is not sufficient to flip
structural bias).

**Practical rule given**: if you DO take a short-term countertrend sale
off that kind of sweep (against the higher-timeframe bullish structure),
your exit/target should be conservative — **end at the nearest liquidity
point**, not the full opposite structural low — because price may react
from a nearby key level and resume the bullish move without ever reaching
the more distant target. Demonstrated on a real EURCAD chart: price swept
a previous weekly low (structurally bearish setup this time), and the
"safest" first target was the NEAREST liquidity, not the full further
extreme, even though price eventually did reach further in that instance.

**Backtester/bot implication**: this refines Section 6's exit-targeting
logic with an additional guard — when a trade is taken counter to (or as
a minor retracement within) the dominant higher-timeframe structural
bias, cap the target at the nearest liquidity point rather than a full
opposite-structure extreme, since continuation of the dominant bias can
resume before the far target is reached. This is conceptually adjacent
to, but distinct from, Section 5's "retracement vs. bias-change"
distinction (Video 17) — here the emphasis is specifically on TARGET
SIZING for such trades, not just on whether they're valid to take.

## Reconfirmed
- Recursive cascade logic (same pattern at every timeframe pair) —
  consistent with Video 16-18's timeframe-agnostic framing.
- Candle-closure discipline still described as "very important," matching
  Section 4's wick-vs-close rule.

## Open items
- No new terminology. 4 of 6 Bishop videos remain to be processed.
