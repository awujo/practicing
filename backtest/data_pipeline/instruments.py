"""
Canonical instrument list for the SLK backtester's data pipeline.

Maps our internal symbol to the source-specific instrument code, asset
class, and where to fetch it from. Oanda covers forex, metals, energy, and
index CFDs in one feed (and is the broker referenced throughout
STRATEGY.md, so its candle data matches what the strategy was taught on).
Crypto isn't available on Oanda, so it's routed through ccxt/Binance
instead.

Granularity mapping (STRATEGY.md timeframe -> Oanda granularity code):
    Monthly -> M      Weekly -> W       Daily -> D
    4H -> H4          3H -> H3          2H -> H2         1H -> H1
    30min -> M30      15min -> M15      5min -> M5

NOTE: Oanda has no native 45-minute granularity (M45 shows up in the
Bishop PDF review as a confirmation timeframe some traders use). There's
no way around this except resampling M15 bars into 45-minute bars
ourselves during backtest prep -- flagging here so it isn't forgotten
when the resampling step gets built.
"""

# Granularities pulled for every instrument by default. Trimmed to what
# STRATEGY.md's cascade actually uses (Section 2's Monthly/Weekly/Daily/4H
# bias chain, Section 5/7's flexible lower-timeframe confirmation set).
DEFAULT_GRANULARITIES = ["M", "W", "D", "H4", "H3", "H2", "H1", "M30", "M15", "M5"]

OANDA_INSTRUMENTS = {
    # Forex majors
    "EURUSD": "EUR_USD",
    "GBPUSD": "GBP_USD",
    "USDJPY": "USD_JPY",
    "USDCHF": "USD_CHF",
    "USDCAD": "USD_CAD",
    "AUDUSD": "AUD_USD",
    "NZDUSD": "NZD_USD",
    # Forex crosses seen in mentor/Bishop material
    "EURGBP": "EUR_GBP",
    "EURJPY": "EUR_JPY",
    "EURCHF": "EUR_CHF",
    "EURCAD": "EUR_CAD",
    "EURNZD": "EUR_NZD",
    "GBPJPY": "GBP_JPY",
    "GBPCHF": "GBP_CHF",
    "GBPCAD": "GBP_CAD",
    "GBPNZD": "GBP_NZD",
    "GBPAUD": "GBP_AUD",
    "AUDCAD": "AUD_CAD",
    "AUDJPY": "AUD_JPY",
    "CHFJPY": "CHF_JPY",
    # Metals
    "XAUUSD": "XAU_USD",  # Gold
    "XAGUSD": "XAG_USD",  # Silver
    # Energy
    "USOIL": "WTICO_USD",  # WTI crude, matches "USOIL" naming in Bishop's PDF
    # Indices (CFDs)
    "US30": "US30_USD",
    "NAS100": "NAS100_USD",
    "JP225": "JP225_USD",
}

# Crypto isn't on Oanda -- pulled from Binance via ccxt instead. Symbol is
# the ccxt/exchange pair format.
CCXT_INSTRUMENTS = {
    "ETHUSDT": {"exchange": "binance", "symbol": "ETH/USDT"},
}


def all_instruments():
    """Yield (internal_symbol, source, source_symbol) for every configured instrument."""
    for internal, oanda_symbol in OANDA_INSTRUMENTS.items():
        yield internal, "oanda", oanda_symbol
    for internal, cfg in CCXT_INSTRUMENTS.items():
        yield internal, "ccxt", cfg
