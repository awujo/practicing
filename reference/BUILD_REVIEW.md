# Independent Bishop build review

Review baseline: `b4bb1d9` on `claude-bishop-aggressive`, 2026-10-20.
Scope: existing candle store, database and cTrader layer; Kevin replay checks as a reference.
This is an implementation review, not evidence that the trading strategy is profitable or that every teaching example matches.

## Findings

| ID | Severity | Status | Evidence / required correction |
|---|---|---|---|
| INF-1 | High | Fixed; regression-tested | At baseline `ctrader/tokens.py:68-80` returned memory settings without borrowed ownership when no database existed, permitting an expired shared environment token to refresh and invalidate Kevin's token. Reproduced with a fake endpoint. Memory fallback now retains the read-only ownership policy; explicit own-token mode is tested separately. |
| INF-2 | High | Fixed; consumer integration still required | At baseline `bishop/candles.py:22-34` used last *observed* H1 + 1 hour as timeframe end, allowing partial daily bars to look closed. `resample.end` now uses the nominal NY boundary, `nominal_end` supports all six timeframes, and `completed` filters both forming H1 and higher-timeframe bars. Engine consumers must use this completion API and separately validate feed coverage. |
| INF-3 | Medium | Fixed for existing tables | `bishop/db.py:15` pointed to an absent `db/schema.sql`. A Bishop-only settings/run schema is now present and tested. All existing settings/run SQL mutations are prefixed `bishop_`. Generic `execute()` itself does not enforce isolation; audit every future SQL writer and schema statement. |
| INF-4 | Medium | Fixed | At baseline `bishop/store.py:main` imported nonexistent `.backtest.PAIRS`. It now imports the independent `bishop.universe.PAIRS`. |
| INF-5 | Medium | Open | `bishop/store.py:hourly` deliberately returns an existing partial cTrader store after acquisition fails. It does not prove requested history coverage or internal gap completeness. Replay/backtest must validate the frozen input range and classify insufficient data separately from a trading mismatch; do not report full 2018+ coverage merely because some bars loaded. |
| INF-6 | Low | Open | `ctrader/tokens.py:56`: token-table name is interpolated into SQL without validating it as an identifier. It is environment configuration, not external request data, but reject anything except a plain table identifier to avoid invalid SQL or unintended table access. |
| SRC-1 | High | Extractor fixed; source-bundle regeneration tracked separately | `knowledge-base/tools/extract_frames.py:extract_interval` used default `fps=1/interval` selection but burned/indexed `n*interval`. An independent 61-second 1-fps source encoding source-second as pixel luminance yielded selected seconds `[7,22,37,52]` for interval 15, labelled as `[0,15,30,45]`. Fixed extractor preserves actual selected PTS and samples the first frame of each occupied interval bucket. Existing sheets remain approximate until regenerated; do not treat the tool fix alone as correcting every saved source citation. |

### Confirmed protections

- `DbSettings.set()` refuses writes of borrowed `ctrader_*` keys; `refresh_tokens(DbSettings)` refuses refresh before making a request.
- `bishop/store.py:_open_client` uses `default_settings(strict=True)`. A configured database failure therefore aborts normal candle authentication and triggers fallback rather than silently using refreshable memory settings. The no-database case in INF-1 remains distinct.
- `store.recent()` excludes any H1 bar whose start + 1 hour is later than `now`.
- cTrader and Dukascopy primary files retain separate source identities. Recent fallback is an explicitly separate overlay, but consumers still need to record that the returned series spans two feeds.
- No broker execution has been added by this review.

## Kevin replay gaps to avoid

Reviewed Kevin baseline `7bccddd`, `slk/verify_examples.py`, `slk/verify_trades.py`, and `.github/workflows/verify-examples.yml`.

- Bias checker explicitly displays targets without judging them. Its PASS is not a full trade match.
- Exact-trade checker judges side, fill status, time, entry and stop, but not target or entry timeframe. Pair is selected upstream rather than enforced in `check()`.
- A weighted nearest-candidate score can select a failing candidate even if another candidate satisfies every constraint. Strict acceptance should evaluate the conjunction of all criteria on each candidate, then choose among genuine matches; mismatch diagnostics can rank separately.
- Default +/-3-day and 5-pip tolerances are broad implementation defaults rather than the individual chart's evidence resolution.
- Example checker always exits zero, and trade workflow uses `|| true`; a green workflow does not mean examples matched.
- Saved default exact-trade report is 0/6 PASS; neck variant is 1/6. These are saved reports, not a fresh production-credential run.

## Required Bishop acceptance contract

1. Freeze teaching observations independently of engine results: source path, timestamp/page, actual viewed frame, pair, side, setup/entry timeframe, event time and timezone, entry, stop, target, and whether values are exact or visibly approximate. Record unknowns as unknowns, never inferred exact prices.
2. A verified trade passes only when **one actual engine-produced candidate simultaneously matches every required field**: pair, side, timeframe, setup/fill time, entry, stop, target, and filled status. A pending or missed order does not reproduce an executed trade.
3. Tolerances must come from source measurement resolution and be frozen before replay. Never widen them because the engine missed. Reject non-finite numbers, negative tolerances, malformed times and invalid price geometry.
4. No engine candidate, no candle data, source ambiguity and a genuine mismatch are distinct outcomes. Unknowns/unresolved cases never count as passes. Report verified and total coverage together so excluded cases are visible.
5. Include explicit no-trade examples with an as-of clock: there must be no prohibited actionable signal by that clock. Also verify setup timing so an eventual correct trade does not excuse a premature signal.
6. Replay only information available at each observation time. Replaying a full series then filtering output timestamps is insufficient unless causality is independently demonstrated. Completed higher-timeframe candles, pivot confirmation times, and source feed/session conventions must be checked.
7. Teacher-faithful zone-edge stops and the owner's fixed 10–11-pip aggressive override are separate profiles. A chosen override must never be presented as an exact reproduction of a teacher trade with a different stop. Show both results without overwriting teacher expectations.
8. Verification must fail the acceptance job when any verified example fails, errors or lacks required data. Unresolved examples keep the full source-study milestone incomplete even if the verified subset passes. Zero verified examples is not success.
9. Synthetic rule tests and golden speed-regression tests complement real chart replays; they cannot establish teacher fidelity alone. No fabricated chart fixture or fixture-driven engine branching.

## Verification performed for this review

- Source inspection and two isolated offline reproductions: INF-1 fake refresh endpoint was invoked; INF-2 partial daily observed end preceded nominal close by 22 hours.
- No production credentials, database queries, broker orders or external messages used.
- Ongoing code/acceptance review follows below as modules arrive.

## Incremental review: initial acceptance checker and infrastructure corrections

- INF-1 correction inspected: `MemorySettings` now inherits `CTRADER_TOKEN_TABLE` ownership policy; borrowed writes are blocked and `_store` rejects shared token persistence. Explicit empty token-table setting preserves independently owned refresh behavior. Independent offline regression tests cover no DB, DB failure, strict failure, memory writes and independent-mode refresh.
- INF-3 correction inspected: `db/schema.sql` now creates only `bishop_settings` and `bishop_runs`; isolation test intercepts executed schema statements.
- Initial `bishop/replay.py` checks all trade dimensions and rejects empty/unresolved coverage. Independent `tests/test_replay.py` exercises each dimension separately, one-candidate conjunction, all-candidates matching, source tolerances, unresolved sources, malformed fixtures, no-trade observations and profile separation. Synthetic fixture tests are explicitly labelled checker contracts, not teacher evidence.
- Review requests sent: remove unconditional `1e-12` price allowance; reject verified fixtures that retain unresolved source questions; no-trade observations must not hide same-pair fills on another execution timeframe/profile. Regression tests added before correction.
- All three checker review requests are now corrected and regression-tested. Price comparisons use decimal representations and the explicit source tolerance, with no added epsilon.
- Candle correction additionally fixes `nominal_end(H1)` previously raising and `nominal_end(H2/H4)` incorrectly adding an entire day. Twenty candle tests cover all timeframes, winter/summer closes, spring/fall transitions, missing samples, exact-close availability and contamination by forming H1 data. Another agent was requested to review this implementation independently.
- Focused suite after these corrections: **69 passed in 0.48 s** (`tests/test_candles.py`, `tests/test_replay.py`, `tests/test_token_policy.py`). These tests validate infrastructure and the acceptance checker, not teacher-trade replay success.
- Independent candle review by `infrastructure_fix` confirmed H2/H4 NY boundaries, autumn fold policy and W/M calendar arithmetic. Explicit scope limit: the Friday weekly close is an FX convention. Weekend-trading assets need a separate calendar policy or rejected weekend samples; do not silently reuse this weekly clock for crypto. Current default universe is FX and the cTrader store filters FX weekends.
- Acceptance schema expanded to require explicit teacher bias side/timeframe and setup-availability window separately from fill time; independent tests cover wrong bias, wrong bias timeframe, premature/late setup, setup after fill, and no-trade exemption. Current offline suite after this expansion: **91 passed in 0.50 s**. Source examples remain unresolved; these are not 91 teacher trades.
- No-trade checks now reject actionable `PENDING`, `TRIGGERED` and `APPROVED` orders as well as `FILLED` trades within the prohibited same-pair time window; malformed same-pair order timestamps also fail. Independent regression tests cover each status.
- `bishop/price_action.py` independently reviewed with five additional reviewer tests: completed-candle integration, end-column precedence, second-candle availability/no formation self-signal, mirror sweep/immutability and invalid OHLC. No blocker for its stated primitive scope. Exact-junction/gap handling remains an explicit choice; temporal feed gaps require upstream coverage checks. `BREAK` is relative-level closure, including an entirely gapped-beyond candle, not independently established structural BOS.
- Frame-extractor correction inspected and CFR pixel-identity tests run successfully. Actual selected source PTS now drives both labels and index, with a recorded timestamps manifest. Staging avoids stale old sheet tails and protects old output from generation failures; final multi-file replacement is not an atomic bundle swap. VFR-gap sampling policy and nonzero initial media timestamp conventions need explicit documentation; source timing truth must not be replaced with a claim of exact lattice sampling.

## Foundation milestone: final reviewer status

- Final extractor policy is now explicit: first source frame in each occupied interval bucket, with empty buckets skipped. The `prev_selected_t` bucket comparison avoids the earlier proposed selector's sparse-VFR catch-up frames. Independent final run: **5 frame-extraction tests passed in 3.02 s** (1-fps source identity, 1.5-fps fractional PTS/source identity, nonpositive interval, sparse VFR, stale sheet/frame cleanup). No blocker found in this correction for the elapsed-first-video-frame source clock.
- The saved teaching fixture document validates structurally and contains **40 unresolved observations, zero verified trades** at this review point. Explicit bias/setup fields do not make unreadable historical values known. This is source-inventory coverage, not a claim of 40 matched trades.
- Foundation modules and tests are reviewable; this milestone is not a completed trading bot, live deployment, full source-verification sign-off or acceptance replay pass. Source-bundle regeneration completion must be checked by the coordinating agent before committing it. Original course sheets not regenerated remain approximate and must not supply falsely exact timestamp evidence.
- Remaining integration work: complete independently verifiable teaching observations, implement causal bias/setup/trade logic, validate frozen candle coverage and source conventions, replay every verified example with engine-generated observations, and review each subsequent change. No production database, Telegram or broker action was performed in this review.
