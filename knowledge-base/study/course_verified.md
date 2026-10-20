# Core-course source verification — first pass

Reviewed 2026-10-20 against the newly generated, descriptive-slug transcripts.
This is an evidence ledger, **not an assertion that every transcript or frame
has been reviewed**. No bot output has yet been compared with all course trades.
The old `STRATEGY.md` remains a draft wherever a claim is absent from this ledger.

`T vN@a-b` means seconds a–b in the descriptive `video-N-*` transcript;
`F vN/sheet_NNN` means a contact sheet actually opened during this review.
`confirmed` means the stated rule was directly checked in the cited passage;
`corrected` means an overbroad draft/imported interpretation must change;
`new` adds precision missing from the draft. Implementation choices are separate.

**Subsequent extraction finding:** original ffmpeg `fps` sampling may show a
source state around 7.5 seconds after its burned `n*15` label. The exact 1395s
frame versus the sheet labelled 1395s showed an unfinished versus finished box.
Core sheets have not yet been regenerated; their timestamps below are approximate
locators, not proof of the candle state at that exact second. Transcript segment
citations are unchanged. Historical fixtures require native-time frame extraction
and direct state verification before assigning precise times or geometry.

## Rules checked directly

| ID | Status | Rule and implementation consequence | Evidence |
|---|---|---|---|
| C01 | confirmed | Bullish = HH/HL; bearish = LH/LL. In bullish context HH is ERL and HL is IRL/structural point; mirror for bearish. These are contextual roles, not permanent tags on every candle. | T v3@48-170,246-284; v5@149-198,297-320 |
| C02 | corrected | A shift may break one **or** two structural points; do not hard-code two as a universal prerequisite. No numerical swing/fractal order is supplied here. | T v3@298-323,566-595 |
| C03 | confirmed | Body close beyond a structural point is a break. Wick excursion and close back inside is a liquidity sweep, not the same event. Wait for the analysis candle to close before classifying it. | T v3@427-535,605-642 |
| C04 | confirmed | A consolidation has no directional bias by itself. Two taught exits: sweep/manipulation then displacement, or direct break followed by retest of the disrespected level. Do not require a sweep for the latter. | T v3@647-993 |
| C05 | confirmed | Aggressive/direct entry can act at a KL overlapping an imbalance **without waiting for inducement**. Approximately 10–11 pips is expressly discussed for this style; confirmation entries are the alternative. This does not establish fixed 10 pips for every actual example. | T v3@1002-1078 |
| C06 | confirmed | Defined range starts with sweep + break; IRL→ERL→new IRL is the range progression. Distinguish a wick sweep of the external extreme from a body breakout that extends the range. | T v7@305-326,1683-1734,1783-1786,1866-1918,1983-2026 |
| C07 | confirmed | Previous D/W/M highs/lows and Asian highs/lows are liquidity forms and possible targets. Prior-day low sweep points toward prior-day high, and mirrors recursively, subject to actual directional context. These are teachings/expectations, not a guarantee of market outcome. | T v5@1100-1128,1190-1313; v6@519-564 |
| C08 | new | Asian-session illustration uses New York chart time and says 17:00→midnight. Source UI has an end-time discrepancy (see below); do not silently choose a universal fixed UTC window. | T v6@728-797; F v6/sheet_013 at 750/765s |
| C09 | confirmed | Monthly KL reaction/close is checked on W for sweep+break or engulfing, then D for opportunities. Weekly similarly scales to D. An HTF reaction alone is a lean, not a licence to ignore lower-TF confirmation. | T v9@76-151,574-672 |
| C10 | corrected | Lower-TF counter-direction moves can be traded as retracements, but do not by themselves reverse the established larger storyline. A strict global no-countertrend assertion is a selected aligned-only bot policy, not an accurate description of every taught example. | T v9@674-697,754-828; v17@1203-1234,1406-1454 |
| C11 | confirmed | KLs are specific closing/body prices, not a whole order-block box. Types: A peak, V trough, and open-close junction of consecutive same-direction candles. Wicks have separate sweep/tap roles. | T v11@60-111,122-145,488-491; F v11/sheet_003 |
| C12 | confirmed | A normally supplies sells; V normally supplies buys. An impulsive body close through flips the level's usable role for a retest. Both OC roles can also flip. Exact impulse threshold is unspecified. | T v11@151-270 |
| C13 | confirmed | OC entry logic is not just candle-body engulfing. Two consecutive down candles form an OC; a later engulfing/body close through that OC can produce a bullish retest (mirror bearish). Teacher says it need not engulf both original candles. | T v11@276-406; v14@533-606,636-658 |
| C14 | confirmed | Mechanized initial cascade: D KL tap→reject→close, then H4 sweep/break or engulfing pathway, then entries at a nearby qualifying KL. Earlier engulfing statements must be read with v17's later distinction below. | T v11@598-628; v12@545-656 |
| C15 | corrected | Imbalance overlap is desirable, but NOT an unconditional requirement for every origin/AMS entry: teacher explicitly allows complete AMS without overlap and uses nearby OC after IRL sweep. Keep these models distinct instead of a universal FVG gate. | T v14@89-179 |
| C16 | confirmed | Continuation bearish example: prior ERL/V is broken with an impulsive close; seek nearby IRL and retest the disrespected level overlapping imbalance. Mirror bullish. 10–11-pip stop and 3R/4R are preferences stated here. | T v14@263-355 |
| C17 | corrected | Additional IRL is NOT required for every continuation/confirmation: HTF level tested and closes appropriately, lower H1/M30 engulfing, then A/V retest is valid without another IRL. Do not force the third model below on all entries. | T v12@1600-1704,1802-1828,1899-1915; F v12/sheet_028 |
| C18 | confirmed | Three alternative lower-TF entry models: (1) engulf→direct retest of new A/V; (2) engulf breaks OC made by two consecutive opposite candles→OC retest; (3) engulf→next candle approaches but does not tap A/V (becomes IRL)→sweep that candle and tap level. They are alternatives, not simultaneous conditions. | T v14@456-753; F v14/sheet_009 confirms first-model schematic at 480-525s |
| C19 | confirmed | H4 setup can use H1 or M30 entry confirmation. H1 continuation can add a position from M30/M15 when one of those models reforms. Do not enforce a one-position-per-story assumption as teacher law. | T v14@456-478,376-419,787-825 |
| C20 | confirmed | Prefer a consistent selected entry system rather than an unexplained dynamic choice among models. Selection is a setting; all three models are taught. | T v15@52-167 |
| C21 | confirmed | Origin ideal stop beyond strong sweep high/low; lower-TF confirmation stop beyond relevant wick. Add 1 pip or 0.5 pip buffer. Fixed ~10-pip personal preference is explicitly contrasted with safer structural placement; 5-pip near-miss acknowledged. | T v13@307-332,1717-1936,2142-2157; F v13/sheet_033 |
| C22 | confirmed | Storyline target is next KL on its origin TF: D story targets D KL even with H1 entry; H4 story targets H4 KL. Entry TF must not silently replace target TF. Source also teaches routine 3R, so report structural target and fixed-R management as distinct policies. | T v16@822-970; v4@126-194; v14@345-355 |
| C23 | corrected | An engulfing/OC break ALONE does not flip an already-running storyline. At its next origin-TF KL, require next-lower-TF breakout or sweep+break in new direction. A lower-TF retracement entry is not a confirmed storyline flip. | T v17@1203-1234,1339-1454; F v17/sheet_021 (schematic, not measured trade) |
| C24 | corrected | Engulfing is not completely banned from top-down initial context: W reject→D engulf is mentioned, but teacher then requires H4 breakout or sweep+break to establish synchronization. An implementation treating D engulf as self-sufficient would overstate the teaching. | T v17@1133-1191,1280-1318 |
| C25 | corrected | Breakout confirming a D rejection can occur SAME DAY or NEXT DAY. Kevin's default next-day-only gate must not be ported as a Bishop course requirement. | T v17@1248-1272 |
| C26 | confirmed | Most recent breakout establishes direction; entry need not be at that exact breakout level. Seek valid KL nearest the expected liquidity. If two unresolved candidates compete, using the extreme is described as a practical fallback. No unconditional nearest/farthest ranking is justified. | T v18@1402-1449,1580-1611 |
| C27 | confirmed | Single-candle formation may serve as both IRL and ERL depending on the stage of the range cycle. A permanent `candle_type=IRL` without context is insufficient. | T v18@94-118,248-271,297-320 |

## Actual visual coverage

Opened and rendered six sheets (24 sampled frames); no claim of full frame coverage:

- `video-11-key-levels-1/sheets/sheet_003.jpg`, 120/135/150/165s:
  hand-drawn A peak and V trough, with thin lines through turns; central
  two-candle drawing has a line at the shared body junction. These are schematic
  illustrations on an EURUSD chart, not timed EURUSD trades.
- `video-13-bias-continuation-part-2/sheets/sheet_033.jpg`, 1920–1965s:
  EURUSD chart with long box and turquoise origin/continuation sketches; Gold
  chart appears at 1965s. Supports context distinction around fixed-stop Q&A;
  exact box prices have not been independently transcribed for a trade fixture.
- `video-17-storyline-2/sheets/sheet_021.jpg`, 1200–1245s:
  Gold 1h plotting area used as a whiteboard, horizontal bounds and hand-drawn
  bearish path then bullish retracement. Not a historical Gold trade.
- `video-6-part-2-liquidity/sheets/sheet_013.jpg`, 720–765s:
  GBPUSD chart with shaded session boxes; time-zone list at 750s shows New York,
  and indicator dialog at 765s reads Session **17:00–00:15**. Spoken explanation
  at 778–788s says disregard “15,” cursor indicates midnight. End-boundary
  inclusion requires explicit treatment; do not erase this source discrepancy.
- `video-14-entry-models-1/sheets/sheet_009.jpg`, 480–525s:
  whiteboard bearish AMS, “4hrs→1hr/30m,” then engulfing/tap drawing; confirms
  direct A-level retest model rather than live measurable Gold execution.
- `video-12-bias-continuation-part-1/sheets/sheet_028.jpg`, 1620–1665s:
  hand-drawn bullish continuation and engulfing candles at the broken level;
  illustrates lower-TF confirmation and structural-stop alternative.

## Numerical definitions that remain implementation choices

Do not attribute these to the teacher without more evidence:

- Fixed n-left/n-right swing detector, tie-handling and initialization.
- Impulse body threshold, displacement ATR multiple or minimum FVG width.
- Exact three-candle FVG algorithm: imbalance is used throughout these checked
  passages, but a complete mathematical boundary definition has not been checked.
- Numerical definition of “near,” “overlap,” exact KL/open matching tolerance,
  engulfing body/range tests, maximum wait/holding age, and setup freshness count.
- Default stacking cap, portfolio risk cap, spread/commission/slippage assumptions.
- Session DST handling, 00:00 versus 00:15 cutoff, candle-boundary alignment
  matching the source's broker. Core v6 says UTC−4 New York during its sample;
  it does not prove year-round fixed UTC−4.
- Whether every origin trade permits entry before source-TF close. Direct entries
  and conservative lower-TF confirmation are distinct; do not mix their clocks.

## Example acceptance implications

An abstract schematic can test the rule sequence but is not a historical trade
with readable price/date/OHLC. Preserve that distinction in example fixtures.
Do not infer dates from the chart's current/replay cursor unless the teaching
actually associates the trade with that date. For a historical trade, independently
verify symbol, broker, TF, entry time/price, stop, target, and uncertainty before
claiming exact replay coverage. An unreadable field remains unresolved, never zero.

To satisfy “all verified examples match,” separate teacher-exact replay from the
owner's aggressive fixed-stop operating preset. A fixed-stop preset need not equal
a teacher's zone-edge or sweep-extreme stop; a mismatch is not cured by modifying
the expected source stop. A trade passing side/entry alone is not a full pass.

## Coverage still open

This first pass used targeted reading across videos 1–18 (orientation 1–2,
structure 3–4, liquidity 5–6, ranges 7–8, bias 9–10, levels 11, entry/management
12–15, storyline 16–18). It did **not** read every line of all 18 transcripts or
inspect every frame. In particular, live examples in v4/v8/v10/v13/v15/v18 need
the example extractor's independent chart verification. Claims of “all source
fully processed / zero contradictions” in the old rulebook are not established by
this review. Supplementary Bishop sessions need their own independent ledger.
