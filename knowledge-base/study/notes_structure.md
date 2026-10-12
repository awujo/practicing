# Kevin King (SLK) - market structure notes (intro, basic-ms 1-3, advance-ms 1-3)
Tags: [T video@s] transcript, [F video/sheet_NNN] frame. Videos abbreviated: bms=kevin-basic-ms, bms2/bms3, ams=kevin-advance-market-sturcture, ams2, ams3.
Whisper garbles: "eye/II/each/air" = High (H); "ILO/high low" = HL/higher low; "BMS" = break of market structure; "weak/week" = wick; "kuditi grab" = liquidity grab; "slip" = sweep; "IDM"= inducement; "condo"=candle.

## 0. Context
- Strategy = SLK "Structural Liquidity and Key levels" [T intro@175]. Works on forex/crypto/stocks [T intro@203]. Analysis on TradingView. No numeric params anywhere in intro (class logistics only). Trader himself says "my trading is anticipation and execution" [T ams2@737].
- Three structure states: bullish (uptrend), bearish (downtrend), range/consolidation [T bms2@293-344].
- Two layers: "basic" structure (H/L/HH/HL/LH/LL, BOS, BMS) and "advanced" (sweep + BOS + inducement) [T bms2@183-258; T ams@190-250].

## 1. Swing points (basic) - mechanical definition
- Swing point = turning point marked at the extreme of a leg: "lowest point price got to before reversal" and "highest point before reversal" [T bms@159-167, bms@326-332; T bms2@2023].
- A candidate high/low is NOT a swing point if price merely wobbled inside the leg: example where a small pullback near the top is rejected; only the extreme before a real reversal counts [T bms@285-332]. Reversal is "real" only when it subsequently takes out the previous opposite swing (see "confirmation" below).
- Labels: L/H = first swing. In uptrend: HH = high above previous high; HL = low above previous low. Downtrend: LL, LH. [T bms2@870-1640; T bms3@278-455]. Frame bms2/sheet_012 (880-940s) and sheet_027 show zig-zag labelled H, HH, L, HL, "UP TREND" line [F confirm].
- Which point is the swing low in an uptrend (confirmation rule): the HL/HH is assigned to the lowest point of the pullback that actually pushed price to break the last high. If price makes another dip before the break, the earlier candidate is discarded and the later dip becomes the HL [T bms@456-620]. A candidate high/low is "not confirmed" until price breaks beyond the prior opposite swing [T bms@537-552]. => Coder: swing low confirmed only after a later close/break above the previous swing high; pick the min low between the previous swing high and the breaking leg's origin (the lowest point of the leg that made the break).
- Hierarchy: uptrend = highs broken, lows protected (no low is broken); downtrend = highs protected, lows broken [T bms2@1590-1617, bms3@187-236]. Frames bms/sheet_007 (480-540s): EURUSD 1h with H/HL/HH marked on candles [F].
- No candle count, no fractal (n-left/n-right), no % retracement, no min size stated. Kevin says "when we get to advanced structure you will know why [that high] cannot be considered" [T bms@379-393] - never fully answered later.
- Tip: he marks on line chart (close-only) to find structure easily [T bms2@1805, ams2@1074, ams3@631-669]. Suggests swings on closes for HTF/basic work.

## 2. BOS, BMS, CHOCH (basic)
- BOS = break of structure IN THE DIRECTION of the trend (new HH in uptrend, new LL in downtrend) [T bms3@723-760]. Each BOS is a "structural point" break [T bms3@806-816].
- Reversal break: close beyond the last protected swing against the trend (downtrend: close above last LH; uptrend: close below last HL). Called CHOCH ("change of character") by "some people"; Kevin's own term is BMS = break in market structure [T bms3@875-1090]. "when we close above this last high... that is change of character" [T bms3@893-899].
- Frame bms3/sheet_012 (880s) + sheet_015 (1120-1180s): downtrend H,L,LH,LL with "BOS" tag on every LL break; "COCH" tag on the break above the LAST LH (the lower one), and "BMS" tag on the break of the EARLIER, higher LH [F]. So frame labels: COCH = first break (above the most recent LH), BMS = second break (above prior higher LH). Matches transcript: "some want the second break as extra confirmation... I use the first one" [T bms3@1189-1211]. Kevin uses first break as the flip; second = extra confirmation, "not wrong".
- Analogy: generator switch-on = first break, change-over = second/confirmation [T bms3@1100-1160].
- After BMS: price retraces, then makes HH/HL; if next break also happens trend has flipped; BMS "tells us there is about to be a change in direction; sometimes deep retracement, sometimes none" [T bms3@1317-1337]. After BMS the series restarts (new trend direction) [T bms3@1347-1368].
- Body vs wick: basic notes say "move and close above" [T bms3@1077-1081]. Explicit rule from advanced: BOS requires BODY CLOSE beyond the level, not a wick [T ams@2011-2027; T ams2@1191-1237 "I don't put the BOS on the wick... body of the candle, even if small"].

## 3. Range / consolidation
- No new HH/LL/BOS/BMS; price oscillates between a high and low [T bms3@1448-1545; T ams2@208-263]. Advice: stay away; scalp possible but "not advisable" [T bms3@1529; T ams2@295-319].
- Direction hint: look at left side of chart; prior bullish -> likely breaks up, prior bearish -> likely breaks down, "not a must" [T ams2@405-452]. Break must be full body (not wick), then wait for retest of the breakout level and trade continuation [T ams2@519-545, 659-677].
- Use higher TF to check trend before range [T ams2@500-505].

## 4. Advanced market structure (AMS) = sweep + BOS + inducement (IDM)
- Sequence: sweep of liquidity -> BOS (one or double) -> inducement; "price comes back to take out the inducement then continues" [T ams@220-260, 740-760; T ams2@22; T ams3@109-140].
- Frame ams/sheet_013 (960-1020s) and sheet_026: Kevin's drawing "AMS consist of SWEEP, BOS, IDM"; bullish zig-zag with a SWEEP of a low at the start, BOS, IDM (small pullback low), second BOS, HL labels. HTF triple-candle drawing labelled SWEEP [F]. Drawing shows H, L, HL, HH labels inside, as ams said.
- Single-candle definitions (wick vs body) [T ams@304-380, 790-915; T ams3@1938-2139]:
  - SWEEP of high: candle's wick goes above prior candle's high (wick-to-wick) but does NOT close/body above it (price returns). Sweep of low is mirror. "wick to wick" [T ams@397-411]; "it goes above and comes back to close below" [T ams3@259-311]. Also called liquidity grab / "slip".
  - BOS: candle BODY closes above (below) the prior high (low) -> "this is BOS not sweep" [T ams@372-379, 553-559].
  - Conflict: ams says sweep= wick beyond, no body beyond; ams3@2118-2124 "even if it traded back into the range... it's a sweep". Consistent: wick beyond + close back inside.
- Liquidity rests above each swing high/below each swing low [T ams3@315-319].
- BOS validity in AMS: need a SWEEP first, then a candle BODY close beyond the previous swing high (the last marked high) [T ams@1818-2060: "sweep is important, there must be a sweep and then a body close, not a wick, above the previous swing points"].
- Inducement: the minor pullback high/low (a fake move / "fake sale" in a bullish setup) between BOS legs; lures early counter-trend traders; price tends to return to sweep it before the real move, "not every time but most of the time" [T ams@1331-1425, 1596-1620; T ams3@411-600, 1211-1241, 1459]. The first BOS is often the one created by inducement low... "first BOS is usually the inducement" [T ams2@1548-1551 garbled]. Inducement can come before the BOS or after it [T ams2@956-962]. Inducement sits at/near a key level (key levels not yet taught) [T ams2@1301-1310, 1565-1575; T ams3@1257].
- Frame ams3/sheet_006 (400-460s): USDCAD 4h drawing: "hh" with wick above (sweep/liq grab), then "bos" on the break down, then rally. Text "sweep / liq grab" [F]. Bearish version of sweep->BOS.
- Frame ams2/sheet_012 (880-940s) XAUUSD 2h: schematic zig-zags with horizontal lines at previous swing and a green long-trade box; shows the inducement-after-BOS vs inducement-before-BOS variants [F, partial - no labels visible].
- AMS tells "get ready, price about to move" [T ams3@1022-1037]. Multi-TF: an HTF sweep/break candle pair (e.g. daily) is a full AMS on 4h/1h inside it [T ams@606-660, 1125-1150].
- A sweep can also be body-to-wick type ("wick to body") - Kevin says there's another variation and defers ("will explain when to use body sweep") [T ams2@2068-2238]. UNRESOLVED.

## 5. Bias logic (what Kevin says; sparse)
- Bias = structure direction: HH/HL = bullish, LL/LH = bearish, neither = range [T bms2@870-1640; T ams3@1010-1022 "identify the direction of bias... which is HH/HL or LH/LL; keep doing that until you see an AMS, it tells you to get ready"].
- "We are going to use [AMS] to determine our direction" [T ams3@734].
- TF: basic structure is clearer on higher TF; AMS (sweep/BOS/IDM) shows more on lower TF [T bms2@661-680]. Examples shown on 1h, 2h, 4h, daily. Top-down: spot HTF structure (daily/4h), then drop to 1h/4h to find AMS inside the leg [T ams@606-660, 1136-1150; T ams2@500]. Exact TF ladder (e.g. D->4h->1h->15m) NOT specified.
- Bias flips: close beyond the last protected swing against the trend (CHOCH/BMS) [T bms3@875-1090]; he treats first break as the flip, second break as optional confirmation.
- No-trade: range/consolidation -> stay away [T bms3@1529; ams2@295]. He does not state a rule "no bias" for mixed HTF/LTF.
- Sessions, candle counts, % retracement, risk: none in these seven videos. Intro only schedule. He mentions weekly analysis done on Sunday [T intro@620-632].

## 6. Contradictions / things the coder must decide
1. Naming: BMS vs CHOCH; frame has COCH on 1st break and BMS on 2nd (higher LH). Decide: flip = close beyond most recent protected swing (CHOCH); optional "confirmed" state when the earlier swing also breaks.
2. Swing-point validity: no fractal rule; use "extreme of the leg that preceded a confirmed break". Implement as zigzag: swing is confirmed only when price closes beyond the previous opposite swing; choose the extreme between. Kevin's "internal vs external" structure was NEVER defined in these videos; "basic vs advanced" is his only split (and TF-based). Do not invent.
3. Close definition: body close on the analysis TF vs wick. Rule: BOS/CHOCH = candle close beyond level. Sweep = wick beyond, close back inside.
4. Is a CHOCH required to be preceded by a sweep? Basic videos: no. AMS videos: a BOS validated after a sweep. Treat AMS as higher-quality signal, not required for bias.
5. Inducement detection is vague (location relative to key levels, which come in later videos). Defer to alerts phase.
6. "Higher low" in an uptrend begins labelling confusion (he mis-labels H/L himself, T bms2@2088-2108); ground truth: first swing L, then H, then HL/HH...
7. No timeframe hierarchy, no session filter, no quantitative filters. Mark as parameters (config) in bot.
8. Wick-to-body sweep variant unresolved [ams2@2068].

## 7. Suggested implementable core
- Zigzag swings on closes (or high/low); confirm swing only upon close beyond prior opposite swing.
- State machine: UP (HH+HL), DOWN (LH+LL), RANGE (no new extreme in either direction / last break inside).
- Event per candle: BOS if close beyond last swing in trend direction; CHOCH if close beyond last protected swing against trend (flip bias); SWEEP if wick beyond swing high/low and close back inside.
- Bias output: bullish/bearish from state; no-trade if RANGE (optionally when HTF/LTF conflict - not specified by Kevin).
