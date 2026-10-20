"""Incremental H1 candle store (one compressed .npz per pair) kept between GitHub Actions runs by actions/cache.

Why not MySQL: the hourly job would pull ~25k rows per pair (700k rows for 28 pairs) from Aiven over the internet
every hour, and the free DB would hold half a million candle rows; restoring a ~15 MB cache archive takes seconds
and keeps the DB small. If the cache is ever evicted (7 days unused) the store is rebuilt by the next run or by
the "SLK candle backfill" workflow.

Sources (one per file, recorded in the file's meta `src`; a file of another source is rebuilt, never mixed):
  ctrader    PRIMARY. IC Markets cTrader Open API H1 trendbars (bid, UTC, hour-aligned). ONE connection per job
             for all pairs (`get_feed`), requests as wide as the API allows, <= 4 per second. Completed months are
             final (q=3, MONTH), the current month is refreshed every run (q=2, CUR: last few days re-fetched).
  dukascopy  FALLBACK (no cTrader secrets, or cTrader failed). Same candles as bishop.data.recent / bishop.data.hourly
             (Dukascopy BID), tagged 3 = monthly hour file (final), 2 = daily minute file, 1 = hourly tick file.
             A better source replaces a worse one for the same month/day, exactly as `recent` prefers them.
When cTrader fails on a pair whose file is already a cTrader file, the missing recent hours come from Dukascopy
into a separate overlay file (`<store>-fallback/`, not cached) that `recent()` appends after the last cTrader bar
for this run only; the cTrader file is never touched by Dukascopy bars.

    from bishop import store
    store.update(pair, now, since)          # download only the missing parts; saves the file
    store.update_all(pairs, now, days)      # many pairs, one cTrader connection, Dukascopy fallback per pair
    store.recent(pair, days, now)           # engine candles up to the last closed hour (+ fallback overlay)
    store.hourly(pair, start_year, end_year)  # final months only (backtest)
"""
import atexit
import json
import os
import re
import shutil
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd

from . import data, instruments

DIR = os.environ.get("BISHOP_STORE", os.path.join(os.environ.get("BISHOP_CACHE", "data"), "store"))
COLS = ("open", "high", "low", "close")
MONTH, DAY, TICK = 3, 2, 1
CUR = DAY  # cTrader bars of the current (unfinished) month: refreshed every run, replaced once the month is final
SOURCES = ("ctrader", "dukascopy")
REFRESH = pd.Timedelta(days=3)  # cTrader: the last few stored days of the current month are fetched again
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


def default_source():
    """`BISHOP_SOURCE` (ctrader | dukascopy) if set, else ctrader when the cTrader secrets are present."""
    s = os.environ.get("BISHOP_SOURCE", "").strip().lower()
    if s in SOURCES:
        return s
    env = os.environ.get
    ok = env("CTRADER_CLIENT_ID") and env("CTRADER_CLIENT_SECRET") and (env("CTRADER_ACCESS_TOKEN") or env("DATABASE_URL"))
    return "ctrader" if ok else "dukascopy"


def _safe(e, limit=300):
    """Error text without secrets: values of CTRADER_* / DATABASE_* / TELEGRAM_* env vars and long digit runs
    (account numbers) are masked; cut at `limit` characters."""
    text = f"{type(e).__name__}: {e}"
    for k, v in os.environ.items():
        if k.startswith(("CTRADER_", "DATABASE_", "TELEGRAM_")) and v and len(v.strip()) >= 8:
            text = text.replace(v.strip(), "***")
    return re.sub(r"\d{6,}", "#", text)[:limit]


def warn(msg):
    """GitHub annotation (readable through the API; the logs are not) + plain log line."""
    print(f"::warning title=Candles::{msg}", flush=True)


def _closed_mask(t):
    """Vectorised fx_closed for bar open times t (UTC seconds)."""
    ny = pd.to_datetime(np.asarray(t, dtype=np.int64), unit="s", utc=True).tz_convert("America/New_York")
    d, h = ny.dayofweek.to_numpy(), ny.hour.to_numpy()
    return ((d == 4) & (h >= 17)) | (d == 5) | ((d == 6) & (h < 17))


def clean_ctrader(rows, lo=None, hi=None):
    """cTrader trendbar rows (t, o, h, l, c, volume) -> store rows (t, o, h, l, c): only hour-aligned bars with
    ticks (volume > 0) outside the FX weekend (Fri 17:00 -> Sun 17:00 New York, as Dukascopy has no bars there),
    open time in [lo, hi)."""
    if not rows:
        return []
    a = np.array([r[:6] for r in rows], dtype=float)
    keep = (a[:, 5] > 0) & (a[:, 0] % 3600 == 0) & ~_closed_mask(a[:, 0])
    if lo is not None:
        keep &= a[:, 0] >= lo
    if hi is not None:
        keep &= a[:, 0] < hi
    return [tuple(r[:5]) for r in a[keep].tolist()]


class CTraderFeed:
    """H1 bars from one CTraderClient connection (shared by all pairs of a job). Reconnects once if the
    connection drops."""

    def __init__(self, client, factory=None):
        self.c, self.factory = client, factory

    @property
    def max_span(self):
        return self.c.max_span("H1")

    def prefetch(self, pairs):
        """One symbol-list request for all pairs instead of two per pair."""
        self.c.get_symbols(list(pairs))

    def info(self, pair):
        """cTrader symbol info of the pair kept in the file meta: {symbol_id, name, digits, pip_position} (pip size
        and price decimals for bishop/instruments)."""
        if not hasattr(self.c, "symbol"):
            return None
        i = self.c.symbol(pair)
        return {k: i.get(k) for k in ("symbol_id", "name", "digits", "pip_position")}

    def bars(self, pair, lo, hi):
        """Clean H1 rows (t, o, h, l, c) with open time in [lo, hi) (UTC seconds)."""
        try:
            raw = self.c.trendbar_rows(pair, "H1", int(lo), int(hi))
        except (ConnectionError, TimeoutError, OSError):
            if self.factory is None:
                raise
            self.close()
            self.c = self.factory()
            raw = self.c.trendbar_rows(pair, "H1", int(lo), int(hi))
        return clean_ctrader(raw, lo, hi)

    def close(self):
        try:
            self.c.close()
        except Exception:
            pass


_FEED = {}


def _open_client():
    from ctrader import tokens
    from ctrader.client import CTraderClient
    c = CTraderClient(settings=tokens.default_settings(strict=True))  # refreshed tokens go to the DB settings
    try:
        c.__enter__()  # connect + app auth + account auth (+ token refresh)
    except BaseException:
        c.close()
        raise
    return c


def get_feed():
    """The job's one cTrader connection (opened on first use, closed at exit). A failure is remembered, so a job
    tries once and then uses the Dukascopy fallback. Worker processes (backtest pool) never open their own:
    only the process that opened the first feed may (env BISHOP_FEED_OWNER), so tokens are refreshed by one
    process only."""
    pid = os.getpid()
    owner = os.environ.setdefault("BISHOP_FEED_OWNER", str(pid))
    if owner != str(pid):
        raise RuntimeError("cTrader feed belongs to the parent process")
    with _glock:
        st = _FEED.get(pid)
        if st is None:
            try:
                st = ("ok", CTraderFeed(_open_client(), _open_client))
                atexit.register(close_feed)
            except Exception as e:
                st = ("err", _safe(e))
            _FEED[pid] = st
    if st[0] == "err":
        raise RuntimeError(f"cTrader unavailable: {st[1]}")
    return st[1]


def close_feed():
    st = _FEED.pop(os.getpid(), None)
    if st and st[0] == "ok":
        st[1].close()


def _fb_root(root=None):
    return (root or DIR).rstrip("/\\") + "-fallback"


class Pair:
    """Candles of one pair: arrays t (UTC seconds), open/high/low/close, q (source), plus finished months/days."""

    def __init__(self, pair, root=None, source=None):
        """Load the pair's file. `source` given (ctrader | dukascopy) = this object will download from it: a file
        of another source is dropped and rebuilt (sources are never mixed in one file). Without `source` the file
        is only read, whatever its source (`self.src`, None for an empty store)."""
        self.pair, self.root = pair, root or DIR
        self.path = os.path.join(self.root, f"{pair}.npz")
        self._empty()
        self.src = None
        self.sym = None  # cTrader symbol info (meta "sym"): pip_position / digits -> bishop.instruments.register
        self.changed = False
        self.failed = []  # month files that could not be downloaded this run (retried next run)
        if os.path.exists(self.path):
            try:
                z = np.load(self.path, allow_pickle=False)
                self.df = pd.DataFrame({c: z[c] for c in COLS} | {"q": z["q"]}, index=pd.Index(z["t"], name="t"))
                meta = json.loads(str(z["meta"]))
                self.done_m, self.done_d = set(meta.get("m", [])), set(meta.get("d", []))
                self.src = meta.get("src") or ("dukascopy" if len(self.df) else None)  # v2 files: Dukascopy
                self.sym = meta.get("sym") if self.src == "ctrader" else None
                if self.sym:
                    instruments.register(pair, self.sym.get("pip_position"), self.sym.get("digits"))
            except Exception as e:  # broken file: start again
                print(f"store {pair}: unreadable ({type(e).__name__}), rebuilding", flush=True)
                self._empty()
        if source is not None:
            self.use_source(source)

    def use_source(self, source):
        """This object will download from `source`: a file of another source is dropped (rebuilt)."""
        if source not in SOURCES:
            raise ValueError(f"unknown candle source {source!r}")
        if self.src not in (None, source):
            print(f"store {self.pair}: file source {self.src} != {source}, rebuilding", flush=True)
            self._empty()
            self.sym = None
            self.changed = True
        self.src = source
        return self

    def missing_months(self, months):
        return sorted({(y, m) for y, m in months if f"{y}-{m:02d}" not in self.done_m})

    def _empty(self):
        self.df = pd.DataFrame({c: np.array([], float) for c in COLS} | {"q": np.array([], np.int8)},
                               index=pd.Index(np.array([], np.int64), name="t"))
        self.done_m, self.done_d = set(), set()

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
                            meta=json.dumps({"m": sorted(self.done_m), "d": sorted(self.done_d), "src": self.src,
                                             **({"sym": self.sym} if self.sym else {})}),
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

    def update(self, now, since, day_floor=None):
        """Dukascopy: bring the store up to the last closed hour before `now` for times >= `since` (recent()'s
        rules). `day_floor`: skip day files before this day (fallback overlay: only the recent gap)."""
        now, since = _utc(now), _utc(since)
        today = now.normalize()
        days = []
        for per in pd.period_range(pd.Period(year=since.year, month=since.month, freq="M"),
                                   pd.Period(year=today.year, month=today.month, freq="M"), freq="M"):
            if (per.year, per.month) < (today.year, today.month):
                try:
                    if self.ensure_month(per.year, per.month):
                        if self.changed and len(self.done_m) % 6 == 0:
                            self.save()  # keep progress if the run is cancelled
                        continue
                except RuntimeError as e:  # Dukascopy throttling: skip the month, keep the rest, retry next run
                    self.failed.append(f"{per.year}-{per.month:02d}")
                    print(f"{self.pair} {per.year}-{per.month:02d}: {e}", flush=True)
                    continue
                last = per.days_in_month  # month file not out yet: its days
                days += [pd.Timestamp(per.year, per.month, d, tz="UTC") for d in range(1, last + 1)]
            else:
                days += [pd.Timestamp(per.year, per.month, d, tz="UTC") for d in range(1, today.day)]
        for d in days:
            if day_floor is None or d >= day_floor:
                self.ensure_day(d, now)
        self._hours(today, now, range(now.hour))
        return self

    # ---------------------------------------------------------------- cTrader
    def ctrader_months(self, feed, months):
        """Completed months [(y, m)] not final yet -> fetched as few, as wide requests as the API allows
        (consecutive missing months grouped up to feed.max_span) and stored as final (MONTH). Saved after each
        request so a cancelled job keeps its progress."""
        todo = self.missing_months(months)
        span = feed.max_span
        groups = []
        for y, m in todo:
            lo = pd.Timestamp(y, m, 1, tz="UTC")
            hi = lo + pd.offsets.MonthBegin(1)
            g = groups[-1] if groups else None
            if g and g[1] == lo and (hi - g[0]).total_seconds() <= span:
                g[1] = hi
                g[2].append(f"{y}-{m:02d}")
            else:
                groups.append([lo, hi, [f"{y}-{m:02d}"]])
        for lo, hi, keys in groups:
            a, b = int(lo.timestamp()), int(hi.timestamp())
            self.put(feed.bars(self.pair, a, b), MONTH, a, b)
            self.done_m.update(keys)
            self.save()

    def ctrader_current(self, feed, now):
        """Current month up to the last closed hour: from the month start, or the last stored bar minus REFRESH
        (a few days, so a bar stored while still forming elsewhere is replaced). Stored as CUR (refreshable)."""
        now = _utc(now)
        cur = pd.Timestamp(now.year, now.month, 1, tz="UTC")
        hi = int(now.floor("h").timestamp())  # bars opening before this hour have closed
        lo = int(cur.timestamp())
        last = self.last_time()
        if last is not None and last >= lo:
            lo = max(lo, int((pd.Timestamp(last, unit="s", tz="UTC") - REFRESH).floor("h").timestamp()))
        if lo >= hi:
            return
        rows = feed.bars(self.pair, lo, hi)
        if rows:  # an empty reply (weekend) keeps what is stored
            self.put(rows, CUR, lo, hi)

    def update_ctrader(self, feed, now, since):
        """cTrader: completed months from `since` that are not final yet, then the current month's new bars."""
        now, since = _utc(now), _utc(since)
        info = getattr(feed, "info", None)
        if info is not None:
            try:
                sym = info(self.pair)
            except Exception as e:  # symbol info is a nice-to-have (pip size); the bars are what matters
                print(f"{self.pair}: cTrader symbol info failed ({_safe(e)})", flush=True)
                sym = None
            if sym and sym != self.sym:
                self.sym, self.changed = sym, True
                instruments.register(self.pair, sym.get("pip_position"), sym.get("digits"))
        months = [(p.year, p.month) for p in pd.period_range(pd.Period(year=since.year, month=since.month, freq="M"),
                                                             pd.Period(year=now.year, month=now.month, freq="M"),
                                                             freq="M")
                  if (p.year, p.month) < (now.year, now.month)]
        self.ctrader_months(feed, months)
        self.ctrader_current(feed, now)
        return self


def load(pair, root=None):
    return Pair(pair, root)


def _overlay_frame(pair, root, after):
    """Dukascopy fallback bars (overlay file of this run) after the last cTrader bar `after`."""
    path = os.path.join(_fb_root(root), f"{pair}.npz")
    if not os.path.exists(path):
        return None
    df = Pair(pair, _fb_root(root)).frame(lo=None if after is None else after + 1)
    return df if len(df) else None


def _drop_overlay(pair, root):
    try:
        os.remove(os.path.join(_fb_root(root), f"{pair}.npz"))
    except OSError:
        pass


def update(pair, now=None, since=None, days=None, root=None, source=None, feed=None):
    """Download what is missing for one pair and save. Returns the Pair.
    source ctrader: into the pair file (a Dukascopy file is rebuilt). source dukascopy: into the pair file, unless
    it is a cTrader file: then only the gap after its last bar, into the fallback overlay (never mixed)."""
    now = _utc(now)
    since = _utc(since) if since is not None else now - pd.Timedelta(days=days or 30)
    src = source or default_source()
    with _lock(pair):
        if src == "ctrader":
            feed = feed or get_feed()  # before touching the file: no connection = file left as it is
            p = Pair(pair, root, source="ctrader")
            try:
                p.update_ctrader(feed, now, since)
            finally:
                p.save()
            _drop_overlay(pair, root)
            return p
        cur = Pair(pair, root)
        if cur.src == "ctrader" and len(cur.df):
            last = pd.Timestamp(cur.last_time() + 3600, unit="s", tz="UTC")
            gap = max(since, last)
            ov = Pair(pair, _fb_root(root), source="dukascopy")
            try:
                ov.update(now, gap, day_floor=gap.normalize())
            finally:
                ov.save()
            if ov.failed:
                raise RuntimeError(f"{len(ov.failed)} month file(s) not downloaded, first {ov.failed[0]}")
            return cur
        p = Pair(pair, root, source="dukascopy")
        try:
            p.update(now, since)
        finally:
            p.save()  # whatever was downloaded stays, even when a later download fails
    if p.failed:
        raise RuntimeError(f"{len(p.failed)} month file(s) not downloaded, first {p.failed[0]} (kept the rest)")
    return p


def _ctrader_each(pairs, fn):
    """fn(pair, feed) for every pair over the job's one cTrader connection, sequentially (the API allows ~5
    history requests per second per connection, so threads would not help). Returns {pair: error text}."""
    try:
        feed = get_feed()
        feed.prefetch(pairs)
    except Exception as e:
        return {p: f"cTrader: {_safe(e)}" for p in pairs}
    failed = {}
    for p in pairs:
        try:
            fn(p, feed)
        except Exception as e:
            failed[p] = f"cTrader: {_safe(e, 700)}"
            print(f"{p}: {failed[p]}", flush=True)
    return failed


def _fallback_note(failed):
    first = next(iter(failed.values()))
    warn(f"cTrader candles failed for {len(failed)} pair(s) ({', '.join(list(failed)[:6])}"
         f"{' ...' if len(failed) > 6 else ''}): {first}. Using Dukascopy for them.")


def update_all(pairs, now=None, days=30, threads=8, root=None, source=None):
    """update() for many pairs. cTrader: one connection, pairs in turn; pairs that fail (or all, when cTrader
    cannot connect) fall back to Dukascopy (threads). Returns {pair: error text} for pairs that got nothing."""
    pairs = list(pairs)
    src = source or default_source()
    pre = {}
    if src == "ctrader":
        pre = _ctrader_each(pairs, lambda p, feed: update(p, now, days=days, root=root, source="ctrader", feed=feed))
        if not pre:
            return {}
        # An unavailable broker symbol cannot be repaired by rebuilding years of
        # another feed during an hourly run. Report it and continue the other pairs.
        unavailable = {p: e for p, e in pre.items() if "not found on this account" in e}
        pre = {p: e for p, e in pre.items() if p not in unavailable}
        if not pre:
            return unavailable
        _fallback_note(pre)
        pairs = list(pre)
    errors = dict(unavailable) if src == "ctrader" else {}

    def one(pair):
        try:
            update(pair, now, days=days, root=root, source="dukascopy")
        except Exception as e:
            errors[pair] = (pre[pair] + "; Dukascopy: " if pair in pre else "") + _safe(e)

    with ThreadPoolExecutor(threads) as ex:
        list(ex.map(one, pairs))
    return errors


def recent(pair, days, now=None, root=None):
    """Engine candles: hourly OHLC from now - days up to the last closed hour in the store (+ this run's
    Dukascopy fallback overlay after the last cTrader bar)."""
    now = _utc(now)
    t0 = now - pd.Timedelta(days=days)
    p = Pair(pair, root)
    df = p.frame(lo=int(np.ceil(t0.timestamp())))
    if p.src == "ctrader":
        ov = _overlay_frame(pair, root, p.last_time())
        if ov is not None:
            df = pd.concat([df, ov[ov.index >= t0]])
    df = df[df.index + pd.Timedelta(hours=1) <= now]
    if df.empty:
        raise RuntimeError(f"no stored candles for {pair} (run the backfill workflow)")
    return df


def _months(start_year, end_year, now):
    return [(y, m) for y in range(start_year, end_year + 1) for m in range(1, 13) if (y, m) < (now.year, now.month)]


def hourly(pair, start_year, end_year, root=None, now=None, source=None, feed=None):
    """Final-month candles of [start_year, end_year] (backtest), downloading missing months. cTrader first; if it
    fails, a cTrader file is used as it is and only an empty / Dukascopy file is filled from Dukascopy."""
    now = _utc(now)
    src = source or default_source()
    with _lock(pair):
        p = None
        if src == "ctrader":
            p = Pair(pair, root)
            months = _months(start_year, end_year, now)
            try:
                if p.src != "ctrader" or p.missing_months(months):
                    f = feed or get_feed()  # raises before the file is touched
                    p.use_source("ctrader").ctrader_months(f, months)
            except Exception as e:
                print(f"{pair}: cTrader months failed ({_safe(e)}), Dukascopy fallback", flush=True)
                if p.src == "ctrader":
                    p.save()
                p = None
        if p is None:
            p = Pair(pair, root)
            if p.src == "ctrader" and len(p.df):
                pass  # never mix: use the cTrader months that are there
            else:
                p = Pair(pair, root, source="dukascopy")
                for y, m in _months(start_year, end_year, now):
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


def months_all(pairs, start_year, end_year, threads=3, root=None, now=None, source=None):
    """Download missing final months for many pairs (before a backtest): cTrader over one connection, Dukascopy
    (threads) for the pairs where cTrader failed."""
    pairs = list(pairs)
    src = source or default_source()
    if src == "ctrader":
        failed = _ctrader_each(pairs, lambda p, feed: Pair(p, root, source="ctrader").ctrader_months(
            feed, _months(start_year, end_year, _utc(now))))
        if not failed:
            return
        _fallback_note(failed)
        pairs = list(failed)

    def one(p):
        try:
            hourly(p, start_year, end_year, root, now, source="dukascopy")
        except RuntimeError as e:
            print(f"{p}: {e}", flush=True)

    with ThreadPoolExecutor(threads) as ex:
        list(ex.map(one, pairs))


def backfill(pairs, start_year, now=None, threads=3, root=None, source=None):
    """All months from start_year plus the current month for many pairs. Returns {pair: error}."""
    now = _utc(now)
    since = pd.Timestamp(start_year, 1, 1, tz="UTC")
    return update_all(pairs, now, days=(now - since).days + 1, threads=threads, root=root, source=source)


def complete(pairs, start_year, root=None, now=None, max_age_days=10, source=None):
    """True when every pair has candles from early January of start_year up to the last ~week (and, with
    `source`, every file is of that source). Workflows save the candle cache only when this holds, so a cancelled
    run can't save a partial store, and a Dukascopy store is never saved under the cTrader cache key."""
    now = _utc(now)
    first_ok = pd.Timestamp(start_year, 1, 15, tz="UTC").timestamp()
    last_ok = (now - pd.Timedelta(days=max_age_days)).timestamp()
    bad = []
    for p in pairs:
        s = Pair(p, root)
        d = s.df
        if d.empty or d.index[0] > first_ok or d.index[-1] < last_ok or (source and s.src != source):
            bad.append(p)
    return not bad, bad


def describe(pair, root=None):
    s = Pair(pair, root)
    if s.df.empty:
        return f"{pair} 0 bars"
    a, b = (pd.Timestamp(int(x), unit="s").strftime("%Y-%m-%d %H:%M") for x in (s.df.index[0], s.df.index[-1]))
    return f"{pair} {len(s.df)} bars {a}..{b} {s.src}"


def main(argv=None):
    import argparse
    from .backtest import PAIRS
    ap = argparse.ArgumentParser(description="Fill the candle store (python -m bishop.store --start 2018)")
    ap.add_argument("--pairs", default="")
    ap.add_argument("--start", type=int, default=datetime.now(timezone.utc).year - 3)
    ap.add_argument("--threads", type=int, default=3)  # Dukascopy fallback answers 503 when hit harder
    ap.add_argument("--source", choices=("auto", *SOURCES), default="auto",
                    help="auto = cTrader when its secrets are set, else Dukascopy (with --check: any source)")
    ap.add_argument("--check", action="store_true", help="only report whether the store is complete (exit 0/1)")
    ap.add_argument("--notice", action="store_true", help="per-pair bar counts as GitHub ::notice:: annotations")
    a = ap.parse_args(argv)
    pairs = [x.strip().upper() for x in a.pairs.split(",") if x.strip()] or list(PAIRS)
    source = None if a.source == "auto" else a.source
    if a.check:
        ok, bad = complete(pairs, a.start, source=source)
        print(f"store complete from {a.start}{' (' + source + ')' if source else ''}: {ok}"
              + (f" (missing/short/other source: {', '.join(bad)})" if bad else ""))
        return 0 if ok else 1
    t = datetime.now()
    src = source or default_source()
    print(f"candle source: {src}", flush=True)
    err = backfill(pairs, a.start, threads=a.threads, source=src)
    close_feed()
    lines = [describe(p) + (f" ERROR {err[p]}" if p in err else "") for p in pairs]
    for line in lines:
        print(line)
    summary = f"backfill {len(pairs) - len(err)}/{len(pairs)} pairs in {(datetime.now() - t).total_seconds():.0f}s"
    print(summary)
    if a.notice:  # GitHub shows at most 10 annotations of a type per step: 7 pairs per notice
        for i in range(0, len(lines), 7):
            print(f"::notice title=Candles {i // 7 + 1}::" + " | ".join(lines[i:i + 7]))
        print(f"::notice title=Backfill::{summary} (source {src})")
    return 1 if err else 0


if __name__ == "__main__":
    raise SystemExit(main())
