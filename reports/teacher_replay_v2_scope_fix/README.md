# Protection and continuity replay checkpoint

All ten source-confirmation diagnostics completed. None establishes an exact teacher match. The original 40-record acceptance gate remains unresolved; source fixtures are unchanged. These alternate-feed diagnostics do not establish teacher execution times or profitability.

| Example | Setups before → after | Orders before → after |
|---|---:|---:|
| pdf-p08-eurgbp-buy-1 | 796 → 637 | 26 → 16 |
| pdf-p15-usdcad-sell-1 | 1508 → 0 | 27 → 0 |
| pdf-p19-gbpjpy-buy-1 | 1352 → 1775 | 17 → 16 |
| pdf-p19-gbpjpy-buy-2 | 1352 → 1775 | 17 → 16 |
| pdf-p23-usdchf-sell-1 | 1291 → 301 | 22 → 10 |
| pdf-p23-usdchf-sell-2 | 845 → 155 | 16 → 9 |
| pdf-p35-gbpjpy-buy-1 | 1503 → 1144 | 13 → 16 |
| pdf-p37-eurgbp-sell-1 | 860 → 799 | 13 → 12 |
| pdf-p54-eurgbp-buy-1 | 1255 → 295 | 14 → 18 |
| pdf-p60-gbpaud-sell-1 | 0 → 0 | 0 → 0 |

Changes restrict protection to causal entry-episode evidence, retire consumed pools and obsolete reactions, and invalidate inference across missing observations. Smaller candidate counts are not proof of improved fidelity. In particular, USDCAD now has no candidate; its first blocking condition requires source review. p08 still has the previously diagnosed stop mismatch.

Reports retain their original implementation fingerprint `c5adadf2120cc10b84ab0f68c8ef72c7e7dd3fd30b7f5de3c7237073d4a19613`. A subsequent engine guard rejects nonmonotone candle publication; these synchronous frozen feeds are unaffected. Full receipt-order replay is not implemented. Do not describe this guard as support for late-arriving internal candles.

Validation: 252 tests passed. Report hashes and the original source fixture hash are checked separately below.
