# Kevin King SLK — Bias Strategy (v0.6, Claude branch)

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
[T basic-ms@159-620, F basic-ms/sheet_004]. The low that counts is "the lowest point that pushed price to take out
the high"; if price dips deeper before the break, the deeper dip becomes the HL [T basic-ms@456-620].
Bot (`slk/structure.structural_swings`, used for **trend and targets**): a close above the last swing high fixes
the swing low = lowest close since that high; a close below the last swing low fixes the swing high = highest
close since that low (against the trend = BMS). The high/low to be broken is the most extreme close-line turning
point since the last fix, so a lower high inside an uptrend pullback (higher low in a downtrend) is never a swing.
Swings are known only at the breaking close (no look-ahead).

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
   (A-shape or bearish OC for a sell), formed **before** the tap; older levels are ignored ("you place your mark at
   the most recent one ... we just remove everything and mark that last one") [T story-line-pt2@897-1000;
   F story-line-pt2/sheet_013-016]. Bot (#26, `most_recent_level`): a tapped level counts only if no newer fresh
   level of the same side existed at the tap; levels formed after the tap never count.
   Also mark the target: the next opposite fresh KL of the **same or a higher TF** (D story: D, W, M levels;
   W story: W, M; M story: M "next monthly fresh level"), or the ERL, whichever comes first, so the TP is capped at the
   next level of the weaker TF [T story-line@648, story-line-pt2@1914-1968, class-wrok@480-620; F story-line-pt2/
   sheet_025-028]. Bot (#30, `htf_targets`): each higher-TF level as of its last closed candle.
3. **Tap, reject, close (origin TF, candles).** A candle **wicks into** the level and **closes back below it**.
   Wait for the candle to close. → status `TAPPED`
   *Alternative start (no key level):* the origin candle's wick sweeps the **previous origin candle's high**
   (previous day high for D, previous week high for W) and the candle closes back below it; then the same steps 4-6
   with point B = the last lower-TF V-shape made **before the sweep** (the sweep candle's own swing does not count)
   and invalidation = a body close back above the swept high [T story-line-pt3@1887-2096, pt4@1349-1500;
   F story-line-pt3/sheet_026-029]. "Sometimes there will not be any key level": the bot uses it only on a bar
   where no fresh trend level was tapped (a sweep INTO a key level, like USDCAD, is that level's tap). Built
   (`sweep_start`, kind `sweep`).
4. **Find point B (confirm TF).** On the lower timeframe, find the **last swing low made before price first
   tapped the level**. Not the low made by the rejection itself [T story-line-pt3@1690-1790, F story-line-pt2].
   "Last V-shape" = the last valley of the lower-TF close line, i.e. a two-candle turn (as the V key level); in the
   CADJPY replay B is the small 4H close peak (~113.2) right before the tapping 4H candle [F story-line-pt2/sheet_015
   t=1140-1180]. Bot: close-line turning points of order `b_pivot` = 1 made before the first touching lower-TF
   candle; the touching candle's close may complete that turn.
5. **Breakout (confirm TF, candles).** A candle **body closes below B** → story **confirmed**, bias **BEARISH**.
   He labels it `bms` / `EXT`. Any later breaks are internal BOS and are for entries only.
   The confirm TF may also show a **sweep + break (QM)** instead of a plain break; either confirms [T story-line-pt2@330-436].
   Point B is read with the tap candle hidden (he uses TradingView Replay) so the swing is found as it was before the tap [F qns-pt1/pt2].
6. **Hold until:**
   - target reached → `TARGET_HIT`;
   - a body close back above the origin level → `INVALIDATED`;
   - a daily KL on the way is rejected the other way **and** H4 breaks the other way → story over, status
     `ENDED_FLIP` with the reason, and the opposite story may start from that level [T story-line-pt2@1779-1869:
     "the moment we tap on another daily key level before the zone we are expecting price to come into, the moment
     price closes below it and then gives us a breakout in four hours, it means that that daily has flipped";
     F story-line-pt2/sheet_023: CADJPY levels 113.946 / 113.49 between origin 112.903 and target 114.65].
     Bot (#29, `flip_end`): an opposite fresh origin-TF key level strictly between the origin level and the target,
     tapped-rejected-closed after the confirmation, then a confirm-TF body close beyond **its own point B** (same
     external-break rules: last V/A before its first touch, same-day close, `max_wait`, `max_retaps`). The trade view
     closes at that close (outcome `flip`); the new story (rule `flip`) skips the origin-trend filter (the flip is
     the change of direction) but keeps the higher-TF filter.

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
- **Overlap (exception a, built `overlap_rule`, rule `+overlap`):** a weekly KL that is also a daily KL (same spot,
  fresh) counts as "daily rejects daily": the D story with its H4 breakout. A weekly tap is judged only after the
  weekly candle closes [T all-in-1@1424-1620, cadjpy-bd@811-905 "for it to overlap it needs to be on the same spot";
  F all-in-1/sheet_020-027, qns-pt2]. TP: Kevin says "instead of swing it to here, we take our profit at this key
  level" and the frame shows TP at the next KL 0.8722 (EURGBP) — so the TP is the **next opposite key level** (same
  or higher TF), not a far swing; this replaces v0.5's "the weekly target becomes the TP" (the 0.8722 line is the
  next D/W key level, and class-wrok@480-620 caps the weaker TF the same way). Bot: origin D level within
  `overlap_tol_pips` of a fresh W level of the same side whose first touch is on the W candle holding the D tap, that
  W candle closed by the confirmation; target = nearest opposite KL, ERL only if there is none.
- **Alignment (continuation, exception b, built `alignment_start`, rule `alignment`):** a weekly close beyond the
  last weekly swing first, then Daily and H4 must break the same way. No alignment, no continuation trade
  [T weekly-recap@151-282, 626-670, 2098-2160 ("if weekly does this, wait for daily to do it"); F weekly-recap/
  sheet_003-008]. Bot: last W structural break closed before the D bar, that D bar closes beyond the last D
  structural swing the same way (origin = the protected D swing, invalidation = a D close back through it), then
  within `max_wait` D bars an H4 close beyond the last H4 close turn made since that D bar started (same-day D
  close rule). Continuation stories exist only through this chain.
- **Swing ladder (bot helper):** on the daily close line, keep a line at every unbroken close-swing high/low extended right; these are the candidates for point B and for targets [F weekly-recap].
- **CADJPY exception (c, built `cadjpy_exception`, rule `cadjpy`):** weekly bullish + daily sweeps the previous-day
  low into a daily OC level and closes back above it → daily bias confirmed **without** an H4 breakout (at that D
  close); target = previous high [T cadjpy-bd@400-760, 940-995 "you really do not need to be waiting for this
  breakout again", 1380-1600; F cadjpy-bd/sheet_008-009: line ~113.2, sweep candle closes above, "target" 114.466].
  Mirror for sells. The only place where the external break is not required.

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
| 1 | Swing detection | Turning points of the **close line**, fixed by a close beyond the previous opposite swing (§1), for trend and targets. Point B uses the last close-line V/A turn before the tap (§2 step 4). |
| 2 | Key-level price | **Body/close price** where two candles turn: the line-chart peak/valley, not the wick tip [F key-levels-pt1/sheet_018]. |
| 3 | Zone height | None: a thin line. Tap = wick touches/crosses the line, rejection = close back on the original side. |
| 4 | Daily close | 17:00 New York (TradingView forex and IC Markets cTrader use the same close). |
| 5 | Several fresh KLs | Most recent fresh KL that agrees with the trend (Kevin: "most recent") [T story-line-pt2@897-1000]. |
| 6 | Tap tolerance | OUR CHOICE: a wick within 1 pip of the line counts as a touch. |
| 7 | Max wait tap → breakout | OUR CHOICE: 5 origin-TF candles. |
| 8 | Pairs / sessions | All pairs, no session filter. |
| 9 | Structural swing candidates | OUR CHOICE: the high/low that must be broken is a close-line turning point of order `swing_pivot` = 2 (2 closes each side); Kevin gives no size for "main leg". |
| 10 | Point B turn | OUR CHOICE grounded in the V/A-shape definition (two candles turning) and the CADJPY replay: order `b_pivot` = 1 on the confirm-TF close line. |
| 11 | Sweep start on M | OUR CHOICE: Kevin shows previous day / previous week; the bot also allows previous month for the M story. Trend and HTF filters apply as for a key level. |
| 12 | Sweep start vs key level | OUR CHOICE: a key-level tap on the same origin bar wins; the sweep start is used only when no fresh trend level was tapped. |
| 13 | Other engine defaults | OUR CHOICE: `level_pivot` = 1, `max_hold` = 20 origin bars, `stop_buffer_pips` = 2, `max_retaps` = 3 (Kevin skips at "4-5" taps), `same_bar_close` on (written rule). |
| 14 | Rules #26/#29/#30/#31 on or off | All on by default (`most_recent_level`, `flip_end`, `htf_targets`, `overlap_rule`, `alignment_start`, `cadjpy_exception`; Mini App "Bias rules"): Kevin uses each one in class. Every story carries `rule` (standard / sweep_start / flip / alignment / cadjpy, `+overlap`) and `end_reason`. |
| 15 | Most recent level (#26) | OUR CHOICE: "most recent" = latest `born` among fresh same-side origin-TF levels (sweeps excluded) at the tap bar; a stale level tapped instead -> no KL start (the sweep start may still apply). |
| 16 | Flip (#29) | OUR CHOICE: "on the way" = strictly between the origin level and the target; only origin-TF key levels (no sweeps); first flip confirmed wins (ties: most recent level); it must happen inside `max_hold`; trade view exits at the flip close; the new opposite story keeps the HTF filter but not the origin-trend filter. |
| 17 | Targets (#30) | OUR CHOICE: nearest of (fresh opposite KLs of origin + all higher TFs as of their last closed candle, origin-TF structural swings = ERL); previous-candle highs/lows are not targets. |
| 18 | Overlap (#31a) | OUR CHOICE: `overlap_tol_pips` = 3 ("same spot"); only the next higher TF; the W candle must have closed by the confirmation, else the normal target; overlap TP = next KL, ERL only without a KL. |
| 19 | Alignment (#31b) | OUR CHOICE: W/D breaks = `structural_swings` fixes (§1); H4 break = close beyond the last order-`b_pivot` H4 close turn made since the D break bar started, within `max_wait` D bars, same-day D close; stop beyond the D break bar's wick; D story only. |
| 20 | CADJPY (#31c) | OUR CHOICE: D story only; level kind open-close or flipped (his "daily open close level" was a flipped zone); W trend (structural) in the story direction; tap candle wick beyond the previous D candle's low/high and close back beyond it; target = nearest D structural swing (ERL, "previous high"), else the normal target; point B shown as the level. |
