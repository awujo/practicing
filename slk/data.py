"""Hourly candles from Dukascopy's public datafeed, cached as CSV.

Files: https://datafeed.dukascopy.com/datafeed/<PAIR>/<YYYY>/<MM-1>/BID_candles_hour_1.bi5
Each record (24 bytes, big-endian): seconds-from-month-start, open, close, low, high (int32
scaled by point), volume (float32). Times are UTC.
"""
import io
import lzma
import os
import random
import struct
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import pandas as pd

URL = "https://datafeed.dukascopy.com/datafeed/{pair}/{y}/{m:02d}/BID_candles_hour_1.bi5"
CACHE = os.environ.get("SLK_CACHE", "data")


def point(pair):
    return 1e3 if pair.endswith("JPY") or pair.startswith("XAU") else 1e5


def _get(url, tries=7):
    last = None
    for k in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.read()
        except Exception as e:  # network hiccup / throttling, or 404 for future months
            if getattr(e, "code", None) == 404:
                return b""
            last = e
            if k < tries - 1:
                time.sleep(2 ** k + random.uniform(0, 1))
    raise RuntimeError(f"download failed: {url} ({type(last).__name__}: {last})")


def _month(pair, y, m):
    raw = _get(URL.format(pair=pair, y=y, m=m - 1))
    if not raw:
        return []
    data = lzma.decompress(raw)
    start = datetime(y, m, 1, tzinfo=timezone.utc).timestamp()
    p = point(pair)
    rows = []
    for off in range(0, len(data), 24):
        t, o, c, lo, hi, v = struct.unpack(">5if", data[off:off + 24])
        if v <= 0:
            continue  # weekend / no-trade filler
        rows.append((start + t, o / p, hi / p, lo / p, c / p))
    return rows


def hourly(pair, start_year, end_year):
    """UTC-indexed hourly OHLC for [start_year, end_year], cached per pair."""
    os.makedirs(CACHE, exist_ok=True)
    path = os.path.join(CACHE, f"{pair}_H1.csv.gz")
    now = datetime.utcnow()
    if os.path.exists(path):
        df = pd.read_csv(path, index_col=0, parse_dates=True)
        # the cache must reach (almost) the end of end_year, or the last week when end_year is not over yet;
        # a cache saved early in a year would otherwise be reused for that year forever
        need = min(datetime(end_year, 12, 20), now - pd.Timedelta(days=7))
        if df.index[0].year <= start_year and df.index[-1].tz_localize(None) >= pd.Timestamp(need):
            return df
    months = [(y, m) for y in range(start_year, end_year + 1) for m in range(1, 13) if (y, m) <= (now.year, now.month)]

    def safe(ym):
        try:
            return _month(pair, *ym)
        except RuntimeError:
            return None

    with ThreadPoolExecutor(3) as ex:
        got = list(ex.map(safe, months))
    for i, ym in enumerate(months):  # one more sequential try for months that failed
        if got[i] is None:
            got[i] = _month(pair, *ym)
    rows = [r for chunk in got for r in chunk]
    if not rows:
        raise RuntimeError(f"no data for {pair}; first URL: {URL.format(pair=pair, y=start_year, m=0)}")
    df = pd.DataFrame(rows, columns=["t", "open", "high", "low", "close"])
    df.index = pd.to_datetime(df.pop("t"), unit="s", utc=True)
    df = df[~df.index.duplicated()].sort_index()
    df.to_csv(path, compression="gzip")
    return df


# ---------------------------------------------------------------- live data (no yearly cache)
DAY_URL = "https://datafeed.dukascopy.com/datafeed/{pair}/{y}/{m:02d}/{d:02d}/BID_candles_min_1.bi5"
TICK_URL = "https://datafeed.dukascopy.com/datafeed/{pair}/{y}/{m:02d}/{d:02d}/{h:02d}h_ticks.bi5"


def _bars(data, start, p, size=24):
    """Decode 24-byte candle records (seconds from `start`) -> rows (t, o, h, l, c)."""
    rows = []
    for off in range(0, len(data) - size + 1, size):
        t, o, c, lo, hi, v = struct.unpack(">5if", data[off:off + size])
        if v > 0:
            rows.append((start + t, o / p, hi / p, lo / p, c / p))
    return rows


def _to_h1(rows):
    """Minute/tick rows (t, o, h, l, c) -> hourly rows."""
    out = {}
    for t, o, h, l, c in sorted(rows):
        k = int(t // 3600) * 3600
        if k not in out:
            out[k] = [k, o, h, l, c]
        else:
            b = out[k]
            b[2], b[3], b[4] = max(b[2], h), min(b[3], l), c
    return [tuple(v) for v in out.values()]


def _ticks(raw, start, p):
    """Decode 20-byte tick records (ms from hour start, ask, bid, ask vol, bid vol) -> bid rows."""
    rows = []
    for off in range(0, len(raw) - 19, 20):
        ms, _ask, bid, _av, _bv = struct.unpack(">3i2f", raw[off:off + 20])
        x = bid / p
        rows.append((start + ms / 1000, x, x, x, x))
    return rows


def _day(pair, y, m, d):
    raw = _get(DAY_URL.format(pair=pair, y=y, m=m - 1, d=d))
    if not raw:
        return []
    start = datetime(y, m, d, tzinfo=timezone.utc).timestamp()
    return _to_h1(_bars(lzma.decompress(raw), start, point(pair)))


def _hour(pair, y, m, d, h):
    raw = _get(TICK_URL.format(pair=pair, y=y, m=m - 1, d=d, h=h))
    if not raw:
        return []
    start = datetime(y, m, d, h, tzinfo=timezone.utc).timestamp()
    return _to_h1(_ticks(lzma.decompress(raw), start, point(pair)))


def _month_cached(pair, y, m):
    """A finished month never changes: keep it on disk (SLK_CACHE/months) so hourly runs stay light."""
    d = os.path.join(CACHE, "months")
    path = os.path.join(d, f"{pair}_{y}{m:02d}.csv")
    if os.path.exists(path):
        return [tuple(r) for r in pd.read_csv(path).itertuples(index=False)]
    rows = _month(pair, y, m)
    if rows:
        os.makedirs(d, exist_ok=True)
        pd.DataFrame(rows, columns=["t", "open", "high", "low", "close"]).to_csv(path, index=False)
    return rows


def recent(pair, days, now=None):
    """UTC-indexed hourly OHLC for the last `days` days up to the last finished hour.

    Finished months come from the monthly hour file (cached per month), the current month from daily
    minute files, and today (or a day whose minute file is not out yet) from hourly tick files.
    """
    now = now or datetime.now(timezone.utc)
    t0 = pd.Timestamp(now) - pd.Timedelta(days=days)
    today = pd.Timestamp(now).normalize()
    jobs = []
    for per in pd.period_range(pd.Period(year=t0.year, month=t0.month, freq="M"),
                               pd.Period(year=today.year, month=today.month, freq="M"), freq="M"):
        if (per.year, per.month) < (today.year, today.month):
            jobs.append(("month", per.year, per.month))
        else:
            for d in range(1, today.day):
                jobs.append(("day", per.year, per.month, d))
    for h in range(now.hour):
        jobs.append(("hour", today.year, today.month, today.day, h))

    def run(j):
        kind, *a = j
        if kind == "month":
            rows = _month_cached(pair, *a)
            if rows:
                return rows
            y, m = a  # month file not published yet: rebuild from its days
            last = (pd.Timestamp(year=y, month=m, day=1) + pd.offsets.MonthEnd(0)).day
            return [r for d in range(1, last + 1) for r in _day_or_hours(pair, y, m, d, now)]
        if kind == "day":
            return _day_or_hours(pair, *a, now)
        return _hour(pair, *a)

    with ThreadPoolExecutor(3) as ex:
        rows = [r for chunk in ex.map(run, jobs) for r in chunk]
    if not rows:
        raise RuntimeError(f"no recent data for {pair}")
    df = pd.DataFrame(rows, columns=["t", "open", "high", "low", "close"])
    df.index = pd.to_datetime(df.pop("t"), unit="s", utc=True)
    df = df[~df.index.duplicated(keep="last")].sort_index()
    return df[df.index >= t0]


def _day_or_hours(pair, y, m, d, now):
    rows = _day(pair, y, m, d)
    if rows or pd.Timestamp(year=y, month=m, day=d, tz="UTC") < pd.Timestamp(now) - pd.Timedelta(days=3):
        return rows
    return [r for h in range(24) for r in _hour(pair, y, m, d, h)]  # minute file not out yet
