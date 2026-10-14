"""Export one pair's H1 candles and explain its current bias story (point B, first touch, target) for offline checks.

    python -m slk.debug_pair --pair XAUUSD --days 1500 [--out data/debug] [--story D]

Used by .github/workflows/debug-pair.yml. cTrader first (the live source); when cTrader fails the error is printed
(with the client's diagnostics: what the server sent, ping, symbol ids) and the Dukascopy fallback is exported
instead, exactly what live then uses. Files: <out>/<PAIR>_H1_<source>.csv.gz and <out>/<PAIR>_explain.txt.
"""
import argparse
import os
import re
import sys

import numpy as np
import pandas as pd

from . import instruments, store
from .story import DEFAULT, STORIES, _Ctx, _point_b, current_tap, find_stories


def fetch(pair, days, now=None):
    """store.update from the default source, Dukascopy when cTrader fails. Returns (frame, source, error text)."""
    err = None
    src = store.default_source()
    if src == "ctrader":
        try:
            store.update(pair, now, days=days, source="ctrader")
        except Exception as e:
            err = store._safe(e, 1500)
            print(f"::warning title=cTrader {pair}::{err}", flush=True)
            src = "dukascopy"
            store.close_feed()
    if src == "dukascopy":
        store.update(pair, now, days=days, source="dukascopy")
    p = store.Pair(pair)
    return p.frame(), p.src, err


def explain(pair, h1, story="D", cfg=None):
    """Lines describing the latest story start the engine sees on these (closed) bars: the tapped level, the first
    confirm-TF bar touching it (k0), the confirm-TF close-line turns before k0 (point B = the last opposite one) and
    the target. Same rules as current_tap / find_stories (STRATEGY §2)."""
    cfg = {**DEFAULT, **(cfg or {})}
    otf, ctf = STORIES[story]
    fp = lambda x: instruments.fmt(pair, x)  # noqa: E731
    out = [f"{pair} {story} story ({otf}->{ctf}), pip {instruments.pip(pair):g}, {len(h1)} H1 bars "
           f"{h1.index[0]:%Y-%m-%d %H:%M}..{h1.index[-1]:%Y-%m-%d %H:%M} UTC"]
    tap = current_tap(pair, h1, story, cfg)
    rows = find_stories(pair, h1, story, cfg)
    r = tap or (rows[-1] if rows else None)
    if r is None:
        return out + ["no story"]
    out.append(f"{'TAPPED' if tap else 'last confirmed'}: {r['side']} level {fp(r['level'])} ({r['level_kind']}, "
               f"formed {r.get('level_time')}), tap bar {r['tap_time']} UTC, B {fp(r['B'])}, "
               f"target {fp(r.get('target'))}")
    X = _Ctx(pair, h1, story, cfg)
    bar = next(i for i in range(len(X.o_start)) if str(X.o_start[i])[:16] == str(r["tap_time"])[:16])
    sell = r["side"] == "SELL"
    C, lvp = X.C, float(r["level"])
    ks = np.arange(X.first_k[bar], X.first_k[bar + 1])
    touch = [k for k in ks if (C["high"][k] >= lvp - X.tol if sell else C["low"][k] <= lvp + X.tol)]
    k0 = touch[0] if touch else ks[0]
    cs = [pd.Timestamp(x) for x in X.c_start]
    out.append(f"first {ctf} bar touching {fp(lvp)} (k0): {cs[k0]:%Y-%m-%d %H:%M} UTC "
               f"(O {fp(C['open'][k0])} H {fp(C['high'][k0])} L {fp(C['low'][k0])} C {fp(C['close'][k0])})")
    want = "L" if sell else "H"
    turns = [s for s in X.csw.at(k0) if s[1] == want and s[0] < k0][-5:]
    out.append(f"{ctf} close-line {'V' if sell else 'A'}-turns (order b_pivot={cfg['b_pivot']}) before k0: " +
               ", ".join(f"{cs[s[0]]:%m-%d %H:%M} {fp(s[2])}" for s in turns))
    out.append(f"point B = {fp(_point_b(X.csw.at(k0), k0, sell))} (the last one)")
    lo = max(0, k0 - 8)
    hi = min(len(C["close"]), int(X.first_k[min(bar + 2, len(X.first_k) - 1)]))
    out.append(f"{ctf} bars {cs[lo]:%m-%d %H:%M}..: " + "; ".join(
        f"{cs[k]:%d %H:%M} O{fp(C['open'][k])} H{fp(C['high'][k])} L{fp(C['low'][k])} C{fp(C['close'][k])}"
        + (" <k0" if k == k0 else "") for k in range(lo, hi)))
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--pair", required=True)
    ap.add_argument("--days", type=int, default=1500)
    ap.add_argument("--out", default="data/debug")
    ap.add_argument("--story", default="D", choices=list(STORIES))
    a = ap.parse_args(argv)
    pair = re.sub(r"[^A-Z0-9]", "", a.pair.upper())[:12]
    df, src, err = fetch(pair, a.days)
    store.close_feed()
    os.makedirs(a.out, exist_ok=True)
    df.to_csv(os.path.join(a.out, f"{pair}_H1_{src}.csv.gz"), float_format="%.6g")
    print(f"::notice title={pair} candles::{len(df)} H1 bars {df.index[0]}..{df.index[-1]} source {src}"
          + (f" (cTrader failed: {err[:300]})" if err else ""), flush=True)
    from .live import drop_forming
    now = df.index[-1] + pd.Timedelta(hours=1)
    lines = explain(pair, drop_forming(df, STORIES[a.story][0], now), a.story)
    with open(os.path.join(a.out, f"{pair}_explain.txt"), "w") as f:
        f.write("\n".join(lines) + ("\ncTrader error: " + err if err else "") + "\n")
    for i, line in enumerate(lines):
        print(line)
        if i < 8:
            print(f"::notice title={pair} explain {i + 1}::{line[:1500]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
