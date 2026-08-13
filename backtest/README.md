# Backtest data pipeline

This is the data layer only -- it fetches and locally caches historical
OHLCV candles so the actual strategy/backtest engine (not built yet) has
something to run against. See `../knowledge-base/STRATEGY.md` for the
ruleset this will eventually test.

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

## Not built yet

The actual backtest engine: candle-close structure-break detection,
key-level/liquidity-pool identification, the bias cascade and bias-flip
state machine, entry/exit logic, position sizing/stacking. This pipeline
only gets the raw price data in place first.
