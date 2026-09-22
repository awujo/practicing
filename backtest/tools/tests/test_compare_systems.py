import argparse
import sys
from types import SimpleNamespace
from unittest import mock

import pytest

from ...engine.runner import TRIGGERS_SHIPPED, TRIGGERS_TAUGHT
from ...engine.trade_log import TradeRecord
from ..compare_systems import SHIPPED, TAUGHT, VARIANTS, _dump, _stats, main
from ..live_flags import LIVE_FIXED_FLAGS, LIVE_LAUNCH_FLAGS


class Rec:
    def __init__(self, exit_reason, r_multiple, trigger_type="engulfing"):
        self.exit_reason = exit_reason
        self.r_multiple = r_multiple
        self.trigger_type = trigger_type


def test_shipped_overrides_nothing():
    """The baseline has to be run_backtest's own defaults, or "shipped"
    is measuring something nobody ships."""
    assert SHIPPED == {}


def test_taught_is_the_three_rules_the_source_states_as_rules():
    """Triggers, the ERL target, and the bias caveat. Each has the
    source stating it as the rule rather than as a preference."""
    assert TAUGHT == {
        "confirmation_triggers": TRIGGERS_TAUGHT,
        "erl_mode": "target",
        "bias_caveat": True,
    }
    assert TRIGGERS_TAUGHT != TRIGGERS_SHIPPED


def test_qmr_and_imbalance_are_variants_not_part_of_taught():
    """Both are preferences -- 4th man's "I love to play..." -- not
    gates, and Bishop never gates on either. Folding a preference into
    the default is how a system stops being the one that was taught.

    The imbalance filter additionally has a measurement against it."""
    assert "require_qmr" not in TAUGHT
    assert "require_imbalance_overlap" not in TAUGHT
    assert set(VARIANTS) == {"qmr", "imbalance"}


def test_stats_breaks_down_by_trigger():
    from collections import Counter

    s = _stats([
        Rec("target_hit", 3.0, "breakout"),
        Rec("stop_hit", -1.0, "disrespect"),
        Rec("still_open", None, "fourth_man"),
    ])
    assert s["n"] == 2
    assert s["by_trigger"] == Counter({"breakout": 1, "disrespect": 1})


def test_each_mode_writes_its_own_csv(tmp_path):
    rec = TradeRecord(trade_id=1, instrument="EURUSD", entry_time="2026-01-01",
                      status="closed_win", r_multiple=3.0)
    args = SimpleNamespace(dump_trades=str(tmp_path), entry_style="conservative")
    _dump([rec], "EURUSD", "shipped", args)
    _dump([rec], "EURUSD", "taught", args)
    _dump([rec], "EURUSD", "taught+qmr", args)
    assert sorted(p.name for p in tmp_path.iterdir()) == [
        "EURUSD_conservative.csv",
        "EURUSD_conservative_taught.csv",
        "EURUSD_conservative_taught_qmr.csv",
    ]


def test_an_unknown_variant_is_rejected_rather_than_ignored():
    """A typo must not quietly run one fewer comparison than asked for."""
    argv = ["compare_systems", "--instruments", "EURUSD", "--variants", "nonsense"]
    with mock.patch.object(sys, "argv", argv):
        with pytest.raises(SystemExit) as e:
            main()
    assert e.value.code != 0


def test_defaults_match_the_deployed_launch_flags():
    parsed = {}
    real = argparse.ArgumentParser.parse_args

    def capture(self, *a, **k):
        parsed.update(vars(real(self, *a, **k)))
        raise SystemExit(0)

    argv = ["compare_systems", "--instruments", "NONE_AT_ALL"]
    with mock.patch.object(argparse.ArgumentParser, "parse_args", capture), \
            mock.patch.object(sys, "argv", argv):
        with pytest.raises(SystemExit):
            main()

    assert parsed["origin_kind"] == LIVE_LAUNCH_FLAGS["origin_kind"]
    assert parsed["stop_anchor"] == LIVE_LAUNCH_FLAGS["stop_anchor"]
    assert parsed["min_reward_r"] == LIVE_FIXED_FLAGS["min_reward_r"]
