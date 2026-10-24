# First-take → later reaction correction

Policy3 fixes the USDCAD suppression regression: the original observable H4 liquidity take can sponsor a later related KL rejection in the same valid episode. It does not need to sweep the same pool again. Role loss/unavailability, broken/replaced episodes, gaps and first takes from older episodes prevent reuse. Normal and nested confirmations use the same rule.

First-take observations are recorded independently of future reactions, preserving event prefixes; `liquidity_take_events` and setup evidence carry pool/bar/receipt provenance. Source fixtures, prices and tolerances are unchanged.

All ten source-confirmation diagnostics completed with implementation fingerprint `3db7c1cdc1cc680767361c1803373736540cac92c2a4ff4ce443bc6608549f41`. Every strict result remains UNRESOLVED. The original40record teacher acceptance gate remains unresolved, including30records without local matching-pair inputs. p60 remains M45-resolution unsupported; p35 lacks a printed numeric plan. Alternate-feed and source-clock limitations still apply.

| Example | Scope-fix setups → corrected | Orders before → after |
|---|---:|---:|
| pdf-p08-eurgbp-buy-1 | 637 → 576 | 16 → 29 |
| pdf-p37-eurgbp-sell-1 | 799 → 1130 | 12 → 14 |
| pdf-p54-eurgbp-buy-1 | 295 → 1127 | 18 → 18 |
| pdf-p15-usdcad-sell-1 | 0 → 312 | 0 → 7 |
| pdf-p19-gbpjpy-buy-1 | 1775 → 1737 | 16 → 24 |
| pdf-p19-gbpjpy-buy-2 | 1775 → 1737 | 16 → 24 |
| pdf-p23-usdchf-sell-1 | 301 → 504 | 10 → 20 |
| pdf-p23-usdchf-sell-2 | 155 → 364 | 9 → 15 |
| pdf-p35-gbpjpy-buy-1 | 1144 → 1458 | 16 → 19 |
| pdf-p60-gbpaud-sell-1 | 0 → 0 | 0 → 0 |

USDCAD:312setups and7selected orders restored from zero. The original07:00UTC H1 breakout candidate is1.40425/1.40521/1.40249 versus source1.40471/1.40539/1.40129. All24story aliases at that clock link to the original01:00–02:00UTC take bar, available before setup. This verifies the regression correction and provenance, not source association or matching geometry. Protective origin across the full multi-candle excursion remains a source-fidelity question.

Validation:265tests passed in6.05s, including13independent first-take causality/provenance checks. All ten report byte hashes, identical implementation fingerprints and unchanged source fixture hash verified. No live orders, deployment or messaging.
