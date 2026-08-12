# Video 9: Bias / Storyline

## Content type
Live teaching + extensive real chart walkthroughs (GBPUSD monthly -> weekly -> daily -> 4H drill-down, plus a full weekly-timeframe case study). This is the master framework that ties structure + liquidity + range cycle + key levels together into an actual top-down trade thesis ("storyline"/"bias"). Arguably the single most important video processed so far.

## The Top-Down Storyline Process (THE core bias-building algorithm)

### Monthly check (once per month)
1. Check how the previous monthly candle closed relative to a monthly key level (e.g. did June trade into a monthly key level and close above/below it?).
2. That close direction sets the bias for the upcoming month.
3. **Confirmation**: scale down one timeframe (Monthly -> Weekly). Look for EITHER a weekly liquidity sweep + break of structure, OR a weekly engulfing candle, in the bias direction.
4. Once confirmed, scale down again (Weekly -> Daily) to find actual trading opportunities.
5. Keep trading that direction until "the move on the monthly is exhausted" — i.e. until price reaches the target implied by the monthly-level reaction.

### Weekly check (every week, e.g. Sunday)
1. Check how the previous weekly candle closed relative to a weekly key level.
2. A weekly close beyond a level sets a directional lean for the week — but is **NOT sufficient alone**. Must scale down to the daily for confirmation.
3. **Daily confirmation** can be any of: a liquidity sweep + break of structure, a simple engulfing candle, OR price returning to tap a previously-disrespected key level.
4. Until the daily confirms alignment, treat the weekly-implied move as potentially "just retracement" — don't commit fully.
5. Explicit journaling practice recommended: write down what the weekly is showing, where it reacted from (weekly open/close vs daily open/close), and the resulting conclusion. Stated benefit: "saves a lot of stress" — prevents chasing every counter-move.

### Daily routine (every day, Daily vs 4H)
1. Compare what the Daily is showing vs what the 4H is showing.
2. **Priority rule: DAILY beats 4H.** If daily shows a sweep+break or engulfing in one direction, but 4H shows a reaction from a key level suggesting the opposite, treat the 4H move as **retracement only**, not a reversal.
3. Continue scaling down (1H -> 30min) for actual entries, always in the direction the higher timeframe (daily) established.

## The framework's actual name (self-deprecating but useful)
He calls the whole combined framework **"SLK" = Structure, Liquidity, Key level** — downplays it ("not about the name, we want results"), but it's a clean label for the overall system worth using in our own code/docs.

## Refinements to existing rules
- **Candle-close importance scales UP on higher timeframes**: explicitly states "candle closure matters a lot, especially on the higher timeframe" — the wick-vs-close distinction (Video 7) is even more critical to respect strictly on weekly/monthly than on lower timeframes.
- **Key levels are dual-purpose**: usable both as entries AND as the "nearest point of exit" (i.e. a key level can double as a stop-loss/invalidation reference, not just an entry trigger).
- **Induced-move trap (explicit warning)**: price will sometimes give a genuine-looking counter-trend bounce specifically to induce buyers/sellers into the wrong side before continuing the dominant (higher-timeframe) direction. Ties directly into the inducement-liquidity concept — treat counter-trend reactions against a confirmed higher-timeframe bias with suspicion.
- **Data feed caveat** (acknowledged once, in passing): candle closes can differ slightly between data feeds/brokers near key levels. For our own backtester, we need one consistent historical OHLC data source and should not assume our data will exactly match his TradingView/Oanda feed tick-for-tick at the margins.

## Live case study confirms the whole chain end-to-end
Walked a full real example: weekly candle took out an old weekly high, tapped a key level, closed below -> weekly screaming sells -> dropped to daily -> daily confirmed with a sweep+break to the downside -> dropped to 4H -> 4H showed a countertrend "induced buyers" setup that got reversed, confirming the daily bias was correct and the 4H bounce was just a trap. Then a second full example on GU showing the same top-down chain across monthly->weekly->daily context resulting in a multi-week sustained move, explicitly reconfirming: after ERL taken -> reversal; after IRL taken -> continuation; ranges start and end the same way (sweep+break).

## Open items carried forward
- "Premium & discount" and "the 10 trade rule" still not covered — expect in remaining videos (2, 3, 5, 10-18 now available)
- Precise V-shape vs A-shape killer criteria still not formally defined
- "QMR key level" still undefined
