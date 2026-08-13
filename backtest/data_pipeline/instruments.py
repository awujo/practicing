"""
Canonical instrument list for the SLK backtester's data pipeline.

Data source: Dukascopy, via the `dukascopy-python` package. No account, no
KYC, no API key -- Oanda (the broker referenced throughout STRATEGY.md)
rejects new clients from Nigeria, and separately this session's own
network egress policy blocks outbound calls to Oanda, Dukascopy,
Twelve Data, and Binance alike (confirmed by testing all four -- see
backtest/README.md). Dukascopy is the one option here that needs no
account at all, so once the pipeline runs somewhere with normal internet
access (your own machine, not this cloud session), there's no signup step
in the way. It also covers forex, metals, oil, indices, AND crypto from a
single source, so the separate ccxt/Binance fetcher is no longer needed
as the primary path (kept around as `fetch_crypto.py` only as a fallback
for deeper crypto history than Dukascopy has).

Granularity mapping (STRATEGY.md timeframe -> dukascopy_python INTERVAL_*):
    Monthly -> INTERVAL_MONTH_1     Weekly -> INTERVAL_WEEK_1
    Daily -> INTERVAL_DAY_1         4H -> INTERVAL_HOUR_4
    1H -> INTERVAL_HOUR_1           30min -> INTERVAL_MIN_30
    15min -> INTERVAL_MIN_15        5min -> INTERVAL_MIN_5

NOTE: Dukascopy has no native 2H/3H/45min granularity. Resolved via local
resampling, not fetched directly -- see resample.py and
derive_granularities.py, run after H1/M15 are cached.
"""

# Granularities pulled for every instrument by default -- everything
# Dukascopy natively supports from STRATEGY.md's cascade. H2/H3/M45 are
# deliberately absent; see the module docstring.
DEFAULT_GRANULARITIES = ["M", "W", "D", "H4", "H1", "M30", "M15", "M5"]

# Our granularity code -> dukascopy_python attribute name (fetch_dukascopy.py
# does getattr(dukascopy_python, name), so a stale name fails loudly at
# call time rather than silently mis-mapping).
DUKASCOPY_GRANULARITY_TO_INTERVAL = {
    "M": "INTERVAL_MONTH_1",
    "W": "INTERVAL_WEEK_1",
    "D": "INTERVAL_DAY_1",
    "H4": "INTERVAL_HOUR_4",
    "H1": "INTERVAL_HOUR_1",
    "M30": "INTERVAL_MIN_30",
    "M15": "INTERVAL_MIN_15",
    "M5": "INTERVAL_MIN_5",
}

# Internal symbol -> dukascopy_python.instruments constant NAME (not the
# value directly, so fetch_dukascopy.py can do getattr(instruments, name)
# and fail loudly if a name ever goes stale against a future package version).
DUKASCOPY_INSTRUMENTS = {
    # Forex majors
    "EURUSD": "INSTRUMENT_FX_MAJORS_EUR_USD",
    "GBPUSD": "INSTRUMENT_FX_MAJORS_GBP_USD",
    "USDJPY": "INSTRUMENT_FX_MAJORS_USD_JPY",
    "USDCHF": "INSTRUMENT_FX_MAJORS_USD_CHF",
    "USDCAD": "INSTRUMENT_FX_MAJORS_USD_CAD",
    "AUDUSD": "INSTRUMENT_FX_MAJORS_AUD_USD",
    "NZDUSD": "INSTRUMENT_FX_MAJORS_NZD_USD",
    # Forex crosses seen in mentor/Bishop material
    "EURGBP": "INSTRUMENT_FX_CROSSES_EUR_GBP",
    "EURJPY": "INSTRUMENT_FX_CROSSES_EUR_JPY",
    "EURCHF": "INSTRUMENT_FX_CROSSES_EUR_CHF",
    "EURCAD": "INSTRUMENT_FX_CROSSES_EUR_CAD",
    "EURNZD": "INSTRUMENT_FX_CROSSES_EUR_NZD",
    "GBPJPY": "INSTRUMENT_FX_CROSSES_GBP_JPY",
    "GBPCHF": "INSTRUMENT_FX_CROSSES_GBP_CHF",
    "GBPCAD": "INSTRUMENT_FX_CROSSES_GBP_CAD",
    "GBPNZD": "INSTRUMENT_FX_CROSSES_GBP_NZD",
    "GBPAUD": "INSTRUMENT_FX_CROSSES_GBP_AUD",
    "AUDCAD": "INSTRUMENT_FX_CROSSES_AUD_CAD",
    "AUDJPY": "INSTRUMENT_FX_CROSSES_AUD_JPY",
    "CHFJPY": "INSTRUMENT_FX_CROSSES_CHF_JPY",
    # Metals
    "XAUUSD": "INSTRUMENT_FX_METALS_XAU_USD",  # Gold
    "XAGUSD": "INSTRUMENT_FX_METALS_XAG_USD",  # Silver
    # Energy -- "USOIL" in the mentor/Bishop material is WTI ("Light"), not Brent
    "USOIL": "INSTRUMENT_CMD_ENERGY_E_LIGHT",
    # Indices (CFDs)
    "US30": "INSTRUMENT_IDX_AMERICA_E_D_J_IND",   # Dow Jones Industrial
    "NAS100": "INSTRUMENT_IDX_AMERICA_E_NQ_100",  # Nasdaq 100
    "JP225": "INSTRUMENT_IDX_ASIA_E_N225JAP",     # Nikkei 225
    # Crypto -- Dukascopy covers this directly, no separate source needed
    "ETHUSD": "INSTRUMENT_VCCY_ETH_USD",
}


# Fallback only (fetch_crypto.py) -- Dukascopy's ETH/USD above is the
# primary crypto path now. Kept in case Dukascopy's crypto history turns
# out too short for a given backtest window and deeper Binance history is
# needed instead.
CCXT_INSTRUMENTS = {
    "ETHUSDT": {"exchange": "binance", "symbol": "ETH/USDT"},
}


def all_instruments():
    """Yield (internal_symbol, dukascopy_instrument_constant_name) for every configured instrument."""
    yield from DUKASCOPY_INSTRUMENTS.items()
