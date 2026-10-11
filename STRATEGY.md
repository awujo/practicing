# STRATEGY.md — Kevin King SLK-style method (Stage 0)

Source of truth: `knowledge-base/videos/*/transcript.txt` only. Timestamps are seconds
from each transcript's `[start-end]` markers. Anything guessed is marked **UNCONFIRMED**.

## 1. Bias / Storyline ("building bias" = "storyline", same thing)
- Storyline = the sequence of structure events that tells you where price is likely going;
  you build it top-down. (`kevin-story-line` [0.0-40.5])
- Timeframe entry point depends on the calendar: at the start of a new month start from
  Monthly; start of a new week start from Weekly; otherwise Daily/4H. (`kevin-all-in-1` [86.4-100.6])
- Stack TFs: bias TF → next TF down for structure → next for entries. Never take an entry
  on the same TF that gave the break without confirming below. (`kevin-basic-ms-pt2`, `kevin-entry-2` [5.3-34.3])
- The TF whose candle *caused* the breakout/storyline is the TF you then look for entries on.
  (`kevin-entry-2` [5.3-34.3])
- No valid storyline = no trade. (`kevin-story-line`, `kevin-introduction-to-entry`)

## 2. Basic Market Structure
- Swings: higher highs/higher lows = uptrend; lower highs/lower lows = downtrend. The low
  before a reversal point defines the first HL in an up-leg. (`kevin-basic-ms` [61.6-102.2])
- BOS = break of structure in trend direction; BMS/CHoCH = break against current structure
  (trend-change signal). (`kevin-basic-ms-pt2` [25.6-106.0], `kevin-advance-market-sturcture-pt2` [22.1-45.1])
- Break validity: body close beyond the swing point counts; wick-only = liquidity sweep, not
  a break. (`kevin-basic-ms-pt2`, `kevin-advance-market-sturcture-pt2`)
- Internal breaks inside a swing leg (IH/IL) don't change external structure. (`kevin-basic-ms` [35.7-61.6])
- Line-chart trick: switch to line chart to see obvious external breaks cleanly.
  (`kevin-eurgbp-bd` [93.6-138.2])

## 3. Advanced Market Structure (AMS)
- AMS = Sweep of liquidity + BOS + Inducement, all three required to complete it.
  (`kevin-advance-market-sturcture-pt2` [22.1-45.1])
- Double-BOS and validation standards discussed across pt1–pt3; pt3 exists because students
  struggled — re-read carefully when implementing. (`kevin-advance-market-sturcture-pt3` [29.9-58.9])
- Fractal: one HTF candle can contain a full AMS leg on a lower TF. (`kevin-advance-market-sturcture`)

## 4. Liquidity
- "Liquidity means money": anywhere there are resting orders (equal highs/lows, trendlines,
  obvious swing points) is liquidity. (`kevin-liquidity` [19.0-35.9])
- Inducement = minor liquidity taken to fuel the real move. (`kevin-liquidity`, `kevin-advance-market-sturcture-pt2`)
- Internal vs external range liquidity; TP targets sit at opposite external liquidity.
  (`kevin-liquidity-pt2`, `kevin-liquidity-pt3`)

## 5. Key Levels
- Three types: A-shape, V-shape, Open-Close (OC) levels. Two opposite-direction candles form
  V/A shapes. (`kevin-key-levels-pt1`, `kevin-entry-2` [41.3-96.0])
- Levels invalidate and flip roles (S/R flip). Freshness matters: fresh level > unfresh;
  wick-touch vs body-close changes status. (`kevin-key-levels-pt1`, `kevin-key-levels-pt3`, `kevin-key-levels-pt4`)
- Prefer HTF levels; confluence of multiple level types strengthens a POI. (`kevin-key-levels-pt3`)

## 6. Entries
- Continuation over reversal: prefer entries aligned with the completed storyline/bias.
  (`kevin-introduction-to-entry` [110.6-131.8], `kevin-entry3` [62.1-91.9])
- Model A: breakout + retest rejection at a key level (third-candle rejection; ~5-candle
  sequence). (`kevin-introduction-to-entry`, `kevin-entry-4`)
- Model B: QMRO — sweep + BOS then retrace into the mitigation/rejection origin zone
  (apex/head/shoulder/neck). (`kevin-entry3`, `kevin-entry-4`)
- If a TF breaks but shows no continuation, do not force entries there. (`kevin-entry3` [101.9-120.5])
- Confirmation TF: after storyline forms on TF X, drop below X to time the entry.
  (`kevin-entry-2` [5.3-34.3], `kevin-all-in-1` [1972.7-1995.7])

## 7. Stop Loss
- Place SL behind the rejection candle / invalidation point of the setup, not a fixed pip
  number by default. (`kevin-qns-pt1` [1310.3-1317.7], `kevin-entry3` [326.6-336.6, 682.6-691.7])
- Typical small stops quoted in examples: 10–15 pips. (`kevin-entry3` [372.1-385.8, 1165.7-1174.6])
- If two nearby candidate stop points exist, cover both. (`kevin-cadjpy-bd` [244.3-281.3])
- Big-SL alternative: enter earlier and put SL at the validation point — still valid, just a
  different R:R style. (`kevin-all-in-1` [1979.7-2017.4])
- If price keeps tripping your SL at a level, adjust placement (experience → smaller stops).
  (`kevin-qns-pt1` [1323.7-1370.1])

## 8. Targets
- Target the opposite/next external liquidity (equal highs/lows, unfresh key levels).
  (`kevin-liquidity-pt2`, `kevin-liquidity-pt3`, `kevin-all-in-1` [1992.7-1995.7])

## 9. When NOT to trade
- No completed storyline → no entry. (`kevin-story-line`)
- Break without continuation on that TF → stand aside. (`kevin-entry3` [101.9-120.5])
- Setup against bias (reversal hunting) → skip unless AMS confirmed. (`kevin-introduction-to-entry`)
- Entry requires the level AND the confirmation candle; missing either = no trade.
  (`kevin-qns-pt1` [1485.5-1495.1])

## Open questions (ask owner)
1. Risk % per trade and max open trades — never stated in any transcript. **UNCONFIRMED.**
2. Session/time-of-day filters (London/NY killzones)? Kevin mentions premarket routine but
   no explicit killzone rule found. **UNCONFIRMED.**
3. Exact pair list to start with (examples use USDJPY, EURGBP, CADJPY, USDCHF, EURAUD).
4. Minimum RR threshold before taking a signal — not quantified in transcripts. **UNCONFIRMED.**
5. Whether "B-series stronger than A-series" ranking applies to bot signal scoring weights.
