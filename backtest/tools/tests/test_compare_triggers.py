import argparse
import sys
from collections import Counter
from types import SimpleNamespace
from unittest import mock

import pytest

from ...engine.runner import TRIGGERS_SHIPPED, TRIGGERS_TAUGHT
from ...engine.trade_log import TradeRecord
from ..compare_triggers import MODES, _dump, _stats, main
from ..live_flags import LIVE_FIXED_FLAGS, LIVE_LAUNCH_FLAGS


class Rec:
    def __init__(self, exit_reason, r_multiple, trigger_type="engulfing"):
        self.exit_reason = exit_reason
        self.r_multiple = r_multiple
        self.trigger_type = trigger_type


def test_it_compares_the_two_real_trigger_sets():
    """Not hand-written copies. If TRIGGERS_TAUGHT gains a pattern, this
    tool must compare the new set, not a stale literal."""
    assert MODES["shipped"] is TRIGGERS_SHIPPED
    assert MODES["taught"] is TRIGGERS_TAUGHT


def test_stats_breaks_results_down_by_trigger():
    """The breakdown is the point. A headline alone is what made the
    2026-09-02 A/B read as a verdict on stops when it had actually
    measured "take only plug-and-play trades"."""
    s = _stats([
        Rec("target_hit", 3.0, "breakout"),
        Rec("target_hit", 2.0, "open_close"),
        Rec("stop_hit", -1.0, "breakout"),
        Rec("still_open", None, "fourth_man"),
    ])
    assert s["n"] == 3
    assert s["by_trigger"] == Counter({"breakout": 2, "open_close": 1})
    assert s["total"] == pytest.approx(4.0)
    assert s["avg_win"] == pytest.approx(2.5)


def test_open_trades_are_excluded_rather_than_counted_as_zero():
    assert _stats([Rec("still_open", None)])["n"] == 0
    assert _stats([Rec("still_open", None)])["per"] == 0.0


def test_the_two_modes_write_to_separate_csvs(tmp_path):
    rec = TradeRecord(trade_id=1, instrument="EURUSD", entry_time="2026-01-01",
                      status="closed_win", r_multiple=3.0)
    args = SimpleNamespace(dump_trades=str(tmp_path), entry_style="conservative")
    _dump([rec], "EURUSD", "shipped", args)
    _dump([rec], "EURUSD", "taught", args)
    assert sorted(p.name for p in tmp_path.iterdir()) == [
        "EURUSD_conservative.csv", "EURUSD_conservative_taughttriggers.csv"]


def test_defaults_match_the_deployed_launch_flags():
    """Same guard the other comparison tools carry -- review finding 8."""
    parsed = {}
    real = argparse.ArgumentParser.parse_args

    def capture(self, *a, **k):
        parsed.update(vars(real(self, *a, **k)))
        raise SystemExit(0)

    argv = ["compare_triggers", "--instruments", "NONE_AT_ALL"]
    with mock.patch.object(argparse.ArgumentParser, "parse_args", capture), \
            mock.patch.object(sys, "argv", argv):
        with pytest.raises(SystemExit):
            main()

    assert parsed["origin_kind"] == LIVE_LAUNCH_FLAGS["origin_kind"]
    assert parsed["stop_anchor"] == LIVE_LAUNCH_FLAGS["stop_anchor"]
    assert parsed["min_reward_r"] == LIVE_FIXED_FLAGS["min_reward_r"]
    assert parsed["wick_based_sweep_break"] is False
    assert parsed["no_avoid_rollover"] is False
