# Kevin King SLK — Bias Strategy (v0.4, Claude branch)

Built from the `kevin_King` course only. All 29 transcripts plus every contact sheet (~700) of all videos.
Evidence with timestamps: `knowledge-base/study/notes_*.md` (transcripts) and `frames_*.md` (pictures, A–H).
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
   The confirm TF may also show a **sweep + break (QM)** instead of a plain break; either confirms [T story-line-pt2@330-436].
   Point B is read with the tap candle hidden (he uses TradingView Replay) so the swing is found as it was before the tap [F qns-pt1/pt2].
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
- After an H4 breakout in a **daily** story, the daily candle must also close beyond B the same day, otherwise cancel [F qns-pt2].
- **Overlap:** a weekly KL that is also a daily KL counts as "daily rejects daily"; the weekly target becomes the TP. A weekly tap is judged only after the weekly candle closes [F all-in-1, T class-wrok@480-620].
- **Alignment (continuation):** a weekly close beyond the last weekly swing first, then Daily and H4 must break the same way. No alignment, no trade [F weekly-recap].
- **Swing ladder (bot helper):** on the daily close line, keep a line at every unbroken close-swing high/low extended right; these are the candidates for point B and for targets [F weekly-recap].
- Exception seen on CADJPY: weekly bullish + daily sweeps the previous-day low into a daily OC level and closes back above it → daily bias confirmed **without** an H4 breakout; target = previous high [F cadjpy-bd].

---

## 3. Entry (after bias is confirmed)

Entry boxes are allowed (a small grey rectangle ~10–20 pips around the entry zone). Key levels stay thin lines [F cadjpy-bd, eurgbp-bd].

Two entry models (`entry_models` setting, both on by default; each entry row carries `model`). Both need:
bias already confirmed (external break only; entries never change the bias), a 3rd-candle rejection,
break and retest, the most recent level.

**Model A — continuation ("A series"):** [T introduction-to-entry, entry-2/3, F entry-2/sheet_005-009, entry3]
1. On the entry TF, two candles (c1, c2) form an A/V level (thin line at the shared body price, extended right 5–12 candles).
2. The **3rd candle rejects** the level with a wick (wick to the line, body closes back). More rejecting candles after it are fine.
3. The **breakout = the 4th candle OR ANY LATER candle** ("4th+ candle BREAKS out", frames_E): an impulsive body close
   beyond the c1..(breakout−1) extreme (internal BOS). No candle may **close back through the line** before the
   breakout (that kills the level). There is no limit on how many candles later the breakout comes (Kevin gives none); `breakout_max_bars` (0 = no limit, default) can set one.
4. **Entry = retest of that line.** Skip the first retracement after the external breakout. If price never retests → missed, do not chase.

**Model B — QMR = Quasimodo Reversal ("B series"; Whisper transcribed it "QMRO"):** [T entry-4@830-1905, cadjpy@117-260,
F entry-4/sheet_011-023, introduction-to-entry/sheet_017-021, cadjpy-bd/sheet_024]
1. On the entry TF close line, in the bias direction (sell shown): **shoulder** (swing high) → **neck** (the swing low
   between) → **head** (a higher close than the shoulder = liquidity sweep beyond it) → a **body close below the neck**.
   QMR zone = the shoulder and neck lines (thin lines; the entry *area* may be boxed).
2. No blind limit order: wait for price to come **back into the shoulder/neck zone and react**, then a **lower-TF (1H)
   breakout** in the bias direction there (= a Model-A pattern on the trigger TF whose rejection reached the zone).
3. **Entry = retest of that 1H line** (continuation). Stop beyond the **head**; if that is wider than `max_stop_pips`,
   beyond the rejecting candle (notes_entry §3: big zone → stop on the rejection candle). TP1/TP2 as Model A.
4. **Rank:** QMR level with rejection > breakout level with rejection > plain level. A newer level replaces an older
   pending one, except that a pending QMR is not replaced by a newer continuation level [T q1@840-1065, e4@1420-1440].

**Which timeframe:** H4 internal breaks first, most recent first, pick one with a 3rd-candle rejection; none → 2H → 1H → otherwise no trade.
A level that is rejected on H4 and 2H at the same price is stronger; D/H4/2H levels at *different* prices = "no overlap".
Choose the TF that gives the better risk/reward (EURGBP: daily 15.3 pips R 2.59; 4H 6.6 pips R 4.95) [F eurgbp-bd].

**OUR CHOICE (entry rules Kevin does not state; defaults, tuned by backtest):**
| Point | Default |
|---|---|
| Latest breakout candle | No limit by default (`breakout_max_bars` = 0); the user can set one in the Mini App. Kevin never gives a number. |
| Breakout candle | first candle with an impulsive body (≥ 1× average body of the last 10) closing beyond c1..(breakout−1); a non-impulsive close beyond just widens the base. |
| Stop (Model A) | beyond the highest wick (sell) / lowest wick (buy) of c3..(breakout−1) + 1 pip. |
| QM swings | close-line pivots (order 2), consecutive shoulder → neck → head; head must be a higher close (sell) / lower close (buy). |
| QM validity | neck broken within `qmr_max_bars` = 30 QM-TF candles of the head, before any close beyond the head; the neck break must close after the story tap; a close beyond the head later kills the QM. |
| "Back in the zone and react" | the trigger-TF pattern's rejection wick reaches the neck line (± tap tolerance); first such pattern per QM, within 30 QM-TF candles of the neck break. |
| Trigger TF | H4/H2/H1 QM → 1H (his H4 → 1H); D QM → H4; W QM → D; never below the story's lowest entry TF (W story: H4 QM triggers on H4). |
| QMR stop | beyond the head wick + 1 pip if ≤ `max_stop_pips`, else beyond the trigger rejection wick + 1 pip. |
| QMR vs. continuation close together | no merged "stop covers both" zone; the rank rule above decides. |

**Stop loss:** just beyond the rejecting candle / small zone. Seen: 8–21 pips; 15–20 pip max is stated, 38 pips called "valid but unwanted"; skip if spread is wide (AUDNZD, NZDCHF avoided) [T wr@1590-1630].
**Take profit:** TP1 = next key level / R 1.4–2, TP2 = point B / target, R up to ~5 [F weekly-recap, all-in-1].
**Risk:** max daily loss 0.5% [T structuring@836-880]. Take ~1–2 clean setups per week; no session or news rules exist.

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
