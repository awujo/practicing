"""Tests for the signal-count tool.

The tool has one job: report the number of signals the LIVE bot's own
call to run_backtest() would produce. A default that drifts away from
LiveBot's makes it silently measure a different strategy and answer the
wrong question confidently -- which is the exact failure mode that cost
two days before this tool existed. So the defaults are pinned to
LiveBot's, by import, not by memory.
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


def test_defaults_match_the_live_bot():
    from bot.orchestrator import LiveBot
    fields = LiveBot.__dataclass_fields__
    d = _defaults()
    assert d["stop_anchor"] == fields["stop_anchor"].default
    assert d["origin_kind"] == fields["origin_kind"].default
    assert d["close_based_sweep_break"] is fields["close_based_sweep_break"].default


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
