"""Per-symbol pip size, price decimals and Dukascopy names (FX, metals, indices). Stdlib only.

pip(pair) is the unit of every *_pips setting (tap/level/overlap tolerance, stop buffer, max_stop_pips, spread) and of
the stop_pips numbers in alerts. Order of precedence:
  1. the broker's own pip: cTrader symbol `pipPosition` (pip = 10**-pipPosition) when it is known in this process
     (`register`, called by slk/store.py when it loads a cTrader candle file whose meta carries the symbol info);
  2. the static table below: FX 0.0001 (JPY quote 0.01), XAUUSD 0.1, XAGUSD 0.01, other metals 0.1, indices 1.0.
Price decimals for messages follow the same order (cTrader `digits`, else the table).
Before 2026-10-14 every non-JPY symbol was 0.0001 with 5 decimals, so gold tolerances/buffers were 1000x too small
and prices were printed as 4154.36000 (REVIEW "Gold alert check").
"""
import re

FX_PIP, JPY_PIP = 0.0001, 0.01
# symbol prefix -> (pip, decimals). Gold 0.1 / silver 0.01 = the usual retail convention (owner, 2026-10-14).
METALS = {"XAU": (0.1, 2), "XAG": (0.01, 3), "XPT": (0.1, 2), "XPD": (0.1, 2)}
# Index CFDs as IC Markets cTrader names them (and common aliases): 1 pip = 1 index point, 2 decimals.
INDICES = {"US500", "US30", "USTEC", "US2000", "UK100", "DE40", "GER40", "DE30", "JP225", "AUS200", "FRA40",
           "F40", "EUSTX50", "STOXX50", "HK50", "CA60", "CN50", "ES35", "IT40", "NETH25", "SWI20", "SPX500",
           "NAS100", "SPI200"}
# Dukascopy datafeed names and price scale (prices are int32 * 1/point) of non-FX symbols we can fall back to.
DUKASCOPY = {"XAUUSD": ("XAUUSD", 1e3), "XAGUSD": ("XAGUSD", 1e3),
             "US500": ("USA500IDXUSD", 1e3), "SPX500": ("USA500IDXUSD", 1e3), "US30": ("USA30IDXUSD", 1e3),
             "USTEC": ("USATECHIDXUSD", 1e3), "NAS100": ("USATECHIDXUSD", 1e3), "DE40": ("DEUIDXEUR", 1e3),
             "GER40": ("DEUIDXEUR", 1e3), "UK100": ("GBRIDXGBP", 1e3), "JP225": ("JPNIDXJPY", 1e3),
             "AUS200": ("AUSIDXAUD", 1e3), "FRA40": ("FRAIDXEUR", 1e3), "EUSTX50": ("EUSIDXEUR", 1e3),
             "HK50": ("HKGIDXHKD", 1e3)}

_BROKER = {}  # normalized pair -> {"pip": float, "digits": int} (cTrader symbol info seen in this process)


def norm(pair):
    return re.sub(r"[^A-Z0-9]", "", str(pair).upper())


def static(pair):
    """(pip, decimals) from the table (no broker info)."""
    p = norm(pair)
    if is_deriv(p):
        for row in deriv_symbols():
            if row["key"]==p:return row["pip"],row["digits"]
        raise ValueError("Deriv pip metadata unavailable")
    for pre, v in METALS.items():
        if p.startswith(pre):
            return v
    if p in INDICES:
        return 1.0, 2
    return (JPY_PIP, 3) if p.endswith("JPY") else (FX_PIP, 5)


def register(pair, pip_position=None, digits=None):
    """Remember the broker's pip (10**-pip_position) and price digits for `pair` (cTrader symbol info)."""
    d = {}
    if pip_position is not None:
        d["pip"] = 10.0 ** -int(pip_position)
    if digits is not None:
        d["digits"] = int(digits)
    if d:
        _BROKER[norm(pair)] = d


def clear():
    _BROKER.clear()


def pip(pair):
    b = _BROKER.get(norm(pair), {})
    return b.get("pip") or static(pair)[0]


def decimals(pair):
    b = _BROKER.get(norm(pair), {})
    d = b.get("digits")
    return d if d is not None else static(pair)[1]


def fmt(pair, x):
    return "-" if x is None else f"{float(x):.{decimals(pair)}f}"


def mismatch(pair, pip_position):
    """Text when the broker's pip differs from the static table (diagnostics), else None."""
    if pip_position is None:
        return None
    a, b = 10.0 ** -int(pip_position), static(pair)[0]
    return None if abs(a - b) < 1e-12 else f"{norm(pair)}: cTrader pip {a:g} (pipPosition {pip_position}) != table {b:g}"


def dukascopy(pair):
    """(datafeed name, point) for Dukascopy: FX = the pair itself, 1e5 (JPY quote 1e3)."""
    p = norm(pair)
    if p in DUKASCOPY:
        return DUKASCOPY[p]
    return p, (1e3 if p.endswith("JPY") else 1e5)


def is_deriv(pair):
    return norm(pair).startswith("DV")


def deriv_symbols():
    import json
    from pathlib import Path
    path=Path(__file__).resolve().parents[1]/"data"/"deriv_symbols.json"
    return json.loads(path.read_text())["symbols"] if path.exists() else []


def label(pair):
    if is_deriv(pair):
        for row in deriv_symbols():
            if row["key"]==norm(pair):return "Deriv · "+row["name"]
        return "Deriv · "+str(pair)
    return str(pair)


def deriv_continuous(pair):
    return any(r["key"]==norm(pair) and r.get("market") in ("synthetic_index","cryptocurrency")
               for r in deriv_symbols())


def market_category(symbol, market=None):
    """UI classification; provider market wins where supplied by Deriv."""
    markets={'synthetic_index':'Synthetic indices','cryptocurrency':'Cryptocurrencies',
             'indices':'Indices','commodities':'Commodities'}
    if market in markets:return markets[market]
    pair=re.sub('^FRX','',symbol.upper())
    major={'EURUSD','GBPUSD','USDJPY','USDCHF','USDCAD','AUDUSD','NZDUSD'}
    currencies={'USD','EUR','GBP','JPY','CHF','CAD','AUD','NZD','SGD','HKD','CNH','CZK','DKK','HUF','MXN','NOK','PLN','SEK','THB','TRY','ZAR'}
    if pair in major:return 'Forex · majors'
    if len(pair)==6 and pair[:3] in currencies and pair[3:] in currencies:
        return 'Forex · minors' if {pair[:3],pair[3:]} <= {'USD','EUR','GBP','JPY','CHF','CAD','AUD','NZD'} else 'Forex · exotics'
    if pair.startswith(('XAU','XAG','XPT','XPD')):return 'Metals'
    if pair in {'XBRUSD','XTIUSD','XNGUSD'}:return 'Energy'
    if re.fullmatch(r'GC[A-Z]\d{2}',pair):return 'Futures'
    if pair in {'AUS200','CA60','CHINA50','CHINAH','DE30','DE40','ES35','F40','HK50','IT40','JP225','MIDDE50','MIDDE60','NETH25','NOR25','SA40','SE30','STOXX50','SWI20','TECDE30','UK100','US2000','US30','US500','USTEC'}:return 'Indices'
    if pair.endswith('USD'):return 'Cryptocurrencies'
    return 'Other markets'
