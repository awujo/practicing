# Kevin King SLK — Bias Strategy (v0.9, Claude branch)

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
**Which swing flips it (v0.9, `trend_mode`, owner decision 2026-10-14): the LAST V-shape (A-shape) of the current
leg** (`leg`, default). Kevin's weekly BOS: "there is already a weekly BOS here, the downside ... this was the last
V-shaped key level ... mark this guy as the BOS, like the external breakout on weekly timeframe" [T weekly-recap@343-376;
F weekly-recap/sheet_005 t=360: EURAUD W line 1.71717 at the base of the March-2025 rally, the last V before the top;
sheet_008 t=560: GBPAUD W line 2.0362 at the Sep-2025 V]; the reversal is the close beyond the most recent LH/HL,
"some people want to see the second break as extra confirmation, but me personally I use this first one"
[T basic-ms-pt3@875-1211]; on D he marks every close-line valley of the leg and "the most recent one" is the BOS
level [T weekly-recap@420-490, 976-1000; F weekly-recap/sheet_005-008]. Bot: the structural-swing rule above, but the
candidate swings are V/A-shape turns (close-line turning points of order `level_pivot` = 1, the same two-candle turn
as a key level) instead of order `swing_pivot` = 2, on every timeframe (M, W, D; H4 for the entry alignment): Kevin
teaches one structure for all timeframes and shows the last-V rule on W and D. `protected` = the v0.8 reading
(order 2): in a strong leg the order-2 rule found no pullback, so the protected low stayed at the leg's origin
(EURAUD W 1.6026 from Nov 2024 while Kevin's weekly BOS was the Jan 2026 close below 1.7172). ERL targets keep the
order-2 swings.

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
  When the origin TF points against the higher TF, the origin TF is only **retracing**: the levels of the higher-TF side
  count (v0.8, `pullback_levels`, §2 step 1).
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
   **Pullback (v0.8, `pullback_levels`, default on):** when the origin-TF trend points against the higher-TF trend
   (D down while W up), the daily is retracing and the story is taken in the **higher-TF direction**, from the levels
   of that side. Kevin: CADJPY "daily time frame is in the uptrend ... I say bullish again because normally we are
   already bullish. So these are just retracement" [T story-line-pt2@1420-1580; F story-line-pt2/sheet_010-013: the
   Jan 5-8 2026 drop to 112.903 inside the uptrend]; EURGBP "price has to break this place on daily to confirm that
   ... the weekly is ready to go back" (weekly reject weekly at the W V 0.8657 while the daily was down)
   [T all-in-1@1357-1388, 1570-1590]; USDCAD "the moment price closes below this ... daily time frame is now bearish"
   (W bearish, daily up into the KL) [T story-line-pt4@1465-1496]. Before v0.8 the D trend filter took only D-trend
   levels and the HTF filter removed every D-trend level against W, so **no D story could start while D and W
   disagreed** — exactly the state of all three examples. A range on either TF keeps the old rule.
2. **Pick the level.** Take the most recent **fresh** key level that agrees with the trend
   (A-shape or bearish OC for a sell), formed **before** the tap; older levels are ignored ("you place your mark at
   the most recent one ... we just remove everything and mark that last one") [T story-line-pt2@897-1000;
   F story-line-pt2/sheet_013-016]. Bot (#26, `most_recent_level`): a tapped level counts only if no newer fresh
   level of the same side existed at the tap; levels formed after the tap never count; a newer level that the tap
   candle closed through has failed ("abused ... not fresh"), so it does not block the deeper level that held.
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
- **Next Day Rule (built `next_day_rule`, §5 #21):** the cleanest breakout comes after the rejection candle has
  closed: "you go to four hours after the close of this day, you just see a clean breakout" [T story-line-pt3@1358-1401];
  the trade comes "the next day ... not that particular day" [T qns-pt2@1946-1962]. Every story carries `next_day`.
- **Retrace on the breakout day (flag, §5 #22):** the day that gave the breakout "should not trade back into the breakout
  zone"; if it does it is "no longer high probability" [T qns-pt2@1946-2030]. Flagged (`retrace`), not cancelled:
  only the D close back through B cancels (rule above).
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
  close rule). Continuation stories exist only through this chain. v0.8 (`align_retap_ends`, code default on): an
  H4 wick back to the protected D swing before the H4 break ends the chain; that tap is a new "daily reject daily"
  whose point B is the last A/V before THAT tap [T story-line-pt4@622-765: GBPJPY V 210.809 tapped Mon Jan 19 2026,
  Kevin builds the story from that tap and waits for its own H4 breakout; F story-line-pt4/sheet_009-010].
- **Swing ladder (bot helper):** on the daily close line, keep a line at every unbroken close-swing high/low extended right; these are the candidates for point B and for targets [F weekly-recap].
- **CADJPY exception (c, built `cadjpy_exception`, rule `cadjpy`):** weekly bullish + daily sweeps the previous-day
  low into a daily OC level and closes back above it → daily bias confirmed **without** an H4 breakout (at that D
  close); target = previous high [T cadjpy-bd@400-760, 940-995 "you really do not need to be waiting for this
  breakout again", 1380-1600; F cadjpy-bd/sheet_008-009: line ~113.2, sweep candle closes above, "target" 114.466].
  Only after the daily has **already flipped** that way: "after the bullish close above this guy, price did a sweep
  of previous day low", "weekly is bullish and now daily has flipped the zone" [T cadjpy-bd@440-560, 680-720;
  F cadjpy-bd/sheet_008: the big bull D candle closes above the D sell zone, the sweep comes 1-2 candles later].
  Bot: a D body close through an opposite key level within `max_wait` D bars before the sweep (Validation 4).
  v0.8 (`cadjpy_zone`, code default on): that flipped opposite level must be at **the same spot** as the swept level
  (within `overlap_tol_pips`), and the swept level must be a daily **open-close** level: "daily closed above the
  daily seller ... now daily has flipped the zone. Now when daily flipped the zone, price did a sweep of previous day
  low into the daily open close level", "price did a close above it back into the zone ... retest this key level and
  then continue the buy" [T cadjpy-bd@599-639, 693-739; F cadjpy-bd/sheet_008-009: the short line ~113.2 is the
  close of the big bull candle that broke the sell zone; the Mon Feb 2 2026 sweep goes into it]. When several levels
  are hit by the sweep wick, the OC level of the flipped zone starts the story (his line ~113.2, not the newer
  113.6 flip). Before v0.8 any OC/flip level and any opposite break anywhere counted: 22% of all D stories on the
  offline pairs (273 of 1214, -34.9 R) and it fired a wrong BUY in the USDJPY no-trade example; now 40 of 1582.
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
5. **Stop = beyond the invalidation zone** = the level's whole zone, all wicks from c1 up to the breakout (the two
   candles of the A/V shape and the rejection); only when that zone is too big (> `max_stop_pips`) beyond the
   rejecting candle [T entry3@247-385 "if the zone is too big you use this candle that got rejected ... if the zone is
   not big then you use this one, because this is the invalidation point", qns-pt1@1497-1660 "the safest is placing
   them at the invalidation zone ... no need to be selfish with your stop loss"; F entry-2/sheet_005-009 (stop beyond
   the rejection-candle zone), qns-pt1/sheet_021 (stop under the small zone, 14.9 pips), entry3/sheet_010-013 (37 →
   22 pips: big zone → rejection candle)].
6. **No entry after the story ended** (target reached, origin close back through the level, or a flip #29).

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

**Which timeframe:** H4 internal breaks first, most recent first, pick one with a 3rd-candle rejection; none → 2H → otherwise no trade.
D story: **H4 and 2H only, no 1H fallback** (owner decision 2026-10-14, `entry_tfs` `D=H4,H2;W=D,H4;M=W,D`): "if you
don't find it in 2 hours ... price is not giving you any entry" [T entry-2@668-713], "90% of my entries are from four
hours or two hours" [T entry3@2011-2016]. Backtest TP1 by entry TF: H4 −0.01 R, H2 −0.15 R, H1 −0.24 R. Entries stay
alert-only (no live trading on this model, REVIEW "Entry diagnosis").
A level that is rejected on H4 and 2H at the same price is stronger; D/H4/2H levels at *different* prices = "no overlap".
Choose the TF that gives the better risk/reward (EURGBP: daily 15.3 pips R 2.59; 4H 6.6 pips R 4.95) [F eurgbp-bd].

**OUR CHOICE (entry rules Kevin does not state; defaults, tuned by backtest):**
| Point | Default |
|---|---|
| Entry timeframes (`entry_tfs`) | Owner decision 2026-10-14: D story H4 → H2 (no H1), W story D → H4, M story W → D. H1 only as an experiment (backtest variant `entry_tfs` D=H4,H2,H1). TP1 avg R by TF (28 pairs): H4 −0.01, H2 −0.15, H1 −0.24. Alert-only. |
| Latest breakout candle | No limit by default (`breakout_max_bars` = 0); the user can set one in the Mini App. Kevin never gives a number. |
| Breakout candle | first candle with an impulsive body (≥ 1× average body of the last 10) closing beyond c1..(breakout−1); a non-impulsive close beyond just widens the base. |
| Stop (Model A) | `stop_at` = zone (default, 2026-10-14): beyond the highest wick (sell) / lowest wick (buy) of **c1**..(breakout−1) + 1 pip (Kevin's invalidation zone); if that is wider than `max_stop_pips`, beyond the c3..(breakout−1) rejection wick + 1 pip. Before 2026-10-14 the stop was always the c3.. wick: it ignored the c1/c2 wicks of the level, so the stop could sit *inside* the A/V shape (median 5.9 pips, a quarter under 3 pips, down to 0.2; REVIEW "Entry diagnosis"). `stop_at` = rejection keeps the old rule (golden test only). |
| QM swings | close-line pivots (order 2), consecutive shoulder → neck → head; head must be a higher close (sell) / lower close (buy). |
| QM validity | neck broken within `qmr_max_bars` = 30 QM-TF candles of the head, before any close beyond the head; the neck break must close after the story tap; a close beyond the head later kills the QM. |
| "Back in the zone and react" | the trigger-TF pattern's rejection wick reaches the neck line (± tap tolerance); first such pattern per QM, within 30 QM-TF candles of the neck break. |
| Trigger TF | H4/H2/H1 QM → 1H (his H4 → 1H); D QM → H4; W QM → D; never below the story's lowest entry TF (W story: H4 QM triggers on H4). |
| QMR stop | beyond the head wick + 1 pip if ≤ `max_stop_pips`, else the trigger line's own Model A stop (its zone, else its rejection wick). |
| Story end | no new entry after the story's own `end_time` (slk.story: target, origin close through the level, flip #29), besides the H1 target touch / origin close / `max_hold` checks. Before 2026-10-14 a flip did not stop entries (14% of the fills on the offline pairs came after the flip). |
| QM known | at the close of the later of the neck-break bar and the head pivot's confirmation (head + `pivot` bars); before 2026-10-14 the neck break alone (a break right after the head was used before the head was known). |
| Backtest costs | candles are bid; `spread_pips` (default 0 = none) puts a BUY fill and a SELL stop/TP on the ask. Same H1 bar stop + target = loss; the fill bar can only stop out. |
| QMR vs. continuation close together | no merged "stop covers both" zone; the rank rule above decides. |
| Alignment for continuation entries (`entry_alignment`, owner decision) | `d_h4` (default): model A only when D and H4 are in line = the CONFIRMED origin-TF story ("daily reject daily") AND the last H4 structural break (close beyond the last H4 close-line swing, §1) in the trade direction, checked at the pattern's breakout close [T entry-4@1670-1690 "I only like to trade continuation ... daily reject daily, 4 hours break, which means daily and 4 hours they are in line"; T entry3@696-818: W story, daily breakout, then a recent 4H breakout = "4 hours are aligned with daily ... that is our alignment"]. `w_d_h4`: also the last W structural break the same way [T weekly-recap@151-282, story-line@304-322]. `off`: no check. QMR not affected. Backtest compares all three (REPORT.md "Variants"). |

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
| 6 | Tap tolerance | v0.8: 0 (`tap_tol_pips`, was 1 pip): the wick must reach the line. Kevin: USDCAD "this very candle traded close to the open close key level but did not enter it ... acting as an inducement" [T story-line-pt4@1315-1335; F story-line-pt4/sheet_017 t=1320: line 1.39201, wick 1.39199 = 0.2 pip short, not a tap]. With 1 pip the bot took the GBPJPY Fri Jan 16 2026 wick 0.2 pip short of 211.386 as a tap and built a story Kevin never had. Broker differences are `level_tol_pips` (#25), off by default. |
| 7 | Max wait tap → breakout | OUR CHOICE: 5 origin-TF candles. |
| 8 | Pairs / sessions | All pairs, no session filter. |
| 9 | Structural swing candidates | Trend (v0.9, `trend_mode` leg): the high/low that must be broken is a V/A-shape turn of the close line (order `level_pivot` = 1), Kevin's "last V-shaped key level" (#27). Targets (ERL) and `trend_mode` protected: OUR CHOICE order `swing_pivot` = 2 (2 closes each side). |
| 10 | Point B turn | OUR CHOICE grounded in the V/A-shape definition (two candles turning) and the CADJPY replay: order `b_pivot` = 1 on the confirm-TF close line. |
| 11 | Sweep start on M | OUR CHOICE: Kevin shows previous day / previous week; the bot also allows previous month for the M story. Trend and HTF filters apply as for a key level. |
| 12 | Sweep start vs key level | OUR CHOICE: a key-level tap on the same origin bar wins; the sweep start is used only when no fresh trend level was tapped. |
| 13 | Other engine defaults | OUR CHOICE: `level_pivot` = 1, `max_hold` = 20 origin bars, `stop_buffer_pips` = 2, `max_retaps` = 3 (Kevin skips at "4-5" taps), `same_bar_close` on (written rule). |
| 14 | Rules #26/#29/#30/#31 on or off | All on by default (`most_recent_level`, `flip_end`, `htf_targets`, `overlap_rule`, `alignment_start`, `cadjpy_exception`; Mini App "Bias rules"): Kevin uses each one in class. Every story carries `rule` (standard / sweep_start / flip / alignment / cadjpy, `+overlap`) and `end_reason`. |
| 15 | Most recent level (#26) | OUR CHOICE: "most recent" = latest `born` among fresh same-side origin-TF levels (sweeps excluded) at the tap bar; a stale level tapped instead -> no KL start (the sweep start may still apply). |
| 16 | Flip (#29) | OUR CHOICE: "on the way" = strictly between the origin level and the target; only origin-TF key levels (no sweeps); first flip confirmed wins (ties: most recent level); it must happen inside `max_hold`; trade view exits at the flip close; the new opposite story keeps the HTF filter but not the origin-trend filter. |
| 16b | Flip age | **2026-10-15 `flip_max_age` = 100 bars:** a level broken by a body close becomes a fresh flipped level only if the candle that drew the line is at most 100 bars (of the level's TF) older than the break. OUR CHOICE: no limit before; then EURGBP D "tapped" 0.84614, a Jun-2024 open-close level on its 7th flip (owner: "I can't see any KL"). Flip count is no rule: Kevin's GBPJPY 211.386 [T story-line-pt4@1315] is a 3rd flip of a 3-week-old A. Examples pass the same (7/9) with 40..250. Labels: `level_src` (A / V / OC the line came from, kept by flips), `level_candle` (the candle whose close is the line), `chain` (W1→D1→H4 when the W trend agrees). |
| 16c | Standing bias | **2026-10-15 (owner, checked against Kevin):** the bias is not the story. A confirmed story sets the bias of its pair and timeframe; reaching the target, or running out of time, does not end it; a new same-side story is a continuation. It ends only when proven otherwise: a confirmed opposite story (BIAS CHANGE) or the holding story INVALIDATED / ENDED_FLIP (then no bias until the next story) [T story-line-pt4@1925-1967 "since we are still bearish ... price is not ready to buy yet ... after this weekly [reject] we are going to see daily breakout, we now know that price is ready to buy"; all-in-1@1249-1290 "we are still bullish on weekly ... because we are not close below this body"; weekly-recap@151]. `slk/standing.py`; alerts carry the bias line, the daily summary and the Mini App "Current bias" show it. Entries still come only from a confirmed story until its target. |
| 17 | Targets (#30) | **2026-10-15 `target_mode` = `leg` (default):** target = the external range liquidity of the leg = lowest low (sell) / highest high (buy) of the origin candles from the level candle to the tap, where the pullback into the level started [T liquidity@1444-1500 "whenever we take price from the internal range we always put our take profit at the external range", liquidity-pt2@1637-1658, weekly-recap@1200 "my first target would be this low before I target the weekly key level"]. Kevin's examples: EURAUD 1.6620 (bot 1.66234; old rule 1.67211), CADJPY 114.65 (114.639; old 113.848), GBPAUD 1.9029 (1.90805; old 1.91374). Already passed at confirmation → next structural swing, then KLs. Sweep starts, overlap (#31a) and CADJPY (#31c) keep their rules. `nearest` (before): OUR CHOICE nearest of (fresh opposite KLs of origin + all higher TFs as of their last closed candle, origin-TF structural swings = ERL); previous-candle highs/lows are not targets. |
| 18 | Overlap (#31a) | OUR CHOICE: `overlap_tol_pips` = 3 ("same spot"); only the next higher TF; the W candle must have closed by the confirmation (its nominal Friday 17:00 New York close, also in live where the last W bar is still forming), else the normal target; overlap TP = next KL, ERL only without a KL. |
| 19 | Alignment (#31b) | OUR CHOICE: W/D breaks = `structural_swings` fixes (§1); H4 break = close beyond the last order-`b_pivot` H4 close turn made since the D break bar started, within `max_wait` D bars, same-day D close; stop beyond the D break bar's wick; D story only. |
| 20 | CADJPY (#31c) | OUR CHOICE: D story only; level kind open-close (v0.8; v0.6 also took flipped levels) at the spot of the opposite level the daily closed through (v0.8, `overlap_tol_pips`); W trend (structural) in the story direction; the daily flipped that way first = a D body close through an opposite key level within `max_wait` (5) D bars before the sweep (Kevin: "after the bullish close above this guy"; the window is ours); tap candle wick beyond the previous D candle's low/high and close back beyond it; target = nearest D structural swing (ERL, "previous high"), else the normal target; point B shown as the level. |
| 21 | Next Day Rule | **Owner decision 2026-10-14: `next_day_rule` = `require` (default).** A story whose first valid breakout is inside the rejection candle is dropped (not moved to the next day); also in `current_tap` and flips, same for M→W, W→D, D→H4. `flag` (the default before) keeps every story and only marks `next_day`; alerts still say "✅ Next Day Rule". Alignment stories always break the next day; CADJPY has no breakout (`next_day` n/a, kept). Kevin: the trade comes "the next day ... not that particular day" [T qns-pt2@1946-1962], "you go to four hours after the close of this day, you just see a clean breakout" [T story-line-pt3@1358-1401]. Backtest (IC cTrader, 28 pairs 2018-2025, REPORT.md Variants): under `flag` next-day breakouts 5312 stories, 79.2% target, **+43.6 R**; same-day 4867 stories, 74.1%, **−188.3 R**; whole variant `require` −33.2 R vs `flag` −160.4 R. |
| 22 | Retrace warning | OUR CHOICE: `retrace` = a later confirm-TF candle of the origin bar holding the breakout closes back at/beyond B (known at that origin close = the confirmation, no look-ahead). Shown as a warning line (follow-up `RETRACE` alert if it ever appears after the CONFIRMED alert); never invalidates. |
| 23 | Early breakout alert | OUR CHOICE `early_breakout_alert` off by default: "H4 breakout — waiting for the daily close" when a closed confirm-TF candle inside the still-open origin candle closed beyond B of a TAPPED story. The row stays TAPPED; sent once per story (settings key `early_alerts_sent`). |
| 24 | Alert times | OUR CHOICE: alert times in `display_tz` (default Africa/Lagos), each labelled candle open or close; the rejection candle is named by its trading day (17:00 New York close: the D candle opening Wed 17:00 NY is Thursday's); "formed" = the origin candle at whose close the level existed. |
| 25 | Broker tolerance (`level_tol_pips`) | OUR CHOICE, default 0 (= exactly the behaviour before it existed, golden-tested): a wick that stops up to N pips (max 5) further from the line still counts as a touch. Added to `tap_tol_pips` (#6) and used for every WICK test: the tap, the fresh / untouched check of a level (and of target levels), the first touching confirm-TF candle (point B is the last turn before it) and re-taps. Never used for closes: a body close through a level (break / flip / invalidation) and the confirm-TF close beyond point B must be real closes beyond the price. Why: the bot's candles are IC Markets cTrader bid prices (Dukascopy fallback) while Kevin marks FOREX.com / OANDA charts; feeds differ by 1-2 pips, so a level Kevin sees tapped can miss by a pip on IC. |
| 26 | Pullback levels (v0.8) | OUR CHOICE details of §2 step 1: the higher-TF trend is the structural trend of its last CLOSED bar (as the HTF filter); only when both trends are up/down and differ; the story then needs the higher-TF side level, its own point B and external break as usual. Switch `pullback_levels` (Mini App, Bias rules); backtest variant `pullback_levels` on/off. On the 8 offline pairs (2022-2026) it adds ~480 D stories at -0.09 R each (all D stories -0.05 R): kept on because it is what Kevin does in all three examples, the owner may switch it off. |
| 27 | Trend definition (v0.9) | **Owner decision 2026-10-14: `trend_mode` = `leg` (default)**, Mini App setting (Bias rules), backtest variant `trend_mode` leg/protected. See §1 "Which swing flips it". Applies to every TF where the trend is read (origin trend, HTF trend/filter, pullback rule, M/W/D alignment breaks, CADJPY W trend, entry alignment H4/W breaks). OUR CHOICE: "V-shape" = close-line turning point of order `level_pivot` (1); ERL targets stay on order-2 swings. Offline 8 example pairs 2022-2026 (require): leg 1013 tradable stories, −10.6 R vs protected 1031, −40.4 R; Kevin's examples 7/9 → 8/9 (EURAUD and GBPAUD sells pass; USDCAD fails: on IC the W closed above its last A-shape 1.3798 on Jan 9 2026, REVIEW "Weekly trend definition"). |
| 28 | Pip size per symbol (2026-10-14) | Every `*_pips` setting (tap / level / overlap tolerance, stop buffer, `max_stop_pips`, `spread_pips`) and every "N pips" in alerts uses the symbol's pip (`slk/instruments.py`): the cTrader symbol's `pipPosition` when the candle file came from cTrader (kept in the store meta), else the table FX 0.0001, JPY quote 0.01, **XAUUSD 0.1**, **XAGUSD 0.01**, other metals 0.1, indices (US500, US30, USTEC, DE40, UK100, JP225 ...) 1.0. Prices are printed with the symbol's decimals (cTrader `digits`, else FX 5, JPY 3, gold 2, silver 3, indices 2). Before, every non-JPY symbol used 0.0001 and 5 decimals: gold tolerances/buffers were 1000x too small (stop buffer 0.0002 instead of 0.2) and prices read "4154.36000". Point B, levels and targets never depend on the pip (absolute prices). |
