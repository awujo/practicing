"""
Dependency-free inline-SVG candlestick renderer for the on-demand trade
viewer -- same "no CDN, no JS framework" philosophy as report.py's equity
curve (backtest/engine/report.py), just extended to full OHLC candles
plus price-level and entry/exit markers, so a trade's actual stop/target/
key-level placement is visible against real price action -- the same way
you'd eyeball one of Bishop's own chart examples -- instead of just being
logged as numbers in a CSV row.
"""

MARKER_COLORS = {
    "entry": "#2563eb",
    "stop": "#dc2626",
    "target": "#16a34a",
    "key_level": "#a855f7",
}


def render_candlestick_svg(candles, price_markers=None, entry_index=None, exit_index=None,
                            title="", width=920, height=340) -> str:
    """`candles`: a time-ordered list of engine.candles.Candle. `price_markers`:
    dict of label -> price (labels matching MARKER_COLORS render in that
    color; unrecognized labels fall back to grey). `entry_index`/
    `exit_index`: positions within `candles` to mark with a vertical dashed
    line, or None to omit."""
    if not candles:
        return f'<p><em>No candle data in this window{": " + title if title else ""}.</em></p>'

    price_markers = price_markers or {}
    margin_left, margin_right, margin_top, margin_bottom = 8, 130, 24, 10
    plot_w = width - margin_left - margin_right
    plot_h = height - margin_top - margin_bottom
    n = len(candles)
    candle_w = plot_w / n

    prices = [c.low for c in candles] + [c.high for c in candles]
    prices += [p for p in price_markers.values() if p is not None]
    lo, hi = min(prices), max(prices)
    span = (hi - lo) or 1.0

    def y(price):
        return margin_top + plot_h - ((price - lo) / span) * plot_h

    def xc(i):
        return margin_left + (i + 0.5) * candle_w

    parts = []
    for i, c in enumerate(candles):
        cx = xc(i)
        up = c.close >= c.open
        color = "#16a34a" if up else "#dc2626"
        y_o, y_c = y(c.open), y(c.close)
        top, bottom = (y_c, y_o) if up else (y_o, y_c)
        bw = max(candle_w * 0.6, 1.0)
        parts.append(
            f'<line x1="{cx:.1f}" y1="{y(c.high):.1f}" x2="{cx:.1f}" y2="{y(c.low):.1f}" '
            f'stroke="{color}" stroke-width="1"/>'
            f'<rect x="{cx - bw / 2:.1f}" y="{top:.1f}" width="{bw:.1f}" '
            f'height="{max(bottom - top, 1.0):.1f}" fill="{color}"/>'
        )

    for idx, color in ((entry_index, "#2563eb"), (exit_index, "#111827")):
        if idx is None or not (0 <= idx < n):
            continue
        cx = xc(idx)
        parts.append(
            f'<line x1="{cx:.1f}" y1="{margin_top}" x2="{cx:.1f}" y2="{height - margin_bottom}" '
            f'stroke="{color}" stroke-width="1" stroke-dasharray="2,2" opacity="0.6"/>'
        )

    for label, price in price_markers.items():
        if price is None:
            continue
        color = MARKER_COLORS.get(label, "#666")
        yy = y(price)
        parts.append(
            f'<line x1="{margin_left}" y1="{yy:.1f}" x2="{width - margin_right}" y2="{yy:.1f}" '
            f'stroke="{color}" stroke-width="1.25" stroke-dasharray="6,3"/>'
            f'<text x="{width - margin_right + 4}" y="{yy + 3:.1f}" font-size="11" fill="{color}">'
            f'{label} {price:g}</text>'
        )

    title_svg = f'<text x="{margin_left}" y="16" font-size="13" fill="#333">{title}</text>' if title else ""

    return (
        f'<svg viewBox="0 0 {width} {height}" xmlns="http://www.w3.org/2000/svg" '
        f'style="background:#fff;border:1px solid #ddd;max-width:100%">'
        f'{title_svg}{"".join(parts)}</svg>'
    )
