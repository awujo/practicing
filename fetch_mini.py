"""One-off: fetch a bounded candle set for EURUSD/GBPJPY/GBPNZD into the cache.

This environment has no access to the repo's GitHub Releases (no remote is
configured), so the normal `data-latest` download path is unavailable and
dukascopy-python must fetch directly. History is capped at 2015-01-01 to
keep the download small; M/W are fetched via resampling from D because
dukascopy-python's native month/week paths are flakier.
"""
import sys, time
from datetime import datetime, timezone

sys.path.insert(0, "/workspace")

import pandas as pd
import dukascopy_python
from dukascopy_python import instruments as di

from backtest.data_pipeline import cache
from backtest.data_pipeline.instruments import DUKASCOPY_INSTRUMENTS

START = datetime(2015, 1, 1, tzinfo=timezone.utc)
END = datetime(2026, 9, 29, tzinfo=timezone.utc)

INTERVALS = {
    "H1": dukascopy_python.INTERVAL_HOUR_1,
    "H4": dukascopy_python.INTERVAL_HOUR_4,
    "D": dukascopy_python.INTERVAL_DAY_1,
}

for sym in ["EURUSD", "GBPJPY", "GBPNZD"]:
    inst = getattr(di, DUKASCOPY_INSTRUMENTS[sym])
    for gran, interval in INTERVALS.items():
        t0 = time.time()
        df = dukascopy_python.fetch(instrument=inst, interval=interval,
                                    offer_side=dukascopy_python.OFFER_SIDE_BID,
                                    start=START, end=END)
        df = df.reset_index()
        rows = []
        for _, r in df.iterrows():
            ts = pd.Timestamp(r["timestamp"]).tz_convert("UTC")
            rows.append({"time": ts.strftime("%Y-%m-%dT%H:%M:%SZ"),
                         "open": float(r["open"]), "high": float(r["high"]),
                         "low": float(r["low"]), "close": float(r["close"]),
                         "volume": float(r["volume"])})
        added = cache.append("dukascopy", sym, gran, rows)
        print(f"{sym} {gran}: {len(rows)} fetched, {added} cached ({time.time()-t0:.1f}s)", flush=True)
        # W derived from D locally (W-MON anchor, same rule as resample.py)
        if gran == "D":
            import pandas as pd_mod
            ddf = pd_mod.DataFrame(rows)
            ddf["time"] = pd_mod.to_datetime(ddf["time"], utc=True)
            ddf = ddf.set_index("time")
            w = ddf.resample("W-MON", origin="start").agg(
                {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}
            ).dropna().reset_index()
            wrows = [{"time": t.strftime("%Y-%m-%dT%H:%M:%SZ"), "open": o, "high": h,
                      "low": l, "close": c, "volume": v}
                     for t, o, h, l, c, v in zip(w["time"], w["open"], w["high"], w["low"], w["close"], w["volume"])]
            added_w = cache.append("dukascopy", sym, "W", wrows)
            print(f"{sym} W (resampled): {len(wrows)} built, {added_w} cached", flush=True)

import pandas as pd  # used inside loop above via pd.Timestamp
print("DONE")
