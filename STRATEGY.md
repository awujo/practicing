# Kevin King SLK — Bias Strategy (v0.1, Claude branch)

Source: only the `kevin_King` course (29 transcripts + contact sheets). Evidence notes with
timestamps: `knowledge-base/study/notes_*.md`. Tags: `[T video@sec]` transcript, `[F video/sheet]` frame.
Anything marked **OUR CHOICE** is not said by Kevin; it is a default we pick so it can be coded and
then tuned by backtest.

Priority: **1. Bias** (this document). 2. Entry alerts. 3. Trade execution (cTrader, later).

---

## 1. Core definitions

| Term | Rule | Source |
|---|---|---|
| Swing high / low | Extreme point before a reversal. Confirmed only after price breaks the previous opposite swing. | [T basic-ms@159-620] |
| Trend | Up = HH + HL. Down = LH + LL. Neither = range → stay away. | [T basic-ms-pt2@1590, pt3@1529] |
| Break (BOS) | Candle **body closes** beyond the swing. A wick-only poke that closes back = **sweep** (liquidity taken), not a break. | [T liquidity@647-800, F basic-ms-pt3/sheet_015] |
| Reversal break (his "BMS") | Body close beyond the last protected swing against the trend. Bias flips on the first one. | [T basic-ms-pt3@875-1211] |
| Liquidity | Only two kinds: IRL (inside the swing range) and ERL (beyond it). Price takes IRL, then expands to ERL. ERL = target. | [T liquidity@269-423, 1196-1560] |
| Single-candle liquidity | The previous month/week/day candle's high and low (PMH/PML, PWH/PWL, PDH/PDL). | [T liquidity-pt2@65-460] |
| Sessions / equal highs-lows | **Not used** by Kevin. | [T liquidity-pt2@438-448] |

### Key levels (KL) — built from two consecutive candles, bodies only, wicks ignored

| Shape | Candles | Line drawn at | Used for |
|---|---|---|---|
| A-shape | bullish then bearish | shared body price (close of 1 ≈ open of 2) | SELL |
| V-shape | bearish then bullish | shared body price | BUY |
| Open-Close (OC) | two same-colour candles | close of 1 / open of 2 | bearish OC = SELL, bullish OC = BUY |

[T key-levels-pt1@1173-1711, F key-levels-pt3/sheet_005, F key-levels-pt1/sheet_014]

- **Fresh** = no wick has touched it since creation. First wick touch makes it *used*. A later full-body
  close through it makes it fresh again (and flips its direction). [T key-levels-pt4@441-805]
- **Invalid / flip**: a full-body close through the level. A broken A-shape becomes a buy level on retest,
  a broken V-shape a sell level. [T key-levels-pt3@296-420]
- Kevin uses each level **once**; higher timeframe levels are stronger. [T key-levels-pt4@1087-1110, story-line@979]
- Zone drawing: see §5 Q3 (from frames). **OUR CHOICE:**
  only A/V at a confirmed swing point count (otherwise every pair of candles would be a level);
  OC only counts if the move that starts from it breaks structure.

---

## 2. The bias = "Story line" (two steps, two timeframes)

Kevin: *"No breakout, no story line, no trade."* [T story-line-pt3@689-726]

| Origin TF (step 1) | Confirm TF (step 2) | When to run |
|---|---|---|
| Monthly | Weekly | new month |
| Weekly | Daily | new week |
| Daily | H4 | every day (his main daily routine: "daily reject daily + H4 breakout") |
| H4 | H1 | weaker; only when D has no story (TP capped at next H4 level) |

[T story-line@468, pt2@288-330, pt4@566, class-wrok@480-620]

**Step 1 — Tap, reject, close (origin TF).** A candle wicks into a *fresh* KL and **closes** back
outside it on the rejection side. Wait for the close. [T story-line@1314-1541]
Alternative origin: a sweep of the previous day/week high or low (wick beyond, close back). [T story-line-pt3@1887-2090]

**Step 2 — Breakout (one TF lower).** Find the **last opposite swing created before price first tapped
the KL** (for a sell: last V/swing low; for a buy: last A/swing high). A lower-TF candle **body closes**
beyond it → bias confirmed. A sweep + BOS also qualifies. Breaks after the tap are *internal* and are
used only for entries, not for bias. [T story-line-pt2@505-650, pt3@594-1260]

**Output** (per pair, per origin TF):

```
bias:          BULLISH | BEARISH | NO_TRADE
origin:        TF, KL type, KL price, tap candle time
confirmed_by:  lower-TF breakout candle time + swing price
target:        next fresh KL of same/higher TF in the bias direction, or ERL (previous high/low)
invalidation:  body close beyond the origin KL
status:        WAITING_TAP → TAPPED → CONFIRMED → TARGET_HIT | INVALIDATED | CANCELLED
```

### No-trade / cancel / flip rules

1. Step 1 without step 2 → **NO_TRADE**, keep waiting (the breakout may come 3–5 days later and is still valid). [T story-line-pt3@360-536]
2. Monthly and weekly point opposite ways → **NO_TRADE**. [T class-wrok@1236-1312]
3. Never against the higher-TF trend. [T liquidity-pt3@712-723]
4. Same day the lower TF closes back through the breakout level → cancel; re-check next day. [T qns-pt2@1700-2030]
5. Price taps the level many times (4–5) before breaking out → skip, messy. [T qns-pt2@2076-2150]
6. A daily KL on the way to target is rejected + H4 breaks the other way → old story over, new one may start. [T story-line-pt2@1779-1832]
7. Pair is hard to read in 30 seconds → skip. [T story-line-pt4@1195-1217]

---

## 3. Entry (stage 2 — summary only, details in `knowledge-base/study/notes_entry.md`)

- Entry TF = the TF that gave the breakout (D story → H4, W story → D). Drop to 2H/1H after the H4 reaction.
- **Continuation model:** c1–c2 form an A/V level, c3 rejects, c4 breaks out, **c5 retests = entry**. Skip if no retest.
- **QMRO model:** entry at the shoulder level after a 3rd-candle rejection, then a 1H breakout.
- SL beyond the invalidation zone / rejecting candle; max ~10–15 pips (USD pairs), 15–20 (JPY); skip if bigger or spread > 5 pips.
- TP = bias target; RR not fixed (his examples 1:3 to 1:5). Max daily loss 0.5%. [T structuring@836-1650]

---

## 4. How we measure it (backtest)

For every CONFIRMED bias: did price reach the **target before the invalidation**? Report per pair, per
origin TF, per year: count, hit rate, average R (target distance ÷ invalidation distance), time to target.
A bias version is only promoted if it beats a coin-flip baseline on out-of-sample years.

---

## 5. Open questions (Kevin does not say — defaults chosen, tune by backtest)

| # | Question | Default (OUR CHOICE) |
|---|---|---|
| Q1 | Daily candle close time | **17:00 New York** (= 00:00 IC Markets server time). Kevin charts on TradingView (frames show clock "UTC+1"); TradingView forex daily candles close at 17:00 NY whatever the display timezone, and cTrader/IC Markets uses the same close. Weekly = Friday 17:00 NY. |
| Q2 | Swing detection | **Structural swings, not a fixed fractal.** Frames [F basic-ms/sheet_004] show him labelling only the major leg extremes (L, H, HL, HH) at the wick tip, a few per week on H1, skipping small pivots. Code: zigzag where a swing is fixed only when price body-closes beyond the previous opposite swing [T basic-ms@159-620]. |
| Q3 | KL zone height | **Shaded box from the level candles' bodies to their wick extreme**, extended right until price comes back. Frames [F key-levels-pt1/sheet_020, sheet_022] (USDJPY H4, ~15-20 pip box) and [F story-line-pt2/sheet_013] (CADJPY D, two lines 112.903 / 112.730). The tap = a wick into the box; the rejection candle closes back out of it. |
| Q4 | Several fresh KLs — which one? | most recent fresh KL price reacted from |
| Q5 | "Fresh" conflict: story-line says *body* entry spends an OC level; key-levels-pt4 says *wick* touch spends it | follow key-levels-pt4 (dedicated lesson) |
| Q6 | Max wait from tap to breakout | 5 origin-TF candles, then drop |
| Q7 | Pairs / sessions | all pairs, no session filter (Kevin uses none; user: "any pair, any session") |
