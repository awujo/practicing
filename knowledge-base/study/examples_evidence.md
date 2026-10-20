# Bishop teaching examples: source extraction and replay readiness

Review date: 2026-10-20. Primary source: `knowledge-base/supplementary/source/bishops_trade_chart_examples.pdf` (60 pages). Machine-readable observations: `tests/bishop_examples.json`. This report replaces neither the teacher nor the source with an inferred successful trading system.

## What was actually reviewed

PDF pages 2–6, 8, 10–11, 13, 15, 17, 19–20, 22–23, 25, 27, 29, 31, 33, 35, 37–38, 40, 42, 44, 46–47, 49–50, 52, 54–60 were rendered and visually inspected. Context-only pages outside this list have not been signed off in this extraction. The 38 JSON observations include repeated views, broker orders and stacked entries; they are **not 38 independent trades**. No video example has been promoted from a transcript deictic such as “here” to an exact numeric trade.

The PDF text layer contains mostly instrument headings. Prices come from rendered pictures, not `pdftotext` or the old measurement summary. Scratch renders are reproducible with:

```sh
pdftoppm -f 8 -l 8 -scale-to 2400 -png -singlefile \
  knowledge-base/supplementary/source/bishops_trade_chart_examples.pdf /tmp/bishop-p8
```

Each record preserves pair, timeframe, direction, explicitly labelled prices, source feed, snapshot date and page evidence. An unreadable value remains `null`.

## Full replay is unresolved

Every record currently has `verification: unresolved`. None has passed a historical bot replay. Important missing requirements:

- Exact setup/entry UTC window: snapshot creation dates are visible, but are not order entry timestamps. Chart-axis timezone is not established just by the UTC+1 creation-header timezone. Broker times can use a different timezone.
- Source-aligned candles, symbol and quote-scale mapping, especially FOREXCOM oil prices in the thousands versus broker oil around 80. H1 candles cannot reproduce M30/M45 bar formations reliably.
- A second independent visual reviewer must sign off the extracted prices and stacked-box associations.
- Numerical tolerances have not been justified by measured feed differences or quote precision, so the tolerance fields remain `null`. No arbitrary five-pip or multi-day allowance has been inserted to manufacture a match.
- Several pages do not show a numeric original stop or entry. Page 35 remains a directional/context example with entry/stop/target `null`.

A strict replay gate must report these as **UNRESOLVED**, count them, and refuse a “all examples match” result. It must never skip unresolved observations and return a green empty denominator. Expected prices must not be replaced with the engine's own outputs.

`chart_snapshot_date` records only the date printed in a chart-creation header. For example, AUDUSD p17 was captured July 16 while the depicted entry appears July 15; EURJPY p46 was captured May 27 while the broker arrow appears May 26. These dates must not silently become exact entry dates.

## Corrected values versus the inherited measurement note

These are source-reading corrections made before any engine comparison, not changes made to improve a replay score. Each needs independent second review.

| Page | Instrument / observation | Inherited note | Directly read source label |
|---|---|---|---|
| 2 | EURCAD chart entry | approximately 1.61274 | **1.61278**; broker arrow is a separate observation |
| 3 | EURJPY chart entry / stop / target | approximated 186.35 / ~186.25 / ~186.80 | **186.324 / 186.231 / 186.800** |
| 8 | EURGBP entry | 0.85319 | **0.85315** |
| 10 | USOIL first entry | 8110.7 | **8119.7** |
| 11 | XAUUSD entry / stop | 4128.22 / ~4134.50 | **4125.22 / 4134.59** |
| 23 left | USDCHF target | 0.80525 | **0.80535** |
| 27 | GBPUSD entry | 1.31923 | **1.31932** |
| 38 | US30 entry | 50818.7 | **50816.7** |
| 47 | GBPCAD entry | 1.84766 | **1.84768** |
| 52 | NAS100 stop | 29068.5 | **29060.5** |
| 54 | EURGBP entry | 0.86606 | **0.86609** |
| 58 | JP225 stop | 62613 | **62813** |
| 60 | GBPAUD target | 1.87393 | **1.87390** |

## Preserve demonstrated alternatives

- **EURCHF p5/p6:** chart target **0.93498**, broker pending-order target **0.93704**. Entry **0.93193** and stop **0.93147** agree. These are separate expectations; do not combine the chart's entry/stop with a single claimed universally agreed target. The broker screen explicitly says BUY LIMIT, not proof of a filled order.
- **USOIL p10:** two entries with individual stops and two nearby teal target labels (**8462.1**, **8459.8**). JSON stores a provisional target association, explicitly unresolved pending independent box tracing. Neither box may borrow the other's stop.
- **GBPJPY p19:** two entries (**216.877**, **217.255**) and stops (**216.700**, **217.088**), with target labels **218.014** and **218.007**. Target association requires second review. Do not merge the positions or label them independent setups.
- **XAGUSD p22:** Saxo chart plan entry **59.7269**, stop **60.0626**, TP **58.3773**. Broker SELL line **59.655** and TP **58.534** differ, and no numeric broker original SL is readable. Broker SL remains `null`.
- **USDCHF p23:** two snapshots show the same entry **0.80736**, but stops **0.80783 / 0.80787** and targets **0.80535 / 0.80532**. Treat them as source-demonstrated plan variants, not two independent trades.
- **GBPNZD p31:** chart plan **2.29993 / 2.29842 / 2.30503** differs from broker record open **2.30008**, close **2.30172**, displayed SL **2.30017**, TP **2.30672**. The shown broker SL is above its buy entry and therefore cannot establish its original initial risk. Do not silently substitute it for the chart's initial stop.
- **XAUUSD p11** is credited to `mindguy0x`, not Bishop, and EURGBP p8 explicitly attributes the CE to “4thman”. They are community examples included in Bishop's compilation, not evidence that Bishop personally executed every trade.

## What the pictures establish—and what they do not

The drawn price plans use differing structural risk distances. A fixed 10–11-pip stop and fixed 3R target cannot reproduce all these original price plans. Teacher-example replay must use the demonstrated model; aggressive user-default experiments must be reported separately rather than changing source expectations.

Pink/red and teal are **TradingView position-tool risk and reward boxes**. Their near/far edges equal the drawn entry/stop/target by construction. The apparent invariant “stop at the far edge of the pink zone” is therefore **not independent proof** that the box is an FVG or that every original stop was calculated from an imbalance boundary. To establish an FVG stop rule, inspect the underlying candles, identify the gap without reference to the position box, and check the actual gap boundary against the labelled stop. The inherited measurement note's broad “zero exceptions” conclusion goes beyond what price-box geometry alone demonstrates.

Similarly, chart arrows and retrospective annotations do not automatically prove live fills, profits, or a profitable strategy. Fixture assertions should cover only what the source actually shows.

## Native-video observations added (40 total source observations)

Two additional entries-part-5 snapshots were independently extracted from the original MP4 at **native source PTS**, not trusted from the contact sheet's burned timestamp. `ffprobe` reports stream/format start0; `ffmpeg -copyts -ss 1065/1410 ... -vf showinfo` reports exact `pts_time:1065` and `pts_time:1410`. Native PNGs and MP4 SHA256 references are retained in the JSON/evidence directory.

| Source PTS | Chart | Entry | Stop | Target | Source limits |
|---|---|---:|---:|---:|---|
| 1065 | XAUUSD H3 Saxo | 4079.56 | 4064.31 | 4165.88 | Tool RR5.66, risk15.25. Teacher changes the tool during explanation; this is one exact observed stage, not proof of actual filled trade. |
| 1410 | EURUSD H2 FOREXCOM | 1.15330 | 1.15280 | 1.15589 | Transcript1403–1418: “personally I would have done something like this”, aim about5R; explicitly an illustrative placement. |

At native1395 the EURUSD teacher is actively dragging the stop: the visible stop is **1.14920**, RR**0.63**, with target offscreen. A nearby contact-sheet tile or a transient tool value must not be mistaken for the final1410 plan. Likewise, another XAUUSD target seen at a different video stage must not be merged into the native1065 H3 plan. The source time at which a drawing is shown is not the historical time at which its trade would become observable.

All40 observations remain full-replay **UNRESOLVED**. `bias`, `setup_time`, actual UTC `time`, and numerical tolerances stay null pending proper source/candle alignment. `mode:teacher_source_stop` states only that the source's own stop is preserved; it asserts no universal FVG-stop rule. `source_execution_status` distinguishes plans, the explicitly pending EURCHF broker order, and the XAGUSD open-position screenshot; `execution_status` remains unresolved for engine acceptance.

The root reviewer independently opened PDFp8 and agreed **EURGBP entry0.85315 / stop0.85289 / target0.85447**. That second check covers only those three numeric labels. It does not sign off time, bias, FVG or replay correctness.

The root reviewer also opened the retained native1410 PNG and confirmed the
EURUSD2h FOREXCOM labels **entry1.15330 / stop1.15280 / target1.15589**. This is
a second numeric-label check only; it does not establish a historical fill.
