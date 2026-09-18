# Full code review, 2026-09-18

Commissioned after two weeks with no live trade and a run of patches that
each fixed something real and changed nothing about the outcome. The
instruction was to stop patching, read the whole system as if I knew
nothing about it, and say honestly whether it can work.

This document records findings in the order of severity, each with the
evidence that establishes it. A finding with no reproduction is marked as
a suspicion, not a fact.

---

## 1. ROOT CAUSE: the engine reads higher-timeframe bars before they close

**Severity: critical. This is why the bot does not trade.**

Candles are stamped at their OPEN time. `resample.py` resamples with
`label="left", closed="left"`, so the row `2026-09-17T12:00Z` in the H4
series is the candle covering 12:00–16:00. It does not exist, and cannot
be known, until 16:00.

Every downstream consumer compares that stamp directly against the entry
candle's time, as though the bar were available at its own open:

- `_aligned_timeframes()` — `bisect.bisect_right(times, as_of_time)`
- `_last_direction_at()` — `bisect.bisect_left(times, t)`
- `bias_at()` — `[bp for bp in breakpoints if bp[0] <= t]`

So an H1 entry candidate at 13:00 is allowed to be confirmed by an H4
bar that closes at 16:00, a Daily bar that closes at midnight, and a
Weekly bar that closes the following Monday.

Reproduction (`_aligned_timeframes` with one confirmation per timeframe,
all still forming at the as-of instant):

    entry candidate at 2026-09-17 13:00:00+00:00
    aligned timeframes the engine reports: ['Weekly', 'Daily', 'H4']

    H4      bar stamped 12:00 17 Sep  closes 16:00 17 Sep  known yet? NO
    Daily   bar stamped 00:00 17 Sep  closes 00:00 18 Sep  known yet? NO
    Weekly  bar stamped 00:00 14 Sep  closes 00:00 21 Sep  known yet? NO

All three gates pass on information from the future.

### What this does to the backtest

It inflates it. Every reported figure — the 0.64 R/trade swing baseline,
the +2,668R totals, every A/B comparison this project has ever run —
was measured with the engine able to see up to a week ahead at the
moment it decided to enter. None of those numbers are trustworthy, and
the comparisons between them are only as valid as the assumption that
the bias affects each variant equally, which nobody has checked.

### What this does to live trading

It is the direct, sufficient cause of the two-week silence.

`run_backtest()` replays all history every cycle. When the bot runs at
17:00, the H4 series contains the 12:00 bar, so the engine now produces
the signal for the H1 candle at 13:00 — correctly, by its own rules,
four hours after the fact. The orchestrator compares
`new_candle.time - record.entry_time`, sees four hours against a
three-hour cutoff, and declines it as stale. Correctly.

**Nothing is broken in the live path. The live path is refusing signals
that the engine can only ever produce late.** Every stale decline, and
every drift decline (price has moved on by the time the signal appears),
is this same fact seen from a different angle.

### The lag this predicts, against the lag observed

The bound on lateness is the length of the highest-timeframe bar the
signal depended on:

| depends on | max lateness |
|---|---|
| H4 confirmation | 4 hours |
| Daily confirmation or Daily bias | 24 hours |
| Weekly bias | 7 days |

Observed staleness in the audit database, 14–18 Sep:

    4h, 5h, 11h, 12h, 17h, 19h          <- Daily-bounded
    1d3h, 1d8h, 2d3h, 2d20h             <- Daily/Weekly
    4d19h, 5d10h, 7d6h                  <- Weekly-bounded

The distribution matches the prediction, including the maximum: the
worst observed lag is CHFJPY at 7 days 6 hours, against a Weekly bound
of 7 days.

This is not a coincidence and it is not a tuning problem. No cutoff, no
order type, no drift tolerance and no polling frequency can fix it,
because the signal genuinely does not exist at the time it is stamped
for.

### The shape of the fix

The codebase already has the right concept in two places and applies it
to the wrong lag. `SwingPoint.confirmed_at` and `KeyLevel.confirmed_at`
exist to model the n-bar FRACTAL lag (a pivot is not knowable until n
bars later) and there are `known_at()` helpers for both. What is missing
is the BAR-CLOSE lag: a bar stamped at T is not knowable until T + its
own length, on every timeframe.

Every object the entry loop consults needs a `known_at` that includes
the bar-close term, and every lookup needs to filter on it rather than
on the bar's open stamp:

- `Confirmation` — add `known_at = time + bar_length(timeframe)`
- `replay_bias()` breakpoints — same
- `KeyLevel.confirmed_at` — currently `candles[i + n].time`, the OPEN of
  the confirming bar; should be its CLOSE
- `SwingPoint.confirmed_at` — same off-by-one-bar

Then re-run every A/B from scratch, because the existing numbers do not
survive this change.

---

## 2. `StructureTracker` latches permanently after an unconfirmed sweep

**Severity: high. Silently disables half of the confirmation stream for
long stretches.**

In `StructureTracker.run()`, a pending sweep blocks all further sweeps in
that direction:

```python
if pending_sweep_high is None and last_swing_high is not None and c.high > last_swing_high.price:
    pending_sweep_high = SwingPoint(...)
    structural_low_at_sweep = last_swing_low     # frozen here, never refreshed
```

`pending_sweep_high` is cleared only when the break confirms, and the
break can only confirm by closing beyond `structural_low_at_sweep` —
which is captured once, at the moment of the first sweep, and never
updated as price moves.

In a sustained uptrend this means: the first higher high registers a
bearish sweep against the low that existed at that moment; price then
rises for weeks; confirming a bearish break would require closing below
a low from the start of the trend. It never happens, so the bearish path
stays latched for the rest of the series, and no further bearish sweep
is ever recorded.

Reproduction — 90 candles containing repeated rallies and selloffs
produced exactly one event and never set `strong_low` or `strong_high`:

    events: {('sweep', 'bearish'): 1}
    strong_low: None
    strong_high: None

    i=54 BEAR SWEEP  structural_low_at_sweep=117.69999999999995
    end state: pending_bull=False  pending_bear=True    (36 candles later)

There is a second, rarer variant of the same latch: if the opposing swing
point is `None` when the sweep registers, `structural_low_at_sweep`
stays `None` forever and the confirm branch can never fire, because
nothing re-populates it.

The likely intent is that a bearish break of structure is measured
against the MOST RECENT structural low, not the one from weeks ago. As
written, the level to break gets further away the longer the trend runs.

Effect: `detect_confirmations()` merges sweep+break events with plain
breakouts, so the plain-breakout half keeps working and the failure is
invisible in aggregate. It quietly removes one of the two confirmation
shapes for long periods.

---

## 3. `replay_bias()` decides a past flip using a future confirmation

**Severity: high, and a second independent source of retroactive change.**

```python
start = bisect.bisect_right(confirmation_times, c.time)
window = confirmations_sorted[start:start + confirmation_window]
if cascade.check_flip(eligible, c, window):
```

Condition (c) of the flip test — "the lower timeframe has stopped
confirming the old direction" — is evaluated against confirmations
STRICTLY AFTER the rejection candle. With `confirmation_window=1`, a
flip at time T depends on the single next lower-timeframe confirmation,
whenever that happens to arrive.

This makes the bias at T unstable in a specific and damaging way. At the
moment T occurs there are no later confirmations, so the window is empty,
`any([])` is False, and the flip is ALLOWED. Later, once a confirmation
in the old direction arrives, the same flip is VETOED.

So a bias flip can appear in real time and then vanish on replay. Signals
that depended on it appear and then disappear between one hourly cycle
and the next. This is independent of finding 1 and would survive fixing
it.

---

## 4. `classify_entry_pattern()` needs up to 3 candles after the entry

**Severity: medium. Guarantees every signal is at least one hour late,
and makes the classification itself time-dependent.**

`FOLLOWING_LOOKAHEAD = 3`, and:

```python
following = h1[i + 1: i + 1 + FOLLOWING_LOOKAHEAD]
classification = classify_entry_pattern(new_key_level, following)
if classification is None:
    continue
```

`classify_entry_pattern()` returns `None` for an empty `following`, so
the newest H1 candle can never produce a signal — a minimum one-hour lag
by construction, before finding 1 is even considered.

Worse, the answer changes with how many candles have arrived. With one
following candle the function falls through to `FRESH_IRL_REQUIRED`;
with three it may instead return `NESTED_DISRESPECT`, which carries a
DIFFERENT reference level, and therefore a different entry price, stop
and target. The same entry candle yields a different trade depending on
when it is evaluated.

---

## 5. Both bots share one cache, written from two different brokers

**Severity: unknown, currently unproven. Recorded as a suspicion.**

Neither launch command passes `--source`, so both processes read and
write `dukascopy` cache files. Each syncs H1 from its OWN MT5 terminal —
two accounts on two brokers — into the same CSVs, then re-derives
H4/D/W from the result.

Sampling XAUUSD's H1 and H4 files three times over three minutes showed
no churn: identical size, mtime and rows. So they are not visibly
fighting, and the hypothesis is NOT established. It remains a design
hazard worth removing rather than a diagnosed fault.

The observation that prompted it is still unexplained: two processes 41
seconds apart reported different H4 bias for XAUUSD, the later one
anchored at an EARLIER time (`H4@2026-09-18 04:00` then
`H4@2026-09-15 04:00`). Findings 1 and 3 can both produce exactly this,
so it may already be accounted for.

---

## 6. Infrastructure: the VPS was out of memory (fixed 2026-09-18)

Not a code fault, but it was actively degrading the system and it masked
everything above.

`ollama` held 2.9 GB on a 7.8 GB box shared with two trading bots and two
MT5 terminals. Swap was 100% consumed (36 KiB free of 2 GB). Both bots
had roughly 450 MB each paged out to disk, and the hourly cycle could not
finish its 25 instruments inside the hour — the Telegram staleness alert
named exactly instruments 17 through 25 of the list, the contiguous tail,
which is the signature of a loop running out of time rather than a data
problem.

Stopping ollama freed 2.9 GB; the tail-staleness alert stopped. This was
real and worth fixing. It is NOT the reason there were no trades:
findings 1 and 4 produce late signals on an idle machine.

---

## Bottom line so far

The strategy code is careful, well-documented, and extensively tested.
The tests are honest about their own limits and several of them encode
real lessons. That is not the problem.

The problem is that the whole engine was designed as a backtest — a
function over a complete history — and is being used as a live signal
generator, which is a function over history AS IT WAS AT A GIVEN MOMENT.
Those are different functions. The code has the concept needed to
reconcile them (`known_at`) and applies it only to the fractal lag,
missing the much larger bar-close lag.

Until that is fixed, the live bot cannot trade, and the backtest cannot
tell you whether the strategy is any good.

---

*Review in progress: engine reviewed; bot/ (orchestrator, execution,
risk, sizing, reconciliation) not yet covered.*
