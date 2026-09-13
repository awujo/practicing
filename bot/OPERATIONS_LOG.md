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

## 2026-09-01 -- minimum-reward entry filter validated and enabled live: a clean improvement, not a tradeoff

Direct question: "a trade of less than 1R doesn't make sense to hold ...
check backtesting ... taking trade with less than 1R and leaving it
which gives more profit." Ran the same A/B process used for
`avoid_rollover_entries` -- `run_backtest()` gained `min_reward_r`
(default `None`), skipping any entry whose ERL-capped target sits less
than that many R away from entry. Full 2025-2026 backtest, all 25
instruments, both styles, `min_reward_r=1.0`:

| | without filter | with filter (min 1R target) |
|---|---|---|
| closed trades | 2,696 | 2,631 |
| win rate | 51.7% | 51.9% |
| total R | 2,668.2 | 2,684.3 |
| avg R/trade | 0.990 | 1.020 |

Unlike the rollover filter, this is NOT a safety-vs-opportunity
tradeoff -- the 65 removed trades were net LOSERS (-16.1R combined,
44.6% win rate vs. 51.7% overall). Skipping them raised total R, win
rate, AND avg R/trade simultaneously, and the backtest can judge this
one directly (no slippage model needed to know whether a sub-1R target
is worth the risk, unlike the rollover-window execution risk).

**Enabled live immediately**, no further confirmation needed given the
unambiguous result: `orchestrator.py`'s `_check_instrument()` now calls
`run_backtest(..., avoid_rollover_entries=True, min_reward_r=1.0)`.
Existing rollover-flag test extended to also assert `min_reward_r=1.0`
is passed. 351 tests pass. Temporary `compare-min-reward-filter.yml`
workflow removed now that results are captured, same pattern as
`compare-rollover-filter.yml` before it.

**Needs `git pull` + `systemctl restart slk-bot1 slk-bot2` on the VPS.**

## 2026-09-01 -- fixed a live cause of "GitHub Action found more trades than executed": the reference feed didn't know about today's two new live-only filters

Direct question: why does `hourly-signal-check.yml`'s Dukascopy
reference keep finding more signals than the live bots actually
traded? Root-caused at least one concrete, current cause:
`check_recent_signals.py` (the reference generator behind that
workflow and `bot/reconcile_signals.py`) called
`run_backtest(instrument, style)` with no flags -- but `orchestrator.py`'s
`_check_instrument()`, as of the two entries just above, now
unconditionally calls `run_backtest(..., avoid_rollover_entries=True,
min_reward_r=1.0)`. Every rollover-window signal and every sub-1R
signal the reference feed picked up would never even reach
`_consider_entry()` live -- filtered out before `run_backtest()`
returns them as candidates, so no audit row (not even a decline) is
ever logged. `reconcile_signals.py` would report every one of those as
`MISSING`, indistinguishable from the real "the bot never saw it" bug
this whole reconciliation mechanism exists to catch -- permanently
drowning out genuine misses in predictable, non-actionable noise.

**Fixed**: `check_recent_signals.py` now calls `run_backtest()` with
the identical flags the live orchestrator uses, so the reference feed
represents what the live bots are actually SUPPOSED to trade, not a
strictly broader raw-signal set. New test asserts both flags are
passed. 352 tests pass.

Note: this explains signals from TODAY's two new filters specifically.
The user's original report of this mismatch predates both filters, so
other causes (reconnect-storm outages, MT5-vs-Dukascopy candle
differences noted in `reconcile_signals.py`'s own docstring, the
STALE_ENTRY_CUTOFF declining old catch-up signals) likely still
contribute too -- this fix removes one confirmed source, not
necessarily the only one. Worth re-checking the reconciliation report
after this deploys to see how much of the gap remains.

No VPS deploy needed for this one -- `check_recent_signals.py` only
ever runs inside `hourly-signal-check.yml` on GitHub Actions, which
checks out `main` fresh on every run, so the very next scheduled or
manually-triggered run already publishes a feed generated with this
fix. `bot/reconcile_signals.py` (the VPS-side reader) needed no
changes -- it just reads whatever feed gets published.

## 2026-09-01 -- root-caused the original "Dukascopy sees more trades" gap: found TWO distinct causes, fixed one

Direct follow-up: the reference-feed mismatch was reported before
today's two entry filters existed, so the fix above only explained
part of it. Pulled a genuinely pre-fix Dukascopy reference run (commit
e7c0a77, Sept 1 01:15 UTC, 36h window) and compared its 11 published
signals directly against both audit databases for the same window.
Result: **9 of 11 signals had zero trace in either database** -- not
declined, not late, just absent.

Two distinct, confirmed causes:

1. **Restart-induced cold-start signal loss.** `_last_entry_time`
   (the watermark that lets `_check_instrument()` catch up on
   everything since the last real check) lives only in memory. Every
   process restart resets it, and the FIRST check per instrument after
   a restart falls back to exact-match-only (by design, to avoid
   replaying full history on a truly blank slate) -- so a real signal
   that closed around a restart, and doesn't land on the literal next
   candle checked, is silently and permanently dropped. Confirmed via
   journalctl: at least 3-4 process restarts (PID changes) fell inside
   the 36h window this reference feed covered, matching how often this
   bot was being redeployed that day.

   **Fixed**: `AuditLog.last_entry_time(instrument)` (new method)
   returns the most recent `entry_attempt`'s own signal-candle time --
   durable, survives a restart. `_check_instrument()` now reconstructs
   the watermark from this when nothing is cached in memory yet,
   falling back to a genuine cold start only when the audit database
   has never seen that instrument at all. Four new tests (2 in
   `test_audit_log.py`, 2 in `test_orchestrator.py`, including one
   confirming a truly new instrument still starts cold). 358 tests
   pass.

2. **MT5-vs-Dukascopy data divergence -- NOT fixed, separate issue.**
   The one EURCAD row that DOES exist in the audit database is for an
   11:00 candle; Dukascopy's reference found its EURCAD setup at 13:00
   -- a different candle entirely, and by the time the live attempt was
   logged (12:44-12:46) the 13:00 candle hadn't even closed yet. This
   means `run_backtest()` running against MT5's live-merged cache
   genuinely produced a DIFFERENT trade candidate than the pure-
   Dukascopy offline engine, for the same instrument in the same
   window -- not a timing gap, a real difference in what the two data
   feeds show. Already an acknowledged tradeoff
   (`live_cache_sync.py`'s own docstring: two different liquidity
   providers, "usually small, occasionally not" different prices) but
   this is direct evidence of the "occasionally not" case actually
   happening, and restart-watermark persistence does nothing for it.
   No fix attempted here -- would need comparing raw MT5 vs. Dukascopy
   candle data for this exact window to characterize further, and it's
   not obvious there's anything to "fix" beyond continuing to accept
   the tradeoff.

**Needs `git pull` + `systemctl restart slk-bot1 slk-bot2` on the
VPS.** Worth watching `bot/reconcile_signals.py`'s next few runs to see
how much of the original gap is now closed vs. still attributable to
cause 2.

## 2026-09-01 -- queued for after exams: rework entries as limit orders with a retest fill, not market orders at signal time

Direct user correction: SLK entries are conceptually limit orders resting
at a specific level, waiting for a retest -- not market orders fired the
instant a trigger confirms. User's own trading, and "bishops"
(mentors/community this strategy is transcribed from), hardly use market
orders at all. This matches something already half-true in the code:
`entries.py`'s `aggressive_entry_price()` already returns the KEY
LEVEL's price, not the trigger candle's close -- but nothing anywhere
(backtest OR live) ever treats that as a real resting order. The
backtest assumes an instant fill at `entry_price` the moment the trigger
fires, with no check that price ever actually revisits it and no concept
of the setup expiring unfilled. Live, both entry styles go through
`place_market_order()` (`TRADE_ACTION_DEAL`) regardless -- there is zero
limit-order code anywhere in `bot/mt5_execution.py`.

**Per-trigger definitions, as given directly by the user (2026-09-01
voice message) and cross-checked against the existing code:**

- **Break-and-retake (breakout)** -- not currently a distinct trigger.
  `entries.py`'s own module docstring already flags this gap:
  "breakout-as-entry (NOT YET WIRED as its own detected trigger in
  runner.py)", with a stop-loss formula already drafted and unused
  (`breakout_leg_stop_loss()` -- anchored to the low/high of the WHOLE
  LEG that produced the breakout, not just the breakout candle). The
  trigger: an A/V-shape key level exists; a candle CLOSES beyond it
  (the break, on a close/line-chart basis, matching this engine's
  existing close-based-breakout convention); then wait for price to
  come back and retest THAT SAME A/V level; enter there via a resting
  limit order. Two-stage: confirmation = the close-based break, fill =
  the later retest of the original level.
- **Engulfing** -- entry is NOT at the engulfing candle's own close
  (which is what `conservative_entry_price()` currently uses, and
  roughly what aggressive's `classification.reference_level` also
  tends to track for this trigger). Two consecutive same-direction
  candles (e.g. both bearish) form an "open_close" key level between
  the first candle's close and the second candle's open -- exactly
  `key_levels.py`'s existing `detect_open_close_level()` (two
  consecutive same-direction candles' overlapping open/close range,
  level = the overlap midpoint). A third candle then closes back
  through both of them, engulfing them -- that's the confirmation. The
  entry itself is a limit order resting at that open_close level,
  filled whenever a later candle (4th, 5th, "depending on the case")
  actually retests it.
- **4th-man confirmation** -- tentatively already correct as-is.
  `fourth_man_confirmation_level()`'s V/A-shape price is already the
  reclaim candle's (`curr`'s) own close -- so `aggressive_entry_price()`
  for this trigger already computes the right number. What's still
  missing is treating it as an actual resting limit order rather than
  an instant fill assumption. Needs a direct "yes that's right" from
  the user before assuming it, same as the other two.

**Cancellation rule -- NOT a simple time/candle-count expiry.** Direct
instruction: cancel the resting limit order once price has moved,
without ever filling it, roughly 80% of the way toward what the
trade's own target would have been. Reasoning given directly: once
that much of the move has already happened without a fill, the reward
left even if it retraces and fills late is too small relative to the
risk to be worth taking -- continuing to leave the order resting past
that point risks a genuinely bad late entry instead of protecting a
good one. This needs to be measured against the SAME target computation
`run_backtest()` already produces (`primary_target()`, ERL-capped) for
the setup, not a separate number.

**Requested validation, once built:** an A/B backtest of this
retest-based limit-order model against the existing instant-fill
market-order model, using the same GitHub Actions workflow-dispatch
pattern used today for `avoid_rollover_entries` and `min_reward_r`
(temporary `.github/workflows/compare-*.yml`, deleted after results are
captured) -- compare before trusting either as the new normal, exact
same bar as every other change made this session.

**Why this is queued, not built now:** this is not a small change. It
needs (a) new fill-simulation logic inside `run_backtest()` that scans
forward from each trigger for either a genuine retest touch or the
80%-of-target cancellation condition, and treats "never filled" as its
own outcome (not a loss -- no trade happened at all), (b) real pending-
order lifecycle in live execution (`TRADE_ACTION_PENDING` +
`ORDER_TYPE_BUY_LIMIT`/`SELL_LIMIT` to place, a poll loop to detect a
fill vs. the cancellation condition, `TRADE_ACTION_REMOVE` to cancel),
and (c) full A/B validation before it should ever touch live money --
realistically hours of work plus a monitored deploy. Direct instruction
2026-09-01: queue it here fully scoped rather than build and deploy it
unvalidated right as the user goes offline for several weeks (exams,
Claude subscription lapsing) with no one able to catch a subtle bug in
core entry/execution logic. The live bot keeps running today's
validated market-order approach unchanged until this is picked back up.

## 2026-09-01 -- retest-fill entries A/B result: dramatically WORSE than market orders, live pending-order build NOT recommended

Follow-up to the entry above. Built `retest_fill_entries` as an opt-in
`run_backtest()` flag (backtest-only -- `bot/orchestrator.py` untouched,
nothing about live behavior changed) and ran the requested A/B: full
2025-2026 backtest, all 25 live instruments, aggressive style (the only
style this is meaningful for -- conservative's entry_price is already
the confirmation candle's own close, no level to retest), market-order
instant-fill (today's live behavior) vs. resting-limit retest-fill.

First run surfaced a real gap: `_resolve_trade_outcome`'s scan started
at `entry_idx + 1`, so a retest-fill candle that ALSO crossed
`stop_loss` within the SAME bar it filled on (a wide pullback candle
that fills the resting order and keeps falling through the stop before
closing) was silently treated as still open instead of an immediate
loss. Direct instruction 2026-09-01 to fix this and re-run rather than
leave it as a disclosed caveat. Fixed by including the fill candle
itself in the outcome scan whenever the fill happened on a genuinely
later candle than the trigger -- `_resolve_trade_outcome`'s existing
"stop wins same-candle ties" rule handles the rest, no new tie-break
logic needed; unchanged for the default instant-fill path, which must
not be touched.

**The fix made the result WORSE, not better** -- it was hiding real
losses, so the first run's numbers were actually flattering this model.
Corrected numbers (2nd run, after the fix):

```
                                 market order (today)      retest-fill limit
total trades                                     1398                    767
closed trades                                    1398                    767
wins                                              840                    222
win rate                                        60.1%                  28.9%
total R                                        1923.0                   88.1
avg R per trade                                 1.376                  0.115
```

(First run, before the fix, for reference: wins 284, win rate 37.0%,
total R 336.1, avg R 0.438 -- all overstated because same-candle
stop-outs on the fill candle were going uncounted.)

631 of 1398 (45.1%) of today's trades would NEVER have filled as a
resting limit order at all -- either price ran 80% of the way to target
first (RETEST_TARGET_EROSION_PCT) or the retest never came within
RETEST_FILL_LOOKAHEAD (120 H1 candles). Of the 767 that DID fill, the
average quality is now barely above breakeven (0.115R vs. 1.376R) --
both the quantity AND the per-trade quality collapsed, and the fix
removed what little cushion the first run showed.

**Why, most likely:** waiting for a retest doesn't just get a better
price on the same set of trades -- it changes WHICH trades qualify at
all. A trade that runs straight to target without ever pulling back
(the cleanest, most decisive continuations) never retests its trigger
level, so it's excluded from this sample entirely, even though it would
have been a live winner today. A trade that DOES come back and retest
is, by that same fact, showing hesitation/weakness right after its own
trigger -- and that hesitation correlates with going on to fail more
often, not less (including, per the fix above, failing WITHIN the same
candle that fills it). The entry-price improvement from waiting for the
retest is real but small next to the sample-composition effect: this
selects AWAY from the strongest movers and TOWARD the shakier ones.

**Recommendation: don't build the live pending-order mechanics
(TRADE_ACTION_PENDING placement, fill/cancel polling) queued in the
entry above.** The premise driving that request -- that resting limit
orders would perform better than market orders -- is directly
contradicted by this backtest, by a wide margin on every metric, and
the margin only got wider once the implementation was corrected. Worth
revisiting only if the per-trigger price definitions turn out to be
wrong in a way that specifically explains the win-rate collapse (e.g.
if "engulfing" should retest a different level than
`aggressive_entry_price()` currently computes for it -- see the
still-open per-trigger definitional questions in the entry above), not
by tuning RETEST_TARGET_EROSION_PCT/RETEST_FILL_LOOKAHEAD in isolation.
The code (`retest_fill_entries` flag, `_first_retest_fill()`, full test
coverage) stays in `runner.py` either way -- it's backtest-only and
harmless at the default (`False`), so there's no reason to rip it out,
just don't build on top of it without addressing why win rate collapsed
first.

**2026-09-01, later -- reverted.** Direct instruction: pull the code
back out of `runner.py`/`test_runner.py` entirely (`git revert` of
c662961 and 3e10422, clean, no conflicts -- 358 tests passing again,
same count as before this feature ever existed) and leave only this
written record for anyone who wants to look into it later. The idea
itself -- SLK entries as resting limit orders with a retest, not market
orders -- is NOT disproven in principle; what's disproven is THIS
mechanized version of it (aggressive_entry_price()'s existing key-level
price, waited on via `_first_retest_fill()`'s wick-touch + 80%-target-
erosion rule) on THIS strategy, by real backtest evidence, twice. A
future attempt should start from the still-open per-trigger
definitional questions above (particularly whether "engulfing" should
retest a different level than what `aggressive_entry_price()` computes
today), not from re-adding this exact implementation.

## 2026-09-01, 22:27 -- CRITICAL, UNINVESTIGATED: same signal re-attempted with different entry/stop/risk each time, produced 3 concurrent same-direction CHFJPY positions

Reported directly by the user via phone screenshots (MT5 app + Telegram
log), NOT yet investigated against the actual deployed code or the
audit database -- no VPS terminal access from the session that received
this report. Writing down the raw evidence precisely so it isn't lost
before someone with real access can dig in.

**Observed on the account (likely aggressive -- conservative was halted
on daily drawdown from 17:18 UTC onward today, see the entry above;
these attempts are timestamped after that):** three open CHFJPY SELL
positions, 6.42 lots each, entries at 197.336 / 197.360 / 197.328,
current price ~197.454 (all three underwater since price is ABOVE all
three short entries), combined floating P&L -$1,355.71
(-472.88/-376.70/-504.93). Balance 103,724.10, equity 102,368.39.

**Telegram log shows the SAME 17:00:00 UTC bearish CHFJPY signal
(engulfing, direct_mitigation, Weekly/Daily/H4 all bearish-aligned)
attempted at least twice with DIFFERENT numbers each time, both
declared execution_failed:**
- 18:34:01 -- entry 197.748, stop 197.8615 (`engulfing_kl_fallback`),
  target 197.4075, risking $500.00 -- `TRADE_RETCODE_INVALID_STOPS`.
- 18:58:35 -- entry 197.8515, stop 198.101 (`engulfing`), target
  197.103, risking $1,000.00 -- `TRADE_RETCODE_TIMEOUT`; log explicitly
  says "confirmed no position was opened."

Neither of those two logged attempts' entry_price matches ANY of the
three actual open positions (197.336/197.360/197.328) -- meaning there
were MORE attempts than the two visible in this scrollback, and at
least three of them (with yet other entry prices) succeeded.

**Why this looks different from the already-fixed duplicate-fill bug
(2026-08-26 EURCAD, "confirmation lost, retry created a second
position"):** that bug replayed the SAME order (same price/stop/risk)
after a lost confirmation. Here the entry price, stop_kind (`engulfing`
vs `engulfing_kl_fallback`), and risk amount ($1,000 vs $500) all
differ between attempts for the supposedly SAME 17:00:00 signal
candle -- that means the bot re-ran the FULL signal evaluation
(`run_backtest()` -> `_consider_entry()`) multiple times and got a
different answer each time, not that it blindly retried one failed
`order_send()`. Two candidate mechanisms, NEITHER confirmed yet:
(1) the underlying H1 17:00 candle's cached OHLC or the key level it's
    measured against shifted between polls (`live_cache_sync.py`
    revising recent bars as more data streams in), changing
    `entry_price`/`stop_loss` on each fresh `run_backtest()` call for
    what `entry_time` still reports as the same 17:00:00 candle: OR
(2) `_last_entry_time`/the audit-log watermark got reset or widened
    somewhere in between (a reconnect, a restart) such that the SAME
    candle fell back into the "since last checked" gap and got
    re-evaluated as if it were still unseen -- which would implicate
    the watermark-persistence fix landed earlier today (`5dcf2b8`) if
    that's confirmed to be the deployed code at the time these fired;
    NOT confirmed either way from this scrollback alone.
$500 vs $1,000 risk differing between attempts is ALSO consistent with
either mechanism if enough real time passed between them for account
equity/day_start_balance to move.

**Needs, once someone has VPS/terminal access again:** (1) confirm
which commit was actually deployed at 18:34-19:11 UTC today: (2) pull
every `entry_attempt` row for CHFJPY from the aggressive account's audit
db in that window (`sqlite3 aggressive_audit.db "SELECT * FROM decisions
WHERE instrument='CHFJPY' AND timestamp BETWEEN '2026-09-01T18:00' AND
'2026-09-01T20:00'"`) to see EVERY attempt, not just the two visible in
Telegram scrollback, and check whether `entry_price`/`stop_loss` genuinely
differ across rows sharing the same `entry_time`; (3) check
`journalctl -u slk-bot2` for that window for restarts/reconnects
coinciding with the differing attempts; (4) if mechanism (2) is
confirmed, the watermark-persistence fix needs to re-derive a stricter
"have we already ATTEMPTED this exact entry_time, regardless of
success/failure" check, not just "what's the newest entry_time seen" --
right now `AuditLog.last_entry_time()` already returns the newest
entry_time including failed attempts (see its own comment), so if this
IS the cause, the bug is likely somewhere in the RANGE match (`watermark
< r.entry_time <= new_candle.time`) or in something resetting
`_last_entry_time` mid-process, not in whether failures get logged.

**Immediate note, not a fix:** whatever the mechanism, the practical
effect is real risk beyond what was intended -- three same-direction
positions instead of one meant ~3x the designed per-trade risk was live
on one instrument at once. The risk manager's aggregate/day checks are
still the ultimate backstop (see the conservative-account halt earlier
today) but do not prevent duplicate ENTRIES into the same setup the way
`find_open_entry_row`-style per-trade dedup is supposed to.

**2026-09-01, 22:32 -- sharper evidence, still user-reported, still not
independently verified:** MT5 chart screenshot of one of the three open
positions shows its actual SL/TP lines: SL 198.101, TP 197.103. Those
are the EXACT sl/tp from the 18:58:35 attempt that computed entry
197.8515 and then failed with `TRADE_RETCODE_TIMEOUT` ("confirmed no
position was opened" -- per that attempt's own log line). But this
position's real entry is ~197.34 (one of the three fills logged in the
entry above) -- roughly 50 pips away from 197.8515, far beyond ordinary
market-order slippage (the GBPAUD incident that started this whole
session's slippage investigation was 54 POINTS, i.e. ~0.5 pip on a
5-digit pair; this is ~500 points on CHFJPY). Measured from where it
ACTUALLY sits: risk to that stop is ~0.76, reward to that target is
~0.23 -- worse than 1:3 IN THE WRONG DIRECTION, nothing like the
strategy's intended ~3:1.

This makes "ordinary slippage on the reported price" implausible as the
sole explanation and makes a THIRD candidate mechanism the most likely
one to check first, ahead of the two already listed above: a stale or
duplicate order carrying an OLD computation's `sl`/`tp` (from the
197.8515 attempt, or another attempt not visible in this scrollback) got
sent and filled much later, after price had already moved far past
where that stop/target made sense -- i.e. `place_market_order()`
sending the ORIGINAL computed `stop_loss`/`target_price` regardless of
how far the eventual fill lands from the ORIGINAL computed
`entry_price`, the same root mechanism as the GBPAUD incident
(entry_execution.py's request builds `sl`/`tp` from values computed
once, never re-derived from the actual fill), just far more extreme
here and compounded by whatever caused multiple attempts at the same
signal in the first place. `STALE_ENTRY_CUTOFF` (orchestrator.py) is
supposed to decline a signal this old outright rather than let it
execute -- worth checking directly whether it was bypassed, not just
whether it exists.

## 2026-09-01, later -- CHFJPY incident ROOT-CAUSED and fixed (two defects, both in mt5_execution.py)

Resolves the two entries above. The breakthrough was a detail in the
user's own screenshot that earlier passes had skimmed past: **all three
positions were 6.42 lots.** Identical. Three independent evaluations
would have produced three different lot sizes (the Telegram logs show
$500 and $1,000 risk on different attempts -- neither can yield the same
volume as the other). Identical volume means ONE computation sent
repeatedly. That killed the "multiple processes" theory (independently
disproven: `docker exec mt5 ps aux | grep run_live | wc -l` returned
exactly 2, the correct count) and pointed straight at the retry loop.

**Defect A -- ambiguous sends were blind-retried (fixed, `df55dc3`).**
`RETRYABLE_RETCODE_NAMES` conflated two categorically different
failures:
- REJECTED (`REQUOTE`/`PRICE_CHANGED`/`PRICE_OFF`) -- the broker
  answered and refused. Nothing landed; re-sending is safe.
- AMBIGUOUS (`TIMEOUT`/`CONNECTION`, or `order_send()` returning None)
  -- no answer came back at all. The order may have filled with the
  confirmation lost.

`_recover_landed_order()` was supposed to make retrying the ambiguous
case safe by asking the broker whether a position appeared -- but it
queries over the SAME link whose failure caused the ambiguity, so under
exactly the conditions that matter it under-reads. Live trace: three
`order_send` calls each timed out, each actually filled (197.336 /
197.360 / 197.328), each recovery check came back empty inside its 2.0s
settle window, the loop ran to `max_retries=3` (three retries, three
positions -- the numbers match exactly) and returned "confirmed no
position was opened," which is verbatim what the 18:58 Telegram message
said. The bot tracked none of them, so the risk manager was blind to all
three and nothing managed their exits.

Fix: ambiguity is now terminal. Verify once (still adopting the position
when the check DOES find it), then stop either way; only REJECTED sends
loop. This deliberately gives up genuinely-transient failures where
nothing landed -- `test_a_connection_failure_that_truly_failed_is_still_
retried` was renamed and its assertion inverted on purpose, with the
reasoning recorded in the test. One missed entry out of ~1400 trades is a
rounding error against a silently tripled position.

**Defect B -- stop/target never re-derived from the actual fill (fixed,
`9049e57`).** Even with A fixed, the surviving single position was still
wrong: the chart showed SL 198.101 / TP 197.103 on a position filled at
~197.34. Those are the values computed for entry 197.8515 at 17:00,
still sent verbatim at 18:58 after price had moved ~50 pips -- roughly
2x the trade's whole 0.2495 stop distance. Under Market Execution the
request's `price` field is ignored (fills at market) while `sl`/`tp` go
through exactly as computed, so the position carried risk ~0.76 against
reward ~0.23. Inverted R:R, never validated at that shape by any
backtest. Same root mechanism as the GBPAUD incident that opened this
whole session, just far more extreme.

Fix: `max_entry_drift_fraction` on `MT5Execution` -- decline when the
live mid price sits further from `entry_price` than that fraction of the
stop distance. Checked inside `compute_lot_size()` (the existing
pre-send validation gate) so declines surface as `decline_sizing_entry_
price_drifted` through the normal audit/Telegram path with the full
reason. None by default, matching `max_spread_points`; wired on at 0.25
in `run_live.py`. A test replays the exact CHFJPY numbers and asserts the
decline.

**Deliberately fail-closed, with a tripwire:** unreadable bid/ask
declines the trade (`decline_sizing_price_unavailable`) rather than
sending blind -- "couldn't check" must not read as "checked, all clear,"
which is the precise conflation that caused the earlier duplicate fills
(see `_our_open_tickets()`'s docstring). The risk this creates is real
and is called out in `run_live.py`: if that reason appears for EVERY
instrument right after a deploy, this broker/bridge isn't exposing
prices as expected and `max_entry_drift_fraction=None` should be passed
to turn the guard off, rather than leaving the bot silently idle.

**Still NOT fixed, deliberately:** `STALE_ENTRY_CUTOFF` remains 3h. The
drift guard makes it much less dangerous (a stale signal whose price has
moved now gets declined on price rather than executed on time), so
tightening it was left alone rather than changing two things at once
before an unmonitored stretch.

**Not addressed by either fix:** the three positions from this incident
were already open and untracked when these fixes landed. Nothing here
retroactively adopts or manages them -- they need manual closing or
manual reconciliation.

## 2026-09-01 -- stop-loss placement doesn't match SLK's own 5-15 pip range, in BOTH directions (found, NOT fixed)

Raised directly by the user looking at the CHFJPY chart: "is that where
the SL is meant to be based on SLK? That SL is too much for a logical
point." Investigated, and they're right -- but the problem is wider than
the one trade, and the obvious fix would make it worse.

**Too wide (CHFJPY).** entry 197.8515, stop 198.101 = 0.2495 = ~25 pips.
`MAX_NATURAL_STOP_PIPS = 30.0` is the gate deciding when a trigger's
natural anchor is "too wide" and the fallback takes over, so 25 passed
and the natural engulfing stop was used as-is. That constant's own
comment concedes the issue: *"STRATEGY.md's own worked examples run 5-15
pips; picked generously above that"* -- and it's flagged in the code as
"a judgment call, not a number from the source material." Twice the top
of the documented range.

**Too tight (EURGBP, same day).** `entry 0.85574 | stop 0.85564
(plug_and_play) | key level 0.85574 (V)` -- rejected with
`TRADE_RETCODE_INVALID_STOPS`. Entry EQUALS the key level and the stop
sits 1 pip from it.

**Why both happen, and why lowering the threshold is the wrong fix.**
For `DIRECT_MITIGATION` (both trades above),
`classify_entry_pattern()` returns `new_key_level` itself as
`reference_level`. Aggressive style then sets
`entry_price = aggressive_entry_price(reference_level) =
new_key_level.price`. The universal fallback is
`origin_stop_loss(new_key_level.price, ...)` = that same price +/- a 1
pip pad. So **for aggressive style the fallback stop is always ~1 pip
from entry, by construction** -- entry and the fallback's anchor are the
same number. It gets declined by the broker minimum-stop check, or
rejected as INVALID_STOPS, or (if it ever passes) stopped out on noise.

Which means lowering `MAX_NATURAL_STOP_PIPS` from 30 toward SLK's 15 --
the intuitive fix, and what "the stop is too wide" seems to call for --
would push MORE aggressive-style trades into a fallback that produces a
1-pip stop. It would trade the too-wide failure for the too-tight one at
higher volume. The threshold is not the defect; the fallback having no
valid anchor for an entry taken AT the level is.

Conservative style is unaffected by this specific collapse:
`conservative_entry_price()` is the confirmation candle's close, which
sits some real distance from the key level -- e.g. the 18:34 CHFJPY
attempt, entry 197.748 / stop 197.8615 (`engulfing_kl_fallback`) =
~11 pips, squarely inside SLK's 5-15.

**Deliberately NOT fixed 2026-09-01.** This is core strategy logic, it
needs a stop rule anchored to actual structure rather than to the entry
price itself, both failure directions have to be addressed together, and
any candidate needs the same A/B-over-2025-2026 validation every other
change this session went through. Landing that unverified hours before
several unmonitored weeks is exactly the wrong trade-off. Whoever picks
this up:
1. Decide what the fallback's anchor should be for an entry taken AT the
   key level -- candidates: the swept liquidity point
   (`candidate.liquidity_price`, already carried on `EntryCandidate` for
   this kind of purpose), the H4 level BELOW/ABOVE the reaction level,
   or the trigger candle's own structural extreme with a floor.
2. Only then revisit `MAX_NATURAL_STOP_PIPS`; 30 may well be right once
   the fallback is sound, and is certainly wrong to lower while it isn't.
3. A/B both changes together -- they interact, and moving one without
   the other is what makes this look like a threshold problem.

### CORRECTION, same night -- the framing above is wrong, and so were two of its numbers

Direct user correction, and it supersedes the framing of everything
above it. Recorded rather than edited away, because the wrong version is
the more instructive one.

**"CHFJPY was more than 30 pips."** Correct, and the reason it looked
otherwise is itself a defect. CHFJPY's pip is 0.01 (`DEFAULT_PIP_SIZES`),
so:
- computed entry 197.8515 -> stop 198.101 = 0.2495 = **24.95 pips**
- ACTUAL fill ~197.336 -> stop 198.101 = 0.765 = **76.5 pips**

The trade never opened at 197.8515. `_natural_stop_too_wide(entry_price,
natural, pip_size)` is evaluated against the COMPUTED entry, so it
measured 24.95, passed it under the 30 gate, and the live position then
carried 76.5. **The width check is measured against a price the position
may never open at** -- a third defect, distinct from the two fixed
tonight. (The entry-drift guard shipped tonight, `9049e57`, now declines
fills that land that far from the computed entry, so this specific gap is
incidentally closed on the live path -- but the check itself is still
measuring the wrong reference and would mislead again the moment the
drift guard is loosened or bypassed.)

**"All pairs don't have the same volatility rate."** Also correct.
`MAX_NATURAL_STOP_PIPS = 30` is one constant applied across every
instrument. Against the real pip table that is 0.0030 on EURUSD (~0.26%
of price), 0.30 on CHFJPY (~0.15%), 3.0 on XAUUSD (~0.07%), 30 points on
US30 (~0.07%) -- a ~4x spread in relative terms before differing
volatility is even considered. It is not a meaningful limit on any of
them, and normalising it (by ATR, by percent-of-price) would still be
the wrong fix -- see below.

**The core correction -- "in SLK it isn't about the pips on the SL."**
Direct quote: *"if you really understand SLK and where your immediate
invalidation point is your SL will not even be wide, that's the truth.
So if the bot is using wide SL it means it hasn't understood the
process."*

That invalidates the whole direction the entry above was heading in.
Points 1-3 treat this as "pick a better fallback, then retune the
threshold." But a stop is not a number to be capped -- it FOLLOWS from
correctly identifying the immediate invalidation point. A stop that
comes out wide is a SYMPTOM that the anchor is wrong, not a value to be
clamped. `_natural_stop_too_wide()` -> substitute-a-different-rule is
precisely a band-aid over a misidentified invalidation point: it makes
a bad anchor produce a plausible-looking number instead of surfacing
that the anchor was bad.

The unexplained detail from the entry above now has a likely
explanation: the CHFJPY stop anchored at **198.101** while all of 1 Sep
traded in the 197.1-197.7 band. That is not a tight stop gone slightly
wide. That is an anchor pointing at something with no relationship to
the setup -- `engulfing_stop_loss()` takes the more extreme of the
engulfing/engulfed candle wicks, so the engine believes one of those two
candles has a high near 198.09. Either the candle pair being matched is
not the one the setup is actually about, or the reaction level driving
it is stale/distant.

**So the real question is not "what should MAX_NATURAL_STOP_PIPS be" but
"why is the anchor landing 40+ pips away from the price action the setup
is built on."** Threshold work, fallback work, and ATR-normalisation are
all downstream of that and should not be attempted first -- any of them
would make the numbers look more reasonable while leaving a
misidentified invalidation point in place, which is a worse failure than
an obviously-wrong stop, because it stops being obvious.

Start here instead: take the CHFJPY 17:00 signal, pull the actual H1
candles the engine matched as the engulfing pair (and the H4 reaction
level it used), and check them against where price genuinely was. That
tells you whether this is bad cached data, wrong candle pairing, or a
stale reaction level -- and only then is it worth touching any rule.

## 2026-09-01 -- SOURCE STUDY: what SLK actually says about stop placement, vs. what the bot does

Direct instruction: *"You need to study what SL is and where invalidation
points are honestly for SLK based on bishop concept. Check if you can
find visual examples of bishops SL placements."* Done -- against the raw
transcripts and the chart-example deck, not the existing notes'
paraphrase. This supersedes the framing of every earlier stop-loss entry
in this file.

### 1. The empirical anchor: a real Bishop execution, exact numbers

`bishop_chart_examples_pages7-60.md` line 139, independently
re-verified from the rendered PDF page: EURCHF, **`BUY LIMIT 0.93193,
SL 0.93147, TP 0.93704`**.
- risk = **4.6 pips**
- reward = 51.1 pips
- **R:R = 11.1 : 1**

Note also it is a **BUY LIMIT** -- a resting order at a level, not a
market order.

### 2. The stated numbers, from the mentor's own Q&A (video-13)

A student asks the exact question this project keeps circling: *"I'm
currently struggling with stop loss placement... I don't always get a
standard, would I say, mechanical logic to stop loss placement... Apart
from, say, maybe 10 pips or stuff like that... is there another
mechanical method?"* The answer, in his words:
- *"These are seven pips stops"*
- *"I just moved it here to about **five pips**"*
- *"I just believe that **10 pips is fine**... I would just prefer to
  play the 10 pips stops"*
- *"and you're showing me **15 pips stops**. So I'm trying to look at
  how long it's going to take to hit one to three... **It might take
  very long time**"*

**READ THESE AS OBSERVATIONS, NOT AS A SPECIFICATION.** Direct user
correction after an earlier draft of this very entry made that mistake:
*"it's not just a fixed 10 or 15... Bishop's SL aren't small because he
wants it small, he is placing them at logical invalidation points."*

These numbers are what correct placement HAPPENED TO PRODUCE on those
particular charts. They are outputs, never inputs. Nothing in the method
targets a pip count, compares against one, or caps one. If the logical
invalidation point sits 25 pips away on a volatile instrument then 25
pips is the correct stop there; if it sits 3 pips away, 3 is correct.
The stops come out small so consistently because the invalidation point
is genuinely close when the setup has been read properly -- that is the
whole claim, and it is a claim about READING THE SETUP, not about
sizing.

This also dissolves the cross-instrument volatility problem raised
earlier in this file: no ATR normalisation, no per-instrument pip table,
no threshold of any kind is needed, because a pip number is never
consulted in the first place. The instrument's own structure supplies
the distance.

Elsewhere, same register -- qualitative, never numeric: *"my stop loss
was very tight. Not like very tight. It was a little bit, just a
little"*; *"my stop loss was very tiny here, like this"*; *"your stop
loss should have been very small."* The one place a number does carry
weight is as a REJECTION signal: 15 pips prompts *"how long is it going
to take to hit one to three... it might take very long time"* -- i.e. a
stop that comes out wide is read as evidence the setup is poor, and the
response is to pass on the trade, not to move the stop.

### 3. The mechanical rule -- WHERE the stop goes

Not a pip budget. A structural point:
- *"ideally, where we should place our stops in situations like this is
  **just below the low**, below this particular low"*
- *"We have a sweep, we have a break, internal range liquidity, QMRK
  level. We are playing above this QMRK level. The ideal place to place
  your stops is just going to be **above this particular high**... just
  place it above this particular high **to give it some space to
  break**"*
- *"Or many a times, I could just put my stop **at the A shape key
  level**"*
- *"it is always safer for me to put it above that high, **the strong
  high that was actually created**"* / *"when you catch an origin of a
  trade, just put it above"*

And the reasoning for the A/V point, which is the whole concept in one
sentence: *"there's every possibility that price would tap into my QMRK
level, hit my stop plus, **which is the V shape key level**, before it
continues to drop."* i.e. the stop must sit beyond the level price can
legitimately still tap without the idea being wrong.

**The invalidation point is the strong high/low created by the sweep --
or the OPPOSITE-shape key level -- not a distance from entry.** The
tight pip count is a CONSEQUENCE of picking that point correctly, which
is exactly the user's own formulation: *"if you really understand SLK
and where your immediate invalidation point is your SL will not even be
wide."*

### 4. What the code does instead

| Trigger | Code's anchor (`entries.py`) | Source's anchor |
|---|---|---|
| engulfing | more extreme of the engulfing/engulfed candle **wicks** + pad | the strong high/low the sweep created; or the opposite A/V key level |
| 4th man | pad beyond the **sweep candle's** low/high | closest match in the codebase -- this one is roughly right |
| plug and play | far edge of the overlapping **imbalance** | not a stop rule stated in these terms in the source |
| universal fallback | `origin_stop_loss(new_key_level.price)` = **the level being entered at**, + 1 pip | the OPPOSITE-shape key level, not the one you entered at |

Two concrete defects fall straight out of that table:

**(a) The fallback anchors to the entry's own level.** On aggressive
style `entry_price = aggressive_entry_price(reference_level) =
new_key_level.price`, and the fallback is that same price +/- 1 pip --
so the stop collapses onto the entry. That is the 1-pip EURGBP
INVALID_STOPS rejection (`entry 0.85574 | stop 0.85564 | key level
0.85574`). The source says the opposite: enter at the V-shape, stop at
the **A-shape** -- a DIFFERENT level.

**(b) The engulfing anchor has no structural meaning.** A two-candle
wick extreme is not "the strong high that was actually created." When
those candles happen to have a long wick, the stop lands somewhere
arbitrary -- which is the CHFJPY stop at 198.101 while all of 1 Sep
traded 197.1-197.7.

`MAX_NATURAL_STOP_PIPS = 30` then papers over both by substituting one
wrong anchor for another whenever the first looks too wide. Against a
source whose own numbers are 5-10 pips and who calls 15 too wide, a
30-pip gate is 2-6x too loose to catch anything meaningful -- and, as
established in the correction above, it is measured against the
COMPUTED entry, not the fill.

### 5. What the fix should use -- already present in the code

`EntryCandidate.liquidity_price` already carries *"the setup's own swept
liquidity point -- the particular high/low that was actually created by
this specific setup's sweep"* (its own docstring, citing this same Video
13 Q&A). **That is the mentor's "strong high that was actually
created", already computed and already threaded through to the entry
loop.** The stop rules simply don't consult it. A candidate rewrite:
1. Primary anchor: `candidate.liquidity_price` +/- pad -- the swept
   structural point.
2. Where the entry is AT a V/A-shape key level, the alternate anchor is
   the nearest OPPOSITE-shape key level, per *"put my stop at the A
   shape key level"* -- never the entry's own level.
3. Validate the ANCHOR structurally, never by pip width. An earlier
   draft of this list said "treat a stop wider than ~10-15 pips as a
   signal the anchor is wrong" -- which is the same pip-budget thinking
   in a new costume, and was corrected directly. The stop's width is an
   OUTPUT; it is not evidence of anything on its own, because a real
   invalidation point genuinely is further away on some instruments and
   in some conditions. What can legitimately be checked is whether the
   anchor is structurally coherent, all of which are answerable without
   reference to any pip count:
   - is it on the correct side of entry (already `_stop_on_correct_side`)
   - does it come from THIS setup's own sweep, rather than an unrelated
     older extreme (the CHFJPY failure -- an anchor at 198.101 when the
     whole session traded 197.1-197.7 is wrong because it belongs to a
     different piece of structure, NOT because 76 pips is a big number)
   - is the candle/level it derives from inside the setup's own window
   - for the opposite-shape fallback, does such a level actually exist
     nearby (if not, there is no valid stop and the setup is skipped)
   `_natural_stop_too_wide()` / `MAX_NATURAL_STOP_PIPS` should be
   DELETED rather than retuned or ATR-normalised: a width test cannot
   distinguish "correct anchor, volatile instrument" from "anchor
   pointing at unrelated structure", and substituting a second anchor
   whenever the first looks wide is what hides the real fault.
4. A/B over 2025-2026 before trusting any of it. Note this will also
   change R:R materially: the source's real trades run 5-11R, while the
   engine targets a flat 3:1 with an ERL cap. A correct tight stop makes
   the current 3:1 target far easier to reach, so trade count, win rate
   and average R will ALL move -- do not read one metric in isolation.

**Not implemented tonight, deliberately** -- this is core strategy logic
and needs the A/B plus a real design pass, not a midnight patch before
an unmonitored stretch.

## 2026-09-02 -- WORKED EXAMPLE: the CHFJPY stop, and why wide stops cancel the edge outright

The clearest single illustration of the anchor problem, on a real live
trade, with numbers read off the user's own chart. Keep this one -- it
is more use than any amount of description.

**The setup.** CHFJPY H1, 1 Sep. An impulsive red candle drops from
~197.69 to ~197.13. Price bounces off that low, puts in a retracement
high around **197.41-197.43**, and a SELL is taken at **197.345**,
targeting the low at **197.103**.

**Where the stop belongs.** Just above the retracement's own high --
about **197.44**. That high is the last structure holding the short
thesis up: above it, the "impulsive drop continues after this pullback"
idea is dead; anywhere below it, nothing has gone wrong yet. This is
the immediate invalidation point, arrived at structurally with no pip
count consulted.

**Where the stop actually went: 197.603.** That level sits inside the
consolidation price was ranging in BEFORE the impulsive drop -- i.e.
structure the setup had already broken through and invalidated on its
way down. It is not the invalidation point for a short taken on the
retracement OF that move. (The other position from the same incident
was worse still: 198.101, up at the 28 Aug highs, unrelated to this
setup entirely.)

**What it costs, same entry, same target:**

| | risk | reward | R:R |
|---|---|---|---|
| logical stop ~197.44 | ~9.5 pips | 24.2 pips | **~2.5R** |
| actual stop 197.603 | 25.8 pips | 24.2 pips | **0.94R** |

Nothing about the setup, the entry or the target changed. **The stop
placement alone turned a 2.5R trade into a sub-1R one.**

### The systemic consequence -- this is not a per-trade annoyance

Direct user framing: *"if SL are wide like this we will not even get a
1:1 RR."* Correct, and it generalises. If stops are systematically 2-3x
wider than the true invalidation point, then every trade's R is
understated by roughly that factor. A 3:1 target stops being a
reasonable objective and becomes arithmetically out of reach -- price
would have to travel two to three times further than the setup actually
calls for to pay the same R. That is not a scattering of bad trades; it
is the edge being cancelled across the whole book, on every instrument,
for as long as the anchors stay wrong.

It also reframes what "the strategy underperforms live" would even
mean: an engine measuring R against wrong stops cannot be evaluated on
R at all.

### Knock-on: `min_reward_r=1.0` is now suspect, and so is its A/B

The minimum-reward filter enabled 2026-09-01 skips any entry whose
ERL-capped target is under 1R at entry. **But R is computed from the
stop -- so when the stop is wrong, the filter is measuring the wrong
quantity.** This trade is the proof: 0.94R with the bad stop (the filter
would discard it), ~2.5R with the correct one (a perfectly good trade).
The filter is not distinguishing weak setups from strong ones; it is
partly distinguishing badly-anchored stops from luckily-anchored ones.

And the A/B that validated it (+16.1R, win rate 51.7% -> 51.9%) ran
against those same wrong stops throughout. It therefore measured "which
bad-stop trades are worth dropping", not "which setups are weak" --
which is a different question with no bearing on whether the filter is
correct once stops are fixed.

**Do not treat that validation as still standing after any stop-anchor
change. Re-run it.** The same caution applies to every other A/B in this
file that used R as its metric (rollover filter, retest-fill): they are
all denominated in a unit that this finding calls into question.

## 2026-09-02 -- SOLVED (from the visual source): the stop is the FAR EDGE OF THE IMBALANCE ZONE

The user supplied the 60-page Bishop chart-examples PDF directly, after
correctly pointing out that the repo contains NO images at all -- only
transcripts and second-hand notes -- and that every stop rule proposed
so far was therefore inferred from someone saying *"here"*, *"this
low"*, *"that high"* while pointing at a screen nobody could see. That
was exactly right, and it explains why two separate attempts at defining
the anchor both missed.

With the charts in hand the rule is unambiguous, and it is not what any
of the text-derived guesses said.

### The rule

Every example uses the same two-zone annotation:
- **PINK zone = behind entry (the risk side).** The imbalance/FVG price
  came back to rebalance.
- **TEAL zone = in front of entry (the reward side).** The continuation
  the trade is aiming at.
- Long -> pink below, teal above. Short -> pink above, teal below.

And:
- **ENTRY = the NEAR edge of the pink zone** (the edge price reaches
  first). Placed as a resting LIMIT order.
- **STOP = the FAR edge of the pink zone.**
- **TARGET = the teal zone's extent (or beyond it).**

**So stop distance = the height of the imbalance zone.** Nothing else.
No pip budget, no candle wick, no cap.

### The two measured examples that prove it is not a pip count

**EURCHF, M30 long (pages 5-6, chart + broker screenshot of the same
trade):** pink zone spans 0.93147-0.93193. Broker shows
`BUY LIMIT 0.93193` (top of pink = near edge), `SL 0.93147` (bottom of
pink = far edge), `TP 0.93704`. Risk **4.6 pips**, R:R **11.1:1**.

**EURNZD, H3 short (page 13):** pink zone spans 1.96156-1.96472, sitting
ABOVE entry. Entry 1.96156 (bottom of pink = near edge, and where the
"H3 Engulfing Confirmation Entry" label points); 1.96472 carries a RED
axis label -- the stop -- at the top of pink. Teal runs down to 1.94902,
carrying a TEAL axis label -- the target. Risk **31.6 pips**, R:R **~4:1**.

**Same rule. A 7x difference in pip count.** A 31.6-pip stop is
perfectly correct SLK when the zone is 31.6 pips tall. This kills every
threshold discussed in this file, including the "5-15 pips" that earlier
entries derived from the transcripts and the `MAX_NATURAL_STOP_PIPS = 30`
gate -- **which would have REJECTED the valid EURNZD trade above.** The
pip figures the mentor says out loud (five, seven, "10 pips is fine")
are measurements of whatever zone he happened to be trading, exactly as
the user said: *"Bishop's SL aren't small because he wants it small, he
is placing them at logical invalidation points."*

R:R is likewise not fixed -- 11:1 and 4:1 in these two -- because the
target is the liquidity draw, not a ratio. The engine's flat `rr=3.0`
default has the same shape of error as the stop thresholds.

### What this means for the code -- the rule is ALREADY implemented

`entries.py`'s `imbalance_stop_loss()` is correct as written, and its
docstring already states the exact invalidation logic observed here:
*"price is expected to sweep liquidity and rebalance THAT gap, and has
no logical reason to trade beyond its far edge to do so. Stop sits just
past the far edge."*

**The defect is its SCOPE, not its logic.** In `runner.py` it fires only
when `imbalance_overlap` is true (an imbalance overlapping the key
level, labelled "plug_and_play"). Every other trade falls through to
anchors with no structural meaning:
- `engulfing_stop_loss()` -- the more extreme of two candle WICKS
- `fourth_man_stop_loss()` -- the sweep candle's wick
- `origin_stop_loss(new_key_level.price)` as the width-triggered
  fallback -- which on aggressive style IS the entry price (1-pip stop,
  the live EURGBP INVALID_STOPS rejection)

Per this evidence the imbalance zone is not a special case for one
trigger type -- **it is the mechanism, in every example in the deck.**

### Candidate fix (NOT yet implemented)

1. Make the imbalance-anchored stop the PRIMARY rule for all triggers,
   not just `plug_and_play`.
2. Entry at the zone's near edge (this also matches the BUY LIMIT
   observation -- see the retest-fill entries above, whose failed A/B
   should be revisited once entry and stop are both defined off the same
   zone rather than against a market-order fill).
3. If no imbalance zone can be identified for a setup, SKIP it -- there
   is no valid stop. Do not fall back to a wick.
4. Delete `MAX_NATURAL_STOP_PIPS` / `_natural_stop_too_wide()` outright:
   proven above to reject valid trades.
5. Re-run every R-denominated A/B afterwards (see the 2026-09-02 entry
   on why they are all currently measured in a suspect unit).

Also note the earlier `stop_anchor="structural"` attempt (reaction-leg
extreme) was A/B'd and **failed** -- median stop 9.4 -> 24.3 pips, total
R 2671 -> 2392. It is off by default and should be REPLACED by the
zone-anchored rule above, not tuned. Its one real success (sub-2-pip
collapses 352 -> 10) came from removing the entry-price fallback, which
the zone rule also removes.

### Process note worth keeping

The repo still contains no images. The PDF was supplied directly in
chat. **Commit it (or attach it to a release) so this is reproducible**
-- otherwise the next session is back to inferring geometry from
transcripts, which is precisely how the last two attempts went wrong.

## 2026-09-02 -- ALL 60 PDF PAGES STUDIED: the stop rule, measured

Full page-by-page study of Bishop's chart-examples PDF, supplied
directly by the user. Every page read as an image. Raw per-page
measurements preserved in
`knowledge-base/supplementary/bishop_pdf_sl_measurements.md`.

**~35 measured trades. Zero exceptions.**

### The rule

Every example annotates two zones: a risk-side zone behind entry (pink;
grey in the one mindguy0x chart) and a teal target zone in front.

- **ENTRY = the NEAR edge of the risk-side zone** (grey axis label),
  placed as a resting LIMIT order
- **STOP = the FAR edge of that same zone** (always the RED axis label)
- **TARGET = the far edge of the teal zone** (always the TEAL label)

**So the stop distance is simply that zone's own height**, on that
instrument and that timeframe. The zone is the imbalance/FVG price
returned to rebalance; if price clears the whole gap, the reason for
the trade is gone.

Confirmed to the pip by the single page pairing a chart with its broker
screenshot: **EURCHF, pink zone 0.93147-0.93193, order `BUY LIMIT
0.93193 / SL 0.93147 / TP 0.93704`.**

### The measurements that kill every pip threshold

Observed stops, each in its own instrument's pips:

```
3.0  3.1  4.6  5.5  6.0  6.2  6.8  6.9  7.6  9.7  11.3 11.9 14.1 15.0
15.1 16.7 17.7 31.6 49.2 51.1 67.9 68.6 80.0 82.8 89.7 132.6 378 518.9
```

A ~170x spread, and every one of them is correct, because each is just
its own zone. **`MAX_NATURAL_STOP_PIPS = 30` would reject roughly eight
of these valid trades** -- including EURNZD (31.6), XAUUSD (~62.8),
USOIL (68.6 and 82.8) and XAGUSD (518.9).

Note also **CHFJPY H1 appears in the deck at 15.0 pips** -- the same
pair and timeframe where our live stops were 25.8 and 76.5.

Observed R:R: **2.1 to 11.1, typically 4-6.** Never the engine's flat
`rr=3.0`. The target is the liquidity draw, not a ratio -- the same
shape of error as the stop thresholds, and still unaddressed.

The identical stop rule appears on engulfing, breakout,
breakout-with-idm and 4th-man (V-shape) entries, across M30/M45/H1/H2/
H3/H4. **It is trigger-independent.**

### What was implemented

`stop_anchor="zone"` in `run_backtest()` (opt-in; default
`trigger_wick` untouched, nothing live changed):
- stop = far edge of the imbalance zone, for EVERY trigger, via the
  existing `imbalance_stop_loss()` -- which was already correct and
  already documented the right invalidation logic, but was only ever
  reached through `imbalance_overlap` ("plug_and_play")
- no width test
- **no zone => SKIP the setup.** No identifiable zone means no defined
  invalidation point, so there is no valid stop. This replaces falling
  back to a candle wick, which is what produced the CHFJPY stop at
  198.101 on a session that traded 197.1-197.7.

### Honest caveat on the entry side

Only the STOP anchor was changed. The deck also shows entry at the
zone's near edge as a LIMIT order, which this does not yet implement --
entry still uses `aggressive_entry_price()`/`conservative_entry_price()`
against a market fill. Changing both at once would make the A/B
unreadable, so entry is left for a second pass. That also means the
earlier retest-fill A/B (which failed) was testing limit-style entry
WITHOUT the matching zone-anchored stop, i.e. half the mechanism -- it
should be re-run once both sides come from the same zone.

## 2026-09-02 -- zone-anchor A/B, run 1: INVALID, and why (kept as the record)

First A/B of `stop_anchor="zone"` (run 33574694823) came back looking
like a heavy loss. It is not a verdict on the rule -- the run did not
test the rule. Keeping it because the way it failed is the useful part.

```
                               trigger_wick (today)                     zone
total trades                                   2697                      533
wins                                           1395                      247
win rate                                      51.7%                    46.3%
total R                                      2671.2                    419.0
avg R per trade                               0.990                    0.786
median risk (pips)                              9.4                      9.7
stops under 2 pips                              352                       56
stops over 30 pips                              318                      119
2164 of 2697 setups (80.2%) skipped for "no zone"
zone stop_kind breakdown: {'plug_and_play_zone': 533}
```

**The tell is the last line.** Every surviving trade is
`plug_and_play_zone` -- not one engulfing, 4th-man or breakout entry
got a zone-anchored stop. The implementation reused the existing
`overlapping` list, which is imbalances overlapping the KEY LEVEL
price. But that condition is exactly what already labels a trade
`plug_and_play` upstream. So the flag did not apply the zone rule to
every trigger; it kept the trades that already used it and skipped the
other 80%.

Which also reinterprets the headline numbers: median risk barely moved
(9.4 -> 9.7) because those 533 trades were **identical** to their
default versions. The R and win-rate drops are just what you get from
dropping 80% of the book, not from a different stop. This run measured
"take only plug-and-play trades" -- a question nobody asked.

**Fix:** `_entry_zone()` now finds the zone at the ENTRY rather than on
the key level -- within the same setup-scoped window, the imbalance
lying behind entry (below for a long, above for a short) whose NEAR
edge is closest to `entry_price`. That matches every example in the
deck, where entry sits on the near edge and the stop on the far one,
and where the zone frequently does not touch the reaction level at all.
Re-run: 33575395100.

**Process note for next time:** the `stop_kind` breakdown is what
caught this, and it was only in the output because the workflow printed
it. Keep emitting a breakdown of which code path actually produced each
result -- a headline table alone would have been read as "the rule
loses", and the wrong conclusion would have gone in the log.

## 2026-09-02 -- zone-anchor A/B, run 2 (valid): stops improve, win rate collapses

Run 33575395100, after `_entry_zone()` was fixed to find the zone at the
ENTRY rather than on the key level. All three triggers now get
zone-anchored stops (`engulfing_zone` 433, `fourth_man_zone` 337,
`plug_and_play_zone` 550), so this run does test the rule.

```
                               trigger_wick (today)                     zone
total trades                                   2697                     1320
wins                                           1395                      502
win rate                                      51.7%                    38.0%
total R                                      2671.2                    628.4
avg R per trade                               0.990                    0.476
median risk (pips)                              9.4                      7.7
min risk (pips)                                 0.2                      1.0
max risk (pips)                              2967.0                   2174.0
stops under 2 pips                              352                      145
stops over 30 pips                              318                      222
1377 of 2697 setups (51.1%) skipped for no identifiable zone
```

**What improved, and it is real:** median stop 9.4 -> 7.7 pips, the
1-pip collapse cut 352 -> 145, the >30-pip unrelated-anchor cases cut
318 -> 222, and the minimum stop is no longer 0.2 pips. The stops are
measurably better placed.

**What got worse:** win rate 51.7% -> 38.0%, total R 2671 -> 628, avg R
0.990 -> 0.476. On these numbers the change must NOT be enabled.

**Most likely cause -- the experiment is structurally incomplete.** In
the deck, entry sits at the zone's NEAR edge and the stop at its FAR
edge; those are one geometry, not two independent choices. This run
moved only the stop while entry still comes from
`aggressive_entry_price()`/`conservative_entry_price()` against a market
fill, which can sit anywhere relative to the zone. So trades get the
tight stop WITHOUT the favourable entry that makes that stop survivable
-- entry is frequently deep inside the zone (or beyond it), leaving far
less room before the far edge than Bishop's own trades have. A win-rate
collapse is the expected symptom of exactly that.

This was flagged as a caveat before the run, not after, and the result
is consistent with it. It is not yet evidence against the deck's rule;
it is evidence that half the mechanism performs worse than the current
whole.

**Next: test entry and stop together, both from the same zone** -- entry
as a resting order at the near edge (which needs fill simulation, since
such an entry may never fill: see the reverted retest-fill work,
c662961/3e10422, whose A/B failed for the mirror-image reason -- it
tested limit-style ENTRY without the matching zone-anchored STOP).
Neither half works alone; the deck only ever shows them together.

## 2026-09-02 -- zone selection (nearest vs widest) tested and RULED OUT

Before recommending it, tested the leading explanation for run 2's
win-rate collapse. Hypothesis: `_entry_zone()` picks the imbalance
nearest to entry, and our detector finds 20-26k imbalances per
instrument on H1 (EURUSD median 4.5 pips, p10 0.7; GBPJPY 7.6/1.1;
GBPNZD 10.1/1.5), so "nearest" would often be a sub-pip noise gap
rather than the one significant zone Bishop marks per setup. Consistent
with zone mode still emitting 145 stops under 2 pips.

Measured locally on the three cached instruments, both styles, full
history, by swapping only the selector:

```
baseline trigger_wick   trades=4183  win=53.1%  totalR=4449.9  avgR=1.064  medStop=12.5  <2pip=463
zone_entry NEAREST      trades=1809  win=41.7%  totalR=1132.8  avgR=0.626  medStop=10.4  <2pip=133
zone_entry WIDEST       trades=1718  win=42.0%  totalR=1077.9  avgR=0.627  medStop=12.5  <2pip= 73
```

Widest halves the sub-2-pip stops and restores a sane median stop, but
the outcome is unchanged: 41.7% -> 42.0% win rate, 0.626 -> 0.627 avg R.
**Zone selection is not the explanation.** Recording it so nobody spends
time re-deriving this refinement -- it is a real cleanup of the stop
distribution and makes no difference to results.

Also visible here: `zone_entry` does beat `zone` alone (41.7% vs 38.0%
at full scale in run 2), which supports the "entry and stop are one
geometry" reading -- the complete mechanism is better than half of it.
It is still well short of the current default.

### Two explanations remain, neither yet tested

1. **Our FVG detection is not his zone drawing.** We detect every
   3-candle gap. He marks ONE significant zone per setup, possibly by
   eye, possibly by a different construction (an open-close gap, the
   displacement leg's range). Applying his RULE to different ZONES is a
   different experiment.
2. **The deck is a curated teaching artifact, not a sample.** It shows
   trades worth publishing. Deriving the stop MECHANIC from it is sound;
   inferring a hit rate from it is not. Our engine selects a different
   population of setups, so his rule on our setups is not his trading.

**Recommendation: do not enable any zone mode.** Live keeps the current
stop logic. What is established and worth keeping is the measured rule
itself (`knowledge-base/supplementary/bishop_pdf_sl_measurements.md`,
all 35 measurements) plus yesterday's two live execution fixes.

## 2026-09-02 -- FINAL three-way A/B: both zone modes clearly underperform. Do not enable.

Run 33576378823. Full 2025-2026, 25 instruments, both entry styles.

```
                                  trigger_wick                zone          zone_entry
total trades                              2697                1320                1238
wins                                      1395                 502                 457
win rate                                 51.7%               38.0%               36.9%
total R                                 2671.2               628.4               534.2
avg R per trade                          0.990               0.476               0.431
median risk (pips)                         9.4                 7.7                 8.7
min risk (pips)                            0.2                 1.0                 1.1
max risk (pips)                         2967.0              2174.0              5063.0
stops < 2 pips                             352                 145                 127
stops > 30 pips                            318                 222                 233
setups skipped                               0                1377                1459
```

**Verdict: neither zone mode goes live.** Both cost roughly a quarter of
the win rate and three quarters of total R.

**CORRECTION to the previous entry.** It recorded that `zone_entry`
beats `zone`, based on a 3-instrument local preview (41.7% vs 38.0%),
and read that as supporting "entry and stop are one geometry". At full
scale the ordering REVERSES: 36.9% vs 38.0%. Completing the mechanism
does not rescue it, and that inference should not have been drawn from
three instruments. The corrected reading is that entry-at-the-near-edge
adds nothing here and slightly hurts -- 1459 setups skipped for never
filling, and a max stop of 5063 pips (worse than the default's 2967),
meaning some zones being selected are enormous.

**What is genuinely better, and is the only thing worth carrying
forward:** the stop DISTRIBUTION improves on every measure that
described a real live failure. The 1-pip collapse (the live EURGBP
INVALID_STOPS rejection) drops 352 -> 145 -> 127. The minimum stop stops
being 0.2 pips. The >30-pip unrelated-anchor cases (the live CHFJPY
198.101 stop) drop 318 -> 222. So zone anchoring does place stops more
sensibly -- it just does not make money on this engine's setups.

### Conclusion after a full night on this

The RULE is established beyond reasonable doubt: 35 measured trades
across 60 pages, zero exceptions, one broker screenshot confirming it to
the pip. Entry at the zone's near edge, stop at its far edge, stop
distance = the zone's own height.

Three faithful implementations were tested (stop only; entry+stop; and
nearest-vs-widest zone selection). All underperform the current default,
and the obvious refinement changes nothing. So the gap is NOT in the
rule as read, and not in zone selection. The two remaining explanations
were stated before these runs and both survive:

1. **Our FVG detection is not his zone drawing.** We detect every
   3-candle gap (20-26k per instrument, 10th percentile under 1.5 pips).
   He marks one significant zone per setup. Same rule, different zones,
   different experiment.
2. **The deck is a curated teaching artifact.** It shows trades worth
   publishing. The stop MECHANIC can be read off it; a hit rate cannot.
   Our engine selects a different population of setups.

Anyone picking this up should start at (1) -- specifically, work out what
construction actually reproduces the zones drawn on those 60 charts,
because everything downstream depends on feeding the rule the right
zones. `knowledge-base/supplementary/bishop_pdf_sl_measurements.md` has
every measurement to check a candidate construction against.

**Live is untouched throughout.** All three modes are opt-in; the default
`trigger_wick` path is byte-for-byte unchanged, and the bots continue on
`d340eb8` with yesterday's two execution fixes.

## 2026-09-02 -- CORRECTION: the pink boxes are a R:R TOOL, not FVGs. The real defect is the fallback.

**The user rejected the zone results and was right to.** Their words:
*"The pink box is not an FVG. Is the Stop section of a rise/reward ratio
tool."* Confirmed. That makes the rule I derived CIRCULAR -- the box's
far edge IS the stop by construction, so "the stop sits at the far edge
of the zone" says nothing about what structural feature set that price.
Every zone backtest above therefore tested my guess, not Bishop's
method, and a failing backtest of the wrong rule is not evidence against
the right one. A corroborating detail was already in my own notes and I
walked past it: on EURCHF the teal box tops at 0.93498 while the real TP
was 0.93704 -- a genuine target zone would not do that.

**What the charts actually say.** Page 8's annotation reads *"H2 High
swept, Low standing V-shaped kl 4thman's CE"* with the stop just below
that standing low -- a CANDLE extreme, matching video-13's "just below
the low, below this particular low". That is precisely what
`engulfing_stop_loss()` and `fourth_man_stop_loss()` already compute.

**So the anchors were never the defect.** `_natural_stop_too_wide()`
substituting `origin_stop_loss(new_key_level.price)` is. Isolating the
fallback trades (3 cached instruments, full history, both styles):

```
fallback fired        n= 846  win=36.9%  totalR= 277.1  medStop=25.4  <2pip=235
natural anchor kept   n=3337  win=57.2%  totalR=4172.8  medStop=11.7  <2pip=228
```

20% of trades producing 6% of the R, at 36.9% vs 57.2% win rate. And it
causes BOTH live failures at once: 28% of its trades carry sub-2-pip
stops (the EURGBP INVALID_STOPS rejection) while its median stop is
WIDER at 25.4 pips (the CHFJPY 25.8/76.5). Same mechanism, opposite
symptoms, because that anchor resolves to the entry price itself on
aggressive style and to something distant on conservative.

### Full A/B (run 33600184873, 25 instruments, 2025-2026, both styles)

```
                                    trigger_wick          trigger_only
total trades                                2697                  2741
wins                                        1395                  1465
win rate                                   51.7%                 53.4%
total R                                   2671.2                2835.8
avg R per trade                            0.990                 1.035
median risk (pips)                           9.4                  11.9
min risk (pips)                              0.2                   0.2
max risk (pips)                           2967.0                3753.0
stops < 2 pips                               352                   161
stops > 30 pips                              318                   647
```

**A real but MIXED result.** Win rate +1.7pp, total R +6.2%, avg R
+4.5%, and the 1-pip collapse halved (352 -> 161). But stops over 30
pips DOUBLED (318 -> 647) and max risk rose, because trades whose wide
natural anchor used to be swapped out now keep it. The fallback was
doing two jobs -- causing the 1-pip disaster AND hiding wide anchors.
Removing it wins on net but makes the CHFJPY-style failure more common,
not less.

Note also the local 3-instrument preview overstated this (55.3% vs 53.4%
win, +269R vs +164R). Direction held, magnitude did not -- same lesson
as the zone_entry preview that reversed outright at full scale.

**Recommendation: worth enabling, but it is a judgment call, not a
free win** -- it trades more wide stops for far fewer broken ones and
~6% more R. Left OFF pending the user's decision; `trigger_wick` remains
the default and live is untouched.

**Still open:** wide natural anchors. `trigger_only` does not address
them, it just stops hiding them. That is the remaining piece of the
CHFJPY problem, and the honest next question is what bounds a natural
anchor WITHOUT a pip threshold and without the entry-price fallback.

## 2026-09-02 -- WHERE Bishop actually puts the stop, and why ours goes wide

Direct question: from the PDF, what are the logical places he keeps his
SL? Re-read the charts with that specific question rather than looking
at the drawn boxes (which are a risk/reward tool -- see the correction
above).

**The answer is consistent across every chart, both directions, and all
four trigger types:**

> The stop sits **just beyond the swing extreme created by the
> confirmation itself** -- the low that held for a long, the high that
> held for a short. Always the immediate turn. Never an older level.

Evidence:
- p8 EURGBP H2 long: annotation reads *"H2 High swept, **Low standing**
  V-shaped kl 4thman's CE"*; stop 0.85289 sits just below that standing
  low.
- p17 AUDUSD M30 long: stop 0.69793 sits just below the low of the small
  dip where the engulfing formed.
- p29 CHFJPY H1 short: stop 199.787 sits just above the local swing high
  immediately before the drop -- NOT at an older level.

Matches video-13 word for word: *"just below the low, below this
particular low"* / *"above that high, the strong high that was actually
created"*.

**This is what `engulfing_stop_loss()` and `fourth_man_stop_loss()`
already compute.** The formulas were never the problem.

### So why do ours come out wide? Measured, not guessed.

For trades whose natural anchor exceeds 30 pips, compared the
confirmation candle's own range against the median range of the
preceding 20 bars:

```
EURUSD   wide(>30p) n= 178  median 2.43x the 20-bar median  |  normal n=1414  1.23x
GBPJPY   wide(>30p) n= 344  median 1.67x                    |  normal n= 978  1.09x
GBPNZD   wide(>30p) n= 519  median 1.42x                    |  normal n= 785  1.07x
```

**Wide anchors come from abnormally large confirmation candles.** The
rule is behaving correctly -- it puts the stop past the wick of a candle
that happens to be 1.4-2.4x normal size. A spike/expansion bar.

And that is exactly what Bishop does not trade. In every chart in the
deck his confirmation is an ordinary-sized bar at a clean turn, never a
2.4x expansion candle. He is filtering these out by eye; the engine has
no equivalent.

**So the missing rule is not a stop rule at all -- it is a SETUP
QUALITY rule:** if the confirmation candle is abnormally large for that
instrument at that moment, it is not the clean turn the method is
built on, and the setup should be skipped. Relative and self-scaling
(a ratio against recent range), so it carries none of the problems of
a pip threshold -- it adapts per instrument and per volatility regime
automatically.

This also reframes the "wide anchor" open item: there is nothing to fix
in the stop formula. The work is in not taking those setups.

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

## 2026-09-02 -- NEGATIVE RESULT: "skip abnormally large confirmation
## candles" does NOT work. Wide natural stops are not bad setups.

Tested the hypothesis recorded in the previous entry (that wide natural
stop anchors come from oversized confirmation candles, and that skipping
those setups would be the missing SLK "setup quality" rule). Swept three
skip thresholds on the three locally-cached instruments (EURUSD, GBPJPY,
GBPNZD), where "Nx" is the confirmation candle's range divided by the
20-bar median range at that moment:

                trades   win%   totalR   avgR   med stop   >30p
no filter        4218   55.3%   4718.8   1.119    15.5     1041
skip >2.5x       3787   53.8%   4136.6   1.092    14.5      825
skip >2.0x       3446   53.0%   3685.8   1.070    14.0      702
skip >1.5x       2745   52.5%   2903.1   1.058    13.0      488

Monotonically worse on every quality metric as the filter tightens. The
decisive number is **avg R per trade**, which falls 1.119 -> 1.058: it is
already normalized for stop size, so if oversized-candle setups were
genuinely lower quality, removing them would have RAISED it. It lowered
it. A large confirmation candle produces a wide stop AND a proportionally
wide run; the R holds. The filter removes good trades along with the
ugly-looking ones.

**Hypothesis rejected. Do not re-try a candle-size / volatility-ratio
setup filter without new evidence -- this is a measured dead end, not an
untested idea.**

What this sharpens (the distinction now has numbers on both sides):

- Fallback stops ARE broken: 846 trades, 36.9% win, 277.1R, median stop
  25.4 pips, 235 of them under 2 pips. Source is
  `_natural_stop_too_wide()` substituting
  `origin_stop_loss(new_key_level.price)`, which resolves to the ENTRY
  PRICE itself on aggressive style (`aggressive_entry_price()` returns
  `key_level.price`) and to a distant level on conservative. This single
  substitution caused BOTH live failures -- the sub-2-pip EURGBP stops
  and the far-too-wide CHFJPY stop.
- Natural anchors are fine even when wide: 3337 trades, 57.2% win,
  4172.8R, median stop 11.7 pips.

CHFJPY was a FALLBACK stop, not a wide natural anchor. So the earlier
conclusion that "the bot hasn't understood SLK" is correct but much
narrower than a stop-placement philosophy: `engulfing_stop_loss()` and
`fourth_man_stop_loss()` already compute exactly what Bishop does (just
beyond the swing extreme the confirmation itself created). The defect is
one substitution rule that fires above `MAX_NATURAL_STOP_PIPS = 30.0`
and replaces a correct stop with an incoherent one.

NEXT CANDIDATE (untested, do not enable): when the natural stop exceeds
the width limit, SKIP the trade instead of substituting a fake stop.
Must be A/B'd at full 25-instrument scale on GitHub Actions before any
live change. Note this is not the same as the rejected filter above --
that one skipped on candle size regardless of stop coherence; this one
skips only the trades currently getting a fabricated stop.

Two decisions still open and belonging to the operator, not the bot:
  1. Whether to enable `stop_anchor="trigger_only"` live (full A/B run
     33600184873: win 51.7%->53.4%, total R 2671->2836, sub-2-pip stops
     352->161, but >30-pip stops 318->647). A judgment call, not a free
     win. Currently OFF.
  2. Whether to pursue the skip-instead-of-substitute rule above.

## 2026-09-02 -- CORRECTION: the "100% follows Bishop's rule" claim was
## measured against too weak a test. Operator was right.

Operator sent Bishop's EURJPY H2 engulfing example beside one of our own
rendered GBPJPY charts and said the placements are wrong. They are.

The fidelity test reported earlier that day asked only: is the stop beyond
the CONFIRMATION CANDLE's own extreme? engulfing and fourth_man scored
100% on that. But Bishop's stop in the EURJPY chart clears the whole leg
that made the turn -- the descending cluster of lows into the entry -- not
just the one or two candles of the confirmation. Re-measured against that
standard:

                    clears confirmation   clears 5-bar leg   clears 10-bar leg
  engulfing              100.0%               55-63%             43-45%
  fourth_man             100.0%               48-51%             29-38%
  plug_and_play           34-44%               16-18%              9-11%
  FALLBACK                  5-11%              0-2.6%              0.0%

So more than half of even the "good" stops sit INSIDE the swing: price can
take out the recent lows without invalidating anything and still stop us
out. The earlier 100% was true of the test I ran and NOT true of the claim
I made from it. Anchors are `engulfing_stop_loss()` (min/max of two candle
wicks) and `fourth_man_stop_loss()` (one candle's wick) -- single candles
by construction, so they cannot clear a leg except by luck.

The operator's screenshot is the cleanest single example: GBPJPY short,
entry 135.145, real anchor 135.510 (36.5 pips, above the swing high),
replaced by the fallback with 135.155 -- ONE pip. Price ticked up into
that pip, stopped the trade at -1R, then collapsed for what would have
been a full winner on the correct anchor.

Mode comparison (3 cached instruments, aggressive), adding `trigger_skip`
(natural anchor, skip the setup when it is too wide rather than
substitute):

  mode           trades  win%   totalR   avgR  medStop  clears5  clears10
  trigger_wick     2140  63.2%  3235.0  1.512     7.3    40.5%    28.4%
  trigger_only     2140  65.2%  3372.4  1.576     9.9    48.6%    35.0%
  trigger_skip     1845  67.5%  3122.2  1.692     8.2    46.0%    32.2%
  structural       2147  64.4%  2929.3  1.364    23.5    92.1%    86.2%

Two things follow, and they point different ways:

1. `trigger_only` beats the default on every axis -- win rate, total R,
   average R, sub-2-pip count (431 -> 210) and structural fidelity. The
   fallback is strictly harmful; removing it costs nothing.
2. `structural` is the ONLY mode that places stops where Bishop places
   them (92% vs 40-49%), and it earns ~9% less R than the default here.

Point 2 is NOT settled, and this engine cannot settle it. Two confounds
both favour tight stops: entries fill at the exact computed price with no
fill test at all (`open_position()` on the trigger candle -- neither the
market orders we run live nor real limit orders), and targets are a
multiple of the stop, so a wider stop must chase a proportionally more
distant target. A 1-pip stop scoring +3R in this engine is fiction.

Earlier that day I marked `structural` "FAILED -- do not enable" on the
grounds that it widened the median stop 9.4 -> 24.3 pips. That was the
wrong criterion by the operator's own standing correction (width is an
output, never a target), and the docstring has been revised to say so.

NEXT: fix the fill model before running any further stop-anchor A/B. Until
entries are filled against real price action, every comparison in this log
is biased toward whichever rule keeps stops tightest.

## 2026-09-02 -- LIVE AUDIT DB READ: the bot has a DELIVERY problem, not
## a strategy problem. 1 order placed in 42 attempts.

Pulled the real numbers off both audit DBs on the VPS (read-only). Every
entry attempt ever made, by outcome:

  order actually placed (decision='allow')            1
  execution_failed                                   12
  decline_stale_signal (all 2h+ past candle close)   22
  decline_daily_aggregate_risk                        4
  decline_sizing_entry_price_drifted                  2
  decline_sizing_symbol_not_tradeable                 1
                                                     --
                                                     42

`orchestrator.py:449` writes 'allow' only when `place_market_order()`
succeeded, so that 1 is literal: one order has ever reached the broker.

**Timing (delay measured from CANDLE CLOSE, not candle open -- entry_time
is the bar's OPEN, so a perfectly prompt trade already reads ~1h stale on
a naive timestamp-minus-entry_time measure; an earlier pass got this
wrong and reported "no fresh signals at all"):**

  <5m       0     <-- nothing is ever prompt
  5-30m     5
  30-60m    9
  1-2h      6
  2h+      22

**All 17 execution failures, by broker retcode:**
  INVALID_STOPS  12    TIMEOUT  4    CONNECTION  1

**stops_level = 0 on EVERY symbol on BOTH accounts** (checked live via the
mt5linux bridge inside the `mt5` container; spreads 0-9 points). The
broker imposes no minimum stop distance at all. That RULES OUT "stop too
close to price" as the cause of any INVALID_STOPS rejection -- including
the 1-pip ones, which are still far outside a 0.2-pip spread. The only
remaining explanation is the stop being on the WRONG SIDE of the current
price by send time, i.e. price had already traded past it during the
30min-2h the order sat unsent.

Two claims made earlier this session and now retracted:
1. "INVALID_STOPS is the 1-pip fallback bug" -- wrong; 7 of 12 had
   perfectly normal stops (9.3, 10.4, 11.4, 13.9, 14.2, 25.9, 46.6 pips).
2. The revised "4 of 12 are the fallback" -- also wrong. stops_level=0
   means NONE were rejected for distance. The fallback defect is real and
   documented above, but it did not cause these rejections.

**Everything traces to one cause: the bot is 30 minutes to 2 hours late
on every signal.** Lateness produces the 22 stale declines, the 12
wrong-side rejections, the 2 drift declines, and the CHFJPY 50-pip fill.
41 of 42 failures are downstream of it. Stop placement -- the subject of
most of this session -- is a real but SECOND-ORDER problem: it changes
what happens on trades that reach the broker, and almost none do.

**Open positions: 0 on both accounts.** The three untracked CHFJPY
positions have closed (consistent with the -$1,355 the operator saw).
The EURCAD/EURNZD/GBPAUD timeouts left no orphans either. Note this does
NOT vindicate `_recover_landed_order()`'s "confirmed no position was
opened" message -- CHFJPY carried that exact message while three
positions were open. The message remains untrustworthy.

Both accounts are on MetaQuotes-Demo (see launch_bot1.sh), so all of the
above is simulated money and purely diagnostic.

NEXT, in priority order:
1. The lateness. Either fix the delay, or make it harmless by resting
   LIMIT orders at the computed entry instead of sending market orders
   late (the operator's own SLK entry model, and the reverted work from
   earlier this session). Limits are the stronger option: they remove
   wrong-side rejections, drift, and stale-signal loss in one move.
2. Rotate the Telegram bot token -- it is hardcoded in launch_bot1.sh and
   was pasted in plaintext into a chat transcript. Move it to
   ~/.mt5_bot_env with MT5_PW.
3. Stop-anchor choice (trigger_only / trigger_skip / structural) -- still
   open, still unresolved by backtest because of the perfect-fill model,
   and now clearly not the bottleneck.

## 2026-09-02 -- Resting limit entries wired in (OPT-IN, still OFF live)

Built in response to the audit above: the bot is never prompt, and market
orders sent 30min-2h late caused 41 of its 42 failed attempts. A resting
limit makes lateness harmless rather than something to detect -- the order
sits at the level the setup was sized for, so it fills at that price or
not at all. It is also simply what an SLK entry IS: a predefined key level
price is expected to return to, not a chase.

Enabled with `--entry-order-type limit`. Default stays `market`, so
nothing changes until it is passed. To try it on one bot:

    (edit launch_bot1.sh, add:  --entry-order-type limit)
    systemctl restart slk-bot1

What happens per signal under `limit`:
  1. Re-check the setup against every H1 candle that closed since it fired
     (`setup_validity.check_setup()`, reading the cache
     `sync_recent_from_mt5()` just refreshed -- live bars, not history).
     Stop breached, or 80%+ of the target already made => decline, logged
     as decline_setup_stop_breached / decline_setup_target_achieved.
  2. Re-run the aggregate risk check counting every ALREADY-RESTING order
     as though it had filled. Without this the same daily headroom is
     handed to every limit placed that day and a simultaneous batch fill
     breaches the cap. Reuses RiskManager rather than reimplementing it.
  3. Place the limit AT the computed entry; log allow_pending.
  4. On every later poll, `_reconcile_pending_entries()`: promote fills to
     tracked positions, cancel orders whose setup has since died, cancel
     everything at the Friday cutoff, and WARN about anything resting at
     the broker this process did not place (a restart loses the in-memory
     map but not the orders -- never silently adopt).

Weekend rule: WEEKEND_CUTOFF_WEEKDAY/HOUR_UTC, currently Friday 19:00 UTC.
Cancellation is in-process in UTC rather than the broker's own
ORDER_TIME_SPECIFIED expiry ON PURPOSE -- this terminal's clock runs +3h
against UTC, and an expiry sent in the wrong frame fires either three
hours early or three hours into the weekend. 19:00 is a deliberately
conservative guess: THE BROKER'S ACTUAL CLOSE IS STILL UNCONFIRMED.

Verified in the live check this session: `stops_level=0` on every symbol
on both accounts, so nothing here is at risk of the broker's minimum-stop
rule; and `_account_state()` reads positions_get() only, which is why
step 2 above had to be added explicitly.

NOT DONE, and needed before this can be called complete:
  - Closing open POSITIONS before the weekend. This change only cancels
    resting ORDERS. There is no close-position method in mt5_execution.py
    at all, so "flat before the weekend" is only half-implemented.
  - Confirming the broker's Friday close time and correcting the cutoff.
  - A restart still loses the pending-order map (orders are warned about,
    not re-adopted). Persisting it the way `last_entry_time()` is
    persisted would close that.
  - None of this has run against a live terminal. It is unit-tested
    against the fake only -- same caveat as every other MT5 path here.

## 2026-09-02 -- Weekend rule completed: positions are closed, not just
## orders cancelled. Cutoff is the New York close, DST-aware.

Operator: "My broker closes when the New York exchange closes. Close open
positions too before the weekend."

The close is 17:00 Friday NEW YORK, which is NOT a fixed UTC hour: 21:00
UTC under EDT, 22:00 under EST. It is computed in the America/New_York
zone via zoneinfo and converted, so it tracks the DST changeover on its
own. The previous placeholder (a flat 19:00 UTC) is gone -- it would have
been an hour wrong for half the year and, in winter, would have flattened
three hours early.

Three windows, all measured backwards from that close:
  NO_NEW_ENTRIES_MINUTES_BEFORE_CLOSE = 240   -> stop opening (Fri 13:00 NY)
  FLATTEN_MINUTES_BEFORE_CLOSE        = 60    -> close everything (Fri 16:00 NY)
  the close itself                            -> flat

Stopping entries 4 hours out is a judgment call, not a measured number: a
trade opened at 16:00 and force-closed at 16:00 is closed by the clock
rather than by its stop or target, so it books noise. Flattening 60
minutes early rather than at the bell is deliberate too -- spreads widen
sharply into the Friday close, and closing needs the market open enough
to actually fill.

`_market_closed_for_weekend()` exists as its own case because
"minutes until the next Friday close" rolls forward the instant the close
passes -- so on a Saturday it reports six days, and a window measured only
that way reads the weekend itself as the safest moment of the week. A
restart over a weekend with orders resting has to still cancel them.

New in mt5_execution.py:
  - `our_open_positions()` -- positions carrying our magic; None on a
    failed read, which the caller escalates ("CHECK BY HAND") rather than
    treating as "the account is flat".
  - `close_position(ticket)` -- MT5 has no close action, so this is an
    opposing DEAL carrying `position: <ticket>` for the position's
    BROKER-REPORTED volume (not anything this process remembers, which
    would over- or under-close a partially closed position). An already
    closed position is SUCCESS. An ambiguous close is NEVER retried: a
    repeat close against a position that already closed opens a NEW
    position the other way, which is worse than the problem it would fix.

Scope: positions with OUR magic are closed, including untracked ones (the
CHFJPY triple-fill case -- ours whether or not this process remembers
placing them, and exactly the ones most likely to be left over a weekend).
A position opened by hand in the terminal is left alone and logged.

Verified end-to-end: run_once() at Friday 20:15 UTC closes an open
position and empties the book. 258 tests pass. Still unit-tested against
the fake only -- no live terminal.

STILL OPEN:
  - Enabling any of this. `--entry-order-type limit` is off; the weekend
    flatten, however, is ALWAYS ON once deployed (it is not gated on the
    limit flag) -- that is deliberate, it is a safety rule, but it means
    deploying this changes live behavior on Fridays.
  - A restart still loses the pending-order map (orders are warned about,
    not re-adopted).

## 2026-09-02 -- FIXED: every restart logged a false "daily drawdown
## breach" halt

From the operator's log after the 5abf2df deploy:

    12:18:54 INFO  starting live loop: prop_firm, instruments=(...)
    12:18:55 ERROR HALTED: daily drawdown breach: 6.86% >= 4%

One second after startup, on an account that had lost nothing that day.
6.86% was its CUMULATIVE loss since the phase began (~$6,860 of 100,000).

Cause is an ordering bug in `run_once()`. `__post_init__` seeds
`day_start_balance` with the PHASE starting balance (100,000) because a
cold start has no account reading yet. `run_once()` then built `state`
from that seed and only afterwards called `_roll_day_if_needed()` to
snapshot the real balance -- but `state` was already constructed, so
`check_health(state)` measured today's drawdown against 100,000 and read
the account's whole-phase loss as a single day's.

Self-clearing (the next poll, ~5s later, has the correct snapshot and
`halted` is re-derived every iteration), so NOTHING was ever actually
blocked by it. That is also why it survived this long: it looked like a
transient startup artifact. But it fired a false ERROR and a Telegram
halt alert on every single restart, and a halt alert that is usually
wrong is one that gets ignored on the day it is right.

Fix: `_roll_day_if_needed()` now returns whether the baseline moved, and
`run_once()` rebuilds `state` when it did, before anything reads it. Two
tests: a restart on an account down 6.86% since phase start does NOT halt
and snapshots 93,140 as the day's baseline; a genuine -6% intraday move
still halts.

Also seen in the same log, unfixed and lower severity:

    09:53:29 WARNING new_candle_closed(USDCAD) failed:
             copy_rates_from_pos(USDCAD, H1) failed: (-1, 'Terminal: Call failed')

Single-instrument bridge failure, caught and skipped per-instrument, with
the failing/recovered dedup already in place so it logs once rather than
per poll. Same class as the reconnect flakiness that produces the
catch-up lateness -- it costs that instrument that hour's check. Not
separately worth fixing: it is the Wine/mt5linux bridge being unreliable
on an oversubscribed box, which is the condition the resting-limit work
exists to tolerate rather than eliminate.

## 2026-09-02 -- PATTERN AUDIT: swept the codebase for repeats of the two
## bug shapes that account for nearly everything found this session.

Operator, reasonably: "What if another error comes up. It seems every
[time]." Rather than reassure, swept for the specific shapes rather than
reading hopefully. Nearly every bug this session was one of two:

  A. "can't tell" collapsed into a definite answer ("nothing is there",
     "all clear", "already handled")
  B. state read after the thing it was derived from changed

Six more instances of A found, FIVE OF THEM IN CODE WRITTEN TODAY.

A1-A5: `self._mt5.positions_get() or ()` / `orders_get() or ()`, in
our_open_positions(), close_position(), pending_tickets_by_symbol(),
_our_pending_tickets() and _our_open_tickets(). The real MT5 API returns
**None on failure** and an **empty tuple when there genuinely is
nothing**, WITHOUT RAISING -- so `or ()` made a broken query
indistinguishable from an empty account, and the surrounding try/except
never fired because nothing was thrown.

  - The worst was close_position(): a failed read fell through to "if not
    matches" and returned SUCCESS, reason "position was already closed".
    The weekend flatten would have logged every position as dealt with
    while they sat open through the weekend -- i.e. the one rule the
    operator asked for by name would have reported success while doing
    nothing.
  - _our_open_tickets() is the function whose OWN DOCSTRING is about this
    exact conflation ("'Can't tell' must mean 'can't tell' to the
    caller, not 'assume empty'"). The docstring only ever covered the
    exception path; `or ()` defeated it on the None path. A documented
    rule is not an enforced one.

A6: `_candles_since()` returned `[]` on an unreadable H1 cache. An empty
list means "nothing has happened since the signal, it is fresh" to
check_setup(), so an unverifiable setup was declared ALIVE and a limit
rested against a thesis nobody had checked. Now returns None; the entry
path declines (decline_setup_unverifiable) and the reconcile path LEAVES
a resting order alone rather than cancelling -- "don't know" argues for
doing nothing, not for acting, and the order costs nothing while it waits.

B: only one mutation site remains (day_start_balance), fixed earlier
today by rebuilding `state` when the baseline moves.

267 tests pass. One `or ()` deliberately kept, at the fill-price lookup in
_recover_landed_order(): the position is already confirmed adopted via the
ticket-set diff, and that read only decorates the result with a price, so
a None there costs a log field rather than a correctness guarantee. It is
commented as such so it is not "fixed" or copied.

LESSON for whoever picks this up: `or ()`, `or []`, `or {}` on any MT5
query in this codebase is a bug until proven otherwise. The API's failure
signal is a falsy return, so the idiom that looks like defensive tidying
is precisely what erases the distinction that matters.

## 2026-09-02, 15:25 -- LIVE CONFIGURATION AS LEFT (operator away ~1 month)

Both bots on commit `fa6e0ac`, MetaQuotes-Demo, 25 instruments each.

  slk-bot1  conservative  port 18812  MARKET orders  <- CONTROL, unchanged
  slk-bot2  aggressive    port 18813  LIMIT orders   <- the change under test
                                      (--entry-order-type limit)

Deliberately ONE variable. The stop anchor stays at the default
`trigger_wick` on both, despite trigger_only/structural being unresolved,
because stacking a second change would make a month of data
unattributable. Limits are also the change that addresses what is
actually broken: lateness caused 41 of the bot's 42 failed attempts;
stop placement only governs orders that reach the broker, and almost
none did.

Why this was enabled before a live test rather than after: on market
orders the bot places roughly 1 order in 42 attempts, so a month of it
produces nothing to learn from. The account is demo, so the downside is
data rather than money, and bot1 is untouched as a fallback. A guaranteed
dead month is worse than an untested code path on play money.

Survivability checked before leaving: `Restart=always` on both units, and
/srv at 50% (48G used, 49G free) -- the audit DBs and candle cache have
room to grow for far longer than a month.

WHEN YOU COME BACK, one command answers whether it worked:

    journalctl -u slk-bot2 --since "30 days ago" | grep -c allow_pending

Any number above zero means orders reached the broker, which has
essentially never happened on this deployment. Compare against bot1's
`allow` count over the same window for the A/B.

REVERT (puts bot2 back to exactly bot1's behavior):

    sed -i 's| --entry-order-type limit||' /srv/slk-bot/launch_bot2.sh
    systemctl restart slk-bot2

FIRST UNATTENDED EVENT: Friday 20:00 UTC (16:00 New York), the weekend
flatten runs for the first time on both bots. Look for `weekend_flatten`,
or `CLOSE IT BY HAND` if a close did not go through. This is
close_position()'s first contact with a real terminal -- it is unit-tested
against the fake only.

STILL OPEN (nothing urgent, all recorded above in full):
  - stop anchor: trigger_only / trigger_skip / structural, unresolved
    because the backtest's perfect-fill model biases every comparison
    toward tight stops. Fix the fill model before trusting another A/B.
  - the Telegram bot token is exposed in launch_bot1.sh and in a chat
    transcript. Operator is aware and chose to leave it.
  - a restart still loses the pending-order map (resting orders are
    warned about, not re-adopted).

## 2026-09-02, 16:46 -- CAUGHT BY A TELEGRAM LOG: the 3h staleness gate
## sat IN FRONT of the limit path and would have neutered the whole month

An hour after limits went on, bot2 sent:

    EURCHF: entry_attempt (decline_stale_signal) -- signal candle is
    0 days 07:00:00 old (cutoff 3:00:00) -- market has likely moved past
    this level, not attempting it late

That decline is `_check_instrument`'s STALE_ENTRY_CUTOFF check at
orchestrator.py:446, which `continue`s BEFORE `_consider_entry()` is ever
called -- so the limit path, and `check_setup()` with it, never ran.

Consequence had this not been caught: bot2 would have declined exactly the
same 2h+ bucket as bot1 -- 22 of the bot's 42 lifetime attempts, the
single biggest failure category and the whole reason limits were enabled.
The month's experiment would have produced nearly the same nothing as
market orders, and the comparison would have looked like "limits don't
help" when limits had never been reached.

Fix: STALE_ENTRY_CUTOFF_LIMIT = 24h, used when entry_order_type ==
"limit". The 3h number was always a PROXY for a question about price
("has the market moved past this level?"), and it is the right proxy for
a market order, which buys at whatever price exists on arrival.
`check_setup()` answers that question directly from the candles, and a
resting limit fills at the level or not at all -- so the proxy is not just
unnecessary there, it actively blocks the mechanism that replaces it.

24h is a backstop, not a staleness judgment: the storyline gate
independently re-checks Daily/H4 alignment before any entry search runs,
so anything reaching this point already has current higher-timeframe
context. Market mode keeps 3h unchanged, with a test pinning both.

Also visible in the same log, noted not fixed: the second EURCHF signal
had entry 0.94139 EQUAL to its key level with a 2-pip stop -- the
aggressive plug_and_play case where `aggressive_entry_price()` returns
the key level itself. Harmless on this broker (stops_level=0 confirmed,
spreads 2-9 points), and the stop-anchor work above is where it gets
addressed properly. Not touched now: one variable at a time.

269 tests pass.

## 2026-09-02, 17:00 -- ROOT CAUSE OF THE LATENESS, and it was fixable
## all along: 36,000 pointless broker calls an hour

Operator, on being told limits were a workaround for lateness: "Why can't
we not fix this data being stale or late issues." Correct instinct. I had
concluded the lateness was structural ("you cannot make a 25-instrument
pass finish inside 5 minutes on 2 shared vCPUs") without ever measuring
WHY the pass was slow. It was not the pass. It was this:

`MT5Client.new_candle_closed()` called `fetch_candles()` -- a live
copy_rates_from_pos over the RPyC/Wine bridge -- unconditionally, once
per instrument, per poll. At POLL_SECONDS=5 and 25 instruments:

    720 polls/hour x 25 instruments x 2 bots = 36,000 bridge calls/hour

against an MT5 terminal running under Wine on a box already at load ~7
with 1.4GB of 2GB swap in use. THAT is the queue the signals were sitting
behind.

And essentially every one of those calls was guaranteed to find nothing.
An H1 candle only closes on the hour; between :00 and :59 there is
nothing to fetch. The clock already knows this for free.

Fix: `new_candle_closed()` now compares the last candle it was given
against `_last_completed_open(granularity)` -- pure arithmetic, no broker
call -- and returns None immediately when no new bar can exist yet. Same
50 real calls an hour instead of 36,000, a 720x reduction.

Behaviour is provably unchanged: every skipped call is one that would
have returned None anyway (it is the same `_last_closed_time` comparison,
just reached without a round-trip first). If a broker's bar is late, the
next poll five seconds later still asks. An unknown granularity never
skips, so a timeframe added later fails safe toward an extra fetch rather
than going blind.

Two things I had wrong and should not have asserted:

1. "The lateness is structural, you can't optimise it away." Wrong -- I
   generalised from cold-start storyline timings (which ARE genuinely
   slow: a fresh process rebuilds every instrument's Weekly/Daily/H4
   bias) and never separated that one-off cost from steady state. The
   steady-state cost was almost entirely this call.
2. The EURCHF "7 hours old" decline that prompted this was NOT the bot
   running 7 hours behind. bot2 had restarted 24 minutes earlier, and a
   fresh process reconstructs its watermark from `audit_log.
   last_entry_time()`, so it correctly replayed everything since that
   instrument's last audited entry -- including 07:00's signals. Restart
   replay and steady-state lag are different problems that both surface
   as `decline_stale_signal`, and today's deploys produced a lot of the
   former. Some meaningful share of the "22 of 42 at 2h+" is restart
   replay, not queue delay, which means the 42-attempt audit sample is
   more contaminated than presented.

Limits remain the right change regardless -- they make a late or replayed
signal harmless rather than merely rarer -- but they are no longer the
ONLY answer to lateness, and should not have been sold as one.

399 tests pass (bot + engine).

## 2026-09-02, 17:30 -- the 24h limit window was unsafe as justified;
## added the current-bias check that makes it defensible

Operator, on being told limit mode allows signals up to 24h old:
"under 24h how." Right to ask -- the justification I gave was wrong.

I wrote that 24h was safe because "the storyline gate independently
re-checks that Daily/H4 bias still aligns before any entry search runs."
It does not, on the path that matters.
`_storyline_hunted_anywhere_in_gap()` returns True if the gate said HUNT
at ANY of the last 72 candles (3 days), which exists so a signal missed
during an outage still gets reported. Only the FAST path checks the
current candle; the gap-replay path passes on a historical hunt state.

So under the 24h window a limit could rest on a setup whose Weekly/Daily/
H4 alignment had since flipped -- and `check_setup()` would never catch
it, because it compares price against stop and target and never looks at
bias at all. The order would sit there holding a thesis that had expired,
possibly for a full day.

Fix: `_place_limit_entry()` now re-asks `_storyline_says_hunt()` about the
CURRENT candle and declines with `decline_bias_no_longer_aligned` if the
answer is no. `_check_instrument()` records which candle it is evaluating
(`_current_candle_time`) so the limit path can ask.

Market mode is deliberately untouched: it fires once and is done, so a
stale bias cannot keep costing anything after the fact. A resting order is
different in kind -- it commits to the thesis for as long as it sits
there, which is exactly why it needs the thesis to hold NOW.

275 tests pass.

Note for later: this is the second time today that gap-replay behavior
correct for REPORTING turned out to be wrong for ACTING. The first was the
3h staleness gate blocking the limit path. Worth checking any future
"never silently drop a signal" mechanism against the question "and should
it be traded?", which is a different question with a different answer.

## 2026-09-02, 18:00 -- FILL MODEL BUILT. Every backtest number in this
## log before now was roughly 3x inflated.

Operator: "this 80% was just a number I formed, can we run a test over the
last year and this year to find what optimal % is best." The engine could
not answer it -- it opened every position at the exact computed price on
the trigger candle, so there was no resting order for a cancellation rule
to act on. Built the fill simulation, which also closes the perfect-fill
hole that has undermined every comparison in this file.

Three fill models now available on run_backtest(), default unchanged:
  entry_fill="instant"       (default) fill at entry_price on the trigger
  entry_fill="market_close"  fill at the trigger candle's CLOSE
  entry_fill="limit"         rest at entry_price; fill only if price
                             returns, with cancel_at_target_fraction and
                             a 48-candle expiry

Measured on the three cached instruments, aggressive:

  fill model                     trades   win%   totalR   avgR  medStop
  instant at key level (FANTASY)   2140  63.2%   3235.0  1.512      7.3
  market order at close            2001  43.5%   1218.7  0.609     20.8
  limit, no cancel                 1759  39.9%   1010.1  0.574      7.5
  limit, cancel at 80%             1137  42.0%    738.0  0.649      9.5

**The default is not achievable by any order type.** For aggressive style
entry_price IS the key level, and by the time the confirmation candle has
closed price has usually reacted away from it -- so "instant" was filling
at a price nobody could have got. Every headline number in this log
(3,235R here; the 2,671R / 2,836R stop-anchor A/Bs; the candle-size sweep;
the structural-vs-default comparison) was produced under it and is
inflated by roughly 3x. Win rates around 63% are really around 43%.

ANSWER TO THE QUESTION ASKED: the cancellation threshold barely matters.
Across 30%-100% average R moves 0.642 -> 0.653 and total R 688 -> 749 --
flat. 80% was a fine guess; so is anything from 50% to 100%. This is not
a knob worth tuning, and that is a useful thing to know rather than a
disappointment.

WHAT IS NOT SETTLED: market_close earns more TOTAL R (1218 vs 738) while
limit+cancel earns more PER TRADE (0.649 vs 0.609) on far fewer trades,
with a much tighter median stop (9.5 vs 20.8 pips). Total R is what
compounds at fixed fractional risk, so market looks ahead -- BUT the
engine still models no spread and no slippage, and both fall entirely on
the market side (measured live: 54 points of slippage on a single GBPAUD
fill). A 480R gap is not obviously larger than that unmodelled cost.
Adding spread/slippage is the next thing needed before this comparison
decides anything.

Also note limits fill only 82% of setups with no cancel, 53% at the 80%
threshold -- the missing ones are largely runaway winners that never came
back, which is exactly the adverse selection a resting order buys. That
is a real cost of the approach, not a modelling artifact.

Nothing about the live bots changes on this commit. bot2 stays on limits:
the case for it live was never its backtested R, it was that market orders
were physically failing to reach the broker (1 order placed in 42
attempts), and that is still true.

## 2026-09-02, 19:00 -- VERDICT REVERSED AGAIN, and this time in the
## operator's favour: with realistic fills, `structural` WINS on every
## metric. The stop placement they have been describing all along is right.

Operator marked up two rendered charts by hand: blue where the entry
should be, red where the stop should be. The red mark sat well below the
swing -- the invalidation point, exactly as described since the CHFJPY
argument. Two separate claims in that markup; both checked.

CLAIM 1: "it's not waiting for the retracement to the KL." Measured:

    93% of limit fills land on the very NEXT candle
    median departure from the level before filling: 1.9 pips (GBPJPY),
                                                    0.9 pips (EURUSD)
    over half fill after price moved less than 2 pips away

So on the chart it does look instant. But the entry LEVEL is structurally
right: 71.5% of resting orders sit INSIDE the confirmation candle's body
(the open-close level SLK asks for), only 11% at an edge. What is really
happening is that on H1 the next candle almost always reaches back into
the prior candle's body, so the retracement completes inside one hour.
Live that is fine -- a real limit fills tick by tick. In the BACKTEST it
is a genuine weakness worth recording: for those 93% next-candle fills
the engine cannot tell whether price touched the entry before or after
running toward target, and it assumes before. That is optimistic and
currently unquantified.

CLAIM 2: the stop is in the wrong place. Correct, and the fill model
built earlier today finally allows a fair test. Same three cached
instruments, aggressive, entry_fill="limit", cancel at 80%:

  stop anchor    trades   win%   totalR   avgR  medStop  clears leg
  trigger_wick     1137  42.0%    738.0  0.649      9.5      33.3%
  trigger_only     1159  43.4%    782.1  0.675     13.6      44.3%
  structural       1336  49.3%    901.3  0.675     30.6      93.7%

`structural` wins on trade count, win rate, total R, ties on avg R, and
clears the leg 93.7% of the time against 33.3%. There is no axis on which
it loses.

THIS REVERSES THE EARLIER VERDICT, TWICE OVER. Under the old instant-fill
model structural looked WORSE (2929 vs 3235 total R), and that is the
number this log used to leave it disabled. The instant-fill model was
filling every trade at the exact key level -- a price only reachable if
you already had the position -- which flattered tight stops specifically,
because a tight stop only survives if the entry is perfect. Give the
entry a realistic fill and the tight stop's advantage disappears
entirely: it is now the worst of the three.

So the operator's position, held against my numbers since the CHFJPY
argument, was right, and my numbers were wrong for a reason that had
nothing to do with stops: the fill model. Recorded plainly because the
sequence matters -- "the backtest disagrees" was never a good answer when
the backtest could not model the thing being argued about.

Wired `--stop-anchor` through run_live.py -> LiveBot -> run_backtest so
this is now settable live (default unchanged).

CAVEAT before acting: three instruments, and the intrabar-fill assumption
above still favours limits generally. Worth a full 25-instrument run.

## 2026-09-02, 20:00 -- PDF committed, and it settles the entry question:
## the missing rule was never the STOP, it was requiring the RETEST.

The deck is now in the repo (knowledge-base/supplementary/source/), so
none of this has to be taken on trust again.

Page 6 is the decisive page: a broker screenshot of a resting
`BUY LIMIT 0.93193 | SL 0.93147 | TP 0.93704` on EURCHF M30, with the
market reading **0.93330** at the top of the same screen. The order sits
~14 pips BELOW price, UNFILLED, waiting for a pullback to a level price
has already left. Page 17 (AUDUSD M30, entry 0.69853 / stop 0.69793)
shows the same shape.

Ours did the opposite. It rested the limit at the key level the
confirmation had just formed at -- where price still was -- so 93% of
fills landed on the very next candle after a median departure under 2
pips. A market order wearing a limit's label, exactly as the operator
said when they looked at the charts.

Added `min_departure_r`: price must travel this many R AWAY from the
entry, in the trade's favour, before a touch counts as a fill. 0.0
(default) is the old behavior. Sweep, aggressive, cancel at 80%:

  departure  trades   win%   totalR   avgR  medStop
       0.00    1137  42.0%    738.0  0.649      9.5
       0.50    1082  47.6%    948.5  0.877      9.2
       1.00     991  50.6%    991.3  1.000      8.2
       1.50     846  52.7%    929.3  1.098      6.6

And crossed with the stop anchor:

  anchor        dep  trades   win%   totalR   avgR  medStop  fill=1cdl
  trigger_wick  0.0    1137  42.0%    738.0  0.649      9.5       94%
  trigger_wick  1.0     991  50.6%    991.3  1.000      8.2       61%
  structural    0.0    1336  49.3%    901.3  0.675     30.6       80%
  structural    1.0     765  52.8%    792.1  1.035     21.1       35%

**THIS RESOLVES THE TENSION AND REVERSES THIS MORNING'S RECOMMENDATION
AGAIN.** With the retest required, the ORIGINAL tight anchor wins outright
(991R vs structural's 792R) AND its 8.2-pip median stop matches the
source material's own measured distances (median 9.7, range 3.1-17.7 over
15 trades). structural's 21-30 pips remains 2-3x anything in the deck.

So the sequence was: structural looked worse under fantasy fills, better
under naive limit fills, and worse again once the limit models what
Bishop actually does. The stop anchor was never the defect. The defect was
that we were not waiting for the retest, and a tight stop cannot survive
an entry taken before the pullback -- which is exactly why widening the
stop appeared to help.

CAVEAT, and it is not small: 61% of fills still land on the FIRST candle
after the signal even at 1.0R departure, meaning one candle both travelled
1R away and came back. On H1 highs and lows have no order, so the engine
assumes depart-then-return when return-then-depart is equally consistent
with the data. That inflates the departure results by an unknown amount.
Resolving it needs M1/M5 data to sequence the intrabar path, which the
cache does not currently hold.

RECOMMENDATION FOR bot2, superseding the structural one made at 19:00:
revert to trigger_wick. It is both the better performer under the honest
fill model and the one matching the source. min_departure_r is NOT yet
wired to the live bot -- backtest only.

## 2026-09-11 -- OPERATOR-REPORTED INCIDENTS FROM ~2 WEEKS UNATTENDED
## RUNNING (2026-09-02 to 2026-09-11). Recorded verbatim first, root-caused
## below where confirmed, still OPEN where not. Do not treat anything in
## this entry as fixed unless it says so explicitly.

Operator was away for exams; checked in after roughly a week and a half
and reported multiple serious problems from the Telegram log, plus a
direct message from a friend running a comparable SLK bot on IC Markets /
cTrader instead of MT5. Summarized in the operator's own words: "The bot
worked so bad for the last 2 weeks... I even have a note full of errors
detected by me." Reported in full below, then triaged.

### INCIDENT 1 -- XAGUSD: logged $1,000 risk, opened position was ~$9,999

    2026-09-06 22:16:33,670 INFO bot.orchestrator: XAGUSD: entry_attempt
    (allow_pending) -- limit resting at 65.91 -- setup intact -- entry
    level was revisited and would have filled
      signal candle: 2026-09-04 18:00:00+00:00
      bullish | confirmation: fourth_man (direct_mitigation) | effective
      bias: Weekly | aligned: Daily,H4
      bias by timeframe: Weekly=bullish, Daily=bullish, H4=bullish
      entry 65.91 | stop 64.72699999999999 (fourth_man_structural) |
      target 67.467 | key level 65.91 (V)
      risking $1,000.00

    [IDENTICAL second line, same instrument, same signal candle, same
    entry/stop/target, same "risking $1,000.00" -- timestamped
    2026-09-06 22:16:33,670, the SAME MILLISECOND as the first]

Operator: "this opened with about $9999 check not $1000." A single H1
signal correctly logged at $1,000 intended risk apparently turned into
roughly 10x that when it actually opened. THIS IS A REAL-MONEY-SHAPED BUG
even though the account is demo -- the same bug on a funded account would
be a account-ending event on one trade.

STATUS: NOT YET ROOT-CAUSED. Two lines with byte-identical content at the
exact same millisecond is the loudest single clue in the whole report --
that is not consistent with a normal retry (which would carry a different
timestamp) and points at either (a) two live bot processes running
concurrently against the same account, in lockstep from a shared restart,
each independently reaching and logging the same decision, or (b) a
single process calling the logging/placement path twice for one signal.
Both would explain a doubled-or-worse position; neither is confirmed.
Diagnostics requested from the operator, not yet returned:
  - `git log -1` on the VPS checkout, both bot dirs -- confirms which
    commit was actually running when this happened, since the repo has
    moved since the last confirmed deploy and this may predate fixes
    already in main.
  - `ps aux | grep run_live` -- checks for a duplicate/zombie bot2 process
    (Restart=always plus a hung old process not exiting cleanly is a
    known failure shape for exactly this symptom).
  - The XAGUSD rows from `conservative_audit.db`/`aggressive_audit.db`
    around 2026-09-04 through 09-07 -- to see whether the audit DB itself
    (not just Telegram) shows one entry_attempt row or two, and whether
    two tickets exist.
  - `positions_get`/`history_deals_get` for XAGUSD in that window, read
    directly from the terminal -- to see the actual ticket count, lot
    sizes, and realized loss.
Do not accept "duplicate process" or "duplicate log call" as the answer
until the audit DB and ticket history confirm it -- this session has
guessed wrong on root cause from log text alone multiple times already
today (see the several retracted INVALID_STOPS theories and the
stop-anchor verdict reversed twice), and this incident is too costly to
guess on again.

### INCIDENT 2 -- a signal ~2 days stale still got a resting limit placed

Same XAGUSD example as Incident 1: signal candle 2026-09-04 18:00:00,
order allowed 2026-09-06 22:16:33 -- roughly 52 hours later. Operator:
"Our limit order that is a day stale have caused a problem. This is over
$9999 in SL."

`STALE_ENTRY_CUTOFF_LIMIT = timedelta(hours=24)` exists at HEAD
(orchestrator.py, added 2026-09-02 commit 6f0700f) specifically to
decline anything older than this under `--entry-order-type limit`. 52
hours should have tripped it and produced `decline_stale_signal`, not
`allow_pending`.

STATUS: NOT YET ROOT-CAUSED, likely connects to Incident 1 rather than
being independent. Two live hypotheses, not yet distinguished:
  (a) the VPS was running a commit older than 6f0700f/current HEAD when
      this fired, so the 24h limit cutoff simply did not exist yet on the
      deployed code -- possible, since the operator's last confirmed
      "git pull" was mid-session and several more commits landed
      afterward that may not have been deployed;
  (b) the cutoff exists in the deployed code but the staleness
      computation itself is wrong in the specific case of a signal that
      only becomes reachable again after an extended MT5 outage (see
      Incident 4) -- e.g. if `new_candle.time` used in the comparison
      does not reflect true "now" the way it's assumed to.
Resolve by first confirming the deployed commit (see Incident 1's
diagnostics); if the fix was deployed and still failed, the staleness
arithmetic itself needs a live trace, not a guess.

### INCIDENT 3 -- a real, correct decline (recorded for contrast, not a bug)

    2026-09-07 21:11:29,270 INFO bot.orchestrator: EURJPY: entry_attempt
    (decline_sizing_entry_price_drifted) -- EURJPY is at 179.428, 1.8045
    away from this signal's 181.232 entry -- more than 100% of its 0.573
    stop distance (limit 0.573). A market order would fill here while the
    stop/target still go out sized for 181.232, so the trade would carry
    a risk:reward it was never validated at. Declining instead.
      signal candle: 2026-09-07 02:00:00+00:00
      bearish | confirmation: plug_and_play (direct_mitigation) |
      effective bias: Weekly | aligned: Weekly,Daily,H4
      entry 181.232 | stop 181.80499999999998 (plug_and_play_structural) |
      target 179.51300000000006 | key level 181.232 (open_close)

Operator flagged this as "What it could have been, another option to make
money gone" -- i.e. frustration at a decline, not a bug report. This is
the entry-drift guard (added 2026-09-01 after the CHFJPY incident) working
exactly as designed: EURJPY moved 180 pips (over 3x its own stop distance)
between signal and this check, a MARKET order here would be badly
mispriced. Declining it was correct. Recorded because it illustrates the
cost side of the drift guard plainly, and because it is exactly the kind
of missed opportunity that `--entry-order-type limit` on this same signal
would have converted into a resting order instead of a discard -- if
EURJPY had been on limit mode. Worth a direct decision from the operator:
is bot1 (still market-only) costing more in missed EURJPY-style moves than
it saves in avoided bad fills? Not answerable without more of this data.

### INCIDENT 4 -- repeated MT5 authorization/connection failures, at least
### one caused the account picture to be temporarily wrong

    2026-09-11 07:02:16,897 WARNING reconnect failed (attempt 3, next
    retry in 20s): mt5.initialize() failed: (-6, 'Terminal: Authorization
    failed')
    2026-09-11 07:02:36,298 WARNING reconnect failed (attempt 4, next
    retry in 40s): mt5.initialize() failed: (-6, 'Terminal: Authorization
    failed')
    2026-09-11 07:03:04 through 07:03:09+ -- new_candle_closed(SYMBOL)
    failed: copy_rates_from_pos(SYMBOL, H1) failed: (-10004, 'No IPC
    connection') for USDJPY, USDCHF, USDCAD, AUDUSD, NZDUSD... (repeats
    across essentially every instrument in the same few seconds)

Earlier the same session:
    2026-09-11 06:24:05 -- "reconnected to MT5"
    2026-09-11 06:24:06 -- "resources at recovery: load=10.9,5.7,5.6
    mem=2.7/7.8GB swap=2.0/2.0GB cpus=2"
    2026-09-11 06:52:38-40 -- BOTH bots logged "starting live loop" again
    within 2 seconds of each other (fresh process start, not just a
    reconnect) -- i.e. something restarted both bot processes, not just
    reconnected MT5. Operator: "I did[n't] do anything via terminal the
    bot restarted I think."

STATUS: This is the box's stability, not the trading logic. Load 10.9 on
2 vCPUs (5.4x oversubscribed) and swap AT its 2.0GB CAP are both worse
than the numbers that already caused the original 2026-08-26 lateness
investigation. "Terminal: Authorization failed" from mt5.initialize()
is MT5-terminal-level (session/license), not a network blip -- consistent
with the underlying Wine-hosted terminal itself crashing or losing its
session under memory pressure, which then cascades into "No IPC
connection" for every symbol until reconnect succeeds. This is very
likely THE mechanism behind both Incidents 1 and 2: a terminal-level
crash-and-restart is exactly the boundary condition under which
`_last_entry_time` / pending-order bookkeeping can be re-derived
incorrectly (see Incident 2's hypothesis (a)/(b)) and, if systemd's
Restart=always fires before the old process has fully released its MT5
session, is also how a second process could end up briefly live
alongside a new one (Incident 1).

Not yet checked: whether `systemctl status` shows a clean single PID per
unit with no restart flapping, and what `journalctl -u slk-bot1 -u
slk-bot2` shows for actual process START events (not just MT5 reconnects)
across the full two weeks -- needed to know how many times this actually
happened, not just the one morning the operator captured.

### THE OPERATOR'S ARCHITECTURE QUESTION -- "why sequential, why not one
### script per instrument running independently"

Direct quote (paraphrased from voice-to-text): getting all candles for
all instruments "in a screenshot order" [sequentially] is what's "making
us lose money" from lateness, so why not run each instrument as its own
separate, independently-running script instead of one process working
through 25 instruments in turn.

ANSWERED DIRECTLY, not deferred: this is the right question to ask, and
the honest answer is that the sequential SCAN was already fixed on
2026-09-02 (36,000 pointless MT5 calls/hour down to ~50, commit 5edbf9e)
and is very unlikely to be today's bottleneck. What Incident 4 shows
instead is the MT5 terminal itself failing at the authorization/IPC
level -- a problem that splitting into one script per instrument would
make WORSE, not better: each instrument would need either its own MT5
terminal instance (25 Wine-hosted terminals instead of 2, on a box
already swapping at its cap with 2 vCPUs) or would still funnel through
the SAME single terminal per account via the SAME mt5linux bridge, in
which case splitting into separate processes changes nothing about the
bridge's stability and only adds process-count overhead. Recorded so this
specific proposal is not revisited without new evidence -- the honest
open problem is terminal/bridge stability under memory pressure, not
scan architecture.

### RAISED BY THE OPERATOR, FROM A FRIEND RUNNING A COMPARABLE BOT

Friend's own SLK-style bot runs on IC Markets via the cTrader Open API,
not MT5. Quoted from the operator's conversation with them: "No call
limit right? / They have rate limits for sure / But it's generous / And
you can tell your ai to do research and work around it."

WORTH TAKING SERIOUSLY, NOT YET ACTED ON. cTrader's Open API is a proper
network protocol (JSON/Protobuf over a socket) that a Linux process talks
to directly -- no Wine, no desktop terminal, no IPC bridge, none of which
this deployment can currently keep stable under its own load. If Incident
4 is confirmed as this deployment's primary remaining failure mode (looks
likely), IC Markets + cTrader is a genuine structural fix to the exact
class of bug that has caused two of today's incidents, not a lateral
move. This is a real broker+execution-layer migration, not a config
change -- new credentials, a new client library, and mt5_execution.py's
retry/ambiguity/idempotency logic (all of the CHFJPY-triple-fill-derived
safety rules) would need to be re-verified against cTrader's own
semantics rather than assumed to carry over. Not started. Needs an
explicit decision, not a unilateral rewrite, once the two incidents above
are actually root-caused -- fixing MT5 stability and then discovering
cTrader was unnecessary is a much cheaper mistake than migrating broker
APIs and discovering the real bug was never MT5 at all.

## 2026-09-11 -- RESOLUTION on the incidents above, and one theory retracted

### Twin-process bug: CONFIRMED and FIXED, financial damage NOT confirmed

Direct process evidence (`ps aux`) showed FOUR live `bot.run_live`
processes where two were expected: a pair started 2026-09-03 (never
killed, ~53 hours CPU time each) alongside the current pair from a
same-day restart. Both zombie processes were polling the same 25
instruments against the same two MT5 accounts through the same bridge
ports as the live pair, for roughly 9 days.

Killed (`kill` then confirmed dead), then hardened against recurrence:
both `slk-bot1`/`slk-bot2` systemd units already carried an `ExecStop=`
pkill hook (added at some earlier point in this project, evidently not
sufficient on its own), but `ExecStop` only fires when systemd believes
the unit is still active at the moment it decides to stop it -- if the
outer `docker exec` client dies on its own (a docker/network hiccup) while
the real python process inside the container survives, systemd sees the
MainPID already gone, may skip `ExecStop` entirely, and `Restart=always`
launches a fresh process on top of the orphan. Added a matching
`ExecStartPre=-docker exec mt5 pkill -f ...` (leading `-` so a normal
"nothing to kill" is not a startup failure) plus a 2s settle sleep to both
units' override.conf, so cleanup is attempted on the way IN as well as
the way out -- either one firing is enough to prevent accumulation.
`systemctl daemon-reload` + restart verified exactly 4 processes (2 per
bot, as expected) with a clean startup log.

Financial impact of the duplication itself: queried both audit DBs,
unrestricted, for any (instrument, entry_time) pair with more than one
`allow`/`allow_pending` row. RESULT: ZERO rows in either database, across
the entire recorded history. So despite running doubled for 9 days, the
audit trail shows no signal was ever actually double-executed. Working
theory: MT5/mt5linux likely only tolerates one effective IPC client per
terminal at a time, so the zombie process was mostly failing its own MT5
calls (consistent with the "Terminal: Authorization failed" / "No IPC
connection" storms) rather than successfully racing the live process to
place a second order. The duplication's proven cost is resource
contention and instability, not doubled trades -- though this is a
negative result (absence of evidence in one query), not a proof that no
other symptom exists; flagged as the current best understanding, not a
closed book.

### The specific $9,999 claim: NOT reproduced by MT5's own deal history

Operator's report: "Our limit order that is a day stale have caused a
problem. This is over $9999 in SL," attached to the XAGUSD signal above.
Pulled the actual deal history for that ticket directly from the broker:

    BUY  vol=1.69 price=65.910 profit=0.0      (opening deal)
    SELL vol=1.69 price=65.934 profit=+202.80  (closing deal)

Single position, matching volume on both legs (no duplication), entry
exactly at the intended 65.91 key level, and a POSITIVE closing profit of
$202.80 -- not a loss, and nowhere near $9,999 in either direction. Hand-
verified the lot size independently against the account's own
`symbol_info` (tick_value=0.5, tick_size=0.001): risk distance 1.183 /
0.001 * 0.5 = $591.50/lot; $1,000 / $591.50 = 1.69 lots, exactly matching
what filled. The sizing math for this trade is correct.

RETRACTED: the "duplicate order caused 10x sizing" theory for this
specific trade, floated in the previous entry before the audit row and
deal history were available. The trade this incident report was attached
to appears, on the broker's own record, to have executed correctly and
profitably. Where the operator's $9,999 figure came from is UNRESOLVED --
possibly a different instrument, a floating (unrealized) figure seen
mid-trade before price recovered, or something read differently in the
MT5 app than intended. Needs a screenshot of the actual figure to trace
further; not assumed to be operator error, just not yet explained.

### Standing, unrevised from the previous entry
  - Incident 3 (EURJPY entry-drift decline) -- correct behavior, not a
    bug; recorded as a live illustration of the drift guard's cost.
  - Incident 4 (MT5 authorization/IPC failures, high load/swap) -- the
    twin-process contention is a plausible PARTIAL contributor (now
    removed), but the box's underlying resource pressure predates this
    specific bug and is not fully explained by it alone. Continue
    monitoring load/swap after this fix; if authorization failures
    persist with only 2 processes running, that points back to the
    Wine/terminal stability question directly, strengthening (not yet
    proving) the case for the cTrader alternative.
  - Architecture question (one script per instrument) -- the twin-process
    finding is a concrete, now-demonstrated data point AGAINST this: two
    REDUNDANT processes per bot alone produced measurable instability.
    Twenty-five separate processes would multiply that pressure, not
    relieve it. Not revisited without new evidence.
  - cTrader/IC Markets -- still a serious option if Incident 4 persists
    post-fix, still not started, still needs an explicit decision once
    the picture is clearer than it is today.

## 2026-09-11, later -- XAGUSD thread closed by the operator

Operator confirmed they manually closed the XAGUSD position at the
+$202.80 profit found in the deal history, and asked to let the original
"$9,999" figure go rather than keep chasing it. Matches the broker record
exactly. No further action on this specific ticket. The twin-process fix
and the "zero duplicate orders across full history" finding both stand
independently of this and remain the operative conclusions.

## 2026-09-11, later -- Implemented "the wick stuff" properly: it's two
## changes, not one, and only one was asked for by name

Operator: "Ok that's nice. Implement it the wick stuff" -- referring to
the earlier flag that `--stop-anchor structural` was never reverted to
`trigger_wick` after the retest-modeled backtest showed trigger_wick
winning (991R vs 792R).

Caught before touching the config: that 991R number was measured WITH
`min_departure_r=1.0` (the retest requirement) ALSO applied in the
backtest. min_departure_r has never been wired into live execution --
the live limit path has always rested the order the instant the setup is
confirmed alive, with no retest requirement at all. Re-checking the
comparison at departure=0.0 (what live actually does today):

  trigger_wick  dep=0.0  738.0R  42.0% win
  structural    dep=0.0  901.3R  49.3% win

Under the fill behavior actually running in production, `structural`
WINS. Switching only the stop anchor, without also making the live
order-placement path wait for a genuine retest, would have moved bot2
from the better-performing config to the worse one by the project's own
numbers -- the two changes are a package, and only implementing the
half that was named out loud would have been a regression dressed up as
the fix that was asked for.

Built both:

1. `setup_validity.check_setup()` gains `min_departure_r` (default 0.0,
   reproducing every prior behavior exactly) and `ValidityVerdict.departed`
   -- has price moved this many multiples of the stop distance away from
   entry, in the trade's favour, at ANY point since the signal. Once
   proven, stays proven even if price pulls back afterward (that pullback
   is the fill, not a reason to reset the requirement).

2. `orchestrator.py`: a new `awaiting_departure` dict and `AwaitingEntry`,
   parallel to `pending_entries`/`PendingEntry` but for signals validated
   as alive that have not yet departed. `_place_limit_entry()` now: if
   not departed, records the signal and returns without touching the
   broker (logging `awaiting_departure` once, not every poll); if
   departed, proceeds to place exactly as before. `_reconcile_awaiting_
   departure()` (wired into run_once() alongside the existing pending-
   order reconcile) re-calls `_place_limit_entry()` on every poll for
   anything still waiting -- same function, same bias/validity checks,
   so there is one implementation of "is this signal still good," not two
   that can drift apart. Two things ONLY apply to the awaiting stage,
   since check_setup() has no way to notice either on its own: an
   explicit 24h expiry (STALE_ENTRY_CUTOFF_LIMIT re-applied, since a
   signal that never departs would otherwise wait forever) and the
   weekend cutoff (nothing left in limbo over a closed weekend, mirroring
   pending_entries even though nothing is resting at the broker yet to
   cancel). The risk-headroom gate was moved to fire only at ACTUAL
   placement (once departed) rather than when the signal first appears --
   headroom that's full today may free up before departure confirms, and
   gating on a stale snapshot would decline signals for the wrong reason.

New CLI flag `--min-departure-r` (default 0.0) on `run_live.py`, threaded
to `LiveBot.min_departure_r`. 15 new tests (setup_validity: departure
tracking including the target-achieved-without-departing edge case;
orchestrator: deferred placement, death by stop-breach/bias-flip/
timeout/weekend, and the 0.0-changes-nothing guarantee). Also fixed
three PRE-EXISTING tests that read the real wall clock via
`_weekend_is_close()` with no `now=` override -- found because running
this suite for the first time on a Friday evening (2026-09-11, past the
21:00 UTC EDT close) made them fail for real, regardless of this feature;
they would have failed the same way on any prior Friday evening or
weekend anyone happened to run them. Pinned with an explicit mock,
unrelated to the departure feature itself.

DEPLOY NEEDED, not yet done: `--stop-anchor structural` must be removed
from bot2's launch script (reverting to the trigger_wick default) AND
`--min-departure-r 1.0` added, together -- doing only the first half
regresses bot2 by the numbers above. `journalctl` cutoff messages will
change wording slightly (staleness/weekend-cancel reasons on
`awaiting_departure` entries use the same phrasing as `pending_entries`'
but say "still waiting for the retest" rather than "resting order").

## 2026-09-11, 23:05 -- Resource snapshot 23 minutes after the twin-process
## fix, and an hourly watch set up rather than judging off one reading

Operator asked directly whether stale/delayed price data (MT5 terminal
instability) is a root cause needing a broker migration (IC Markets +
cTrader, raised by a friend's own bot). Answered precisely: authorization/
IPC failures are a TERMINAL STABILITY problem, not literally "delayed
data" -- but a real, distinct, still-open question from tonight's
duplicate-process fix.

First post-fix reading, ~23 minutes after the clean restart:

    Mem:  total 7.8Gi  used 2.8Gi  available 4.9Gi   (RAM was never the
                                                       real pressure)
    Swap: total 2.0Gi  used 1.2Gi  free 848Mi         (was 2.0/2.0 FULL
                                                       a few hours earlier
                                                       -- 40% drained)
    load average: 2.13, 4.22, 4.75                    (falling fast as the
                                                       higher recent
                                                       history ages out)
    authorization/IPC failures in the last hour: 0

All four numbers move exactly the way they should if the twin-process bug
was a major contributor to the instability. NOT treated as conclusive --
23 minutes is far too short a window; the original 2026-08-26 instability
built up over HOURS as history accumulated, and declaring this solved off
one clean reading would repeat the same overconfidence this session had
to retract three separate times tonight already (stop-anchor verdict
twice, the XAGUSD sizing theory).

Set up passive observability instead of guessing: an hourly cron
appending `free -h`/`uptime`/auth-failure-count to
/srv/slk-bot/health_watch.log. No trading-logic changes.

DECISION RULE recorded for whoever reads this log next:
  - swap keeps draining, failures stay at 0    -> the twin-process bug
    WAS the disease; watch a little longer, then close this out.
  - swap plateaus (~1GB), occasional failures  -> some residual strain;
    resize the VPS (cheap, reversible) BEFORE considering anything else.
  - swap climbs back to full, failures return
    in volume even with just 2 processes       -> the box is genuinely
    undersized for 2 Wine-hosted MT5 terminals; try the resize first
    regardless (cheapest test of that theory), and only escalate to the
    cTrader migration if resizing does not fix it.

Deliberately sequenced VPS-resize before cTrader in every branch: a
broker migration is a multi-week rewrite of every safety rule in
mt5_execution.py (retry/ambiguity handling, tick-grid rounding, the
entry-drift guard, close_position's opposing-deal semantics), all of it
re-scarred against a new API's own quirks -- the same kind of cost this
project has spent weeks paying against MT5 already. A resize is a
five-minute, fully reversible test of the identical "not enough headroom"
hypothesis. Not started; watching first.

## 2026-09-11, 23:40 -- CONFIRMED: run_backtest() costs 54-73s per
## instrument on the live box RIGHT NOW, not the ~12s cited earlier tonight

Operator ran the timing script from the "Why Signals Arrive Late"
walkthrough, inside the mt5 container where the real cache lives:

    EURUSD   72.9s
    GBPJPY   53.8s
    USDJPY   63.7s

The ~12s/instrument figure used in tonight's diagram was the 2026-08-26
post-optimization measurement ("238.0s -> 75.0s across three instruments
x two styles") -- but that was taken on a dedicated GitHub Actions core,
not this VPS, and is over two weeks old. The real, current, on-box cost
is 5-6x higher. This was flagged as "not yet re-measured" rather than
assumed, and the caution was warranted -- the old number badly
understated the problem.

Arithmetic this changes: a SINGLE hunting instrument now costs roughly a
minute, not 12 seconds. Two or three aligning in the same poll (routine
at the top of the hour, when correlated pairs' Daily/H4 bias often flips
together) means two or three minutes where `run_once()` does nothing else
-- not other instruments, not pending-order reconciliation, not the
weekend check. This is very likely the dominant remaining cause of the
lateness the operator has been describing for two weeks, on top of (not
instead of) the two mechanisms already fixed (the polling storm, the
twin-process bug).

Two candidate contributors to the 5-6x gap from the old number, not yet
distinguished:
  (a) the VPS shares 2 vCPUs across two Wine-hosted MT5 terminals and two
      live bot processes, all polling concurrently with this measurement
      -- versus a dedicated, unloaded CI core;
  (b) `run_backtest()`'s cost grows monotonically with the amount of
      cached history it replays (documented in its own module comment
      since 2026-08-26), and roughly 2.5 more weeks of live-synced
      history has accumulated since that number was taken.
A fresh cProfile of one call (same technique as the original 2026-08-26
investigation) was requested to distinguish "same known hot spots,
now bigger" from "something new is now the bottleneck" -- result pending.

One structurally important, favorable finding either way: `run_backtest()`
makes ZERO MT5/bridge calls -- by the time it runs, `sync_recent_from_mt5()`
has already finished the only network step, and everything inside
run_backtest() is pure CPU work over already-synced local cache files.
That means running it CONCURRENTLY across instruments is safe with
respect to the shared, almost certainly non-thread-safe MT5 connection --
the risky part is already over by the time the expensive part starts.
The GIL means real parallelism needs separate processes, not threads, and
with 2 vCPUs the ceiling is 2 concurrent replays at a time -- a real,
meaningful cut to the worst-case pileup, not a full fix, and one more
reason a VPS resize (already being evaluated for the load/swap question)
would compound in value here too.

NEXT: read the profile once it comes back, then decide, with the
operator, whether to (1) reduce the per-call cost further if the profile
shows a fixable hot spot, and/or (2) build a small process-pool so
multiple instruments' searches run concurrently within one run_once()
iteration instead of strictly sequentially. Not started -- this changes
the live loop's core scheduling and deserves a clear decision point
before writing it, not a unilateral change.

## 2026-09-11, 23:55 -- Shipped the safe 29%: candle caching. The other
## 60% (and the actual multi-instrument pileup from tonight's diagram)
## is still open, and honestly scoped as such

From the profile: `load_candles()` (candles.py) cost 34.5s of a
120s-under-cProfile / 73s-real call -- ~29% -- entirely spent re-reading
and re-parsing D/H4/H1/W CSV files that had not changed since the
previous call. `sync_recent_from_mt5()` only appends to these files once
an hour; nothing justified paying `pandas.read_csv` plus a
half-million-row `Candle(...)` listcomp again on every call in between.

Added an in-process cache to `load_candles()`, keyed by the resolved file
PATH (not by source/symbol/granularity -- tests monkeypatch DATA_ROOT per
test, so the same symbol name can resolve to a different file across
tests, and keying by the tuple alone would leak one test's cache into
another's) and invalidated by (size, mtime) -- one cheap `os.stat()` per
call, a full re-read only when the file has actually changed. Returns a
fresh list on every call (a shallow copy when served from the cache) so
no caller can corrupt what the next one sees by mutating what it got
back.

Verified two ways: 6 new tests in `backtest/engine/tests/test_candles.py`
covering the caching behavior itself (skips re-parsing when unchanged,
picks up a real change, never leaks a mutation between calls, missing
files still raise), and the FULL existing suite (431 tests across
backtest/engine, backtest/data_pipeline, bot) passes bit-identical --
proof this changes nothing about which trades get selected, only how
often the same unchanged bytes get re-parsed. The bit-identical-output
standard matches how the 2026-08-26 optimization was verified.

WHAT THIS DOES NOT FIX, stated plainly so it isn't mistaken for solving
tonight's diagram: `run_backtest()`'s own once-per-hour call for a given
instrument still pays full price, because by the time it's called the
underlying file HAS genuinely changed that hour (a new candle was
synced) -- the cache correctly detects that and re-parses; that is not
wasted work. So the exact mechanism the "Why Signals Arrive Late"
diagram named -- several instruments' Daily/H4 bias aligning in the SAME
poll, each needing its own ~40-70s-post-fix (was 54-73s) fresh replay,
stacked sequentially on one thread -- is UNTOUCHED by tonight's fix. That
remains open, and deliberately so: fixing it means either reducing the
OTHER ~60% of the profiled cost (`_unswept_period_extremes`,
`is_swing_high` and its 1.4M calls to `all()`, `detect_confirmations`,
`bias_at` -- real strategy logic whose cost scales with accumulated
history, not incidental waste) or running multiple instruments'
replays concurrently (safe w.r.t. the MT5 connection specifically,
since run_backtest() makes no bridge calls at all -- see the previous
entry -- but real strategy-adjacent code and a scheduling change,
neither of which belongs in a 1am add-on to tonight's session).

The clearest immediate beneficiary of tonight's fix is a path that did
NOT exist before this session: `_candles_since()` (used by
`_reconcile_pending_entries` and the new `_reconcile_awaiting_departure`)
re-reads the SAME H1 file on EVERY 5-SECOND POLL for every resting or
awaiting-departure signal. Before tonight's min_departure_r feature, that
was one extra reload per pending order; now that signals can sit in
`awaiting_departure` for hours, that same file could have been
re-parsed from scratch every 5 seconds for as long as it waited. This
fix removes essentially all of that cost, and it matters more now than
it would have last week specifically because of the feature built
earlier tonight.

NEXT (both un-started, both need a clear-headed session, not this one):
  1. Profile-guided reduction of the algorithmic 60% -- is_swing_high's
     458,082 calls (1.4M calls to builtins.all()) looks like the
     single most promising target, but touching trade-selection logic
     needs the full test suite plus a bit-identical-output check the
     same way this fix and the 2026-08-26 optimization were verified,
     not a guess.
  2. A small process pool so multiple instruments' full replays can run
     concurrently within one run_once() iteration, bounded by vCPU count
     (2 today -> at most 2 at once; more if the VPS is resized, which is
     already being evaluated for the swap/load question).

## 2026-09-12 -- OPERATOR PUSHED BACK ON min_departure_r=1.0: FINER SWEEP
## TOOL BUILT, NOT YET RUN ON REAL DATA.

Operator's objection, in their own words: requiring a full 1R travel
before a limit order even rests refuses real "sniper" entries -- their
experience is that price often retraces to the level on the very next
candle, well under 1R away, and a hard 1.0 requirement throws those out.
This is a specific, checkable claim, not a vibe -- it deserves a real
sweep, not a rerun of last night's yes/no comparison.

The 2026-09-02 entry (above) only sampled four points under the OLD
stop-anchor pairing: 0.0 (738R, 42.0%), 0.5 (948.5R, 47.6%), 1.0 (991.3R,
50.6%), 1.5 (929.3R, 52.7%). That 0.5 point already suggests a middle
ground -- 1082 trades (vs 1137 at 0.0, vs 991 at 1.0) capturing MOST of
0.0's entry volume while recovering most of 1.0's quality gain -- but it
was never re-measured against the CURRENT live pairing (trigger_wick +
avoid_rollover_entries=True + min_reward_r=1.0, i.e. exactly what
orchestrator.py's run_backtest() call actually uses day to day).

Built `backtest/tools/sweep_departure.py`: sweeps min_departure_r at
0.0-1.0 in steps of 0.1 (finer than the four spot-checks), using that
exact live parameter set, entry_fill="limit", cancel_at_target_fraction
matching TARGET_ACHIEVED_FRACTION (0.8). Reuses `run_backtest()` and
`trade_log.summarize()` as-is -- no new backtest logic, just a wider grid
over the existing, already-validated one.

NOT YET RUN against real data: this sandbox's `backtest/data/dukascopy/`
holds only `.lock` sidecar files, no actual cached CSVs (same limitation
hit twice already this week for the timing scripts) -- `run_backtest()`
silently returns zero trades rather than erroring, which is expected here,
not a bug in the new tool. Needs to run on the VPS, where the real cache
lives:

    docker exec -u abc -w /config/trading mt5 python3 -m backtest.tools.sweep_departure \
        --instruments $(grep -oP '(?<=--instruments )\S+' /srv/slk-bot/launch_bot2.sh) \
        --stop-anchor trigger_wick

Until that comes back, no config change follows from this -- the operator
has not yet been shown data at finer resolution than 0.5 vs 1.0, so
"revert to immediate" and "keep 1.0" are both premature calls right now.

## 2026-09-12 -- SHADOW BOOK: PAPER-TRADE THE OPERATOR'S OWN IDEA LIVE,
## NEVER TOUCHING MT5, SIDE BY SIDE WITH THE REAL DEPLOYED BEHAVIOR.

Operator, verbatim, after the backtest-sweep response: "I never hit mt5
for a real trade because im finding it hard to believe your numbers with
my experience with SLK already." Fair -- a backtest's own assumptions
(H1 resolution, no intrabar sequencing, per the 2026-09-02 entry's own
caveat) are exactly the kind of thing a live comparison can catch that a
backtest cannot. Direct request: track the operator's own idea (immediate
placement) forward on real incoming candles, storing it in a DB and
posting to Telegram exactly like a real trade -- entry, fill or no fill,
stop or target -- but never actually placing anything at the broker.

Built `bot/shadow_book.py` (`ShadowBook`), wired into `LiveBot` via a new
`shadow_books` field (empty tuple by default -- opt-in only) and a new
`--shadow-departure-r` flag on `run_live.py`. Design constraints, in order
of how much they mattered:

  1. MUST NOT be able to reach MT5. A ShadowBook holds no reference to
     mt5_exec or mt5_client at all -- not "doesn't call it," CANNOT call
     it, there is no such attribute on the object. Verified by a test
     that asserts neither attribute exists.
  2. MUST NOT add to the CPU cost `run_backtest()` already spends (54-73s/
     instrument, see the last two log entries). Achieved by hooking the
     shadow book onto the `fresh` signal list `_check_instrument()`
     already computes from the ONE real `run_backtest()` call -- no
     second call, ever. Per-poll reconciliation after that is a plain
     Python loop over "candles since the signal," not a strategy replay,
     and skips `load_candles()` entirely for any instrument with nothing
     being tracked.
  3. MUST reuse tested fill/outcome logic rather than re-derive it.
     Reuses `_resting_limit_outcome()` and `_resolve_trade_outcome()`
     from `backtest/engine/runner.py` verbatim -- the exact functions the
     backtest itself already relies on to simulate a resting limit's fill
     point and a filled trade's stop/target race. `check_setup()` was
     considered instead and rejected: its `revisited` flag doesn't
     distinguish "revisited before departure" from "revisited after,"
     which is exactly the ambiguity that would matter most for a
     min_departure_r=0.0 vs 1.0 comparison.
  4. MUST be directly comparable to the real audit data. Writes through
     the SAME `AuditLog`/`DecisionRecord` schema real trades use, to a
     separate db (`<audit-db-stem>_shadow_<value>.db`), and logs via
     `logging.getLogger("bot.shadow_book")` -- a child of the "bot"
     logger telegram_notify.py already listens on, so it reaches the
     same Telegram chat automatically, tagged `[SHADOW:<value>]`. No new
     Telegram wiring needed.

NOT modeled, documented rather than silently wrong: an already-"filled"
shadow trade is not force-closed at the weekend flatten the way a real
position would be -- it keeps walking forward through Monday's candles.
Rare (weekly at most) and visible in the data (an open shadow trade
spanning a weekend gap), not hidden.

11 new tests (`bot/tests/test_shadow_book.py`), all synthetic candles, no
real cache needed. Full suite: 427 passed, 6 skipped (pre-existing).

Deploy (adds ONE flag to bot2's existing launch command -- no new
process, no new systemd unit, since this runs inside the same LiveBot
that already produces the signals):

    --shadow-departure-r 0.0

Runs the operator's own idea (immediate placement) forward for real,
next to whatever --min-departure-r is actually deployed (1.0 as of last
night). Give it real time and real signals, then compare
`aggressive_shadow_0.0.db` against `aggressive_audit.db` -- same schema,
directly comparable win rate / total R / fill timing, no backtest
assumptions in between.

## 2026-09-12 -- min_departure_r SWITCHED TO 0.8 (from 1.0), AND A
## STANDALONE STALE-CACHE WATCHDOG.

The finer sweep (finally) completed -- full 25-instrument grid, `.00` to
`1.00` in 0.1 steps, aggressive/trigger_wick/avoid_rollover/min_reward_r=1.0
(exactly live's real parameters):

  departure  trades   win%   totalR   avgR  medStop
       0.00    9034   41.9%   5814.3  0.644      8.2
       0.10    8910   44.9%   6748.5  0.757      8.2
       0.20    8881   45.3%   6872.7  0.774      8.2
       0.30    8840   46.0%   7071.1  0.800      8.1
       0.40    8785   46.5%   7195.4  0.819      8.0
       0.50    8692   47.3%   7407.8  0.852      8.0
       0.60    8560   47.9%   7504.9  0.877      7.8
       0.70    8398   48.6%   7613.3  0.907      7.6
       0.80    8213   49.1%   7663.8  0.933      7.5
       0.90    8031   49.5%   7646.5  0.952      7.3
       1.00    7837   50.1%   7663.8  0.978      7.1

Two findings, both against the operator's original two claims:

1. Operator was right that 1.0 was stricter than necessary: total R goes
   completely FLAT from 0.80 to 1.00 (7663.8 both times, identical to one
   decimal), while trade count keeps falling the whole way (8213 -> 7837,
   -376 trades) for that flat stretch. 0.80 strictly dominates 1.00 --
   same profit, more entries taken. No reason to keep 1.0.
2. The operator's original ask ("immediate," 0.0) was still the worst
   point on the whole curve, and by a lot -- 0.00 to 0.10 alone is the
   single biggest jump on the table (totalR 5814.3 -> 6748.5, +16.1%,
   for a 1.4% trade-count cost). Immediate placement is confirmed bad at
   full scale (25 instruments, up to 23 years of history per instrument
   -- EURUSD/XAUUSD cache back to 2003, US30 to 2012), not just the
   earlier 3-instrument spot check.

Deployed: `launch_bot2.sh`'s `--min-departure-r` changed 1.0 -> 0.8,
confirmed live via `ps aux` showing the new value in the running process
command line. `min_departure_r=0.0` continues running in parallel as a
`ShadowBook` (paper only, per the entry above) so the operator's original
idea keeps getting validated against live data going forward, not just
this one backtest.

Also built, per direct request ("is there a way we have a clock that
checks if any pair is stale... if any stale is detected it sends it to
Telegram"): `bot/check_staleness.py`, a standalone cron-fired watchdog.
Explicitly told the operator up front this does NOT fix staleness -- it
is a smoke detector for it, so the next stale-candle incident is caught
immediately instead of discovered after a bad trade attempt, the way
every prior one was.

Deliberately a SEPARATE process, not a method on LiveBot: if a hung or
crash-looping bot process is what caused the staleness, a check living
inside that same process could get stuck with it. Reads the cache files
directly (`cache.last_cached_time()`), holds no MT5 connection, and knows
the weekend market-closed window (duplicated from
`orchestrator._market_closed_for_weekend`'s exact rule rather than
imported, so this stays independent of orchestrator.py's MT5-facing
imports) so it doesn't false-alarm every Friday night through Sunday.
12 new tests, full suite 439 passed / 6 skipped.

Also flagged directly to the operator: their own pasted `ps aux` output
this session included the live MT5 password and Telegram bot token in
plaintext. The MT5 one is a demo account; the Telegram bot token is a
live credential and worth rotating via @BotFather regardless.

Deploy: a wrapper script (`/srv/slk-bot/check_staleness.sh`), not a raw
crontab line -- crontab entries can't span multiple lines, and this
command needs both an env var and a nested command substitution for the
instrument list. Cron just calls the script every 15 minutes.

NOT done tonight: nothing about this watchdog reduces the algorithmic 60%
of run_backtest()'s cost, or adds concurrency -- both still open, both
still deferred to a dedicated session (see the last several entries).

## 2026-09-13 -- TESTING (not yet deciding) A BOUNDED TRAILING HISTORY
## WINDOW, PER OPERATOR SUGGESTION.

Operator's own proposal, verbatim: "we don't need data up to 2003 to
know what a pair is currently on... 2 years [of Weekly/Daily] can tell
you what you want unless it doesn't, [then] the system can add an extra
year... For the 4H to the 1H... a year worth... if it doesn't, add extra
6 months." Direct, correct read of the actual bottleneck: EURUSD/XAUUSD's
cache goes back to 2003 (155k/144k H1 candles), and the ~60% algorithmic
share of run_backtest()'s cost that's been deferred all week scales with
exactly that.

This is not a new idea in this project -- an earlier fix's own writeup
already said "no check needs 2003's H1 candles re-walked to know what
the current H1 just did" and sketched "warm up once from full history,
checkpoint to disk, then feed one candle at a time," but never built it.
What shipped instead (the storyline gate) only skips CALLING
run_backtest() when not hunting -- it does nothing to the replay's own
cost once it does run.

There is also an explicit standing warning against the naive version of
this, in run_backtest()'s own docstring: start_date/end_date "is NOT a
data-loading window... narrowing the loaded data itself would silently
break bias-building, alignment, and stacking context." So this is being
TESTED, not assumed safe or unsafe either way, per direct instruction
("test firstly and also compare it if you started from 2003... see what
the 2 results will look like").

Found supporting evidence the idea is at least directionally sound: key
level/liquidity search is ALREADY bounded to "the current structural leg
since the previous breakout" -- an explicit existing comment reads "a
level from years before the market's last major direction change was
never really 'still in play' for this setup." The strategy's own logic
already agrees old history mostly doesn't matter; the open question is
only how far back the BIAS CASCADE genuinely needs to walk to bootstrap
the CORRECT current state, not whether it needs 2003.

Built `backtest/tools/compare_history_window.py`: monkeypatches the
candle loader `run_backtest()` calls so it serves only a trailing window
per granularity (Daily/Weekly get one window, H4/H1 another, matching
the operator's own split), runs full-history and windowed variants of
the SAME instrument, and diffs every trade whose entry falls in a
"recent" period (default last 2 years -- the only period a live decision
actually is) between the two. Identical trades = safe at that window
size. Any mismatch is printed with the full trade detail on both sides,
not just a count, so a real divergence is diagnosable, not just
detected.

10 new tests (`backtest/tools/tests/test_compare_history_window.py`),
including two genuine end-to-end runs against test_runner.py's own
synthetic_cache fixture: a generous window reproduces the fixture's one
trade bit-for-bit (proves the patch mechanism is inert when it should
be), and a deliberately too-short window (1 day) loses the trade
entirely (proves the tool can actually detect a real divergence, not
just always report "identical"). Full suite: 449 passed, 6 skipped.

NOT YET RUN against real data -- needs the VPS. Deploy:

    docker exec -u abc -w /config/trading mt5 nice -n 19 python3 -m backtest.tools.compare_history_window \
        --instruments EURUSD,GBPJPY,US30 \
        --dw-years 2 --h-years 1 --recent-years 2

Starting with 3 instruments (one very long history, one mid, one
index-limited to 2012) rather than all 25 -- this is a correctness
check first, not the full sweep; broaden once the shape of the answer
is known. NOT yet implementing the operator's adaptive "add more time if
it doesn't confirm" escalation -- that requires deciding what "doesn't
confirm" means algorithmically (run_backtest() already signals ONE clear
case, returning [] when no confirmed structure exists to bootstrap a
bias from, but a truncated window could also produce a WRONG bias
non-emptily, which an empty-check alone would not catch) -- exactly the
kind of silent failure mode this comparison is meant to surface before
any escalation logic gets built on top of an unverified assumption.

CAUGHT BY THE OPERATOR before this ever ran against real data: the first
version's cutoff was `newest_cached_candle - window`, anchored to TODAY
regardless of which trade in the comparison period was being checked. A
trade dated 2 years old, with a 2-year window configured, would have
seen history only from (today - 2y) to today -- almost none of which
predates the trade itself -- instead of a real 2-year runway ending AT
ITS OWN entry time. Operator's own words: "for a trade 2 years ago it
will start from 4 years ago from today" -- exactly right, and exactly
what the fix does: extend the cutoff by the comparison period's own
length (recent_days) on top of the window, so the OLDEST trade being
checked still gets its full configured runway. New regression test
(`test_windowed_loader_extends_the_cutoff_by_recent_days`) locks in the
corrected math. Full suite: 450 passed, 6 skipped. This would have
produced a silently wrong (falsely worse) comparison if it had run
before being caught.
