"""Resample H1 to Kevin's timeframes. Candles close at 17:00 New York (STRATEGY §5)."""
import pandas as pd
from contextvars import ContextVar
from contextlib import contextmanager
from functools import wraps

UTC_MARKET=ContextVar("slk_utc_market",default=False)

@contextmanager
def market(pair):
    from .instruments import is_deriv
    token=UTC_MARKET.set(is_deriv(pair))
    try:yield
    finally:UTC_MARKET.reset(token)


def market_function(extract):
    def decorate(function):
        @wraps(function)
        def run(*args,**kwargs):
            with market(extract(args,kwargs)):
                return function(*args,**kwargs)
        return run
    return decorate


def wall_time(idx):
    if UTC_MARKET.get():return idx.tz_convert("UTC").tz_localize(None)
    return idx.tz_convert("America/New_York").tz_localize(None)+pd.Timedelta(hours=7)



def _key(idx, tf):
    # shift so 17:00 New York becomes midnight; then H2/H4/D/W/M are plain calendar bins
    s = wall_time(idx)
    if tf == "H4":
        return s.floor("4h")
    if tf == "H2":
        return s.floor("2h")
    if tf == "D":
        return s.floor("D")
    if tf == "W":
        d = s.floor("D")
        return d - pd.to_timedelta(d.dayofweek, unit="D")
    if tf == "M":
        return s.to_period("M").to_timestamp()
    raise ValueError(tf)


def resample(h1, tf):
    """OHLC bars of timeframe tf with UTC 'start' and 'end' columns, oldest first."""
    df = h1.copy()
    df["t"] = df.index
    if tf == "H1":
        df["start"], df["end"] = df["t"], df["t"] + pd.Timedelta(hours=1)
        return df[["open", "high", "low", "close", "start", "end"]].reset_index(drop=True)
    g = df.groupby(_key(df.index, tf))
    out = pd.DataFrame({
        "open": g["open"].first(), "high": g["high"].max(), "low": g["low"].min(),
        "close": g["close"].last(), "start": g["t"].min(), "end": g["t"].max() + pd.Timedelta(hours=1),
    })
    return out.reset_index(drop=True)


def nominal_end(start, tf):
    """Nominal close (UTC) of the D/W/M bar that starts at `start`: 17:00 New York; a week closes Friday 17:00,
    a month at 17:00 New York on its last day (same clock as slk/live.py drop_forming)."""
    k = _key(pd.DatetimeIndex([pd.Timestamp(start)]), tf)[0]
    if UTC_MARKET.get():
        return (k+(pd.offsets.MonthBegin(1) if tf=="M" else pd.Timedelta(days=7 if tf=="W" else 1))).tz_localize("UTC")
    e = k + (pd.offsets.MonthBegin(1) if tf == "M" else pd.Timedelta(days=5 if tf == "W" else 1))
    return (e - pd.Timedelta(hours=7)).tz_localize("America/New_York").tz_convert("UTC")
