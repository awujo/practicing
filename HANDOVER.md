# Bishop "aggressive" bot: rebuild (handover)

Branch `claude-bishop-aggressive` (repo awujo/practicing). It starts with **only the teaching material** of the
Bishop course. Rebuild the bot from it the same way the Kevin King SLK bot was built on branch `claude-kevin-king`.
Keep this file up to date with every commit: what is built, how it maps to the course, and what is open.

## Source material (the only source of truth for the rules)

| Path | What |
|---|---|
| `knowledge-base/videos/video-N-<description>/` | rebuilt transcripts for all 18 core videos; numeric-only folders contain older notes/transcripts |
| `knowledge-base/videos/bishop-*/transcript.txt`, `plug-and-play/` | 10 Bishop sessions: bias entries, building bias 1+2, daily routine, entries part 5, repeating system, trades breakdown 2+3, what next, plug and play |
| `knowledge-base/supplementary/*.md` | written notes per Bishop session, SL measurements, chart-example notes |
| `knowledge-base/supplementary/source/bishops_trade_chart_examples.pdf` | Bishop's 60-page chart-example PDF (the only visual source kept) |
| `knowledge-base/STRATEGY.md` | the consolidated rulebook written from all of the above (sections 1-9). A summary, not the source: check every rule against the transcripts/notes before coding it, quote them in code comments as `[T video-13@...]` / `[N b_entries_part5]` |
| `reference/OPEN_QUESTIONS.md`, `reference/PROJECT_HISTORY.md` | lessons from the first Bishop bot on `main` (MT5/VPS, conservative + aggressive styles): read them, do not copy its code |

Transcripts have landed for all release assets. Transcription completion is not source-study completion.
Bishop's 10 release assets include one byte-identical duplicate (Part 3), leaving nine unique sessions.
Course and plug-and-play high-resolution sheets exist; Bishop session sheets initially had ~420px tiles
and have now been replaced with corrected source-timestamp 1280px/2×2 sheets. Original course/plug-and-play
timestamp labels remain approximate until regenerated with the repaired extractor. Inspection coverage is
recorded separately from extraction completion in the study ledgers.
The original source releases are:

| Release tag (GitHub Releases of this repo) | Videos | `slug_prefix` |
|---|---|---|
| `video1` | course video 1 | `video` |
| `remaining-videes` | course videos 2-18 | `video` |
| `defi-bishop` | 10 Bishop study sessions (+ 4 tweet images) | `bishop` |
| `plug-and-play` | Plug and Play system video | `bishop` |

1. Actions → "Transcribe" (`.github/workflows/transcribe.yml`, run on this branch, one run per tag above):
   faster-whisper transcript + contact sheets → `knowledge-base/videos/<slug>/transcript.txt`,
   `knowledge-base/frames/<slug>/`. Use a larger whisper model than `small` if it fits the time limit.
2. Actions → "Extract course video frames" (`extract-frames.yml`): readable sheets (1280 px tiles, 2x2, every
   20 s; lower the interval where a chart is being drawn). Check the source resolution printed in the job log.
3. Study every video from its new transcript AND its frames (charts, levels, entries, stops, targets, pair,
   timeframe, date), with independent agents cross-checking: one agent reads, a second agent verifies each
   extracted rule/example against transcript + frames, disagreements are resolved against the source and written
   down. Rebuild `knowledge-base/STRATEGY.md` from that (the old one is kept as a first draft; mark every rule as
   confirmed / corrected / new, with its source). Record Bishop's concrete trade examples (pair, date, TF, entry,
   stop, TP) in `tests/bishop_examples.json` so the bot can be replayed against them, as `tests/kevin_trades.json`
   on `claude-kevin-king`.

## What to build: the AGGRESSIVE style

STRATEGY.md §5 "Entry style spectrum": **Aggressive** = enter directly once the key-level + imbalance setup is fully
formed, without waiting for inducement/confirmation, with a wider stop (~10-11 pips). Conservative (wait for the
lower-TF confirmation, e.g. H2 engulfing) is a later option/setting, not the default. Bias = the top-down storyline
process of §2 (weekly/daily bias, key levels A / V / open-close, liquidity IRL/ERL, sessions §8, management §6).

## Target architecture (same as the Kevin bot; port the infrastructure from `claude-kevin-king`)

- **GitHub Actions** (repo is public until 1 Nov for free minutes): hourly live job (cron + an external hourly
  tick through the Mini App server `/cron/tick`), backtest job, examples-replay job. Candles: IC Markets cTrader
  (Open API secrets already in the repo: CTRADER_*), Dukascopy fallback, cached in the Actions cache.
- **Aiven MySQL** (secret DATABASE_URL / DATABASE_PASSWORD / DATABASE_CA): use a **separate table prefix or schema**
  (e.g. `bishop_bias`, `bishop_entries`, `bishop_settings`) so the Kevin bot's tables are untouched.
- **Telegram**: alerts only to the owner (chat id 1410229777, secret TELEGRAM_BOT_TOKEN). Use a separate bot token
  if the owner provides one, otherwise prefix every message "BISHOP".
- **Telegram Mini App on Render** (FastAPI + static JS, owner-only initData check): bias cards, entries, paper
  results, settings form (every rule a setting with the course default). A new Render service for this branch.
- Paper trading first: entries are tracked on paper (TP/SL/R) before any broker order.

Files worth porting from `claude-kevin-king` (adapt, don't copy blindly): `slk/candles.py`, `slk/store.py`,
`slk/ctrader*.py`, `slk/db.py`, `slk/settings.py`, `slk/live.py` (run loop, reconcile, alerts, Telegram),
`webapp/` (auth, API, Mini App), `.github/workflows/{live,backtest,verify-examples,backfill}.yml`, the tests style.

## Working rules (from the owner)

- Follow the teaching exactly; validate every rule against the transcripts/notes; say when something is our choice.
- Backtest every rule choice (all pairs, 2018+, costs included) and report honestly; no curve fitting.
- Telegram messages in readable sections (headline / key level / story so far / context / plan).
- Never print or commit secrets; the owner must not paste secrets in chat (GitHub Secrets / Render only).
- Commit + push to this branch only; no PRs unless asked; update this HANDOVER.md each commit.

## Status

- 2026-10-20: branch created with the material only (no code yet).
- 2026-10-20: added transcribe.yml, extract-frames.yml (slug_prefix input) and knowledge-base/tools/extract_frames.py from claude-kevin-king to rebuild transcripts + readable frames (Step 0).
- 2026-10-20, Codex continuation: separate source readers, second source verifier, chart extractor and ongoing code reviewer are active as requested. Their actual coverage and disagreements are recorded in `knowledge-base/study/`; this is targeted first-pass verification, not all-source completion.
- Rebuilt `knowledge-base/STRATEGY.md` as an evidence-qualified first-pass specification; unchanged old draft preserved as `knowledge-base/study/STRATEGY_LEGACY.md`. Do not copy Kevin's next-day-only filter: Bishop explicitly permits same-day confirmation. Source-backed direct 10–11-pip teaching exists in video 3 as well as continuation discussion in video 13.
- Added strict `bishop/replay.py`: matching includes fill, pair, side, timeframe, execution profile, bias, separate setup/fill timing, entry, stop and target. Source tolerances are explicit, with no hidden pip/day relaxation. Unresolved/empty/error coverage cannot pass. The checker compares actual engine observations; it is not a detector or a substitute for running one.
- Initial `tests/bishop_examples.json` contains 40 observations (38 PDF plus two native-video snapshots), including repeated/stacked/chart-vs-broker views; these are not 40 independent executed trades. All remain unresolved until bias, setup/fill UTC timing, source-feed alignment, execution status and independently supported tolerances are established. Thirteen old numerical notes were corrected from rendered PDF labels. Position-tool risk-box edges alone do not prove independent FVG geometry; fixture mode is `teacher_source_stop`.
- Infrastructure corrections: shared-token read-only policy now covers memory fallback; invalid token-table identifiers are rejected; initial SQL schema creates only `bishop_settings`/`bishop_runs`; backfill CLI no longer imports the absent backtest module. Candle ends now use calendar closes, and `candles.completed` excludes forming H1 and higher-timeframe bars. The inherited session clock is FX-specific; weekend-traded assets need a separate policy.
- Development CI runs offline regression tests and the backfill import check; it is explicitly not a successful teacher-replay certificate. `reference/BUILD_REVIEW.md` tracks independent findings and remaining gaps.
- First engine primitives: `bishop/price_action.py` detects two-candle A/V/OC candidates at exact shared body junctions and classifies role-relative touches/sweeps/close breaks. This exact-junction/gap policy is an explicit conservative implementation choice. Availability is the second candle's close; formation candles cannot trigger their own levels. Synthetic/prefix tests and separate reviewer integration tests pass. These are not complete bias, freshness, entry or execution models.
- Source-frame correction: removed ffmpeg midpoint sampling mislabeled as earlier times. Source PTS now drives burned labels, captions and `timestamps.json`; occupied-interval selection handles sparse variable-frame-rate gaps without catch-up samples. Generation is staged and stale sheets are removed on replacement. Five independent source-identity/fractional/VFR/cleanup tests pass. All nine unique Bishop sessions were regenerated: 964 unique frames / 244 sheets (1080 / 273 across ten directories including the duplicate). `bishop_frame_manifest.json` records hashes, native dimensions, source-zero convention, counts and remaining course/plug timestamp limitations. Extraction is complete for this release; exhaustive visual study is still open.
- Validation at this milestone: **124 local regression tests pass**; the first foundation commit `8b762c8` also passed [Bishop development checks](https://github.com/awujo/practicing/actions/runs/39420948570). These are foundation checks, not historical teacher replay acceptance; all 40 source observations remain unresolved and zero historical matches are claimed.

## Open continuation work

- Finish exhaustive source/frame coverage and resolve exact historical example timestamps, feed geometry and demonstrated execution states. Correct frame timestamp sampling before promoting exact timed video observations.
- Implement the causal Bishop detector and execution models from the verified specification, reviewing every increment. Preserve source stops/targets separately from the aggressive operating preset. Never branch on fixture IDs or fill observations from expected values.
- Run every promoted teaching case through the actual detector; no release claim until every verified example matches and unresolved coverage is closed. Then freeze cost assumptions and run supported-pair 2018+ backtests with actual coverage checks (the candle store may otherwise return partial cached history after acquisition failure).
- Build paper runner, hourly/backtest/replay workflows, database bias/entry persistence, Telegram formatting and Mini App. No Bishop live deployment or broker execution has been enabled.

## Offline causal engine milestone (2026-10-20)

- Added causal structure/bias, two supported setup routes, explicit risk profiles,
  coverage validation, bid/ask execution and offline backtest CLI. Choices and
  unsupported routes are reported; no live activation or broker orders.
- Added frozen alternate-feed EURGBP input/provenance and reproducible eight-case
  study. First-close H1 yields 67 candidates/56 observed fills; H2 38/28.
  These overlap and are not portfolio results. Exact-junction variants yield
  no setups. Selected teacher H2 window yields zero setups; all 40 source
  observations remain UNRESOLVED. Fourth-man CE and source clock/feed
  alignment remain open; source expectations were not changed.
- Independent final review reproduced and verified fixes for leading partial
  aggregates and historical actionable-order intervals in no-trade replay.
  Full suite: 204 passed. Reports and scope: `reports/ENGINE_MILESTONE.md`,
  `reference/ENGINE_REVIEW.md`, `reference/FINAL_ENGINE_REVIEW.md`.
- Next: source-grounded fourth-man/remaining entry routes, ERL and major-swing
  rules, exact historical alignment and exhaustive source replay; then broader
  cost-aware historical coverage. Paper runner/UI/integrations remain open.

## Owner-directed full-study phase (2026-10-20)

- Owner clarified sequence: study all material and understand the rules first,
  then build the whole system, then test/correct against teaching examples.
  Further engine implementation is paused; the earlier next-route build plan
  is superseded by this source-study phase.
- Inventory:28unique videos (~14.28hours),866unique existing contact sheets,
  13alternate older ASR transcripts,13supplementary notes,60-pagePDF and4release
  images. Independent readers assigned full transcript and systematic visual
  coverage. See `knowledge-base/study/FULL_STUDY_PROGRESS.md` and per-source
  inventory; enumeration/started jobs are not completed study.
- Corrected course/plug sourcePTS frame extraction runs into separate scratch
  staging while current sheets are read. Original MP4s retained for exact-frame
  ambiguity checks. Do not claim completed extraction without manifest states.
- Source correction: PDFp8's “4thman's CE” label does not by itself establish a
  distinct unimplemented entry algorithm. Its high-swept/low-standing V-pattern
  must be mapped to the lessons; earlier missing-route explanation was too strong.
  No fixture values or engine outputs were changed by this correction.

- Study checkpoint: saved full transcript ledgers for all28unique videos,
  source-backed example narratives,13-note audit, PDF pageledger, four verified
  releaseimages now retained with provenance, primary cross-check and separate
  verifier. Visualstudy remains partial; see exactranges in perreaderreports.
  Working synthesis is not implementation approval. Corrected frame job was
  interrupted with prioragentturn; resumed in root session78088, adopting verified
  completed7/8priorityoutputs and skipping previouslycomplete sources.

## Full sampled-source pass complete (2026-10-23)

- All 28 unique canonical transcripts read end-to-end; all 874 sampled sheet
  positions covered across documented old/corrected/mixed reader versions. All
  60 PDF pages inspected individually at detail, all four images at native
  size, all 13 supplementary notes read. This is not continuous native-video
  viewing, independent double review or historical replay acceptance.
- Completed and published corrected course/plug extraction: 19 verified source
  assets, 2,481 frames / 630 sheets. Together with Bishop: 3,445 unique frames /
  874 sheets. Source and output hashes retained in course_frame_manifest.json;
  old course images remain in Git at dd91b14. No active extraction job remains.
- Dense native cursor evidence plus alternate English ASR resolves v7's key
  old/new-high referent issue: old protected high holds after wick-only weak-low
  take; new lower candidate remains liquidity until the body-break contrast.
  Retained all 21 reviewed native frames and alternate small/medium ASR outputs
  with model revisions/hashes. Network-broken v8 question and plug sponsorship
  negation remain low-confidence; no rule or exception is invented.
- Expanded source specification v0.2, synthesis, chronological example catalogues
  (61 session pair/story segments, not fills), independent verification and
  IMPLEMENTATION_HANDOFF.md. Historical clock/feed/candle-pair gaps remain
  later example-reconstruction work. Teacher expectations were not changed.
- No engine, fixture or test changes in this source-study milestone. Next is
  explicit causal event/numerical contracts, then complete source-route build,
  independent code review and teacher-example replay in the owner's order.
  Existing engine remains partial; no live alerts or broker activation.

- Final independent source-consistency verdict is saved in
  `full_study_verification.md` section8: declared coverage and handoff accepted,
  with old/corrected sample limits, residual speech/p8 uncertainties and numerical
  choices explicit. Ready for contract definition before code; existing engine
  and all40historical observations are not certified by this source review.
