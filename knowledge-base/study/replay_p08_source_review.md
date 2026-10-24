# Independent source review: PDF p7–8 EURGBP

2026-10-23. Read-only teacher-example reconstruction after replay was authorized. No fixture, detector, expected price, tolerance or execution record was changed. This review independently inspects the actual PDF images; it does not establish an exact historical detector match.

## Primary evidence actually inspected

Source: `knowledge-base/supplementary/source/bishops_trade_chart_examples.pdf`, SHA256 `e6393b2e35cf79e3b3f8b63095cce9224ded8487f845e3dd29172730288c2729`. Rendered p7 to `/tmp/bishop-p07.png` (2200-pixel maximum dimension) and p8 to `/tmp/bishop-p08.png` (3000-pixel maximum dimension), then visually inspected both complete images. Temporary renders are conveniences; PDF pages and hash are the durable evidence references.

Crosschecked `tests/bishop_example_alignment.json` case `pdf-p08-eurgbp-buy-1`, `tests/bishop_examples.json` same ID, `full_supplement_study.md` p7–8 review and candle narrative, `full_study_verification.md` §5, `full_primary_crosscheck.md` item7, and `full_session_study.md` confirmation-shape rules18–24. Those ledgers corroborate the following limits; they are not substitutes for the page inspection.

## Directly verified facts

| Field | Independent source observation | Scope of verification |
|---|---|---|
| Instrument/feed | EURGBP, FOREXCOM on both pages | Printed chart identity |
| Context | p7 left chart is Daily, explicitly labelled `Daily bullish BOS`; p7 right H4 also carries `Daily bullish BOS` | BUY/D context annotation is directly established; precise causal candle availability is not |
| H4 sequence | Initial `H4 breakout` annotation, then later `H4 breakout with idm / H4RH4`; later label points to lower-wick/reaction region | Distinct labelled stages; not a numerical definition of all structural references |
| Entry view | p8 explicitly `EURGBP · 2h · FOREXCOM` | H2 source chart |
| Named CE | `H2 High swept, Low standing / V-shaped kl / 4thman's CE` | Literal source wording and attribution, not independently numbered candle mapping |
| Direction | Long position drawing: reward above entry, risk below | BUY illustration, despite the phrase “High swept” |
| Entry | 0.85315 | Printed gray entry label; not 0.85319 |
| Stop | 0.85289 | Printed red risk boundary |
| Target | 0.85447 | Printed green target boundary |
| p8 header | `Jul 23, 2026 19:08 UTC+1` | Snapshot creation minute, not setup/placement/fill |
| Execution | Chart and drawn position tool only on these pages | No broker order ticket, fill confirmation, realized exit or participation proof |

Printed plan risk is 0.00026 (2.6 conventional EURGBP pips); reward is 0.00132 (13.2 pips), approximately 5.08R as arithmetic on the displayed plan. This is not an independently realized return, a universal RR rule or an 11-pip-stop example. The underlying structural/FVG rationale for the stop is not proved by its position-tool edge.

## Source sequence that can be reconstructed

1. Daily chart shows a sharp decline followed by a recovery; the author's marked body-level reference is labelled Daily bullish BOS. This is the source's BUY context. The page does **not** explicitly label a new `Daily reject Daily` event, Weekly alignment, or a Weekly-origin story. Those must not be added merely because other examples use that checklist.
2. H4 view shows an initial bullish expansion/breakout, an intervening pullback, and a renewed bullish move. The initial breakout and later with-idm/H4RH4 are labelled separately. The second annotation's leader attaches to a lower-wick reference in the pullback/reaction region; it is not permission to substitute an arbitrary local turn.
3. H2 view preserves those H4 context annotations. It shows an initial upward leg, descending candles into the body junction around the displayed entry, then rising candles, including a large later upward candle. The CE annotation identifies a V-shaped KL and explicitly describes a high as swept while a low remains standing.
4. The long tool is placed at 0.85315 with the stop/target above. A later visible upper wick extends above the target line. This is visible price excursion on the source chart, not proof that an issued order filled and its TP realized.

The p8 label leader identifies the entry region, but the exact two reference candles are not numbered. A plausible geometric interpretation is a later rising H2 candle taking the preceding rising candle's high while leaving its low intact, with the entry using the earlier trough/body junction. This would explain why “High swept, Low standing” can accompany a BUY. It is **a candidate interpretation**, not a certified algorithm or extraction. It must not be converted into an unconditional sell mirror, or into a standard engulf merely because an engulf might appear on another TF.

The page does not prove whether “swept” here means a wick excursion followed by close back inside, a taken high generally, or a reference earlier in the larger sequence. The session E5/RS low-swept/high-standing V-buy teaching has a different literal swept-side label. Exact reference identity and author terminology remain the open mapping, not an established contradiction resolved by invention.

## Four different clocks

- **Snapshot:** p8's printed minute corresponds to 2026-07-23 18:08–18:09 UTC. This conversion agrees with the alignment JSON. p7's separate chart snapshots are printed 19:04 and 19:06 UTC+1. These are image creation clocks only.
- **Pattern occurrence:** chart geometry gives relative order (rise, pullback, lower reaction region, later rise). Axis date/hour labels do not uniquely establish which specific candle the author considered the CE or when its required facts occurred intrabar.
- **Setup availability/order placement:** unknown. Neither the tool's left boundary nor its header proves when the setup was first eligible, whether the author acted before H2 close, or whether a limit was actually issued.
- **Fill/exit:** unknown. Price crossing a drawn entry or target does not establish order existence, bid/ask fill, fill ordering relative to confirmation, or realized result.

A lower wick in the setup vicinity appears below the displayed stop boundary. That fact alone cannot classify this plan as a stopped trade: the wick may precede setup availability or placement. Conversely, later favorable excursion cannot classify it as a win. The unknown clocks matter in both directions.

## Existing alternate-feed chronology: useful diagnostic, not source proof

The alignment record openly identifies its data as IC Markets cTrader BID H1, not source FOREXCOM. Its eight H2 aggregates from July23 are a **candidate alternate-feed chronology** under a declared aggregation clock. The relevant numerical sequence listed there includes bearish 09:00–11:00 UTC, bullish 11:00–13:00, further bullish 13:00–15:00, then the large 15:00–17:00 rise. Those timestamps are facts about that diagnostic record, not independently reconstructed source setup/fill timestamps.

In that alternate sequence, the 13:00–15:00 candle exceeds the preceding candle's high (0.85383 versus 0.85335) and leaves its low standing (0.85288 versus 0.85284). This is compatible with the candidate high-taken/low-standing interpretation above, but cross-feed resemblance cannot certify which source candles the annotation names. The source drawing's entry remains 0.85315. Alternate prior-close/open 0.85313/0.85311 differ by 0.2pip and do not justify changing that source price or widening a tolerance.

The H1 coverage diagnostic reports all 48 hourly rows for its July22–24 window. That does not establish source H2 candle alignment, tick/M30 coverage, spread, or intrabar confirmation-versus-touch order. It cannot turn a possible H2 confirmation into a known fill time. No source-price tolerance can be selected from whichever difference makes the replay pass.

## Replay disposition and actionable evidence gaps

**Independent source-label check: verified. Exact teacher replay acceptance: unresolved.** This review independently agrees on identity, BUY direction, H2 entry view, printed prices, Daily BUY annotation and the named H4/H2 stages. It does not promote the fixture or replace its missing fields. In particular, `tests/bishop_examples.json` still has `bias: null`; p7 establishes a Daily BUY annotation, while its exact causal availability remains unresolved as the alignment file already states.

A detector diagnostic can truthfully report whether its declared policy/alternate feed reproduces a compatible D→H4→H2 sequence and how its chosen references differ. It cannot claim a full source match unless the following are resolved:

1. Source FOREXCOM candle data with explicit chart timezone/anchor, or independently verified source OHLC and candle identities for the marked sequence.
2. Numbered CE reference-candle mapping and whether the relevant high passage is a strict wick sweep, a body break, or a different earlier reference.
3. Earliest source setup availability and whether this route permits/uses intrabar entry in this case; ordered finer observations if confirmation and entry touch occupy one candle.
4. Actual order existence/type and fill/exit evidence, or a source classification that remains illustrative plan rather than executed trade.
5. Stop rationale and target reference if evaluating structural-risk/ERL model fidelity beyond the three displayed numerical coordinates.

No newly invented `fourth_man` algorithm, absence of one named route, or broad assertion that “the feed caused zero setups” is established by this review. Any failure should be attributed to a demonstrated detector predicate/data limitation, with unresolved source mapping kept explicit.
