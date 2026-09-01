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
- **Persistence** (updated 2026-08-30): both bots run under systemd
  units `slk-bot1.service` / `slk-bot2.service` at
  `/etc/systemd/system/`, each calling the existing
  `launch_bot1.sh`/`launch_bot2.sh` scripts, `Restart=always`,
  `RestartSec=10`. Deploy/restart with `systemctl restart slk-bot1
  slk-bot2` (add `systemctl daemon-reload` first if the unit files
  themselves changed); inspect with `systemctl status slk-bot1` /
  `journalctl -u slk-bot1 -f`. Replaces the tmux sessions (`bot1`/`bot2`)
  this section used to describe -- the tmux server itself was found
  dead (not just the bot processes) with no clear trigger, taking both
  bots down silently and with no crash trace; systemd now restarts a
  crashed bot automatically instead of relying on a manual
  `tmux send-keys` relaunch.
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

## 2026-08-29 -- root-caused the EURJPY invalid-stops incident: 14-15h-stale catch-up, not a fresh signal

Following on from the two fixes above: checked whether the rejected
EURJPY/USDCHF/AUDCAD orders were fresh signals or old ones caught up
late. An offline check against a GitHub Actions Dukascopy pull first
suggested USDCHF/AUDCAD were WEEKS old -- wrong conclusion, because that
dataset has diverged from the VPS's real cache (`sync_recent_from_mt5`
merges live MT5 candles into the same `dukascopy`-named cache files, so
the two are no longer identical). Re-run directly on the VPS against the
real cache: EURJPY's two rejected orders exactly match the 16:00 and
17:00 UTC candles from the PREVIOUS day (stop-loss values 185.483 and
185.467 matched exactly) -- attempted live at 07:17 UTC the next day,
14-15 hours after their entry/stop/target math was computed.

Root cause: the watermark-widening (08-28) and storyline-gap-replay
(08-29) fixes both correctly stop a missed signal from being silently
dropped, but neither had any concept of "too old to still be worth
trading" -- a caught-up signal was executed at whatever price/stop it
was computed at, regardless of how much the market had moved since.
Today it happened to get rejected by MT5's own invalid-stops check;
that's luck, not a safeguard.

**Fixed**: `STALE_ENTRY_CUTOFF` (3 hours) in `orchestrator.py` -- a
caught-up signal older than this is declined (`decline_stale_signal`,
full reasoning still logged/audited) rather than passed to
`_consider_entry`/the risk manager/MT5. 3 hours is generous room for a
real reconnect storm's recovery (the worst measured one resolved in
minutes) while reliably excluding "yesterday afternoon." Direct
request: "leave the trade if it have passed."

Also added `bot/diagnostics.py`'s `resource_snapshot()` (pure /proc
reads, no new dependency) -- logged once at the start of an outage and
once at recovery (not per attempt, since a real storm is 150+ of them).
This is aimed at finally settling the still-open question of whether
the recurring auth failures are VPS-side (resource contention with
kugo-backend) or broker-side: high load/swap at failure time points at
the VPS, clean numbers point at the broker. Nothing conclusive yet --
needs a few more live incidents to accumulate data.

**Both need `git pull` + bot restart on the VPS to take effect,** same
as the two fixes above.

## 2026-08-29 evening -- self-inflicted outage: every entry decision crashed on deploy

The `entry_time` field added earlier the same day broke logging
entirely once deployed. `CREATE TABLE IF NOT EXISTS` is a no-op against
`decisions`, which already existed on both bots from before that field
was added -- so every single `append()` call (allow, decline,
execution_failed, ALL of them) started raising `sqlite3.OperationalError:
table decisions has no column named entry_time`, confirmed live from
~19:21 UTC. Uncaught up through `_check_instrument`'s per-instrument
exception isolation, which also meant `_last_entry_time` never advanced
for whatever instrument hit it -- so the same signal would have kept
getting retried and crashing again on every subsequent poll.

**Fixed**: `AuditLog._ensure_schema()` now checks `PRAGMA table_info` and
`ALTER TABLE ADD COLUMN`s anything `DecisionRecord` declares that the
live table doesn't have. Self-healing by construction -- any future
field addition is now safe without a hand-written migration. New test
reproduces the exact scenario (a db file with an older schema, opened
by current code). **Needs `git pull` + bot restart immediately** --
every entry decision has been failing to log since the previous deploy.

Also worth noting from the Telegram log while diagnosing this: one
outage's resource_snapshot showed `load=41.2,53.1,30.7 mem=7.4/7.8GB`
-- a load average of 41-53 on a 2-vCPU box, memory nearly maxed. Several
`new_candle_closed` calls in the same window failed with
`copy_rates_from_pos ... IPC recv failed` / `No IPC connection`, and one
reconnect failed with `IPC timeout` -- different failure text than the
usual `Terminal: Authorization failed`. This is the first real evidence
pointing at VPS-side resource contention specifically (severe enough to
break IPC between the Python bridge and the Wine-hosted terminal, not
just an auth handshake) rather than the broker. Not conclusive on its
own -- one data point -- but the diagnostic is doing its job.

## 2026-08-30 -- root cause of a "signal candle from Saturday" report: weekend-stale offset detection

Direct question: XAUUSD declined a signal whose candle was timestamped
2026-08-29 10:00 UTC -- a Saturday, when gold/FX markets are closed.
Checked the offline Dukascopy release first: it ends cleanly at Friday
2026-08-28T20:00:00Z, nothing for the weekend -- ruling out the data
source. The candle came from the live VPS side.

Root cause: `MT5Client._detect_server_utc_offset()` compares the
currently-forming M1 candle's reported time against Python's real UTC
"now" to work out the broker's clock offset -- correct only while the
market is open. Called during a weekend closure, `rates[0]` isn't
forming right now at all; it's the last bar from before Friday's close,
many hours stale. The raw comparison then produces a wildly wrong
delta, which got silently cached and applied (as a fixed subtraction)
to EVERY candle timestamp fetched until the next reconnect -- corrupting
them all, not just the weekend read itself. `_server_utc_offset` resets
to `None` on every reconnect (by design, to catch a real DST/server
change), so every reconnect during the weekend re-triggers this.

**Fixed**: the detected offset is now sanity-checked against a
plausible range (+/-6h of UTC -- this broker's confirmed at +3). An
implausible result raises `MT5ConnectionError` instead of being
adopted, which `fetch_candles`/`sync_recent_from_mt5`'s existing
try/except already handles by skipping that cycle -- and is simply
correct: there's nothing to trade while the market is shut, so failing
to fetch until a genuinely fresh candle exists again (the market
reopens) is the right behavior, not a gap to paper over. Two new tests
reproduce the exact scenario (a stale Friday-close M1 candle read on
Saturday) at both the detection function and the fetch_candles() call
path. 185 tests pass. **Needs `git pull` + bot restart on the VPS.**

## 2026-08-30 -- tmux server died silently, taking both bots down; migrated to systemd

Follow-on from the weekend-offset investigation above: while checking
why a Sunday-morning signal looked wrong, found both bots simply not
running, with no crash trace visible via the usual `tmux attach`/
`capture-pane` -- `tmux send-keys -t bot1 ...` failed with "no server
running on /tmp/tmux-0/default". Not just the bot processes but the
whole tmux server had exited; root cause of that specific death is
undetermined.

Checked `uptime` (53 days, no reboot) and `dmesg` (no OOM-kill entries)
-- ruled out a VPS crash/reboot as the cause. `free -h` at the time
showed memory healthy (not chronically maxed), though a later outage
(see the IPC-failure entry above) did show real load/swap pressure from
another process on the box (`kugo-backend`, cron `*/1`, and possibly a
studifypro compression script -- unconfirmed) -- a separate, real
finding, but not what killed tmux itself.

**Fixed** by replacing tmux-based supervision with systemd:
`slk-bot1.service` / `slk-bot2.service` created at
`/etc/systemd/system/`, `Restart=always`, `RestartSec=10`, calling the
existing `launch_bot1.sh`/`launch_bot2.sh` unchanged. Deployed and
confirmed running by the user. **All future deploys/restarts use
`systemctl restart slk-bot1 slk-bot2`** (or `systemctl daemon-reload`
first if the unit files change) -- not the old `tmux send-keys`
pattern, which no longer applies.

## 2026-08-30 -- storyline log line now shows each timeframe's own confirmation date/time

Direct request: the "hunting"/"waiting" Telegram log line (e.g.
`NZDUSD: hunting -- Weekly/Daily/H4 aligned bullish -- watching H1 for
the entry`) gave no way to tell whether each timeframe's alignment had
just happened or was sitting near the stale edge of its
`ALIGNMENT_LOOKBACK` window -- i.e. whether the log was reporting the
current candle or an old one.

`Storyline` (live_strategy.py) gained `weekly_confirmed_at` /
`daily_confirmed_at` / `h4_confirmed_at` fields, populated from the
`.time` of each timeframe's own most recent `Confirmation` --
`_recent_direction()` now returns the whole `Confirmation` object
instead of just `.direction`, so this is free: no extra data fetch or
computation, only exposing timestamps that were already being read to
decide alignment. Negligible load impact.

`_storyline_says_hunt()` (orchestrator.py) appends these as a suffix on
stage-transition log lines only, e.g. `(Weekly@2026-01-05
00:00:00+00:00, Daily@2026-01-12 00:00:00+00:00, H4@2026-01-13
12:00:00+00:00)`. New test
`test_storyline_transition_is_logged_with_each_timeframes_own_confirmation_time`
asserts all three appear in the logged message. 186 tests pass.
**Needs `git pull` + `systemctl restart slk-bot1 slk-bot2` on the VPS**
(tmux is no longer how these are supervised -- see the systemd
migration above).

## 2026-08-30 -- self-inflicted Telegram spam from the weekend offset fail-closed fix

Direct report: ~2,800 Telegram messages in 3 hours. Caused by the
fail-closed weekend-offset fix above: `_server_utc_offset` never gets
set to a real value while detection keeps failing (correctly, market's
closed), so every single 5-second poll for every instrument re-attempts
detection, fails the same way, and `_check_instrument`/
`_storyline_says_hunt` logged a fresh WARNING (-> Telegram) every time
with no dedup. A real, correct condition (market closed) turned into an
unbounded log storm because nothing suppressed the repeat.

**Fixed**: both call sites now log a `new_candle_closed(...)` failure
only when the message differs from the last one logged for that
instrument/granularity (`LiveBot._last_candle_error`,
`_log_candle_error_if_changed()`), clearing on the next success. The
offset-detection error text drifts roughly hourly on its own (it's
derived from real UTC "now" vs. a fixed stale candle time), so this
still surfaces that the condition is ongoing -- just once an hour per
instrument instead of once every 5 seconds. Two new tests reproduce the
exact scenario (identical repeated failure vs. a changed message). 188
tests pass. **Needs `git pull` + `systemctl restart slk-bot1 slk-bot2`
on the VPS.**

## 2026-08-30 -- correction: the first spam fix wasn't enough, dedup needed to be state-based not text-based

The first attempt (previous entry) deduped on exact message text, which
seemed right (the resource_snapshot precedent logs "once per outage,
not per attempt") but wasn't: the offset-detection error text embeds a
computed hour count that drifts roughly once an hour on its own (see
mt5_data.py's `_detect_server_utc_offset` docstring), and the ~25
tracked instruments' stale Friday-close candles are all within a few
minutes of each other -- so all 25 crossed that hourly drift boundary
within the same ~15-second window, each counting as a "new" message
under text-based dedup. Confirmed live: still a ~25-message burst every
hour, correctly reported back as "still spamming."

**Actually fixed**: `_candle_error_active` now tracks failing/recovered
STATE per instrument (H1) / instrument:granularity (storyline W/D/H4),
not message text. A key logs once when it FIRST enters a failure state
and stays silent for the rest of that outage regardless of how the
message text drifts; it only logs again after a genuine recovery
(offset detection succeeds again) followed by a new failure. During a
full weekend closure this means one message per instrument, period --
not one per instrument per hour. New test
`test_a_new_candle_closed_failure_is_logged_again_after_a_real_recovery`
covers the recover-then-fail-again case the first fix's tests didn't
have. 188 tests pass. **Needs `git pull` + `systemctl restart slk-bot1
slk-bot2` on the VPS.**

## 2026-08-30 -- Telegram itself flood-blocked the bot for 1h45m+ after the earlier spam incident

Direct report: no Telegram messages since 21:53 WAT despite the market
reopening and the bot clearly working (audit DB being written, real
storyline transitions in the journal). Root cause, confirmed via
journalctl: every single delivery attempt from 21:01:20 UTC onward
returned `HTTP Error 429: Too Many Requests` from Telegram's own API --
not a bug in the trading logic, Telegram's own flood control reacting
to the earlier spam storm (see the two entries above). `TelegramHandler`
had no concept of backoff: every new event just retried immediately,
got another 429, and (matching Telegram's documented flood-control
behavior) retrying INSIDE an active block is exactly what keeps
renewing it -- almost certainly why this ran for well over an hour
instead of clearing in the usual 30-60s.

**Fixed**: `_send()` now parses the 429 response body's
`parameters.retry_after` (Telegram's own stated cooldown in seconds)
and sets `_blocked_until`; both `emit()` and `flush()` (the latter is
called once per poll loop by run_live.py, so it needed the same guard)
now skip attempting a send entirely while still inside that window --
new events stay queued, nothing is attempted, nothing renews the block.
Falls back to a doubling default backoff (60s, capped at 30 min) if a
429 doesn't carry `retry_after`. A successful send clears the block and
resets the backoff. Five new tests cover: respecting `retry_after`,
`flush()` also respecting it, the no-`retry_after` fallback, recovery
clearing state, and repeated failures doubling the backoff. 193 tests
pass.

Note for next deploy: `_blocked_until` is in-memory, so restarting the
process resets it -- if Telegram's OWN block is still active
server-side at restart time, the very next send attempt will hit
another 429, but the new code will correctly back off on THAT one
rather than hammering it, so this is self-correcting either way.
**Needs `git pull` + `systemctl restart slk-bot1 slk-bot2` on the VPS.**

## 2026-08-30 -- leftover corruption from the weekend-offset bug: future-dated candles frozen 20 of 25 instruments' live detection

Follow-on from investigating why bot2's audit DB was 5+ hours stale
while bot1's wasn't. Direct evidence: `AUDCAD` was repeatedly declining
the exact same stale-signal staleness values 18 minutes apart --
staleness that should have GROWN between polls if real time were
advancing normally, so something wasn't. Read the raw cache file
(`backtest/data/dukascopy/AUDCAD/H1.csv`) directly: it contained two
rows timestamped `2026-09-01T15:00:00Z` / `2026-09-01T17:00:00Z` --
tomorrow -- with OHLCV values that exactly duplicate the real
`2026-08-30T21:00:00Z` row. A scan across every instrument's cache
found the same pattern in 20 of 25: AUDCAD, AUDJPY, CHFJPY, EURCAD,
EURCHF, EURNZD, EURUSD, GBPAUD, GBPCAD, GBPCHF, GBPJPY, GBPNZD, GBPUSD,
JP225, NAS100, NZDUSD, US30, USDCAD, USDCHF, USDJPY.

Root cause: leftover damage from the weekend server-clock-offset bug
(see the entry above, fixed earlier the same day) -- BEFORE that fix
landed, `sync_recent_from_mt5` had already written the same real candle
out a second time under a wildly wrong (~+42h) offset, for nearly every
instrument being synced during that window. The offset-detection fix
stops NEW corruption but does nothing about rows already written:
`cache.append()`'s dedupe is by exact timestamp, so a bogus row with a
timestamp nothing else will ever collide with sits there permanently.
Consequence, not just cosmetic: since a CLOSED candle timestamped in
2026-09-01 sorts after everything real, `new_candle_closed()` would
never again recognize any genuinely new candle as "newer" for that
instrument until real calendar time actually reached the bogus date --
live entry detection for those 20 instruments was effectively frozen,
silently, for both bots.

**Fixed two ways**:
1. Immediate data cleanup: a one-off script (not committed --
   deliberately temporary tooling, see the pattern elsewhere in this
   log) stripped every future-dated row from all affected cache files,
   using `cache._file_lock(path, exclusive=True)` so it was safe to run
   without stopping either live bot.
2. Root fix: `MT5Client.fetch_candles()` (mt5_data.py) now drops any
   candle MT5 reports as CLOSED whose time is after "now" (5-minute
   slack for ordinary clock skew) -- a closed candle can never
   legitimately be future-dated, regardless of which bug produces one,
   so this is a second, independent line of defense from the offset-
   plausibility check, not a replacement for it. New test
   `test_fetch_candles_drops_a_future_dated_candle_mt5_reports_as_closed`
   reproduces the exact ~42h-future scenario. One pre-existing test
   (`test_fetch_candles_auto_detects_and_applies_the_offset_when_not_pinned`)
   had a self-inconsistent mocked "now" that only became a problem once
   this check existed -- fixed to use a self-consistent timeline. 194
   tests pass.

**Needs, in this order, on the VPS**: (1) run the future-candle cleanup
across all cache files -- ask for the script if it wasn't kept from
this session; (2) `git pull` + `systemctl restart slk-bot1 slk-bot2`.
Worth re-scanning the cache after deploy to confirm no instrument still
carries a future-dated row.

## 2026-08-31 -- every restart today had been leaking the containerized process: up to 14 live bots running at once

Discovered while chasing a "how long will Telegram be down" question
after a `systemctl restart` that was taking unusually long. `docker exec
mt5 ps aux | grep run_live` showed **14** `python3 -m bot.run_live`
processes alive simultaneously -- 7 conservative, 7 aggressive -- most
dated `Aug30` (surviving from earlier restarts done that same day) plus
the 2 newest from the most recent restart.

Root cause: `slk-bot1.service`/`slk-bot2.service` (see the systemd
migration entry above) has `ExecStart=/bin/bash launch_bot1.sh`, whose
last line is a plain (non-`exec`'d) `docker exec ... python3 -m
bot.run_live ...`, and NO `ExecStop=` was ever defined. Systemd's
default stop behavior only signals what's in ITS OWN cgroup on the
host -- the local `bash` wrapper and the local `docker exec` CLIENT.
The actual `python3 -m bot.run_live` process, though, runs inside the
CONTAINER's own process namespace, managed by dockerd/containerd, not
by systemd at all. Killing the local `docker exec` client does not
kill the remote process it started; the remote process simply keeps
running, permanently orphaned, invisible to `systemctl status` (which
only ever showed ONE Active line per service, because it only ever
knew about its own current wrapper PID). Every `systemctl restart`
done this entire session -- and there were many, one per fix deployed
today -- silently doubled the count.

**This was not just noise.** Each leaked process is a fully independent
live copy of the bot, polling MT5 and capable of independently deciding
to place a trade -- multiple copies of "conservative" all seeing the
same signal could each have sent their own `order_send()`, opening
duplicate positions with duplicate risk. It's also very likely a real
contributor to the chronic VPS load (38-41 average, tracked in several
entries above) this whole session blamed mostly on other processes
(kugo-backend, studifypro) -- 14 python processes each burning
8-13% CPU is a substantial chunk of that on its own.

**Fixed**: killed every orphaned process
(`docker exec mt5 pkill -f "python3 -m bot.run_live"`), confirmed via
`ps` that exactly 2 remained after a clean restart. Then added an
explicit `ExecStop=` to each unit via a systemd drop-in
(`/etc/systemd/system/slk-bot{1,2}.service.d/override.conf`) that
reaches directly into the container:

```
[Service]
ExecStop=/usr/bin/docker exec mt5 pkill -f "run_live.*--audit-db conservative_audit.db"
```

(and the `aggressive_audit.db` equivalent for bot2 -- matched on the
`--audit-db` flag specifically so each unit's ExecStop can only ever
kill ITS OWN process, never the other bot's). Verified live: restarted
both services twice in a row and confirmed the process count stayed at
exactly 2 both times, not 4.

**Not yet done**: verify neither bot actually opened a duplicate
position while multiple copies were running today -- worth a manual
check of both MT5 accounts' open positions against `tracked_positions`
expectations next time either account is checked. Not in the git repo
(systemd unit + drop-in are VPS-only, like the base unit files
themselves) -- if this VPS is ever rebuilt, the drop-in override.conf
files above need to be recreated, not just the base .service files.

## 2026-08-31 -- self-inflicted: the future-candle cleanup script broke EURUSD/USDCHF's timestamp format

Direct report: EURUSD and USDCHF started throwing
`TypeError: '<' not supported between instances of 'str' and
'Timestamp'` in `_find_entry_candidates` (runner.py), caught by the
per-instrument exception handler so the bot kept running but silently
skipped those two instruments every cycle.

Root cause: my own fault, introduced by the future-dated-candle cleanup
script (see the entry above) run earlier the same day. That script read
each cache file with `pd.read_csv(path, parse_dates=["time"])` and
wrote it back with `cleaned.to_csv(...)`, which serializes a tz-aware
datetime column using pandas' default string format
(`2026-08-30 21:00:00+00:00` -- space separator, `+00:00` suffix).
EVERY other writer in this codebase (`sync_recent_from_mt5`,
`dukascopy_client.py`, `fetch_crypto.py`, `resample.py`) uses a
DIFFERENT convention: `isoformat().replace("+00:00", "Z")` ->
`2026-08-30T21:00:00Z`. This exact failure mode is already documented
in `live_cache_sync.py`'s own module docstring from an earlier
incident: mixing the two formats in the same CSV column makes pandas
silently fail to parse SOME rows into real Timestamps while leaving
others as raw strings, and any downstream comparison between them
(here, `bisect.bisect_left` inside `_find_entry_candidates`) blows up.
Once my cleanup rewrote a file's existing rows in the wrong format,
the very next live append (in the correct "Z" format, from
`sync_recent_from_mt5`) mixed the two conventions in the same file --
which is why only SOME instruments broke and not immediately all 25:
it needed a live append to actually happen after the rewrite.

**Fixed**: a second one-off script (not committed, same pattern) read
every dukascopy cache file's `time` column as raw strings, parsed with
`pd.to_datetime(..., utc=True, format="mixed")` (robust to the mixed
formats already on disk), sorted, deduped, and re-wrote every row using
the correct `isoformat().replace("+00:00", "Z")` convention -- run
across ALL 25 instruments x ALL granularities (D/H1/H2/H3/H4/M/M15/
M30/M45/M5/W, not just the H1/H4/D/W the bot actually reads, for
consistency), using the same `cache._file_lock(exclusive=True)` as
before. No restart needed -- `run_backtest()` reads the cache fresh
from disk on every call, so this took effect on the very next poll
cycle. Confirmed via journalctl: no further errors for EURUSD/USDCHF.

**Lesson for next time a cache file needs rewriting by an ad-hoc
script**: never round-trip through `pd.read_csv(parse_dates=...)` +
`df.to_csv()` -- always serialize the `time` column explicitly with
`.isoformat().replace("+00:00", "Z")` to match every other writer, or
reuse `cache.py`'s own row-building convention directly instead of
letting pandas pick a default format.

## 2026-09-01 -- CRITICAL: confirmed live duplicate order fills, root-caused and fixed

Direct report with MT5 mobile screenshots as evidence: EURCAD filled
TWICE (tickets #10279010232, #10279098481 -- same direction, same
13.48 lots, same SL 1.61140/TP 1.60728, opened 3 minutes apart on
2026-08-31) and EURNZD filled THREE times (same 5.79 lots, all at
2026-09-01 11:33:01 -- the same second). Both this codebase's own
comments from an earlier 2026-08-26 incident (three duplicate EURCAD
fills after a TRADE_RETCODE_CONNECTION) and this one share the same
shape: an ambiguous send failure (CONNECTION or TIMEOUT), a retry that
should have been blocked by `_recover_landed_order()`'s "did it
already land?" check, and a real duplicate fill anyway. None of these
positions were ever in `tracked_positions`, so the risk manager was
blind to roughly double-to-triple the intended $1,000 risk on each.

Root cause, in `mt5_execution.py`: `_our_open_tickets()` returned an
EMPTY SET both when `positions_get()` genuinely found nothing AND when
the query itself raised an exception. The exact connectivity trouble
that produces an ambiguous TIMEOUT on `order_send()` is often ALSO
what makes `positions_get()` unreliable at that same moment (this
session's logs show repeated "Terminal: Authorization failed"
reconnect storms right around these incidents) -- so the one check
meant to prevent a duplicate went blind precisely when it was needed
most, and the retry loop proceeded as if "confirmed nothing landed"
when the truth was "couldn't tell." A second, independent gap: the
check ran with NO settle delay at all immediately after the ambiguous
failure, racing a fill that can be real but not yet reflected in
`positions_get()`.

**Fixed**: `_our_open_tickets()` now returns `None` (not an empty set)
when the query fails, and `_recover_landed_order()` treats that as a
TERMINAL failure -- stop immediately, do not retry, and say so loudly:
"could NOT verify whether a position landed ... MANUAL RECONCILIATION
REQUIRED". A retry is only ever attempted when verification genuinely
succeeded and found nothing. Also added a 2-second settle delay
(`recovery_check_settle_seconds`, configurable) before the check runs,
so a fill that's real but momentarily invisible gets a fair chance to
show up before the code concludes otherwise. Three new tests: a
`positions_get()` failure refuses to retry, a fill that only appears
after the settle delay is recovered (not duplicated), and the existing
idempotency tests updated to keep running instantly (settle delay set
to 0 in tests, same pattern as `retry_backoff_seconds`). 196 tests
pass.

**NOT yet done, and important**: this fix prevents FUTURE duplicates.
It does NOT retroactively fix the two EURCAD positions already open
and untracked on the conservative account (#10279010232,
#10279098481) -- those still need a human decision (close one,
manually reconcile both into the audit log, or leave them and just
make sure the risk manager's live exposure math accounts for them).
The EURNZD triplicate has already closed (profitably, by luck --
+$1,895 combined) so nothing to reconcile there beyond noting it in
the account's history.

Also reported alongside this: (1) risk sometimes appearing to exceed
$1,000 per trade -- largely explained by this exact bug (the "same"
$1,000-risk trade landing 2-3 times looks like 2-3x risk because it
IS), worth re-checking after this fix whether any TRUE single-trade
oversizing remains; (2) the GitHub Action backtest finding more
signals than were executed live -- plausible given how many reconnect
storms are visible in the same logs (a real-time signal missed or
correctly declined-as-stale during an outage has no backtest
equivalent, since the offline run never experiences an outage). Both
lower priority than the duplicate-fill fix; worth a dedicated look
later if they persist once this deploys.

**Needs `git pull` + `systemctl restart slk-bot1 slk-bot2` on the
VPS** -- this is the highest-priority deploy of the day.

## 2026-09-01 -- session-rollover entry filter validated and enabled live

Direct report following up on the GBPAUD incident above: risk sizing
looked wrong on other trades too ("$1,500 range of risk"). Traced the
GBPAUD loss precisely via its audit row: requested entry 1.88948, stop
1.88846 (102-point distance, sized for $1,000), actual fill 1.89002
(54 points of slippage) -- real distance to the still-fixed stop became
156 points, 53% wider, and -$1,530.32 realized when it hit. Not a
sizing-math bug (`compute_lot_size()` is correct); the gap is between
the REQUESTED price sizing is computed against and the ACTUAL fill
price a market order can land at, with nothing correcting the stop
distance for the difference.

STRATEGY.md Section 8 already documents the likely cause: "Avoid
holding into very late hours -- spread widens sharply around session
rollover (~10pm reference)." The GBPAUD entry was at 22:00 UTC, exactly
that window. The live bot had never implemented this rule.

Ran the `avoid_rollover_entries` A/B backtest (added above) over full
2025-2026 history, all 25 instruments, both styles:

| | without filter | with filter (21:00-23:00 UTC blocked) |
|---|---|---|
| closed trades | 2,696 | 2,512 |
| win rate | 51.7% | 51.1% |
| total R | 2,668.2 | 2,451.5 |
| avg R/trade | 0.990 | 0.976 |

The 185 removed trades contributed +216.7R (~8% of total), slightly
ABOVE the overall per-trade average -- meaning the backtest thinks
rollover-window signals are perfectly fine. That's expected and not a
contradiction: `run_backtest()` has zero slippage model, so it cannot
see the exact execution risk (a real, demonstrated 54-point slippage
event) this filter exists to avoid. The comparison validates signal
quality, not execution safety, and was never going to be able to prove
the live incident wrong either way.

**Decision (direct instruction): enable it live regardless of the
backtest R cost** -- demonstrated live execution risk outweighs an
opportunity cost the simulation structurally cannot measure.
`orchestrator.py`'s `_check_instrument()` now calls `run_backtest(...,
avoid_rollover_entries=True)` unconditionally. New test
`test_check_instrument_always_asks_run_backtest_to_avoid_rollover_entries`
asserts the flag is actually passed. 349 tests pass. Scope: all 25
instruments (GBPAUD, the actual incident, is a cross, not one of the 7
FX majors -- a majors-only scope would not have caught it); new
entries only, not overnight-holding behavior (STRATEGY.md's separate
"day trader, does not swing overnight" rule -- a bigger change, not
done here).

The temporary `compare-rollover-filter.yml` workflow has been removed
now that results are captured, matching this project's established
pattern (see the lookahead-bias and confirmation-source comparisons
earlier in this file).

**Needs `git pull` + `systemctl restart slk-bot1 slk-bot2` on the VPS.**

Also still open from the same report: risk exceeding $1,000 on OTHER
trades may be largely the same slippage-vs-fixed-stop mechanism (any
trade, any hour, can in principle slip on a Market Execution fill) --
this rollover fix only addresses the specific high-spread WINDOW, not
slippage in general. Worth re-checking whether oversized-risk reports
keep happening on trades entered well outside 21:00-23:00 UTC; if so,
that's a broader "stop should account for realized fill price" problem
this fix does not solve.

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
- **Stale-signal orders can hit INVALID_STOPS with no pre-check.**
  Confirmed live 2026-08-31: EURUSD signal candle at 13:00:00, order
  attempt at 14:08:39 (68 minutes later, within the 3h staleness
  cutoff) -- entry/stop/target were all computed once at signal time
  and never re-validated against the CURRENT market price before
  `_consider_entry()` (orchestrator.py:402) hands them straight to
  `place_market_order()`. If price drifts enough in that window, the
  stop can end up too close to (or briefly past) wherever price
  actually is by send time, and the broker rejects with
  `TRADE_RETCODE_INVALID_STOPS`. Confirmed low-severity as observed --
  the order is cleanly rejected, logged with full reasoning, no money
  moved, no duplicate-order risk (distinct from the 2026-08-31
  duplicate-fill bug, already fixed). Net effect is a missed trade, not
  a bad one. Direct instruction 2026-09-01: leave as-is for now, revisit
  if this starts happening often enough to matter. If it's ever worth
  fixing: re-fetch a current quote and re-check the stop distance
  against the broker's minimum using CURRENT price before sending,
  declining cleanly (matching the existing `STOP_TOO_CLOSE` pattern in
  `compute_lot_size()`) instead of round-tripping to the broker for a
  rejection that was predictable in advance.
