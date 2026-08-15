"""
On-demand trade-chart viewer -- meant to run on Render (see render.yaml
at the repo root), not GitHub Pages. See data_access.py's module
docstring for why: it reads the repo's candle cache and published
results LIVE on every request, so it's never tied to one specific
backtest run, and it lets the repo itself stay private (this pulls it
server-side with a token instead of needing a public GH Pages site).

Charts are rendered on click (a Flask route per trade), not
pre-generated for the whole result set -- kinder to build time and to a
300+ trade result set than baking out one static page per trade.

Protected by HTTP Basic Auth (WEBAPP_USERNAME/WEBAPP_PASSWORD env vars)
since this exposes the strategy's actual entries/stops/targets, which is
the whole reason for not just using public GitHub Pages in the first
place.
"""

import bisect
import os

import pandas as pd
from flask import Flask, Response, abort, request

from . import data_access
from .charts import render_candlestick_svg

app = Flask(__name__)

WEBAPP_USERNAME = os.environ.get("WEBAPP_USERNAME")
WEBAPP_PASSWORD = os.environ.get("WEBAPP_PASSWORD")

# granularity -> (candles before entry, candles after entry) shown per chart.
CHART_WINDOWS = {
    "D": (120, 20),
    "H4": (90, 30),
    "H1": (60, 40),
}


@app.before_request
def _require_auth():
    if not WEBAPP_USERNAME or not WEBAPP_PASSWORD:
        return  # not configured yet -- fail open rather than lock the operator out during setup
    auth = request.authorization
    if not auth or auth.username != WEBAPP_USERNAME or auth.password != WEBAPP_PASSWORD:
        abort(Response("Authentication required", 401, {"WWW-Authenticate": 'Basic realm="SLK backtest viewer"'}))


def _page(body: str, title: str = "SLK Backtest Viewer") -> str:
    return f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>{title}</title>
<style>
body {{ font-family: system-ui, sans-serif; max-width: 1100px; margin: 2rem auto; padding: 0 1rem; color: #1a1a1a; }}
table {{ border-collapse: collapse; width: 100%; font-size: 0.85rem; }}
td, th {{ padding: 4px 10px; border-bottom: 1px solid #eee; text-align: left; white-space: nowrap; }}
tr:hover td {{ background: #f8f8f8; }}
a {{ color: #2563eb; text-decoration: none; }}
a:hover {{ text-decoration: underline; }}
.win {{ color: #16a34a; font-weight: 600; }}
.loss {{ color: #dc2626; font-weight: 600; }}
.chart-block {{ margin: 1.5rem 0; overflow-x: auto; }}
.meta {{ font-size: 0.9rem; color: #444; margin: 0.5rem 0 1rem; }}
</style></head><body>{body}</body></html>'''


def _escape(value) -> str:
    return (str(value) if value is not None else "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _nearest_index(times: list, t) -> int | None:
    if not times:
        return None
    idx = bisect.bisect_left(times, t)
    return min(idx, len(times) - 1)


@app.route("/")
def index():
    names = data_access.list_result_sets()
    if not names:
        return _page("<h1>SLK Backtest Viewer</h1><p>No results published yet -- run run-backtest.yml first.</p>")
    items = "".join(f'<li><a href="/results/{_escape(n)}">{_escape(n)}</a></li>' for n in names)
    return _page(f"<h1>SLK Backtest Viewer</h1><ul>{items}</ul>")


@app.route("/results/<name>")
def results(name):
    rows = data_access.load_results(name)
    if not rows:
        abort(404)

    body_rows = []
    for r in rows:
        status = r.get("status", "")
        cls = "win" if status == "closed_win" else ("loss" if status == "closed_loss" else "")
        r_display = f"{float(r['r_multiple']):+.2f}R" if r.get("r_multiple") else "—"
        body_rows.append(
            f'<tr><td><a href="/trade/{_escape(name)}/{_escape(r["trade_id"])}">#{_escape(r["trade_id"])}</a></td>'
            f'<td>{_escape(r.get("entry_time"))}</td><td>{_escape(r.get("direction"))}</td>'
            f'<td>{_escape(r.get("trade_kind"))}</td><td>{_escape(r.get("stop_kind"))}</td>'
            f'<td>{_escape(status)}</td><td class="{cls}">{r_display}</td></tr>'
        )
    table = (
        '<table><thead><tr><th>Trade</th><th>Entry time</th><th>Dir</th>'
        '<th>Kind</th><th>Stop kind</th><th>Status</th><th>R</th></tr></thead>'
        f'<tbody>{"".join(body_rows)}</tbody></table>'
    )
    return _page(f'<p><a href="/">&larr; all results</a></p><h1>{_escape(name)}</h1>{table}', title=name)


@app.route("/trade/<name>/<trade_id>")
def trade_detail(name, trade_id):
    row = data_access.get_trade(name, trade_id)
    if row is None:
        abort(404)

    instrument = row["instrument"]
    entry_time = pd.Timestamp(row["entry_time"])
    exit_time = pd.Timestamp(row["exit_time"]) if row.get("exit_time") else None
    entry_price = float(row["entry_price"])
    stop_loss = float(row["stop_loss"])
    target = float(row["primary_target"])
    key_level = float(row["key_level_price"]) if row.get("key_level_price") else None

    charts = []
    for granularity, (before, after) in CHART_WINDOWS.items():
        candles = data_access.load_candle_window(instrument, granularity, entry_time, before, after)
        times = [c.time for c in candles]
        entry_idx = _nearest_index(times, entry_time)
        exit_idx = _nearest_index(times, exit_time) if exit_time is not None else None
        markers = {"entry": entry_price, "stop": stop_loss, "target": target}
        if granularity != "D":
            markers["key_level"] = key_level
        svg = render_candlestick_svg(candles, markers, entry_idx, exit_idx,
                                      title=f"{instrument} {granularity}")
        charts.append(f'<div class="chart-block"><h3>{granularity}</h3>{svg}</div>')

    r_display = f' ({_escape(row["r_multiple"])}R)' if row.get("r_multiple") else ""
    meta = (
        '<div class="meta">'
        f'{_escape(row.get("direction"))} &middot; {_escape(row.get("trade_kind"))} &middot; '
        f'entry {entry_price:g} &middot; stop {stop_loss:g} ({_escape(row.get("stop_kind"))}) &middot; '
        f'target {target:g} &middot; key level '
        f'{key_level if key_level is not None else "—"} ({_escape(row.get("key_level_shape"))}) &middot; '
        f'status {_escape(row.get("status"))}{r_display}'
        '</div>'
    )
    return _page(
        f'<p><a href="/results/{_escape(name)}">&larr; {_escape(name)}</a></p>'
        f'<h1>Trade #{_escape(trade_id)} &mdash; {_escape(instrument)}</h1>{meta}{"".join(charts)}',
        title=f"Trade #{trade_id}",
    )


if __name__ == "__main__":
    app.run(debug=True, port=int(os.environ.get("PORT", 5000)))
