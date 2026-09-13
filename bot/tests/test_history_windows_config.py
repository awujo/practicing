"""Guards bot/history_windows.json's own shape -- not a claim that its
values are correct (that's compare_history_window.py's escalation search,
see OPERATIONS_LOG.md 2026-09-13), just that a future hand-edit can't
silently corrupt it into something run_live.py would choke on or
silently misinterpret."""

import json
import os

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "..", "history_windows.json")

# Confirmed via backtest/tools/compare_history_window.py's escalation
# search, under origin_kind=any + close_based_sweep_break=True, as of
# 2026-09-13. See that entry's own "re-run every 6 months" note before
# assuming these stay valid indefinitely.
EXPECTED_INSTRUMENTS = {"EURUSD", "GBPJPY", "US30", "GBPAUD", "NAS100", "USDJPY", "EURJPY", "JP225"}
GRANULARITIES = {"D", "W", "H4", "H1"}


def _load():
    with open(CONFIG_PATH) as f:
        return json.load(f)


def test_history_windows_config_is_valid_json():
    config = _load()
    assert isinstance(config, dict)


def test_history_windows_config_has_exactly_the_confirmed_instruments():
    assert set(_load().keys()) == EXPECTED_INSTRUMENTS


def test_history_windows_config_entries_have_all_four_granularities():
    for instrument, window in _load().items():
        assert set(window.keys()) == GRANULARITIES, instrument


def test_history_windows_config_values_are_positive_numbers():
    for instrument, window in _load().items():
        for granularity, years in window.items():
            assert isinstance(years, (int, float)) and years > 0, f"{instrument}/{granularity}"


def test_history_windows_config_h_values_are_half_the_dw_values():
    """Matches the escalation methodology's own step ratio (dw-step-years
    1.0, h-step-years 0.5) -- H4/H1 always half of D/W in every confirmed
    result so far. Not a hard requirement of the mechanism itself, just a
    sanity check that a hand-edit didn't transpose two numbers."""
    for instrument, window in _load().items():
        assert window["D"] == window["W"], instrument
        assert window["H4"] == window["H1"] == window["D"] / 2, instrument
