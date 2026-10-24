# USDCAD and GBPJPY: additional direct PDF replay source review

2026-10-24. Read-only independent source pass for PDF p14–15, p18–19 and
p34–35. No acquisition, engine, fixture, expected value or tolerance change.
The existing local frozen Kevin datasets are possible alternate-feed diagnostic
inputs; they were not read or used to select source prices or timestamps here.
This document establishes source observations, not successful historical replay.

## Actual inspection and references

Opened original `supplementary/source/bishops_trade_chart_examples.pdf` rendered
pages14,15,18,19,34,35 individually at3000px long edge. Also rendered p19 at6000px
and inspected its enlarged overlapping target-box region to resolve the two
printed target associations. Temporary artifacts:
`/workspace/scratch/eurgbp_source_review/other-{14,15,18,19,34,35}.png`,
`detail-19.png`, and `p19_targets_crop.png`.
Read relevant detailed entries in `full_supplement_study.md`, and existing
fixture observations `pdf-p15-usdcad-sell-1`, `pdf-p19-gbpjpy-buy-1`,
`pdf-p19-gbpjpy-buy-2`, `pdf-p35-gbpjpy-buy-1` in
`tests/bishop_examples.json`. Existing values agree where directly readable;
this is a second image reading, not an assumption that fixtures are verified.

## Verified snapshot minutes and UTC conversion

| Source panel | Printed creation time | UTC minute |
|---|---|---|
| p14 USDCAD Daily | Jul16,2026 14:32 UTC+1 | 2026-07-16 13:32 UTC |
| p14 USDCAD H4 | Jul16,2026 14:33 UTC+1 | 2026-07-16 13:33 UTC |
| p15 USDCAD H1 | Jul16,2026 14:35 UTC+1 | 2026-07-16 13:35 UTC |
| p18 GBPJPY Daily | Jul15,2026 18:20 UTC+1 | 2026-07-15 17:20 UTC |
| p18 GBPJPY H4 | Jul15,2026 18:21 UTC+1 | 2026-07-15 17:21 UTC |
| p19 GBPJPY H1 | Jul15,2026 18:26 UTC+1 | 2026-07-15 17:26 UTC |
| p34 GBPJPY Daily | Jun05,2026 13:10 UTC+1 | 2026-06-05 12:10 UTC |
| p34 GBPJPY H4 | Jun05,2026 13:11 UTC+1 | 2026-06-05 12:11 UTC |
| p35 GBPJPY H1 | Jun05,2026 13:13 UTC+1 | 2026-06-05 12:13 UTC |

Each is minute precision: the possible snapshot seconds lie within that printed
minute. These are image creation/export clocks, not setup-eligibility, limit
placement, retest, fill, story origin close or structural confirmation clocks.
Printed UTC+1 permits direct conversion without inferring DST from an asset.
The phone status clocks14:51 (p15) and18:29 (p19) do not print timezone/date.
Phone-axis times are likewise not independently established UTC times.

Daily and lower panels visibly show different right-edge market stages; p18
Daily displays216.822 while H4 already extends above218.8. A minute-separated
export is not proof that the charts' rightmost candles are synchronous live
states. The cause of differing states is not established by the pictures.
Do not derive closed Daily readiness from export time and a rightmost candle.

## Independent price extraction

| Observation | Direction/annotated route | Entry | Source drawn stop | Source drawn target |
|---|---|---:|---:|---:|
| p15 USDCAD | SELL, H1 Breakout Confirmation Entry | 1.40471 | 1.40539 | 1.40129 |
| p19 GBPJPY first | BUY, H1 breakout Confirmation Entry1 | 216.877 | 216.700 | 218.014 |
| p19 GBPJPY second | BUY, H1 Breakout with idm Confirmation Entry2 | 217.255 | 217.088 | 218.007 |
| p35 GBPJPY | BUY, H1 Breakout Confirmation Entry | not printed | not printed | not printed |

p19's target mapping is independently supported by the enlarged box geometry:
the first wider/light-green tool begins at the lower216.877 entry and its top
edge is slightly higher; the second narrower tool begins at217.255 and its top
is slightly lower. The two green axis labels are218.014 above218.007,
respectively. Thus the existing first→218.014/second→218.007 mapping agrees
with the actual image. This resolves that particular label association without
claiming numeric broker execution matches.

Do not turn p35's price-axis proximity into an exact entry, stop or TP. The
chart has neither numbered position-tool labels nor a broker order record.
The horizontal references are contextual levels, not three independently
labelled trade prices.

## p14–15 USDCAD: source sequence and limits

All TradingView panels identify USDCAD / FOREXCOM. p14 Daily explicitly says
**Daily bearish breakout**. Price previously rallied, formed an upper cluster,
then declined through two marked body references before an extended downward
leg. This is a bearish Daily structural context claim. The figure does not
explicitly annotate a Daily KL rejection or a prior-day-high sweep: do not
invent both as mandatory origin events when testing this example.

H4 shows bearish delivery, a corrective bounce into a marked internal level
near1.4054, then renewed selling. Its annotation is **H4 breakout with idm /
H4rH4**. Exact body-reference ID, liquidity candle(s), reaction and availability
clocks remain to be reconstructed. A recent local pivot chosen by the engine
is not automatically the chart's intended protected origin.

p15 H1 labels **H1 Breakout Confirmation Entry** at1.40471. The correction and
local breakout/retest area precede continued bearish candles. The source-selected
stop is1.40539 and target1.40129; the last visible lower wick passes the drawn
target. This shows the chart plan's later excursion, not original order type,
acceptance time or realized planned R.

The adjoining mobile **USDCAD.pi H1** chart has a red downward arrow around
1.4046 and a connected blue upward arrow around1.4024. These are approximate
visual axis readings, not precise prices to write into fixtures. The depicted
closed short leg ends substantially above the chart's1.40129 TP. Preserve this
execution-vs-plan distinction: the later chart touching TP must not overwrite
the mobile early-close path. There is no printed original broker stop/TP or
order-history row identifying exact fill/exit. The `.pi` symbol is a visible
provider/symbol difference from the TradingView FOREXCOM source.

Critical checks: Daily bearish BO identity/availability → related H4 bearish
structure/known inducement and KL reaction → positive H1 BO and selected KL →
readiness before limit touch. Verify whether the source stop protects the shown
upper reference; do not infer an FVG far edge from a red risk rectangle. The
snapshot has already observed a long drop and cannot supply the missing order
creation clock.

## p18–19 GBPJPY: two drawn entries, three phone arrows

All TradingView panels identify GBPJPY / FOREXCOM. p18 Daily explicitly says
**Daily bullish breakout / Daily reject Daily**. An upward leg is followed by
a pullback to marked body references. No Weekly confirmation is shown; no
universal Weekly alignment claim follows.

p18 H4 falls from an upper swing to a lower wick/internal floor near216.5,
recovers, revisits the later body region near216.8 and then expands strongly.
The deeper **Daily** reaction and later **H4 breakout with idm / H4rH4** region
are separate annotations. A single latest-local-low representation would lose
that layered sequence.

p19 H1 first shows a small base, upward departure and the first annotated
breakout entry at216.877. Later a new bullish breakout/inducement opportunity
is marked as entry2 at217.255 with its own217.088 stop. The two drawings share
nearly the same upper objective but retain separate exact target labels above.
They are source-demonstrated additional entry/continuation opportunities;
they must not be merged into one order or treated as automatic retries.
No source sentence on this page proves that first entry is a prerequisite to
qualifying the second pattern.

Subsequent chart candles rise above both targets. The adjacent **GBPJPY.pi H1**
mobile chart visibly has **three** blue entry arrows (roughly216.86,217.0 and
217.18) connected toward a red exit near217.8. Those are approximate readings;
only the fact of multiple depicted entry paths and lower common exit region is
secure here. Two chart tools do not establish exactly two broker positions,
and three phone entries cannot be forced one-to-one onto the two chart plans.
The phone exit is below both drawn targets; do not book full target R for each
plan from the later rally. Exact position IDs, size allocation, fill/exit
prices, management decisions and server timezone remain unresolved.

Critical checks: Daily positive structure/rejection → H4 liquidity and reaction
at the correct layered reference → first H1 positive BO → fresh second H1 BO
with inducement; retain eligibility clocks, first/second identity and independent
protection. None of those clocks equals the17:26UTC export minute. Source wick
vs body reference and exact single/series inducement must be causally identified.

## p34–35 GBPJPY: context/model replay only

This is a separate June05 story, not p19's July15 sequence. p34 Daily explicitly
says **Daily bullish breakout / PDL Swept**. The higher-timeframe chart shows an
upward leg, pullback and lower-tail rejection. H4 has a deeper low-sweep toward
the marked Daily-origin area, recovery and later pullback/base near214.7,
followed by fresh expansion. **H4 breakout with idm / H4rH4** labels the higher
entry-context region. Daily-origin and H4 reaction references remain distinct.

p35 is a candlestick H1 chart, not a line chart. Initial rally/pullback produces
a base near214.7; a subsequent upward break through the local body reference
near214.8 accelerates above215.5. Explicit label: **H1 Breakout Confirmation
Entry**. Those approximate levels describe geometry only. There is no numeric
entry/stop/target box, no exact price plan, and no phone execution evidence.
This case can test contextual direction, source TF/model and sequence only
until stronger source information exists. It cannot fully pass numeric entry,
stop, target or executed-result acceptance. The12:13UTC snapshot is an upper
observation bound for the annotated completed picture, not a fill timestamp.

## What is confirmed and what remains open

Confirmed by direct second image reading: source instrument labels, FOREXCOM
panels, stated Daily direction/narrative, H4rH4 context, H1 breakout family,
all nine printed price labels on p15/p19, p19 target associations and the nine
creation-minute UTC conversions. Mobile execution-path differences are retained
as visible qualitative evidence, not exact broker accounting.

Unresolved: source candle IDs and actual earliest eligibility UTC, original
order type/placement time, FOREXCOM feed/candle alignment, historical broker
server timezone, exact selected KL geometry/liquidity segmentation, stop
rationale independent of the drawn risk box, and exact realized outcomes.
Existing local alternate-provider H1 data can diagnose model disagreement but
cannot repair these source omissions or certify exact FOREXCOM replication.
H1 input also cannot independently reconstruct sub-H1 confirmations/ordering.
No full historical acceptance or profitable result is claimed by this review.
