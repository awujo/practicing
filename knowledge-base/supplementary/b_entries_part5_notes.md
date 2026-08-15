# Bishop Supplementary: "Entries Part 5"

## Content type
A dedicated, systematic breakdown of entry/confirmation methodology —
the clearest single explanation of "what to do after you have your
bias" across all of Bishop's supplementary material. Opens with a
theoretical/diagrammed section (no real charts) explicitly naming and
defining THREE distinct entry approaches, then applies them to 5 real
pairs: XAUUSD, GBPUSD ("GU"), EURUSD ("EU"), EURAUD ("Euro AED"), and
GBPCAD ("JVP card"). This is the most valuable single video for pinning
down exact entry-model terminology and priority, since Bishop explicitly
ranks the approaches by his own preference rather than just describing
them neutrally.

## NEW: Three named, explicitly-defined entry approaches, ranked by
Bishop's own stated preference
1. **"Direct entry via H2 scale-down"**: after a confirmed H4 breakout
   closes, immediately scale down to the H2 timeframe and look for that
   timeframe's own breakout-with-liquidity, then take a limit order
   directly at the nearest key level to that H2 liquidity — no additional
   confirmation candle required on H2 itself. Fastest but least confirmed.
2. **"Direct entry at the H4 key level"**: skip the H2 step entirely and
   place a limit order directly at the H4 single-candle-liquidity/key
   level itself, expecting price to sweep it and reverse from there. Even
   faster/more aggressive than #1, no lower-timeframe confirmation at all.
3. **"Confirmation entry"**: wait for price to actually trade into the H4
   key level and give an observable reaction, THEN look for one of the
   familiar confirmation triggers (breakout, sweep+break, or engulfing) on
   a lower timeframe (explicitly stated as flexible: H3/H2/H1/M45/M30/M15/
   M5, "depends on you"). **Bishop's explicit personal ranking**: of the
   confirmation-entry sub-types, a plain **breakout** or a **sweep-and-
   break** are his stated favorites ("personally, I would tell you these
   two... your losses are going to be minimal compared to other forms of
   confirmation entry"), ahead of a plain **engulfing**.

This is a genuinely new, precise formalization of what earlier notes
(Sections 5/5B, and multiple Bishop videos) had already gestured at as
"aggressive vs. conservative" entry styles — this video gives the full
3-way taxonomy with an explicit internal ranking, rather than a rough
2-point spectrum. **Backtester/bot implication**: the entry-model
selector should support all three as distinct, independently-triggerable
paths (not just a binary aggressive/conservative flag), and when multiple
paths would trigger concurrently, prefer breakout/sweep+break over a bare
engulfing per Bishop's own stated preference — directly actionable
config-level guidance.

## NEW (minor): explicit stop-loss-tightness guidance under a specific
confirmation pattern
For the "low swept, high still standing" V-shape confirmation entry
pattern (already documented from prior videos), Bishop adds the explicit
detail that this specific pattern most reliably shows up on the immediate
next-lower timeframe from wherever the H4/H3 setup was seen (e.g. if it
appears on H4, it's very likely to also appear on H2 or H3) — offered as
a cross-timeframe validation check, not a guarantee ("it doesn't always
appear all the time").

## Reinforced
- Explicit, blunt statement that NO confirmation type is a guarantee
  against a stop-out: "none of these are insurance from stop loss... stop
  loss is everybody's food." Directly reinforces the probabilistic framing
  already in STRATEGY.md and prior Bishop risk-management notes.
- "Price moves from internal to external liquidity and back again" —
  restated again as the closing rationale on the EU (EURUSD) trade.
- Bullish/bearish structural continuation logic (a swept high in a
  bullish trend doesn't necessarily mean price must reach the low) —
  reconfirmed on the GU (GBPUSD) example, consistent with the Building
  Bias 2 case-study notes' target-sizing guard.
- Multiple pairs where Bishop explicitly narrates uncertainty about his
  own exact entry timeframe/level from memory ("let me check my
  journal... I can't remember or figure it out") before confirming from
  the chart — an honest, unscripted demonstration that even the trader
  himself relies on the chart record rather than memory, consistent with
  prior risk-management honesty notes.
- An explicit missed-entry admission (XAUUSD 1H level): "it's quite an
  annoying buy to miss... there's always another setup."

## Visual verification pass
Re-transcribed via `transcribe.yml` (video_slug `bishop-entries-part5`,
source: the `defi-bishop` GitHub release) and verified with 10s-interval
frame extraction across all 5 real-trade windows, read directly,
cross-referenced against the TradingView symbol sidebar in-frame (a
stable 5-pair watchlist: XAUUSD, GBPUSD, EURUSD, EURAUD, GBPCAD, matching
the transcript's pair sequence exactly). "GU" is confirmed as trader
shorthand for GBPUSD, "EU" for EURUSD, "Euro AED" is unambiguously
**EURAUD**, and "JVP card" is unambiguously **GBPCAD** (same garble
pattern as the Trades Breakdown 3 video). Confirms real, concretely-
marked levels behind every example: XAUUSD daily ray ~4,040 and 3H rays
~4,170/~4,065; GBPUSD daily rays ~1.34274/~1.34950; EURUSD 4H ray
~1.15600; EURAUD 2H rays ~1.64100/~1.63840; GBPCAD 4H ray ~1.88700. No
corrections needed to the mechanical claims — the opening theoretical
section (0:00-~13:30) is freehand-drawn diagrams rather than real charts
and was reviewed via the transcript text only, which is sufficient since
it contains no chart-specific claims to verify.

## Open items
- No new terminology, but a genuinely valuable formalization: the
  3-way entry-model taxonomy (H2 scale-down direct / H4 direct / lower-
  timeframe confirmation) with Bishop's explicit internal ranking
  (breakout & sweep+break preferred over plain engulfing) is worth
  encoding directly into the backtester's entry-model configuration.
