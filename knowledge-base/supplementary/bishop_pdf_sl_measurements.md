# Bishop chart-examples PDF -- page-by-page SL measurements

Raw measurements taken 2026-09-02 by reading all 60 pages of the
chart-examples PDF as images (the PDF itself is NOT in this repo -- it
was supplied directly in chat; see the process note at the end).

Purpose: derive the actual stop-placement rule from evidence rather than
from transcripts, after two attempts at inferring it from spoken words
("here", "this low", "that high") both produced wrong rules. Every entry
below records what was visible on the page: zone boundaries, the RED
axis label (= stop), the TEAL axis label (= target), and the grey label
(= entry).

# Columns: page | instrument | TF | dir | zone(pink) lo-hi | entry | stop | target | notes

## p1-2 EURCAD
D: "Daily bullish breakout / Daily reject Daily". H4: "H4 breakout with idm H4rH4".
p2 H2: teal ~1.61300-1.61716, pink ~1.61135-1.61300. "H2 Engulfing Confirmation Entry" -> pink.
Broker screenshot: entry marker ~1.61274, red marker top ~1.61643. Entry at pink TOP / teal BOTTOM.
STOP: not explicitly labelled. INFERRED far edge = pink low ~1.61135.

## p3-4 EURJPY
D bullish breakout. H4 bullish breakout w/ idm H4RH4.
p3 H2: teal ~186.35-186.80, pink ~186.25-186.35. "H2 Engulfing Confirmation Entry" -> teal/pink boundary ~186.35.
STOP: not explicitly labelled. Zone height ~10 pips.

## p5-6 EURCHF  *** HARD EVIDENCE ***
p5 M30 chart: teal 0.93193-0.93498, pink 0.93147-0.93193.
p6 BROKER SCREENSHOT: BUY LIMIT 0.93193 | SL 0.93147 | TP 0.93704
=> ENTRY = pink TOP (near edge). STOP = pink BOTTOM (far edge). Risk 4.6 pips. R:R 11.1
CONFIRMS: stop = far edge of pink zone. Entry = near edge. LIMIT order.

## p7 EURGBP
D: "Daily bullish BOS". H4: "H4 breakout", "H4 breakout with idm H4rH4". No zones/SL on this page.

## p12 EURNZD (D + H4)
"Daily bearish breakout", "H4 breakout with idm H4rH4". No zones on this page.

## p13 EURNZD H3  *** STRONG (TradingView position tool) ***
SHORT. pink ABOVE 1.96156-1.96472 (1.96472 = RED axis label). teal BELOW down to 1.94902 (TEAL label).
"H3 Engulfing Confirmation Entry" -> 1.96156 (grey label = entry).
=> ENTRY = pink BOTTOM (near edge for a short). STOP = pink TOP (far edge) 1.96472. Risk 31.6 pips. R:R ~4
CONFIRMS rule; 7x the EURCHF pip count. PIP COUNT IS NOT THE RULE.

## p14 USDCAD (D + H4)
"Daily bearish breakout", "H4 breakout with idm H4rH4". No zones on this page.

## p8 EURGBP H2 LONG  *** RED/TEAL AXIS LABELS ***
"H2 High swept, Low standing V-shaped kl 4thman's CE"  (4th-man trigger, NOT engulfing)
pink 0.85289-0.85319 (0.85289 = RED label). teal 0.85319-0.85447 (0.85447 = TEAL label).
ENTRY 0.85319 (pink top) | STOP 0.85289 (pink bottom) | TGT 0.85447
Risk 3.0 pips. R:R ~4.3. => same rule on a 4th-man CE.

## p9 USOIL D+H4 -- context only, no zones

## p10 USOIL H2 LONG -- *** TWO STACKED ENTRIES, EACH ITS OWN ZONE ***
"1st Confirmation Entry H2 Engulfing" and "2nd Confirmation Entry H2 Breakout"
Axis labels: 8462.1(TEAL) 8172.1(grey) 8110.7(grey) 8103.5(RED) 8040.6 8027.9(RED)
1st: entry ~8110.7 (zone top), stop 8027.9 (zone bottom). risk 82.8
2nd: entry ~8172.1, stop 8103.5. risk 68.6
=> two red labels = two stops, one per entry. Same near-edge/far-edge rule each.
=> BREAKOUT is also a confirmation-entry trigger (2nd entry), same stop rule.

## p11 XAUUSD 60m (mindguy0x, "Fudoshin - Unshakable / SLK") SHORT
Uses GREY instead of pink for the risk-side zone; teal same.
Labels: 4134.50(grey) 4128.22(grey) 4092.16(TEAL)
ENTRY ~4128.22 | STOP ~4134.50 (grey zone far edge) | TGT 4092.16
Risk ~6.28 price = 62.8 gold pips. R:R ~5.7

## RUNNING RANGE OF OBSERVED STOPS (in each instrument's own pips)
EURGBP 3.0 | EURCHF 4.6 | EURNZD 31.6 | XAUUSD ~62.8 | USOIL 68.6, 82.8
=> 27x spread. Pip count is definitively NOT the rule. Zone height IS.

## p15 USDCAD H1 SHORT -- "H1 Breakout Confirmation Entry"
pink ABOVE 1.40471-1.40539 (1.40539 RED). teal BELOW to 1.40129 (TEAL).
ENTRY 1.40471 | STOP 1.40539 | TGT 1.40129. Risk 6.8 pips. R:R ~5.0
=> breakout CE again, same rule.

## p16 AUDUSD D+H4 -- context only

## p17 AUDUSD M30 LONG -- "M30 Engulfing Confirmation Entry"
teal 0.69853-0.70156 (0.70156 TEAL). pink 0.69793-0.69853 (0.69793 RED).
ENTRY 0.69853 | STOP 0.69793 | TGT 0.70156. Risk 6.0 pips. R:R ~5.0

## p18 GBPJPY D+H4 -- context only

## p19 GBPJPY H1 LONG -- TWO stacked entries, two zones, two RED labels
"H1 breakout Confirmation Entry 1" -> 216.877, stop 216.700(RED). risk 17.7 pips
"H1 Breakout with idm Confirmation Entry 2" -> 217.255, stop 217.088(RED). risk 16.7 pips
TGT 218.014 (TEAL) for both.

## p20L XAGUSD H4 SHORT
pink ABOVE 59.9649-60.4838(RED). teal to 57.2402(TEAL). ENTRY 59.9649. risk 0.5189. R:R 5.25
## p20R USOIL H4 LONG
teal 7266.8-8111.4(TEAL). pink 7134.2(RED)-7266.8. ENTRY 7266.8. risk 132.6. R:R 6.4

## p21 XAGUSD D+H4 -- context only ("Daily bearish breakout PDH swept")

## p22 XAGUSD H2 SHORT -- "H2 Engulfing Confirmation Entry" + broker screenshot
pink 59.7269-60.0626(RED). teal to 58.3773(TEAL). ENTRY 59.7269.
Broker: SELL 0.06 @ 59.655, TP 58.534. risk 0.3357. R:R ~4.0

## p23 USDCHF H1 SHORT (two variants of same setup)
L: pink 0.80736-0.80783(RED), teal to 0.80525(TEAL). ENTRY 0.80736. risk 4.7 pips. R:R 4.5
R: pink 0.80736-0.80787(RED), teal to 0.80532(TEAL). risk 5.1 pips

## INTERIM CONCLUSION (13 measured trades)
RULE HOLDS 13/13, zero exceptions so far:
  ENTRY = NEAR edge of the risk-side zone (pink/grey)
  STOP  = FAR edge of that same zone  (always the RED axis label)
  TGT   = far edge of teal zone       (always the TEAL axis label)
Stop range 3.0 pips (EURGBP) .. 518.9 (XAGUSD) -- ~170x. NOT a pip rule.
R:R range ~4:1 .. 11:1 -- ALL well above the engine's flat rr=3.0.
Triggers seen with identical stop rule: engulfing, 4th-man (V-shape kl),
breakout, breakout-with-idm. => stop rule is trigger-INDEPENDENT.

## p24 AUDUSD D+H4 -- context. Has the weekly-beats-daily written reasoning.
## p25 AUDUSD H2 SHORT -- "H2 Engulfing CE"
pink 0.69391-0.69460(RED). teal to 0.69108(TEAL). ENTRY 0.69391. risk 6.9 pips. R:R 4.1
## p26 GBPUSD D+H4 -- context
## p27 GBPUSD H1 SHORT -- "H1 Breakout CE"
pink 1.31923-1.31999(RED). teal to 1.31594(TEAL). ENTRY 1.31923. risk 7.6 pips. R:R 4.3
## p28 CHFJPY D+H4 -- context
## p29 CHFJPY H1 SHORT -- "H1 Engulfing CE"   *** SAME PAIR/TF AS OUR LIVE FAILURE ***
pink 199.637-199.787(RED). teal to 199.010(TEAL). ENTRY 199.637.
risk 15.0 pips. R:R 4.2
COMPARE our live CHFJPY H1: stops of 25.8 and 76.5 pips on the same pair+TF.

## p30 GBPNZD D+H4 context
## p31 GBPNZD H1 LONG -- "H1 Engulfing CE" + CLOSED ORDER RECORD
pink 2.29842(RED)-2.29993. teal top 2.30503(TEAL). ENTRY 2.29993. risk 15.1 pips. R:R 3.4
Order record: buy 0.33, 2.30008 -> 2.30172, profit +31.52, comm -2.31 (real closed trade)
## p32 GBPCAD D + broker screenshot
## p33 GBPCAD H2 LONG -- "H2 Breakout CE"
pink 1.86043(RED)-1.86184. teal top 1.87036(TEAL). ENTRY 1.86184. risk 14.1 pips. R:R 6.0
## p34 GBPJPY D+H4 context
## p35 GBPJPY H1 -- "H1 Breakout CE", labels only, no zones drawn

## p36 EURGBP D+H4 context
## p37 EURGBP H1 SHORT -- "H1 Engulfing CE"
pink 0.86580-0.86611(RED). teal to 0.86451(TEAL). ENTRY 0.86580. risk 3.1 pips. R:R 4.2
## p38 US30 H4+M30 LONG -- "M30 Engulfing CE"
pink 50750.8(RED)-50818.7. teal top 51022.9(TEAL). ENTRY 50818.7. risk 67.9 pts. R:R 3.0
## p39 AUDCAD D+H4 context
## p40 AUDCAD H2 LONG -- "H2 Breakout CE"
pink 0.98622(RED)-0.98719. teal top 0.99123(TEAL). ENTRY 0.98719. risk 9.7 pips. R:R 4.2
## p41 USOIL D+H4 context ("H4 rejects H4 at extreme")

## p42 USOIL H3 SHORT -- "H3 Engulfing CE"
pink 9007.0-9087.0(RED). teal to 8651.5(TEAL). ENTRY 9007.0. risk 80.0. R:R 4.4
## p43 ETHUSDT D+H4 context
## p44 ETHUSDT H1 SHORT -- "H1 Breakout CE"
pink 2078.59-2084.05(RED). teal to 2052.41(TEAL). ENTRY 2078.59. risk 5.46. R:R 4.8
## p45 EURJPY D+H4 context ("Old daily low swept")
## p46 EURJPY M45 LONG -- "M45 breakout CE"
pink 185.146(RED)-185.214. teal top 185.624(TEAL). ENTRY 185.214. risk 6.8 pips. R:R 6.0
## p47 GBPCAD H2 LONG -- "H2 Engulfing CE"
pink 1.84653(RED)-1.84766. teal top 1.85244(TEAL). ENTRY 1.84766. risk 11.3 pips. R:R 4.2
## p48 GBPCAD H4 context

## p49-50 NAS100 H1 LONG: pink 28981.2(RED)-29032.3, teal 29322.3(TEAL). risk 51.1. R:R 5.7
## p51-52 NAS100 H1 SHORT: pink 28978.8-29068.5(RED), teal 28714.4(TEAL). risk 89.7. R:R 2.9
## p53-54 EURGBP H2 LONG "H2 Breakout CE": pink 0.86544(RED)-0.86606, teal 0.86975(TEAL). risk 6.2 pips. R:R 5.9
## p55-56 US30 H1 LONG "H1 breakout CE": pink 49775.1(RED)-49824.3, teal 50123.3(TEAL). risk 49.2. R:R 6.1
## p57-58 JP225 H1 LONG "H1 Breakout CE": pink 62613(RED)-62991, teal 63793(TEAL). risk 378. R:R 2.1
## p59-60 GBPAUD M45 SHORT "2nd Entry ... M45 break with idm":
   pink 1.87881-1.88000(RED). teal to 1.87393(TEAL). ENTRY 1.87881. risk 11.9 pips. R:R 4.1

# =========================== FINAL ===========================
# ALL 60 PAGES STUDIED. ~35 measured trades. ZERO EXCEPTIONS.
#
# THE RULE (invariant across every instrument, timeframe and trigger):
#   ENTRY  = NEAR edge of the risk-side zone (pink; grey for mindguy0x)
#            -> placed as a resting LIMIT order (p6 broker: "BUY LIMIT")
#   STOP   = FAR edge of that SAME zone            (always RED axis label)
#   TARGET = far edge of the teal zone             (always TEAL axis label)
#   => STOP DISTANCE == THE ZONE'S OWN HEIGHT. Nothing else.
#
# The zone is the imbalance/FVG price returns to rebalance.
# Invalidation logic: if price clears the WHOLE gap, the "came back to
# rebalance it and continue" reason for the trade is gone.
#
# OBSERVED STOP RANGE (each instrument's own pips):
#   3.0 (EURGBP) 3.1 4.6 5.5 6.0 6.2 6.8 6.9 7.6 9.7 11.3 11.9 14.1 15.0
#   15.1 16.7 17.7 31.6 49.2 51.1 67.9 68.6 80.0 82.8 89.7 132.6 378 518.9
#   => ~170x spread. A pip threshold cannot express this. MAX_NATURAL_STOP_PIPS=30
#      would REJECT ~8 of these valid trades.
#
# OBSERVED R:R: 2.1 .. 11.1, typically 4-6. NOT the engine's flat 3.0.
#
# TRIGGERS all sharing the identical stop rule (=> trigger-INDEPENDENT):
#   engulfing, breakout, breakout-with-idm, 4th-man V-shape, M45/M30/H1/H2/H3/H4
#
# CODE IMPLICATION: entries.py's imbalance_stop_loss() ALREADY implements
# this exactly. Defect is SCOPE -- runner.py only fires it when
# imbalance_overlap is true ("plug_and_play"); all other trades fall
# through to candle-wick anchors that have no structural meaning.


## PROCESS NOTE -- why this file exists
The repo contains no images. Both earlier attempts at a stop rule were
inferred from transcript deictics and both were wrong (a reaction-leg
extreme rule was A/B'd and failed: median stop 9.4 -> 24.3 pips). This
file preserves the measurements so the rule is reproducible without
re-reading the PDF. **Commit the PDF itself (or attach it to a release)
so the underlying evidence is reproducible too.**
