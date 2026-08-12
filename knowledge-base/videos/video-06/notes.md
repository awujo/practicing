# Video 6: Part 2 - Liquidity

## Content type
Live teaching session with chart walkthroughs (daily/weekly/4H/1H examples) plus Q&A. Heavy real strategy content — directly extends Video 4's framework.

## Forms of Liquidity (concrete taxonomy)
- Previous daily high / previous daily low
- Previous weekly high / previous weekly low
- **Asian session high / Asian session low** (session-range liquidity — see dedicated setup below)
- **Trendline liquidity**: a series of consecutive higher-lows (or lower-highs) forms an implied trendline after a structure break; you do NOT need to draw the full trendline — treat the *last point* on that sequence as the relevant resting liquidity.
- Multiple old highs/lows can stack as sequential liquidity pools, swept one after another in the direction of the move.

## Liquidity cycle applies across all timeframes
Same internal->external liquidity cycle from Video 4 applies at daily and weekly swing level too, not just intraday ranges: price takes out a previous daily/weekly low, then runs to take out the next daily/weekly high (or vice versa), alternating.

## "Two structural points" rule (direct answer to a student question)
Price needs to take out **two structural points** (each of which is also an internal range liquidity point) before you should expect a change in direction / confirm continuation. This is a countable, codeable confirmation rule — e.g. requires two consecutive IRL sweeps in the same direction before trusting the structural bias.

## The Asian-Session Setup ("London setup using key levels")
This is a specific, recurring, high-value setup:
1. Mark the Asian session high and low for the day (a defined range).
2. Price sweeps the Asian low (or high) — this acts as internal range liquidity / inducement.
3. Price reacts at a **key level overlapping an imbalance** near that sweep.
4. Target: the opposite Asian extreme (Asian high if low was swept, or vice versa) — this is the next external liquidity target.
5. Frequency: occurs roughly **1-3 times per week**, called out specifically for GBPUSD.

### Exact session definition (confirmed from indicator settings screenshot)
- Custom TradingView indicator used: **"AsiaSessionHighLowMidLines"**
- Session window: **17:00 to 00:15**
- Chart timezone: **UTC-4 (New York time)** — this is his working convention; matters for exact backtest replication since session boundaries are timezone-relative.
- (In UTC this is roughly 21:00-04:15 UTC, but must confirm against actual DST handling later when we build the backtester — do not hardcode without verifying.)

## Reconfirmed: "the one setup for life"
Independently reconfirms Video 4's continuation setup as his single favorite: a setup with inducement/internal liquidity + an imbalance + a key level overlapping that imbalance. Explicitly says "we can take losses with it" — i.e. this is a probabilistic edge, not a certainty, sized/managed accordingly (ties back to Video 1's risk-scaling philosophy).

## Process / tooling notes
- Always sets chart timezone to New York (UTC-4) before doing any analysis.
- Uses a custom Asian session indicator that shades the session range visually (grey boxes on chart) and draws high/low/mid lines.
- Cross-references multiple timeframes for the same idea (4H structure -> daily confirmation in one example).

## Open items carried forward
- "Storyline" and "bias building" referenced again as where these liquidity concepts get formally assembled into a trade thesis (expected in Video 9).
- "London setup using key levels" named explicitly as an upcoming dedicated topic — watch for a video that names this directly.
