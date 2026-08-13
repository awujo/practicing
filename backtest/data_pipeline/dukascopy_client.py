"""
Thin wrapper around the `dukascopy-python` package's OHLCV fetch.

That package already handles the hard parts (bi5 tick file download,
decompression, per-instrument price-decimal scaling, resampling into
candles) -- this module just adapts its output into our cache schema
(time, open, high, low, close, volume) and instrument/granularity naming.
"""

from datetime import datetime, timezone

import dukascopy_python
from dukascopy_python import instruments as dukascopy_instruments

from .instruments import DUKASCOPY_INSTRUMENTS, DUKASCOPY_GRANULARITY_TO_INTERVAL

# Bid side matches the default candle convention on most retail charting
# platforms (TradingView included), which is what STRATEGY.md was taught
# against.
DEFAULT_OFFER_SIDE = dukascopy_python.OFFER_SIDE_BID

# Dukascopy's earliest available history varies a lot by instrument (forex
# majors go back to the early 2000s; CFDs/crypto much less). No harm in
# asking for more than exists -- the package just returns what's there.
FULL_HISTORY_START = datetime(2003, 1, 1, tzinfo=timezone.utc)


def fetch_candles(internal_symbol: str, granularity: str, since: str | None = None,
                   until: datetime | None = None) -> list[dict]:
    """
    Fetch candles for `internal_symbol` (see instruments.py) at `granularity`
    (our code, e.g. "D", "H4", "M15"), from `since` (exclusive, ISO-8601
    string or None for full available history) up to `until` (default: now).

    Returns a list of dicts with keys: time, open, high, low, close, volume.
    """
    if internal_symbol not in DUKASCOPY_INSTRUMENTS:
        raise KeyError(f"{internal_symbol!r} not in DUKASCOPY_INSTRUMENTS")
    if granularity not in DUKASCOPY_GRANULARITY_TO_INTERVAL:
        raise KeyError(
            f"Dukascopy has no native {granularity!r} granularity "
            f"(see instruments.py's module docstring for the H2/H3/M45 gap)"
        )

    instrument = getattr(dukascopy_instruments, DUKASCOPY_INSTRUMENTS[internal_symbol])
    interval = getattr(dukascopy_python, DUKASCOPY_GRANULARITY_TO_INTERVAL[granularity])

    start = (
        datetime.fromisoformat(since.replace("Z", "+00:00")) if since else FULL_HISTORY_START
    )
    end = until or datetime.now(timezone.utc)

    df = dukascopy_python.fetch(
        instrument=instrument,
        interval=interval,
        offer_side=DEFAULT_OFFER_SIDE,
        start=start,
        end=end,
    )

    if df.empty:
        return []

    df = df.reset_index()  # "timestamp" moves from index back to a column
    return [
        {
            "time": row.timestamp.isoformat().replace("+00:00", "Z"),
            "open": float(row.open),
            "high": float(row.high),
            "low": float(row.low),
            "close": float(row.close),
            "volume": float(row.volume),
        }
        for row in df.itertuples(index=False)
    ]
