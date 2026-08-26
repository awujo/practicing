# Live deployment: operations log

Chronological record of the live VPS deployment -- what's running, what
broke, what fixed it, and gotchas specific to this exact setup. Written
so a fresh session (a different Claude account, or a human) can read
this instead of needing the original chat history to know what's already
been tried, found, and fixed. `bot/README.md` covers the general
setup/design; this file covers this specific deployment's state and
incident history. Keep entries short -- the full reasoning for any fix
lives in that commit's own message (`git log`), this file just needs to
say what happened and point at the commit. For the whole project's
history before this (strategy extraction, backtest engine build-out,
the live bot's foundation), see [`../PROJECT_HISTORY.md`](../PROJECT_HISTORY.md).

## Current deployment topology (as of 2026-08-26)

- **VPS**: one Docker container named `mt5` (image `gmag11/metatrader5_vnc`),
  running TWO MT5 terminals on the same Wine prefix (see README's
  "Running more than one account" section) -- one per entry style.
- **Repo checkout the container actually runs**: `/srv/slk-bot/mt5data/trading`
  on the host, bind-mounted to `/config/trading` inside the container
  (`docker inspect mt5` confirms the mount: `/srv/slk-bot/mt5data` ->
  `/config`). **Editing `/config/trading/...` from inside the container
  and editing `/srv/slk-bot/mt5data/trading/...` from the host are the
  SAME files** -- no `docker cp` needed for this repo's own Python code,
  a plain `git pull`/`reset` on the host path is enough.
- **Trap**: `/srv/slk-bot/trading` (note: NOT `mt5data/trading`) is a
  SEPARATE, stale, unmounted clone left over from earlier setup work.
  It is NOT what the container runs. Confirmed via `docker inspect`
  before trusting either path -- don't assume, check the mount.
- **Launch scripts**: `/srv/slk-bot/launch_bot1.sh` (conservative,
  account `111379608`, bridge port `18812`, terminal
  `C:\Program Files\MetaTrader 5\terminal64.exe`) and
  `/srv/slk-bot/launch_bot2.sh` (aggressive, account `5054897845`,
  bridge port `18813`, terminal `C:\MT5-Aggressive\terminal64.exe`).
  Both run `docker exec -u abc ... -w /config/trading mt5 python3 -m
  bot.run_live ...`, both currently track ALL 25 supported instruments
  (`DUKASCOPY_INSTRUMENTS` minus `USOIL`/`ETHUSD`, which are unconfirmed
  on this broker).
- **Persistence**: both bots run inside tmux sessions named `bot1` and
  `bot2` on the VPS host (`tmux attach -t bot1` / `capture-pane -t bot1
  -p` to inspect). Launching via a plain SSH foreground command instead
  of through these sessions means the bot dies the moment the SSH
  connection drops -- always relaunch via `tmux send-keys -t bot1
  "bash /srv/slk-bot/launch_bot1.sh" Enter`, not directly.
- **Audit logs**: `conservative_audit.db` / `aggressive_audit.db`,
  SQLite, at `/config/trading/<name>.db` inside the container (same
  bind-mounted host path as above). Untracked in git on purpose (real
  account data) -- `git reset --hard` on the host checkout does NOT
  touch them, confirmed safe.
- **Git housekeeping on the VPS checkout**: it's owned by the
  container's `abc` user, not host `root`, so a fresh `git` invocation
  from the host needs `git config --global --add safe.directory
  /srv/slk-bot/mt5data/trading` once (dubious-ownership check) before
  anything else works.
- **No `git` inside the container** (minimal image) -- all git
  operations (`fetch`/`reset`/`log`) run from the HOST at
  `/srv/slk-bot/mt5data/trading`, relying on the bind mount to reach the
  container's copy. `docker exec ... git` will fail with "executable
  file not found".

## Diagnostic tooling (doesn't touch the VPS)

- `.github/workflows/fetch-data.yml` -- refreshes the Dukascopy data
  cache (hourly, on the hour, or `workflow_dispatch` on demand -- was
  daily until 2026-08-26, bumped to hourly specifically so the check
  below always has genuinely fresh data). Publishes to the `data-latest`
  GitHub release.
- `.github/workflows/check-signals.yml` -- runs `run_backtest()` against
  that cached Dukascopy data only (no MT5 involved) for a given `since`
  time / instrument list / style list, and prints every signal found.
  Built specifically so "did the strategy actually produce a setup this
  week" can be checked without running anything on the VPS (which
  visibly slows down the live bots' own poll loop when tried directly).
  Takes ~25-40 min for the full 25-instrument x 2-style sweep -- use this
  one for an ad hoc, longer-range check.
- `.github/workflows/hourly-signal-check.yml` -- the automated,
  continuous version: fires right after every `fetch-data.yml` run
  completes, checks a rolling 3-hour window across all instruments/both
  styles, and posts the result to that run's Actions job summary (visible
  on the Actions tab without opening logs). This is the reference feed
  to actually compare a live account's `decisions` table against --
  a signal that shows up here with nothing anywhere near it in the
  matching audit database is concrete evidence MT5 is still missing
  something, independent of whether the strategy just didn't find a
  setup that hour. Added 2026-08-26, right after the broker-clock-offset
  fix, specifically to give that fix something to be checked against
  going forward rather than trusting it on faith.
- All three are triggered via the GitHub API (`actions_run_trigger` /
  `POST .../dispatches`) or the Actions tab UI -- no VPS access needed to
  run any of them.

## Incident log

**2026-08-2x -- Filling-mode order rejection.** Real order rejected
with `TRADE_RETCODE_INVALID_FILL`: `place_market_order()` hardcoded
`ORDER_FILLING_IOC`, which the broker didn't support. Fixed to pick
`type_filling` from the symbol's own `filling_mode` bitmask. Commit
`f8b3799`.

**2026-08-2x -- Live cache sync crash, mixed timestamp formats.**
`sync_recent_from_mt5()` wrote plain `.isoformat()` (keeps `+00:00`)
into the same CSV column every other writer uses `Z` for -- pandas
partially parsed the column, leaving some rows as real `Timestamp`s and
others as raw strings, crashing any later `>`/`<` comparison between
them. Fixed to match the `Z` convention everywhere. Commit `20304e2`.
This is what actually killed both bots for the first ~10 hours of live
running before anyone noticed no trades were happening.

**2026-08-25 -- Plain breakouts corrected to close-based, not
wick-based.** Direct correction from the strategy source (Bishop/SLK):
breakouts are read off the LINE CHART (closing prices), matching how
A/V-shape key levels already work -- not the candle's wick extreme.
Backtested both ways across 2025+2026, all instruments, both styles;
close-based won on every metric. Commit `2482da7`.

**2026-08-25/26 -- Cache-file race condition crashed bot1.**
Two bot processes (conservative + aggressive) both call
`cache.append()` for the SAME shared CSV file concurrently. The old
`to_csv(path)` truncated the file in place, so the other process's
concurrent read could catch it empty mid-write ->
`pandas.errors.EmptyDataError`, killing the whole process (no
per-instrument error isolation existed yet either -- see next entry).
Fixed with an atomic temp-file + `os.replace()` write. Commit `900f463`.

**2026-08-26 -- Per-instrument errors no longer kill the whole bot.**
Same commit as above: `run_once()`'s per-instrument loop had zero
exception isolation -- any unexpected error on ONE instrument (of 25)
took the entire process down, including every other instrument and all
future iterations. Three distinct live crashes in one session from
exactly this class of bug is what motivated it. Now wrapped so one
instrument's failure is logged and skipped; the rest keep running.
Commit `900f463`.

**2026-08-26 -- MT5 candle timestamps were broker-server time
mislabeled as UTC.** Found while investigating "zero rows, ever" in
both audit databases (i.e. the live orchestrator had never once reached
a loggable decision in its entire history). `fetch_candles()` did
`pd.Timestamp(r["time"], unit="s", tz="UTC")` -- but MT5's
`copy_rates_from_pos()` reports times in the BROKER's own server clock
(MetaQuotes-Demo runs EEST, UTC+3), not true UTC, despite the raw value
looking like a plain Unix timestamp. Confirmed empirically: a cache file
last-written at `07:44:37` real UTC contained a row timestamped
`09:00:00`. Every live-synced candle was splicing onto Dukascopy's
genuinely-UTC historical data with the wrong period boundaries --
plausible cause of the live bias diverging from what the pure-Dukascopy
backtest saw, independent of the "zero audit rows" question (which
turned out to be self-consistent internally and not fully explained by
this alone -- worth re-checking once the fix has been live a while).
Fixed: `MT5Client` now detects the broker's real UTC offset once per
connection (M1 candle's reported time vs. Python's own UTC clock,
rounded to the nearest hour) and subtracts it from every candle.
Commit `4a0f1bf`. **Not yet confirmed whether audit rows start
populating now that this is live -- check `decisions` table row counts
after this has run through a few H1 closes.**

**2026-08-26 -- ROOT CAUSE of the missed signals: the VPS cannot keep
up with the full-replay architecture.** After the timestamp fix went
live, a real Dukascopy-confirmed signal (GBPNZD, 11:00 UTC, both
styles) was STILL missed, with both audit DBs empty and the cache
hours stale. Investigation ruled out, in order: the offset fix itself
(no errors), a crashed/hung terminal (the MT5 feed was confirmed
healthy and ticking live via a direct API query -- broker clock ~3h
ahead, exactly as expected), and a blocked/hung bot process
(`/proc/<pid>/stat` showed both in state `R`, actively burning ~70-77%
CPU each).

The real cause is architectural. `run_backtest()` is called on EVERY
new H1 candle close, per instrument, per style -- and it re-walks the
ENTIRE cached history each time (see `runner.py`'s own docstring:
`start_date`/`end_date` deliberately do NOT narrow the data load,
because `claimed_origins` bookkeeping and bias-building need it all).
Per instrument that's roughly 143k H1 + 36k H4 + 6k D + 1.2k W ~=
**186,000 candles walked (several times over) to evaluate the ONE
candle that just closed.**

Measured cost: ~50s per `run_backtest` per instrument on a dedicated
GitHub Actions core. This VPS has **2 vCPUs at load average ~7**
(3-4x oversubscribed), 1.4GB of 2GB swap in active use, and the `mt5`
container alone showing 2414% CPU across 266 PIDs (two full MT5
terminals + Wine + WebView2, two `mt5linux` bridges, both bots). That
inflates each run to ~175s+. With 25 instruments x 2 styles, all H1
candles closing simultaneously on the hour, that's ~146 minutes of work
per 60-minute hour -- it can never catch up, which is exactly the
observed behavior (hours-stale cache, no errors, pegged CPU).

Note the cost also GROWS monotonically: every month adds ~720 H1
candles to the array being replayed, forever.

## The planned fix (Stage 2 -- incremental state)

Direct user architectural critique, and it's correct: a Daily bias
cannot change until a Daily candle closes, yet it is currently
recomputed 24x/day; a Weekly bias is recomputed 168x/week. And no
check needs 2003's H1 candles re-walked to know what the current H1
just did. The reference point raised was another SLK-based scanner
(built by "DevT", using IC Markets data) that tracks the last BOS as
state and reacts to the next event, rather than replaying history.

The good news, and why this is a bounded refactor rather than a
rewrite: the detection code is ALREADY sequential state machines
internally -- `detect_confirmations()` walks forward carrying
`last_swing_high`/`last_swing_low`/`claimed_high`/`claimed_low`,
`replay_bias()` carries a `BiasCascade` (`direction`, `origin_time`)
plus `tested_level_times`, and `StructureTracker` carries its own
sweep/break state. That state is small and already exists; it is just
thrown away and rebuilt from scratch on every call. The work is to
expose it, persist it, and resume from it: warm up once from full
history, checkpoint to disk, then feed one candle at a time.

Staged plan:
- **Stage 0 (stopgap, do first):** cut both bots' instrument lists
  down so the box survives. Buys latency, not a fix.
- **Stage 1 (low risk):** timeframe-gated recompute -- only recompute
  the Daily cascade on a Daily close, Weekly on Weekly close, H4 every
  4H. Honestly only ~40-50% of the win, since H1 is the largest array
  and still recomputes hourly.
- **Stage 2 (the real fix):** checkpointed incremental state as above.
  Steady-state cost drops from ~186,000 candle-visits per check to ~1,
  and stops growing with history.
- **Stage 3 (optional):** drop the full trade-lifecycle simulation from
  the live path -- live only needs "did an entry trigger on this
  candle", not the simulated outcome.

The original design's stated reason for full replay was fear of
behavioral drift from the validated backtest. That is directly
testable: assert the incremental path produces bit-identical output to
a full replay over the same data. Known sharp edge to test carefully:
swing detection uses lookahead (`is_swing_high` checks i +/- n), so a
swing is not confirmable until n candles later -- the incremental
version needs a trailing buffer and must treat the last n candles as
provisional.

**Backup branch: `backup/full-replay-architecture`** (at commit
`9e10822`) preserves the entire pre-rewrite state -- the architecture
described above, as actually deployed and running on 2026-08-26.
Restore with `git checkout backup/full-replay-architecture` if the
incremental work needs to be abandoned or compared against.

## Open / worth re-checking

- Confirm the MT5 timestamp fix actually results in the cache's live
  tail landing at sane (non-future, correctly-offset) times, and that
  the audit databases start getting real rows (even declines) instead
  of staying empty. NOTE: as of 2026-08-26 this is still unconfirmed,
  and is now confounded by the resource-starvation issue above -- the
  bots never got far enough through an iteration to log anything, so
  the timestamp fix has not really been given a fair test yet.
- `USOIL` and `ETHUSD` still unconfirmed on MetaQuotes-Demo (not in
  Market Watch under the names checked) -- excluded from both bots'
  instrument lists until confirmed.
- `history_deals_get()`'s exact real-world return shape (used by
  `fetch_closed_deal()` for outcome reconciliation) is still the least
  field-verified piece of `orchestrator.py` -- confirm against a real
  closed trade once one actually happens live.
