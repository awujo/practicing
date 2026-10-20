# Full historical research review — 20 October 2026

**Decision:** the study has produced useful diagnostic evidence, but no tested change is ready for live promotion. Price frequently returns to the original target after a simulated stopout. Wider structural stops improve some simulated outcomes, but neither those stops nor mechanical re-entry produces a demonstrated profitable policy. The longer history materially weakens the earlier pilot's suggestion of consistently poor directional behaviour: the aggregate Daily endpoint result is close to neutral, slightly negative.

All 28 pair studies completed. Database publication stopping at 406/560 ledgers under the 128 MiB payload cap does not remove any pair from this analysis: every pair archive and all 560 native/scenario ledgers were downloaded and inspected. The combined summary was also recovered independently of database saving.

## Coverage, samples and exclusions

- Approximately **835 calendar days evaluated per pair**, from 6 July 2024 to 19 October 2026, after approximately 365 days of historical context. First batch boundaries differ from others by one hour.
- **280 windows**, ten per pair, each at most 90 days. Native Daily and Weekly origins; completed H4 observation cadence, code-default settings rather than the exact current live settings.
- **30,760 native lifecycle events**, 30,543 lifecycle scenario records and 16,613 entry counterfactual records. Counterfactuals are repeated alternatives on the same opportunities, not independent trades.
- 96,189 processed H4 cutoffs and 3,340 gap-adjacent excluded cutoffs: about **3.36%** of their combined count. Gap exclusions reset bootstrap; older context gaps and holiday-calendar approximations remain limitations.
- **1,236 eligible new confirmations**, each tested against four entry variants: 4,944 native entry trials. Those produced 444 closed variant outcomes representing **219 distinct confirmed-story opportunities**, not 444 independent opportunities. Most trials had no qualifying pending setup or were cancelled/censored/unfilled.
- No native event ID duplicated across windows. Within a pair/origin/time/side the signal summaries retain the newest tap, preventing multiple old stories from inflating a candle's directional observation count. Currency exposure, overlapping 24/72-hour windows and repeated confirmations remain dependent.

Native lifecycle inventory: 20,219 continuation, 4,808 tapped, 1,916 external-break-pending-origin, 1,636 confirmed, 960 target-hit, 561 line-end, 443 invalidated, 215 ended-flip and two cancelled events. These populations include no-trade states; they cannot be divided into a target-hit trade success rate.

## 1. Bias direction: the full history is different from the 21-day pilot

Directional score is signed price movement over the next 24 real hours divided by the preceding average H1 high–low range. It is **not trade R, percent return or profit**. Positive means the endpoint moved in the signalled direction. Complete endpoint requirements exclude some weekend/gap periods.

| Origin | Distinct completed signal units | Mean directional score | Ended in intended direction |
|---|---:|---:|---:|
| Daily | 8,066 | −0.078 | 3,974/8,066 = 49.3% |
| Weekly | 642 | −0.029 | 315/642 = 49.1% |

The Daily score was −0.009 in the evaluated portion of 2024, −0.053 in 2025 and −0.151 in 2026. Weekly was −0.114, +0.243 and −0.412 respectively, with much smaller, selected samples. These are not untouched validation periods: the entire history has been inspected.

There is no strong aggregate next-day directional advantage in this measurement. There is also no support for extrapolating the very negative 21-day pilot across the whole history. A directional bias is not itself a specified trade: timing, target, stop, costs and holding window still matter.

Nine pairs had positive Daily directional means and 19 negative; Weekly had 17 positive and 11 negative. Pair rankings are descriptive, not a valid pair-selection rule. Per-pair entry samples were small, commonly only a handful of closed H1 cases across the whole study.

## 2. Old storylines versus fresh stories

Canonical Daily 24-hour observations break down as follows:

| Daily signal | Units | Mean directional score |
|---|---:|---:|
| Initial confirmation | 790 | −0.015 |
| Continuation before target | 1,739 | −0.001 |
| Continuation after target | 5,530 | −0.118 |

Seven additional accepted continuation units had another status such as cancellation, so these three rows do not sum to all 8,066 Daily units. About **68.6%** of the canonical Daily observations were post-target continuations. This supports investigating alert repetition and post-target story quality. It does not show that every old story is wrong.

| Daily lifecycle policy | 24h units | Mean 24h score | 72h units | Mean 72h score |
|---|---:|---:|---:|---:|
| Keep eligible signals | 8,066 | -0.078 | 6,019 | -0.182 |
| Retire at target | 2,529 | -0.005 | 1,861 | -0.238 |
| Require newer valid origin confirmation after target | 2,756 | +0.027 | 2,015 | -0.290 |
| Only latest tap story | 3,437 | -0.134 | 2,586 | -0.432 |
| Retire on newer same-direction tap | 3,700 | -0.070 | 2,768 | -0.271 |
| Retire on newer opposite-direction tap | 7,489 | -0.084 | 5,597 | -0.213 |
| Maximum five days | 1,364 | -0.089 | 1,151 | -0.175 |
| Maximum ten days | 3,369 | -0.091 | 2,415 | -0.336 |
| Maximum twenty days | 5,190 | -0.099 | 3,879 | -0.301 |
| Maximum forty days | 7,033 | -0.115 | 5,284 | -0.310 |

Requiring a newer still-valid origin confirmation was slightly positive at 24 hours (+0.027) but negative at 72 hours (−0.290). That tiny positive full-sample result is not evidence of a tradable improvement. Retiring at target brought the Daily next-day score near zero. A blanket latest-story-only rule or fixed age expiry did not show a consistent benefit. Different policies retain different opportunities; these are not randomized paired return comparisons.

Weekly post-target continuation was near neutral (+0.004 over 349 units), compared with −0.067 for 293 pre-target continuation units. The Daily finding must not be transplanted mechanically onto Weekly stories. Weekly age is measured from the origin candle's open, so the same number-of-days cutoff has a different meaning than on Daily stories.

Replacement uses native new taps/confirmations generated by the existing engine. It does not test arbitrary new definitions of a rejection or every possible pattern grammar. Pre-window standing state is not fully reconstructed from lifecycle events, and the window bootstrap deliberately excludes already-present confirmations as new signals.

## 3. Entry performance: no profitable baseline demonstrated

These are conservative H1 simulations with a fixed one-pip spread, 0.2-pip slippage and zero commission. Entry alignment is disabled for the experiment; these are not exact live-policy or account returns. R is each trade's entry-to-stop risk distance. Stops and targets inside the same hourly bar are ambiguous, with stop-first accounting and no profit awarded on the fill candle.

| Entry variant | Closed variant outcomes | Positive | Mean R | Ambiguous closed outcomes |
|---|---:|---:|---:|---:|
| H1 zone | 189 | 47 | -0.502 | 87 |
| H1 rejection stop | 187 | 36 | -1.157 | 115 |
| H2 zone | 57 | 16 | -0.318 | 24 |
| H4 zone | 11 | 2 | -0.793 | 4 |

All closed entry outcomes were from **Daily-origin stories**. Weekly entries produced no closed case under the current search design; see the weekend limitation below. The four variants often describe the same underlying opportunity.

H1 zone, H1 rejection and H2 zone each had a negative mean in every evaluated calendar-year segment. H4 had too few cases to rank reliably. Removing the ambiguous closed outcomes still left negative means (H1 zone −0.452R, H1 rejection −0.641R, H2 −0.399R); that is a retrospective sensitivity check, not an executable filter or proof that the conservative fill assumptions are correct.

### Important gap/rollover stress case

The worst H1-rejection result was −49.5R, not an ordinary one-risk stop. The source EURCHF bid candles show the 28 July 2026 21:00 UTC hourly bar opening at **0.92912**, after the preceding close **0.93283**, around New York rollover. The pending BUY entry was **0.93108**, stop **0.93104** and target **0.93114**: just **0.4 pip** of stop distance, smaller than the assumed one-pip spread. The simulator keeps the specified limit entry price and uses the adverse opening quote for the gap stop. This creates an extreme conservative loss relative to the tiny nominal risk.

The quote observation is real in the frozen input; its economic tradability, actual ask spread, broker handling of a marketable limit plus attached stop, and fill sequence are **not established** by H1 bid OHLC. Do not interpret −49.5R as verified account loss or use it alone to reject the strategy.

Fourteen of 187 H1-rejection closed cases had stops narrower than one pip; 45 were at most two pips. H1 zone had a median stop of 6.9 pips, versus 4.0 pips for H1 rejection. A cost-relative minimum stop width and rollover handling deserve explicit future tests.

Twelve H1-zone cases and 13 H1-rejection cases incurred losses beyond a normal stop plus the assumed slippage, consistent with gap-stress treatment. Excluding those cases retrospectively leaves means of −0.312R and −0.545R respectively—still negative, but those exclusions are not a validated trading rule. M5/tick bid-and-ask data and broker fill rules are needed to assess execution properly.

## 4. Your stopout question: price often did recover

Post-stop paths start **after the stopped hourly candle closes**, so they do not reuse an intrabar high or low from the same candle. The target-touch result is a price-path observation; it is not another executed, cost-adjusted profitable trade, and SELL executable ask touches were not reconstructed from bid-only paths.

| Original entry variant | Simulated stopouts | Complete next-24h paths | Later touched original target | Recovered entry without target | Continued against trade / near stop |
|---|---:|---:|---:|---:|---:|
| H1 zone | 142 | 110 | 85 (77.3% of complete paths) | 13 | 12 |
| H1 rejection | 151 | 118 | 94 (79.7% of complete paths) | 11 | 13 |
| H2 zone | 41 | 31 | 19 | 6 | 6 |
| H4 zone | 9 | 7 | 5 | 0 | 2 |

For H1 zone, 32 stopped paths were censored; for H1 rejection, 33. Thus the 77–80% figures apply to complete follow-up paths, **not all stopouts**. The entry variants overlap heavily and must not be pooled as independent evidence. Seventy-two-hour results have more censoring and a different weekday composition.

This is meaningful support for your concern: getting stopped did not usually imply price permanently abandoned the intended direction in these observed cases. It does not tell us whether the stop was inappropriate, the entry was early, or the hourly simulator invented the apparent stop before a target. We need finer execution evidence to separate those explanations.

## 5. Would wider or different stops solve it?

Matched closed outcomes compare the same confirmation and entry variant where both the baseline and alternative closed:

| Entry variant and stop comparison | Matched cases | Baseline mean R | Alternative mean R |
|---|---:|---:|---:|
| H1 zone → 1.5× original risk distance | 188 | −0.500 | −0.395 |
| H1 zone → H2 structural stop | 180 | −0.510 | −0.334 |
| H1 zone → H4 structural stop | 182 | −0.482 | −0.132 |
| H1 rejection → H4 structural stop | 181 | −1.158 | −0.172 |

The H4 stop produced more positive outcomes, but a materially different risk/target geometry. Its median stop distance was **3.50×** the H1-zone baseline and **5.36×** the H1-rejection baseline. R is recalculated using the changed stop, so comparing means without discussing risk would be misleading. Equal currency risk requires smaller positions with wider stops. Holding quantity fixed gives a different comparison: H1 zone's H4-stop average was −0.379 in original-risk units; H1 rejection's was −1.820. Neither establishes a profitable replacement.

The structural stop uses extrema of the five completed H4 bars available at entry, plus a buffer. It is a defined proxy, not proof of the optimal invalidation level. Some alternative stops can be narrower, and invalid/missing candidates are omitted. That creates different subsets, which is why the matched results above are preferable to comparing unmatched averages.

## 6. Re-entry versus taking the opposite direction

The tested rule waits for a new completed H1 break of the preceding three-bar range, then seeks a limit retest with its own structural stop and 2R target. One setup is tested per direction, not unlimited retries or a fully confirmed new Daily/Weekly story.

| Starting entry variant | Same-direction re-entry closed cases | Mean incremental re-entry R | Opposite-direction setup closed cases | Mean incremental opposite R |
|---|---:|---:|---:|---:|
| H1 zone | 96 | -0.014 | 110 | -0.121 |
| H1 rejection | 103 | -0.017 | 118 | -0.078 |
| H2 zone | 30 | -0.150 | 30 | -0.114 |
| H4 zone | 6 | -0.239 | 7 | -0.569 |

Mechanical re-entry did not demonstrate a positive incremental average. Blindly switching direction after a stop was not supported either. Some later recoveries were too late, occurred without the tested setup, or were captured poorly by that setup's stop/target. A price recovery is not automatically an available entry.

On matched H1-zone cases, combining the original stop with the re-entry under an explicit equal-cash-risk-per-trade assumption remained negative (mean −1.333R across 96 cases). This is not a portfolio backtest; overlapping trades and cross-pair exposure remain unmodelled.

## 7. Targets, partial exits, trailing stops and costs

For H1 zone, the original target averaged −0.502R; a 1R target −0.571R, 2R −0.509R, 3R −0.350R, nearest confirmed H4 pivot −0.534R and recent origin-range extreme −0.436R. A 3R target helped this particular mean but remained negative. Other entry timeframes did not show a consistent corresponding benefit, so there is no optimal-target conclusion.

Taking half at 1R then moving the stop to breakeven worsened the H1-zone mean to −0.545R and H1-rejection mean to −1.194R. The H1 trailing-stop rule was slightly less negative for H1 zone (−0.455R) but did not establish an edge. Partial sizing and stop changes are based on closed candles; fine execution order is still unknown.

Higher assumed spread/slippage generally worsened performance. For example, H1-zone mean was −0.453R at half-pip spread, −0.502R at one pip and −0.651R at two pips. Even the optimistic half-pip case stayed negative. Cost variants reuse the same baseline setup; they do not regenerate spread-dependent setups. Actual variable spreads and commissions are not included.

## 8. Context and confirmation

- Low-volatility groups were more negative descriptively: Daily low −0.474 range units versus normal −0.029; Weekly low −0.500 versus normal −0.005. These are screening observations, not validated low-volatility abstention rules.
- Origin alignment was not automatically better: Daily own-trend agreement averaged −0.135 versus −0.013 for disagreement. The groups are observational and can overlap at a candle through different stories. Higher-timeframe disagreement was largely excluded by the baseline configuration, so we cannot infer whether removing that filter helps.
- Simple age cutoffs did not improve the full Daily sample. Some long-age groups were near neutral or positive, contradicting a universal “old story = bad” rule. Story identity, structure and entry quality may matter more than an arbitrary expiry.
- Distance, WAT time buckets, rule/level type and origin flags are in the saved context tables. Some small groups look positive, but selecting the best after inspecting many groups would overfit. There is no fitted or held-out validation of those apparent pockets.
- The origin-confirmation diagnostic recorded 1,252 Daily lower-break records later confirming versus 300 origin invalidations and ten censored; Weekly had 270 confirming, 75 invalidating and nine censored. **These are break-event records, not unique independent setups**. They show a lower-timeframe break does not ensure the origin close will confirm. They do not permit intrabar alerts or claim that waiting always improves trade returns.

## 9. Weekly entries and the weekend blind spot

The weekly lifecycle engine was replayed, but the entry window was only **24 real hours** after a new confirmation. Weekly confirmation occurs at the Friday close; much of that search window has no open FX session. The native Weekly trials therefore produced 719 no-pending-setup records, 96 censored and one censored setup search, **with no closed entry outcome**.

There were also no complete 24-hour *initial Weekly confirmation* endpoint outcomes, whereas the 72-hour event-path table had 242 such records. Weekly continuation observations during open sessions are a different population.

This is an important limitation in the research design. The 835-day input horizon does not cure a clock definition that prevents observing the next open session. Before judging Weekly entry quality we need an explicit market-open-hours clock or a specified next-session entry window, not a claim that Weekly setups do not work. The same real-hour clock also influences Daily weekend censoring and 72-hour comparisons.

## What can be judged now

1. **Supported diagnostic:** stopouts often precede recovery to the original target price in complete observed paths. Entry/stop timing deserves serious study.
2. **Candidate for further testing:** wider causal structural invalidation levels, with fixed-cash-risk sizing, cost-aware minimum stop widths and realistic execution.
3. **Not established:** automatic re-entry, reversing after a stop, blanket expiry, fresh-story-only logic, optimal target or a profitable entry timeframe.
4. **Must be corrected or resolved before strong claims:** Weekly market-session clock, tiny-stop/gap fill treatment, real bid/ask spread, intrabar ordering, window/gap exclusions and exact live configuration alignment.
5. **No live promotion:** all historical periods were inspected and many alternatives compared. Choose a small number of hypotheses, verify execution with genuine finer data and test them on new untouched data. No ANN or causal “why the market did this” model was trained.

## Every pair

Daily/Weekly scores below are next-24h H1-range units, not returns. H1 closed outcomes share opportunities with other variants; tiny per-pair samples cannot establish reliable pair selection.

| Pair | Daily units | Daily score | Weekly units | Weekly score | H1 zone closed | H1 zone mean R |
|---|---:|---:|---:|---:|---:|---:|
| AUDCAD | 257 | -0.562 | 13 | +1.504 | 4 | -0.049 |
| AUDCHF | 231 | -0.098 | 37 | +0.213 | 5 | -0.087 |
| AUDJPY | 304 | +0.191 | 22 | +0.866 | 7 | -0.672 |
| AUDNZD | 355 | +0.409 | 9 | -1.214 | 0 | — |
| AUDUSD | 328 | -0.077 | 26 | +0.568 | 10 | -0.806 |
| CADCHF | 287 | +0.070 | 26 | -0.450 | 8 | -0.659 |
| CADJPY | 320 | -0.458 | 25 | -2.077 | 8 | -0.723 |
| CHFJPY | 345 | +0.085 | 28 | +0.072 | 8 | -0.095 |
| EURAUD | 296 | -0.138 | 22 | +0.178 | 6 | +0.235 |
| EURCAD | 199 | -0.204 | 19 | -0.294 | 5 | -1.082 |
| EURCHF | 304 | -0.354 | 23 | +0.938 | 15 | -1.799 |
| EURGBP | 278 | -0.074 | 22 | +0.158 | 6 | +0.065 |
| EURJPY | 326 | +0.100 | 37 | -0.837 | 7 | +0.405 |
| EURNZD | 323 | -0.124 | 24 | +1.043 | 5 | -0.524 |
| EURUSD | 239 | -0.166 | 21 | -0.526 | 6 | -0.583 |
| GBPAUD | 232 | -0.007 | 18 | +0.724 | 1 | -1.014 |
| GBPCAD | 272 | -0.102 | 27 | -0.326 | 9 | -0.836 |
| GBPCHF | 203 | -0.710 | 27 | -0.876 | 6 | -0.058 |
| GBPJPY | 299 | -0.458 | 27 | +0.207 | 7 | -0.301 |
| GBPNZD | 314 | -0.197 | 25 | +0.571 | 7 | -0.073 |
| GBPUSD | 365 | -0.248 | 33 | +0.232 | 9 | -0.769 |
| NZDCAD | 182 | -0.764 | 27 | -0.272 | 7 | -0.723 |
| NZDCHF | 309 | +0.087 | 6 | -3.273 | 0 | — |
| NZDJPY | 325 | -0.020 | 22 | +1.180 | 6 | -0.379 |
| NZDUSD | 306 | +0.210 | 9 | +0.803 | 9 | -1.117 |
| USDCAD | 281 | +0.386 | 12 | +0.018 | 10 | -0.029 |
| USDCHF | 331 | +0.695 | 34 | +0.196 | 9 | +0.491 |
| USDJPY | 255 | -0.418 | 21 | -1.647 | 9 | -0.464 |

## Sources and retained outputs

- Original study: https://github.com/awujo/practicing/actions/runs/39296129468
- Recovered combined summary: https://github.com/awujo/practicing/actions/runs/39384374117 (artifact recovered-history-summary-39384374117).
- Database checkpoint: https://github.com/awujo/practicing/actions/runs/39391560836 — 406/560 ledgers, storage_blocked. Analysis includes all 560 regardless.
- Adjacent history-summary.json contains all automatically generated policy, target/stop, context, confirmation and path groups. audit-summary.json contains additional matched, year, ambiguity and re-entry checks. pairs.csv contains all pair rows. analyze_archives.py reproduces the additional checks from extracted archives.
- Original pair archives have seven-day retention. A separate downloadable bundle preserves all 28 extracted result archives and this analysis for the user; it contains result ledgers, not all original H1 source candles. Preserving the file requires downloading it; neither temporary workspace nor artifact retention is permanent backup.

No live rules changed and no extra historical study was launched for this review.
