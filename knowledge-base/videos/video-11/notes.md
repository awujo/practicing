# Video 11: Key Levels 1

## Content type
Dedicated deep-dive on key levels — finally gives precise definitions for the "V shape" / "A shape" / "open close" terminology used since Video 4. Resolves a long-standing open question. Also gives a quantified success rate for the core continuation setup.

## THE THREE KEY LEVEL TYPES (precise definitions, finally)
Key levels are marked on **closing prices**, not wicks/highs-lows — this is stated explicitly and is important for implementation.

1. **A-shape key level**: a peak/apex-shaped reversal point (price rises into it, then reverses down — visually resembles the letter "A", a rooftop shape). Confirmed visually from a screenshot: a horizontal level drawn exactly at a local top where price peaks then drops. **Default use: SELLING opportunities.**

2. **V-shape key level**: a trough-shaped reversal point (price falls into it, then reverses up — resembles the letter "V"). **Default use: BUYING opportunities.**

3. **Open-close key level ("open close killer")**: formed by TWO CONSECUTIVE candles of the same direction (two down candles, or two up candles) whose open and close prices overlap. Two consecutive down (sell) candles with overlapping open/close -> typically used for SELL continuation. Two consecutive up candles -> BUY continuation. **An engulfing candle that consumes one or both of these candles is functionally equivalent to a body-close break of a V/A-shape key level** — same structural-break signal, just expressed via engulfing instead of a simple close-through.

## UNIVERSAL FLIP RULE (important, precise)
ANY key level type (A-shape, V-shape, open-close) can flip its default directional bias if price **disrespects** it — defined precisely as: price closes beyond it as a body, with an impulsive move, in the opposite direction. Once disrespected this way, the level's expected future reaction flips to the opposite side (an A-shape sell level can become a buy level, and vice versa for V-shape).

## Two-target strategy after a level is disrespected
After a key level is disrespected (body-close break), there are TWO places price might react from next:
1. **The SAME level that was broken** — if price first creates inducement liquidity near it, then taps back into that same (now-flipped) level and continues. This is the high-probability, most common scenario.
2. **"The extreme"** — a further/more extreme level (e.g. the original V/A-shape's far point) if no inducement liquidity forms near the broken level first. Lower-probability fallback target.

## QUANTIFIED reliability estimate (valuable, directly testable)
The specific pattern: **sweep previous [period] high -> engulf on that timeframe -> next candle serves as inducement/IRL close to the resulting key level -> price taps that key level -> continues** holds **70-80% of the time**, explicitly validated on the **4H and Daily** timeframes specifically (stated twice, consistent number both times). This is a genuinely quantified, testable claim for backtesting validation — not vague "it usually works," an actual percentage range.

## Simplified "just key levels" bias-building recipe
References an earlier dedicated session (a midnight 12am-2am call) where bias was built using ONLY key levels — no order block marking at all. Reduced to two conditions:
1. Price closes above/below a key level (sets direction).
2. Scale one timeframe down: look for a sweep+break OR an engulfing to confirm.
This is the minimal viable version of Video 9's storyline process — useful as a lightweight bias-check when full order-block/imbalance analysis isn't needed.

## Stop-loss scaling by timeframe (new nuance)
On daily-timeframe entries, stop-loss can be **10-15 pips** (vs. the 10-pip default used on lower timeframes) — a slightly wider allowance scaled to the entry timeframe rather than a single fixed universal value.

## Reconfirmed
- Key levels remain dual-purpose: entries AND exit points (repeated yet again, now with several new live examples on AUDUSD, EURUSD, GBPUSD).
- Price moves from "one key level to the other, one key level to the other" — sequential key-level-to-key-level movement, same pattern as the sequential liquidity rule from Video 5 but applied to key levels specifically.
- Line chart remains the preferred tool for spotting key levels cleanly.

## Open items
- Still pending: premium & discount, "10 trade rule", "QMR key level".
- Video ended mid-topic ("that is the basics of key levels") with a promise to continue in a later session same day — Video 11 titled "Key Levels 1" strongly implies a "Key Levels 2" exists; watch for it if more material surfaces (not currently in our set of 18).
