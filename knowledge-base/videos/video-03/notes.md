# Video 3: All You Need to Know About Structure

## Content type
Foundational teaching session — basics of market structure through to advanced market structure, explained cleanly and systematically. This is effectively the "textbook" version of everything Videos 4/6/7/8/9 apply in practice. High density, minimal tangents.

## Basics of Market Structure (clean definitions)
- **Bullish**: consecutive higher highs + higher lows.
- **Bearish**: consecutive lower lows + lower highs.
- Every **higher high** (bullish) = **External Range Liquidity (ERL)**.
- Every **higher low** (bullish) = BOTH an **Internal Range Liquidity (IRL)** AND a **structural point**.
- Mirrored for bearish: every lower low = ERL, every lower high = IRL + structural point.

## Structural point / Break of Structure (precise definition + origin of the wick-vs-close rule)
- A directional bias shift is signaled when price trades below/above ONE or TWO structural points — **not always exactly two**; sometimes one suffices (adds nuance to Video 6's "two structural points" rule — it's a typical/common threshold, not an absolute requirement).
- **This is the original source of the wick-vs-close distinction** (Video 7 applied it, this video explains why): "the way you get to know if we have broken structure is how the candle closes... if we close above or below [the structural points]... with a body." A mere wick through without a body close does NOT count as a break — those swept points instead become internal range liquidity, to be revisited and properly closed through later.
- Explicit statement: understanding candle closure "you will never go wrong with the direction" — you can still miss entries or get a wide stop-loss, but directional bias itself won't be wrong if closure discipline is followed correctly.

## Consolidation & Manipulation Framework (NEW — important, not covered elsewhere yet)
When the market is NOT trending (ranging/consolidating), its primary purpose is **engineering liquidity**: building up buy-side liquidity above the range and sell-side liquidity below it (ICT terminology, used loosely here). Two possible resolutions:

### A. Manipulation + Displacement
1. Price manipulates (sweeps) ONE side of the consolidation's liquidity.
2. Followed immediately by **displacement** — a strong, impulsive move in the opposite direction. This displacement confirms the new trend.
3. Asian session is explicitly named as the most common source of this consolidation pattern — ties directly into the Asian-session setups already documented (Videos 6/8).

### B. Break and Retest (no manipulation)
1. Price does NOT sweep either side first — it just breaks out directly with displacement.
2. Price then retraces back to retest the SAME key level that has been respected multiple times previously (2nd, 3rd, 4th test of that level).
3. **Quantified estimate given directly**: roughly **80% probability** that if this key level has an inducement liquidity nearby and is overlapping an imbalance, price continues in the breakout direction after the retest. This is a genuinely testable number for our backtester to validate against real data.

## Entry style spectrum: Aggressive vs. Conservative (explicit, sanctioned tradeoff)
Directly addressed via a student question about missing trades:
- **Aggressive style**: once a key-level+imbalance setup is fully formed (regardless of whether inducement has tapped yet), enter directly with a **wider stop (~10-11 pips)** to give the trade room. Accepts more drawdown/whipsaw risk in exchange for not missing moves that never give a clean confirmation entry.
- **Conservative style**: wait for full confirmation entry (lower timeframe trigger, e.g. Bishop's H2 engulfing candle) before entering. Avoids some false starts but risks missing moves that run without ever giving that confirmation.
- Presented as a legitimate personal-style choice, not one superior to the other — **our backtester should test both entry styles** as separate variants rather than assuming one is "the" correct approach.

## Advanced Market Structure — full step-by-step mechanism (cleanest explanation yet)
1. **Strong low** forms: sweep of liquidity + impulsive break of structure (the origin of a new order flow).
2. Price gives a full order flow: creates a higher low, then a higher high.
3. Price returns to take out the **IRL** (the higher low) -> **expansion/continuation** to the upside.
4. Price takes out the **ERL** (the prior external high) -> **reversal**.
5. After the reversal, the "strong low" reference point moves forward to the new low created by this reversal (a fresh sweep+break origin) — the cycle repeats.

## "Your stop loss is my entry" — order block mechanics explained
- Retail/naive traders buying from an order block typically place stop-loss just below it and entry at the block's open price — this creates a predictable cluster of resting stop-losses just below that level.
- Liquidity-aware traders deliberately enter AT that stop-cluster location, because price is statistically drawn to sweep it (a liquidity magnet).
- Explains the "sniper entry" social-media trope: a trader posts a screenshot bragging about a great entry right as price wicks through and stops them out, then reverses in the smart-money direction.
- Practical implication: **inducement liquidity commonly forms just beyond order blocks / key levels**, specifically where retail stops cluster — useful detail for identifying inducement in the backtester.

## Engineered liquidity pattern — reconfirmed with cleaner logic
Matches Video 7's "engineered internal range liquidity" pattern: after a reversal, if the new range fails to take out the new external range liquidity (price trades both lower and higher without closing through), the **lowest low (or highest high) inside that failed range** becomes the engineered/internal liquidity that must be taken before real continuation resumes.

## Process/tooling confirmation
Reiterated: his live chart has only two tools active — a key-level drawing tool and the line chart. No extra indicators beyond the custom Asian session tool seen earlier. Minimalist by design.

## Open items
- Call ended with "Can we talk about premium and discount today? Yes, we should be able to" — but the recording cuts off before it's actually covered. **Do not assume Video 5 covers premium & discount** just because of this — it may be in a live session not among the 18 uploaded videos. Still an open question.
