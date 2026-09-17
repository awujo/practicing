"""Tests for the by-hand setup report.

This tool exists to be checked against a chart, so the one thing it
must never do is misreport a price or a side. A wrong digit count turns
188.388 into 188.38800 and a wrong side sends someone looking for a low
where the engine armed a high -- either wastes the reader's time and,
worse, makes a correct engine look broken.
"""

import pandas as pd
import pytest

from ..show_setups import _digits, _fmt


def test_fx_pairs_print_five_decimals():
    assert _digits("GBPUSD") == 5
    assert _digits("EURCHF") == 5
    assert _fmt(1.3505, 5) == "1.35050"


def test_jpy_metals_and_indices_print_two():
    for sym in ("USDJPY", "CHFJPY", "XAUUSD", "US30", "NAS100", "JP225", "USOIL"):
        assert _digits(sym) == 2, sym
    assert _fmt(188.388, 2) == "188.39"


def test_a_pool_price_never_loses_its_significant_digits():
    """The failure that matters: a level printed with too few digits is
    a level the reader cannot find on their chart."""
    assert _fmt(0.81781, 5) == "0.81781"
    assert _fmt(1.35050, 5) == "1.35050"
