# Video 8: Part 2 - Range

## Content type
Live chart-marking session (multiple real GU/EU/USDCAD examples across daily/4H/weekly timeframes) plus Q&A and a homework assignment. Note: first ~2.5 minutes of the transcript is garbled/unusable (unclear audio at the start of the recording) — no content appears to be lost, picks up cleanly once the actual teaching begins.

## Assignment given (useful for our own validation process)
Mark out completed "range cycles" on charts across multiple instruments (not just EU/GU majors — also NZDUSD, BTC, ETH suggested), labeling sweep, break, internal->external liquidity progression. Good practice for us too when validating the backtester's structure-detection logic against real charts.

## Reconfirmed rules (with multiple live examples)
- Sweep + break = range definition (Video 7's rule), applied repeatedly across daily, 4H, and weekly timeframes with real GU/EU/USDCAD examples.
- Fixed **10 pips stop-loss**, **1:3 R:R** target reconfirmed again as the standard trade management (used in nearly every live example this session).
- "Look to the left" to find the current range cycle's origin reconfirmed.
- Range cycle is fractal — same pattern repeats at every timeframe (weekly, daily, 4H, 2H all shown with the same sweep/break/IRL->ERL structure).

## Key-level types are interchangeable (direct Q&A answer)
A "killer"/key-level can be based on either a V-shape/A-shape reaction OR simply an **"open close" level** (using a candle's open or close price as the reference level) — explicitly stated these are not preferential, "it is the one that is available to us at the moment" that gets used. Pick whichever valid key-level type is present in the current setup.

### Imbalance-overlap quality signal
Direct answer to a student question: a key level that has an **imbalance overlapping it holds/performs better** than one without an imbalance overlapping it. This reinforces the imbalance-overlap requirement as a genuine quality filter, not just decoration.

## Asian Session setup — precise 4H-candle definition (new, important)
Complements Video 6's clock-time definition (17:00-00:15 NY) with a candle-count definition: **the Asian session = exactly 2 four-hour candles**. Concrete setup pattern for GBPUSD:
1. On the 4H chart, price creates an Asian low and Asian high (within those 2 candles).
2. Price forms a 4H key level.
3. London session takes out the Asian low, taps into that 4H key level.
4. Price moves to the external range liquidity (upside continuation in the example given).
- The 4H candle that completes the Asian session can itself serve as internal range liquidity/inducement if price approaches but doesn't tap it before continuing.

## Daily/weekly "engulf but don't tap" inducement pattern (new)
When a daily (or weekly) candle **engulfs** the prior candle's range while trading close to a previous key level but does **NOT** actually touch/tap that key level, the untouched-but-approached candle itself becomes inducement / internal range liquidity. Price is then expected to:
1. Take out the (now inducement) daily/weekly high or low
2. Tap the original key level
3. Continue toward the next liquidity target
Shown live on both USDCAD (weekly V-shape killer example) and EU (daily example).

## Higher-timeframe context matters — real trade lesson (important caveat)
Live account of a loss around an NFP (Non-Farm Payrolls news) day: had correctly identified a multi-day buy trend context (Tuesday through Friday) but the specific NFP-day trade still resulted in a loss because "the market is not always going to give it to you the way you see it." Explicit lesson:
- Always check the higher-timeframe trend/context before taking any trade.
- Even correct structural analysis can be overridden short-term by news events (NFP specifically called out).
- Losses get reviewed retrospectively using the same liquidity/structure framework to understand what actually happened.
- **Backtesting implication**: should model/flag major news events (NFP etc.) as a distinct risk factor, not assume the structural rules hold unconditionally through news releases.

## Open items carried forward
- "QMR killer" still undefined (third video to reference it without explanation — Video 1's welcome video said upcoming classes cover "premium and discount" and "the 10 trade rule" from scratch; QMR may be covered explicitly in a not-yet-uploaded video)
- Precise V-shape vs A-shape killer criteria still not formally defined, though both continue to appear interchangeably usable with open-close levels
- Bias/storyline methodology still pending (mentor explicitly says "we are getting there, don't rush" in response to a student asking about bias — confirms Video 9 is the right place to expect this)
