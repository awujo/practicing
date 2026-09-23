"""
The renderer must survive the CSV round trip, which is the only way it
is ever actually used.

The first version of this tool was smoke-tested by handing `render()` a
dict built in memory, with `entry_time` as a real datetime. That passed,
and the tool then died on the first trade it was pointed at: a CSV
stores times as ISO STRINGS (`write_trade_log` calls `.isoformat()`)
while `Candle.time` is a `pd.Timestamp`, and `Timestamp <= str` raises
TypeError rather than comparing. Every panel is windowed by that
comparison.

So these tests go through `write_trade_log` and `csv.DictReader` rather
than constructing rows by hand. A fixture that skips the serialisation
step cannot catch a serialisation bug.
"""

from __future__ import annotations

import csv
import random

import pandas as pd
import pytest

from ...engine.candles import Candle
from ...engine.structure import Direction
from ...engine.trade_log import TradeRecord, write_trade_log
from .. import render_setup

T0 = pd.Timestamp("2026-01-01")


def _c(i, o, h, l, c):
    return Candle(time=T0 + pd.Timedelta(hours=i), open=o, high=h, low=l,
                  close=c, volume=0)


@pytest.fixture
def series():
    """H1 with a deliberate reaction: touch at 280, lift to a minor high
    at 283, pullback, then a close clearing it at 286."""
    random.seed(1)
    h1, px = [], 104.0
    for i in range(280):
        o = px
        c = px - abs(random.gauss(0.03, 0.06))
        h1.append(_c(i, o, max(o, c) + .05, min(o, c) - .05, c))
        px = c
    level = px - 0.10
    h1 += [
        _c(280, px, px + .05, level, level + .05),
        _c(281, level + .05, level + .40, level, level + .35),
        _c(282, level + .35, level + .90, level + .30, level + .85),
        _c(283, level + .85, level + 1.20, level + .80, level + 1.10),
        _c(284, level + 1.1, level + 1.15, level + .55, level + .60),
        _c(285, level + .60, level + .75, level + .50, level + .70),
        _c(286, level + .70, level + 1.60, level + .65, level + 1.45),
    ]
    for i in range(287, 320):
        o = h1[-1].close
        c = o + abs(random.gauss(.05, .06))
        h1.append(_c(i, o, max(o, c) + .05, min(o, c) - .05, c))
    return h1, level


@pytest.fixture
def rendered(series, tmp_path, monkeypatch):
    h1, level = series
    data = {
        "H1": h1,
        "H4": [_c(i * 4, 100, 101, 99, 100.5) for i in range(90)],
        "D": [_c(i * 24, 100, 101, 99, 100.5) for i in range(60)],
        "W": [_c(i * 168, 100, 101, 99, 100.5) for i in range(30)],
    }
    monkeypatch.setattr(render_setup, "load_candles",
                        lambda source, symbol, tf: data[tf])
    monkeypatch.setattr(render_setup, "default_pip_size", lambda symbol: 0.01)

    record = TradeRecord(
        trade_id=1, instrument="AUDJPY", entry_time=h1[286].time,
        exit_time=h1[300].time, direction=Direction.BULLISH,
        trigger_type="breakout", stop_kind="breakout",
        entry_price=h1[286].close, stop_loss=level - 0.05,
        primary_target=level + 6.0, key_level_price=level,
        key_level_shape="V", exit_reason="target_hit", r_multiple=4.0,
        aligned_timeframes="Daily,H4", bias_weekly=Direction.BULLISH,
        bias_daily=Direction.BULLISH, bias_h4=Direction.BULLISH)

    csv_path = tmp_path / "AUDJPY_conservative_slk.csv"
    write_trade_log([record], str(csv_path))
    with open(csv_path, newline="") as fh:
        rows = list(csv.DictReader(fh))

    out = tmp_path / "setup.html"
    render_setup.render("AUDJPY", rows, "dukascopy", "conservative", str(out))
    return rows, out.read_text(), level


def test_the_csv_round_trip_is_what_gets_rendered(rendered):
    """The regression this file exists for. If `entry_time` ever stops
    being parsed, every panel below is empty and this fails first."""
    rows, html, _ = rendered
    assert isinstance(rows[0]["entry_time"], str)
    assert render_setup._when(rows[0]["entry_time"]) == pd.Timestamp(
        rows[0]["entry_time"])


def test_all_four_timeframes_are_drawn(rendered):
    """The whole point over render_trades: a clean H1 trigger against a
    weekly that says the opposite is still a bad trade, and only the
    cascade shows it."""
    _, html, _ = rendered
    assert html.count("<svg") == 4
    for title in ("Weekly", "Daily", "H4", "H1"):
        assert title in html


def test_the_reaction_geometry_is_marked_for_a_break_trigger(rendered):
    """Touch, reaction low and minor swing high -- what the detector
    claims it saw, which is the thing under suspicion."""
    _, html, _ = rendered
    assert ">touch<" in html
    assert "reaction low" in html
    assert "minor high (recomputed)" in html


def test_recomputed_marks_are_labelled_as_recomputed(rendered):
    """Everything else on the page is a value the engine RECORDED. The
    reaction marks are not, and a reader must be able to tell which is
    which -- otherwise the chart can agree with the code purely because
    both ran the same possibly-wrong function."""
    _, html, _ = rendered
    assert "recomputed" in html
    assert "not evidence on their own" in html


def test_recorded_levels_come_from_the_row_not_recomputed(rendered):
    """Entry, stop, target and key level are drawn from the CSV, so the
    chart cannot flatter the engine by drawing what it meant."""
    rows, html, level = rendered
    assert render_setup._fmt(float(rows[0]["stop_loss"]), 0.01) in html
    assert render_setup._fmt(float(rows[0]["primary_target"]), 0.01) in html
    assert render_setup._fmt(level, 0.01) in html


def test_a_row_with_an_unparseable_time_is_skipped_not_fatal(series, tmp_path,
                                                             monkeypatch):
    """One bad row must not take the whole page down -- the page is the
    diagnostic, and losing it is worse than losing a trade from it."""
    h1, level = series
    monkeypatch.setattr(render_setup, "load_candles",
                        lambda source, symbol, tf: h1)
    monkeypatch.setattr(render_setup, "default_pip_size", lambda symbol: 0.01)
    rows = [{"entry_time": "not a date", "trade_id": "9", "direction": "bullish",
             "exit_reason": "stop_hit", "r_multiple": "-1.0"}]
    out = tmp_path / "setup.html"
    render_setup.render("AUDJPY", rows, "dukascopy", "conservative", str(out))
    assert "<svg" not in out.read_text()
