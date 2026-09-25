"""
The reporting layer. Tested through a real cache round trip, because the
last tool that went out untested crashed on its first real use for a
reason my smoke test had skipped: it passed a datetime directly and never
went through the CSV.
"""

from __future__ import annotations

import random

import pandas as pd
import pytest

from ...engine.structure import Direction
from ..replay import Trade
from ..run import _combine, _stats, run_one

T0 = pd.Timestamp("2026-01-01")


def trade(r, outcome, entry=1.1000, stop=1.0990, form="engulf",
          direction=Direction.BULLISH, ambiguous=False, hour=0):
    """`hour` sets the EXIT time, which is what the curve is ordered by."""
    return Trade(entry_time=T0, entry=entry, stop=stop, target=1.1020,
                 direction=direction, level_price=entry, form=form,
                 exit_time=T0 + pd.Timedelta(hours=hour),
                 outcome=outcome, r=r, same_candle_stop=ambiguous)


def test_no_trades_is_an_empty_result_not_a_division_by_zero():
    assert _stats([], 0.0001, 1.0) == {}
    assert _combine([("EURUSD", [], 0.0001)], 1.0) == {}


def test_spread_is_charged_against_each_trade_s_own_risk():
    """A flat charge per round trip assumes every trade risks the same
    distance. A 10-pip stop pays 0.1R on a 1-pip spread; a 1-pip stop pays
    a full 1R for the same spread, and a flat figure hides that."""
    wide = _stats([trade(1.0, "target", entry=1.1000, stop=1.0990)],
                  0.0001, 1.0)      # 10 pips of risk
    tight = _stats([trade(1.0, "target", entry=1.1000, stop=1.0999)],
                   0.0001, 1.0)     # 1 pip of risk

    assert wide["gross"] == pytest.approx(1.0)
    assert wide["net"] == pytest.approx(0.9), "1 pip on 10 pips of risk"
    assert tight["net"] == pytest.approx(0.0), "1 pip on 1 pip of risk"


def test_zero_spread_reports_gross_unchanged():
    s = _stats([trade(2.0, "target"), trade(-1.0, "stop")], 0.0001, 0.0)
    assert s["gross"] == pytest.approx(1.0)
    assert s["net"] == pytest.approx(1.0)


def test_the_win_rate_counts_targets_only():
    s = _stats([trade(3.0, "target"), trade(-1.0, "stop"),
                trade(-1.0, "stop"), trade(-1.0, "stop")], 0.0001, 0.0)
    assert s["n"] == 4
    assert s["win"] == pytest.approx(25.0)


def test_ambiguous_fills_are_counted_and_not_hidden():
    s = _stats([trade(-1.0, "stop", ambiguous=True), trade(-1.0, "stop")],
               0.0001, 0.0)
    assert s["ambiguous"] == 1, "the assumption has to be countable"


def test_combining_uses_each_instrument_s_own_pip_size():
    """The reason the combined line is built per instrument rather than
    recomputed with one pip: a JPY pair's pip is 0.01, so costing it at
    0.0001 would overstate its risk in pips a hundredfold and make its
    spread look free."""
    eur = ("EURUSD", [trade(1.0, "target", entry=1.1000, stop=1.0990)], 0.0001)
    jpy = ("USDJPY", [trade(1.0, "target", entry=150.00, stop=149.90)], 0.01)

    got = _combine([eur, jpy], spread=1.0)
    assert got["n"] == 2
    assert got["gross"] == pytest.approx(2.0)
    # both risk 10 pips on their own scale, so both pay 0.1R
    assert got["net"] == pytest.approx(1.8)

    wrong = _stats([eur[1][0], jpy[1][0]], 0.0001, 1.0)
    assert wrong["net"] > got["net"], \
        "one pip size across both would have understated the cost"


def test_the_weighted_win_rate_is_not_a_mean_of_means():
    """Ten trades at 50% and one at 0% is 45.5%, not 25%."""
    many = ("A", [trade(1.0, "target")] * 5 + [trade(-1.0, "stop")] * 5, 0.0001)
    one = ("B", [trade(-1.0, "stop")], 0.0001)
    assert _combine([many, one], 0.0)["win"] == pytest.approx(100 * 5 / 11)


def test_run_one_goes_through_the_real_cache_and_prints(tmp_path, capsys,
                                                        monkeypatch):
    """A round trip through the CSV cache, which is what the runner will
    actually meet. A missing series must be reported and skipped rather
    than replaying a cascade with no Weekly in it."""
    from ...data_pipeline import cache

    monkeypatch.setattr(cache, "DATA_ROOT", str(tmp_path))

    random.seed(11)
    px, rows = 1.1000, []
    for i in range(2400):
        o = px
        px += random.gauss(0, 0.0009)
        rows.append({"time": (T0 + pd.Timedelta(hours=i)).isoformat(),
                     "open": o, "high": max(o, px) + 0.0004,
                     "low": min(o, px) - 0.0004, "close": px, "volume": 0})
    def agg(hours):
        out = []
        for i in range(0, len(rows) - hours + 1, hours):
            chunk = rows[i:i + hours]
            out.append({"time": chunk[0]["time"], "open": chunk[0]["open"],
                        "high": max(c["high"] for c in chunk),
                        "low": min(c["low"] for c in chunk),
                        "close": chunk[-1]["close"], "volume": 0})
        return out

    for code, series in (("H1", rows), ("H4", agg(4)), ("D", agg(24)),
                         ("W", agg(168))):
        assert cache.append("dukascopy", "EURUSD", code, series)

    trades = run_one("EURUSD", n=2, spread=1.0, source="dukascopy")
    out = capsys.readouterr().out

    assert "EURUSD  n=2" in out
    assert "ALL" in out
    assert "ambiguous fills" in out or not trades
    for t in trades:
        assert t.r is not None, "a settled trade must have an R"
        assert t.outcome in {"target", "stop"}, "open trades are excluded"


def test_a_missing_series_is_reported_rather_than_replayed(tmp_path, capsys,
                                                          monkeypatch):
    from ...data_pipeline import cache

    monkeypatch.setattr(cache, "DATA_ROOT", str(tmp_path))
    assert run_one("EURUSD", n=2, spread=0.0, source="dukascopy") == []
    assert "cannot load" in capsys.readouterr().err


def test_the_loader_cache_is_released_between_instruments(tmp_path,
                                                          monkeypatch):
    """The loader's cache never evicts, which is right for the live bot
    and wrong for a batch walk over 27 instruments: EURUSD's H1 alone is
    ~155k Candle objects. The live VPS is already swapping and the live
    bots share the box, so a batch job that grows without bound there can
    push the thing that is actually trading into swap."""
    from ...data_pipeline import cache
    from ...engine import candles

    monkeypatch.setattr(cache, "DATA_ROOT", str(tmp_path))
    rows = [{"time": (T0 + pd.Timedelta(hours=i)).isoformat(),
             "open": 1.1, "high": 1.1005, "low": 1.0995, "close": 1.1,
             "volume": 0} for i in range(300)]
    for code in ("H1", "H4", "D", "W"):
        cache.append("dukascopy", "EURUSD", code, rows)

    candles.clear_cache()
    run_one("EURUSD", n=2, spread=0.0, source="dukascopy")
    assert not candles._cache, "the parsed series are still held"


# --- drawdown, the headline ---------------------------------------------

def test_drawdown_is_peak_to_trough_not_the_total():
    """R/trade alone cannot say whether a system is tradeable. A set of
    trades summing to +2R can still have gone 3R underwater on the way,
    and that hole is what decides position size."""
    trades = [trade(5.0, "target", hour=1),
              trade(-1.0, "stop", hour=2),
              trade(-1.0, "stop", hour=3),
              trade(-1.0, "stop", hour=4),
              trade(-1.0, "stop", hour=5),
              trade(1.0, "target", hour=6)]
    s = _stats(trades, 0.0001, 0.0)

    assert s["net"] == pytest.approx(2.0)
    assert s["max_dd"] == pytest.approx(4.0), "peak +5, trough +1"
    assert s["worst_streak"] == 4


def test_the_curve_is_ordered_by_exit_not_entry():
    """A trade that opens early and closes late belongs where its result
    landed. Ordering by entry draws a smoother curve than anyone lived."""
    early_exit_loss = trade(-1.0, "stop", hour=1)
    late_exit_win = trade(5.0, "target", hour=9)
    # passed win-first, but the loss settled first
    s = _stats([late_exit_win, early_exit_loss], 0.0001, 0.0)
    assert s["max_dd"] == pytest.approx(1.0), \
        "the loss landed first, so the curve dipped before it rose"


def test_a_system_that_only_wins_has_no_drawdown():
    s = _stats([trade(1.0, "target", hour=1), trade(1.0, "target", hour=2)],
               0.0001, 0.0)
    assert s["max_dd"] == pytest.approx(0.0)
    assert s["worst_streak"] == 0


def test_pooled_drawdown_is_merged_not_summed():
    """Two instruments whose bad stretches happen at different times do
    NOT add up: while one is drawing down the other is recovering, and
    summing the holes claims a loss the portfolio never took.

    The holes have to INTERLEAVE for that to show. A first version of
    this test put A's losses at hours 2-3 and B's at 4-5, which are
    consecutive once merged, so they compounded into one 4R slide and the
    sum and the merge agreed -- the test was asserting something its own
    fixture could not demonstrate.
    """
    a = ("A", [trade(-2.0, "stop", hour=1), trade(3.0, "target", hour=4)],
         0.0001)
    b = ("B", [trade(3.0, "target", hour=2), trade(-2.0, "stop", hour=3)],
         0.0001)

    each = _stats(a[1], 0.0001, 0.0)["max_dd"] + _stats(b[1], 0.0001, 0.0)["max_dd"]
    pooled = _combine([a, b], 0.0)

    assert each == pytest.approx(4.0), "2R each on its own"
    assert pooled["n"] == 4
    assert pooled["max_dd"] == pytest.approx(2.0), \
        "B's win covered A's loss, so the portfolio was never 4R down"
    assert pooled["max_dd"] < each
    assert pooled["worst_streak"] == 1, "the losses never ran together"


def test_the_profit_factor_is_gross_win_over_gross_loss():
    s = _stats([trade(3.0, "target", hour=1), trade(-1.0, "stop", hour=2)],
               0.0001, 0.0)
    assert s["profit_factor"] == pytest.approx(3.0)
    assert s["avg_win"] == pytest.approx(3.0)
    assert s["avg_loss"] == pytest.approx(1.0)


def test_spread_is_charged_before_the_drawdown_is_walked():
    """Costs belong inside the curve. Charged afterwards they would shrink
    the total while leaving the hole looking shallower than it was."""
    trades = [trade(1.0, "target", hour=1), trade(-1.0, "stop", hour=2)]
    free = _stats(trades, 0.0001, 0.0)
    costed = _stats(trades, 0.0001, 1.0)      # 10 pips risk -> 0.1R each
    assert costed["max_dd"] > free["max_dd"], \
        "the losing leg costs more than 1R once spread is in the curve"


# --- the CSV, written as it goes ----------------------------------------

def test_trades_are_dumped_per_instrument_as_each_one_finishes(tmp_path,
                                                              monkeypatch):
    """A run that dies partway -- a closed terminal, an OOM -- must keep
    what it already computed. This project has lost whole runs to a
    dropped SSH session twice."""
    import csv as csv_mod

    from ...data_pipeline import cache

    monkeypatch.setattr(cache, "DATA_ROOT", str(tmp_path / "data"))

    random.seed(11)
    px, rows = 1.1000, []
    for i in range(2400):
        o = px
        px += random.gauss(0, 0.0009)
        rows.append({"time": (T0 + pd.Timedelta(hours=i)).isoformat(),
                     "open": o, "high": max(o, px) + 0.0004,
                     "low": min(o, px) - 0.0004, "close": px, "volume": 0})

    def agg(hours):
        out = []
        for i in range(0, len(rows) - hours + 1, hours):
            chunk = rows[i:i + hours]
            out.append({"time": chunk[0]["time"], "open": chunk[0]["open"],
                        "high": max(c["high"] for c in chunk),
                        "low": min(c["low"] for c in chunk),
                        "close": chunk[-1]["close"], "volume": 0})
        return out

    for code, series in (("H1", rows), ("H4", agg(4)), ("D", agg(24)),
                         ("W", agg(168))):
        cache.append("dukascopy", "EURUSD", code, series)

    out_dir = tmp_path / "results"
    trades = run_one("EURUSD", n=2, spread=1.0, source="dukascopy",
                     dump_dir=str(out_dir))
    assert trades, "the fixture must trade or this proves nothing"

    path = out_dir / "EURUSD_slk_n2.csv"
    assert path.exists(), "nothing was written"
    with open(path) as handle:
        got = list(csv_mod.DictReader(handle))

    assert len(got) == len(trades)
    assert got[0]["form"] in {"engulf", "inducement", "breakout", "sweep_break"}
    assert got[0]["liquidity"], "the entitling liquidity has to survive to here"
    assert got[0]["outcome"] in {"target", "stop"}
