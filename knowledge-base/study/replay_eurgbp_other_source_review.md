# EURGBP PDF p36–37 and p53–54: independent source reading

2026-10-23. Read-only source review for `pdf-p37-eurgbp-sell-1` and
`pdf-p54-eurgbp-buy-1`. This reviews source annotations and visible geometry;
it is not detector/feed agreement or an accepted historical replay.
No fixture, engine, tolerance or timestamp was changed. No alternate feed was
consulted in this extraction.

## Material actually inspected

Rendered original `supplementary/source/bishops_trade_chart_examples.pdf` pages
36,37,53,54 with pdftoppm at 3000px long edge and opened all four rendered
images individually. Temporary renders are under
`/workspace/scratch/eurgbp_source_review/page-{36,37,53,54}.png`.
Cross-read `full_supplement_study.md` detailed pages35–60, source-rule sections
of `../STRATEGY.md`, `full_entry_study.md` and `full_session_study.md`, and the
existing two observations in `tests/bishop_examples.json`. Agreement with the
old fixture is reported below, not used as a substitute for reading the image.

## Independently read price labels

| Source | Side/model annotation | Entry (grey) | Stop (red) | Target (teal) |
|---|---|---:|---:|---:|
| p37 | SELL, “H1 Engulfing Confirmation Entry” | 0.86580 | 0.86611 | 0.86451 |
| p54 | BUY, “H2 Breakout Confirmation Entry” | 0.86609 | 0.86544 | 0.86975 |

These six printed labels agree with the current fixture values. In particular,
p54 entry is **0.86609**, not the superseded 0.86606 extraction. p37 entry is
printed with its final zero. These are independently confirmed drawn-plan
prices; exact broker fills and actual stop/TP instructions are not established
by these labels. Assuming conventional EURGBP pip=0.0001, arithmetic planned
risk/reward is p37 3.1p/12.9p (about4.16R) and p54 6.5p/36.6p (about5.63R).
These derived ratios are not source claims of realized returns.

## What the creation timestamps establish

| Panel | Printed TradingView creation time | Direct UTC conversion |
|---|---|---|
| p36 Daily | Jun01,2026 17:05 UTC+1 | 2026-06-01 16:05 UTC, minute precision |
| p36 H4 | Jun01,2026 17:06 UTC+1 | 2026-06-01 16:06 UTC, minute precision |
| p37 H1 | Jun01,2026 17:08 UTC+1 | 2026-06-01 16:08 UTC, minute precision |
| p53 Daily | May14,2026 20:06 UTC+1 | 2026-05-14 19:06 UTC, minute precision |
| p53 H4 | May14,2026 20:07 UTC+1 | 2026-05-14 19:07 UTC, minute precision |
| p54 H2 | May14,2026 20:09 UTC+1 | 2026-05-14 19:09 UTC, minute precision |

If represented as intervals, each printed minute spans that UTC minute through
before the next minute; seconds are absent. These are creation/export snapshot
clocks, **not setup, order creation, retest, fill, Daily close or H4 close clocks**.
They establish that the annotated picture existed by that printed snapshot,
assuming its metadata, not when each pattern first became tradable. The visible
later rally/drop has already occurred in the lower chart at export.

The Daily and lower panels also show differing right-edge price states (e.g.
p53 Daily0.86597 versus H4 approximately0.87095, p36 Daily0.86659 versus
H4 approximately0.86411). Do not assume their rightmost candles represent one
synchronously live state merely because exports are a minute apart. The reason
for those differing states is not established by the pictures. The phone p37
clock says17:09 without an explicit timezone/date in its status bar. Phone-axis
29May/1Jun labels are useful local chart context, not UTC fill timestamps.

## p36–37 SELL: observed context and sequence

p36 Daily is explicitly labelled “Daily recent breakout bearish / PDH swept /
Daily reject Daily”. Its chart shows a prior downward leg, subsequent recovery
to the marked upper Daily reference and the latest illustrated rejection near
that region. Therefore the source's stated usable direction is **Daily bearish**;
it is not evidence that a Weekly bearish story was independently confirmed.
The higher and lower horizontal Daily references remain distinct objects.
The exact candle IDs, body-close reference and reaction-close availability must
be reconstructed; no exact source level prices are printed for those context
lines.

p36 H4 repeats that Daily annotation at the upper area. Visible H4 recovery
wicks through an upper reference, followed by downward displacement. A later
small return near the lower local reference precedes further decline. The
entry-context annotation is “H4 breakout with idm / H4rH4”. This is evidence of
the teacher's H4 breakout/inducement/reaction interpretation, not a numerical
one-bar-only liquidity detector or mathematical FVG definition.

p37 H1 repeats the Daily and H4 context labels. Price initially declines,
rebounds from a nearer low into the layered H4 reference area, then turns down;
the selected H1 price is explicitly annotated **engulfing confirmation entry**.
The printed short tool has stop above entry and target at a lower horizontal
reference. Subsequent visible candles extend below0.86451 and below0.8643.
That establishes target traversal on the illustrated chart, not exact intrabar
order or realized broker R.

The adjacent mobile EURGBP H1 chart contains a red downward arrow near0.8657
and a blue upward arrow near0.8645 connected by a dashed red line. This is
additional visible evidence of a depicted completed short execution path, which
should be retained beside the current fixture's ILLUSTRATIVE_PLAN classification.
It is more than an empty risk box, but it is not a numerical order-history row:
exact entry, exit, size, stop and target instructions, server timezone and
identity linkage to the left drawing cannot be independently recovered here.
Do not simply replace0.86580 with an axis-interpolated phone entry or assert
that the pictured stop/target were actually submitted. Exact participation and
execution accounting remain unresolved pending stronger broker evidence.

## p53–54 BUY: observed context and sequence

p53 Daily explicitly says “Daily bullish breakout / PDL swept / Daily reject
Daily”. The displayed candles show an upward recovery/breakout followed by
pullback/rejection at the marked lower reference. This is a Daily buy-context
claim; it is not proof of universal Weekly alignment. Lower Daily-origin
references and the later H4 reference are drawn separately.

p53 H4 first rises, returns sharply lower with a substantial lower wick toward
the Daily-origin area, then recovers. A later decline/base around0.8660 is
followed by strong upward expansion. It is labelled “H4 breakout with idm /
H4rH4”. The lower Daily reaction and the higher H4 inducement/reaction region
must remain separate in reconstruction; collapsing all lows to the latest
local turn loses the annotated sequence.

p54 H2 supplies the explicit lower entry: **H2 Breakout Confirmation Entry**.
A declining correction/small base precedes the upward body expansion; the
selected grey level is0.86609. The stop0.86544 is below that base and the
teal target0.86975 lies at the higher horizontal reference. Two strong bullish
candles extend through the target, with a wick above0.8715. The picture is a
chart plan plus later price excursion; no accompanying mobile execution or
order-history image establishes an actual fill or realized5.63R result.

Do not recast this annotation as H2 direct merely because entry TF is H2. Its
source label is breakout **confirmation** in H4rH4 context. Distinguishing the
H4-reaction→H2-BO path from the direct-H2 alternative requires the actual
causal bar mapping, including H4 reaction and breakout clocks. No lower
engulfing condition is printed or required by this particular source label.

## Source-rule replay checkpoints

For each checkpoint report source field, independently reconstructed bar IDs,
first availability and match/mismatch/unresolved. No missing field is a pass.

| Checkpoint | p36–37 SELL | p53–54 BUY |
|---|---|---|
| Instrument/feed | EURGBP, FOREXCOM on TradingView panels | EURGBP, FOREXCOM on TradingView panels |
| Story TF/direction | Daily bearish, PDH sweep + Daily reject Daily annotations | Daily bullish, PDL sweep + Daily reject Daily annotations |
| Context causality | Identify Daily reference, swept prior high, closed rejection and related H4 positive bearish BO | Identify Daily reference, swept prior low, closed rejection and related H4 positive bullish BO |
| H4 entry context | BO with inducement and H4rH4; identify distinct liquidity and actual KL reaction | BO with inducement and H4rH4; identify distinct Daily and H4 references and H4 reaction |
| Lower model | H1 engulfing CE; identify new A/OC and actual engulf subtype without imposing both | H2 breakout CE; identify structural close and selected KL |
| Readiness | Each break/engulf's own close, story and reaction prerequisites; personal intrabar H4 reaction permission is separate | Same; explicit direct-H2 H4-BO-close rule must not be applied by assuming all H2 entries are direct |
| Entry/stop/target | 0.86580 /0.86611 /0.86451 | 0.86609 /0.86544 /0.86975 |
| Stop rationale | Source-selected price; relevant higher wick/KL must be independently identified before claiming exact reason | Source-selected price; lower base/zone geometry needs independent derivation |
| Target identity | Lower drawn reference; verify whether entry-TF ERL and which active range | Higher drawn reference; verify active entry-TF ERL independently |
| Fill/outcome | Tool target traversed; phone depicts short entry→exit, exact accounting unresolved | Tool target traversed; no independent execution evidence |

The PDF does not numerically identify FVG boundaries, entry-KL kind, exact
structural reference/bar IDs or full liquidity segmentation for these two
examples. A colored position-box boundary is not independent proof of FVG-edge
protection. Fixed11 is a separate owner experiment and cannot replace the
source stop in fidelity checks. Neither later target traversal nor a snapshot
creation date proves the limit was ready/placed before price touched it.

## Replay readiness conclusion

The six plan prices, direction, entry TF, named lower model, source feed label,
Daily narrative and snapshot-minute UTC conversions have a second direct image
reading. Exact setup/fill UTC, broker/feed alignment and numerical causal KL,
structure/liquidity identities remain unresolved. The current fixture's missing
second-reader reason can be narrowed specifically for the fields confirmed
here, but this note does not authorize promoting the entire case to verified
historical acceptance. Comparing another feed may diagnose a mismatch; it
cannot change these source observations or supply absent FOREXCOM clocks.
