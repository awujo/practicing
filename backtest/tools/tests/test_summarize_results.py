import csv

import pytest

from ..summarize_results import load, qmr_breakdown, stats

FIELDS = ["trade_id", "status", "r_multiple", "qmr_test_count", "erl_capped"]


def write(path, rows):
    with open(path, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS)
        w.writeheader()
        for r in rows:
            w.writerow(r)


def rec(status, r, qmr=0, capped="False"):
    return {"trade_id": 1, "status": status, "r_multiple": r,
            "qmr_test_count": qmr, "erl_capped": capped}


def test_open_trades_are_excluded_not_counted_as_zero(tmp_path):
    """Folding an unfinished trade in at 0R silently drags every average
    toward zero, and the more recent the run the more of them there are."""
    p = tmp_path / "x.csv"
    write(p, [rec("closed_win", 3.0), rec("open", ""), rec("closed_loss", -1.0)])
    rows = load(str(p))
    assert len(rows) == 2
    assert stats(rows)["n"] == 2
    assert stats(rows)["total"] == pytest.approx(2.0)


def test_a_closed_trade_with_no_r_is_skipped_rather_than_guessed(tmp_path):
    p = tmp_path / "x.csv"
    write(p, [rec("closed_win", 3.0), rec("closed_loss", "")])
    assert len(load(str(p))) == 1


def test_stats_reports_win_rate_and_r_per_trade(tmp_path):
    p = tmp_path / "x.csv"
    write(p, [rec("closed_win", 3.0, capped="True"),
              rec("closed_loss", -1.0),
              rec("closed_win", 2.0)])
    s = stats(load(str(p)))
    assert s["n"] == 3
    assert s["win"] == pytest.approx(200.0 / 3)
    assert s["total"] == pytest.approx(4.0)
    assert s["per"] == pytest.approx(4.0 / 3)
    assert s["avg_win"] == pytest.approx(2.5)
    assert s["capped"] == 1


def test_stats_on_nothing_is_none_not_a_divide_by_zero():
    assert stats([]) is None


def test_qmr_buckets_split_at_two_prior_tests():
    """2+ is 4th man's threshold (video 17): a level tested and respected
    twice before it was finally disrespected. 0 and 1 stay separate
    because he explicitly says once is sometimes not enough."""
    rows = [rec("closed_win", 3.0, qmr=q) for q in (0, 1, 2, 5)]
    for r in rows:
        r["_r"] = r["r_multiple"]
    b = qmr_breakdown(rows)
    assert set(b) == {"0 tests", "1 test", "2+ tests"}
    assert len(b["2+ tests"]) == 2
    assert len(b["1 test"]) == 1


def test_a_missing_or_unparseable_qmr_count_falls_into_the_zero_bucket():
    """Rather than raising. An older CSV predating the column should
    still summarise -- it just has nothing to say about QMR."""
    rows = [rec("closed_win", 1.0, qmr=""), rec("closed_win", 1.0, qmr="n/a")]
    for r in rows:
        r["_r"] = 1.0
    assert len(qmr_breakdown(rows)["0 tests"]) == 2
