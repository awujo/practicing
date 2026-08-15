import pandas as pd

from ...engine.candles import Candle
from ..charts import render_candlestick_svg


def C(i, o, h, l, c):
    return Candle(pd.Timestamp("2024-01-01") + pd.Timedelta(hours=i), o, h, l, c, 1000)


def test_render_candlestick_svg_empty_shows_placeholder():
    assert "No candle data" in render_candlestick_svg([])


def test_render_candlestick_svg_renders_one_rect_and_wick_per_candle():
    candles = [C(0, 1.1000, 1.1010, 1.0995, 1.1005), C(1, 1.1005, 1.1020, 1.1000, 1.1018)]
    svg = render_candlestick_svg(candles)
    assert svg.count("<rect") == 2
    assert svg.count("<line") == 2  # one wick per candle, no markers
    assert "<svg" in svg


def test_render_candlestick_svg_draws_a_dashed_line_and_label_per_price_marker():
    candles = [C(0, 1.1000, 1.1010, 1.0995, 1.1005)]
    svg = render_candlestick_svg(candles, price_markers={"entry": 1.1002, "stop": 1.0990, "target": 1.1030})
    assert svg.count("stroke-dasharray=\"6,3\"") == 3
    assert "entry 1.1002" in svg
    assert "stop 1.099" in svg
    assert "target 1.103" in svg


def test_render_candlestick_svg_skips_none_markers():
    candles = [C(0, 1.1000, 1.1010, 1.0995, 1.1005)]
    svg = render_candlestick_svg(candles, price_markers={"entry": 1.1002, "key_level": None})
    assert svg.count("stroke-dasharray=\"6,3\"") == 1


def test_render_candlestick_svg_marks_entry_and_exit_index():
    candles = [C(i, 1.10, 1.101, 1.099, 1.100) for i in range(5)]
    svg = render_candlestick_svg(candles, entry_index=1, exit_index=3)
    # 5 wicks + 2 entry/exit vertical markers, all as <line> elements with dasharray "2,2"
    assert svg.count("stroke-dasharray=\"2,2\"") == 2


def test_render_candlestick_svg_ignores_out_of_range_entry_exit_index():
    candles = [C(i, 1.10, 1.101, 1.099, 1.100) for i in range(3)]
    svg = render_candlestick_svg(candles, entry_index=None, exit_index=99)
    assert svg.count("stroke-dasharray=\"2,2\"") == 0
