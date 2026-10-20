"""Resample H1 with an explicit New York 17:00 session clock.

This is the inherited feed convention, not a claim about every teacher's broker.
Bar ends are calendar boundaries, never the last available sample's timestamp.
"""
import pandas as pd


def _key(idx, tf):
    # shift so 17:00 New York becomes midnight; then H2/H4/D/W/M are plain calendar bins
    s = (idx.tz_convert("America/New_York").tz_localize(None) + pd.Timedelta(hours=7))
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
    """OHLC bars with observed UTC start and nominal UTC end, oldest first.

Includes a final forming bar; callers wanting only usable signals must use
``completed`` or filter ``end`` against their as-of clock explicitly.
"""
    df = h1.copy()
    df["t"] = df.index
    if tf == "H1":
        df["start"], df["end"] = df["t"], df["t"] + pd.Timedelta(hours=1)
        return df[["open", "high", "low", "close", "start", "end"]].reset_index(drop=True)
    g = df.groupby(_key(df.index, tf))
    out = pd.DataFrame({
        "open": g["open"].first(), "high": g["high"].max(), "low": g["low"].min(),
        "close": g["close"].last(), "start": g["t"].min(),
    })
    out["end"] = _ends(out.index, tf)
    return out.reset_index(drop=True)


def _ends(keys, tf):
    steps = {"H2": pd.Timedelta(hours=2), "H4": pd.Timedelta(hours=4),
             "D": pd.Timedelta(days=1), "W": pd.Timedelta(days=5), "M": pd.offsets.MonthBegin(1)}
    if tf not in steps:
        raise ValueError(tf)
    local = pd.DatetimeIndex(keys) + steps[tf] - pd.Timedelta(hours=7)
    # At the autumn repeated 01:00 boundary, the previous bin ends at the
    # first occurrence; the following bin contains both folds of 01:00.
    return local.tz_localize("America/New_York", ambiguous=True).tz_convert("UTC")


def nominal_end(start, tf):
    """Calendar close of the bar containing aware ``start``, in UTC.

    Handles missing first/last samples and DST. W ends Friday 17:00 New York;
    M ends 17:00 New York on its last calendar day.
    """
    start = pd.Timestamp(start)
    if start.tzinfo is None:
        raise ValueError("start must include a timezone")
    if tf == "H1":
        return start.tz_convert("UTC").floor("h") + pd.Timedelta(hours=1)
    return _ends(_key(pd.DatetimeIndex([start]), tf), tf)[0]


def completed(h1, tf, now):
    """Resample only information available at ``now`` and omit forming bars.

    This proves clock completion, not historical feed completeness. Missing
    market hours require separate input-coverage validation before replay.
    """
    now = pd.Timestamp(now)
    if now.tzinfo is None:
        raise ValueError("now must include a timezone")
    eligible = h1[h1.index + pd.Timedelta(hours=1) <= now]
    bars = resample(eligible, tf)
    return bars[bars["end"] <= now].reset_index(drop=True)
