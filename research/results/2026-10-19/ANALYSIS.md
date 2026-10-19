# First 28-pair research review — 19 October 2026

The queue and publication completed for all 28 pairs. The research found **unfavourable next-day directional behaviour in this window**, particularly among numerous continuation events. It did **not** establish a superior replacement rule, a profitable entry variant, or that the live strategy as a whole is unprofitable. No live strategy settings were changed.

## What was actually studied

- Seven successful batches; all pairs completed on their first attempt. Source: IC Markets cTrader H1 bid candles.
- About 1,200 calendar days of input per pair, but **only the latest 21 calendar days were evaluated**, approximately 28 September–19 October 2026. Earlier data built the historical context; it was not a multi-year performance test.
- First batch evaluation ended at 12:00 UTC; later batches at 13:00 UTC. This explains 90 versus 91 H4 observation points per pair. Total: 2,544 observation points.
- Only Daily storylines, with Weekly/Monthly context, observed at completed H4 boundaries. Code-default configuration, including monthly context, rather than the owner's current database settings. This is engine event eligibility, not an exact replay of Telegram alerts, standing-bias filters, hourly delivery, or the user's live account performance.
- Full reports and SQLite ledgers for every pair were inspected and aggregated. Two code hashes occur because the queue module was added after batch one; the research/entry engine was unchanged between these batch commits.

## Event inventory and repeated-story concentration

| Event type | Recorded events |
|---|---:|
| Continuation | 599 |
| Tapped | 99 |
| External break awaiting origin confirmation | 50 |
| Confirmed | 33 |
| Target hit | 17 |
| Invalidated | 14 |
| Story line ended | 12 |
| Ended by flip | 4 |
| **Total** | **828** |

These are lifecycle records, **not 828 trades or independent signals**. Many are excluded by the existing no-trade eligibility rules. For example, 290 of the 599 continuation records carried a no-trade flag. A target-hit count cannot be divided by confirmation count to estimate success: some stories existed before the evaluation began, while some new stories remained unresolved afterward.

The baseline accepted 327 confirmation/continuation event records. Of these, 278 had complete 24-hour outcomes; 49 were censored because their future window was incomplete or missing expected hours. Removing duplicate pair/time/direction observations left **200 units**, representing **32 storylines at 58 distinct observation times**. These still overlap in time and share currencies; they are not 200 independent experiments.

For a disjoint descriptive breakdown, duplicate stories at a given pair/time/side were represented by the most recently confirmed story, then latest tap, with stable ID as a tie break:

| Canonical signal group | Units | Mean signed next-24h movement |
|---|---:|---:|
| Initial confirmation | 15 | −0.79 |
| Continuation before target | 31 | −2.32 |
| Continuation after target | 154 | −1.50 |
| **All baseline units** | **200** | **−1.58** |

**77% came after the target.** This supports studying whether old stories generate excessive alerts and whether a new structural condition should be required. It does not prove that every post-target continuation is wrong. The 154-unit result uses the canonical story per signal unit; independently filtering a cohort before deduplication produces different counts because multiple stories can describe the same candle.

Median storyline age among these units was **512 hours (21.3 calendar days)**; maximum was 1,324 hours (55.2 days). Sixty-one units were at most ten days old and 139 were older. Calendar age includes weekends.

## Directional outcomes and the five alternatives

The unit below is **one trailing average H1 high–low range**, computed from the preceding 24 available H1 candles. Positive means the next 24-hour closing price moved in the signalled direction; negative means against it. This is **not pips, percent, trade R, account return or a win rate**. It ignores where an actual entry, stop or target would execute.

| Policy | Distinct completed units | Mean | Median | Positive direction |
|---|---:|---:|---:|---:|
| Keep eligible confirmations/continuations | 200 | -1.58 | -0.93 | 74/200 |
| Stop accepting signals after target | 46 | -1.82 | -1.25 | 17/46 |
| Only latest eligible fresh story before target | 46 | -1.82 | -1.25 | 17/46 |
| Story age at most ten days | 61 | -1.51 | -1.49 | 21/61 |
| After target, require close margin ≥0.5 H1 range | 122 | -1.89 | -1.39 | 42/122 |

Every tested policy had a negative descriptive mean in this sample. The ten-day filter was only slightly less negative and retained a different, much smaller population; this does not establish improvement. The close-margin filter was more negative. Fresh-story and retire-at-target policies produced the same scored observations here, so this study could not distinguish their benefits.

The baseline ended in the intended direction in **74/200 observations (37%)**. This is a directional endpoint fraction, not trade win rate. Average favourable excursion was 2.53 range units and adverse excursion 3.84. Both movements can occur on the same path; these averages do not specify their order or a tradable exit.

Eighteen pairs had negative baseline means, three positive, and seven had no eligible complete baseline observations. The positive pairs were EURUSD, NZDCHF and USDCAD; their small samples do not justify selecting them for trading or excluding the others.

A large shared adverse move matters: the 27 units observed on 14 October averaged −6.32. Excluding those observations leaves the other 173 at **−0.83**, still negative. This is a retrospective sensitivity check, not a validated rule to avoid a date or market regime. Many currency pairs share exposure, so adding pairs did not add independent market regimes.

The canonical younger-story group averaged −1.51 versus −1.61 for older stories. Both were negative, and the difference does not support a firm age cutoff. Origin-timeframe agreement also failed to show a compelling descriptive improvement; subgroup observations overlap across stories, so they must not be added together as independent evidence.

## Entry timeframe results

Only **18 eligible new confirmations** entered the experimental entry study. Each was evaluated against four variants, giving **72 trials**, not 72 trades. Thirteen pairs had no eligible new confirmation in the window. The per-pair cap of 12 confirmations did not truncate any pair in this run.

| Entry variant | Trials | Closed trades | Wins / losses | Mean closed-trade R |
|---|---:|---:|---:|---:|
| H1 zone | 18 | 6 | 1 / 5 | −0.679R |
| H1 rejection stop | 18 | 6 | 1 / 5 | −0.662R |
| H2 zone | 18 | 0 | — | — |
| H4 zone | 18 | 0 | — | — |

The same six confirmation cases generated the two sets of H1 closed trades; those are alternative executions, not twelve independent opportunities. The closed cases were AUDJPY, GBPCHF, EURCHF twice, USDJPY and AUDCHF. AUDCHF was positive; the other five cases stopped out. H1 rejection's small numerical advantage is insufficient to prefer it.

For **each H1 variant**, the other trials were eight without an observable pending setup inside 24 hours, two cancelled before a setup, one cancelled before a fill, and one censored. H2 had twelve without a setup, four cancelled before a setup, and two unfilled orders. H4 had fourteen without a setup and four cancelled before a setup. Zero closed H2/H4 trades means **no execution evidence**, not superior risk control or zero expected return.

**Four of the five H1 stopouts in each variant were ambiguous hourly bars:** both stop and target were within the candle's price range. The simulator deliberately counts a stop first and does not award target profit on the fill candle. Actual event order cannot be resolved with H1 candles. These results justify lower-timeframe verification; they do not prove the stop should be widened, the market reversed after the stop, or those trades would have won.

Assumptions: fixed one-pip spread, 0.2-pip slippage, zero commission; pending window 24 real hours, holding window 24 hours after fill. Real spread changes and commissions are absent. Stops can lose more than 1R due to slippage. Entry alignment is explicitly disabled in this research variant. There is no portfolio sizing, exposure limit, drawdown or live profitability result.

## Discovery and statistical limits

**All 28 pairs remained insufficient_data** under the predeclared development/later-period screening. Development baseline counts ranged from 0 to 11 per pair, below the required 30 per period. They summed to 123 across pairs, but pooling correlated markets cannot make the per-pair criterion pass or create independent examples. No group was selected, and no selected group's later-period validation was produced. The threshold of 30 itself is a guardrail, not proof of adequate statistical power.

The broad alternatives and all-window summaries above are exploratory descriptions. The full window has now been inspected, so it must not later be presented as an untouched confirmatory holdout for rules chosen from these findings. No ANN was trained.

## Data quality and comparability

All pair replays completed rather than stopping for recent missing hours. Historical expected-hour gap diagnostics reported 148 hours for 27 pairs and 195 for EURCAD, across the long input history. The calendar check does not model every holiday, so these counts are flags for inspection, not a diagnosis that every flagged hour is a data error. Historical gaps can affect structural context. EURCAD deserves additional checking because it had 47 extra flagged hours.

Warmup contained 19,989–20,036 H1 rows per pair. Batch windows differ by one hour. The 24-real-hour outcome excludes incomplete endpoints, including many weekend-spanning observations; it therefore describes a selected population, not all signals across all weekdays. Exact live alert timing and data-arrival delays were not reconstructed.

## What your original questions can and cannot be answered with

| Question | What this run tells us | Still required |
|---|---|---|
| Are extended stories useful? | They dominate eligible observations; next-day endpoint results were negative. | Longer windows, independent regimes, explicit structural renewal versus fresh-story alternatives. |
| Is replacing an old story with a fresh one better? | Fresh and retire-at-target had identical scored sets here; neither was positive. | More fresh confirmations and comparisons at matched decision times. |
| Is the target the optimal external liquidity? | Post-target activity is common; simply retiring at target did not improve this sample. | Competing target definitions, first-hit timing, overshoot/reversal paths and cost-aware execution. |
| Which entry timeframe is best? | Six H1 closed cases per variant, no H2/H4 closed cases; no winner. | Broader samples and M5 or finer execution data. |
| Were stops wrong or just swept before continuation? | Four hourly stop/target ambiguities require finer data. | Post-stop path study and lower-timeframe order sequencing. |
| Does higher-timeframe alignment help? | No convincing improvement from the small descriptive origin-agreement grouping. | Exact live filters, separate higher-TF/own-TF states and larger conditional samples. |
| Can the machine discover unknown causes? | Only four shallow predeclared discovery groups were screened; none selected. | Richer point-in-time features, controlled discovery and new-period validation. Causal explanations require more than price correlations. |
| Is Weekly entry better than lower-TF entry? | Weekly story origins were not evaluated in this run. | Explicit Weekly-story study; current Daily-origin variants cannot answer it. |

## Recommended next sequence

1. Reconcile research configuration with the intended live settings and inspect historical calendar/feed gaps. Preserve an explicit baseline configuration.
2. Extend the evaluation horizon (within the current 90-day ceiling initially) and include additional non-overlapping periods/regimes. Reuse existing frozen input history where possible; this report does not launch a new queue.
3. Obtain M5 or finer data for the ambiguous H1 trade cases before making stop or entry-quality claims.
4. Expand target/structural-renewal/post-stop alternatives under fixed study definitions. Compare matched opportunities and account for shared currency exposure and clustered dates.
5. Validate any chosen changes on new, untouched periods after realistic spread, commission and execution assumptions. Consider ANN only after reliable labels and sufficient diverse examples exist.

**Decision now:** investigate continuation quality and execution resolution first; do not promote any tested alternative into live rules based on this run. A bad short window is a finding to explain, not sufficient evidence to reverse all signals or declare the whole strategy broken.

## Every pair

Baseline score is the mean signed next-24h move in trailing H1 range units. “—” means no scored observations; it does not mean an error or zero performance. Every pair completed; every discovery screen was insufficient_data.

| Pair | Lifecycle events | Scored baseline units | Baseline score | Eligible new confirmations |
|---|---:|---:|---:|---:|
| AUDCAD | 12 | 4 | -1.59 | 2 |
| AUDCHF | 37 | 10 | -2.48 | 1 |
| AUDJPY | 6 | 2 | -2.20 | 1 |
| AUDNZD | 35 | 11 | -3.54 | 0 |
| AUDUSD | 37 | 1 | -2.05 | 1 |
| CADCHF | 20 | 7 | -2.71 | 1 |
| CADJPY | 44 | 8 | -1.65 | 0 |
| CHFJPY | 69 | 16 | -1.14 | 1 |
| EURAUD | 24 | 8 | -1.04 | 0 |
| EURCAD | 8 | 0 | — | 0 |
| EURCHF | 18 | 3 | -3.63 | 2 |
| EURGBP | 34 | 0 | — | 0 |
| EURJPY | 34 | 13 | -1.58 | 1 |
| EURNZD | 40 | 0 | — | 0 |
| EURUSD | 22 | 11 | +0.35 | 2 |
| GBPAUD | 0 | 0 | — | 0 |
| GBPCAD | 13 | 0 | — | 0 |
| GBPCHF | 36 | 14 | -1.56 | 1 |
| GBPJPY | 45 | 11 | -2.28 | 1 |
| GBPNZD | 41 | 0 | — | 0 |
| GBPUSD | 42 | 14 | -1.61 | 1 |
| NZDCAD | 9 | 0 | — | 0 |
| NZDCHF | 17 | 9 | +0.05 | 1 |
| NZDJPY | 33 | 12 | -2.12 | 0 |
| NZDUSD | 54 | 14 | -1.53 | 0 |
| USDCAD | 19 | 8 | +0.99 | 0 |
| USDCHF | 45 | 16 | -1.93 | 1 |
| USDJPY | 34 | 8 | -1.69 | 1 |

## Reproducibility and sources

- Queue: https://github.com/awujo/practicing/actions/runs/39261159754
- First batch: https://github.com/awujo/practicing/actions/runs/39255962764
- Subsequent batches: 39261223754, 39261650880, 39262056504, 39262526990, 39262964414, 39263389187.
- Downloaded original result artifacts contain individual report.json and ledger.sqlite for every pair. Original Actions artifacts have 30-day retention; research records were published by the successful persistence jobs.
- Adjacent analysis-summary.json and pairs.csv preserve the computed descriptive aggregates. Policy-specific samples are deduplicated separately. Cohorts inside summary JSON are separately deduplicated and can overlap; the disjoint canonical table in this report resolves that overlap by latest confirmation/tap/ID. Do not add overlapping subgroup counts.
