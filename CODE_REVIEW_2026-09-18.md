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

## 4. HIGH — `StructureTracker` latches permanently after a sweep that never confirms

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

## 5. HIGH — `replay_bias()` decides a past flip from a future confirmation

```python
start = bisect.bisect_right(confirmation_times, c.time)
window = confirmations_sorted[start:start + confirmation_window]
```

Condition (c) of the flip test — "the lower timeframe has stopped
confirming the old direction" — is evaluated against confirmations
STRICTLY AFTER the rejection candle.

This makes the bias at T unstable in a damaging direction. At the moment
T occurs there are no later confirmations, the window is empty, `any([])`
is False, and the flip is ALLOWED. Later, once a confirmation in the old
direction arrives, the same flip is VETOED. A bias flip can therefore
appear in real time and vanish on replay, and signals that depended on it
appear and then disappear between one hourly cycle and the next.

Independent of finding 1; would survive fixing it.

---

## 6. MEDIUM — `classify_entry_pattern()` needs up to 3 candles after the entry

`FOLLOWING_LOOKAHEAD = 3`, and the function returns `None` for an empty
`following`, so the newest H1 candle can never produce a signal — a
one-hour minimum lag by construction, before finding 1 is considered.

Worse, its answer changes as candles arrive: with one following candle it
falls through to `FRESH_IRL_REQUIRED`; with three it may return
`NESTED_DISRESPECT`, which carries a different reference level and
therefore a different entry, stop and target. The same candle yields a
different trade depending on when it is evaluated.

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

## What I would do, in order

1. **Add the bar-close term to `known_at` everywhere and re-run every
   A/B.** Nothing else can be evaluated until the backtest stops seeing
   the future. Expect the numbers to get worse — that is the point.
2. **Make the storyline gate take the same flags as the engine**, and
   make the safety test run the deployed configuration. Until then the
   gate is an unmeasured strategy change.
3. **Advance the watermark even when the gate is closed**, or expire the
   backlog deliberately, so a reopening gate does not dump days of dead
   signals into the decline log.
4. **Fix the `StructureTracker` latch** — refresh the opposing structural
   point, or expire an unconfirmed sweep.
5. **Make `replay_bias` condition (c) causal** — look backwards from the
   rejection, not forwards.
6. **Widen the anomaly tolerance** to a fraction of the book, and
   separately investigate the 2026-09-07 `-2,543 vs 1,388` event, which
   has never been explained.

Items 1 and 2 are the ones that decide whether this bot trades. The rest
are real but secondary.

## What this review did not cover

`mt5_execution.py` beyond `compute_lot_size`, the reconciliation paths
(`reconcile_signals.py`, `_reconcile_closed_positions`,
`_reconcile_pending_entries`), `shadow_book.py`, `audit_log.py`, the
webapp, and the data pipeline beyond `resample.py` and `cache.py`. None
of those can explain an absence of trades, which is why they were
deprioritised — not because they are known to be clean.
