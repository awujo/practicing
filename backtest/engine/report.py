"""
Static HTML dashboard generator -- reads every trade-log CSV in
`backtest/results/` (one per instrument/entry-style run) and produces a
single self-contained `index.html` with summary stats, a cumulative-R
equity curve, AND a trade-by-trade reasoning table per run. Meant to be
published to GitHub Pages by the `run-backtest.yml` workflow so results
-- including WHY each trade was taken, not just whether it won -- are
viewable at a stable URL without downloading anything or running code
locally.

The reasoning table exists because a win-rate number alone doesn't
answer "why did the bot take this trade" -- it reconstructs each trade's
story from trade_log.py's rich TradeRecord fields: the bias reading on
every timeframe and which one won the priority hierarchy, which entry
pattern fired, the key level and its QMR/imbalance quality signals, and
which stop-loss rule applied. For very large trade counts the table caps
at the most recent MAX_TRADES_DISPLAYED (the CSV download link still has
everything).

Deliberately no external JS/CSS dependency (no Chart.js, no CDN) -- the
equity curve is a plain inline SVG polyline and the trades table is a
plain scrollable HTML table, both computed in Python. That keeps the
page fully self-contained and testable without a browser, and avoids
depending on a CDN being reachable wherever the page is viewed.
"""

import csv
import glob
import os
import shutil

MAX_TRADES_DISPLAYED = 1000


def _read_csv_rows(path: str) -> list[dict]:
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def _summarize_rows(rows: list[dict]) -> dict:
    closed = [r for r in rows if r.get("status") in ("closed_win", "closed_loss", "closed_breakeven")]
    wins = [r for r in closed if r.get("status") == "closed_win"]
    r_values = [float(r["r_multiple"]) for r in closed if r.get("r_multiple")]
    total_r = sum(r_values)
    return {
        "total_trades": len(rows),
        "closed_trades": len(closed),
        "wins": len(wins),
        "win_rate": (len(wins) / len(closed)) if closed else None,
        "total_r": total_r,
        "avg_r": (total_r / len(r_values)) if r_values else None,
        "r_values": r_values,
    }


def _svg_equity_curve(r_multiples: list[float], width: int = 640, height: int = 200) -> str:
    if not r_multiples:
        return "<p><em>No closed trades yet.</em></p>"

    cumulative = []
    total = 0.0
    for r in r_multiples:
        total += r
        cumulative.append(total)

    values = cumulative + [0.0]
    min_v, max_v = min(values), max(values)
    span = (max_v - min_v) or 1.0
    n = len(cumulative)

    def point(i, v):
        x = 10 + (i / max(n - 1, 1)) * (width - 20)
        y = height - 10 - ((v - min_v) / span) * (height - 20)
        return f"{x:.1f},{y:.1f}"

    polyline = " ".join(point(i, v) for i, v in enumerate(cumulative))
    zero_y = height - 10 - ((0 - min_v) / span) * (height - 20)

    return (
        f'<svg viewBox="0 0 {width} {height}" xmlns="http://www.w3.org/2000/svg" '
        f'style="background:#fafafa;border:1px solid #ddd">'
        f'<line x1="10" y1="{zero_y:.1f}" x2="{width - 10}" y2="{zero_y:.1f}" '
        f'stroke="#999" stroke-dasharray="4" />'
        f'<polyline points="{polyline}" fill="none" stroke="#2563eb" stroke-width="2" />'
        f'</svg>'
    )


def _escape(value) -> str:
    return (str(value) if value is not None else "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _trade_row_html(row: dict) -> str:
    bias_story = " &middot; ".join(
        f"{tf}={row.get(f'bias_{tf.lower()}') or '—'}" for tf in ("Weekly", "Daily", "H4", "H1")
    )
    effective = row.get("effective_bias_timeframe") or "—"
    fvg = "FVG overlap" if row.get("imbalance_overlap") == "True" else "no FVG"
    qmr = row.get("qmr_test_count", "0")
    # trigger_type/aligned_timeframes may be absent on CSVs from before the
    # entry-gate rebuild -- .get() with a dash default keeps older result
    # files rendering instead of erroring.
    trigger = row.get("trigger_type") or "—"
    aligned = row.get("aligned_timeframes") or "—"
    reasoning = (
        f"{_escape(row.get('entry_pattern'))} "
        f"(trigger: {_escape(trigger)}, aligned: {_escape(aligned)}) "
        f"on {_escape(row.get('key_level_shape'))} @ {_escape(row.get('key_level_price'))} "
        f"&mdash; QMR {_escape(qmr)}, {fvg}, stop: {_escape(row.get('stop_kind'))}"
    )
    bias_summary = f"{bias_story} &rarr; effective: {_escape(effective)}"

    status = row.get("status", "")
    r_raw = row.get("r_multiple", "")
    r_display = f"{float(r_raw):+.2f}R" if r_raw else "—"
    row_class = "win" if status == "closed_win" else ("loss" if status == "closed_loss" else "openrow")

    return (
        f'<tr class="{row_class}">'
        f'<td>{_escape(row.get("entry_time"))}</td>'
        f'<td>{_escape(row.get("direction"))}</td>'
        f'<td>{bias_summary}</td>'
        f'<td>{reasoning}</td>'
        f'<td>{_escape(row.get("entry_price"))}</td>'
        f'<td>{_escape(row.get("stop_loss"))}</td>'
        f'<td>{_escape(row.get("primary_target"))}</td>'
        f'<td>{_escape(status)} ({_escape(row.get("exit_reason") or "—")})</td>'
        f'<td class="rcol">{r_display}</td>'
        f'</tr>'
    )


def _trades_table_html(rows: list[dict]) -> str:
    if not rows:
        return ""
    displayed = rows[-MAX_TRADES_DISPLAYED:]
    note = ""
    if len(rows) > MAX_TRADES_DISPLAYED:
        note = (
            f"<p><em>Showing the most recent {MAX_TRADES_DISPLAYED} of {len(rows)} trades -- "
            f"download the CSV above for the full list.</em></p>"
        )
    body_rows = "".join(_trade_row_html(r) for r in displayed)
    return f'''
  <h3>Trade-by-trade reasoning</h3>
  {note}
  <div class="trades-scroll">
    <table class="trades">
      <thead><tr>
        <th>Entry time</th><th>Dir</th><th>Bias cascade</th><th>Why this trade</th>
        <th>Entry</th><th>Stop</th><th>Target</th><th>Outcome</th><th>R</th>
      </tr></thead>
      <tbody>{body_rows}</tbody>
    </table>
  </div>
'''


def _section_html(name: str, stats: dict, rows: list[dict]) -> str:
    win_rate = f"{stats['win_rate'] * 100:.1f}%" if stats["win_rate"] is not None else "n/a"
    avg_r = f"{stats['avg_r']:.2f}" if stats["avg_r"] is not None else "n/a"
    chart = _svg_equity_curve(stats["r_values"])
    trades_table = _trades_table_html(rows)
    return f'''
<section>
  <h2>{_escape(name)}</h2>
  <table>
    <tr><td>Total trades</td><td>{stats["total_trades"]}</td></tr>
    <tr><td>Closed trades</td><td>{stats["closed_trades"]}</td></tr>
    <tr><td>Win rate</td><td>{win_rate}</td></tr>
    <tr><td>Average R</td><td>{avg_r}</td></tr>
    <tr><td>Total R</td><td>{stats["total_r"]:.2f}</td></tr>
  </table>
  <h3>Equity curve (cumulative R)</h3>
  {chart}
  <p><a href="results/{name}.csv">Download raw trade log (CSV)</a></p>
  {trades_table}
</section>
'''


def generate_report(results_dir: str = "backtest/results", out_dir: str = "backtest/site") -> str:
    """Builds out_dir/index.html plus a copy of every results CSV under
    out_dir/results/, ready to publish as one self-contained static site."""
    os.makedirs(out_dir, exist_ok=True)
    site_results_dir = os.path.join(out_dir, "results")
    os.makedirs(site_results_dir, exist_ok=True)

    csv_paths = sorted(glob.glob(os.path.join(results_dir, "*.csv")))
    sections = []
    for path in csv_paths:
        name = os.path.splitext(os.path.basename(path))[0]
        rows = _read_csv_rows(path)
        stats = _summarize_rows(rows)
        sections.append(_section_html(name, stats, rows))
        shutil.copy(path, os.path.join(site_results_dir, os.path.basename(path)))

    body = "".join(sections) if sections else "<p>No results yet -- run the backtest workflow first.</p>"

    html = f'''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>SLK Backtest Results</title>
<style>
body {{ font-family: system-ui, sans-serif; max-width: 1100px; margin: 2rem auto; padding: 0 1rem; color: #1a1a1a; }}
table {{ border-collapse: collapse; margin: 0.75rem 0; }}
td {{ padding: 4px 16px 4px 0; border-bottom: 1px solid #eee; }}
section {{ margin-bottom: 3rem; padding-bottom: 1.5rem; border-bottom: 1px solid #ddd; }}
h1 {{ margin-bottom: 0.25rem; }}
.trades-scroll {{ max-height: 480px; overflow-y: auto; border: 1px solid #ddd; margin-top: 0.5rem; }}
.trades {{ width: 100%; font-size: 0.82rem; }}
.trades th, .trades td {{ padding: 4px 8px; border-bottom: 1px solid #eee; text-align: left; white-space: nowrap; }}
.trades th {{ position: sticky; top: 0; background: #f5f5f5; }}
.trades tr.win td.rcol {{ color: #16a34a; font-weight: 600; }}
.trades tr.loss td.rcol {{ color: #dc2626; font-weight: 600; }}
.trades tr.openrow td.rcol {{ color: #888; }}
</style>
</head>
<body>
<h1>SLK Backtest Results</h1>
<p>Regenerated automatically after every run-backtest workflow run.</p>
{body}
</body>
</html>'''

    out_path = os.path.join(out_dir, "index.html")
    with open(out_path, "w") as f:
        f.write(html)
    return out_path


if __name__ == "__main__":
    path = generate_report()
    print(f"Report written to {path}")
