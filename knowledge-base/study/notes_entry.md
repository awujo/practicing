# Kevin King (SLK) - Bias -> Entry rules (codeable notes)
Tags: [T video@sec] transcript, [F video/sheet] frame. Videos: intro=kevin-introduction-to-entry, e2=kevin-entry-2, e3=kevin-entry3, e4=kevin-entry-4, cad=kevin-cadjpy-bd, eg=kevin-eurgbp-bd, q1/q2=kevin-qns-pt1/pt2. Transcripts are noisy Whisper; "third candle", "rejection", "a-shape/v-shape" = key levels.

## 1. Bias (HTF) -> entry (LTF)
- Two-step storyline, always TWO timeframes: [T q2@110-195]
  1. HTF "tap + reject + close": price taps an A-shape (supply) / V-shape (demand) key level on HTF, rejects it, and the HTF candle CLOSES back beyond the level (e.g. below an A-shape = bearish). Wait for the HTF candle to close (week/day) before acting; acting mid-candle is allowed but "not the best". [T q2@283-480, 596-618]
  2. Confirmation on the NEXT lower TF, exactly one of: (a) QM / "sweep and break" (liquidity sweep + tap + structure break), or (b) a breakout (BO) of the last opposite-shape level created before price tapped the HTF level. [T q2@636-760]
  - If step 2 absent: "only a rejection", no storyline, skip pair. [T q2@723-760]
- TF pairs: monthly->weekly->daily->H4 chain. Weekly bias -> daily confirms -> entries on daily (or lower); daily bias -> H4 confirms -> entries on H4 (2H/1H allowed); monthly -> entry on weekly. [T intro@256-370, q2@110-195]
- Entry TF = the TF that produced the confirming breakout (or "very next TF"). If it shows no valid level, drop one TF (H4 -> 2H, then 1H) but only if price is already reacting from the H4 level. [T intro@494-595, e2@5-34, e2@668-713, cad@1001-1017]
- Breakout definition (the BO to mark): the LAST opposite-shape key level formed BEFORE the candle that tapped the HTF level; remove the tapping candle first, then take the last shape before it. Bearish: break below last V-shape; bullish: break above last A-shape. Candle CLOSE beyond is implied (not explicit). Called "external break". [T q2@1198-1310, 1394-1500]
- Breakouts AFTER the tap (post-BO) are "internal breaks" and are used for entries; the external break is only direction confirmation, not an entry. [T q2@1400-1430, e2@1520-1550, e3@1735-1750, 1873-1885]
- Standard break (external) = confirm direction; internal break = entries. [T e2@1536-1550]
- "Does BO come with entry?": check if BO level itself has 3rd-candle rejection -> entry already exists; otherwise wait for retrace to BO level / shoulder / head. [T e2@1430-1460, intro@1020-1110, eg@637-682]
- Counter-trend: ignore. One-sided; only look for entries in bias direction until TP hit. [T intro@1213-1290]
- Bias can end when target reached (HTF target e.g. previous high/low, CRT target, opposite HTF level); until then keep taking every valid continuation entry (multiple entries per bias). [T e2@1570-1612, cad@1999-2011, q2@1553-1600]
- Alternative HTF-aligned bias (cad): weekly bullish + daily closes back above a daily key level after sweep of previous-day low into daily open-close level => daily flips bullish; H4 BO NOT required; entries can start from daily/H4/2H levels that overlap; TP = previous-day high / external range liquidity. [T cad@62-120? actually 400-760, 940-995, 1380-1600]
- Mixed-TF overlap bonus: same zone is key level on daily + H4 + 2H (must be same spot, and fresh) = very strong. [T cad@811-905, 1590-1680]

## 2. Entry models
### Model A "Continuation" = breakout + retest, "3rd-candle rejection" level (a.k.a. "A series")
- Pattern (candles 1..5): c1+c2 form an A/V-shape key level (two opposite-direction candles); c3 taps/ rejects that level (wick into it, no close through); c4 breaks out in bias direction; c5 retests the level -> entry. c3 MUST be the rejection (more rejections fine, but 3rd must be one). [T e2@35-120, 290-350, 757-767] [F e2/sheet_004: his demo drawing: small 3 candles + big box; long position box shown with R:R 3.34, stop 31.6 pips]
- Level must be the most recent breakout level (internal BO) in the bias direction. All BOS levels are NOT equal: use ones with 3rd-candle rejection; others ignore. [T e2@350-430, e3@558-573]
- Preference order of checking: H4 BO levels -> if none has 3rd-candle rejection, go to 2H (then 1H after H4 reaction). [T e2@668-713, 880-940]
- Level with same rejection on both H4 and 2H = stronger. [T e3@441-449]
- Entry price: retest of the level (limit at level; he says limit order at level is fine, or use LTF confirmation inside the zone to cut stop). [T e2@1458-1495, 1668-1680]. Zone = from level edge (open/close or wick) - exact edge not stated -> resolve.
- No inducement required for entry (inducement only for bias building). [T e2@1655-1727]
- "Missed entry": price may create the level and never retest -> skip, don't chase. [T e2@790-860, cad@1393-1410]
- If a newer BO creates another qualifying level before price retests the first, FORGET the old one, use the most recent (unless the older one is a B-series/QM or on higher TF and price is at HTF key level). [T q1@840-1000, 1020-1065]
- Candle-shape tie-breaker: prefers impulsive BO (volume); candle that formed rejection level vs. neighbour levels that are not "volume" candle excluded. [T e3@1005-1050, 1100-1118]
- Entry executed on LTF screenshot may be 15m/1h, but real trigger is H4/2H; "90% of entries from H4/2H". [T e3@1970-2016] [F e2/sheet_017: USDJPY 1h short, stop ~9 pips, R:R 5.28 drawn]

### Model B "QMRO" (Quasimodo; "B series"; stronger than A)
- Needed: HTF bias + (e.g. daily rejects daily & H4 sweep-of-liquidity + BOS) = QM on the confirmation TF. Three zones: neck (BO level), shoulder, head/apex. Kevin uses the SHOULDER level (not head, not always neck) as the entry. [T e4@830-1000]
- Zone must have 3rd-candle rejection; if both QM level and an A-model level have rejection and are close (< few pips), take QM; stop covers both. [T e4@1100-1260, 1422-1432; T cad@117-260]
- Rank: QMRO level w/ rejection > BO level w/ rejection > plain level. [T e4@1420-1440, cad@147-190]
- QMRO is reversal; he does not limit-order it directly (zone can be deep): wait for price to react from QM zone, then wait for LTF (1H) BO in bias direction, THEN take continuation. [T e4@1650-1850] (rarely limit directly)
- If neck/shoulder not rejection-qualified, wait for next. If ANY level has no rejection, no entry there. [T e4@1893-1905]
- Example: in eg frames H4 breakdown, then a zone retrace; [F eg/sheet_008] shows H4 gray zone+ retest of 0.8670 area then sell-off.

### Both models require: third candle rejection, "break and retest", most recent BO, bias already confirmed.

## 3. Stop-loss, TP, RR
- Default SL: at invalidation (far side of key-level zone incl. wick). If zone is large (>~15 pips), use the rejecting 3rd candle (esp. doji/indecision) instead: SL beyond that candle. [T e3@240-340, q1@1464-1520, eg@682-715]
- Pip caps: USD majors 10-15 pips (most entries 5-10); JPY pairs 15-20; if > ~15 pips (majors) usually skip. [T q1@1553-1640, e3@1166-1176 "10 pip stop", eg@360-390 "15 pip SL, 1:3 RR"]. Skip pairs with spread > ~5 pips (NZD, CHF crosses, AUDNZD). [T e3@1786-1850, 2157-2161]
- TP: next HTF target (previous day/week high/low, CRT target, next opposite key level, external range liquidity). Hold until target; multiple continuation entries en route. [T e2@1570-1612, cad@1580-1600]
- RR: no fixed minimum stated; he cites 1:3 on 15 pips (eg@385), 1:5 as typical goal (q1@330-350). eg@863-895: took H4 (not daily) entry purely because daily-level entry RR too small -> choose the entry TF that gives bigger RR. Coder: implement min RR param (suggest >=3, flag as assumption).
- Risk per trade: not given as %; examples 1% ($500 on 50k, $1000). [T q1@510-530] Stated loser acceptance: win rate 40-50% fine with good RR [T e4@178-199].
- Frequency: 1-2 setups/week fine; no time pressure; "no entry, no trade". [T q1@410-470, intro@210-243, e3@1324-1366]

## 4. Skip / filters (checklist)
- Wait for HTF candle close before bias (week/day). [T q2@364-393]
- Clean setup only: if price taps HTF level multiple times (4-5) before BO -> skip. [T q2@2076-2150]
- Daily-reject-daily + H4 BO: if price retests the BO level and CLOSES back through it on the SAME day, cancel; trade only if the daily closes on the BO-side; entries allowed from NEXT day. [T q2@1700-1760, 1905-1960, 2008-2030]
- EURAUD example: cancelled idea that day, valid next day. [T q1@45-75]
- Skip if SL too large (> caps), spread high, no 3rd-candle level on H4/2H. [T e3@1686-1705, 1786-1850]
- Do not trade counter to bias; do not catch the first reversal move after BOS/QM, wait for first retracement + new BO ("proper alignment"). [T intro@1396-1560, e4@1520-1620]
- News/session: NOT discussed in these videos (screens show 05:xx-06:xx UTC+1 live sessions; no session filter stated). Flag as unresolved.

## 5. Vague points for coder
1. "Key level" detection: V/A shape = 2 opposite candles; edges open/close vs wick; line charts used to see "open-close" levels (e2@960-980; q2@1175). Need rule (suggest zone = body-to-wick of the two candles).
2. "Third candle rejection": c3 wick into zone, close outside; exact tolerance unspecified; indecision/doji preferred for SL.
3. Which of multiple qualifying levels: most recent; B>A; HTF overlap stronger; closest-to-liquidity/inducement also cited (q2@1760).
4. Entry order type: limit at level vs confirmation entry; limit at zone edge assumed.
5. BO validity: close vs wick not stated; "tiny breakout is still a breakout" (e4@1983).
6. Bias expiry / target definition: CRT, previous day/week extreme; unspecified algorithmically.
7. Fresh level requirement (cad@854-905): level untouched since creation (2 candles).
8. Frame notes: [F e2/sheet_004] only shows hand-drawn demo & R:R tool, consistent with transcript; [F cad/sheet_015] shows H4 CADJPY replay 113.8 BO retest area (small level drawn at ~113.80); [F eg/sheet_008] H4 gray supply zone + horizontal level 0.8660 area; [F e3/sheet_024] AUDNZD 2h replay (he rejects trade: spread). [F e4/sheet_012] shows QM sketch (BTC, head/shoulder/neck lines) matching transcript. No frame contradicted transcripts.
