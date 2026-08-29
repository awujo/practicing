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

**2026-08-26 -- FIXED, in two parts.** Profiling first (rather than
acting on the hypothesis below) corrected a wrong assumption recorded
in this file: the cost was NOT dominated by the 155k-candle H1 walk.
`detect_confirmations(h1)` is 0.67s, under 2%. The actual profile of one
EURUSD run_backtest was:

    _find_liquidity_setups   24.72s  (71.4%)
    replay_bias(daily)        7.20s  (20.8%)
    detect_confirmations(h1)  0.67s   (1.9%)

Both hot spots were plain **quadratic scans over already-sorted lists**,
not an architectural problem at all:
- `_find_liquidity_setups` scanned every liquidity point AND every H4
  key level once per breakout (~4,000 breakouts) -- tens of millions of
  comparisons; it also materialised every matching point just to take
  `[0]`.
- `replay_bias` scanned every key level once per candle and, worse,
  rebuilt a full list of every future confirmation just to take the
  first five of it, once per level tested.

Fixed with `bisect` lookups into bounded slices (commit `e8572cf`):
**238.0s -> 75.0s across three instruments x two styles (3.2x), with all
3,328 trade records bit-identical** to the pre-optimisation output.
`_find_liquidity_setups` alone went 24.72s -> 0.11s (225x).

Then the storyline gate (commit `ed9d8f1`, `bot/live_strategy.py`) --
the architectural half, described below. Measured together, the live
loop's daily cost on this box drops from roughly 58 CPU-hours (against
48 available, hence the death spiral) to about 5.5 -- with all 25
instruments kept and no VPS upgrade, both of which the user explicitly
required.

## The fix, part 2 -- the storyline gate (implemented)

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

What shipped: `bot/live_strategy.py` derives the Weekly/Daily/H4 bias
context (touching **no H1 data at all**) and `storyline_at()` answers
"is this pair in the hunting stage?" -- HUNTING requires Daily and H4 to
each independently confirm the same direction AND the effective
highest-priority bias to agree, which is exactly what `run_backtest()`'s
own entry loop demands before it will consider any candidate. Weekly is
recorded when it aligns (a booster, not a gate), matching the entry
loop.

`orchestrator._storyline_says_hunt()` caches that context per instrument
and rebuilds only when a Weekly, Daily or H4 candle closes -- ~7 times a
day rather than the 24 full `run_backtest()` calls it replaces. H4 must
count as a rebuild trigger because the Daily cascade's flip test
consumes H4 confirmations (`replay_bias(daily, ..., h4_confirmations)`),
so rebuilding on Daily closes alone would not be sound. Storyline
transitions are logged at INFO (the "red flag" list, visible in the
bot's log); steady state is silent.

Measured on real history: the gate costs **0.10-0.15 ms** per check
versus tens of seconds for `run_backtest`, and **~70% of H1 closes are
"still waiting"**, so that share of the expensive search disappears.

**The safety property, and how it is enforced.** The gate is only ever
allowed to be a performance filter, never a strategy change -- it must
have no false negatives. That is tested against real multi-year cached
history rather than fixtures (`test_gate_never_suppresses_a_trade_the_
real_backtest_produces`): every one of **3,328 real trades** that
`run_backtest()` produces across EURUSD/GBPJPY/GBPNZD x both styles
falls inside a window where the gate said HUNTING. Zero suppressed.
That test skips when the gitignored candle cache isn't present, so run
the fetch-data workflow (or download the per-instrument release assets)
before trusting a local green run.

**Not done, and not currently needed.** The originally-planned
checkpointed-incremental-state rewrite was NOT built -- profiling showed
it would have been solving the wrong problem. It remains the right move
only if the cost ever becomes a problem again; the notes above about
`claimed_origins` being history-dependent and swing detection needing
`i +/- n` lookahead (so the last n candles stay provisional) still apply
if anyone picks that up. A cheaper unbuilt option first: `run_backtest`
still simulates every historical trade on each live call, and live only
needs "did an entry trigger on the latest candle" -- but note the
`claimed_origins` bookkeeping deliberately only claims a slot AFTER the
stop-on-correct-side guard passes, so that simulation cannot simply be
skipped for older candidates without changing origin/continuation
classification.

**Backup branch: `backup/full-replay-architecture`** (at commit
`9e10822`) preserves the entire pre-rewrite state -- the architecture
described above, as actually deployed and running on 2026-08-26.
Restore with `git checkout backup/full-replay-architecture` if the
incremental work needs to be abandoned or compared against.

## 2026-08-26 evening -- what the live box actually taught us

Deploying the gate did NOT fix the lag on its own, and chasing that down
found two further problems plus one self-inflicted one. Recording the
numbers because every wrong turn came from trusting a dev-sandbox
timing instead of benchmarking on the VPS, which is **19-40x slower**
(it is swapping) and therefore has a completely different cost profile.

**The real bottleneck: `cache.append()` rewriting the whole file.**
Benchmarked on the VPS, adding 10 candles to EURUSD's 9.4MB / 155k-row
H1.csv took **36.40s** (15.80s `pd.read_csv` + 2.30s concat/dedupe/sort
+ 18.30s `to_csv`) -- per granularity, per instrument, per sync, on two
bots sharing the files. `sync_recent_from_mt5()` runs BEFORE the gate,
so no amount of gating could ever have helped. Fixed with a tail-read
plus append-only fast path (commit `ec8e8cb`): the same call is now
**0.001s**. Note the same 18-second `to_csv` window is what made last
night's `EmptyDataError` crash likely in the first place -- the
concurrency bug was a symptom of this, not a separate issue.

**`replay_bias` was still quadratic after the first fix.** The earlier
bisect pass bounded the scan by TIME, but levels that never qualify are
never marked tested, so each candle still re-walked them all. The
dominant filter is `c.low <= level.price <= c.high`, so the index
belonged on the PRICE axis. `build_htf_context()` on the VPS:
**131.61s -> 19.69s** (commit `fb16cc4`), i.e. a rebuild wave across 25
instruments went from ~55 min to ~8.2 min per bot. Waves happen only on
W/D/H4 closes (~7/day), so that is roughly 4% of the box's daily
capacity rather than more than 100%.

**Self-inflicted: root-owned lock files.** Diagnostic commands run as
`docker exec mt5 ...` (no `-u abc`) created `.lock` files owned by root;
the bots run as `abc` and then hit `PermissionError` on every EURUSD
iteration. The per-instrument exception isolation added earlier caught
it, so the loop survived -- but EURUSD silently stopped syncing all
evening. `_file_lock` now degrades to running unlocked with a warning
rather than raising. **Always use `docker exec -u abc` for anything
touching /config/trading/backtest/data.**

### Standing lesson

Profile on the box that is actually struggling. Three separate
hypotheses formed from sandbox timings -- "the H1 walk is the cost",
"this needs an incremental-state rewrite", "these are rebuild storms" --
were all wrong, and each cost hours. The three fixes that mattered were
each found within minutes of running a benchmark on the VPS itself.

## 2026-08-27 -- audit-log schema change (no migration needed)

`DecisionRecord.trade_kind` was removed (see backtest/README.md for why
the whole origin/continuation classification went). The live audit
databases on the VPS already have a `trade_kind` column, and they keep
it: `_ensure_schema()` uses `CREATE TABLE IF NOT EXISTS`, so an existing
table is never altered, and the column is nullable TEXT with no
constraint. New inserts simply omit it and it lands NULL. Nothing to
migrate, no rows to rewrite, and old rows keep whatever they had.

The one thing to know when reading the data later: `trade_kind` is
present-but-NULL for anything logged after this date, and present-and-
populated for anything before. In practice that boundary is academic --
the live databases have essentially no rows yet (see the note below
about the bots never completing an iteration).

## The VPS is NOT dedicated to the bots (found 2026-08-27)

`crontab -l` on the host shows a full production PHP application
(`kugo-backend`) sharing this box, with jobs on aggressive schedules:

    */1  broadcast_riders.php          every minute
    */2  release_stuck_deliveries.php
    */5  retry_stuck_payouts.php
    */15 auto_confirm.php
    plus several hourly/daily pushes

This reframes the resource starvation diagnosed on 2026-08-26. The
working assumption then was "two bots contending for 2 vCPUs". The real
picture is two bots contending with another live application that wakes
up at least once a minute, forever. It is very likely the direct cause
of the swapping that made a `pd.read_csv` 19x slower here than the same
read in a dev sandbox -- the measurement that made no sense at the time
and got written off as "the box is contended".

Nothing about the fixes changes: the cache append, the bisects and the
storyline gate were all real wins and the 7.3x on a full 27-instrument
sweep is measured. But two consequences are worth holding onto:

- **Headroom is thinner than "2 vCPUs" implies.** Any future estimate of
  what this box can carry (more instruments, shorter poll intervals, a
  third style) has to account for kugo-backend, not just the bots.
- **Benchmarks here are noisy by construction.** A timing taken while
  the `*/1` job happens to be running is not comparable to one taken
  between. Repeat measurements before concluding anything from a single
  number -- which is a sharper version of the standing lesson below.

NOT acted on, deliberately: nothing here has been changed or moved.
kugo-backend is somebody's production service and the trading bots are
the guests on this machine. Raised for the record and for whoever
decides whether these two workloads should share a box at all.

## GitHub's hourly schedule is not hourly (measured 2026-08-27)

`fetch-data.yml` is `cron: "0 * * * *"`. What it actually did, on the
day the staleness check first fired:

    08-26 11:34 -> 13:01    1.4h
          13:01 -> 14:49    1.8h
          14:49 -> 16:21    1.5h
          16:21 -> 19:07    2.8h
          19:07 -> 22:56    3.8h
          22:56 -> 04:28    5.5h
    08-27 04:28 -> 16:17   11.8h

GitHub's `schedule` event is best-effort and gets heavily delayed under
load; there is no way to make it reliable from our side. Two things had
been quietly built on the assumption that "hourly" meant hourly:

1. **The reference feed had holes.** `hourly-signal-check.yml` looked
   back only 3 hours. Across that 11.8h gap, every signal in the
   uncovered ~9 hours was never published -- while the feed still
   presented itself as ground truth for "did the bots miss anything".
   Fixed by widening the window to 36 hours, which costs NOTHING:
   `check_recent_signals` runs the full backtest per instrument anyway
   and post-filters on entry_time, so the window is a display bound and
   not a work bound. The 3-hour figure bought no speed and cost
   coverage.

2. **The staleness alarm was tuned to fiction.** It fired on its first
   live run at 4.4h -- a false alarm, since 3.8h and 5.5h gaps are
   routine here. Raised to 8h, which still catches a pipeline that has
   genuinely died but tolerates every delay short of the worst observed.
   A test pins the measured gaps so tightening it back to "hourly" has
   to be deliberate.

The general lesson, and it is the same one this log already records
about profiling: measure the thing rather than trusting its label. The
cron expression says hourly, the workflow is named "Hourly signal
check", and neither is a fact about how often it runs.

Consequence worth knowing: with a 36-hour window the same signal
reprints in every reconciliation for up to a day and a half, and a
genuine miss will be re-reported many times. That is noise in a log
file, not duplicated problems.

## Signal reconciliation (added 2026-08-27)

The check that answers "did the strategy find something the bots
missed?" without needing the two halves compared by hand.

How it fits together:

1. `hourly-signal-check.yml` already computes the Dukascopy reference
   signals hourly. It now also writes them as JSON and force-pushes that
   to the `signal-feed` branch (a few KB, single commit, no history).
2. On the VPS, `python -m bot.reconcile_signals` fetches that branch,
   reads both audit databases, and pairs each published signal with the
   `entry_attempt` row that answered it -- reporting SEEN, LATE (with
   the lag in minutes) or MISSING.

The feed arrives as a git branch deliberately: the VPS checkout already
has working credentials for this remote and no API token, so `git fetch`
+ `git show` needs nothing new configured. Computing the signals ON the
VPS was considered and rejected -- it means a 278MB download plus a
25-instrument x 2-style sweep on the same two oversubscribed vCPUs the
bots are already short of (the mistake bot/README.md's VPS section
already documents).

Run it by hand:

    cd /srv/slk-bot/mt5data/trading && python3 -m bot.reconcile_signals

Or hourly, quiet unless something is actually wrong (cron mails only on
output, and `--quiet-when-clean` prints nothing on a healthy run, so a
message in your inbox always means something needs looking at):

    17 * * * * cd /srv/slk-bot/mt5data/trading && /usr/bin/python3 -m bot.reconcile_signals --quiet-when-clean >> /var/log/slk_reconcile.log 2>&1

Redirected to a log file rather than relying on cron mail: every other
job on this host does the same, which is good evidence mail isn't
configured here. Without the redirect a healthy run and a broken feed
would both be silent -- the exact confusion the separate exit codes (0
clean / 2 feed broken / 3 feed never published) exist to prevent. Check
it with `tail /var/log/slk_reconcile.log`; empty means every signal was
seen on time.

Reading the output:

- **SEEN** -- the bot logged an entry_attempt for that instrument within
  the match window. A row that says `decline_*` still counts as SEEN:
  the bot saw the setup and the risk manager said no, which is a healthy
  outcome. Whether the decline was correct is a separate question.
- **LATE** -- logged, but more than 90 minutes after the entry candle.
  This is the lag symptom, not a data-loss one.
- **MISSING** -- no row anywhere near it. The bot never saw it.
- **No signals published** -- reported explicitly as the CORRECT outcome
  rather than silence, because an empty audit database on an hour when
  Dukascopy also found nothing is not a symptom, and reading it as one
  is how this check would get ignored.
- **STALE FEED** -- the feed hasn't been republished in over 3 hours
  (`--max-feed-age-hours`). This is an alarm in its own right, and it
  fires even when every signal in the stale feed was matched. Without
  it, a publishing pipeline that quietly died would freeze
  `generated_at` and every later run would report "0 signals -- all
  clear" against a window that stopped moving, forever: a dead check
  wearing the costume of a healthy one. The header always prints the
  feed's age so the state is visible even below the threshold.

Baseline as of 2026-08-27, run against the real audit state for the
2026-08-25 to 26 window: **0 seen, 1 late, 8 missing.** The one late is
EURCAD conservative -- Dukascopy's signal is on the 17:00 candle and the
bot's row landed at 20:01, +182 minutes. The aggressive bot logged none
of its four. That is the number this is meant to drive to zero, and it
predates the 2026-08-27 09:18 restart that first put both bots on the
fully-fixed code with no backlog.

## 2026-08-28 -- root cause found: missed signals had no audit trail at all

The 36-hour signal-feed window (see above) surfaced the real test case:
6 genuine setups across 2026-08-26/27, both entry styles (12 published
signals), and reconcile_signals reported ALL TWELVE `MISSING` -- not
late, not declined, nothing. Given the bots' own H1 cache was current to
within the hour when checked, that ruled out "the bots are just behind"
and pointed at something dropping specific candles outright.

Full tmux scrollback for both bots showed the real state: 150 and 158
`reconnect failed: mt5.initialize() ... Terminal: Authorization failed`
lines against only 14 and 13 successful `reconnected to MT5` recoveries,
independently on both terminals/accounts (different Wine paths, ports,
logins) -- something upstream of this repo is periodically revoking or
refusing the MT5 session, and `run_once()`'s fail-closed design correctly
does nothing while that's happening: `is_healthy()` false means the
per-instrument loop never runs at all that iteration, on either bot.

The actual bug was in what happens on the NEXT successful poll.
`MT5Client.new_candle_closed()` reports only the single most-recently
seen H1 bar (own docstring: "then None on every subsequent call until
another one closes") -- it is a one-slot watermark, not a queue. If two
H1 candles close during a reconnect storm, only the newer is ever
reported. `_check_instrument()` then matched entries with
`r.entry_time == new_candle.time` -- exact equality against that one
candle only. `run_backtest()` still had the earlier signal (it replays
full deterministic history on every call), but nothing ever asked for
it: the older candle's trade was silently dropped, no exception, no log
line, no audit row, forever. AUDCAD and EURUSD both missing on the exact
same 13:00 candle is consistent with one storm spanning that hour on
both bots.

A second thing found in the same code and worth recording precisely
because it looked alarming and wasn't: `r.status != "still_open"`
alongside the entry_time check. `TradeRecord.status` is only ever
`"open"` / `"closed_win"` / `"closed_loss"` / `"closed_breakeven"` --
`"still_open"` is a completely different field (`exit_reason`). The
comparison was therefore always `True` and filtered nothing. Removed as
dead/misleading code, not because it caused anything.

**The fix**: `LiveBot` now tracks `_last_entry_time` per instrument --
the newest candle actually evaluated last time. Once set, a check widens
its match from "exactly the candle that just closed" to "everything with
`entry_time` after the watermark, up to and including this candle" --
so any candle skipped by a reconnect storm gets picked up on the next
successful poll instead of vanishing. The FIRST check for an instrument
in a process's lifetime (no watermark yet) still uses exact-match only,
deliberately: matching "everything run_backtest() has ever produced"
on a cold start would replay every historical trade back to whenever
the cache begins. A full process restart resets the watermark and
re-enters that cold-start behavior; an in-process reconnect does not,
which is exactly the gap this closes.

**Known residual gap, not fixed here**: the storyline gate
(`_storyline_says_hunt`) is still evaluated only at `new_candle.time`,
not at every candle in a skipped stretch. A signal whose own candle
would have passed the gate, but whose bias has since moved on by the
time polling resumes, could still be missed. The live evidence for this
incident doesn't implicate it -- the gate logged "hunting" on both sides
of every gap involved -- and fixing it properly means replaying the gate
hour-by-hour across the gap, a bigger change than this evidence
currently justifies. Worth revisiting if a future MISSING signal shows
the gate closed between the skipped candle and the recovery.

**Separately, still open**: WHY the MT5 sessions keep losing
authorization on both independent terminals is not diagnosed here. This
fix stops a dropped connection from also silently dropping trades, but
it doesn't stop the connection from dropping.

One thing IS confirmed by reading `mt5_data.py`'s `connect()`, though:
the failure is `mt5.initialize() failed`, not `mt5.login() failed`.
`initialize()` is called with no credentials at all -- it only attaches
to the already-running `terminal64.exe`. So this rules out a stored
password/typo on our side: the already-running terminal itself is
reporting it isn't authorized, before our code ever gets a chance to
attempt a fresh login. Whatever is wrong is happening between the GUI
terminal and MetaQuotes-Demo's servers, outside anything this repo
controls -- and there's no way from these symptoms alone to tell "the
VPS is starving the terminal of CPU/network responsiveness closely
enough that the broker's session keepalive times out" from "MetaQuotes-
Demo's free public pool is just flaky." Both are consistent with what's
been observed; nothing here distinguishes them.

## 2026-08-28 -- reconnect backoff (doesn't fix the cause, stops compounding it)

`_try_reconnect()` had no backoff: `run_live.py`'s POLL_SECONDS=5 poll
loop meant a real `mt5.initialize()` attempt fired every flat 5 seconds
for as long as the account stayed unhealthy, forever. The two storms
that produced the missing-signals incident above were 150 and 158
consecutive failures -- 12+ minutes of IPC/network calls thrown at an
already-failing terminal, on a VPS with already-documented resource
contention, during precisely the window it needed that load least.

Added exponential backoff between actual reconnect attempts (not
between `run_once()` polls -- `is_healthy()` is still checked every
cycle; `_try_reconnect()` itself now just returns immediately, without
attempting `connect()`, while inside its own backoff window).  First
retry after going unhealthy is still immediate, matching the old
behavior for the common one-off blip; the delay only grows on repeated
failure -- 5s, 10s, 20s, 40s, capped at 60s -- and resets the moment a
reconnect actually succeeds, so a later, independent outage starts from
5s again rather than continuing wherever the last one left off.

This is explicitly NOT a fix for the auth failures themselves -- it's
confirmed to only reduce load during an outage that's already
happening, and is offered as that: a safe, root-cause-agnostic
mitigation, not a diagnosis. If the failures are broker-side, this
changes nothing about their frequency, only how hard the bot hammers the
terminal while they're occurring. Covered by 5 new tests: immediate
first retry, no wasted attempts inside the backoff window, the delay
sequence itself, reset-on-success (and that a later failure restarts
from the base delay, not from where the prior outage left off), and that
`run_once()`'s own per-poll health check is unaffected by the backoff
living inside `_try_reconnect()`.

## 2026-08-28 -- Telegram notifications added

`bot/telegram_notify.py`: a `logging.Handler` on the `"bot"` logger,
rate-limited (MIN_SEND_INTERVAL=3s, batches anything queued in that
window into one message rather than one HTTP call per line), stdlib
`urllib` only -- no new dependency. Opt-in via `TELEGRAM_BOT_TOKEN` +
`TELEGRAM_CHAT_ID` env vars; a no-op with neither set.

Two gaps had to be closed for "log everything going on" to actually mean
that, not just "whatever already happened to call logger.warning()":
entry decisions/declines/halts/phase-transitions all funnel through
`_log_event()` already, so one `logger.info()` call added there covers
all of them for free -- but trade EXITS (wins/losses) only ever reached
`audit_log.update_outcome()` directly, never the standard logger at all,
so a closed trade would have been invisible to this no matter what the
handler did. `_record_closed_trade()` now also logs the outcome
(instrument, exit reason, R multiple, $ P&L).

**A live secret was pasted directly into this session's chat during
setup.** Treated as compromised on the spot -- never used as-is, no
committed file, README instructs regenerating via BotFather `/revoke`
before use. Worth restating for whoever reads this later: any credential
that has ever been pasted into a chat (with an AI assistant or anyone
else) should be rotated, not reused, regardless of whether it "looks
like" it leaked anywhere -- there's no way to confirm it didn't.

## 2026-08-28 -- Telegram messages enriched to the full "thought process"

Direct follow-up to the notification setup above: "everything going on
... thought process, structure alignment, storyline change, storyline
alignment, confirmation, entry, exit stop loss, any errors, any problem
logging in." The event-level coverage (via `_log_event`'s single funnel
and `_record_closed_trade`'s new line, previous entry) already covered
WHICH events reach Telegram; this covers WHAT each one says.

Every entry_attempt already carries the strategy's full read of the
setup as DecisionRecord fields -- bias per timeframe, the effective
timeframe, which timeframes aligned, the confirmation trigger, the key
level, stop, target -- populated via `_audit_fields_from_trade_record()`
and written to SQLite, but the log LINE only ever said e.g. "EURUSD:
entry_attempt (allow) -- placed". `_describe_event()` now builds the
full multi-line message from that same data for entry_attempt events --
present whether the entry was allowed, declined, or failed to place,
since the risk manager's decision is a separate question from what the
strategy actually saw. The closed-trade line also gained entry/exit
price side by side, not just the outcome, so a message reads as a full
round-trip rather than a bare number.

Confirmed as a genuinely separate axis from "which events get sent":
`--telegram-level` (the previous entry's addition) controls WHICH lines
reach Telegram at all; this controls how much each one says once it's
selected. Both are required together for "everything" -- INFO level
with the terse messages would still show every entry/exit, just without
the reasoning; the rich messages at WARNING level would never fire at
all, since entry_attempt is logged at INFO.

3 new tests assert the actual rendered text (bias breakdown, confirmation
trigger, aligned timeframes, stop/target, entry->exit price pair), not
just that a log call happened. 320 tests pass total.

## 2026-08-29 -- order rejections: prices weren't snapped to the broker's tick grid

USDCHF, EURJPY (x2), and AUDCAD orders all rejected with
`TRADE_RETCODE_INVALID_STOPS` between 07:11 and 07:22 UTC. `entry_price`/
`stop_loss`/`target_price` come straight from the strategy's own
pip-padding arithmetic (`entries.py`), which routinely produces ordinary
binary-float noise -- e.g. `159.44850000000002` instead of `159.4485`,
confirmed directly in one of the rejected orders' own Telegram log line
(`target 185.85499999999996`). Nothing before this rounded those prices
to the symbol's actual tick grid before `order_send()` -- MT5 rejects a
sl/tp that doesn't land exactly on it, outright.

**Fixed**, `13e2d23`: `MT5Execution.place_market_order()` now snaps all
three prices via a new `_round_price()` helper (prefers `symbol_info().
digits`, falls back to deriving a grid from `.point`) before building the
order request. New regression test reproduces the exact USDJPY-shaped
float-noise case. **Needs `git pull` + bot restart on the VPS to take
effect** -- not live until then.

## 2026-08-29 -- a second, live-confirmed instance of the storyline gate's documented residual gap

`bot/reconcile_signals.py` showed 6 signals (GBPJPY 08-27 22:00, USDJPY
08-28 07:00, NZDUSD 08-28 13:00, both styles) MISSING with **zero**
audit trail -- not even a decline. Different from the watermark bug
fixed 2026-08-28: these postdate that fix, and Telegram (logging since
08-28 10:45 UTC) shows why for the one case inside its window: a
reconnect storm spanned NZDUSD's 13:00 candle (warnings from 13:11
through at least 14:05 UTC, several back-to-back cycles). The storyline
gate passed at 13:00 -- but the recovery poll landed on a later candle
where the gate had moved back to `waiting_htf`, so `_check_instrument`
returned before `run_backtest()` was ever called. No watermark was ever
set for that hour, so the existing watermark-widening fix had nothing to
widen -- this is exactly the "known remaining gap" that fix's own
docstring flagged and deliberately left unfixed, pending live evidence.
This is that evidence.

**Fixed**, see commit following this entry: new
`_storyline_hunted_anywhere_in_gap()` replays the (cheap, sub-millisecond)
gate at every H1 candle between the watermark and the recovery candle,
not just the recovery candle itself -- checking the recovery candle
first so the common no-gap case pays nothing extra (a dedicated test
asserts `load_candles()` is never even called on that path). **Needs
`git pull` + bot restart on the VPS to take effect.**

GBPJPY (08-27 22:00) and USDJPY (08-28 07:00) predate Telegram logging,
so there's no direct evidence for those two specifically -- plausible
same cause, not confirmed the same way.

## Open / worth re-checking

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
