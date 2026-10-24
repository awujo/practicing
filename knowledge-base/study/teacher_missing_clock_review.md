# Missing teacher clocks: supplemental source review

2026-10-24. Offline source review of four observations only. Original fixtures
are unchanged. `reports/teacher_clock_annotations.json` records machine-readable
findings; it is supplemental evidence, not a promoted acceptance fixture.

Inspected full-resolution retained PDF renders of pages 5, 6, 21 and 22, and
both repository native video frames at actual PTS1065/1410. Read relevant
canonical transcript passages around 1054–1085 and 1362–1430 seconds. No market
data matching, network acquisition, full-video rewatch or actual-fill clock
verification was performed. The PDF source SHA256 is
`e6393b2e35cf79e3b3f8b63095cce9224ded8487f845e3dd29172730288c2729`.
The native-frame/video identities are retained in the supplemental JSON.

| Observation | Directly visible clock evidence | What remains uncertain |
|---|---|---|
| `pdf-p06-eurchf-buy-1` | PDFp6 broker M30 axis explicitly shows 28 Jul and 29 Jul; phone reads 8:58. Pending BUY LIMIT0.91 remains displayed. PDFp5 adjacent EURCHF FOREXCOM M30 chart header explicitly says Jul29,2026 08:59 UTC+1 (=07:59Z); entry .93193 and stop .93147 coincide with p6, as does nearby candle geometry. | Page6 has no independently visible year, broker timezone, screenshot date or order placement time. Page5 strongly suggests a paired July2026 example, but document adjacency and equal prices do not certify simultaneous clocks or a fill. In particular the differing target (.93498 chart vs .93704 broker) must not be collapsed. |
| `pdf-p22-xagusd-sell-2` | Right-hand broker H2 screenshot shows 9 Jul and 10 Jul on axis, phone23:27, open SELL0.06 at59.655 and TP58.534. Left-hand Saxo H2 chart on the same page is explicitly created Jul13,2026 06:24 UTC+1 (=05:24Z). Page21 D/H4 companion charts say Jul13,2026 06:23 UTC+1. | Broker screenshot itself lacks year/timezone and may predate the paired chart snapshot. Its visible Jul9–10 bars are not a July13 fill. A July2026 broker date is a paired-document hypothesis, not a verified UTC date. The broker SL is still unreadable; chart SL must not fill that missing fact. |
| `video-entries5-native-t1065-xauusd` | Native PTS1065 is Saxo3h. Selected drawing's left anchor tooltip explicitly reads Wed05Aug'26 02:00; right anchor Fri07Aug'26 11:00; bottom-right chart offset UTC+1. Thus drawing coordinates convert to Aug5 01:00Z and Aug7 10:00Z. | These are position-tool coordinates, not candle eligibility, placement, fill or exit. The visible market chronology is August2026; screenshot/recording date is not given by those coordinates. Transcript1054–1085 says “if you took,” “would have,” then adjusts potential R and stop. This is hypothetical geometry, not an executed return or verified fill. |
| `video-entries5-native-t1410-eurusd` | Native PTS1410 is FOREXCOM2h. Bottom crosshair tooltip explicitly reads Tue04Aug'26 12:00, with chart UTC+1 (11:00Z). The drawn box lies around axis Aug5–6; the visible wider chart runs lateJuly into Aug9. | The crosshair is left of the box and is not its entry anchor. Do not assign Aug4 11:00Z as entry. Exact box-left time is not selected/readable. Transcript1403–1418 repeatedly says personally “I would have” placed it and aimed for5R. Chart year/month are established; exact setup/fill and original executed model remain unknown. |

For the native EURUSD case, an exploratory search around Aug3–8,2026 UTC is
justified by the explicit dated chart axis and nearby illustrated candles. It
is deliberately wider than the apparent Aug5–6 drawing to avoid pretending a
pixel-to-time estimate is a verified anchor. A collection range June1–Aug11
provides a declared warmup/aftermath choice; the extra history is engineering
scope, not source clock evidence. Native XAUUSD can use the same collection
range, with Aug4–8 as an exploratory event-search window anchored by the actual
Aug5 drawing coordinate.

For PDFp6 and p22 broker observations, proposed July2026 collection windows
are conditional on paired-document year attribution. They must be labelled
exploratory, retain null verified setup/fill dates, and never make a source
match pass solely because collected candles happen to resemble the picture.
Unknown broker offset is another reason to pad the search rather than assert
an exact UTC candle. No finite verified UTC fill interval follows from these
four images. Even a dated screenshot could establish only an observation time,
not the placement/fill of an already pending/open order.

Review result: the two native observations now have directly verified chart
calendar year/month and dated reference coordinates; the two PDF broker
observations have direct month/day evidence plus explicitly conditional paired
2026 context. All four still have unresolved setup/fill clocks. No source
execution status, prices, stops, targets, model or tolerance was changed.
