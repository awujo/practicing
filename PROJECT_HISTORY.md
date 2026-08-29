# Project history

A chronological narrative of this whole project, phase by phase, with
commit hashes so anyone (a fresh Claude session included) can go read
the actual diff/message for any claim here. `git log` has the full
detail on every commit; this file exists so someone doesn't have to read
all of them just to get oriented. For the live VPS deployment's current
state and incident history specifically, see `bot/OPERATIONS_LOG.md` --
this file covers the whole arc, that one covers "what's running right
now and what's broken/fixed on it."

## Phase 1: Strategy extraction (Aug 14-15)

Source material: a mentor's ("Bishop") video course, ingested via
`.github/workflows/transcribe.yml` (upload video as a GitHub Release
asset -> transcribed with `faster-whisper` on GitHub's infra, since
transcription needs huggingface.co, which most sessions' network policy
blocks). Each video got: a raw transcript, written analysis notes, and
then a **frame-by-frame visual verification pass** against the actual
video/PDF material -- notes were corrected more than once after a visual
check caught something the transcript alone missed or got wrong (e.g.
`5fd06ad` "Correct plug-and-play notes after a visual frame check",
`3a3e19c` "Frame-by-frame visual re-verification of the Bishop
chart-examples PDF, all 60 pages"). Videos covered: plug-and-play,
bias-entries, what-next, repeating-system, trades-breakdown-2/3,
building-bias-1/2, entries-part5, daily-routine, plus two numbered
videos. All of it consolidated into `knowledge-base/STRATEGY.md`, the
cumulative rulebook everything downstream is built from.

Key commits: `a450f11`..`3a3e19c` (the transcript/notes/verification
commits), `664a98a` (multi-video release support in the workflow).

## Phase 2: Backtest engine build-out (Aug 15-16)

Turning STRATEGY.md's rules into working, tested code
(`backtest/engine/`). This wasn't one pass -- several real bugs were
found and fixed as the engine matured:

- `5c2974b` Fixed a stop-loss inversion bug that was causing win-rate
  and total-R to visually disagree on the dashboard.
- `5964825` Rebuilt entry logic to actually enforce Bishop's
  liquidity-cascade gate (a real rule, not previously enforced).
- `8013bc6` / `81e1293` Anchored stop-loss placement to the setup's own
  liquidity point / imbalance, instead of an arbitrary buffer.
- `a1cc490` Fixed a real hang: reaction-level candidates weren't bounded
  to the current structural leg, so the search could run unbounded.
- `a7a6c29` Wired `ranking.py`'s 4-factor scoring into reaction-level
  selection (so multiple valid reaction levels get ranked, not just
  taken in an arbitrary order).
- `d8764c4` Bound imbalance matching by time -- found via the trade
  chart viewer (see below): an imbalance from years earlier/later could
  match purely on price overlap, corrupting stop distance.
- `856330c` / `fb5641e` Added an on-demand trade-chart viewer, deployed
  to Render, and made it viable on Render's free tier (260MB+ full data
  bundle was replaced with small per-instrument slices) -- this became
  the actual tool used to visually catch several of the bugs above.

**The "entry-gate rebuild", a deliberate 7-part series** (`fddaeab` ..
`b7a0b69`), each commit message tagged `(entry-gate rebuild, part N/7)`:
multi-timeframe alignment gate, sequential-nearest-first reaction-level
selection (replacing an earlier scored pick), the 4th-man confirmation
trigger detector, origin/continuation classification by literal
sequence (not a time window), stop-loss keyed to trigger type, the 1:3
target capped at real external-range liquidity (ERL), and a full
stop/target decision audit trail surfaced on the dashboard.

Follow-up fixes after that series: `6ebcc76` (ERL redefined as
Daily/Weekly PERIOD extremes, not H4 swing fractals -- a real
correctness fix, not a style choice), `88d2412`/`7abc982` (year/date-range
filtering, tz-aware date bugs), `137dfde`/`e025d37` ("run a new backtest"
wired into the Render viewer via GitHub Actions, then a fix for its 500
error), `6a57f4e` (mae_r overshoot on the stop-triggering candle).

## Phase 3: Live bot foundation (Aug 16-19)

`6d83f88` started `bot/`: `config.py` (account/phase profiles),
`risk_manager.py` (the live risk gate, validated first as an OFFLINE
analysis against real 2026 trade data before being trusted live),
`audit_log.py` (SQLite decision log, schema deliberately matching the
backtest's own `TradeRecord`).

Then the MT5-specific I/O layer, each piece explicitly built and
committed as "untested against a live terminal" since no MT5 connection
was reachable from the development sandbox at the time:
- `cdad265` `mt5_data.py` -- candle fetching, new-candle-close detection
- `ea3cd2d` `mt5_execution.py` -- lot sizing, order placement
- `adde49a` `live_cache_sync.py` -- the key design decision: rather than
  re-deriving the strategy's entry logic incrementally for live
  "streaming" use (real behavioral-drift risk vs. the validated
  backtest path), this keeps the SAME on-disk cache `run_backtest()`
  reads from topped up with fresh MT5 candles, and the orchestrator just
  calls `run_backtest()` itself, unmodified.
- `859bc72` `orchestrator.py` + `run_live.py` -- the live loop wired
  end-to-end for the first time.
- `a6de796` `mt5linux` bridge support, for the Ubuntu VPS deployment
  target decided on (MT5 has no native Linux client).
- `1e0bfcb` Fixed symbol mapping: a suffix alone can't express an actual
  rename (NAS100 -> USTEC, JP225 -> JPN225 on the real broker checked).

## Phase 4: First live validation (Aug 22-24)

Once actually connected to a real MT5 demo terminal, real bugs surfaced
immediately that no amount of unit testing against a fake could have
caught:

- `f8b3799` A real order got rejected (`TRADE_RETCODE_INVALID_FILL`) --
  hardcoded `ORDER_FILLING_IOC` wasn't supported by this broker; fixed
  to read the symbol's own `filling_mode` bitmask.
- `34d9535` Made the ERL target cap optional, after backtesting both
  ways across years/styles to check for a consistent edge (kept the cap
  -- no consistent edge either way, but no reason to remove it either).
- `a3aa4ad` / `08cb89b` Multi-account VPS setup: running two MT5
  terminals (conservative + aggressive entry style, in parallel, same
  VPS) surfaced a real gotcha -- `mt5.initialize()` with no path
  silently resolves to the WRONG terminal once more than one exists on
  the same Wine prefix. `--terminal-path` became mandatory for every
  account after a test order was silently placed on the wrong one.
  `bot/README.md` rewritten to match what actually worked end-to-end
  (the manual Wine install attempt was abandoned after hours stuck; the
  Docker route worked first try).
- `20304e2` Fixed a live cache sync crash: mixed ISO timestamp formats
  in the same CSV column (`+00:00` vs `Z`) made pandas partially fail to
  parse it, crashing any later time comparison. This one killed both
  bots for their first ~10 hours of live running before anyone noticed.
- `cc4eed9` Added the `check-signals.yml` GitHub Actions workflow --
  lets "did the strategy produce a setup recently" be checked entirely
  on GitHub's infra, against cached Dukascopy data, without touching the
  VPS (running the same check directly on the VPS visibly slowed down
  both live bots' own poll loops).

## Phase 5: Close-based breakouts + the live crash cluster (Aug 25-26)

`2482da7` A direct correction from the strategy source: breakouts are
read off the LINE CHART (closing prices) throughout, matching how
A/V-shape key levels already work -- not the candle's wick extreme.
Backtested both ways (2025+2026, all instruments, both styles) before
committing; close-based won on every metric.

Then, within about 24 hours, three distinct uncaught-exception classes
crashed a live bot process -- see `bot/OPERATIONS_LOG.md` for the full
incident-by-incident account, this is just the summary:
- `900f463` A cache-file write race between the two concurrent bot
  processes (fixed with an atomic temp-file write), bundled with a
  defensive fix so one instrument's unexpected error can no longer take
  the entire process down with it.
- `4a0f1bf` MT5 candle timestamps turned out to be the broker's own
  server clock (EEST, UTC+3 on this broker) silently mislabeled as UTC
  -- found while investigating why the live audit databases had ZERO
  rows in their entire history. Now auto-detected and corrected per
  connection.
- `2820480` `bot/OPERATIONS_LOG.md` added -- the deployment topology and
  incident log going forward lives there, not in this file.

## Phase 6: Backtest lookahead-bias fix (Aug 28)

Direct question: does `run_backtest()` follow the same decision flow as
the live bot candle-by-candle, given the whole candle array already
exists in memory during a backtest? Mostly yes, with one real exception,
found by checking rather than assuming: `is_swing_high()`/`is_swing_low()`
(`structure.py`) and `is_close_peak()`/`is_close_trough()`
(`key_levels.py`) are fractal tests that genuinely can't be known until
`n` bars after the pivot forms -- their own docstrings already said so
-- but `detect_confirmations()`, `StructureTracker.run()`, and
`structural_liquidity_points()` all activated the resulting swing
point/key level starting at the pivot's OWN bar, not `n` bars later when
a live process would actually have that information.

`1617afb` fixed it: `SwingPoint` and `KeyLevel` both gained a
`confirmed_at` field (None = no lag, for open-close/4th-man levels which
really are known immediately) and a `known_at()` helper; the activation
loops shifted by `n`; every consumer that filters/bisects by time for
ELIGIBILITY (`replay_bias()`, `_find_liquidity_setups()`) switched from
raw `.time` to `known_at()`. `.time` itself is untouched everywhere --
still correctly reports when a point actually formed, only when it
becomes USABLE changed. All 111 existing tests passed unmodified.

Measured, not assumed (`.github/workflows/compare-lookahead-fix.yml`,
old_ref `b9b55ff` vs the fix, same data snapshot, all 25 instruments,
both styles, 2025-2026): the fix was real but small in practice --
2,528 trades/53.4% win/+2,688.7R (buggy) vs 2,684 trades/51.9% win/
+2,665.3R (fixed), a 23.4R (0.9%) difference. Delaying a level's
activation doesn't suppress signals, it changes which level is briefly
in play, which can go either way -- confirmed here rather than guessed.
Current (fixed) engine's own standalone total is now the reference
figure for "the live bot's 2-year performance": **+2,665.3R, 51.9% win
rate, 2,684 trades**, all 25 instruments/both styles combined.

## Where things stand

Both bots (conservative + aggressive style, prop-firm phase1, 25
instruments each) are live on a VPS demo account as of the most recent
entry in `bot/OPERATIONS_LOG.md`, which is the source of truth for
current state -- check there, not here, for "is it working right now."
