# Backtest

Two parts: a data pipeline (fetches and caches historical OHLCV candles)
and an engine (implements STRATEGY.md's ruleset against that data). See
`../knowledge-base/STRATEGY.md` for the ruleset itself.

Live execution is out of scope here -- it'll eventually run separately
against MT5 (the actual trading platform), once the ruleset extracted
here has been validated on historical data.

## Data source: Dukascopy, and why it changed from Oanda

Oanda was the original plan (it's the broker referenced throughout the
source material), but it rejects new clients -- including demo accounts
-- from Nigeria. Separately, and more fundamentally: **this pipeline
cannot run inside a Claude Code cloud session at all**, regardless of
vendor. Tested directly -- Oanda, Dukascopy, Twelve Data, and Binance
were all identically rejected by this session's own network egress
policy (403 policy denial at the proxy level, confirmed via
`$HTTPS_PROXY/__agentproxy/status`). That's an infrastructure restriction
on this specific execution environment, unrelated to which data vendor
gets picked. **Run this pipeline somewhere with normal outbound internet
access** -- your own machine works, but see "Running via GitHub Actions"
below for the recommended way to do this without depending on any local
machine (or its power supply) staying on.

Given that constraint, Dukascopy is the right choice anyway: **no
account, no KYC, no API key at all** -- so there's no signup step to hit
a geo-block on, from Nigeria or anywhere else. It also covers forex,
metals, oil, indices, AND crypto (ETH/USD) from one source, via the
`dukascopy-python` package, which handles the tick-data download and
decoding internally.

The Oanda code (`oanda_client.py`, `fetch_oanda.py`) is left in place,
unused, in case a future entity (a prop firm's own jurisdiction, for
instance) makes it usable later. The ccxt/Binance crypto fetcher
(`fetch_crypto.py`) is similarly kept as a fallback if Dukascopy's crypto
history turns out too short for a given backtest window.

## Running via GitHub Actions (recommended -- no local machine needed)

`.github/workflows/fetch-data.yml` runs the entire data pipeline on
GitHub's own servers -- unaffected by local power/internet reliability.
On a daily schedule (and any time via the "Run workflow" button on the
repo's Actions tab), it:

1. Downloads the previous data cache from the `data-latest` GitHub
   Release (if one exists) so the fetch is genuinely incremental instead
   of re-pulling full history every run -- Actions runners have no
   persistent disk between runs otherwise.
2. Runs `fetch_dukascopy.py --all` and `derive_granularities.py --all`.
3. Re-packages `backtest/data/` and publishes it back to the
   `data-latest` release, replacing the previous asset.

To get the data locally (e.g. to inspect it, or to feed a backtest
running somewhere else): download `backtest-data.tar.gz` from the
repo's `data-latest` release and extract it into `backtest/`.

GitHub can silently pause scheduled workflows on low-activity repos --
if a daily run seems to have been skipped, trigger it manually from the
Actions tab; that always works regardless of the cron schedule's state.

`.github/workflows/run-backtest.yml` runs the Phase 5 engine the same
way -- on demand, entirely on GitHub's servers. Trigger it from the
Actions tab with an `instrument` and `style` (aggressive/conservative)
input; it downloads the latest `data-latest` cache, restores any
previously published results, runs `backtest.engine.runner`, regenerates
the results dashboard (`backtest/engine/report.py`), and publishes it to
GitHub Pages -- so there's a standing webpage with win rate, average R,
and a cumulative-R equity curve per instrument/style run, updated
automatically after every run. Requires `fetch-data.yml` to have
published data at least once first. Each run also still uploads the raw
trade-log CSV as a workflow artifact, for anyone who wants the underlying
data rather than just the summary.

**One-time manual step required**: GitHub Pages has to be enabled once
per repo -- go to **Settings -> Pages -> Source**, select **"Deploy from
a branch"**, branch **`gh-pages`** (folder `/ (root)`), and save. The
`gh-pages` branch itself doesn't exist yet -- it gets created
automatically the first time `run-backtest.yml` runs, so run the
workflow once first, then come back and set the Pages source to
`gh-pages` once it exists. After that, the dashboard is live at
`https://<owner>.github.io/<repo>/` and updates itself on every
subsequent run -- no further manual steps.

## Setup (running the pipeline manually instead)

```bash
cd backtest/data_pipeline
pip install -r requirements.txt
```

No credentials needed -- Dukascopy requires none.

## Fetching data

Run these from the **repo root** (the folder containing `backtest/`,
`bot/`, `knowledge-base/`), not from inside `backtest/data_pipeline` --
`python -m` needs the `backtest` package to be importable from your
current directory:

```bash
# everything: all instruments, all granularities
python -m backtest.data_pipeline.fetch_dukascopy --all

# one instrument, all granularities
python -m backtest.data_pipeline.fetch_dukascopy --instrument EURUSD

# one instrument, one granularity
python -m backtest.data_pipeline.fetch_dukascopy --instrument XAUUSD --granularity H4
```

Incremental by default -- re-running only pulls candles newer than what's
already cached, so a daily cron-style re-run is cheap. See
`instruments.py` for the full supported instrument list and how to add
more.

**Validated**: a full `--all` run (all 26 instruments, all 8 native
granularities) has completed successfully end to end, including the
less-common CFD codes (`E_Light` for oil, `E_D&J-Ind`/`E_NQ-100`/
`E_N225Jap` for indices) and crypto (ETHUSD -- 313,743 M5 candles alone).
`derive_granularities --all` (H2/H3/M45) has also run successfully
against the resulting cache. The full pipeline is confirmed working.

**On first run, M30/M15/M5 default to 3 years of history instead of full
history** (the higher timeframes default to Dukascopy's full available
history, back to 2003). Minute-level data for 26 instruments across
decades would be slow to pull and produce unnecessarily huge cache files
-- 3 years is already plenty of confirmation-entry setups for a
meaningful backtest sample. Delete a cached CSV and re-run if you want
more history for a specific symbol/granularity later.

## Storage format

`backtest/data/{source}/{symbol}/{granularity}.csv`, columns
`time,open,high,low,close,volume`, UTC timestamps, one row per *closed*
candle only (the still-forming current candle is never cached). Not
committed to git -- it's regenerable from the fetchers, and would balloon
the repo size across dozens of instrument/granularity pairs.

## Deriving H2 / H3 / M45

Dukascopy has no native 2H, 3H, or 45-minute granularity -- only 1H and
4H between M30 and Daily. The Bishop PDF review found all three used as
confirmation timeframes by traders in the community, so `resample.py`
derives them locally from the cached H1 (-> H2, H3) and M15 (-> M45)
data via pandas resampling. No network call -- run it after
`fetch_dukascopy.py` has populated H1/M15 for the instrument(s) you need:

```bash
python -m backtest.data_pipeline.derive_granularities --all
python -m backtest.data_pipeline.derive_granularities --instrument EURUSD --granularity H2
```

Writes into the same cache format (`backtest/data/dukascopy/{symbol}/H2.csv`
etc.), so `backtest/engine/` doesn't need to know or care whether a
granularity was fetched directly or derived.

One assumption worth knowing about: bins are anchored to UTC midnight
(H2 = 00:00-02:00, 02:00-04:00, ...; M45 tiles exactly since 1440/45=32).
STRATEGY.md doesn't specify what anchor MT5/TradingView actually use for
these non-standard intervals, so if backtest results on H2/H3/M45 ever
look off from what you see live in MT5, a differently-anchored broker
candle is the first thing to check -- consistent with the "candle closes
can differ slightly between feeds" caveat already in STRATEGY.md
Section 2. Covered by `backtest/data_pipeline/tests/test_resample.py`
(OHLCV aggregation correctness, exact M45 tiling, and that gaps produce
no candle rather than a synthetic flat one).

## Engine

`backtest/engine/` implements STRATEGY.md's rules against cached candles,
built in phases so each is testable before the next depends on it:

- [x] **Phase 1 -- structure & liquidity primitives** (`structure.py`,
      `liquidity.py`, `candles.py`): the CRITICAL wick-sweep-vs-body-close-
      break rule (Section 4), the sweep+break state machine that produces
      strong high/low, SCF single-candle IRL/ERL tagging generalized to
      multi-candle structural liquidity (Section 3), and the sequential
      per-category liquidity target flip (daily/weekly/monthly/Asian).
      Covered by `engine/tests/` (synthetic candle sequences, run with
      `python -m pytest backtest/engine/tests/`).
- [x] **Phase 2 -- key-level detection & ranking** (`key_levels.py`,
      `imbalance.py`, `ranking.py`): A-shape/V-shape (close-price peaks/
      troughs, per Section 5's "marked on closes, not wicks" resolution)
      and open-close continuation levels; the universal disrespect/flip
      rule (reuses Phase 1's body-close CRITICAL rule); QMR test-counting
      (2+ prior tests before disrespect, Video 17); and a 4-factor scored
      ranking system (imbalance overlap, recency, QMR test count,
      imbalance-fill size) with CALLER-SUPPLIED weights rather than a
      hardcoded combination formula -- see the module docstring in
      `ranking.py` for why. Also resolves the one real definitional gap
      in STRATEGY.md: "imbalance"/FVG is never precisely defined anywhere
      in the source material, so `imbalance.py` uses the standard ICT
      3-candle gap definition as a stated assumption.
- [x] **Phase 3 -- bias cascade & bias-flip state machine** (`bias.py`):
      the 3-condition flip test (Video 16, completed by Video 17) -- a
      higher-timeframe bias only flips when price trades into the next
      key level on its origin timeframe, rejects and closes the new
      direction, AND the next lower timeframe also stops confirming the
      old direction; if the lower timeframe still confirms the old
      direction, the bias stays put (Video 16's resolved ambiguity).
      Enforces Video 17's completion directly in the type system: only
      `Confirmation` objects (breakout or sweep+break, from
      `detect_confirmations()`) can satisfy condition (c) -- open-close
      breaks and engulfing (Phase 2's disrespect logic) are a different
      type and structurally can't be passed in as flip evidence, so the
      "never validates a bias flip" rule can't be accidentally violated
      by a future caller. Also implements the confirmed strict priority
      hierarchy (Weekly > Daily > 4H > lower timeframes) and Video 16's
      breakout-vs-sweep+break acceptance (both count as valid
      confirmation; `detect_confirmations()` merges them without
      double-tagging a single event as both).
- [x] **Phase 4 -- entry triggers & trade management** (`entries.py`,
      `trade_management.py`): engulfing-candle detection; Video 14's 3
      execution-facing entry patterns (direct mitigation, fresh-IRL-
      required, nested disrespect -- a restatement of Video 13's
      4-branch decision tree); Video 12's IRL-necessity rule (required
      for origin trades, optional for continuation); Video 13's three
      distinct mechanized stop-loss rules (origin: beyond the structural
      extreme + padding; continuation: fixed ~10 pips; no-IRL
      continuation: a tighter stop just past the engulfed candle's own
      extreme); the Aggressive/Conservative entry-style split (Section 5,
      "both sanctioned -- build/test both"); trade stacking via
      `PositionManager` (Video 14 -- multiple concurrent same-direction
      positions, deliberately not restricted to origin-only or
      continuation-only since that's an open question per Section 9);
      the 1:3 primary risk-reward target; Video 16's tiered exit-target
      rule (a storyline concludes at another key level on its OWN origin
      timeframe, not the lower-timeframe entry-trigger level); and
      Bishop's conservative-target cap for countertrend trades taken off
      a swept breakout-candle extreme.
- [x] **Phase 5 -- full backtest runner** (`runner.py`, `trade_log.py`):
      wires Phases 1-4 together into one real MVP chain -- Daily (bias
      origin) -> H4 (lower-timeframe flip evidence) -> H1 (entry trigger
      and trade management), the concrete instantiation of Section 2's
      "Daily beats 4H... scale down further for entries" routine. Bias is
      bootstrapped from the first confirmed Daily structure, replayed
      forward through `bias.replay_bias()` (new in this phase -- a
      backtest driver built on top of the already-tested `BiasCascade`,
      not a reimplementation of it); entries fire on H1 engulfing candles
      aligned with the effective (priority-resolved) bias, classified via
      Phase 4's 3-pattern logic, with stop/target rules selected by
      trade kind and IRL presence exactly as Phase 4 defines them.
      MAE/MFE and R-multiples are computed by walking forward candle by
      candle to whichever of stop/target is touched first. Run via
      `python -m backtest.engine.runner --instrument EURUSD --style
      conservative` (from the repo root) or the `run-backtest.yml`
      GitHub Actions workflow -- both write a `TradeRecord` CSV plus a
      console summary (win rate, total/average R).
      `trade_log.py`'s `TradeRecord` schema logs far more than win/loss
      per trade -- full multi-timeframe bias context, all 4 of Phase 2's
      ranking factors, which entry pattern and stop-loss rule fired, and
      MAE/MFE in R-multiples -- specifically so the resulting dataset
      doubles as ML training data later, not just a backtest report.
      Validated end-to-end against a synthetic multi-timeframe scenario
      (`engine/tests/test_runner.py`) covering both entry styles, since
      this session has no way to run it against real cached data itself
      (see "Data source" above) -- **the first real run against actual
      Dukascopy history is still the true first test of this chain**,
      same caveat as the data pipeline had at first.

      **Performance**: a full-history H1 run (EURUSD's uncapped H1 cache
      is well over 100,000 candles) can legitimately take up to a couple
      minutes -- that's expected, not a hang. Two things keep it there
      rather than effectively hanging: `_last_direction_at()` uses a
      pre-sorted bisect lookup instead of rescanning the whole
      confirmation list per candle, and `MAX_TRADE_DURATION_CANDLES`
      (500 H1 bars, ~3 weeks) caps how far `_resolve_trade_outcome()`
      searches forward before giving up on an unresolved trade --
      without that cap, a trade opened early in a multi-year series
      could scan every remaining candle to the end of history if its
      target was never hit again, and with many trades opening over that
      history the cost multiplies badly. The cap is a performance fix
      but also a more faithful one: Section 8 states this is a
      day-trading approach that "does not swing trades overnight as a
      rule," so a trade genuinely unresolved after ~3 weeks of H1 bars
      isn't realistic to model as still open anyway. Stress-tested
      against a synthetic 180,000-candle H1 series (deliberately
      pathological -- random-walk data fires far more engulfing signals
      than real price action does) at ~13,700 trades in 86 seconds; real
      data should run faster than that worst case.

      `report.py` turns the CSV trade logs into the GitHub Pages
      dashboard described above -- dependency-free (no Chart.js/CDN, just
      inline SVG generated in Python), so it renders identically whether
      or not the viewer's browser can reach a CDN. Beyond the summary
      stats and equity curve, it also renders a **trade-by-trade
      reasoning table** directly on the page (not just a CSV download) --
      each row reconstructs the trade's story from `TradeRecord`'s
      fields: the bias reading on every timeframe and which one won the
      priority hierarchy, which entry pattern fired, the key level and
      its QMR/imbalance quality signals, and which stop-loss rule
      applied -- so the dashboard answers "why did it take this trade",
      not just "did it win". Capped at the most recent 1,000 trades per
      run to keep the page a sane size; the CSV download link still has
      the full history. Covered by `engine/tests/test_report.py`.
- [ ] **Not yet built**: the full Monthly->Weekly->Daily->4H->lower
      cascade (this MVP only does Daily->H4->H1); performance metrics
      beyond win rate/total R (drawdown, profit factor); multi-instrument
      batch runs; weight-sweeping across Phase 2's `ranking.py` factors
      or Phase 4's entry-style/stop-rule variants against real results.

Four deliberate design choices worth flagging:
- STRATEGY.md never gives a precise algorithm for identifying "a prior
  swing point" ("look to the left" is qualitative). Phase 1 uses a
  standard n-bar fractal (local extreme over n bars each side) with `n`
  exposed as a parameter, so swing sensitivity is a backtest-tunable
  input rather than something silently hardcoded as if it were part of
  the taught rule.
- STRATEGY.md's Section 9 explicitly flags unresolved tension between its
  four key-level ranking factors, with no combination rule given. Phase 2
  doesn't guess one -- `ranking.py`'s `DEFAULT_WEIGHTS` (equal weighting)
  is a placeholder to have something runnable, and every factor is left
  independently inspectable on `RankedCandidate` so different weightings
  can be swept during backtesting instead of assumed.
- Video 18 draws a semantic distinction between "break of structure"
  (initiation/origin) and "breakout" (continuation) that's separate from
  Video 16's visual sweep-vs-no-sweep distinction, and Section 2 itself
  reconciles them as related but not identical. Phase 3 doesn't implement
  a third independent classifier for this -- a confirmation event is
  BOS/origin exactly when it's the event that flips `BiasCascade.direction`,
  and a continuation/breakout otherwise, which is a direct reading of
  Section 2's own reconciliation ("a storyline typically begins with a
  break of structure... subsequent confirmations in that established
  direction are properly breakouts").
- Video 13's original 4-branch decision tree describes branches 2 and 4
  with more candle-by-candle detail than Video 14's 3-pattern restatement
  captures (e.g. branch 2 mentions an intermediate "third candle taps the
  original IRL" step Video 14 doesn't repeat). `entries.py`'s
  `classify_entry_pattern()` implements Video 14's simpler 3-pattern
  version directly off the candles immediately following the engulf,
  which is a deliberate simplification -- worth revisiting against real
  backtest output if FRESH_IRL_REQUIRED or NESTED_DISRESPECT classifications
  look wrong on actual charts.
- `runner.py`'s module docstring lists its own MVP simplifications in
  full (Daily->H4->H1 only, bootstrapped initial bias, simplified H4/H1
  bias readings, engulf-open as the consumed key level, a proximity-based
  origin/continuation heuristic, bounded look-ahead windows for QMR/
  confirmation checks, and the same-candle stop-vs-target tie-break) --
  not repeated here to avoid the two copies drifting out of sync.

Candle processing is a plain forward loop over a `list[Candle]`, not
vectorized pandas -- so the same detection code can later replay live,
just-closed MT5 bars one at a time instead of only working in batch mode.
