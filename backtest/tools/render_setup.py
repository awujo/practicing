"""
One trade, drawn across all four timeframes, so the system can be
checked by EYE against Bishop's own charts instead of by aggregate.

Operator, 2026-09-02: "me to trust your backtesting data I'm not sure if
you even implemented it as bishop does that's the problem. I'm not
seeing even the charts to know if you are placing it well." And again,
2026-09-23, after a run that lost money: "is it possible to see a chart
representation of one of these trades from the weekly daily 4h and
confirmation."

`render_trades.py` answers a narrower question -- it draws the H1 entry
alone. That cannot show whether the CASCADE was right, which is where
the strategy actually lives: weekly bias, daily bias, the 4H key level
and liquidity, and only then the H1 confirmation. A trade can have a
perfect H1 trigger and still be nonsense because the weekly said the
other thing.

WHAT IS DRAWN, AND WHERE IT COMES FROM

Everything solid is a NUMBER THE ENGINE RECORDED, read from the
per-trade CSV: entry, stop, target, key level, ERL, exit. Nothing is
re-derived, so the chart cannot flatter the code by drawing what the
code meant instead of what it did.

The H1 panel additionally marks the reaction geometry -- the touch, the
reaction low, the minor swing high -- for the two break triggers. That
IS recomputed, and is drawn dashed and labelled "recomputed" for
exactly that reason: it shows the pattern the detector claims to have
seen, which is the thing under suspicion, so it must not be mistaken
for a recorded fact.

READING IT

  Weekly / Daily    Is the bias real? Look for the break of structure
                    the trade direction is claiming.
  H4                Is the key level a level, and is there liquidity
                    resting beyond it that price came to take?
  H1                Did price come INTO the level, react, and confirm?
                    For a breakout, does the close clear the high the
                    reaction left -- or just a wiggle?

USAGE

    docker exec -u abc -w /config/trading mt5 python3 \\
        -m backtest.tools.render_setup --instrument AUDJPY \\
        --trigger breakout --count 3 --out /config/setup.html

    # then copy it off the box and open it in a browser
    docker cp mt5:/config/setup.html .
"""

from __future__ import annotations

import argparse
import csv
import html
import os

import pandas as pd

from ..engine.candles import Candle, load_candles
from ..engine.runner import default_pip_size

# Bars of context per timeframe. The higher ones get fewer because each
# candle is worth more: 30 weeklies is over half a year.
CONTEXT = {"W": (30, 6), "D": (60, 10), "H4": (70, 16), "H1": (60, 30)}
PANEL_ORDER = ("W", "D", "H4", "H1")
PANEL_TITLE = {"W": "Weekly — bias", "D": "Daily — bias",
               "H4": "H4 — key level & liquidity", "H1": "H1 — confirmation"}

W, H = 1000, 300
PAD_L, PAD_R, PAD_T, PAD_B = 10, 120, 10, 22


def _f(row, key):
    """A float from a CSV cell, or None when it is blank or unparseable.

    Tolerates a value that is already numeric so callers holding real
    TradeRecord values -- tests, or anything driving this in-process --
    do not have to stringify first."""
    v = row.get(key)
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    v = str(v).strip()
    if not v:
        return None
    try:
        return float(v)
    except ValueError:
        return None


def _fmt(p, pip):
    d = 1 if pip >= 1.0 else (3 if pip >= 0.01 else 5)
    return f"{p:.{d}f}"


def _when(value):
    """A trade time as a Timestamp, whatever the caller had.

    `write_trade_log` serialises times with `.isoformat()`, so a CSV row
    hands back a STRING while `Candle.time` is a `pd.Timestamp` -- and
    `Timestamp <= str` does not compare, it raises TypeError. Every
    panel in this tool is windowed by that comparison, so the whole
    thing died on the first real trade it was pointed at. The first
    smoke test missed it by passing a datetime directly instead of
    going through the CSV."""
    if value is None or isinstance(value, pd.Timestamp):
        return value
    try:
        return pd.Timestamp(value)
    except (ValueError, TypeError):
        return None


def _window(candles, at_time, before, after):
    """(slice, index of the anchor within it, absolute offset of the slice).

    Higher timeframes have no candle stamped at an H1 entry time, so the
    anchor is the last candle at or before it -- the one that was
    forming when the trade was taken.

    The absolute offset is returned rather than recovered later with
    `.index()`: Candle is a frozen dataclass, so `.index()` matches by
    VALUE and would silently return an earlier identical bar."""
    lo_i = None
    for i, c in enumerate(candles):
        if c.time <= at_time:
            lo_i = i
        else:
            break
    if lo_i is None:
        return [], -1, 0
    lo = max(0, lo_i - before)
    hi = min(len(candles), lo_i + after + 1)
    return candles[lo:hi], lo_i - lo, lo


def _svg(window, anchor_i, lines, pip, marks=()):
    """One panel. `lines` is [(price, colour, label, dashed)]."""
    if not window:
        return "<p>no data</p>"
    prices = [c.high for c in window] + [c.low for c in window]
    prices += [p for p, *_ in lines if p is not None]
    lo, hi = min(prices), max(prices)
    if hi <= lo:
        hi = lo + pip * 10
    pad = (hi - lo) * 0.06
    lo, hi = lo - pad, hi + pad

    plot_w = W - PAD_L - PAD_R
    plot_h = H - PAD_T - PAD_B
    step = plot_w / max(1, len(window))
    bw = max(1.2, step * 0.6)

    def y(p):
        return PAD_T + (hi - p) / (hi - lo) * plot_h

    out = [f'<svg viewBox="0 0 {W} {H}" width="100%" '
           f'style="background:#0f1115;border-radius:8px">']

    for price, colour, label, dashed in lines:
        if price is None:
            continue
        yy = y(price)
        if not (PAD_T <= yy <= PAD_T + plot_h):
            continue
        dash = ' stroke-dasharray="5,4"' if dashed else ""
        out.append(f'<line x1="{PAD_L}" y1="{yy:.1f}" x2="{PAD_L+plot_w}" '
                   f'y2="{yy:.1f}" stroke="{colour}" stroke-width="1.2"{dash}/>')
        out.append(f'<text x="{PAD_L+plot_w+6}" y="{yy+4:.1f}" fill="{colour}" '
                   f'font-size="11" font-family="monospace">'
                   f'{html.escape(label)} {_fmt(price, pip)}</text>')

    for i, c in enumerate(window):
        x = PAD_L + i * step + step / 2
        up = c.close >= c.open
        colour = "#3fb950" if up else "#f85149"
        if i == anchor_i:
            out.append(f'<rect x="{x-step/2:.1f}" y="{PAD_T}" width="{step:.1f}" '
                       f'height="{plot_h}" fill="#58a6ff" opacity="0.10"/>')
        out.append(f'<line x1="{x:.1f}" y1="{y(c.high):.1f}" x2="{x:.1f}" '
                   f'y2="{y(c.low):.1f}" stroke="{colour}" stroke-width="1"/>')
        top, bot = y(max(c.open, c.close)), y(min(c.open, c.close))
        out.append(f'<rect x="{x-bw/2:.1f}" y="{top:.1f}" width="{bw:.1f}" '
                   f'height="{max(1.0, bot-top):.1f}" fill="{colour}"/>')

    # Event marks: (index, colour, caption). Drawn as a full-height rule
    # with the caption stacked at a different level each time, because
    # five events on one panel as little circles above the wicks is
    # exactly the unreadable mess this tool exists to stop producing.
    seen = [m for m in marks if 0 <= m[0] < len(window)]
    for slot, (idx, colour, caption) in enumerate(seen):
        x = PAD_L + idx * step + step / 2
        ty = PAD_T + 12 + (slot % 4) * 13
        out.append(f'<line x1="{x:.1f}" y1="{PAD_T}" x2="{x:.1f}" '
                   f'y2="{PAD_T+plot_h}" stroke="{colour}" stroke-width="1" '
                   f'stroke-dasharray="2,3" opacity="0.75"/>')
        anchor = "start" if idx < len(window) * 0.75 else "end"
        dx = 4 if anchor == "start" else -4
        out.append(f'<text x="{x+dx:.1f}" y="{ty:.1f}" fill="{colour}" '
                   f'font-size="10" font-family="monospace" '
                   f'text-anchor="{anchor}">{html.escape(caption)}</text>')

    out.append("</svg>")
    return "".join(out)


def _reaction_marks(h1, anchor_i, direction_bullish, level_price):
    """The geometry the break detector claims to have seen.

    RECOMPUTED, not recorded -- the CSV does not store it. Drawn so the
    pattern can be checked against Bishop's drawing, and labelled as
    recomputed so it is never mistaken for what the engine logged.

    Mirrors `_reaction_structure`'s anchored branch: find the touch, then
    the reaction's high since the touch, then the low before that high."""
    touch = None
    for i in range(anchor_i - 1, max(-1, anchor_i - 60), -1):
        c = h1[i]
        if c.low <= level_price <= c.high:
            touch = i
        elif touch is not None:
            break
    if touch is None or anchor_i - touch < 2:
        return [], None

    span = range(touch, anchor_i)
    high_i = (max(span, key=lambda k: h1[k].high) if direction_bullish
              else min(span, key=lambda k: h1[k].low))
    before = range(touch, high_i + 1)
    low_i = (min(before, key=lambda k: h1[k].low) if direction_bullish
             else max(before, key=lambda k: h1[k].high))
    if high_i <= low_i:
        return [], None
    minor = h1[high_i].high if direction_bullish else h1[high_i].low
    return ([(touch, "#d29922", "touch"),
             (low_i, "#58a6ff", "reaction low"),
             (high_i, "#bc8cff", "minor high")], minor)


def render(instrument, rows, source, entry_style, out_path):
    pip = default_pip_size(instrument)
    series = {}
    for tf in PANEL_ORDER:
        try:
            series[tf] = load_candles(source, instrument, tf)
        except FileNotFoundError:
            series[tf] = []

    parts = [
        "<!doctype html><meta charset=utf-8>",
        f"<title>{html.escape(instrument)} setups</title>",
        "<style>body{background:#010409;color:#c9d1d9;font-family:system-ui,"
        "sans-serif;margin:0;padding:16px;max-width:1040px}"
        "h2{font-size:16px;margin:28px 0 4px}h3{font-size:12px;color:#8b949e;"
        "margin:14px 0 4px;font-weight:600;letter-spacing:.04em;"
        "text-transform:uppercase}"
        ".meta{font-family:monospace;font-size:12px;color:#8b949e;"
        "line-height:1.7;margin:6px 0 10px}"
        ".w{color:#3fb950}.l{color:#f85149}"
        ".note{font-size:12px;color:#8b949e;border-left:2px solid #30363d;"
        "padding-left:10px;margin:10px 0}</style>",
        f"<h1 style='font-size:18px'>{html.escape(instrument)} "
        f"&mdash; {html.escape(entry_style)}</h1>",
        "<p class=note>Solid lines are values the engine RECORDED. The dashed "
        "reaction marks on H1 are recomputed for display, so they show what the "
        "detector claims it saw &mdash; the thing under suspicion &mdash; and are "
        "not evidence on their own.</p>",
    ]

    for row in rows:
        entry_t = _when(row["entry_time"])
        if entry_t is None:
            continue
        bullish = "BULL" in (row.get("direction") or "").upper()
        entry = _f(row, "entry_price")
        stop = _f(row, "stop_loss")
        target = _f(row, "primary_target")
        level = _f(row, "key_level_price")
        r = _f(row, "r_multiple")
        risk = abs(entry - stop) if None not in (entry, stop) else None
        tgt_r = (abs(target - entry) / risk) if (risk and target) else None

        won = (row.get("exit_reason") == "target_hit")
        parts.append(
            f"<h2>#{html.escape(row.get('trade_id',''))} "
            f"{'BUY' if bullish else 'SELL'} &middot; "
            f"{html.escape(row.get('trigger_type',''))} &middot; "
            f"{html.escape(str(entry_t)[:16])} "
            f"<span class={'w' if won else 'l'}>"
            f"{'WIN' if won else 'LOSS'} {r:+.2f}R</span></h2>")
        meta = [f"key level {_fmt(level, pip) if level else '-'} "
                f"({html.escape(row.get('key_level_shape','') or '-')})"]
        if tgt_r:
            meta.append(f"target {tgt_r:.1f}R")
        meta.append(f"stop_kind {html.escape(row.get('stop_kind','') or '-')}")
        meta.append(f"aligned [{html.escape(row.get('aligned_timeframes','') or '')}]")
        meta.append("bias W/D/H4 " + "/".join(
            html.escape(row.get(k) or "-")
            for k in ("bias_weekly", "bias_daily", "bias_h4")))
        parts.append("<div class=meta>" + " &nbsp;|&nbsp; ".join(meta) + "</div>")

        # The setup, not just the entry. These four are what the strategy
        # is ABOUT, and none of them was drawable until they were
        # recorded: the breakout that opened the window, the liquidity it
        # left behind, the sweep that took that liquidity, and the touch
        # of the key level that followed.
        liq = _f(row, "liquidity_price")
        t_liq = _when(row.get("liquidity_time"))
        t_sweep = _when(row.get("sweep_time"))
        t_touch = _when(row.get("level_touch_time"))
        t_brk = _when(row.get("h4_breakout_time"))

        for tf in PANEL_ORDER:
            before, after = CONTEXT[tf]
            win, a_i, base = _window(series[tf], entry_t, before, after)
            if not win:
                parts.append(f"<h3>{PANEL_TITLE[tf]}</h3><p class=note>no data</p>")
                continue

            def at(ts, _win=win):
                """Index of `ts` within this panel, or -1."""
                if ts is None:
                    return -1
                for k in range(len(_win) - 1, -1, -1):
                    if _win[k].time <= ts:
                        return k
                return -1

            lines = [(level, "#d29922", "key level", False)]
            marks = []
            # Single candle liquidity, on every panel that can show it.
            if liq:
                lines.append((liq, "#f778ba", "liquidity (single candle)", False))
            for ts, colour, caption in ((t_brk, "#e3b341", "H4 breakout"),
                                        (t_liq, "#f778ba", "pool forms"),
                                        (t_sweep, "#f778ba", "SWEEP"),
                                        (t_touch, "#d29922", "touches KL")):
                k = at(ts)
                if k >= 0:
                    marks.append((k, colour, caption))
            marks.append((a_i, "#58a6ff", "ENTRY"))

            if tf == "H1":
                lines += [(entry, "#58a6ff", "entry", False),
                          (stop, "#f85149", "stop", False),
                          (target, "#3fb950", "target", False)]
                if row.get("trigger_type") in ("breakout", "sweep_break") and level:
                    found, minor = _reaction_marks(series[tf], base + a_i,
                                                   bullish, level)
                    marks += [(i - base, c, t) for i, c, t in found]
                    if minor is not None:
                        lines.append((minor, "#bc8cff", "broke this high (recomputed)", True))
            else:
                lines += [(target, "#3fb950", "target", True),
                          (entry, "#58a6ff", "entry", True),
                          (stop, "#f85149", "stop", True)]

            parts.append(f"<h3>{PANEL_TITLE[tf]}</h3>")
            parts.append(_svg(win, a_i, lines, pip, marks))

        parts.append(
            "<div class=note>Read it in this order: <b>H4 breakout</b> sets the "
            "direction &rarr; it leaves <b>single candle liquidity</b> behind &rarr; "
            "price comes back and <b>sweeps</b> it &rarr; then <b>touches the key "
            "level</b> &rarr; and the confirmation fires at <b>ENTRY</b>. If those "
            "marks are not in that order, or the liquidity line is nowhere near "
            "where price turned, the engine is not trading this setup.</div>")

    with open(out_path, "w") as fh:
        fh.write("\n".join(parts))
    return out_path


def main():
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--instrument", required=True)
    p.add_argument("--entry-style", default="conservative")
    p.add_argument("--suffix", default="_slk")
    p.add_argument("--results-dir", default="backtest/results")
    p.add_argument("--trigger", default="", help="only this trigger_type")
    p.add_argument("--outcome", default="", choices=("", "win", "loss"))
    p.add_argument("--count", type=int, default=3)
    p.add_argument("--source", default="dukascopy")
    p.add_argument("--out", default="/config/setup.html")
    args = p.parse_args()

    path = os.path.join(args.results_dir,
                        f"{args.instrument}_{args.entry_style}{args.suffix}.csv")
    if not os.path.exists(path):
        raise SystemExit(f"no trade log at {path}")
    with open(path, newline="") as fh:
        rows = [r for r in csv.DictReader(fh)
                if r.get("exit_reason") in ("target_hit", "stop_hit")]
    if args.trigger:
        rows = [r for r in rows if r.get("trigger_type") == args.trigger]
    if args.outcome == "win":
        rows = [r for r in rows if r["exit_reason"] == "target_hit"]
    elif args.outcome == "loss":
        rows = [r for r in rows if r["exit_reason"] != "target_hit"]
    if not rows:
        raise SystemExit("no trades match that filter")

    # Spread across the file rather than the first N, which would all
    # come from the same week and show one market condition.
    stride = max(1, len(rows) // args.count)
    picked = rows[::stride][:args.count]

    out = render(args.instrument, picked, args.source, args.entry_style, args.out)
    print(f"{len(picked)} of {len(rows)} matching trades -> {out}")
    print(f"copy it off with:  docker cp mt5:{out} .")


if __name__ == "__main__":
    main()
