# Offline engine milestone — 2026-10-20

The partial causal engine now runs frozen candles through bias, setup detection,
pending orders and bid/ask execution. It is not complete Bishop replication.
All **40 teacher observations remain UNRESOLVED**; no teacher match is claimed.

Reproduce offline from repository root:

```sh
python -m reports.reproduce_initial_study
python -m pytest -q
```

The frozen EURGBP input is IC Markets BID, not the FOREXCOM teaching feed.
Input SHA256: `815f153eccb7ac981c06850bab82a5cd39dd41146810497f7b115d0839d559b0`.
Provenance accompanies the data under `data/examples/`.

Eight predeclared combinations compare H1/H2 entries, exact-junction/first-close
levels and structural/fixed-11-pip stops. These are engineering alternatives,
not selected profitable operating settings. All use a 1-pip spread, 0.2-pip
stop slippage, 0.5-pip round-trip commission and 24-hour pending expiry.

| June 1–July 24, 2026 | Stories | Setups | Observed fills |
|---|---:|---:|---:|
| Exact junction, either entry timeframe/stop | 12 | 0 | 0 |
| First close, H1, either stop | 25 | 67 | 56 |
| First close, H2, either stop | 25 | 38 | 28 |

Alternatives are unranked and may overlap; these counts are not portfolio
trades or performance. Individual runs took roughly 0.06–0.28 seconds here.
The selected July 22–24 H2 source window produces **zero setups**. The source
example is identified as fourth-man CE, which this engine does not implement;
its exact setup/fill clocks and feed alignment also remain unresolved. We
have not altered source expectations or widened tolerances.

Supported entry routes are engulf-retest and OC-break-retest. Local close-turn
structure and origin-timeframe KL targets are explicit provisional policies;
major-swing certification, ERL targets, reused/role-flipped origins, full story
lifecycle, fourth-man/aggressive imbalance entries and finer entry routes
remain open. Fixed-pip and structural-wick stops are explicit experiments;
structural-wick is not a claim of source imbalance-zone-edge geometry.

Coverage gaps block the runner; incomplete leading aggregates are excluded.
Missing active execution hours and ambiguous fill-bar ordering are censored.
Source replay checks preserve pending-order activity intervals, so later
terminal statuses cannot hide an order issued during a no-trade example.

Independent reviewers found and verified fixes for reference causality,
partial aggregates and false no-trade acceptance. Final validation: **204
passed**. See `reference/FINAL_ENGINE_REVIEW.md`. No paper runner, live alerts
or broker execution has been enabled by this milestone.
