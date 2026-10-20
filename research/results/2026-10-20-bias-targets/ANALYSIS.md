# Bias target and successive-target measurement — 20 October 2026

This measures the **bias target**, not entry TP1 or a 24-hour closing-price endpoint. It uses the frozen H1 input for all 28 FX pairs, validated against the original input hashes, and the 1,636 newly confirmed Daily/Weekly bias stories from the full-history study. Configuration follows the original code-default study, including its higher-timeframe settings; this is not an exact live-settings replay. All-bias figures include NO_TRADE stories because those flags restrict entry eligibility, not the existence of a bias storyline. Entry-eligible-only figures are also retained in targets.csv.

## Rule fixed before measurement

Target 1 is the actual native bias target stored at confirmation. After it is touched, a next target is selected strictly ahead of the previous target, the current price path and every wick already seen while waiting for selection. The rule uses the native target helper with the consumed leg removed: **next known origin external-range structural swing first; otherwise a fresh opposing origin/higher-timeframe key level**. All candle availability is restricted by nominal close time, swing known-at indexes and level birth/tap/break indexes. Targets are frozen once selected; future price cannot move the target or create a missing level retrospectively.

This is an explicit **research target ladder**. Historical continuation alerts did not store actual target 2/3/4/5 forecasts, so these are not audited hit rates for previously broadcast targets. The rule is native-derived, not proof that each level is an optimal or untouched external liquidity pool.

Two modes were compared:

1. **After target touch:** choose next target after the completed H1 candle reveals the preceding target touch.
2. **After continuation close:** first wait for another recorded completed continuation break—H4 for Daily stories, Daily for Weekly—then choose the next target. A continuation close is the trigger, not a target hit.

The second mode is the closer match to the question about target reached **and then continuing**. At most five target stages are evaluated. Target touches use bid H1 wicks; they are not trade profits and need not close beyond the target. Same-hour target touch and terminating close are labelled ambiguous, not wins. Story termination before target 1 includes observed invalidation/flip/cancellation; after a target the line ends on an origin close through its original level. No trade stop loss is used.

## First bias target: direct frozen-price check

| Origin | Confirmed bias stories | Target reached | Ended before target | Unfinished at window end | Censored by gaps |
|---|---:|---:|---:|---:|---:|
| Daily | 1,393 | **806 (57.9%)** | 521 | 51 | 15 |
| Weekly | 243 | **114 (46.9%)** | 72 | 45 | 12 |

Percentages use all confirmed stories, leaving unfinished and missing-data cases visible rather than calling them failures. Among hits only, median calendar time from confirmation to observed touch was **29 hours for Daily** and **129 hours for Weekly**. Those medians are conditional on reaching the target, not expected waiting times for every story.

These direct H1 measurements replace the earlier rough counts of 793 Daily /112 Weekly recorded target-status transitions for this question. The method now freezes the actual target at confirmation and checks the candles, separates gaps and uses explicit termination timing. H4 snapshots and direct H1 touches are different measurements.

The historical `erl_taken` flag alone is not treated as proof that the **current** target was already consumed: the native engine can replace an earlier taken target with a further one. The actual frozen target is checked against the available price history. A regression covers that distinction.

## After a new continuation close: Daily target ladder

“Selected” means an ahead target actually existed and was fixed after the required continuation close. Hit percentages include unfinished/censored selected cases in the denominator and are therefore observed hit fractions, not failure-adjusted probability estimates.

| Stage | Targets selected | Reached | Observed hit fraction | Ended first | Unfinished | Gap-censored |
|---|---:|---:|---:|---:|---:|---:|
| T1 | 1393 | 806 | 57.9% | 521 | 51 | 15 |
| T2 | 626 | 457 | 73.0% | 123 | 38 | 8 |
| T3 | 378 | 277 | 73.3% | 58 | 32 | 11 |
| T4 | 227 | 180 | 79.3% | 24 | 15 | 8 |
| T5 | 159 | 116 | 73.0% | 21 | 13 | 9 |

Of the 806 Daily stories that reached target 1, **626 actually produced a selected target 2** under this mode. The other 180 had no known target ahead (127), ended without another continuation close (44), or were unfinished while waiting for one (nine). They are not 180 failed target-2 forecasts.

The 457 target-2 hits represent **32.8% of all 1,393 original Daily stories**. Target-3 hits represent 19.9%, target-4 hits 12.9%, and target-5 hits 8.3%. This shows survivor selection: the roughly 73% conditional target-2 figure does not mean 73% of every new bias reaches a second target.

## After a new continuation close: Weekly target ladder

| Stage | Targets selected | Reached | Ended first | Unfinished | Gap-censored |
|---|---:|---:|---:|---:|---:|
| T1 | 243 | 114 | 72 | 45 | 12 |
| T2 | 62 | 30 | 10 | 17 | 5 |
| T3 | 15 | 8 | 2 | 5 | 0 |
| T4 | 5 | 3 | 0 | 2 | 0 |
| T5 | 1 | 0 | 0 | 0 | 1 |

Weekly target 2 reached **30/62 selected targets (48.4%)**, with 17 unfinished and five censored. Another 37 stories had no next known target, seven ended without a new continuation close, and eight were unfinished waiting for confirmation. Later Weekly stages have very small selected samples; zero observed target-5 hits does not mean three valid forecasts failed—two had no target available and the only selected one was gap-censored.

Weekly right-censoring is substantial because each original evaluation window ends within at most 90 days. Weekly continuation is not disproved by these counts, and deeper-stage percentages are too unstable to promote a policy.

## Alternative: selecting immediately after the previous touch

| Origin | Stage | Selected | Reached | Ended first | Unfinished | Gap-censored |
|---|---:|---:|---:|---:|---:|---:|
| D | T2 | 677 | 498 | 138 | 34 | 7 |
| D | T3 | 456 | 373 | 48 | 27 | 8 |
| D | T4 | 332 | 269 | 36 | 18 | 9 |
| D | T5 | 249 | 202 | 25 | 15 | 7 |
| W | T2 | 80 | 43 | 13 | 21 | 3 |
| W | T3 | 33 | 19 | 5 | 6 | 3 |
| W | T4 | 16 | 12 | 1 | 2 | 1 |
| W | T5 | 7 | 3 | 0 | 3 | 1 |

Immediate selection produces more and generally nearer targets because less movement occurs before the next target is fixed. Daily target-2 hits were 498/677 selected (73.6%), versus 457/626 (73.0%) when waiting. Weekly was 43/80 (53.8%) versus 30/62 (48.4%). **This does not establish that skipping confirmation is better**: the times, candidate levels, availability and forecast populations differ. It is not a matched entry-return comparison, and no intrabar breakout is accepted as a completed continuation.

## Interpretation

- The bias model does often reach its defined main target, and a meaningful subset of Daily stories reaches several successive known targets. This is more relevant to a bias-target objective than asking whether every signal's closing price is favourable exactly 24 hours later.
- A recorded continuation break and an ahead target hit are demonstrably different. A continuation can occur without any further eligible structural target, or can fail to reach a selected target before the original line ends.
- The Daily conditional continuation figures are worth validating; they do not establish profit, independence, superiority to a benchmark, or a live next-target rule.
- Weekly evidence is smaller/slower and more censored. More complete follow-up is needed before judging deeper Weekly targets.
- No expected R, entry stop, portfolio return, optimality or ANN claim is made. Targets and termination distances vary, many forecasts overlap, and currency pairs share exposure.

## Reproducibility and limits

Implementation: `slk/research_bias_targets.py`; tests: `tests/test_research_bias_targets.py`. Tests cover future-invariant native target selection for both Daily and Weekly contexts, no target before previous hit/required close, no false failure when no confirmation exists, same-hour end ambiguity, missing hours and native replacement-target flags.

Inputs were all seven original frozen IC Markets exports, not fresh prices. Original native lifecycle ledgers supply confirmation, continuation-close and flip/cancellation observations. Nominal origin/higher closes prevent forming candles entering target selection. Target 1 is fixed at confirmation; future data is used only for labels. The native backtest context's known-at filters are tested against a prefix-only context with deliberately altered future prices.

Eight-day gap-adjacent selection exclusions, missing-hour censoring, historical context gaps, window resets and partial pre-window standing-state reconstruction remain limitations. Known continuation events can be absent after skipped/bootstrap periods. Bid wick touches are price observations, not proof that an actual ask-side order or entry would execute. There is no untouched validation period; this is exploratory historical measurement.

Outputs: summary.json, targets.csv and compressed per-story records.json.gz. No database writes (publication remains capped), live setting changes, broker orders or new historical replay workflow were needed. The input source and full-history results are those of run https://github.com/awujo/practicing/actions/runs/39296129468 .
