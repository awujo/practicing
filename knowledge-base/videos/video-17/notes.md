# Video 17: Storyline 2

## Content type
Direct continuation of Video 16, worked in exhaustive Q&A detail with a
live student ("Dan Fodio"/"Dixon") pushing on exactly the right edge
cases. This video closes the biggest remaining gap in Video 16's bias-flip
state machine (what does NOT count as a valid flip signal) and gives the
clearest lead yet on the long-standing "QMR key level" mystery term.

## CRITICAL: What does NOT count as a storyline/bias change (completes
Video 16's state machine)
Directly answers a student question ("if it's only an open-close that
breaks on the next lower timeframe, can we still use it?"): **YES, you
can use it — but only to catch a RETRACEMENT entry, never to conclude the
storyline/bias has changed.**

- An **open-close break** (two consecutive candles forming an open-close,
  then price disrespecting/closing through it with an impulsive move) or
  an **engulfing** on the confirmation timeframe is explicitly INSUFFICIENT
  to validate a storyline/bias flip — even though it IS a valid ENTRY
  trigger (consistent with Sections 5's confirmation-entry patterns).
- The SAME chart event (open-close break / engulfing) means two different
  things depending on what question you're asking:
  - As an **entry trigger**: valid, tradeable — but the resulting trade is
    a **retracement/counter-trend scalp** within the still-active larger
    bias, not a new trend.
  - As a **bias-change signal**: NOT valid on its own. Only a full
    **breakout** or **sweep + break of structure** (Video 16's two
    confirmation shapes) on the relevant lower timeframe validates that
    the storyline has actually flipped.
- Directly reinforces and completes Video 16's bias-flip state machine:
  condition 3 ("next lower timeframe must ALSO fail to confirm continuation
  in the original direction") specifically means "must fail to give a
  breakout or sweep+break" — an open-close break/engulfing on that lower
  timeframe does NOT satisfy (or violate) that condition either way; it's
  simply a different, weaker signal category that doesn't participate in
  the bias-flip decision at all.

### Full worked example (weekly -> daily -> 4H round trip)
1. Weekly rejects a weekly key level, closes below -> bearish storyline
   starts.
2. Daily confirms with either a breakout or a sweep+break -> daily in
   sync with weekly -> continue selling.
3. Price sells down to the NEXT weekly key level (per Video 16's
   same-timeframe exit rule), reacts, and closes back ABOVE it by the end
   of that week.
4. This reaction/close alone is explicitly **not enough** to call the
   bias bullish. Must move one timeframe lower (daily) again and require
   a fresh breakout or sweep+break in the NEW (bullish) direction.
5. Until that daily confirmation appears, the weekly bias is still
   bearish — any daily-timeframe open-close break or engulfing seen in
   between is usable only as a retracement/counter-trend entry, not proof
   the trend has changed.
6. Same logic demonstrated again one level down: daily-key-level version
   of the identical round trip (daily reject -> 4H breakout -> price runs
   to next daily level -> reacts and closes back the other way -> 4H must
   ALSO give a fresh breakout in the new direction before the daily bias
   is considered flipped; a mere open-close break on 4H doesn't count).

### Minor timing clarification
The lower-timeframe confirmation candle (breakout/sweep+break) does not
need to occur on the SAME calendar day as the higher-timeframe rejection
— it can arrive the same day or a later day. What matters is current price
action at any given moment, not which specific day the confirmation
candle falls on. Non-issue for implementation as long as the state machine
evaluates continuously rather than resetting daily.

### Weekly bias-holding nuance (reconfirms Video 16, adds detail)
A weekly bearish bias does not mean every single day of that week sells.
Explicit example: Monday-Tuesday can show a retracement/buy move, then
Thursday-Friday resumes and continues the sell — the week still counts as
"bearish" overall even with mid-week counter-moves, as long as the
underlying storyline/state-machine conditions above haven't triggered an
actual flip.

## NEW (strong lead): "QM" / "QMR key level" — clearer, testable
definition
This video gives by far the clearest usable definition of the
previously-unresolved "QMR key level" term (open item since Video 7).
When multiple candidate key levels exist at the origin of a new setup
(e.g. both a more-tested level and a more-distant "extreme" level), the
video gives an explicit criterion for which one price is statistically
more likely to return to and play from:

- **A key level that was tested/respected MULTIPLE TIMES (e.g. twice)
  BEFORE finally getting disrespected** is preferred over a level that
  was disrespected on its first test, or a further "extreme" level that
  was never tested at all.
- **Quantified**: ~80% chance price returns to play the multiply-tested-
  then-disrespected level rather than continuing to the more distant
  extreme.
- The term "QM"/"QMR" appears to specifically flag this class of level —
  a key level with a history of being tested and holding before it was
  finally broken — as opposed to describing a particular shape (A/V/
  open-close). Some transcription ambiguity remains about whether "QM"
  ties to a specific shape or is purely about test-count/history, but the
  CRITERION itself (prior multiple successful tests before disrespect =
  higher-priority return target) is unambiguous and directly codeable.
- **Live chart confirmation**: a real 1H/30min example showed price
  ignoring both a fresh open-close level AND a more distant A-shape
  "extreme" level, instead returning specifically to a V-shape key level
  that had been tested once, respected (bought, closed above), THEN
  disrespected on the very next candle with an impulsive close below —
  exactly the "tested-then-disrespected" signature described above.
- **Implementation implication**: when multiple valid key-level
  candidates exist after a confirmed breakout/sweep+break, rank them by
  prior-test count before disrespect (higher test count = higher
  priority target), not just by proximity or shape alone. This refines
  Section 5's existing "quality signal" (imbalance overlap) and Section
  5's "disrespected-level priority" (recency/proximity) with a third,
  independent ranking factor: **test history**.

## Reconfirmed
- Video 16's core breakout vs. sweep+break distinction and same-timeframe
  storyline start/end rule, both reused directly and repeatedly in this
  video's worked examples.
- IRL/ERL dual-purpose framing ("attack liquidity, rebalance imbalance")
  explicitly invoked again to justify why the tested-then-disrespected
  level is the statistically preferred return point.
- Origin vs. continuation setup terminology (Section 5) reused in
  discussing the initial entry off the sweep+break.
- Strong emphasis on patience and journaling (sticky notes) — process-
  discipline framing consistent with Video 15's "pick one system" advice.

## Open items
- "QMR key level" — now has a strong, testable working definition (see
  above) rather than being purely equivalent to generic "key level" as
  previously assumed (Videos 12/13). Update Section 9 to reflect this as
  a resolved-with-caveats lead rather than a fully open question.
- Remaining ambiguity: whether "QM"/"QMR" strictly requires exactly 2
  prior tests, or "multiple" more loosely (once is explicitly described
  as sometimes insufficient, twice as clearly sufficient) — treat "2+
  prior successful tests before disrespect" as the working threshold
  until refined further.
