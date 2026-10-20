# Kevin's lower-timeframe entry cues (study agent, 2026-10-20)

Extracted by an independent read-only agent from knowledge-base/ transcripts, frame notes (knowledge-base/study/
frames_E..H.md), notes_entry.md and STRATEGY.md §3. T = knowledge-base/videos/kevin-<video>/transcript.txt @ s,
F = frame notes. [RULE] = stated as a rule / repeated, [ONCE] = shown or said once. Used for the feature list of
slk/ltf_features.py and slk/trend_study.py.

## Ladder and trigger
1. [RULE] One TF below the bias: W bias -> D, D bias -> H4; then 2H; 1H only when price already reacts at the H4
   level. H4 and 2H show nothing -> no trade. T entry-2@668-713, introduction-to-entry@494-595, cadjpy-bd@2016-2081.
2. [RULE] "90 percent of my entries are from four hours or two hours". M15/M5 shown only to mislead copiers; "don't
   be asking me question regarding [15/5 min]". M15/M5 data NOT needed. T entry3@1976-2072, entry-4@111-135, qns-pt1@488-505.
3. [RULE] Continuation level: 2 candles turn at one close (A/V), 3rd wicks in and closes back, later candle closes
   beyond -> entry at the retest. T entry-2@35-120, 290-430.
4. [RULE] Newest breakout level replaces an older pending one, unless that one is a QMR. T qns-pt1@840-1065.
5. [RULE] First (external) break only confirms; entries come from later internal breaks. T entry-2@1520-1550, qns-pt2@1400-1430.
6. [RULE] Skip the first fast move after the breakout; wait for the first pullback + new H4 break. T introduction-to-entry@1398-1560.
7. [RULE] QMR: no blind limit; wait for the reaction in the zone, then a 1H breakout. T entry-4@1662-1850.
8. [ONCE] "Confirmation entry inside the level" saves stop, never defined. T entry-2@1458-1495.
9. [RULE] No inducement needed for entries. T entry-2@1655-1693.

## Candle / level quality
10. [ONCE] Impulsive "volume" breakout candles preferred; no threshold. T entry3@995-1117.
11. [ONCE] Engulfing from a 2H QMR inside a 4H zone = "your entry". T cadjpy-bd@1304-1367.
12. [RULE] Wick through the line, body closes back. Lines on line-chart closes.
13. [RULE] Clean: HTF candle closed, clean break, no same-day retest; 4-5 taps before the break -> leave it. T qns-pt2@2070-2160.
14. [RULE] Overlap of fresh D/H4/2H levels at one spot = stronger. T cadjpy-bd@811-905, entry3@441-449.
15. [ONCE] No retest -> missed, don't chase. T entry-2@790-860.

## Not in the sources
16. Sessions: "we don't actually treat sessions" (liquidity-pt2@438-448). 17. FVG / imbalance not used.
18. "Choppy" never said; unclear trend -> skip (story-line-pt4@1195-1217).

## Stop
19. [RULE] Stop at the invalidation zone; big zone -> beyond the rejection/doji candle. T qns-pt1@1464-1537, entry3@247-385.
20. [RULE] USD majors 10-15 pips (often 5-10), JPY 15-20; over ~15-20 "I don't have a better entry". T qns-pt1@1553-1653, weekly-recap@1328-1350.

## TF choice, TP, trend
21. [RULE] Pick the entry TF with the bigger RR (EURGBP: D RR 2.59 vs 4H RR 4.95 taken). T eurgbp-bd@856-892.
22. [ONCE] "4H reject 4H + 1H breakout" only: TP1 1H swing (1:2), TP2 next H4 level (1:5); full D story = hold longer. T class-wrok@563-610, 785-854.
23. [RULE] First target = low before the tap (ERL), then the opposite KL; never TP beyond an opposing D cluster.
24. [RULE] With the trend only, D and H4 in line. T introduction-to-entry@1213-1290, entry-4@1670-1690.
25. [ONCE] Optional: second H4 QMR, or refine on 2H/1H ("CRT"). T weekly-recap@1220-1248, 1407-1427.

## The 6 dated trades (tests/kevin_trades.json)
- EURAUD H4 sell 17 Feb: W+D bearish, 4H level inside D/W level 1.6793-1.6809, 4H QMR, entry 1.6748 retest at the shoulder, stop 18.7 p, TP 4H low 1.6620 (point B), RR 4.71.
- GBPAUD H2 sell 19 Feb: 4H A 1.9143, 4H->2H->1H->30m; "2 hours was good clean"; entry 1.9125 stop 18.5 p TP 1.9029 RR 2.1 (30m RR 5.24).
- USDCHF H1 buy 21 Jan: D range low 0.7890 sweep + D reject D, no 4H break -> next day 4H reject 4H, 1H breakout; entry 0.78997 stop ~10 p, TP1 1H swing (1:2), TP2 0.79504 (1:5) hit.
- EURGBP H4 sell 2 Feb: W + D breakdown; D entry RR 2.59 skipped; 4H level with 3rd-candle rejection, stop by the indecision candle 6.6 p, RR 4.95, worked.
- EURGBP H4 buy 15 Jan: D V 0.8657 tapped; 4H EXB on the 18th; entry 0.8675 stop under the V/IDM 16-22 p, TP 0.8723 hit.
- USDJPY H1 buy 12 Dec: "entry type 2B"; 1H box 155.50-155.60, entry 155.599, stop 155.450 (14.9 p), TP 156.049 RR 3.02. Correction: frames_G says price later ran down through it; the transcript does not say the TP was hit.
