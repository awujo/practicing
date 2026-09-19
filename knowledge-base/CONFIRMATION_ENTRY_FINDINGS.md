# Confirmation entry triggers: what the source says vs what we built

From `bishop-entries-part5`, 06:15-09:30, read off the extracted frames
with the transcript beside them. Recorded before any code changes, for
the operator to correct.

## What he enumerates

At 06:15: *"you're looking for one of four things or three things as the
case may be."* Then, in order:

1. **A breakout** in the intended direction (06:30-06:45)
   *"you want price to give you a breakout... I just want to see price
   give you a breakout to the upside."*

2. **A sweep of liquidity + break of structure** (06:45)
   *"price gives you what a sweep of liquidity and a breakout
   structure."*

   Of these two, at 07:00: *"personally, I would tell you these two...
   if you have these two, [missing it] is a missed entry."* He rates
   them highest.

3. **A disrespect of an open-close key level** — which he CALLS an
   engulfing (08:00-08:45)
   *"two consecutive bearish candles that were disrespected... Two
   bearish candles... This gives you a bearish open-close key level...
   But then price disrespects this guy."*

4. **The 4th man** (from 09:30 onward, described separately)

Summarised by him at 09:15: *"a bearish breakout, a bearish sweep+break,
or a bearish disrespect at open-close."*

## What the engine implements

`_reaction_trigger()` tries exactly two things: `is_engulfing()`, then
`fourth_man_confirmation_level()`.

| his trigger | engine |
|---|---|
| breakout | **missing** |
| sweep + break of structure | **missing** |
| open-close disrespect ("engulfing") | **implemented as something else** |
| 4th man | implemented |

## The one that is wrong, not just missing

`is_engulfing()` is the classic candlestick engulfing: `prev` bearish,
`curr` bullish, `curr.open <= prev.close`, `curr.close >= prev.open`.

That is not what he describes. His is: two consecutive same-direction
candles form an open-close key level, and then a later candle CLOSES
beyond it. He is explicit that the disrespecting candle need not be the
opposite colour -- *"it doesn't necessarily mean it can be a bull[ish
candle]. Sometimes the candle can be below."*

Classic engulfing is a strict subset at best, and not even reliably
that: an engulfing candle satisfies neither the two-candle open-close
formation requirement nor, necessarily, a close beyond it.

## What is already in the codebase

Nothing here needs new primitives:

- breakout and sweep+break are what `detect_confirmations()` produces,
  and `run_backtest` ALREADY computes `h1_confirmations` on the H1
  series -- then uses them only to read an H1 bias, never as an entry
  trigger.
- open-close formation is `detect_open_close_level()`, and disrespect is
  `is_disrespected()`, both in `key_levels.py` and both already used for
  key levels.

So all four triggers are expressible with code that exists.

## Also confirmed by this passage

Open-close key levels ARE direction-specific: *"two consecutive bearish
candles... gives you a bearish open-close key level."* The engine
requires the two candles to share direction, which is right. That was an
open question before this passage answered it.

## Needs confirming before implementing

The transcript garbles one line (08:45 reads *"these points right here
is your work to engulfing"*, probably *"what we call engulfing"*). The
reading above depends on that being the sense, and on the 09:15 summary,
which is clear.

Question for the operator: is the "engulfing" confirmation entry the
open-close-disrespect described here, or is a classic engulfing candle
ALSO a valid separate trigger? The engine currently has only the latter.
