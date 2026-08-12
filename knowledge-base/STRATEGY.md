# Consolidated Strategy Rulebook (Living Document)

Built incrementally from the mentor's video course. Updated after each video is processed. This is the source of truth we'll eventually translate into precise backtestable code.

**Methodology family**: Smart Money Concepts / ICT-style price action (market structure, liquidity, imbalance/FVG, sessions) with the mentor's own terminology layered on top ("key level", "killer" shapes, "storyline").

Status: 3 of 17 videos processed (Video 1: orientation only, Video 4: core structure/liquidity framework, Video 6: liquidity forms + Asian session setup).

**Supplementary source**: additional trade examples/commentary being added from a fellow student's public analysis (Web3Bish0p on X) — logged in `knowledge-base/supplementary/` as they come in.

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

**Exact session definition** (confirmed from his indicator settings): Custom TradingView indicator "AsiaSessionHighLowMidLines", session window **17:00-00:15**, chart timezone **UTC-4 (New York)**. Must confirm DST handling when building the backtester rather than hardcoding a UTC offset.

## 3. Entry Setups (two variants, both derived from the same two conditions)

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

## 4. Trade Management
- Primary target: **1:3 risk-reward** — stated as the repeatable bread-and-butter target. Occasionally extends further (1:6 seen once).
- Explicit lesson: take the 1:3 when it's there — don't hold out for more and risk giving it back.
- Stop-loss: structure-derived (placed relative to the imbalance/key level), not a fixed pip value — one example used ~10 pips, not a universal rule.

## 5. Timeframes
- Bias/setup identification: higher timeframes (1H, 4H, sometimes 3H).
- Entry execution: drops to lower timeframes — 15-minute entries confirmed on the 5-minute chart.
- Uses both candlestick AND line charts — line chart specifically preferred for spotting clean liquidity sweeps / BOS (candlestick wicks can obscure it).

## 6. Session & Pair Rules (concrete, backtestable)
- Day trader — does not swing trades overnight as a rule.
- Avoid GBPUSD / EURUSD during Asian session (low "liquidity injection").
- Asian-session-appropriate pairs: AUDUSD, NZD pairs, USDCHF, GBPJPY, EURJPY.
- Each session (London/NY/Asia) has its own liquidity-injection window tied to real institutional order flow.
- Cancels pending limit orders that would only trigger outside London/NY for majors pairs.
- Avoid holding into very late hours — spread widens sharply around session rollover (~10pm reference).
- Data feed / broker reference: Oanda. Charting: TradingView (uses Replay mode for backtesting review).

## 7. Open Questions / Expected in Later Videos
- Premium & discount pricing theory
- The "10 trade rule"
- Full storyline-building / bias methodology (Video 9 likely covers this — title is "Bias/Storyline")
- Precise definition of "V shape" vs "A shape" killer
- Full confirmation-entry drill-down process (4H -> 15m -> 5m mentioned but not fully demonstrated yet)
- Range theory details (Videos 7 "Defined Ranges/Range Cycle" and 8 "Range" likely cover this in depth)
