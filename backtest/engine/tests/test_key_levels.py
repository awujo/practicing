import pandas as pd
import pytest

from ..candles import Candle
from ..structure import Direction
from ..key_levels import (
    detect_key_levels, detect_open_close_level, is_disrespected,
    count_tests_before_disrespect, is_qmr_level,
)


def C(i, o, h, l, c):
    return Candle(pd.Timestamp("2024-01-01") + pd.Timedelta(hours=i), o, h, l, c, 1000)


def test_detects_a_shape_close_peak():
    # Closes rise into index 2 then fall away -- a close-price peak, sell bias.
    candles = [
        C(0, 1.10, 1.11, 1.09, 1.101),
        C(1, 1.101, 1.12, 1.10, 1.108),
        C(2, 1.108, 1.13, 1.105, 1.115),  # close peak
        C(3, 1.115, 1.116, 1.10, 1.109),
        C(4, 1.109, 1.110, 1.095, 1.100),
    ]
    levels = detect_key_levels(candles, n=2)
    a_shapes = [lvl for lvl in levels if lvl.shape == "A"]
    assert len(a_shapes) == 1
    assert a_shapes[0].price == pytest.approx(1.115)
    assert a_shapes[0].default_bias == Direction.BEARISH


def test_detects_v_shape_close_trough():
    candles = [
        C(0, 1.10, 1.11, 1.09, 1.100),
        C(1, 1.100, 1.101, 1.08, 1.090),
        C(2, 1.090, 1.091, 1.07, 1.080),  # close trough
        C(3, 1.080, 1.095, 1.079, 1.088),
        C(4, 1.088, 1.099, 1.087, 1.095),
    ]
    levels = detect_key_levels(candles, n=2)
    v_shapes = [lvl for lvl in levels if lvl.shape == "V"]
    assert len(v_shapes) == 1
    assert v_shapes[0].price == pytest.approx(1.080)
    assert v_shapes[0].default_bias == Direction.BULLISH


def test_open_close_level_two_down_candles():
    c1 = C(0, 1.1050, 1.1055, 1.1015, 1.1020)  # bearish: close < open
    c2 = C(1, 1.1020, 1.1022, 1.0990, 1.1000)  # bearish, opens where c1 closed
    level = detect_open_close_level(c1, c2)
    assert level is not None
    assert level.shape == "open_close"
    assert level.default_bias == Direction.BEARISH


def test_open_close_level_rejects_non_overlapping():
    c1 = C(0, 1.1050, 1.1055, 1.1015, 1.1020)
    c2 = C(1, 1.0500, 1.0522, 1.0400, 1.0450)  # bearish but no overlap with c1's range
    assert detect_open_close_level(c1, c2) is None


def test_open_close_level_rejects_mixed_direction():
    c1 = C(0, 1.1050, 1.1055, 1.1015, 1.1020)  # bearish
    c2 = C(1, 1.1020, 1.1060, 1.1015, 1.1055)  # bullish
    assert detect_open_close_level(c1, c2) is None


def test_disrespect_flips_a_shape():
    level_candle = C(2, 1.108, 1.13, 1.105, 1.115)
    from ..key_levels import KeyLevel
    a_level = KeyLevel(level_candle.time, 1.115, "A", Direction.BEARISH)

    respecting = C(3, 1.110, 1.116, 1.108, 1.112)   # closes below level -- respects sell bias
    disrespecting = C(4, 1.112, 1.125, 1.111, 1.120)  # closes ABOVE level -- disrespects

    assert not is_disrespected(respecting, a_level)
    assert is_disrespected(disrespecting, a_level)


def test_count_tests_before_disrespect():
    from ..key_levels import KeyLevel
    level = KeyLevel(pd.Timestamp("2024-01-01"), 1.1000, "A", Direction.BEARISH)

    candles_after = [
        # test 1: touches 1.1000, closes back below -- respects
        C(0, 1.098, 1.1005, 1.097, 1.099),
        # test 2: touches again, respects again
        C(1, 1.099, 1.1003, 1.098, 1.0995),
        # disrespect: closes above 1.1000
        C(2, 1.0995, 1.105, 1.099, 1.103),
    ]

    test_count, disrespect_time = count_tests_before_disrespect(candles_after, level)
    assert test_count == 2
    assert disrespect_time == candles_after[2].time
    assert is_qmr_level(test_count) is True


def test_count_tests_never_disrespected_within_window():
    from ..key_levels import KeyLevel
    level = KeyLevel(pd.Timestamp("2024-01-01"), 1.1000, "A", Direction.BEARISH)
    candles_after = [
        C(0, 1.098, 1.1005, 1.097, 1.099),
        C(1, 1.099, 1.1003, 1.098, 1.0995),
    ]
    test_count, disrespect_time = count_tests_before_disrespect(candles_after, level)
    assert test_count == 2
    assert disrespect_time is None
