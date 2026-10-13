# Kevin King SLK — Bias Strategy (v0.2, Claude branch)

Built from the `kevin_King` course only. All 29 transcripts plus a frame-by-frame pass over the
theory videos (structure, liquidity, key levels, story line: ~400 sheets).
Evidence with timestamps: `knowledge-base/study/notes_*.md` (transcripts) and `frames_*.md` (pictures).
Tags: `[T video@sec]` transcript, `[F video/sheet_NNN]` frame. **OUR CHOICE** = Kevin does not say;
default picked so it can be coded, then tuned by backtest.

Priority: **1. Bias** (this file). 2. Entry alerts. 3. Trade execution on cTrader (later).

---

## 0. Two views of the same chart

Kevin switches between two views all the time [F key-levels-pt1/sheet_018, story-line-pt2/sheet_010-013,
advance-market-sturcture-pt2/sheet_018, pt3/sheet_015-017]:

| View | Data | Used for |
|---|---|---|
| **Line chart** (closes only) | close prices | swing highs/lows, trend (HH/HL, LH/LL), A/V key levels |
| **Candles** | open/high/low/close | wicks: sweeps, taps, rejections; body closes: breaks; open-close levels |

The bot does the same: structure and A/V levels from **closes**, sweeps and taps from **wicks**,
breaks from **body closes**.

---

## 1. Building blocks

**Swing.** A turning point of the close line, i.e. the highest/lowest close of a leg. It is fixed only when a
later close goes beyond the previous opposite swing. Kevin marks only the main legs, not every wiggle
[T basic-ms@159-620, F basic-ms/sheet_004].

**Trend.** HH + HL = up, LH + LL = down, otherwise **range → no bias** [T basic-ms-pt2@1590].

**Break vs sweep** [T liquidity@647-800, F advance-market-sturcture-pt3]:
- **Break (BOS)** = a candle **body closes** beyond a swing.
- **Sweep** = a **wick** goes beyond a swing and the candle closes back inside. That swing was liquidity.
- **First break against the trend = BMS** (his CHOCH). It flips the trend; later breaks the same way are BOS.

**Key level (KL).** Two candles turning at the same price. Drawn as a **thin horizontal line** at
the shared **body/close price**, wicks ignored, extended right. No boxes [F key-levels-pt1/sheet_016-022, T key-levels-pt1@1173-1711].

| Shape | On line chart | Candles | Bias use |
|---|---|---|---|
| A-shape | peak of close line | bull then bear | SELL level |
| V-shape | valley of close line | bear then bull | BUY level |
| Open-Close | not visible | two same-colour candles; line at close 1 / open 2 | bear OC = SELL, bull OC = BUY |

- **Fresh** = no wick has touched it since it formed. First wick touch = used. Kevin uses a level once.
  A full-body close through it makes it fresh again with the **opposite role** (broken A → buy level on retest,
  broken V → sell level). [T key-levels-pt3@296-420, key-levels-pt4@441-805]
- Only levels that agree with the trend count: in an uptrend, V/bull-OC; in a downtrend, A/bear-OC [T key-levels-pt3@985-1160].
- Freshness is judged on the level's own timeframe (W/D), not on H1/H4 [F key-levels-pt4].

**Liquidity** [T liquidity@269-1560]:
- **IRL** = inside the current swing range (the pullback low/high). **ERL** = beyond the range extreme.
- Price takes IRL, then runs to ERL, then pulls back to a new IRL, and so on.
- **Previous candle high/low** (month/week/day) is liquidity too, measured on the wick tips [T liquidity-pt2@65-460].
- Kevin does **not** use sessions or equal highs/lows [T liquidity-pt2@438-448].

---

## 2. The story line — how everything goes together (the bias)

Kevin: *"No breakout, no story line, no trade."* [T story-line-pt3@689-726]

Runs on three ladders. Each starts on one timeframe and is confirmed one timeframe lower:

| Story | Origin TF | Confirm TF | Checked |
|---|---|---|---|
| Monthly | M | W | at a new month |
| Weekly | W | D | at a new week |
| Daily (his everyday one) | D | H4 | every day |

### Step by step (sell example; a buy is the mirror image)

1. **Trend (origin TF, line chart).** Down or up? A range means stop, no bias.
2. **Pick the level.** Take the most recent **fresh** key level that agrees with the trend
   (A-shape or bearish OC for a sell). Also mark the target: the next opposite KL of the same or a higher TF,
   or the ERL.
3. **Tap, reject, close (origin TF, candles).** A candle **wicks into** the level and **closes back below it**.
   Wait for the candle to close. → status `TAPPED`
   *Alternative start:* the wick sweeps the previous day/week high and the candle closes back below [T story-line-pt3@1887-2090].
4. **Find point B (confirm TF).** On the lower timeframe, find the **last swing low made before price first
   tapped the level**. Not the low made by the rejection itself [T story-line-pt3@1690-1790, F story-line-pt2].
5. **Breakout (confirm TF, candles).** A candle **body closes below B** → story **confirmed**, bias **BEARISH**.
   He labels it `bms` / `EXT`. Any later breaks are internal BOS and are for entries only.
6. **Hold until:**
   - target reached → `TARGET_HIT`;
   - a body close back above the origin level → `INVALIDATED`;
   - a daily KL on the way is rejected the other way **and** H4 breaks the other way → story over [T story-line-pt2@1779-1832].

### Output per pair (what the bot sends)

```
pair, story (M/W/D), bias BULLISH | BEARISH | NO_TRADE
origin level (type, price, TF), tap time, point B price, breakout time
target price, invalidation price, status
```

### No-trade rules

- Step 3 happened but no breakout yet → **NO_TRADE**, keep watching. A breakout 3–5 days later is still valid [T story-line-pt3@360-536].
- Price taps the level many times (4–5) before breaking out → skip [T qns-pt2@2076-2150].
- Breakout, then on the same day the price closes back through B → cancel, check again the next day [T qns-pt2@1700-2030].
- Monthly and weekly stories point opposite ways → **NO_TRADE** [T class-wrok@1236-1312].
- Never against the higher-timeframe trend [T liquidity-pt3@712-723].
- Trend unclear (range, takes effort to read) → skip [T story-line-pt4@1195-1217].

---

## 3. Entry (stage 2, summary only; see `knowledge-base/study/notes_entry.md`)

- Entry TF = the confirm TF (D story → H4, then 2H/1H).
- Advanced structure order seen on every chart: **sweep (wick) → BOS (body) → inducement → return to KL** [F advance-market-sturcture-pt2/pt3].
- Continuation model: A/V level, rejection, breakout, **retest = entry**. QMRO: entry at the shoulder level.
- SL beyond the invalidation; max ~10–15 pips (USD pairs), 15–20 (JPY). TP = story target. Max daily loss 0.5%.

---

## 4. Backtest measure

For each CONFIRMED story: did price reach the **target before the invalidation**? Report by pair, story
(M/W/D) and year: count, hit rate, average R, days to target. A coin-flip baseline must be beaten out of sample.

---

## 5. Settled points and remaining defaults

| # | Point | Answer |
|---|---|---|
| 1 | Swing detection | Turning points of the **close line**, fixed by a close beyond the previous opposite swing (§1). |
| 2 | Key-level price | **Body/close price** where two candles turn: the line-chart peak/valley, not the wick tip [F key-levels-pt1/sheet_018]. |
| 3 | Zone height | None: a thin line. Tap = wick touches/crosses the line, rejection = close back on the original side. |
| 4 | Daily close | 17:00 New York (TradingView forex and IC Markets cTrader use the same close). |
| 5 | Several fresh KLs | Most recent fresh KL that agrees with the trend (Kevin: "most recent") [T story-line-pt2@897-1000]. |
| 6 | Tap tolerance | OUR CHOICE: a wick within 1 pip of the line counts as a touch. |
| 7 | Max wait tap → breakout | OUR CHOICE: 5 origin-TF candles. |
| 8 | Pairs / sessions | All pairs, no session filter. |
