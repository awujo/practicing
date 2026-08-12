# Consolidated Strategy Rulebook (Living Document)

Built incrementally from the mentor's video course. Updated after each video is processed. This is the source of truth we'll eventually translate into precise backtestable code.

**Methodology family**: Smart Money Concepts / ICT-style price action (market structure, liquidity, imbalance/FVG, sessions) with the mentor's own terminology layered on top ("key level", "killer" shapes, "storyline").

Status: 5 of 17 videos processed (Video 1: orientation only, Video 4: core structure/liquidity framework, Video 6: liquidity forms + Asian session setup, Video 7: defined ranges + range cycle, Video 8: range examples + Asian session 4H-candle definition + news-event caveat).

---

## 1. Core Mental Model

Price is always doing exactly two things:
1. **Attacking liquidity** (sweeping resting stops/orders)
2. **Rebalancing an imbalance** (filling a fair value gap)

Every setup = identifying WHERE price needs to attack liquidity, WHERE the imbalance needing rebalance is, and at WHAT specific price level (inside that imbalance) price is expected to react.

## 2. Liquidity Framework

- **Internal Range Liquidity (IRL)**: minor liquidity resting inside a range (inducement points, small swing highs/lows).
- **External Range Liquidity (ERL)**: liquidity at the range extremes (major swing high/low).
- Expected cycle: sweep IRL -> expand to sweep ERL -> reversal -> new range origin. Repeats. Applies across ALL timeframes, not just intraday — same cycle shows up in daily/weekly swing highs and lows.

### Forms of liquidity (concrete taxonomy)
- Previous daily high / low, previous weekly high / low
- **Asian session high / low** (see dedicated Asian-session setup below)
- **Trendline liquidity**: a series of consecutive higher-lows or lower-highs after a structure break; use the *last point* on that sequence as the liquidity reference — no need to draw the actual trendline.
- Multiple old highs/lows can stack as sequential pools, swept one after another in the direction of the move.

### "Two structural points" confirmation rule
Before trusting a directional/structural bias, price should take out **two structural points** (each also an internal range liquidity point) in the same direction. Countable, codeable confirmation threshold — not just one break.

### The Asian-Session Setup ("London setup using key levels")
1. Mark the Asian session high/low for the day.
2. Price sweeps the Asian low (or high) -> acts as internal range liquidity.
3. Price reacts at a key level overlapping an imbalance near that sweep.
4. Target: the opposite Asian extreme.
5. Frequency: ~1-3x/week, called out specifically for GBPUSD.

**Exact session definition** (confirmed from his indicator settings): Custom TradingView indicator "AsiaSessionHighLowMidLines", session window **17:00-00:15**, chart timezone **UTC-4 (New York)**. Must confirm DST handling when building the backtester rather than hardcoding a UTC offset. Cross-confirmed via a second, independent definition: **Asian session = 2 four-hour candles** — consistent with the clock-time window (~7h15m ≈ two 4H candles). The 4H candle that completes the Asian session can itself serve as inducement if price approaches but doesn't tap it before London continues the move.

### Daily/weekly "engulf but don't tap" inducement pattern
When a daily/weekly candle engulfs the prior candle's range while trading close to a previous key level but does NOT touch/tap that key level, the untouched-but-approached candle itself becomes inducement/internal range liquidity. Expected sequence: take out that candle's high/low -> tap the original key level -> continue toward the next liquidity target.

## 3. Defined Ranges & Range Cycle

A range/swing point is only valid once BOTH conditions are met:
1. **Sweep of liquidity** (a wick through a prior high/low)
2. **Break of structure** (price then breaks/closes through a structural point in that direction)

### Strong Low / Strong High / Weak High / Weak Low
- **Strong low** (bullish range): the sweep+break origin point of the range.
- **Weak high**: the range's primary target = External Range Liquidity (ERL).
- Strong high/low updates forward every time a new valid sweep+break occurs — not a fixed point. To find the current reference point, "look to the left" to the most recent valid sweep+break.

### ABC naming convention
A leg = strong low (sweep+break origin). B leg = inducement/internal range liquidity. C leg = weak high = external range liquidity (target).

### Range Cycle
A range starts with sweep+break and ends the same way (sweep+break), which simultaneously starts the next cycle. Within a range, price works through successive internal range liquidity points, stopping at the "last resort liquidity" (the IRL point closest to the strong high/low) before continuing toward the external range liquidity.

**Core rule**: after every external range liquidity is taken -> expect **reversal**. After every internal range liquidity is taken -> expect **continuation**. Most applicable on lower timeframes (15m/30m).

### CRITICAL rule: wick-sweep vs body-close-break
The single most precise, directly-codeable rule extracted so far:
- Price **wicks through** a level but candle **does not close beyond it** -> structural shift NOT confirmed. ~90% probability price returns to use that level as further internal range liquidity before continuing in the original direction. Treat as invalid/low-probability for redefining strong high/low.
- Price **closes beyond it** (body close through) -> validly confirmed.
- Must compare **close price**, not high/low wick, against the reference level when implementing structure-break detection in code.

### Alternate pattern: "engineered internal range liquidity"
Sometimes after a strong low forms, price fails to cleanly break either side (contracts instead), then comes back to sweep (not necessarily close through) the strong-low area before continuing in the original direction. Same wick-vs-close distinction applies to whether the external range liquidity is still "pending" in this pattern.

## 4. Entry Setups (two variants, both derived from the same two conditions)

### A. "Origin of the move" (highest quality, hardest to catch)
Liquidity sweep + immediate break of structure (BOS) confirms order flow. Entry at a "key level" overlapping inside a fair value gap, right where the order flow was confirmed.

### B. "Continuation setup" (preferred/most repeatable — stated as "the one setup I'd trade for the rest of my life")
Used when the origin move is missed:
1. Find a key level that was previously **disrespected** (broken)
2. Wait for a new **inducement liquidity** to form close to that level
3. That level (overlapping an imbalance) + nearby inducement = entry trigger
Requires patience; do not force it before inducement forms.

### Key-level shapes (terminology, not yet fully defined)
- "V shape killer" — V-shaped reaction at the level
- "A shape killer" — inverse reaction shape (needs more examples from later videos to nail down exact criteria)
- Key levels can also be a plain **"open close" level** (a candle's open or close price used as the reference) — interchangeable with V/A-shape killers; use whichever valid type is present, no fixed preference.
- **Quality signal**: a key level with an imbalance overlapping it performs better than one without — confirmed directly, not just incidental.

## 5. Trade Management
- Primary target: **1:3 risk-reward** — stated as the repeatable bread-and-butter target. Occasionally extends further (1:6 seen once).
- Explicit lesson: take the 1:3 when it's there — don't hold out for more and risk giving it back.
- Stop-loss: structure-derived (placed relative to the imbalance/key level), not a fixed pip value — one example used ~10 pips, not a universal rule.

## 6. Timeframes
- Bias/setup identification: higher timeframes (1H, 4H, sometimes 3H).
- Entry execution: drops to lower timeframes — 15-minute entries confirmed on the 5-minute chart.
- Uses both candlestick AND line charts — line chart specifically preferred for spotting clean liquidity sweeps / BOS (candlestick wicks can obscure it).

## 7. Session & Pair Rules (concrete, backtestable)
- Day trader — does not swing trades overnight as a rule.
- Avoid GBPUSD / EURUSD during Asian session (low "liquidity injection").
- Asian-session-appropriate pairs: AUDUSD, NZD pairs, USDCHF, GBPJPY, EURJPY.
- Each session (London/NY/Asia) has its own liquidity-injection window tied to real institutional order flow.
- Cancels pending limit orders that would only trigger outside London/NY for majors pairs.
- Avoid holding into very late hours — spread widens sharply around session rollover (~10pm reference).
- Data feed / broker reference: Oanda. Charting: TradingView (uses Replay mode for backtesting review).
- **News-event caveat** (from a real loss reviewed in Video 8): structural rules can get overridden short-term by major news releases (NFP specifically called out). Always confirm higher-timeframe trend context before entering, and treat news-day price action as elevated risk — the backtester should model/flag major news events rather than assume the rules hold unconditionally through them.

## 8. Open Questions / Expected in Later Videos
- Premium & discount pricing theory
- The "10 trade rule"
- Full storyline-building / bias methodology (Video 9 likely covers this — title is "Bias/Storyline")
- Precise definition of "V shape" vs "A shape" killer
- Full confirmation-entry drill-down process (4H -> 15m -> 5m mentioned but not fully demonstrated yet)
- "QMR key level" — term used in Videos 7 and 8 without definition, unclear if it's a specific pattern name (possibly related to "Quasimodo" reversal pattern from broader ICT/SMC vocabulary, but not confirmed — do not assume)
