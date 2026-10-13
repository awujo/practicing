"""Incremental H1 candle store (one compressed .npz per pair) kept between GitHub Actions runs by actions/cache.

Why not MySQL: the hourly job would pull ~25k rows per pair (700k rows for 28 pairs) from Aiven over the internet
every hour, and the free DB would hold half a million candle rows; restoring a ~15 MB cache archive takes seconds
and keeps the DB small. If the cache is ever evicted (7 days unused) the store is rebuilt by the next run or by
the "SLK candle backfill" workflow.

Same candles as slk.data.recent / slk.data.hourly (Dukascopy BID), each bar tagged with its source quality:
  3 = monthly hour file (final), 2 = daily minute file, 1 = hourly tick file (today / day file not out yet).
A better source replaces a worse one for the same month/day, exactly as `recent` prefers them, so the store's
window equals what `recent` would download - but each run only fetches what is new (normally one tick file).

    from slk import store
    store.update(pair, now, since)          # download only the missing parts; saves the file
    store.recent(pair, days, now)           # == data.recent(pair, days, now) from the store
    store.hourly(pair, start_year, end_year)  # == data.hourly (month files only) from the store
"""
import json
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd

from . import data

DIR = os.environ.get("SLK_STORE", os.path.join(os.environ.get("SLK_CACHE", "data"), "store"))
COLS = ("open", "high", "low", "close")
MONTH, DAY, TICK = 3, 2, 1
_locks = {}
_glock = threading.Lock()


def _lock(pair):
    with _glock:
        return _locks.setdefault(pair, threading.RLock())


def _utc(t=None):
    t = pd.Timestamp(t if t is not None else datetime.now(timezone.utc))
    return t.tz_localize("UTC") if t.tzinfo is None else t.tz_convert("UTC")


def fx_closed(t):
    """FX weekend (Fri 17:00 -> Sun 17:00 New York) for a UTC time."""
    ny = _utc(t).tz_convert("America/New_York")
    d, h = ny.dayofweek, ny.hour
    return (d == 4 and h >= 17) or d == 5 or (d == 6 and h < 17)


def _no_ticks(t):
    """Hours with no FX ticks for sure (weekend with 1 h / 2 h safety margins): not worth a tick download."""
    ny = _utc(t).tz_convert("America/New_York")
    d, h = ny.dayofweek, ny.hour
    return (d == 4 and h >= 18) or d == 5 or (d == 6 and h < 15)


class Pair:
    """Candles of one pair: arrays t (UTC seconds), open/high/low/close, q (source), plus finished months/days."""

    def __init__(self, pair, root=None):
        self.pair, self.root = pair, root or DIR
        self.path = os.path.join(self.root, f"{pair}.npz")
        self.df = pd.DataFrame({c: np.array([], float) for c in COLS} | {"q": np.array([], np.int8)},
                               index=pd.Index(np.array([], np.int64), name="t"))
        self.done_m, self.done_d, self.changed = set(), set(), False
        if os.path.exists(self.path):
            try:
                z = np.load(self.path, allow_pickle=False)
                self.df = pd.DataFrame({c: z[c] for c in COLS} | {"q": z["q"]}, index=pd.Index(z["t"], name="t"))
                meta = json.loads(str(z["meta"]))
                self.done_m, self.done_d = set(meta.get("m", [])), set(meta.get("d", []))
            except Exception as e:  # broken file: start again
                print(f"store {pair}: unreadable ({type(e).__name__}), rebuilding", flush=True)

    # ---------------------------------------------------------------- writing
    def put(self, rows, q, lo=None, hi=None):
        """Replace bars in [lo, hi) (UTC seconds) by rows (t, o, h, l, c); without a range only add new times."""
        if not rows and lo is None:
            return
        new = pd.DataFrame(rows, columns=["t", *COLS]) if rows else pd.DataFrame(columns=["t", *COLS])
        new["t"] = new["t"].astype(np.int64)
        new = new.drop_duplicates("t", keep="last").set_index("t").astype(float)
        new["q"] = np.int8(q)
        df = self.df
        if lo is not None:
            df = df[(df.index < lo) | (df.index >= hi)]
            new = new[(new.index >= lo) & (new.index < hi)]
        else:
            new = new[~new.index.isin(df.index)]
        self.df = pd.concat([df, new]).sort_index() if len(new) else df
        self.changed = True

    def save(self):
        if not self.changed:
            return False
        os.makedirs(self.root, exist_ok=True)
        tmp = self.path + ".tmp.npz"
        d = self.df
        np.savez_compressed(tmp, t=d.index.to_numpy(np.int64), q=d["q"].to_numpy(np.int8),
                            meta=json.dumps({"m": sorted(self.done_m), "d": sorted(self.done_d)}),
                            **{c: d[c].to_numpy(float) for c in COLS})
        os.replace(tmp, self.path)
        self.changed = False
        return True

    # ---------------------------------------------------------------- reading
    def frame(self, lo=None, min_q=0):
        d = self.df
        if lo is not None:
            d = d[d.index >= lo]
        if min_q:
            d = d[d["q"] >= min_q]
        out = d[list(COLS)].copy()
        out.index = pd.to_datetime(out.index.to_numpy(float), unit="s", utc=True)  # same dtype as data.recent
        out.index.name = "t"  # as data.recent / data.hourly
        return out

    def last_time(self):
        return None if self.df.empty else int(self.df.index[-1])

    # ---------------------------------------------------------------- downloading
    def ensure_month(self, y, m):
        """Final month file into the store (once). True when the month is in the store."""
        key = f"{y}-{m:02d}"
        if key in self.done_m:
            return True
        rows = data._month(self.pair, y, m)
        if not rows:
            return False  # not published yet (or no data)
        lo = int(datetime(y, m, 1, tzinfo=timezone.utc).timestamp())
        hi = int((pd.Timestamp(lo, unit="s", tz="UTC") + pd.offsets.MonthBegin(1)).timestamp())
        self.put(rows, MONTH, lo, hi)
        self.done_m.add(key)
        self.done_d = {d for d in self.done_d if not d.startswith(key)}
        return True

    def _hours(self, day, now, hours=range(24)):
        """Tick files of the given hours of `day` (a UTC midnight Timestamp) that are closed, possibly traded
        and not in the store yet."""
        have = set(self.df.index[self.df.index >= int(day.timestamp())][:30].tolist())
        for h in hours:
            t = day + pd.Timedelta(hours=h)
            if t + pd.Timedelta(hours=1) > now or int(t.timestamp()) in have or _no_ticks(t):
                continue
            self.put(data._hour(self.pair, t.year, t.month, t.day, h), TICK)

    def ensure_day(self, day, now):
        """Day minute file (once it is out); within 3 days of now fall back to hourly tick files, as recent()."""
        key = f"{day:%Y-%m-%d}"
        if key in self.done_d or key[:7] in self.done_m:
            return
        rows = data._day(self.pair, day.year, day.month, day.day)
        lo = int(day.timestamp())
        if rows:
            self.put(rows, DAY, lo, lo + 86400)
            self.done_d.add(key)
        elif day < now - pd.Timedelta(days=3):
            self.done_d.add(key)  # no data that day (weekend / holiday): recent() returns nothing for it either
            self.put([], DAY, lo, lo + 86400)
        else:
            self._hours(day, now)

    def update(self, now, since):
        """Bring the store up to the last closed hour before `now` for times >= `since` (recent()'s rules)."""
        now, since = _utc(now), _utc(since)
        today = now.normalize()
        days = []
        for per in pd.period_range(pd.Period(year=since.year, month=since.month, freq="M"),
                                   pd.Period(year=today.year, month=today.month, freq="M"), freq="M"):
            if (per.year, per.month) < (today.year, today.month):
                if self.ensure_month(per.year, per.month):
                    continue
                last = per.days_in_month  # month file not out yet: its days
                days += [pd.Timestamp(per.year, per.month, d, tz="UTC") for d in range(1, last + 1)]
            else:
                days += [pd.Timestamp(per.year, per.month, d, tz="UTC") for d in range(1, today.day)]
        for d in days:
            self.ensure_day(d, now)
        self._hours(today, now, range(now.hour))
        return self


def load(pair, root=None):
    return Pair(pair, root)


def update(pair, now=None, since=None, days=None, root=None):
    """Download what is missing for one pair and save. Returns the Pair."""
    now = _utc(now)
    since = _utc(since) if since is not None else now - pd.Timedelta(days=days or 30)
    with _lock(pair):
        p = Pair(pair, root).update(now, since)
        p.save()
    return p


def update_all(pairs, now=None, days=30, threads=8, root=None):
    """update() for many pairs in parallel threads (downloads). Returns {pair: error text} for failures."""
    errors = {}

    def one(pair):
        try:
            update(pair, now, days=days, root=root)
        except Exception as e:
            errors[pair] = f"{type(e).__name__}: {e}"

    with ThreadPoolExecutor(threads) as ex:
        list(ex.map(one, pairs))
    return errors


def recent(pair, days, now=None, root=None):
    """Store version of data.recent: hourly OHLC from now - days up to the last stored (closed) hour."""
    now = _utc(now)
    t0 = now - pd.Timedelta(days=days)
    p = Pair(pair, root)
    df = p.frame(lo=int(np.ceil(t0.timestamp())))
    df = df[df.index + pd.Timedelta(hours=1) <= now]
    if df.empty:
        raise RuntimeError(f"no stored candles for {pair} (run the backfill workflow)")
    return df


def hourly(pair, start_year, end_year, root=None, now=None):
    """Store version of data.hourly: month-file candles of [start_year, end_year], downloading missing months."""
    now = _utc(now)
    with _lock(pair):
        p = Pair(pair, root)
        for y in range(start_year, end_year + 1):
            for m in range(1, 13):
                if (y, m) < (now.year, now.month):
                    try:
                        p.ensure_month(y, m)
                    except RuntimeError:
                        p.ensure_month(y, m)  # one more try, like data.hourly
        p.save()
    df = p.frame(min_q=MONTH)
    df = df[(df.index.year >= start_year) & (df.index.year <= end_year)]
    if df.empty:
        raise RuntimeError(f"no data for {pair}")
    return df


def months_all(pairs, start_year, end_year, threads=3, root=None, now=None):
    """Download missing month files for many pairs in parallel threads (before a backtest)."""
    def one(p):
        try:
            hourly(p, start_year, end_year, root, now)
        except RuntimeError as e:
            print(f"{p}: {e}", flush=True)

    with ThreadPoolExecutor(threads) as ex:
        list(ex.map(one, pairs))


def backfill(pairs, start_year, now=None, threads=3, root=None):
    """All month files from start_year plus the current month for many pairs. Returns {pair: error}."""
    now = _utc(now)
    since = pd.Timestamp(start_year, 1, 1, tz="UTC")
    return update_all(pairs, now, days=(now - since).days + 1, threads=threads, root=root)


def main(argv=None):
    import argparse
    import sys
    from .backtest import PAIRS
    ap = argparse.ArgumentParser(description="Fill the candle store (python -m slk.store --start 2018)")
    ap.add_argument("--pairs", default="")
    ap.add_argument("--start", type=int, default=datetime.now(timezone.utc).year - 3)
    ap.add_argument("--threads", type=int, default=3)  # Dukascopy answers 503 when hit harder
    a = ap.parse_args(argv)
    pairs = [x.strip().upper() for x in a.pairs.split(",") if x.strip()] or list(PAIRS)
    t = datetime.now()
    err = backfill(pairs, a.start, threads=a.threads)
    for p in pairs:
        s = Pair(p)
        print(f"{p}: {len(s.df)} bars, months {len(s.done_m)}, last "
              f"{pd.Timestamp(s.last_time(), unit='s') if s.last_time() else '-'}" + (f"  ERROR {err[p]}" if p in err else ""))
    print(f"backfill {len(pairs) - len(err)}/{len(pairs)} pairs in {(datetime.now() - t).total_seconds():.0f}s")
    return 1 if err else 0


if __name__ == "__main__":
    raise SystemExit(main())
