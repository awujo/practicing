"""Frozen H1 input checks with an explicit FX weekend calendar.

This detects missing expected hours, not broker-specific holidays. A missing
holiday is conservatively unresolved until its trading calendar is supplied.
"""
import hashlib
from pathlib import Path

import pandas as pd

from .price_action import validated_bars, _time
from . import candles


def expected_hours(start, end):
    start, end = _time(start, "start"), _time(end, "end")
    if start != start.floor("h") or end != end.floor("h") or end < start:
        raise ValueError("coverage bounds must be ordered UTC hour boundaries")
    hours = pd.date_range(start, end, freq="h", inclusive="left")
    ny = hours.tz_convert("America/New_York")
    closed = ((ny.dayofweek == 4) & (ny.hour >= 17)) | (ny.dayofweek == 5) | ((ny.dayofweek == 6) & (ny.hour < 17))
    return hours[~closed]


def validate_hourly(frame, *, as_of):
    if not isinstance(frame.index, pd.DatetimeIndex) or frame.index.tz is None:
        raise ValueError("H1 input requires a timezone-aware start index")
    if any(frame.index.tz_convert("UTC") != frame.index.tz_convert("UTC").floor("h")):
        raise ValueError("H1 candle starts must be UTC hour aligned")
    copy = frame.copy()
    copy.index = copy.index.tz_convert("UTC")
    checked = validated_bars(copy.assign(end=copy.index + pd.Timedelta(hours=1)), as_of=as_of)
    checked.index = copy.index
    checked.index.name = "time"
    return checked


def coverage(frame, start, end):
    wanted = expected_hours(start, end)
    missing = wanted.difference(frame.index)
    return {"status": "COMPLETE" if not len(missing) else "INCOMPLETE",
            "start": _time(start, "start").isoformat(), "end": _time(end, "end").isoformat(),
            "calendar": "FX Friday17:00-Sunday17:00 America/New_York weekend; holidays not assumed",
            "expected_hours": len(wanted), "present_hours": len(wanted) - len(missing),
            "missing_hours": len(missing), "missing_first_100": [t.isoformat() for t in missing[:100]]}


def load_csv(path, *, as_of):
    path = Path(path)
    frame = pd.read_csv(path, index_col=0, parse_dates=True)
    # Validate original order/geometry before any historical prefix is selected.
    checked = validate_hourly(frame, as_of=max(_time(as_of, "as_of"), frame.index.max() + pd.Timedelta(hours=1)))
    clock = _time(as_of, "as_of")
    return checked[checked.index + pd.Timedelta(hours=1) <= clock], hashlib.sha256(path.read_bytes()).hexdigest()


def completed_from_complete_history(frame, tf, *, as_of):
    """Clock-completed bars with an incomplete leading aggregate removed.

    Caller must FIRST prove coverage of the entire requested H1 range. That
    proof cannot cover opening hours before history_start; check those here.
    Subsequent bars lie within the already-proven range. Closed FX weekend
    hours are not mistaken for absent candle data.
    """
    bars = candles.completed(frame, tf, as_of)
    diagnostic = {"dropped_partial_leading": False, "opening_missing_hours": 0}
    if bars.empty:
        return bars, diagnostic
    observed = _time(bars.iloc[0]["start"], "first observed start")
    if tf == "H1":
        nominal = observed.floor("h")
    else:
        key = candles._key(pd.DatetimeIndex([observed]), tf)[0]
        nominal = (key - pd.Timedelta(hours=7)).tz_localize("America/New_York", ambiguous=True).tz_convert("UTC")
    missing = expected_hours(nominal, bars.iloc[0]["end"]).difference(frame.index)
    diagnostic.update(nominal_first_start=nominal.isoformat(), observed_first_start=observed.isoformat(),
                      opening_missing_hours=len(missing))
    if len(missing):
        bars = bars.iloc[1:].reset_index(drop=True)
        diagnostic["dropped_partial_leading"] = True
    return bars, diagnostic
