# Full code review, 2026-09-18

Commissioned after two weeks with no live trade and a run of patches that
each fixed something real and changed nothing about the outcome. The
instruction was to stop patching, read the whole system as if I knew
nothing about it, and say honestly whether it can work.

Findings are ordered by severity. Each one states the evidence. Anything
I could not reproduce is labelled a suspicion, not a fact.

**Verdict up front.** The strategy code is careful, well documented and
genuinely well tested. The problem is not sloppiness. The problem is that
an engine designed as a *backtest* — a function over a complete history —
is being used as a *live signal generator*, which is a function over
history as it stood at one moment. Those are different functions, and
five separate findings below are all consequences of that one confusion.
Until it is fixed the bot cannot trade, and the backtest cannot tell you
whether the strategy is any good.

---

## 1. CRITICAL — the engine reads higher-timeframe bars before they close

*Status: CONFIRMED end-to-end, twice — by isolated reproduction, and by
running the real engine over a synthetic dataset built through the real
resample pipeline. See "Verification" at the end.*

Candles are stamped at their OPEN. `resample.py` resamples with
`label="left", closed="left"`, so the H4 row `2026-09-17T12:00Z` is the
candle covering 12:00–16:00. It does not exist, and cannot be known,
until 16:00.

Every consumer compares that stamp directly against the entry candle's
time, as if the bar were available at its own open:

- `_aligned_timeframes()` — `bisect.bisect_right(times, as_of_time)`
- `_last_direction_at()` — `bisect.bisect_left(times, t)`
- `bias_at()` — `[bp for bp in breakpoints if bp[0] <= t]`

Reproduced, one confirmation per timeframe, all still forming:

    entry candidate at 2026-09-17 13:00:00+00:00
    aligned timeframes the engine reports: ['Weekly', 'Daily', 'H4']

    H4      stamped 12:00 17 Sep   closes 16:00 17 Sep   known yet? NO
    Daily   stamped 00:00 17 Sep   closes 00:00 18 Sep   known yet? NO
    Weekly  stamped 00:00 14 Sep   closes 00:00 21 Sep   known yet? NO

All three gates passed on information from the future.

**Effect on the backtest:** it is inflated. Every number this project has
produced — the 0.64 R/trade swing baseline, the +2,668R totals, every A/B
— was measured with the engine able to see up to a week ahead at the
moment it decided to enter.

**Effect on live:** this is the direct, sufficient cause of the silence.
`run_backtest()` replays all history each cycle, so when the bot runs at
17:00 the 12:00 H4 bar now exists and the engine emits the signal for the
13:00 H1 candle — four hours late, by its own rules. The orchestrator
measures that against a three-hour cutoff and declines it as stale.
Correctly. **Nothing in the live path is broken; it is refusing signals
the engine can only ever produce late.**

Lateness is bounded by the longest timeframe the signal depended on — 4h
for H4, 24h for Daily, 7d for Weekly. Observed staleness, 14–18 Sep:

    4h, 5h, 11h, 12h, 17h, 19h          <- Daily-bounded
    1d3h, 1d8h, 2d3h, 2d20h             <- Daily/Weekly
    4d19h, 5d10h, 7d6h                  <- Weekly-bounded

The worst case, CHFJPY at 7d 6h, sits on the Weekly bound.

**Fix.** The codebase already has the right concept — `confirmed_at` plus
`known_at()` on `SwingPoint` and `KeyLevel` — and applies it only to the
n-bar FRACTAL lag. It is missing the BAR-CLOSE lag: a bar stamped T is
not knowable until T + its own length. Every `Confirmation`, every
`replay_bias()` breakpoint and both `confirmed_at` values need that term,
and every lookup must filter on it. Then every A/B has to be re-run,
because none of the existing numbers survive the change.

---

## 2. CRITICAL — the storyline gate runs a different strategy than the engine it gates

*Status: FIXED 2026-09-18. `build_htf_context()` now takes `origin_kind`,
`close_based_sweep_break` and `max_history_years`, uses runner's own
`_bootstrap_origin()` instead of a second copy of the rule, and the
orchestrator passes its real values. The real-data safety test now runs
the DEPLOYED flags on both sides (finding 8), and a new orchestrator test
asserts the wiring directly -- it runs everywhere, unlike the real-data
test, which skips without a cache.*

`live_strategy.py` states the property it must have: *"It must have no
false negatives: if `run_backtest()` would have produced a trade at some
candle, the gate must have said hunting at that candle's time."*

It does not hold, because the gate and the engine are configured
differently. `build_htf_context()`:

```python
daily_events = StructureTracker(n).run(daily)                      # close_based_break=False
first_origin = next((e for e in daily_events if e.kind == "valid_sweep_break"), None)
daily_confirmations = detect_confirmations(daily, n, close_based_breakout=close_based_breakout)
```

and the orchestrator calls it as `build_htf_context(instrument, source=self.source)` —
nothing else passed. Meanwhile both bots launch with `--origin-kind any
--close-based-sweep-break --history-windows-config bot/history_windows.json`,
and `run_backtest()` receives all three.

So the gate differs from the engine in three ways at once:

| | gate | engine (as deployed) |
|---|---|---|
| origin | hardcoded `valid_sweep_break` | `origin_kind="any"` |
| sweep break level | wick (`False`) | close (`True`) |
| history | full, uncapped | capped per `history_windows.json` |

Different bias input produces different breakpoints, which produces a
different answer to "are we hunting". The gate can — and by construction
will — say WAITING at candles where `run_backtest()` produces a trade.

**The worst case is total.** If an instrument's Daily history contains no
`valid_sweep_break` at all, `build_htf_context()` returns `None`, the
orchestrator logs a debug line and returns `False`, and that instrument
is gated off permanently — while the engine, bootstrapping from the first
confirmation under `origin_kind="any"`, would have traded it. Finding 4
makes `valid_sweep_break` events rarer than they look, so this is not
hypothetical.

---

## 3. HIGH — the watermark does not advance while the gate is closed, so backlogs flood out dead

*Status: FIXED 2026-09-18. The WAITING path now advances the watermark,
which is sound because a False return means the gate said WAITING at
EVERY candle since it -- so by the gate's own contract (now checked
against the deployed flags, finding 2) there was nothing to find there.
A second route was found while fixing it: `_last_entry_time` is
in-memory only and is rebuilt after a restart from the last entry
ATTEMPT, which the WAITING path does not write -- so a bot polling
happily for a week returns from a restart with a week-old watermark. That
is now bounded by STALE_ENTRY_CUTOFF_LIMIT.*

*Deliberately NOT done: batching the skipped signals into one summary
event. It was written, and a test caught that it replaced per-signal
declines -- which carry the full strategy read (bias per timeframe,
levels, entry/stop/target) that the operator explicitly asked to always
see on Telegram. Signals inside the window are still reported one at a
time.*

In `_check_instrument()` the storyline gate returns early:

```python
if not self._storyline_hunted_anywhere_in_gap(instrument, watermark, new_candle.time):
    return
...
self._last_entry_time[instrument] = new_candle.time     # never reached
```

So during a WAITING stretch the watermark stays where it was. When the
gate finally opens:

```python
fresh = [r for r in records if watermark < r.entry_time <= new_candle.time]
```

every signal accumulated over that whole stretch is emitted at once — and
every one of them is older than the cutoff, so every one is declined as
stale.

This is exactly the observed pattern. The declines arrive in bursts
(21:47–22:09 on the 16th, 08:54–08:57 on the 17th, 11:35–11:36 on the
18th) with 10–27 quiet hours between, and CHFJPY's 09-09 and 09-12
signals were both discovered in the same burst on 09-16. That is a
backlog draining, not a poll being missed.

Combined with finding 2, an instrument can sit behind a gate that is
wrongly closed, accumulate signals, and then discard them all on reopen.

---

## 4. CRITICAL — `StructureTracker` latches permanently after a sweep that never confirms

*Status: CONFIRMED, and far more severe than first written. Upgraded from
HIGH after measuring it on a realistic 3-year H4 series: the engine
produced ZERO bearish sweep+break confirmations in three years.*

    bullish:  40 sweeps, 39 valid_sweep_breaks     <- working normally
    bearish:   1 sweep,   0 valid_sweep_breaks     <- latched on day 2

    the one bearish sweep (2023-01-04) stayed pending 6,554 H4 bars
    = 1,092 days, and blocked 2,106 subsequent bearish sweeps

One latch, on the second day of the series, disabled bearish structure
detection for its entire length.

```python
if pending_sweep_high is None and last_swing_high is not None and c.high > last_swing_high.price:
    pending_sweep_high = SwingPoint(...)
    structural_low_at_sweep = last_swing_low     # captured once, never refreshed
```

`pending_sweep_high` clears only when the break confirms, and confirming
requires closing beyond `structural_low_at_sweep` — frozen at the instant
of the first sweep. In a sustained uptrend the first higher high
registers a bearish sweep against the low of that moment; price then
rises for weeks; confirming would require collapsing to a low from the
start of the trend. It never happens, so the bearish path stays latched
and no further bearish sweep is ever recorded.

Reproduced — 90 candles of repeated rallies and selloffs:

    events: {('sweep', 'bearish'): 1}
    strong_low: None
    strong_high: None
    i=54 BEAR SWEEP  structural_low_at_sweep=117.7   (still pending 36 candles later)

A rarer variant: if the opposing swing is `None` when the sweep
registers, `structural_low_at_sweep` stays `None` forever and the confirm
branch can never fire, because nothing repopulates it.

The likely intent is that a break of structure is measured against the
MOST RECENT opposing structural point. As written the target gets further
away the longer the trend runs.

Because `detect_confirmations()` merges sweep+break with plain breakouts,
the plain half keeps working and this failure is invisible in aggregate —
it quietly removes one of the two confirmation shapes for long stretches.

---

## 5. MEDIUM — `replay_bias()` decides a past flip from a future confirmation

```python
start = bisect.bisect_right(confirmation_times, c.time)
window = confirmations_sorted[start:start + confirmation_window]
```

Condition (c) of the flip test — "the lower timeframe has stopped
confirming the old direction" — is evaluated against confirmations
STRICTLY AFTER the rejection candle.

The look-ahead itself is not in doubt: the flip decision at time T is
made from data after T, which inflates the backtest the same way finding
1 does.

**But the instability I predicted from it did not materialise, and I am
recording that rather than quietly dropping it.** I claimed a flip could
appear in real time and then vanish on replay. Recomputing the Daily
breakpoints at twelve monthly cut-offs over a year: **71 breakpoints
appeared, 0 ever vanished.**

The reason is that `replay_bias()` walks the whole series, so the
"no future confirmation yet" case only applies to the last candle or two
of whatever data exists. That is exactly where the live bot operates, so
the effect is real there — but it is confined to the tail, not spread
through history as I implied.

Downgraded from HIGH to MEDIUM: a genuine look-ahead, not a demonstrated
source of instability.

---

## 6. MEDIUM — `classify_entry_pattern()` needs up to 3 candles after the entry

`FOLLOWING_LOOKAHEAD = 3`, and the function returns `None` for an empty
`following`, so the newest H1 candle can never produce a signal — a
one-hour minimum lag by construction, before finding 1 is considered.

Its answer also changes as candles arrive, though less often than I first
wrote. Classifying 4,000 real key levels with one following candle and
again with three:

    identical: 3,851
    DIFFERENT:   149  (3.7%)

Every difference was `fresh_irl_required` -> `nested_disrespect`, which
carries a DIFFERENT reference level and therefore a different entry, stop
and target. So the same candle does yield a different trade depending on
when it is evaluated — but in roughly 1 case in 27, not as a rule. The
unconditional one-hour minimum lag is the larger half of this finding.

---

## 7. MEDIUM — the anomaly halt trips on ordinary swap and commission

`RiskManager._check_anomaly()` halts when floating P&L is worse than
minus the sum of open positions' stop distances, with a **$1** tolerance:

```python
if floating_today < -open_risk - 1.0:
```

`floating_today` is `equity - balance`, which includes swap and
commission. `open_risk` is pure `|entry - stop| x value`. A book sitting
near its stops overnight will show floating slightly worse than
`open_risk` from financing alone, with no stop having slipped anywhere.

The 2026-09-07 incident is consistent with exactly that: the first halt
fired at floating `-2,005` against `open_risk` `1,998` — a $7 excess on a
$2,000 book, 0.35%. Fourteen halts were logged that morning; it is the
last date real trades appear in the account history.

The later events in that sequence (`-2,543` against `1,388`) are a much
larger excess and may be a genuine stop failure. That deserves its own
investigation and has never had one.

The tolerance should scale with the book — a fraction of `open_risk`, or
an explicit financing allowance — not a flat dollar.

---

## 8. MEDIUM (process) — the safety test validates a configuration nobody runs

`test_gate_never_suppresses_a_trade_the_real_backtest_produces` is the
test that finding 2 should have been caught by. It calls:

```python
ctx = build_htf_context(instrument)          # defaults
run_backtest(instrument, style)              # defaults
```

Both with default flags — so it proves the gate agrees with an engine
configured `origin_kind="sweep_break"`, `close_based_sweep_break=False`,
no rollover filter, no `min_reward_r`, no history caps. Production runs
none of those. The test passes; the deployed pairing is untested.

This is systemic, not a one-off. I made the identical mistake earlier the
same day in `count_signals`, pinning its defaults to `LiveBot`'s
dataclass fields and writing a test asserting they matched — while the
real overrides live at the launch site. `live_flags.py` now exists for
this; the same treatment should be applied to this test, and to
`check_recent_signals.py`, which has a documented history of the same
bug.

---

## 9. SUSPICION (not established) — both bots share one cache, written from two brokers

Neither launch command passes `--source`, so both processes read and
write the same `dukascopy` files. Each syncs H1 from its OWN MT5 terminal
— two accounts on two brokers — into the same CSVs, then re-derives
H4/D/W from the result.

I sampled XAUUSD's H1 and H4 three times over three minutes and saw no
churn: identical size, mtime and rows. **The hypothesis is not
established.** It is a design hazard worth removing, not a diagnosed
fault.

The observation that prompted it — two processes 41 seconds apart
reporting different H4 bias for XAUUSD, the later one anchored EARLIER
(`H4@2026-09-18 04:00` then `H4@2026-09-15 04:00`) — is fully explained
by findings 1 and 5 without needing any cache conflict.

---

## 11. The orchestrator test suite failed every Friday evening (fixed)

Found while fixing finding 1: a change appeared to break 31 orchestrator
tests, and they turned out to be already failing on a clean tree.
`_weekend_is_close()` and `_too_late_to_open()` default `now` to
`datetime.now(timezone.utc)`, so from roughly 20:00 UTC Friday through
the weekend, 31 tests failed for reasons unrelated to the code.

Confirmed both ways after the fix: with the frozen clock at Friday 20:00
the same 31 fail; at Wednesday noon all 83 pass.

This was already known and partially worked around -- one test's
docstring records hitting it on 2026-09-11, and three tests were given a
local `patch.object(LiveBot, "_weekend_is_close", ...)`. The other 31
were left, so it returned the following Friday. Now fixed once, with an
autouse fixture freezing the clock for the whole file.

It matters beyond tidiness: CI is red every Friday for no reason, which
trains everyone to ignore it, and a genuine regression introduced on a
Friday is indistinguishable from the calendar.

## 12. `_too_late_to_open()` is False while the market is shut

Noticed while probing finding 11, not investigated further and NOT fixed.

At Friday 21:30 UTC -- after the 17:00 New York close -- `_weekend_is_close()`
is True but `_too_late_to_open()` is False, because
`_minutes_to_weekend_close()` rolls forward to NEXT Friday the moment
this one passes, so it reports ~six days of headroom. `_market_closed_for_weekend()`
exists precisely because of that roll-forward and is consulted by
`_weekend_is_close()`, but `_too_late_to_open()` does not consult it.

Probably harmless in practice (the market is shut, so nothing fills),
but the two guards disagree about the same moment, and only one of them
gates new entries.

## 10. FIXED 2026-09-18 — the VPS was out of memory

Not a code fault, but it was degrading everything and masking the rest.
`ollama` held 2.9 GB on a 7.8 GB box shared with two bots and two MT5
terminals; swap was 100% consumed (36 KiB free of 2 GB); both bots had
~450 MB each paged to disk. The hourly cycle could not finish 25
instruments inside the hour, and the staleness alert named exactly
instruments 17–25 — the contiguous tail of the list, the signature of a
loop running out of time.

Stopping ollama freed 2.9 GB and the tail-staleness alert stopped. Real,
worth fixing, and **not** the reason there were no trades: findings 1, 3
and 6 produce late signals on a completely idle machine.

---

## Re-verification after the fixes (2026-09-18, before running any A/B)

Everything was re-checked as a genuine before/after, running the same
scripts against the fixed tree and against a git worktree at a227684 --
the commit immediately before the first fix -- over identical synthetic
data.

**Stability: both trees pass.** Asking the engine for its view of the
past at five cut-offs spread over three months gives an identical answer
in both. The pre-fix engine was self-consistent; it simply used data that
postdated the ENTRY, which this test cannot see, because a trade twenty
days behind the cut-off has that data in every view. Recording it because
it is the test I reached for first and it does NOT demonstrate what I
wanted it to.

**The measure that does: could a live bot have acted on it?** For each
sampled trade, truncate the cache to what existed three hours after its
entry candle -- the market bot's own stale cutoff -- and ask whether the
engine produces that trade yet.

| | pre-fix | fixed |
|---|---|---|
| backtest trades (3y synthetic) | 178 | 91 |
| actionable inside the 3h cutoff | 2/12 (17%) | 10/12 (83%) |

83% of what the old backtest promised could never have been taken at the
time. That is the two weeks of silence, measured.

The remaining 2 of 12 are signals whose birth genuinely exceeds three
hours; they are why staleness is now measured from `signal_known_at`
rather than the entry candle, and why the selection window carries a
grace margin.

## Verification

Every finding above was re-tested before any fix was started, with the
goal of FALSIFYING it rather than confirming it. Two claims did not
survive in the form I first wrote them; both were corrected in place
rather than quietly dropped.

**Method.** Three years of synthetic H1 (26,280 bars, seeded random walk
with trend regimes) run through the REAL resample pipeline into a
temporary cache, then through the REAL `run_backtest()` with the deployed
live flags. Nothing mocked except the data directory. It produced 178
trades, enough to measure against.

**Finding 1 — confirmed, quantified.** Latency measured by truncating the
cache to what genuinely existed at T+k (a bar kept only once it had
closed) and asking when each signal first appears:

    entry candle                first visible
    2023-01-24 16:00            >336h          <- ARTIFACT, see below
    2023-05-29 11:00            +6h
    2023-12-06 09:00            +3h
    2024-06-01 05:00            +3h
    2024-10-03 05:00            +96h
    2024-12-25 06:00            +96h
    2025-04-19 23:00            +6h
    2025-07-15 20:00            +2h

The `>336h` row is an artifact and not evidence: that trade is 22 days
into the series, so truncation leaves too little history to bootstrap a
bias at all. Excluding it, latency runs 2h–96h and **4 of 7 signals are
already past the 3-hour stale cutoff at the moment they first become
computable.** The two 96h cases sit in the Weekly range.

**Finding 2 — confirmed by inspection.** `build_htf_context` has exactly
two call sites (`orchestrator.py:691`, `test_live_strategy.py:147`) and
neither passes `origin_kind`, `close_based_sweep_break` or history caps.

**Finding 3 — confirmed by inspection.** `_last_entry_time` has exactly
one write, at `orchestrator.py:666`, after the gate's early return at 576.

**Finding 4 — confirmed and UPGRADED.** Measured on the synthetic H4
series: zero bearish sweep+break events in three years, 2,106 blocked
sweeps, one pending sweep alive for 1,092 days. Caveat: severity depends
on whether price ever closes back through the structural point captured
at the first sweep, so the direction that dies will differ per instrument
and per period. The mechanism is proven; the 100% figure is specific to
this series.

**Finding 5 — DOWNGRADED.** The predicted instability did not appear: 71
breakpoints appeared across twelve monthly cut-offs and none vanished.

**Finding 6 — confirmed, quantified.** 149 of 4,000 (3.7%) classify
differently with one vs three following candles.

**Finding 7 — by inspection only.** The `$1` tolerance and the
`equity - balance` definition are plain in the code, and the observed $7
excess on a $2,000 book is consistent with financing. Confirming that
MT5's equity includes swap for these positions needs the live account.

---

## What I would do, in order

1. **Add the bar-close term to `known_at` everywhere and re-run every
   A/B.** Nothing else can be evaluated until the backtest stops seeing
   the future. Expect the numbers to get worse — that is the point.
2. **Fix the `StructureTracker` latch** — refresh the opposing structural
   point, or expire an unconfirmed sweep. Moved up from 4th after
   measurement: one direction of structure detection is currently dead.
3. **Make the storyline gate take the same flags as the engine**, and
   make the safety test run the deployed configuration. Until then the
   gate is an unmeasured strategy change.
4. **Advance the watermark even when the gate is closed**, or expire the
   backlog deliberately, so a reopening gate does not dump days of dead
   signals into the decline log.
5. **Widen the anomaly tolerance** to a fraction of the book, and
   separately investigate the 2026-09-07 `-2,543 vs 1,388` event, which
   has never been explained.
6. **Make `replay_bias` condition (c) causal** — look backwards from the
   rejection, not forwards. Last because it is a real look-ahead with no
   demonstrated behavioural consequence.

Items 1, 2 and 3 decide whether this bot trades. The rest are real but
secondary.

## What this review did not cover

`mt5_execution.py` beyond `compute_lot_size`, the reconciliation paths
(`reconcile_signals.py`, `_reconcile_closed_positions`,
`_reconcile_pending_entries`), `shadow_book.py`, `audit_log.py`, the
webapp, and the data pipeline beyond `resample.py` and `cache.py`. None
of those can explain an absence of trades, which is why they were
deprioritised — not because they are known to be clean.
