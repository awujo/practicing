# Video 7: Defined Ranges / Range Cycle

## Content type
Live teaching session (starts with a live trade recap, then core lesson on defined ranges + range cycle, ends with Q&A). Extremely dense, precise, directly codeable content — probably the clearest ruleset so far.

## Live example reconfirming prior rules
GU trade this session: fixed **10 pips max stop-loss** rule stated explicitly ("my highest surplus I can go for every trade is 10 pips"), hit 1:3 R:R quickly. Reconfirms the 1:3 target and structure-derived (but capped) stop approach from Videos 4/6. Mentions "QMR key level" terminology on the 45-minute chart — **term not yet defined**, flagged for follow-up (possibly a specific pattern name, unclear from context — do not guess).

## How a Defined Range starts
A range/swing point is only valid once BOTH conditions are met:
1. **Sweep of liquidity** (price wicks through a prior high/low)
2. **Break of structure** (price then breaks/closes through a structural point in that direction)

Both are required — a sweep alone is not enough (see the critical wick-vs-close distinction below).

## Strong Low / Strong High / Weak High / Weak Low
- **Strong low** (in a bullish range): the point where price swept liquidity AND broke structure — this is the origin of the range.
- **Weak high**: the range's primary target = also the External Range Liquidity (ERL).
- A "strong high" is created by the exact same mechanism (sweep + break) as a "weak low" — the labels just depend on which side of the range you're looking from.
- The strong high/low is **not fixed** — it updates forward every time a new valid sweep+break occurs.

## The ABC Concept (naming convention)
- **A leg** = strong low (sweep + break origin)
- **B leg** = inducement liquidity / internal range liquidity
- **C leg** = weak high = external range liquidity (the target)

## Range Cycle
- A range starts with sweep+break, and **ends the same way** (sweep+break), which simultaneously marks the start of the next range/cycle.
- Within a range: price works through a series of internal range liquidity points (called "minor structure"), typically stopping at the **"last resort liquidity"** — the internal range liquidity point closest to the strong high/low — before continuing toward the external range liquidity.
- **Core reversal/continuation rule** (clean and codeable):
  - After EVERY external range liquidity is taken -> expect a **reversal**.
  - After EVERY internal range liquidity is taken -> expect **continuation** of the current trend.
- Range cycle is most useful/applied on **lower timeframes (15m, 30m)** where sweep+break patterns are easier to spot precisely.
- **"Look to the left"**: to find the current range's reference strong high/low, look left on the chart to the most recent valid sweep+break.

## Critical rule: wick-sweep vs body-close-break (precise, codeable)
This is the most concrete rule extracted so far — directly answers a student's question:
- If price **only wicks through** a strong high/low (sweeps it) but the candle **does NOT close beyond it** -> the structural shift is **NOT confirmed**. Roughly a **90% probability** price will come back and use that level as additional internal range liquidity before continuing in the original direction. Treat this new high/low as **low-probability / invalid** for redefining strong high/low.
- If price **closes beyond it** (candle body closes through the level) -> the new strong high/low **IS validly confirmed**.
- This is a real-body-close vs wick distinction — must be implemented precisely in backtest code (compare close price, not high/low, against the reference level).

## Second type of price delivery ("engineered internal range liquidity")
An alternate pattern noted as common:
1. Strong low forms (sweep + break) as usual.
2. Price then fails to break EITHER side cleanly — trades a bit lower without taking out the strong low, and trades a bit higher without taking out the existing external range liquidity (weak high). A contracting/consolidating range.
3. Eventually price comes back to sweep (not necessarily close through) the strong low area — this becomes "engineered internal range liquidity."
4. Price then continues in the original direction toward the still-unbroken external range liquidity.
5. Same wick-vs-close distinction applies when price tests the external range liquidity in this pattern too — a mere sweep without a close-through does not invalidate it as the still-pending target.

## Process notes
- Confirmed again: uses line chart specifically to verify break/no-break of a level (candlestick wicks can visually mislead).
- Multi-timeframe cross-check style continues (30m/45m/daily key levels overlapping in the live example).

## Open items carried forward
- Define "QMR key level" (unclear terminology, appeared without definition)
- Still expecting: premium & discount, "10 trade rule", full storyline/bias methodology (Video 9), precise V-shape vs A-shape killer definitions
