"""
Render real backtest trades as candlestick charts so the entries, stops
and targets can be inspected visually against Bishop's own chart examples.

Motivation (operator, 2026-09-02): "me to trust your backtesting data I'm
not sure if you even implemented it as bishop does that's the problem.
I'm not seeing even the charts to know if you are placing it well."

Aggregate win-rate/R tables cannot answer that question -- only looking at
the actual placements can. This emits a standalone HTML page of inline SVG
candlestick charts, one per trade, each drawn with the same elements
Bishop marks by hand: the key level, the entry, the stop, the target, and
where the trade actually ended.

No third-party plotting dependency (matplotlib is not installed in the
runner image, and hand-written SVG stays crisp on a phone screen, which
is where these get reviewed).

Usage:
    python -m backtest.tools.render_trades --instrument GBPJPY \
        --entry-style aggressive --out /tmp/trades.html
"""

from __future__ import annotations

import argparse
import html
import random

from ..engine.candles import Candle, load_candles
from ..engine.runner import default_pip_size, run_backtest
from ..engine.structure import Direction


# Candles drawn either side of the entry. Enough context to see the swing
# the stop is anchored to, without shrinking the candles into noise.
BARS_BEFORE = 40
BARS_AFTER = 30

CHART_W = 900
CHART_H = 420
PAD_L = 8
PAD_R = 104         # room for the price labels on the right axis
PAD_T = 12
PAD_B = 24

# Minimum vertical spacing between right-axis captions.
LABEL_GAP = 13.0



def _slice_for(candles: list[Candle], entry_time, exit_time):
    """Window of candles around the trade, plus entry/exit indices within it."""
    times = [c.time for c in candles]
    try:
        entry_idx = times.index(entry_time)
    except ValueError:
        # Entry timestamps come from these same candles, so a miss means
        # the trade came from a different series than the one loaded.
        return [], -1, -1

    lo = max(0, entry_idx - BARS_BEFORE)
    hi = min(len(candles), entry_idx + BARS_AFTER + 1)

    exit_idx = -1
    if exit_time is not None:
        try:
            exit_idx = times.index(exit_time)
        except ValueError:
            exit_idx = -1
        else:
            # Always show the exit, even when it lands past the default window.
            if exit_idx >= hi:
                hi = min(len(candles), exit_idx + 6)

    return candles[lo:hi], entry_idx - lo, (exit_idx - lo if exit_idx >= 0 else -1)


def _fmt(price: float, pip_size: float) -> str:
    digits = 3 if pip_size >= 0.01 else 5
    if pip_size >= 1.0:
        digits = 1
    return f"{price:.{digits}f}"


def _render_svg(window: list[Candle], entry_i: int, exit_i: int, trade, pip_size: float) -> str:
    """Draw one trade as an SVG candlestick chart with its levels marked."""
    levels = [trade.entry_price, trade.stop_loss, trade.primary_target, trade.key_level_price]
    lo = min([c.low for c in window] + levels)
    hi = max([c.high for c in window] + levels)
    span = (hi - lo) or 1.0
    lo -= span * 0.06
    hi += span * 0.06
    span = hi - lo

    plot_w = CHART_W - PAD_L - PAD_R
    plot_h = CHART_H - PAD_T - PAD_B
    step = plot_w / max(len(window), 1)
    body_w = max(step * 0.62, 1.0)

    def y(price: float) -> float:
        return PAD_T + (hi - price) / span * plot_h

    def x(i: int) -> float:
        return PAD_L + i * step + step / 2

    out: list[str] = [
        f'<svg viewBox="0 0 {CHART_W} {CHART_H}" xmlns="http://www.w3.org/2000/svg" class="chart">'
    ]

    # Shade the trade's own duration so the holding period is obvious.
    if exit_i >= 0:
        x0 = PAD_L + entry_i * step
        x1 = PAD_L + (exit_i + 1) * step
        out.append(
            f'<rect x="{x0:.1f}" y="{PAD_T}" width="{max(x1 - x0, 1):.1f}" '
            f'height="{plot_h:.1f}" class="dur"/>'
        )

    # Risk and reward bands -- the same visual as a chart R:R tool.
    e, s, t = y(trade.entry_price), y(trade.stop_loss), y(trade.primary_target)
    out.append(
        f'<rect x="{PAD_L}" y="{min(e, s):.1f}" width="{plot_w:.1f}" '
        f'height="{abs(s - e):.1f}" class="band-risk"/>'
    )
    out.append(
        f'<rect x="{PAD_L}" y="{min(e, t):.1f}" width="{plot_w:.1f}" '
        f'height="{abs(t - e):.1f}" class="band-reward"/>'
    )

    # Candles.
    for i, c in enumerate(window):
        cls = "c-up" if c.close >= c.open else "c-dn"
        cx = x(i)
        out.append(
            f'<line x1="{cx:.1f}" y1="{y(c.high):.1f}" x2="{cx:.1f}" '
            f'y2="{y(c.low):.1f}" class="{cls} wick"/>'
        )
        top = y(max(c.open, c.close))
        height = max(abs(y(c.open) - y(c.close)), 1.0)
        out.append(
            f'<rect x="{cx - body_w / 2:.1f}" y="{top:.1f}" width="{body_w:.1f}" '
            f'height="{height:.1f}" class="{cls}"/>'
        )

    # Mark the confirmation candle -- the one the stop is anchored to.
    if 0 <= entry_i < len(window):
        cx = x(entry_i)
        out.append(
            f'<rect x="{cx - body_w / 2 - 2:.1f}" y="{y(window[entry_i].high) - 2:.1f}" '
            f'width="{body_w + 4:.1f}" '
            f'height="{y(window[entry_i].low) - y(window[entry_i].high) + 4:.1f}" '
            f'class="conf"/>'
        )

    # Level lines, drawn last so they sit above the candles.
    levels_drawn = [
        (trade.key_level_price, "lv-key", "key level"),
        (trade.primary_target, "lv-target", "target"),
        (trade.entry_price, "lv-entry", "entry"),
        (trade.stop_loss, "lv-stop", "stop"),
    ]
    for price, cls, _label in levels_drawn:
        py = y(price)
        out.append(
            f'<line x1="{PAD_L}" y1="{py:.1f}" x2="{PAD_L + plot_w:.1f}" y2="{py:.1f}" '
            f'class="lv {cls}"/>'
        )

    # Labels are pushed apart when levels crowd together, so a 1-pip stop
    # stays readable instead of printing four captions on top of each other
    # -- exactly the case worth being able to see.
    label_x = PAD_L + plot_w + 5
    placed: list[float] = []
    for price, cls, label in sorted(levels_drawn, key=lambda lv: y(lv[0])):
        ty = y(price) + 3.5
        if placed and ty - placed[-1] < LABEL_GAP:
            ty = placed[-1] + LABEL_GAP
        placed.append(ty)
        # A leader line keeps the caption tied to the line it names once moved.
        if abs(ty - (y(price) + 3.5)) > 1.0:
            out.append(
                f'<line x1="{PAD_L + plot_w:.1f}" y1="{y(price):.1f}" '
                f'x2="{label_x - 2:.1f}" y2="{ty - 3.5:.1f}" class="lv {cls}" '
                f'stroke-width="0.7" opacity="0.6"/>'
            )
        out.append(
            f'<text x="{label_x:.1f}" y="{ty:.1f}" class="lvt {cls}">'
            f'{label} {_fmt(price, pip_size)}</text>'
        )

    # Where the trade actually ended.
    if exit_i >= 0:
        ex, ey = x(exit_i), y(trade.exit_price)
        out.append(f'<circle cx="{ex:.1f}" cy="{ey:.1f}" r="4.5" class="exit"/>')
        out.append(
            f'<text x="{ex + 7:.1f}" y="{ey - 6:.1f}" class="exit-t">'
            f'{html.escape(str(trade.exit_reason))}</text>'
        )

    out.append("</svg>")
    return "".join(out)


def _card(trade, svg: str, pip_size: float) -> str:
    rr = (abs(trade.primary_target - trade.entry_price)
          / abs(trade.entry_price - trade.stop_loss)) if trade.entry_price != trade.stop_loss else 0.0
    r_text = "open" if trade.r_multiple is None else f"{trade.r_multiple:+.2f}R"
    flag = ""
    natural = ""
    if trade.stop_fallback_used:
        flag = ('<p class="flag">Fallback stop &mdash; the rule that replaces the '
                'confirmation anchor when it exceeds the width limit.</p>')
        if trade.natural_stop_loss is not None:
            natural_pips = abs(trade.entry_price - trade.natural_stop_loss) / pip_size
            natural = (f'<dt>discarded</dt><dd><b>{_fmt(trade.natural_stop_loss, pip_size)}</b> '
                       f'<span class="q">{natural_pips:.1f} pips &middot; the real anchor</span></dd>')

    is_long = trade.direction == Direction.BULLISH
    side = "LONG" if is_long else "SHORT"
    won = trade.r_multiple is not None and trade.r_multiple > 0
    return f"""<section class="trade{' is-fallback' if trade.stop_fallback_used else ''}">
  <header>
    <span class="side {'long' if is_long else 'short'}">{side}</span>
    <h2>{html.escape(trade.instrument)} <span class="trig">{html.escape(str(trade.trigger_type))}</span></h2>
    <span class="when">{html.escape(str(trade.entry_time))}</span>
    <span class="r {'win' if won else 'loss'}">{r_text}</span>
  </header>
  {flag}
  {svg}
  <dl>
    <dt>entry</dt><dd><b>{_fmt(trade.entry_price, pip_size)}</b> <span class="q">{html.escape(trade.entry_style)}</span></dd>
    <dt>stop</dt><dd><b>{_fmt(trade.stop_loss, pip_size)}</b> <span class="q">{trade.risk_pips:.1f} pips &middot; {html.escape(str(trade.stop_kind))}</span></dd>
    {natural}
    <dt>target</dt><dd><b>{_fmt(trade.primary_target, pip_size)}</b> <span class="q">{rr:.1f}R</span></dd>
    <dt>key level</dt><dd><b>{_fmt(trade.key_level_price, pip_size)}</b> <span class="q">{html.escape(str(trade.key_level_shape))}</span></dd>
    <dt>exit</dt><dd><b>{_fmt(trade.exit_price, pip_size) if trade.exit_price else '&mdash;'}</b> <span class="q">{html.escape(str(trade.exit_reason))}</span></dd>
  </dl>
</section>"""


STYLE = """<link rel="stylesheet" href="https://fonts.googleapis.com/css2?\
family=IBM+Plex+Mono:wght@400;500;600&family=IBM+Plex+Sans:wght@400;500;600&display=swap">
<style>
:root{
  --bg:#f7f8f6; --panel:#ffffff; --fg:#171a1d; --muted:#646c74;
  --line:#dfe3e2; --line-soft:#ecefed; --brass:#8a6218;
  --up:#1f8a7c; --down:#d0453f; --entry:#2c5fd0; --stop:#c8322c;
  --target:#0f7a6b; --key:#8a4bb0;
  --ok:#1f7a3d; --warn:#a35a06; --bad:#b3271f;
  --sans:"IBM Plex Sans",system-ui,-apple-system,"Segoe UI",sans-serif;
  --mono:"IBM Plex Mono",ui-monospace,SFMono-Regular,Menlo,monospace;
}
@media (prefers-color-scheme:dark){:root:not([data-theme=light]){
  --bg:#12151a; --panel:#191d23; --fg:#e4e7e6; --muted:#8b949d;
  --line:#272c33; --line-soft:#20252b; --brass:#d3a44a;
  --up:#3fbfa8; --down:#f0655c; --entry:#6f9cf5; --stop:#f0655c;
  --target:#35b39c; --key:#c08ae0;
  --ok:#4fbf74; --warn:#e0a44a; --bad:#f0655c;
}}
:root[data-theme=dark]{
  --bg:#12151a; --panel:#191d23; --fg:#e4e7e6; --muted:#8b949d;
  --line:#272c33; --line-soft:#20252b; --brass:#d3a44a;
  --up:#3fbfa8; --down:#f0655c; --entry:#6f9cf5; --stop:#f0655c;
  --target:#35b39c; --key:#c08ae0;
  --ok:#4fbf74; --warn:#e0a44a; --bad:#f0655c;
}
*{box-sizing:border-box}
body{background:var(--bg);color:var(--fg);font-family:var(--sans);font-size:14px;
  line-height:1.55;margin:0;padding:22px 18px 56px}
.wrap{max-width:1000px;margin:0 auto}
h1{font-size:22px;font-weight:600;letter-spacing:-.01em;margin:0 0 6px;text-wrap:balance}
.lede{color:var(--muted);max-width:66ch;margin:0 0 26px}

/* Verdict band -- the page's single most important reading. */
.fid{width:100%;border-collapse:collapse;margin:0 0 10px;font-size:13px}
.fid caption{caption-side:top;text-align:left;color:var(--muted);padding:0 0 12px;
  max-width:66ch;font-size:13px}
.fid th{font-family:var(--sans);font-size:11px;font-weight:600;letter-spacing:.07em;
  text-transform:uppercase;color:var(--muted);text-align:left;padding:0 12px 7px 0;
  border-bottom:1px solid var(--line)}
.fid td{padding:9px 12px 9px 0;border-bottom:1px solid var(--line-soft);vertical-align:middle}
.fid td:first-child{font-weight:500}
.fid .n{font-family:var(--mono);font-variant-numeric:tabular-nums;color:var(--muted)}
.fid .pct{font-family:var(--mono);font-variant-numeric:tabular-nums;font-weight:600;
  white-space:nowrap}
.fid .bar{width:46%;min-width:110px}
.bar span{display:block;height:7px;border-radius:1px;background:var(--line);position:relative}
.bar span i{position:absolute;inset:0 auto 0 0;border-radius:1px;display:block}
.good .pct,.good i{color:var(--ok)} .good i{background:var(--ok)}
.mixed .pct,.mixed i{color:var(--warn)} .mixed i{background:var(--warn)}
.bad .pct,.bad i{color:var(--bad)} .bad i{background:var(--bad)}
.legend{color:var(--muted);font-size:12.5px;margin:0 0 30px;max-width:66ch}

/* Trade panels. Only the fallback ones get a severity stripe. */
.trade{background:var(--panel);border:1px solid var(--line);border-top:2px solid var(--line);
  padding:14px 16px 16px;margin:0 0 16px}
.trade.is-fallback{border-top-color:var(--bad)}
.trade header{display:flex;align-items:baseline;gap:10px;flex-wrap:wrap;margin:0 0 12px}
.trade h2{font-size:15px;font-weight:600;margin:0;letter-spacing:-.005em}
.trig{color:var(--muted);font-weight:400}
.side{font-family:var(--mono);font-size:10.5px;font-weight:600;letter-spacing:.09em;
  padding:2px 7px;border:1px solid currentColor;border-radius:2px}
.side.long{color:var(--up)} .side.short{color:var(--down)}
.when{color:var(--muted);font-size:12px;font-family:var(--mono)}
.r{margin-left:auto;font-family:var(--mono);font-variant-numeric:tabular-nums;
  font-weight:600;font-size:14px}
.r.win{color:var(--ok)} .r.loss{color:var(--bad)}
.flag{color:var(--bad);font-size:12.5px;margin:0 0 10px;max-width:66ch}

.chart{width:100%;height:auto;display:block;background:transparent}
.chart text{font-family:var(--mono);font-size:11px}
.dur{fill:var(--fg);opacity:.05}
.conf{fill:none;stroke:var(--fg);stroke-width:1.2;stroke-dasharray:2 2;opacity:.75}
.exit{fill:var(--fg)}
.exit-t{fill:var(--fg);font-size:11px}
.band-risk{fill:var(--stop);opacity:.08}
.band-reward{fill:var(--target);opacity:.08}
.c-up{fill:var(--up);stroke:var(--up)}
.c-dn{fill:var(--down);stroke:var(--down)}
.wick{stroke-width:1;fill:none}
.lv{stroke-width:1.4;fill:none}
.lvt{font-size:11px}
.lv-key{stroke:var(--key);fill:var(--key);stroke-dasharray:5 4}
.lv-entry{stroke:var(--entry);fill:var(--entry)}
.lv-stop{stroke:var(--stop);fill:var(--stop)}
.lv-target{stroke:var(--target);fill:var(--target)}

dl{display:grid;grid-template-columns:max-content 1fr;gap:3px 16px;margin:12px 0 0;
  font-size:13px;align-items:baseline}
dt{color:var(--muted);font-size:11px;font-weight:600;letter-spacing:.07em;text-transform:uppercase}
dd{margin:0}
dd b{font-family:var(--mono);font-variant-numeric:tabular-nums;font-weight:500}
.q{color:var(--muted);font-size:12.5px}
</style>"""


def build_page(instrument: str, entry_style: str, trades, pip_size: float,
               candles: list[Candle], title: str, lede: str,
               table: dict[str, tuple[int, int]] | None = None) -> str:
    cards = []
    for tr in trades:
        window, entry_i, exit_i = _slice_for(candles, tr.entry_time, tr.exit_time)
        if not window or entry_i < 0:
            continue
        cards.append(_card(tr, _render_svg(window, entry_i, exit_i, tr, pip_size), pip_size))

    legend = ('<p class="legend">Below: individual trades, drawn from the same run. '
              'The dashed box is the confirmation candle &mdash; the thing the stop is '
              'supposed to be anchored to. Read each chart by asking whether the red stop '
              'line sits just past that box, or somewhere unrelated to it.</p>')

    return (f"<title>{html.escape(title)}</title>{STYLE}"
            f'<div class="wrap"><h1>{html.escape(title)}</h1>'
            f'<p class="lede">{html.escape(lede)}</p>'
            + (fidelity_html(table) if table else "")
            + (legend if cards else "")
            + "".join(cards) + "</div>")


def category(trade) -> str:
    """Which stop-placement rule actually produced this trade's stop."""
    return "fallback" if trade.stop_fallback_used else str(trade.trigger_type)


def stop_beyond_extreme(trade, candle) -> bool:
    """Bishop's rule: the stop sits beyond the extreme the confirmation made.

    For a long that is below the low that held; for a short, above the high
    that held. This is the one placement property that can be checked
    mechanically, so it is what the fidelity table reports.
    """
    if trade.direction == Direction.BULLISH:
        return trade.stop_loss < candle.low
    return trade.stop_loss > candle.high


def fidelity(trades, candles) -> dict[str, tuple[int, int]]:
    """Per-category (count, how many place the stop beyond the extreme)."""
    by_time = {c.time: c for c in candles}
    table: dict[str, list[int]] = {}
    for tr in trades:
        candle = by_time.get(tr.entry_time)
        if candle is None:
            continue
        row = table.setdefault(category(tr), [0, 0])
        row[0] += 1
        row[1] += stop_beyond_extreme(tr, candle)
    return {k: (v[0], v[1]) for k, v in sorted(table.items())}


def pick(trades, count: int, seed: int = 7):
    """A representative spread, not a highlight reel.

    Sampled evenly across the stop-placement categories, and within each
    across winners and losers, so the page cannot flatter the system by
    selection. Seeded, so a given run is reproducible.
    """
    rng = random.Random(seed)
    closed = [t for t in trades if t.r_multiple is not None]
    cats = sorted({category(t) for t in closed})
    per = max(count // max(len(cats) * 2, 1), 1)
    out = []
    for cat in cats:
        for winning in (False, True):
            group = [t for t in closed
                     if category(t) == cat and (t.r_multiple > 0) == winning]
            rng.shuffle(group)
            out.extend(group[:per])
    out.sort(key=lambda t: t.entry_time)
    return out


def fidelity_html(table: dict[str, tuple[int, int]]) -> str:
    rows = []
    for cat, (n, ok) in table.items():
        pct = 100 * ok / n if n else 0.0
        cls = "good" if pct > 95 else ("bad" if pct < 50 else "mixed")
        rows.append(
            f'<tr class="{cls}"><td>{html.escape(cat)}</td>'
            f'<td class="n">{n}</td>'
            f'<td class="bar"><span><i style="width:{pct:.1f}%"></i></span></td>'
            f'<td class="pct">{pct:.1f}%</td></tr>')
    return ('<table class="fid"><caption>Does the stop sit beyond the extreme the '
            "confirmation candle made &mdash; below the low that held for a long, above "
            "the high that held for a short? That is Bishop's rule, and it is the one "
            "placement property that can be checked mechanically. Measured on every "
            "trade in the run, not just the ones drawn below.</caption>"
            "<tr><th>stop rule</th><th>trades</th><th></th><th>follows the rule</th></tr>"
            + "".join(rows) + "</table>")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--instrument", required=True)
    ap.add_argument("--entry-style", default="aggressive")
    ap.add_argument("--source", default="dukascopy")
    ap.add_argument("--stop-anchor", default="trigger_wick")
    ap.add_argument("--count", type=int, default=12)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    pip_size = default_pip_size(args.instrument)
    trades = run_backtest(args.instrument, args.entry_style, source=args.source,
                          stop_anchor=args.stop_anchor)
    candles = load_candles(args.source, args.instrument, "H1")
    chosen = pick(trades, args.count, args.seed)
    table = fidelity(trades, candles)

    page = build_page(
        args.instrument, args.entry_style, chosen, pip_size, candles, table=table,
        title=f"{args.instrument} trade placements",
        lede=("Every stop the bot places, checked against the rule it is supposed to follow, then "
              "shown one trade at a time so the placements can be judged by eye rather than "
              "taken on trust. Trades below are sampled evenly across every stop rule and "
              "across winners and losers, so the selection cannot flatter the system."),
    )
    with open(args.out, "w") as fh:
        fh.write(page)
    print(f"{len(chosen)} trades -> {args.out}")


if __name__ == "__main__":
    main()
