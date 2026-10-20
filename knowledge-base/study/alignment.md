# Historical example alignment: first frozen chronology

2026-10-20. This work aligns source illustrations with alternate-feed candles.
It is **not a historical replay PASS** and does not promote any of the forty
source observations. Expected prices, statuses and tolerances are unchanged.

Machine-readable diagnostics: `tests/bishop_example_alignment.json`.

## EURGBP PDF pages 7–8

Directly inspected the source PDF and rendered pages 7 and 8.

| Source fact | Evidence | Interpretation |
|---|---|---|
| EURGBP, FOREXCOM, H2 | p8 chart title | This is not the IC Markets feed. |
| Entry 0.85315, stop 0.85289, target 0.85447 | p8 axis labels | Preserve these exact source observations. |
| Daily BUY context | p7 explicitly says “Daily bullish BOS” on Daily and H4 views | A directly observed directional annotation, not an inferred exact event time. |
| H4 breakout and H4 breakout with inducement | p7/p8 annotations | Source sequence context; exact eligibility timestamps remain to be reconstructed. |
| “H2 High swept, Low standing / V-shaped kl / 4thman's CE” | p8 | The named CE is not mathematically defined by this picture alone. |
| Created Jul 23 2026, 19:08 UTC+1 | p8 header | Snapshot minute is 18:08 UTC. It is not entry/fill time. |

The p7 Daily chart appears to show a previously completed Daily candle while
the H4/H2 views extend later. Do not assume every chart's final visible candle
belongs to the same completed clock, or turn an annotation into an event time.

### Frozen alternate feed

The existing public Kevin-branch export supplies a useful reproducible alternate
input without broker authentication or token refresh:

- Repository commit: `7bccddd65f7e22a0c31430ff668b36cb7c512f2e`.
- Original path: `data/examples/EURGBP_H1.csv.gz`.
- Original SHA256:
  `257ea6b66bd6c9fc46f421abe358ea792ae50319a38a900d1c4d7b49402fcad6`.
- Provenance: existing IC Markets cTrader BID H1 export; timestamps are UTC hour
  starts. The original export uses `float_format=%.6g`; it is not a full-precision
  broker tick archive.
- Frozen subset: `data/examples/EURGBP_pdf_p08_icmarkets_bid_H1.csv.gz`.
- Subset SHA256:
  `815f153eccb7ac981c06850bab82a5cd39dd41146810497f7b115d0839d559b0`.
- 3,624 H1 bars, Jan 1 2026 22:00 UTC through Jul 31 20:00 UTC.
- Metadata: `data/examples/EURGBP_pdf_p08_icmarkets_bid_H1.meta.json`.
- July 22–23 diagnostic window has all 48 expected UTC hourly starts. This
  narrow completeness check does not certify all warmup history, ticks, M30,
  spread, or exact source-feed compatibility.

The `data/` paths are ignored by Git at this stage. The parent must explicitly
decide whether to retain the public frozen subset in the repository.

### Closed-candle chronology

Using the inherited New York 17:00 session clock, these IC Markets H2 bars are
available by the **snapshot diagnostic clock** Jul 23 18:08 UTC:

| H2 start UTC | End/availability UTC | Open | High | Low | Close |
|---|---|---:|---:|---:|---:|
| Jul 23 07:00 | 09:00 | 0.85408 | 0.85442 | 0.85345 | 0.85353 |
| Jul 23 09:00 | 11:00 | 0.85354 | 0.85370 | 0.85298 | 0.85313 |
| Jul 23 11:00 | 13:00 | 0.85311 | 0.85335 | 0.85284 | 0.85327 |
| Jul 23 13:00 | 15:00 | 0.85328 | 0.85383 | 0.85288 | 0.85371 |
| Jul 23 15:00 | 17:00 | 0.85370 | 0.85467 | 0.85367 | 0.85411 |

The H2 bar starting 17:00 ends 19:00 and is **still forming at 18:08**. Its
completed high/low/close cannot be used to explain a signal supposedly available
at the snapshot clock. A source image can show a forming candle without making
its eventual close available to a bot.

This sequence resembles the source's dip and subsequent expansion, but it does
not settle the actual CE, order type, pending time or fill. A position-tool box
can illustrate a plan without an executed order. Do not claim a win from this
table or reconstruct intrabar stop/target ordering from H1 bars.

The alternate H2 close at 11:00 is **0.85313** and the next H2 open is
**0.85311**, a 0.2-pip gap. The source entry is 0.85315. Therefore:

1. Exact equality between the alternate close and next open would exclude this
   nearby key-level candidate under the first primitive's conservative policy.
2. That is evidence to review the detector's junction definition on real feeds,
   **not permission to widen teaching-example tolerances**.
3. A source-label difference across two feeds is not automatically an engine
   bug. Source geometry and feed compatibility must be checked separately.

Reproduce the timing diagnostic locally:

```python
import pandas as pd
from bishop.candles import completed

h1 = pd.read_csv("data/examples/EURGBP_pdf_p08_icmarkets_bid_H1.csv.gz",
                 index_col=0, parse_dates=True)
bars = completed(h1, "H2", pd.Timestamp("2026-07-23T18:08:00Z"))
print(bars[bars.start >= "2026-07-23T07:00:00Z"])
```

## EURUSD native video PTS 1410

Independently opened the retained native image. It shows EURUSD H2 FOREXCOM,
chart timezone UTC+1, source entry **1.15330**, stop **1.15280**, target
**1.15589**. These are the same preserved observations in the main fixture.

The prior source reader reported the position-tool left anchor as Wed Aug 5
2026 06:00 chart time (05:00 UTC); the native1410 x-axis geometry is consistent
with that. This is a **drawing anchor candidate**, not the time when an order
was eligible or filled. The transcript expressly says “personally I would have
done something like this.” No fill claim follows from this retrospective plan.

There is no local EURUSD export among Kevin's eight example-pair candle files.
Historical EURUSD alignment remains blocked by acquisition and source geometry.

## Public Dukascopy acquisition result

Direct requests through the inherited network configuration returned HTTP 503:

- `https://datafeed.dukascopy.com/datafeed/EURUSD/2026/07/BID_candles_hour_1.bi5`
  (August, zero-based month 07).
- `https://datafeed.dukascopy.com/datafeed/EURGBP/2026/06/BID_candles_hour_1.bi5`
  (July, zero-based month 06).
- A 2025 baseline monthly URL and EURUSD Aug 5 minute-file URL also returned 503.

The `www.dukascopy.com` variant initially returned HTTP200/6009 bytes, but that
response was **not validated as LZMA candle data**; subsequent requests followed
redirects and returned HTTP429. It is not an accepted alternative data endpoint.
No returned webpage or unvalidated response was written as a candle archive.
No broker credentials, account refresh, network-policy bypass or proxy changes
were used. The acquisition failure is recorded separately from strategy mismatch.

## Remaining acceptance requirements

Preserve the Daily BUY annotation as source evidence, but keep the full case
unresolved until the exact source/model sequence, setup availability, execution
state, event clock and independently justified source-feed measurement bounds
are established. A matching price path alone cannot establish all of these.
