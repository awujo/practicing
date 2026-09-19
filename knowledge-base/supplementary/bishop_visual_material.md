# Supplementary Source: Web3Bish0p (Defi Bishop) — Visual Material

Fellow student of the same mentor, posts trade breakdowns publicly on X. This note covers the 3 tweet screenshots and the first 6 of 60 pages of the "trade chart examples" PDF (rest of the PDF pending review).

## Tweet 1: The BIAS -> CONFIRMATION pipeline diagram
Clean diagram formalizing the exact process from Video 9:
- **"KEY LEVELS"** and **"LIQUIDITY"** tracked in parallel across two stages:
  1. **BIAS** stage, built from: **M/W/D/4** (Monthly -> Weekly -> Daily -> 4H, matching Video 9's top-down cascade exactly) then **"Immediate LTF"** (lower timeframe).
  2. **CONFIRMATION** stage: labeled **"C.E"** = Confirmation Entry.
- Directly confirms and formalizes Video 9's process with clean acronyms worth reusing in our own code: bias is built top-down through M/W/D/4H, then confirmed on immediate LTF, then entered on a C.E (confirmation entry) trigger.

## Tweet 2: Fractal structure principle (new, important)
Headline text: **"1 CANDLE ON HTF = ADVANCED M.S ON THE NEXT LTF"** and **"1 CANDLE ON DAILY = H4 A.M.S (TYPE 1/2)"**.
- Formalizes the fractal nature already hinted at in the main course: a single higher-timeframe candle's price action, when viewed on the next timeframe down, contains a complete Advanced Market Structure (A.M.S) cycle of its own (sweep, break, range).
- Explicitly names **two recognized pattern "types"** for how a daily candle's internal H4 structure can play out (diagram shows two example layouts side by side, both labeled with a "D.L" — likely "Daily Low" — reference point). Exact criteria distinguishing Type 1 vs Type 2 not fully clear from the diagram alone — flag for more examples.

## Tweet 3: "Storyline Criteria" formal checklist
From a slide titled "STORYLINE: CAPITALIZING ON THURSDAY EXPANSIONS":
- **Storyline Criteria** (3-point checklist):
  1. Sweep / Rejection / Rebalance
  2. Candle Closures
  3. Break
- Also lists "Timeframe Alignment" and "W Questions" as related concepts (unclear if "W Questions" means Weekly-specific questions or a Who/What/When/Where/Why style checklist — flag for clarification).
- Title suggests a specific observed pattern of **Thursday having notable expansion moves** — possibly tied to pre-NFP (Friday) positioning or weekly liquidity dynamics. Worth testing empirically in the backtester rather than assuming — this is one trader's observation, not yet verified against our own data.
- Independent confirmation that "Sweep + Break" and candle-close discipline (matches Video 7's wick-vs-close rule) are the exact same criteria taught in the main course — good cross-source consistency check.

## PDF pages 1-6 of 60: Real labeled trade examples (EURCAD, EURJPY, EURCHF)
Concrete entry mechanism observed repeatedly across examples:
1. **"Daily bullish breakout, Daily reject Daily"** — daily timeframe itself shows a breakout/rejection pattern (self-referential daily structure check).
2. **"H4 breakout with idm H4rH4"** — H4 timeframe breaks out with inducement ("idm"), reacting off an H4-created level.
3. **"H2 Engulfing Confirmation Entry"** — the actual entry trigger: once Daily + H4 bias align, drop to a 2-hour chart and wait for an **engulfing candle** as the Confirmation Entry (C.E) trigger. This is the most concrete, directly-codeable "C.E" definition we have so far.
4. ~~Teal/pink shaded zones on the charts mark the imbalance/FVG being targeted (teal = continuation zone, pink = the imbalance being rebalanced) — matches "key level overlapping imbalance" from the main course.~~
   **CORRECTED 2026-09-19, by the operator, from the extracted video frames.** Those are **TradingView's Long/Short Position tool** — green is the profit zone, red is the risk zone, drawn around an entry. They are not imbalances or FVGs and have nothing to do with "key level overlapping imbalance".
   Visible plainly once the videos were framed: on `bishop-trades-breakdown-3` at t=870s and t=1050-1095s the pairs sit tight around an entry price, green above and red below, which is the position tool's signature and not how an FVG is shaded.
   This matters because the mistaken reading is the kind of thing that gets built on. Anything in the engine justified by "teal/pink zones on Bishop's charts" needs re-checking against a source that actually says it -- in particular the imbalance-anchored `plug_and_play` stop rule, which takes priority over every trigger-specific stop whenever an overlapping imbalance exists.
5. Real broker execution screenshot (EURCHF, M30): a BUY LIMIT order with stop-loss and take-profit marked. Measured risk:reward on this specific trade was roughly **1:11** (SL ~4.6 pips, TP ~51 pips) — notably wider than the main mentor's usual 1:3. This may reflect Bishop's own individual execution style rather than a core rule change; worth tracking as a possible variation/refinement rather than assuming it replaces the 1:3 default.

## Status
6 of 60 PDF pages reviewed. Remaining 54 pages and all 6 Bishop videos still pending — large volume, will continue processing systematically.
