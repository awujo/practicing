"""Tests for run_live.py's resolve_history_window_years() -- the pure
function that turns a --history-windows-config file's two-tier
{default, instruments} structure into the flat dict LiveBot wants.
"""

from ..run_live import resolve_history_window_years

DEFAULT = {"D": 2, "W": 2, "H4": 1, "H1": 1}
EURUSD_WINDOW = {"D": 8, "W": 8, "H4": 4, "H1": 4}


def test_an_instrument_with_a_specific_override_uses_it_not_the_default():
    config = {"default": DEFAULT, "instruments": {"EURUSD": EURUSD_WINDOW}}
    resolved = resolve_history_window_years(config, ("EURUSD",))
    assert resolved == {"EURUSD": EURUSD_WINDOW}


def test_an_instrument_with_no_entry_falls_back_to_the_default():
    config = {"default": DEFAULT, "instruments": {"EURUSD": EURUSD_WINDOW}}
    resolved = resolve_history_window_years(config, ("EURUSD", "GBPCHF"))
    assert resolved == {"EURUSD": EURUSD_WINDOW, "GBPCHF": DEFAULT}


def test_an_explicit_null_override_stays_uncapped_even_with_a_default_set():
    """The whole point of an explicit null (e.g. GBPNZD): it must NOT
    silently inherit the flat default just because one is configured."""
    config = {"default": DEFAULT, "instruments": {"GBPNZD": None}}
    resolved = resolve_history_window_years(config, ("GBPNZD",))
    assert resolved == {}


def test_no_default_configured_means_unlisted_instruments_stay_uncapped():
    config = {"default": None, "instruments": {"EURUSD": EURUSD_WINDOW}}
    resolved = resolve_history_window_years(config, ("EURUSD", "GBPCHF"))
    assert resolved == {"EURUSD": EURUSD_WINDOW}


def test_missing_instruments_section_treated_as_empty():
    config = {"default": DEFAULT}
    resolved = resolve_history_window_years(config, ("EURUSD",))
    assert resolved == {"EURUSD": DEFAULT}


def test_only_instruments_actually_being_run_are_resolved():
    """An instrument configured in the file but not part of THIS run's
    --instruments list must not appear in the result."""
    config = {"default": DEFAULT, "instruments": {"EURUSD": EURUSD_WINDOW, "GBPJPY": EURUSD_WINDOW}}
    resolved = resolve_history_window_years(config, ("EURUSD",))
    assert resolved == {"EURUSD": EURUSD_WINDOW}
