# Independent source cross-check — 2026-10-20

Second-reader verification of the initial extraction claims. This review reads the
actual transcript files and opens the specific contact sheets named below. It is
a targeted check, not a claim that every transcript and frame has been reviewed.
The first-reader reports `course_verified.md` and `bishop_verified.md` were not
yet written when this check began; they were subsequently read and the named
claims below compared against them. `plug_verified.md` was also read.
Concurrent frame re-extraction changes Bishop sheet numbering: the original
25-tile sheet references below describe the images actually opened during this
review. Treat video slug plus timestamp as the stable citation, and consult the
current frame index after replacement.

## 1. Direct entry and the 10–11-pip quote: confirmed, with a correction

Source: `videos/video-3-all-you-need-to-know-about-structure/transcript.txt`.

- **1022.8–1035.8:** direct entrants may act with or without inducement if the
  key level overlaps an imbalance.
- **1035.8–1042.8:** explicitly says a wider stop “like 10 to 11 pips.”
- **1042.8–1057.8:** contrasts that approach with conservative traders waiting
  for confirmation.
- **1065.8–1078.8:** “you can just take the trade directly” if everything is in
  check and the key level overlaps imbalance; says to give it a ten-pip stop.

Opened `frames/video-3-all-you-need-to-know-about-structure/sheets/sheet_018.jpg`
(1020, 1035, 1050, 1065 seconds). These are schematic range/impulse/retest
drawings, consistent with the direct-entry discussion. They do **not** provide
a measured ten-pip entry/stop box or a dated real trade. Do not invent a replay
fixture from the underlying chart's displayed prices or date: the drawn paths
are teaching schematics.

**Correction to the earlier handoff:** the video-13 stop quote discusses
continuation, but a separate video-3 quote explicitly discusses direct style.
It is therefore inaccurate to say that every 10–11-pip reference in the course
applies only to continuation. Nevertheless, imposing one fixed stop on every
instrument and every structural origin example remains a configured owner
choice, not a substitute for the actual example's displayed stop.

## 2. H4 break on same day or next day: confirmed

Source: `videos/video-17-storyline-2/transcript.txt`, **1256.9–1271.7**.

“The break of structure can happen that same day, can happen the next day,
anyone is fine”; then says not to focus on previous versus current day and gives
daily rejection followed by H4 break next day as an example.

Opened `frames/video-17-storyline-2/sheets/sheet_022.jpg` (1260–1305 seconds).
The 1260-second panel still shows the schematic reversal discussion; no date
constraint is drawn. The transcript provides the explicit timing rule.

**Implementation consequence:** do not port Kevin's `next_day_rule=require` as
a Bishop teaching requirement. This is a calendar allowance, not permission to
trade before the required daily or weekly rejection candle has actually closed.
Keep event occurrence and event availability as separate timestamps in replay.

## 3. Engulfing entry versus established-storyline flip: confirmed

Same transcript, **1133.1–1191.1**, **1201.1–1234.1**, and **1280.5–1318.1**.

- Engulfing can be used for entry confirmation.
- A weekly reject/close followed by daily engulfing has further H4 breakout or
  sweep-and-break confirmation; daily engulfing alone does not finish that route.
- For an already active daily-level-to-daily-level storyline, an engulfing
  cannot by itself validate a change of direction. It can support a retracement
  entry without changing the larger storyline.

Opened `frames/video-17-storyline-2/sheets/sheet_021.jpg` (1200–1245 seconds)
and `sheet_022.jpg`. The diagrams show opposite range levels and an upward
retracement from the bottom within the range; the latter sheet subsequently
sketches the weekly/daily/H4 cascade. No numerical engulfing threshold is given.

**Scope caution:** at 1133–1144 the speaker says “unless it was engulfing that
started the previous storyline,” followed by a clarification of the weekly →
daily-engulfing → H4-break route. Preserve that clarification rather than a
blanket claim that engulfing never participates in any bias-building process.
The supported prohibition is **engulfing alone cannot flip the established
storyline**.

## 4. Bishop direct H2 route waits for closed H4 breakout: confirmed

Source: new
`videos/bishop-defi-bishop-study-20-minute-series-part-5-approach-to-direct-and-confirmation-entries-case/transcript.txt`.

- **106.6–112.3:** “after your four hour breakout candle has closed,” scale
  down to H2.
- **116.2–124.4:** H2 sweep-and-break with liquidity, or breakout with liquidity.
- **124.4–135.5:** direct H2 entry from the nearby key level and onward to ERL.

Opened the matching frame root's `sheets/sheet_001.jpg`. Its index explicitly
says **25 frames/sheet at 20-second intervals**, not the 4-frame/15-second
format of the new course sheets. At 100 seconds the drawing labels the H4
breakout and scale-down route; 120 seconds shows an H2 schematic.

**Implementation consequence:** aggressive entry does not mean using a
still-forming H4 breakout candle. The direct execution route follows completed
bias confirmation and its own H2 liquidity/key-level setup. Do not silently
replace that route with an unconditional H4 close entry.

## 5. Nearest external liquidity as Bishop's target: confirmed

Source: new
`videos/bishop-defi-bishop-study-10-minute-series-part-1-bias-entries-amp-confirmation-entries-combined/transcript.txt`.

- **273.8–310.1:** Japan225 example: daily rejection, H4 breakout, H4
  single-candle liquidity swept, then H1 sweep-and-break confirmation.
- **319.4–326.8:** once ERL is taken, expect reversal.
- **326.8–337.6:** says his personal target is the **nearest external
  liquidity**, explicitly distinguishing that preference from prescribing what
  the student must use.

Opened its `sheets/sheet_001.jpg` (25 frames, 0–480 seconds). At 280–320 seconds
the chart progresses from daily reaction through lower-TF confirmation; at
320 seconds a long box reaches the previously marked high, followed by the
reversal around 340 seconds. This visually supports target-at-ERL. The sheet
view does not justify a precision price/date extraction here.

Also corroborated in the older clean transcription
`videos/bishop-bias-entries/transcript.txt`, **322.7–337.6**, and
`videos/bishop-trades-breakdown-2/transcript.txt`, **167.2–172.2**. The new
repeating-system transcription names “closest external liquidity” at
**593.6–599.2**.

**Correction to implementation defaults:** fixed 3R is not an exact-match
replacement for the teacher's ERL target. A fixture's displayed/quoted target
must remain unchanged. Fixed-R management can be compared as a separately
labelled variant, with its intentional differences reported.

## 6. Imbalance is not a mandatory gate for every entry: confirmed C15

Source: `videos/video-14-entry-models-1/transcript.txt`, **102.7–147.7**.
Explicitly describes complete advanced market structure with no key level
overlapping imbalance, then a nearby open-close level used after IRL is taken.
At **173.7–179.7** the central sequence is IRL taken and reaction from a key
level. Opened `frames/video-14-entry-models-1/sheets/sheet_002.jpg` and
`sheet_003.jpg` (60–165 seconds): the schematic draws the IRL/range sequence and
adds nearby horizontal levels. This confirms first-reader C15's distinction:
direct-at-imbalance is one model, not a mandatory FVG gate on all origin/AMS
entry models.

## 7. Asian session clock: confirmed C08, discrepancy preserved

Source: `videos/video-6-part-2-liquidity/transcript.txt`, **748.1–797.5**.
The speaker selects New York, calls it UTC−4, and repeatedly says 17:00 to
midnight. At **778.7–788.0** he explicitly says “don't mind this 15” and claims
the cursor endpoint shows midnight.

Opened `frames/video-6-part-2-liquidity/sheets/sheet_013.jpg`: at 750 seconds the
timezone menu shows UTC−4 New York, while at 765 seconds the indicator settings
visibly read **17:00–00:15**. First-reader C08 correctly preserves that UI/speech
discrepancy. The source does not establish a year-round fixed-UTC interval or
settle whether future code should follow NY civil-time DST or a fixed offset.

## 8. Independent check of two PDF observations

Independently rendered pages 5 and 6 directly from the committed PDF using
`pdftoppm -f 5 -l 6 -scale-to 1800 -png`, then opened both render outputs.
Compared the resulting labels with `tests/bishop_examples.json`:

| Fixture | Second reader's observed labels | Result |
|---|---|---|
| `pdf-p05-eurchf-buy-1` | EURCHF, 30-minute, FOREXCOM; grey entry **0.93193**, red stop **0.93147**, teal target **0.93498**. TradingView snapshot header **Jul 29, 2026 08:59 UTC+1**. | Numeric labels agree. Chart snapshot time is **not** an order-creation or fill timestamp. |
| `pdf-p06-eurchf-buy-1` | EURCHF.x, M30; dashed **BUY LIMIT 0.91** at **0.93193**, SL **0.93147**, TP **0.93704**. Axis shows 28 Jul/29 Jul, with no independently readable year or timezone. | Numeric labels and pending-order type agree. Actual fill and exact UTC eligibility remain unknown. |

The two targets genuinely differ. Keeping two separate observations is correct;
changing the page-5 chart target to match the page-6 pending order would corrupt
the source. Neither record is promoted to fully verified replay status: the
labels receive second-reader confirmation, while exact event time, source-feed
alignment, trigger identification, execution status and tolerances remain open.

## Remaining verification limits

- This checks the named rule claims, not all source material.
- It establishes no exact historical trade match: these observations do not
  yet include causal candle replays through a completed Bishop engine.
- Numeric imbalance detection, engulfing body bounds, impulse size, equality
  tolerances, and session/time-zone conventions need separate explicit
  definitions and source checks. No such thresholds can be inferred merely
  from the speech above.
