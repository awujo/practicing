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
          direction=Direction.BULLISH, ambiguous=False):
    return Trade(entry_time=T0, entry=entry, stop=stop, target=1.1020,
                 direction=direction, level_price=entry, form=form,
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
