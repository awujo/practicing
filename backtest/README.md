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
gets picked. **Run this pipeline on your own machine**, where normal
outbound internet access applies.

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

## Setup

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
- [ ] Phase 2 -- key-level detection (A/V-shape, open-close, QMR) + the
      4-factor ranking system (Section 5)
- [ ] Phase 3 -- bias cascade + bias-flip state machine (Section 2)
- [ ] Phase 4 -- entry triggers + trade management/stacking (Sections 5-6)
- [ ] Phase 5 -- full backtest runner + performance metrics

One deliberate design choice worth flagging: STRATEGY.md never gives a
precise algorithm for identifying "a prior swing point" ("look to the
left" is qualitative). Phase 1 uses a standard n-bar fractal (local
extreme over n bars each side) with `n` exposed as a parameter, so swing
sensitivity is a backtest-tunable input rather than something silently
hardcoded as if it were part of the taught rule.

Candle processing is a plain forward loop over a `list[Candle]`, not
vectorized pandas -- so the same detection code can later replay live,
just-closed MT5 bars one at a time instead of only working in batch mode.
