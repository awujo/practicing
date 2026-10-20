# Bishop sessions: complete transcript study and ongoing visual audit

Study date: 2026-10-20. This document records source study before further engine
work. No code, source expectations, or replay tolerances are changed here.

All nine unique canonical medium-model session transcripts have been read from
beginning to end in this pass. This does not mean every ASR sentence is correct:
references such as “this level” must be resolved visually, and unsupported
numerical precision is not inferred. The complete available visual audit is
still underway; the exact sheets inspected are listed below. A 15-second frame
sample is not the entire native video and cannot prove an intrabar fill clock.

## Canonical inventory and coverage

The source root for each slug is `knowledge-base/videos/<slug>/transcript.txt`;
frames are `knowledge-base/frames/<slug>/sheets/sheet_NNN.jpg`.
Source times below are seconds from video start. `T` denotes transcript evidence;
`F` denotes actual picture inspection in this pass. The frame manifest records
source hashes and corrected source-PTS sampling. Short legacy transcript aliases
and supplementary prose are secondary locators, not extra independent sources.

| Short name | Canonical slug | Transcript read | Visual sheets inspected in this pass |
|---|---|---|---|
| BE | bishop-defi-bishop-study-10-minute-series-part-1-bias-entries-amp-confirmation-entries-combined | All 6.1–694.1 | 001–012, all 12 |
| WN | bishop-defi-bishop-study-10-minute-series-part-2-if-you-have-ever-thought-what-next-after-gettin | All 2.4–966.9 | 001–017, all 17 |
| RS | bishop-defi-bishop-study-20-minute-series-part-1-repeating-a-system-that-works-an-approach-to-tra | All 4.4–1538.1 | 001–026, all 26 |
| T2 | bishop-defi-bishop-study-20-minute-series-part-2-trades-breakdown-case-study-usdchf-gbpjpy-n | All 3.0–1368.6 | 001–023, all 23 |
| T3 | bishop-defi-bishop-study-20-minute-series-part-3-trades-breakdown-bias-to-entry-case-study-gb | All 3.0–1735.3 | 009, 012, 019, 023, 029 of 29 |
| E5 | bishop-defi-bishop-study-20-minute-series-part-5-approach-to-direct-and-confirmation-entries-case | All 3.4–1662.2 | 003, 006, 011, 018 of 28 |
| B1 | bishop-defi-bishop-study-building-bias-part-1-a-2-part-series-case-study-audjpy-eurusd-sp | All 3.4–1980.5 | 004, 008, 014, 016, 023, 030, 033 of 34 |
| B2 | bishop-defi-bishop-study-building-bias-part-2-a-2-part-series-case-study-eurcad-spx500-nz | All 3.0–2189.6 | 004, 008, 015, 018, 023, 029, 035 of 37 |
| DR | bishop-defi-bishop-study-daily-routine-x-trade-breakdown-how-do-i-manage-trading-multiple-pairs-wha | All 0–2242.8 | 007, 017, 025, 028, 032, 037 of 38 |

The release includes a second T3 directory ending `-1`. Its declared source
video SHA256 is identical to canonical T3. Its independently produced ASR text
is not identical. It is not a tenth independent teaching session and examples
must not be double counted. Canonical T3 is the version without `-1`.

Visual audit so far: 107/244 unique sheets, covering all source samples in the
first four sessions and selected samples in the other five. Remaining 137 sheets
must be inspected before calling the session visual study complete. Several
intro/outro tiles are black or portraits rather than teaching charts.

## Rules reconstructed from the sessions

### Context and directional confirmation

1. **A key level is a decision point, not a guaranteed trade.** B1 T47.4–177.6
   distinguishes buy V, sell A, bullish OC and bearish OC. OC is narrated as a
   candle closing then the next opening at the same level. B1 F180–225 shows
   original V/A levels and close-through role changes. A candle body close
   through a level changes the side on which it can subsequently be used
   (B1 T183.6–297.6). The speech contains corrections/mixed labels; direction
   should be taken from the drawings and explicit close-through side, not a
   garbled isolated “V”/“A” token. Repeated disrespect can flip it again:
   AUDJPY B1 T916.5–935.5 describes buy→sell→buy.
2. **KL origin sequence:** rejection at higher-TF level, that candle closed,
   then breakout OR sweep-and-break/BOS on next lower TF. B1 T373.6–450.3;
   bearish mirror T526.9–620.0. B1 F420–465 displays the checklist and W/D/H4
   columns. Rejection alone is not fully confirmed directional bias.
3. **Liquidity origin is a separate alternative:** sweep a higher-TF high/low,
   candle closure, then next-lower-TF breakout OR sweep+BOS. B2 T29.3–147.7,
   T408.5–478.4, T536.4–615.8. B2 F180–225 and420–465 show high/low, IRL→ERL,
   and the same W/D/H4 ladder. KL rejection and sweep may coexist but neither
   is universally mandatory in addition to the other (B2 T1423.5–1432.7).
4. **Sweep versus close-through:** B2 T192.0–209.1 calls high taken then close
   below a sweep. Wick beyond and body beyond must not be collapsed. Candle
   colour by itself is not the decision; B2 T2000.3–2006.2 says he looks at
   liquidity sweeps/rejections rather than whether the candle is green/red.
   “Can close anywhere” in T203.6–215.7 is imprecise alongside the explicit
   back-inside example; do not infer that a close beyond the swept high is
   equivalent to a rejection without checking the picture/context.
5. **Origin/level timeframe fallback:** if weekly rejects but Daily never
   provides the expected confirmation, one/two Daily candles rejecting that
   SAME Weekly level can instead originate a Daily story; H4 must confirm it.
   B1 T774.6–847.6, EURUSD T1281.9–1359.9. B1 F780–825 literally redraws Daily
   candles at the Weekly level and the H4 confirmation. This does not mean
   the missing Weekly→Daily confirmation happened.
6. **Breakout for direction does not require later retest to stay confirmed.**
   B1 T1133.3–1160.3; WN T714.1–725.5. The breakout validates direction; a
   retest is a separate order requirement for the chosen entry approach.
7. **Do not replace directional BO/BOS with an engulfing automatically.** T3
   T261.3–277.1 explicitly rejects using Daily engulfing as the missing
   Weekly-sale confirmation. Engulfing is an execution confirmation pattern
   elsewhere; its role is not interchangeable across every step of the ladder.

### Hierarchy, reversals and storyline continuity

8. Weekly/Daily alignment is a preferred context, not a universal veto. WN
   T455.2–480.0 deliberately considers a Daily bullish GBPCAD reversal while
   Weekly is bearish and says he does not advise reversal trades. DR
   T394.1–421.5 explicitly permits leaving Weekly and using D+H4 with a
   suitable nearby liquidity target. T3 T261.3–307.9 instead explains GBPCAD
   Daily buys aligned with Monthly while Weekly sales never got Daily
   confirmation. These are different contexts and must remain labelled.
9. He also deliberately ignores contrary lower-TF breaks while the selected
   higher story holds: WN T239.2–256.2; RS T1348.5–1367.2; DR T728.3–758.2
   and839.4–865.4. DR later chooses to await Daily alignment on UK100
   (T904.8–937.8), so permission to trade D/H4 counterweekly is not a command
   to take every disagreement. The material contains discretionary selection.
10. Follow H4 breakouts/sweep+BOS in the selected direction until the draw is
    reached (B1 T470.9–502.9, WN T948.5–960.8). A new H4 continuation can offer
    another entry after a missed retest. BE T170.6–239.9; T2 T337.1–424.2.
11. A lower-TF counter-break is not automatically a full bias flip. T3 USDCAD
    T1624.0–1646.8 explicitly demonstrates a bearish H4 break inside a larger
    bullish idea. RS AUDUSD T1151.6–1187.6 shows counter-break/structural
    liquidity before the continuation. Conversely bias genuinely can flip:
    RS T1050.2–1105.0 moves AUDUSD from sales to bullish breakout and warns
    against marrying bias. No universal numerical lifecycle rule is supplied.
12. A stopped trade does not alone invalidate direction (BE US30
    T404.8–428.6; RS CHFJPY T1296.0–1311.6). A new independent valid setup may
    appear, but losses are not to be deleted or retrospectively relabelled.
    T3 T888.0–902.8 also says to stay away when price fails to give the expected
    reaction; this is not a precisely defined permanent ban or fixed retry cap.

### Liquidity and key-level selection before entry

13. Bishop's chosen H4 checklist is breakout → liquidity → liquidity taken /
    reaction at a relevant H4 KL → lower-TF confirmation. BE T129.5–151.1,
    RS T113.7–140.7, DR T974.8–989.8. He personally waits for the reaction
    instead of setting a direct H4 limit. No reaction means no trade in this
    chosen approach (RS USOIL T903.3–974.1).
14. **Single-candle liquidity is a preference, not a one-bar-only law.** RS
    T263.9–355.9 explicitly permits later candles, series of candles and
    structural/advanced-structure liquidity, not always the immediate next
    candle. E5 T240.5–284.3 repeats this. RS F270–345 draws the multiple-candle
    and V-shaped structural alternatives. One H4 liquidity candle can be an
    advanced structure on the lower TF (B2 T1137.0–1214.7; T2 German40
    T821.7–858.5). Different TF representations are corroboration, not identity
    of all geometries.
15. Closest relevant KL is often used, but deeper/extreme alternatives exist.
    BE US30 T433.0–457.4; T2 GBPJPY T563.3–579.6; T3 USDJPY
    T971.1–986.4. Do not choose the touched level using future outcome. Relevant
    candidate levels must be listed as known alternatives, then record which
    actually received a reaction.
16. FVG/imbalance can motivate expecting deeper retracement rather than the
    immediate post-breakout candle level, but is not deterministic. RS
    USDCAD T825.8–858.5, AUDUSD T1110.4–1139.1. RS F1125 shows an FVG/IFVG
    indicator and three shaded green areas; F1140 returns to the marked KLs.
    These passages do not define an exact universal FVG construction or stop.
17. A small body close through the relevant KL may be a valid breakout:
    DR AUDCAD T1040.2–1056.0 explicitly says even small, it broke the V level
    with a body. This does not settle which historical swing/KL should govern
    every noisy line-chart candidate.

### Three entry approaches and four confirmation shapes

18. **H4→H2 direct:** after the H4 breakout candle CLOSED, scale to H2, see
    H2 breakout/sweep+BOS with single-candle or structural liquidity, take the
    relevant nearest H2 KL directly. E5 T85.8–135.5 and225.9–291.1. E5
    F120–135 labels “H4 BREAKOUT - SCALE TO H2 - LIQ+KL”. This route need not
    wait for a future H4 liquidity sweep/reaction first.
19. **H4 direct:** after breakout and liquidity forms, place direct limit at
    relevant H4 KL, anticipating the sweep into it and expansion. E5
    T156.9–221.2. Stop drawn below protected area. The expected sweep is not
    required to have already happened before placing this direct order.
20. **H4 reaction→lower confirmation:** do not set the limit at H4 level;
    price must reach it and react, then seek preferred lower-TF entry. Waiting
    for the H4 REACTION candle to close is personal choice (E5 T293.6–365.2,
    BE EURGBP T625.3–638.1), distinct from explicit H4 BREAKOUT-close in18.
    E5 lists H3,H2,H1,M45,M30,M15,M5. DR includes actual M30,H2,H3 and H1
    examples. A fixed H1-only engine cannot represent the complete route.
21. Confirmation shape alternatives: breakout, sweep+break/BOS, engulfed OC,
    low-swept/high-standing V entry (bearish mirror high-swept/low-standing).
    RS T140.7–230.1; E5 T378.2–453.1 and558.7–716.6. E5
    T412.2–430.9 says he personally favours BO and sweep+BOS; no guarantee
    against losses (E5 T808.2–842.8). The pattern choice is explicit, not
    a posteriori whichever worked.
22. **Engulfed OC is level disrespect, not necessarily a standard two-candle
    full-range engulfing.** E5 T470.0–540.9 starts from two consecutive
    bearish candles' OC sell level, then price invalidates it and retests for
    buy. Narration T511.5–520.2 explicitly says the candle position may vary;
    key point is the OC invalidated. Must read diagram with candle closes,
    not replace it with an unrelated textbook engulfing definition.
23. **Low-swept/high-standing:** E5 T589.3–634.9 says the source candle colour
    is not essential; price takes its low while its high remains standing,
    producing a V KL for retest buy. E5 F600–645 shows the two wicks, the
    unbroken high, V junction and retest arrow. Opposite-side wick intact is
    part of the described pattern; entry geometry still needs explicit
    matched candle mapping. WN T814.0–827.6 attributes the bearish mirror to
    fourth man. Do not call every such pattern an engulfing on the same TF.
24. Cross-TF engulfing appearance is **often, not always**. RS
    T217.4–230.1; E5 T679.0–716.6; DR T2151.8–2184.0 explicitly checks a
    CADCHF case and says it was not engulfing on lower TF. Therefore mandatory
    half-timeframe engulfing would reject a source-described valid pattern.
    The E5 ASR “12 hour” at702s conflicts with the downscaling context; do not
    convert that token into a rule without native audio corroboration.
25. Concurrent TF competition: T3 GBPCAD T476.6–520.0 prefers H2 over H1
    because higher TF stronger and H1 might never retest. T3 F480–525 shows
    W>D>H4>lower hierarchy and nested H1 candles. This speaks about signals
    he saw together, not hindsight replacement of an earlier executed H1.
26. Nested confirmation is demonstrated, not universally mandatory. T3 USDCAD
    T1651.6–1719.5: cancels original limit after scepticism, waits H1 breakout,
    reaction, H1 low sweep/high standing, then lower engulfing entry. The
    original valid unfilled/cancelled order and later actual entry are distinct.

### Targets, stops, exits and missed orders

27. Liquidity targets are drawn before narrated R. BE JP225 T319.4–337.6
    explicitly calls nearest ERL his personal target, not an obligation for
    every trader. RS USDCHF T593.6–648.3; T2 GBPJPY T611.8–632.0 warns not to
    hold beyond ERL just to exaggerate R. ERL can cause reversal; it is not a
    promise of reversal on every touch (BE EURGBP T674.9–687.8).
28. **Counter-structure target guard:** a high sweep in an overall bullish
    structure does not force a run all the way to the old low; the nearer
    liquidity / KL can give continuation up. B2 T815.5–928.5, EURCAD
    T960.5–1118.1, GER40 T1637.2–1808.7 and AUS200 T1855.0–1878.5.
    At the first liquidity, observe sweep/reject versus body close-through
    before extending. B2 EURCAD T1019.9–1059.0 uses body close above as new
    bullish evidence instead of forcing a sell. This means nearest origin-TF
    opposing KL is not automatically the demonstrated ERL definition.
29. Front-running targets is a personal practice in T3 GBPCAD
    T386.3–456.5: target just below liquidity, alternatively nearby H1 ERL,
    because price sometimes stops short. No fixed pip offset given.
30. **Stop protects relevant nearby structure/liquidity**, not always entry
    candle wick: WN GBPCHF T288.1–300.9 covers the next KL for safety; T3
    GBPUSD T1287.7–1348.1 keeps above H4 liquidity and KL which price has a
    right to sweep; narrower accounts were stopped by1–2pips. E5 EURUSD
    T1355.7–1366.5 says a direct entry should protect another KL when structure
    is weird. DR UK100 T2012.8–2039.5 protects the lower low. These are not
    evidence that every Bishop-session stop is fixed11pips or exactly an FVG
    far edge. Other course/default choices must be kept source-specific.
31. Different stops can be shown while dragging the position tool. A labelled
    risk box is an illustration/plan until a taken trade is independently
    established. E5 XAU F1035–1065 shows a tool being added/adjusted; its
    final 5.66R drawing is not a proven realised trade (teacher says missed).
32. Actual manual exit can differ from planned TP: T3 USDJPY
    T1072.0–1110.9 closed about2R because stalling, though3R was available.
    T3 F1080–1110 shows target being moved from larger target to about3R
    then2.29R. Do not treat final illustrated tool number as exact realised
    broker accounting or backfill an automated target with hindsight.
33. Missed retests are normal and retained. BE GBPAUD T170.6–182.6;
    WN BTC T636.2–654.7; DR AUDCAD T974.8–1004.2; DR CADCHF
    T2186.4–2198.3. An interesting setup, drawn tool, issued limit, fill,
    eventual TP, and narrator's personal participation are different facts.
34. Checklist prevents some bad trades and misses some good ones: DR
    USDCAD T1710.3–1736.9 and1812.7–1828.5 explicitly passes on a later clean
    H2 break because no H4 rejection/liquidity required by his approach.
    This is a valuable *no personal entry* example even though chart moved.
35. Multi-pair workflow: checklist, flag after Daily direction, monitor missing
    H4 break/liquidity/reaction, revisit flagged list, move strong candidates
    to top. DR T172.4–321.4,438.9–474.1,552.0–609.8,1284.4–1308.0,
    1598.7–1608.3. Human wake/scan times are workflow description, not stated
    mandatory market session filters. Aggregate exposure and forgetting
    setups are acknowledged risks (DR T27.1–140.1); no numeric risk cap given.

## Session-by-session example reconstruction

These are source decision sequences, not engine acceptance fixtures. Status is
what the narrator says, qualified where he corrects himself. No exact entry UTC
or broker fill is inferred from crosshair/position-tool anchors.

### BE — bias, entries and confirmation together

- **GBPAUD sell (T50.6–247.8; all F001–005):** Monthly/Weekly/Daily bearish →
  D rejects D KL → H4 bearish BO → single-candle liquidity → extreme H4
  reaction → first LTF order never retests (miss) → another H4 bearish BO,
  liquidity and H4 rejection → H1 breakout-ret entry; stop above local high,
  take to marked external low. He says this was his entry. F225 tool shows
  ~3.95R and F240 retains final short box. Two hypothetical direct H4 entries
  discussed at236–239s are not extra actual personal fills.
- **JP225 buy (T247.9–348.2; F005–006):** D bullish BO and D reject D → H4
  BO → H4 liquidity swept/rejection → H1 sweep+BOS → nearest external high.
  Taken trade narrated, ~5R. F315 tool initially broad stop (~1.41R), F345
  narrows it (~4.83R); the intermediate tool states are not separate trades.
- **US30 (T348.2–507.6; F007–009):** D bullish/reject → H4 reaction → first
  engulfing buy explicitly stopped; bias survives → fresh H4 BO+liquidity →
  closest KL reaction rather than deeper requested level → H1 BO buy to ERL.
  He calls the later setup his entry but opening phrase includes “missed”;
  retain narrated stop and later demonstrated setup with participation qualifier
  rather than silently turning the whole sequence into one winning fill.
- **EURGBP buy (T508.4–694.1; F009–012):** Monthly/Weekly unclear, D-only
  intraday bullish BO → prior D low swept/high intact + KL reject/close above →
  H4 bullish BO/liquidity → H4 reaction → H2 BO; he personally does not wait
  H4 reaction candle close. Target existing external high. F660 ~4.42R tool
  later adjusted; spoken “5R” is approximate. No forced W/D alignment.

### WN — participation after bias

- **GBPCHF sells (T115.5–446.0; F003–008):** W bearish BOS and D sell flow →
  previous D high swept + D KL rejection → H4 bearish BO/liquidity → H4
  reaction. Direct stop would cover QMR/KL; he only trades CE. H2 engulfed OC
  entry/H1 BO represent same opportunity; **he says he did not take it,
  forgot shared outlook** at324–332s. Later H4 continuation→LTF BO is a
  “would have been” entry. Illustrations must not become his realised trades.
- **GBPCAD bullish reversal (T448.8–543.7; F008–010):** Weekly bearish;
  deliberately uses bullish Daily BO/reject → H4 BO/liquidity/reaction → H2
  engulfed OC and later H2 breakout+liquidity/closest KL → external target.
  Willing reversal, warns against reversals; direct entry hypothetical.
- **BTC sell (T543.7–654.7; F010–011):** bearish story; prior D high swept,
  KL reject → H4 BO → extreme reaction with no clean H1 entry initially →
  continue following bearish H4 BOs → another reaction; engulf and BO limits
  never retest → later H1 breakout/liquidity closest KL only opportunity.
  Exact personal participation on final opportunity not separately proven.
- **EURGBP sell (T659.2–840.5; F012–015):** Weekly bearish/reject → D sell BO
  validates direction even without D retest → H4 sell BO/liquidity/extreme
  reaction → illustrated H1 engulf would lose (hypothetical) → H2 high sweep
  with low standing (“fourth man”) only valid shown entry; no clean H3.
  No claim he took this H2 trade. Distinguish opposite-side standing wick
  criterion from OC engulfing; F825 shows the A-junction for sale.
- **USOIL short countertrend (T843.2–948.5; F015–017):** Weekly bullish but
  D bearish BO/reject → H4 sell BO/liquidity/reaction → H1 engulfed OC →
  nearer liquidity target and protected stop. All stop/tool descriptions are
  conditional (“if I was placing”); ~5R illustration not certified personal fill.

### RS — repeating a chosen approach

- **US30 buy (T370.2–542.9; F007–010):** Weekly/Daily bullish without bearish
  Daily BO → D KL reject → H4 BO; bypass a direct-only early opportunity →
  next H4 BO+single liquidity; desired KL narrowly missed, actual engulfed
  OC H4 KL reacts → M45 BO possible later; **personal entry M30 engulfed OC**.
- **USDCHF sell (T544.5–659.2; F010–012):** previous bullish Weekly now rejects
  weekly + sweeps prior high → Daily bearish BOS aligns → D reject D → H4
  bearish BO/liquidity; deeper KLs not retested, closer OC sells → H1 engulf
  with stop above indicated KL/high, target nearest external. Tool outcome
  hypothetical wording around638–652s; exact personal fill not fixed by title.
- **AUDCAD buy (T660.5–757.2; F012–013):** Weekly bullish/prior low swept +
  Weekly reject → D BO then D low sweep/reject → H4 BO/single liquidity →
  extreme KL reaction → H1 BO entry. H2/H3 alternatives and direct H4 engulf
  shown; do not count each as independent taken trade.
- **USDCAD temporary sale (T757.2–876.6; F013–015):** initial bullish higher
  momentum, Weekly rejects → D sell BO → H4 sell BO and imbalance; deeper
  retracement anticipated → reaction only after deeper level; **no clean CE
  before target reached**. A no-personal-entry case, not failed bias.
- **USOIL sell (T882.7–1031.1; F015–018):** D bearish → H4 BO; wait rejection,
  not direct. Price goes past immediate liquidity level to older higher
  liquidity/KL → reaction → high swept/low standing shape; lower TF engulf
  would have been earlier entry he did not see; later engulf was the point
  he noticed/entered as narrated. Previous D low identified target.
- **AUDUSD buy (T1031.3–1213.8; F018–021):** earlier sell bias changes on D
  bullish BO → D KL reject/low sweep → H4 BO/FVG, rejects immediate setup
  as deeper KLs expected → structural V liquidity created/swept → reaction →
  no H1/M30 CE, M15 sweep+BOS only. **He was done for week, did not take**.
- **AUDJPY buy (T1213.8–1258.4; F021–022):** similar D bullish/low sweep,
  deeper KL/H4 structural liquidity → only M15-type entry, rare for him.
  Demonstrated opportunity, no explicit personal executed outcome.
- **CHFJPY buy (T1266.0–1331.2; F022):** symbol resolved from screen, not
  garbled transcript. D bullish/low sweep/high intact/reject → H4 BO/liquidity
  → first rejection could stop → later H1 breakout buy expansion. Hypothetical
  loss mentioned; do not silently omit first risk in favour of later success.
- **EURAUD sell (T1331.2–1466.7; F023–025):** bearish W structure/prior high
  sweep; weak opposite D BO ignored → D reject D → H4 sell BO/liquidity →
  choppy entry; first breakout could stop unless extreme protected → high
  sweep/low standing gives clean entry; M15 engulf corroboration, M30 not
  initially described as clean. Source frames show later retest and sale.
- **Teaching boundary (T1481.7–1515.0; F026):** SLK admits several approaches;
  he rarely uses ranges in his own routine and says study sufficiently and
  execute chosen approach. This cannot justify dropping course rules silently.

### T2 — trade breakdown 2

- **USDCHF initial sale (T30.7–209.9; F001–004):** weekly initially bullish
  but level/rejection warrants sale context; D sell BOS/reject → H4 bearish
  BO/liquidity/reaction → H1 engulf → nearest ERL. **He missed it**.
- **USDCHF subsequent buys (T209.9–430.6; F004–008):** D buy KL rejection,
  next day engulf/ H4 bullish BO, Weekly already bullish → H4 liquidity and
  closest KL reaction → H1 BO entry → next H4 continuation/rejection →
  another H1 BO. Multiple illustrated long boxes; wording mixes actual and
  conditional entries. Preserve both distinct setup times and market targets;
  claimed summed ~10R is not an audited portfolio accounting statement.
- **USDCHF future outlook (T432.6–459.8):** external already taken, possible
  retracement to H4 liquidity then buys; forward conditional scenario.
- **GBPJPY buy (T463.0–632.0; F008–011):** Weekly bullish, Daily Monday BO,
  prior D low swept/high intact → H4 bullish BO/liquidity → lower KL reacts
  instead of initially expected KL → H1 BO buy to near external high, stop
  shown ~12pips atF600; ~5.6R mentioned. Target guard external-first.
- **USOIL abandoned explanation (T681.2–735.3; F012–013):** Weekly/Daily
  sale expectation but he explicitly says example not ideal and moves on.
  Do not promote an incomplete discarded example into a complete rule.
- **US30 buy outlook (T746.3–773.2; F013, t750–765):** ASR calls USOIL but
  screen is **US30 FOREXCOM Daily**. Projected buy came to level then bought;
  he says no personal entry opportunity. This is a concrete transcript-symbol
  correction from visual evidence, not a price-derived substitution.
- **GER40 sale (T774.0–906.0; F014–016):** Weekly bullish but rejects, D sell
  BO → D single candle maps to H4 advanced/algorithmic structure, wait sweep →
  H4 reaction → clean H2 engulf would give4–5R. He personally wanted another
  breakout/CE, passed; illustrated clean trade is an alternative approach.
- **NAS100 sale (T943.9–1047.7; F016–018):** ASR transitions unclear, screen
  NAS100. ATH context, D high sweep/low standing → H4 bearish breaks, waits
  cleaner repeat BO/liquidity → lower TF desired retests absent; missed on
  preferred M45/M30 paths. Do not assign EURGBP symbol from preceding speech.
- **JP225 sale (T1048.9–1194.6; F018–021):** Weekly ATH/bullish; narrator
  admits **no clean Daily sell structure, experience-based** weak/disrespected
  buys then H4 break/liquidity/reaction → H1 high sweep/low standing plus
  M30 sweep+BOS earlier option; original sale personally missed. This example
  cannot be made a fully mechanical Daily BO route without inventing evidence.
- **EURGBP sale (T1196.5–1368.6; F021–023):** W/D bearish → D BO/reject close
  below → H4 sell BO/liquidity/reaction → H1 engulf limit kept despite delay;
  subsequent H2 bearish BOS/liquidity supports leaving limit → target marked
  KL/liquidity. He describes this as his sale. The reason to leave it is
  continuing context, not a stated universal24h TTL.

### T3 — six-trade week plus open continuation

- **GBPCAD buy (T28.9–577.1):** prior W high sweep/rejection suggests sale,
  but Daily never confirms sale. Monthly bullish/low sweep/expansion supports
  Daily bullish BO+KL reject/low sweep → H4 sweep+BOS and single liquidity →
  H4 KL reaction → simultaneous H2/H1 BO, picks H2 → near H1 external/front
  run target ~5–6R. Actual taken. Later continued buy bias but no swept
  liquidity entry, therefore no additional personal order. F009 confirms TF
  hierarchy argument, not universal W-veto.
- **AUDCHF buy loss (T577.9–677.3; F012):** W bullish despite prior W high
  sweep, Daily no bearish confirmation → D buy KL reject → H4 bullish BO/
  liquidity → H1 engulf buy; **actual loss acknowledged**. He does not use
  “external breakouts” as a separate filter and accepts resulting loss.
- **NZDCHF buy loss (T687.8–902.8; F012 at690–705):** screen resolves symbol
  NZDCHF; Weekly bullish/rejection still developing, says should have waited
  new Daily BO → uses D reject D and H4 BO/liquidity → first rejection no
  clean CE; later H4 KL rejection → H2 BO with liquidity (checked journal)
  → immediately stopped. Personal entry recollection corrected from uncertain
  engulf/H1 to **H2** at813.8–851.4. Keep correction and loss.
- **USDJPY buy, manual exit (T903.8–1110.9; F019):** W/D bullish, H4 bullish
  BO/liquidity + KL reaction → initial H1 CE missed/engulf deliberately passed
  in favour BO → H3 BO buy; stop covers engulf and survives spike by1–2pips.
  Weekly high planned target. Stalling disliked, actual closes about2R;
  hypothetical3R could have paid. No mechanised consolidation threshold given.
- **GBPUSD sell (T1112.6–1364.0; F023):** Monthly/W structure bullish,
  Weekly prior high swept + D sell BO → temporary sale with first nearby ERL
  target. D high sweep/reject→H4 sell BO/liquidity→H2 engulf sale. Stop beyond
  nearby H4 liquidity/KL rather than just engulf high. One/two accounts with
  slightly tighter stop were taken out; another survived and TP. Multiple
  accounts' outcomes cannot be conflated into one unqualified win.
- **USDCHF buy (T1364.9–1508.5):** W/D bullish, D KL reaction→H4 BO/liquidity
  → first entry missed → new H4 BO/liquidity/rejection → H2 engulf buy to
  external/previous high, ~3.5–4R narrated; rapid reversal at target. Taken.
- **USDCAD buy still open (T1515.0–1735.3; F029):** W/D bullish→H4 BO/
  liquidity/reaction; original BO then H2 engulf opportunity, stop below wick,
  projected5R. Contrary H4 BO does not inherently invalidate story. **He
  deletes original limit from scepticism**, adds H1 confirmation-on-confirmation
  → H1 reaction low swept/high intact/V; M30 engulf → actual new buy ~6R plan.
  Says **still on trade**. No final TP/SL outcome can be assigned from video.

### E5 — approach to direct and confirmation entries

- Theory T3.4–842.8 supplies the three approaches/four CE shapes detailed
  above. E5 F003,006,011 resolve direct limit vs post-reaction entry and distinct
  wick-sweep pattern. Several drawn risk boxes are diagrams, not trades.
- **XAUUSD buy (T859.9–1180.4; F018 at1020–1065):** structurally bearish
  Weekly but V KL repeatedly respected, Weekly rejection→D bullish BO
  confirms→D reject D→H4 BO/sweep+BOS. He wanted direct limit but does not use
  direct entries; hypothetical H4/H2 opportunities distinguished. H3 engulf
  at2am missed; H1 breakout never retested; M45 sweep+BOS not retested, M30
  sweep+BOS did retest. All illustrated alternatives; he did not take the
  attractive shown buy. Gold feed **Saxo**, not FX source assumptions.
- **GBPUSD buy (T1183.5–1270.2):** he first says had limit, then corrects
  **did not set limit, was watching**. D bullish; sweep high does not force
  old low target; H4 bullish BO→liquidity but expected KL reaction never
  arrives; H2 direct waited level also misses. Keep watch-only correction.
- **EURUSD buy (T1275.0–1430.3):** uncertain recollection of his original
  lower-TF entry, reconstructs D bullish→H4 bullish BO/liquidity/reaction→LTF
  BO+liquidity→target ERL; discusses direct stop protect extra KL and drawn
  ~3–5R. Do not assert exact taken model/TF while narrator cannot remember.
- **EURAUD sale (T1433.3–1546.2):** bearish; admits earlier loss before
  higher liquidity sweep → H4 sweep+BOS; immediate H2 direct BO+liquidity
  retest sells while H4-liquidity-waiters may miss. Two H2 opportunities,
  not evidence he personally took every alternative.
- **GBPCAD sale (T1547.2–1653.3):** D bearish BOS→H4 bearish BO; H2 direct
  route unavailable immediately, forms later. H4 direct KL sale works;
  post-reaction CE H2 engulf, H3 engulf/BO+liquidity and H1 BO+liquidity
  all shown. Distinct approaches share context, not mandatory stacked fills.

### B1 — key-level bias

- Theory T47.4–847.6 includes four KL types, body-close role flips,
  rejection/closed-candle/next-TF BO or sweep+BOS and same-Weekly-level Daily
  fallback; detailed rules1–7. F004,008,014 independently confirm drawings.
- **AUDJPY (T871.0–1162.3; F016):** Monthly bullish; Weekly counter move
  retracement/internal liquidity; twice-flipped OC now buy → Weekly rejection
  → Daily sweep+BOS then repeated bullish BOs. Daily KL rejection→H4 sweep+
  BOS and extreme retest; another reused Daily A now supports buys→H4 BO.
  BO need not retest; direction validation separate from filled entry.
- **EURUSD sell (T1175.2–1459.5; F023):** W bearish OC reject; D opposite
  bullish break initially not aligned. Same W level receives one/two closed
  Daily rejection candles; use Daily-origin fallback → H4 bearish BO/liquidity
  and advanced structures, follow sales. Later actual Daily bearish BO confirms
  Weekly story. Do not backdate late Weekly confirmation over earlier fallback.
- **SPX sell (T1461.5–1638.1):** explanation partly uses liquidity despite
  key-level topic; W bullish/prior high sweep → D bearish BO→Daily bearish
  OC reject, external low standing → H4 bearish BO→no retest, bearish flow
  continues. Retest absent ≠ directional BO absent.
- **BTC no buy (T1638.8–1796.8; F030):** W bearish; Daily bullish BO/reused
  A buy KL reject/closed on Thursday offers temporary buy idea; H4 never
  gives required bullish BO, instead sell KL rejects/close below → criteria
  incomplete, **no reason to buy**. Genuine no-directional-confirmation case.
- **XAU outlook (T1796.8–1957.1; F033):** W bearish/reused OC sell rejection,
  Daily bullish BO disagrees, prefers sales. Earlier Daily rejection produced
  H4 bearish BO; latest Daily rejection has **no new H4 bearish BO yet**, so
  waits. Does not deny possible interim buys; conditional forecast not order.

### B2 — liquidity bias

- Theory T29.3–928.5 specifies sweep+close+next-TF BO/BOS and counter-structure
  nearer target guard. F004,008,015 resolve high/low and target-vs-KL mapping.
- **EURCAD buy (T946.9–1224.8; F018):** W bearish but previous W low swept;
  near liquidity first target until D confirms. Daily later body closes above
  that nearer liquidity/bullish sweep+BOS rather than reject→buy story; target
  W high/local liquidity because W still bearish. H4 structural liquidity /
  advanced-type-one retest then buy. Says he had trade yesterday and exited
  at that liquidity. Exact CE/price/time not narrated here.
- **AUDUSD example abandoned (T1224.8–1254.7):** starts locator but chooses
  not to use; do not count as fully demonstrated route.
- **SPX (T1261.1–1469.7; F023):** W bullish with prior high swept→D bearish
  BO confirms temporary sales to nearer liquidity only→IRL/ERL cycle repeats;
  later W low sweep+KL reaction→D bullish sweep+BOS→back bullish expansion.
  Multiple time stages, not simultaneous opposing orders.
- **NZDJPY sells (T1473.3–1615.9):** Weekly bullish but high swept, nearer
  liquidity first; liquidity then body-close through changes expectation→Daily
  bearish sweep+BOS confirms temporary sales into buy levels; H4 initially
  ranges, later liquidity swept and drops. ASR contradictions around1518–1527
  require frame mapping, not literal “not selling” as universal reversal rule.
- **GER40 (T1617.2–1848.3; F029):** bullish structure; breakout candle high
  swept does not mandate far low, first liquidity target→swept as new internal
  liquidity at buy KL→Weekly low sweep/reject→Daily sweep+BOS bullish. New
  breakout high sweep gives possible sell-to-nearer-liquidity outlook, but
  **no bearish breakout yet** at1780–1785. Single HTF candle can map to lower
  advanced structure; both deeper retest and immediate continuation possible.
- **AUS200 (T1848.3–1983.5):** W bullish BO/high sweep then nearer liquidity
  swept/KL reject, target next high; D sweep+BOS confirms buys; later Daily
  low sweep→H4 bullish BO buy continuation. Projected/retrospective chart
  path, not proven personal entry+exit for each segment.
- **BTC bearish outlook (T1983.5–2189.6; F035):** bearish structure, sweeps
  prior W highs despite bullish-coloured close→D sweep+BOS down, possible57k
  target. Reviews prior bearish breakout low sweep causing countertrend buys,
  he took sell loss where expected earlier rejection; rally need not take old
  high in bearish structure→later reject/close below and bearish continuation.
  Outlook and admitted prior loss separate, target57k not a realised claim.

### DR — multi-pair routine and trade outcomes

- Theory/workflow T27.1–321.4: many pairs increase exposure, forgetting,
  workload; checklist+time management, early scan and periodic watchlist review.
  Nine example-pair identities from screen: XAUUSD,EURNZD,USDCHF,AUDUSD,
  USDCAD,USDJPY,UK100,AUDCAD,CADCHF. Casual GU mention is not tenth pair.
- **USDCHF (T326.5–509.9,1506.2–1568.0; F007):** Weekly bullish, D bearish
  permits Daily/H4 story only with nearest reasonable target; D sell BO→flag,
  wait H4 sell BO→liquidity/extreme reaction→H2 breakout limit; Friday never
  retests. Still valid plan, not fill. Warn Weekly still bullish.
- **AUDUSD buy (T509.9–609.8,1569.1–1657.8; F028):** W structurally bearish
  but prior low swept; D bullish BO confirms→Wednesday flag→H4 BO/liquidity
  forms→H4 KL reaction→M30 engulf buy to external liquidity, ~5R narrated.
  This is an actual personal trade; multiple stop tool adjustments are not
  multiple orders. M30 feed/time grid must eventually be available.
- **USDCAD sells (T614.7–648.0,1657.8–1840.1):** W unclear/retracing, Daily
  sell→flag→H4 sell BO/liquidity/reject → H1/H2 breakout entry, nearer KL first
  target. Later H2 clean BO but **no H4 reaction/liquidity**, passed despite
  working; strong personal no-entry example for checklist enforcement.
- **USDJPY watch/miss (T648.8–767.1,1840.1–1901.4; F032):** W/D bullish,
  ignore H4 bears → Tuesday flag, reaction arrives Friday→H2 possible entry.
  Narrator conditionally examines where his realistic tight stop would be
  sniped versus farther safe stop. The conditional wording does not establish
  an actual stop-out trade from this routine clip.
- **XAUUSD (T770.2–870.6,1299.5–1382.5):** W high swept, D bearish BO→H4
  bearish BO/liquidity → reaction→H1 confirmation marked but **never retest**.
  He corrects “no entry” to “entry first, missed”; retain missed pending plan.
- **UK100 (T876.8–952.6,1901.4–2047.2):** W bullish; ignores initial D sell,
  waits D bullish BO→H4 BO/liquidity/reused OC reaction→H3 CE order, needs
  slightly more accommodating placement; **did not trigger him**. Later M30
  QMR hypothetical retest with stop below low shown; not extra actual win.
- **AUDCAD sale (T953.4–1064.0; F017):** W/D bearish/high sweep→Daily reject→
  small H4 body breakout through V→liquidity remains unswept, expected KL not
  reached; **miss** despite subsequent bearish continuation. New H4 BO does
  not remove his required outstanding liquidity sweep automatically.
- **CADCHF buy (T1064.0–1141.7,2060.6–2242.8; F037):** Monthly low swept/high
  draw→W bullish sweep+BOS→D bullish BO→H4 bullish BO; initial level never
  comes, next BO at6am→liquidity/reaction→low-swept/high-standing CE valid
  though not lower-TF engulf. His preferred breakout-level confirmation never
  retests; **personal missed CE**, direct trader could have caught ~5.5R.
- **EURNZD sale (T1141.7–1284.4,1382.5–1481.9; F025):** W/D bearish,
  first setup forgotten/missed→next H4 BO/liquidity/reaction→H3 engulf limit,
  ~4R plan. He says closed out and continue next week. Later H4 opposite BO
  alone not proof bullish Daily; Daily picture admits ambiguity. Exact exit
  reason/price and whether full4R realised remain unstated.

## Interpretation boundaries and work remaining

- Complete sampled-sheet audit pending for T3,E5,B1,B2,DR; inventory will be
  updated as sheets actually inspected. This document does not label the
  complete source study finished until that is done.
- Exact numerical reproduction is a separate later step. Dates on crosshairs
  and order-tool anchors are not broker fill timestamps; economic-news icons,
  chart right-edge clocks and local timezone displays must not be conflated.
- ASR repeatedly renders “R” as “hour”, bullish/bearish as “foolish/bears”,
  H4 as “flowers”, and symbols incorrectly. The visual corrections here are
  documented explicitly; unclear remaining speech is not converted to code.
- KL role reuse, external-range selection, liquidity segmentation, precise
  fourth-man wick/body geometry, FVG/imbalance stop construction, and story
  invalidation need integrated crosscheck with the full course study. Nothing
  here supports silently reusing Kevin's numeric swing parameters.
- Fine-grained candle clocks, cross-TF availability, tick equality, broker/feed
  offsets, expiry, spreads, slippage, commission, exposure and intrabar order
  assumptions are not completely specified in these sessions. Each later
  engineering choice must remain separate from source facts.
- Actual losses, no-trade criteria failures, passed otherwise-valid patterns,
  missed limits, cancelled orders, partial human exits and still-open trades
  are all part of the teacher examples. They must survive later replay design.
