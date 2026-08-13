# Backtest

Two parts: a data pipeline (fetches and caches historical OHLCV candles)
and an engine (implements STRATEGY.md's ruleset against that data). See
`../knowledge-base/STRATEGY.md` for the ruleset itself.

Live execution is out of scope here -- it'll eventually run separately
against MT5 (the actual trading platform), once the ruleset extracted
here has been validated on historical data.

## Why Oanda

Oanda is the broker referenced throughout the source material (mentor
videos, Bishop's trade breakdowns), and its free v20 API covers forex
majors/crosses, metals (Gold/Silver), oil, and index CFDs (US30/NAS100/
JP225) from one feed across every granularity the strategy's cascade
needs (Monthly down to 5-minute). Using the same broker's data the
strategy was taught on avoids the "candle closes can differ slightly
between feeds" caveat already flagged in STRATEGY.md Section 2 becoming a
real discrepancy.

Crypto (ETH) isn't on Oanda, so it's pulled separately from Binance via
`ccxt` into the same cache format.

## Setup

```bash
cd backtest/data_pipeline
pip install -r requirements.txt
cp .env.example .env   # fill in OANDA_API_KEY (a free practice account works)
set -a; source .env; set +a
```

## Fetching data

```bash
# everything: all instruments, all granularities
python -m backtest.data_pipeline.fetch_oanda --all
python -m backtest.data_pipeline.fetch_crypto --all

# one instrument, all granularities
python -m backtest.data_pipeline.fetch_oanda --instrument EURUSD

# one instrument, one granularity
python -m backtest.data_pipeline.fetch_oanda --instrument XAUUSD --granularity H4
```

Both fetchers are incremental -- re-running them only pulls candles newer
than what's already cached, so a daily cron-style re-run is cheap. See
`instruments.py` for the full supported instrument list and how to add
more.

## Storage format

`backtest/data/{source}/{symbol}/{granularity}.csv`, columns
`time,open,high,low,close,volume`, UTC timestamps, one row per *closed*
candle only (the still-forming current candle is never cached). Not
committed to git -- it's regenerable from the fetchers, and would balloon
the repo size across dozens of instrument/granularity pairs.

## Known gap

Oanda has no native 45-minute granularity, but the Bishop PDF review
found M45 used as a confirmation timeframe by some traders in the
community. There's no fetch-side fix for this -- it'll need to be
resampled from the cached M15 data during backtest data prep. Not handled
here yet.

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
