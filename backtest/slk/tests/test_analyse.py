"""
The measurement tool. Tested through real CSVs, because it exists to
settle a question and a tool that miscounts would settle it wrongly.
"""

from __future__ import annotations

import csv

import pytest

from ..analyse import _rows, _stats, covers_level, distance_r


def write(tmp_path, name, rows):
    path = tmp_path / name
    with open(path, "w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["entry_time", "exit_time", "direction", "form",
                         "entry", "stop", "target", "exit", "outcome", "r",
                         "setup_price", "liquidity", "mitigation",
                         "same_candle_stop"])
        for row in rows:
            writer.writerow(row)
    return path


def row(direction="bullish", entry=1.1000, stop=1.0990, setup=1.0985,
        outcome="target", r=2.0, form="engulf", ambiguous=0):
    return ["t0", "t1", direction, form, entry, stop, 1.1100, 1.1100,
            outcome, r, setup, 1.0980, 1.1005, ambiguous]


def test_a_buy_covers_its_level_when_the_stop_sits_at_or_below_it():
    """The level is inside the trade's risk: price going through it takes
    you out, so you were genuinely trading that level."""
    covered = {"direction": "bullish", "_stop": 1.0985, "_setup": 1.0990,
               "_risk": 0.0015}
    assert covers_level(covered)

    loose = {"direction": "bullish", "_stop": 1.0995, "_setup": 1.0990,
             "_risk": 0.0015}
    assert not covers_level(loose), "the stop never reaches the level"


def test_a_sell_mirrors_it():
    assert covers_level({"direction": "bearish", "_stop": 1.1010,
                         "_setup": 1.1000, "_risk": 0.001})
    assert not covers_level({"direction": "bearish", "_stop": 1.0990,
                             "_setup": 1.1000, "_risk": 0.001})


def test_a_zero_risk_trade_covers_nothing_rather_than_dividing_by_zero():
    assert not covers_level({"direction": "bullish", "_stop": 1.1,
                             "_setup": 1.1, "_risk": 0.0})
    assert distance_r({"_entry": 1.1, "_setup": 1.09, "_risk": 0.0}) == 0.0


def test_distance_is_measured_in_the_trade_s_own_risk():
    """Pips would not compare across instruments; R does."""
    assert distance_r({"_entry": 1.1000, "_setup": 1.0980,
                       "_risk": 0.0010}) == pytest.approx(2.0)


def test_open_trades_are_excluded_from_every_figure(tmp_path):
    write(tmp_path, "EURUSD_slk_n2.csv", [
        row(outcome="target", r=2.0),
        row(outcome="open", r=""),
        row(outcome="stop", r=-1.0),
    ])
    got = list(_rows(str(tmp_path)))
    assert len(got) == 2, "the open one must not reach the statistics"


def test_a_row_with_a_missing_number_is_skipped_not_guessed(tmp_path):
    """The CSV is written by a run that may have died partway."""
    write(tmp_path, "EURUSD_slk_n2.csv", [
        row(outcome="target", r=2.0),
        ["t0", "t1", "bullish", "engulf", "", "", "", "", "stop", "-1.0",
         "", "", "", 0],
    ])
    assert len(list(_rows(str(tmp_path)))) == 1


def test_the_instrument_comes_from_the_filename(tmp_path):
    write(tmp_path, "GBPJPY_slk_n2.csv", [row()])
    assert list(_rows(str(tmp_path)))[0]["_instrument"] == "GBPJPY"


def test_profit_factor_and_win_rate(tmp_path):
    write(tmp_path, "EURUSD_slk_n2.csv", [
        row(outcome="target", r=3.0),
        row(outcome="stop", r=-1.0),
        row(outcome="stop", r=-1.0),
    ])
    s = _stats(list(_rows(str(tmp_path))))
    assert s["n"] == 3
    assert s["win"] == pytest.approx(100 / 3)
    assert s["total"] == pytest.approx(1.0)
    assert s["pf"] == pytest.approx(1.5)


def test_no_rows_is_none_not_a_crash():
    assert _stats([]) is None
