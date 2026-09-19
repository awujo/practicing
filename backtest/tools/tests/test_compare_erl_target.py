import argparse
import sys
from unittest import mock

import pytest

from ..compare_erl_target import MODES, _stats, main
from ..live_flags import LIVE_FIXED_FLAGS, LIVE_LAUNCH_FLAGS


class Rec:
    def __init__(self, exit_reason, r_multiple, erl_capped=False):
        self.exit_reason = exit_reason
        self.r_multiple = r_multiple
        self.erl_capped = erl_capped


def test_stats_counts_only_closed_trades():
    recs = [
        Rec("target_hit", 3.0),
        Rec("target_hit", 5.0, erl_capped=True),
        Rec("stop_hit", -1.0, erl_capped=True),
        Rec("still_open", None),          # excluded
        Rec("target_hit", None),          # excluded: no R to add
    ]
    s = _stats(recs)
    assert s["n"] == 3
    assert s["win_pct"] == pytest.approx(200.0 / 3)
    assert s["total_r"] == pytest.approx(7.0)
    assert s["per_trade"] == pytest.approx(7.0 / 3)
    assert s["avg_win"] == pytest.approx(4.0)
    assert s["capped"] == 2


def test_stats_on_no_closed_trades_does_not_divide_by_zero():
    s = _stats([Rec("still_open", None)])
    assert s == {"n": 0, "win_pct": 0.0, "total_r": 0.0, "per_trade": 0.0,
                 "capped": 0, "avg_win": 0.0}


def test_it_compares_exactly_the_two_target_readings():
    """Not a sweep. The whole point is that these two are the same rule
    read two ways and differ only on trades whose ERL is beyond 3R."""
    assert MODES == ("cap", "target")


def test_defaults_match_the_deployed_launch_flags():
    """Same guard as compare_liquidity_modes' and count_signals'. A tool
    that measures run_backtest's dataclass defaults instead of the
    deployed flags reports on a strategy nobody flies -- review finding
    8, which has since bitten twice."""
    parsed = {}
    real = argparse.ArgumentParser.parse_args

    def capture(self, *a, **k):
        parsed.update(vars(real(self, *a, **k)))
        raise SystemExit(0)

    argv = ["compare_erl_target", "--instruments", "NONE_AT_ALL"]
    with mock.patch.object(argparse.ArgumentParser, "parse_args", capture), \
            mock.patch.object(sys, "argv", argv):
        with pytest.raises(SystemExit):
            main()

    assert parsed["origin_kind"] == LIVE_LAUNCH_FLAGS["origin_kind"]
    assert parsed["stop_anchor"] == LIVE_LAUNCH_FLAGS["stop_anchor"]
    assert parsed["min_reward_r"] == LIVE_FIXED_FLAGS["min_reward_r"]
    # Inverted flags: absent means the behaviour is ON, which is what the
    # bots run. Plain `is False`, not a compound expression -- an earlier
    # version of this assertion elsewhere was a tautology.
    assert parsed["wick_based_sweep_break"] is False   # -> close-based ON
    assert parsed["no_avoid_rollover"] is False        # -> rollover avoidance ON
