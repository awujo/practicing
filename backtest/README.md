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

**This pipeline has not been run against live Dukascopy data yet** -- it
was built and validated (instrument/granularity name resolution, unit
tests) from this cloud session, but the actual network fetch has never
executed anywhere, since this session can't reach Dukascopy either. Your
first local run is the real end-to-end test; if something's off in the
`dukascopy_client.py` response parsing, that's where it'll show up.

## Storage format

`backtest/data/{source}/{symbol}/{granularity}.csv`, columns
`time,open,high,low,close,volume`, UTC timestamps, one row per *closed*
candle only (the still-forming current candle is never cached). Not
committed to git -- it's regenerable from the fetchers, and would balloon
the repo size across dozens of instrument/granularity pairs.

## Known gaps

Dukascopy has no native 45-minute or 2H/3H granularity -- only 1H and 4H
between M30 and Daily. The Bishop PDF review found both M45 and H2/H3
used as confirmation timeframes by traders in the community. There's no
fetch-side fix for this -- they'll need to be resampled from the cached
M15/H1 data during backtest data prep. Not handled here yet.

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
