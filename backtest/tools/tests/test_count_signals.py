"""Tests for the signal-count tool.

The tool has one job: report the number of signals the LIVE bot's own
call to run_backtest() would produce. A default that drifts away from
what is deployed makes it silently measure a different strategy and
answer the wrong question confidently.

The first version of this file pinned the defaults to LiveBot's
dataclass fields and asserted they matched. That test passed and the
tool was still wrong: both bots are launched with `--origin-kind any
--close-based-sweep-break`, which override those defaults at the launch
site the dataclass knows nothing about. So the invariant worth testing
is against the deployment (live_flags.py), not against the class.
"""

import pandas as pd
import pytest

from ...tools.count_signals import main, _when


def _defaults():
    import argparse
    import sys
    from unittest import mock
    parsed = {}
    real = argparse.ArgumentParser.parse_args

    def capture(self, *a, **k):
        ns = real(self, *a, **k)
        parsed.update(vars(ns))
        raise SystemExit(0)

    argv = ["count_signals", "--instruments", "NONE_AT_ALL",
            "--from", "2026-09-04", "--to", "2026-09-18"]
    with mock.patch.object(argparse.ArgumentParser, "parse_args", capture), \
            mock.patch.object(sys, "argv", argv):
        with pytest.raises(SystemExit):
            main()
    return parsed


def test_defaults_match_the_deployed_launch_flags():
    from ...tools.live_flags import LIVE_LAUNCH_FLAGS
    d = _defaults()
    assert d["stop_anchor"] == LIVE_LAUNCH_FLAGS["stop_anchor"]
    assert d["origin_kind"] == LIVE_LAUNCH_FLAGS["origin_kind"]
    assert d["close_based_sweep_break"] is LIVE_LAUNCH_FLAGS["close_based_sweep_break"]


def test_the_deployed_flags_are_not_just_the_dataclass_defaults():
    """A regression guard on the mistake itself. If someone later
    'simplifies' live_flags.py back to LiveBot's dataclass defaults, the
    tools silently start measuring a strategy that is not deployed --
    which is how this went unnoticed the first time. If the deployment
    genuinely changes to match the dataclass, delete this test
    deliberately rather than letting it pass by accident."""
    from bot.orchestrator import LiveBot
    from ...tools.live_flags import LIVE_LAUNCH_FLAGS
    fields = LiveBot.__dataclass_fields__
    assert LIVE_LAUNCH_FLAGS["origin_kind"] != fields["origin_kind"].default
    assert LIVE_LAUNCH_FLAGS["close_based_sweep_break"] is not \
        fields["close_based_sweep_break"].default


def test_signal_latency_uses_the_same_deployed_flags():
    """Two tools answering two halves of one question must not disagree
    about which strategy they are asking about."""
    from ...tools import signal_latency
    from ...tools.live_flags import LIVE_LAUNCH_FLAGS
    assert signal_latency.LIVE_LAUNCH_FLAGS is LIVE_LAUNCH_FLAGS


def test_when_formats_a_timestamp_and_survives_none():
    assert _when(None) == "-"
    assert _when(pd.Timestamp("2026-09-15 12:00", tz="UTC")) == "Tue 15 Sep 12:00"


def test_funnel_uses_the_same_liquidity_mode_the_backtest_does():
    """run_backtest defaults to swing; _find_liquidity_setups defaults to
    single_candle. Taking the latter's default would print a funnel that
    does not belong to the TRADES column beside it."""
    import inspect
    from ...tools import count_signals
    src = inspect.getsource(count_signals.funnel)
    assert 'liquidity_mode="swing"' in src
