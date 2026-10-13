"""Resample H1 to Kevin's timeframes. Candles close at 17:00 New York (STRATEGY §5)."""
import pandas as pd


def _key(idx, tf):
    # shift so 17:00 New York becomes midnight; then H4/D/W/M are plain calendar bins
    s = (idx.tz_convert("America/New_York").tz_localize(None) + pd.Timedelta(hours=7))
    if tf == "H4":
        return s.floor("4h")
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
