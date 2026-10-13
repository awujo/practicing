"""Hourly candles from Dukascopy's public datafeed, cached as CSV.

Files: https://datafeed.dukascopy.com/datafeed/<PAIR>/<YYYY>/<MM-1>/BID_candles_hour_1.bi5
Each record (24 bytes, big-endian): seconds-from-month-start, open, close, low, high (int32
scaled by point), volume (float32). Times are UTC.
"""
import io
import lzma
import os
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


def _get(url, tries=4):
    for k in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.read()
        except Exception as e:  # network hiccup or 404 for future months
            if getattr(e, "code", None) == 404:
                return b""
            time.sleep(2 ** k)
    raise RuntimeError(f"download failed: {url}")


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
    if os.path.exists(path):
        df = pd.read_csv(path, index_col=0, parse_dates=True)
        if df.index[0].year <= start_year and df.index[-1].year >= min(end_year, datetime.utcnow().year):
            return df
    now = datetime.utcnow()
    months = [(y, m) for y in range(start_year, end_year + 1) for m in range(1, 13) if (y, m) <= (now.year, now.month)]
    with ThreadPoolExecutor(8) as ex:
        rows = [r for chunk in ex.map(lambda ym: _month(pair, *ym), months) for r in chunk]
    if not rows:
        raise RuntimeError(f"no data for {pair}; first URL: {URL.format(pair=pair, y=start_year, m=0)}")
    df = pd.DataFrame(rows, columns=["t", "open", "high", "low", "close"])
    df.index = pd.to_datetime(df.pop("t"), unit="s", utc=True)
    df = df[~df.index.duplicated()].sort_index()
    df.to_csv(path, compression="gzip")
    return df
