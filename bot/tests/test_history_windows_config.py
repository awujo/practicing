"""Guards bot/history_windows.json's own shape -- not a claim that its
values are correct (that's compare_history_window.py's escalation search,
see OPERATIONS_LOG.md 2026-09-13), just that a future hand-edit can't
silently corrupt it into something run_live.py would choke on or
misinterpret."""

import json
import os

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "..", "history_windows.json")

# Confirmed by an actual escalation search reaching full convergence
# (bit-identical to full history over the recent comparison period), as
# of 2026-09-13. Everything else in the file is the flat default window
# (2y/1y), which is not a full-convergence guarantee -- see
# resolve_history_window_years()'s own docstring for why that's still a
# reasonable thing to ship (90-100% match, no fabricated trades, across
# every instrument tested except GBPNZD).
FULLY_CONVERGED_INSTRUMENTS = {"EURUSD", "GBPJPY", "GBPAUD", "NAS100", "USDJPY", "EURJPY", "US30", "JP225"}
# Confirmed NOT to converge even at a 15-year search ceiling -- must stay
# an explicit null (uncapped), never inherit the flat default.
EXCLUDED_INSTRUMENTS = {"GBPNZD"}
GRANULARITIES = {"D", "W", "H4", "H1"}


def _load():
    with open(CONFIG_PATH) as f:
        return json.load(f)


def _is_window(value):
    return isinstance(value, dict) and set(value.keys()) == GRANULARITIES


def test_history_windows_config_is_valid_json():
    config = _load()
    assert isinstance(config, dict)


def test_history_windows_config_has_a_default_and_an_instruments_section():
    config = _load()
    assert _is_window(config["default"])
    assert isinstance(config["instruments"], dict)


def test_history_windows_config_excluded_instruments_are_explicit_null():
    instruments = _load()["instruments"]
    for name in EXCLUDED_INSTRUMENTS:
        assert instruments[name] is None, name


def test_history_windows_config_every_non_null_entry_is_a_valid_window():
    for instrument, window in _load()["instruments"].items():
        if window is not None:
            assert _is_window(window), instrument
            for years in window.values():
                assert isinstance(years, (int, float)) and years > 0, instrument


def test_history_windows_config_fully_converged_instruments_have_h_half_of_dw():
    """Matches the escalation methodology's own step ratio -- a sanity
    check against a transposed number, not a hard requirement."""
    instruments = _load()["instruments"]
    for name in FULLY_CONVERGED_INSTRUMENTS:
        window = instruments[name]
        assert window["D"] == window["W"], name
        assert window["H4"] == window["H1"] == window["D"] / 2, name
