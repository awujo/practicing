"""
Static HTML dashboard generator -- reads every trade-log CSV in
`backtest/results/` (one per instrument/entry-style run) and produces a
single self-contained `index.html` with summary stats and a cumulative-R
equity curve per run. Meant to be published to GitHub Pages by the
`run-backtest.yml` workflow so results are viewable at a stable URL
without downloading anything or running code locally.

Deliberately no external JS/CSS dependency (no Chart.js, no CDN) -- the
equity curve is rendered as a plain inline SVG polyline computed in
Python. That keeps the page fully self-contained and testable without a
browser, and avoids depending on a CDN being reachable wherever the page
is viewed.
"""

import csv
import glob
import os
import shutil


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


def _section_html(name: str, stats: dict) -> str:
    win_rate = f"{stats['win_rate'] * 100:.1f}%" if stats["win_rate"] is not None else "n/a"
    avg_r = f"{stats['avg_r']:.2f}" if stats["avg_r"] is not None else "n/a"
    chart = _svg_equity_curve(stats["r_values"])
    return f'''
<section>
  <h2>{name}</h2>
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
        sections.append(_section_html(name, stats))
        shutil.copy(path, os.path.join(site_results_dir, os.path.basename(path)))

    body = "".join(sections) if sections else "<p>No results yet -- run the backtest workflow first.</p>"

    html = f'''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>SLK Backtest Results</title>
<style>
body {{ font-family: system-ui, sans-serif; max-width: 900px; margin: 2rem auto; padding: 0 1rem; color: #1a1a1a; }}
table {{ border-collapse: collapse; margin: 0.75rem 0; }}
td {{ padding: 4px 16px 4px 0; border-bottom: 1px solid #eee; }}
section {{ margin-bottom: 3rem; padding-bottom: 1.5rem; border-bottom: 1px solid #ddd; }}
h1 {{ margin-bottom: 0.25rem; }}
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
