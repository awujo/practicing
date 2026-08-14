import pandas as pd
import pytest

from ..candles import Candle
from ..structure import Direction
from ..key_levels import KeyLevel
from ..entries import (
    is_engulfing, classify_entry_pattern, EntryPattern, irl_required,
    origin_stop_loss, continuation_stop_loss, tight_stop_loss_no_irl,
    aggressive_entry_price, conservative_entry_price,
)


def C(i, o, h, l, c):
    return Candle(pd.Timestamp("2024-01-01") + pd.Timedelta(hours=i), o, h, l, c, 1000)


def T(hours):
    return pd.Timestamp("2024-01-01") + pd.Timedelta(hours=hours)


def test_bullish_engulfing_detected():
    prev = C(0, 1.1020, 1.1025, 1.0995, 1.1000)  # bearish
    curr = C(1, 1.0998, 1.1040, 1.0996, 1.1030)  # bullish, engulfs prev's body
    assert is_engulfing(prev, curr, Direction.BULLISH)
    assert not is_engulfing(prev, curr, Direction.BEARISH)


def test_partial_body_does_not_count_as_engulfing():
    prev = C(0, 1.1020, 1.1025, 1.0995, 1.1000)
    curr = C(1, 1.1005, 1.1030, 1.1003, 1.1015)  # bullish but doesn't fully cover prev's body
    assert not is_engulfing(prev, curr, Direction.BULLISH)


def test_direct_mitigation_when_next_candle_taps_level():
    level = KeyLevel(T(0), 1.1000, "open_close", Direction.BULLISH)
    following = [C(1, 1.0990, 1.1005, 1.0985, 1.0995)]  # touches 1.1000
    result = classify_entry_pattern(level, following)
    assert result.pattern == EntryPattern.DIRECT_MITIGATION
    assert result.reference_level is level


def test_fresh_irl_required_when_next_candle_doesnt_tap():
    level = KeyLevel(T(0), 1.1000, "open_close", Direction.BULLISH)
    # Doesn't touch 1.1000, and no nested open-close disrespect follows.
    following = [
        C(1, 1.1050, 1.1060, 1.1040, 1.1055),
        C(2, 1.1055, 1.1065, 1.1050, 1.1060),
        C(3, 1.1060, 1.1070, 1.1055, 1.1065),
    ]
    result = classify_entry_pattern(level, following)
    assert result.pattern == EntryPattern.FRESH_IRL_REQUIRED
    assert result.fresh_irl_price == pytest.approx(following[0].low)


def test_nested_disrespect_pattern():
    level = KeyLevel(T(0), 1.1000, "open_close", Direction.BULLISH)
    # Candle 1 doesn't tap 1.1000; candles 1+2 form a bearish open-close
    # (~1.1015); candle 3 disrespects that nested level (closes back above it).
    following = [
        C(1, 1.1050, 1.1052, 1.1010, 1.1015),  # bearish, doesn't touch 1.1000
        C(2, 1.1015, 1.1016, 1.0990, 1.0995),  # bearish, overlaps candle 1 -> nested level ~1.1015
        C(3, 1.0995, 1.1030, 1.0994, 1.1020),  # bullish close beyond 1.1015 -> disrespects nested level
    ]
    result = classify_entry_pattern(level, following)
    assert result.pattern == EntryPattern.NESTED_DISRESPECT
    assert result.reference_level.price == pytest.approx(1.1015)


def test_irl_required_rule():
    assert irl_required("origin") is True
    assert irl_required("continuation") is False
    with pytest.raises(ValueError):
        irl_required("something_else")


def test_stop_loss_placements():
    # Origin: 1 pip beyond the structural extreme.
    assert origin_stop_loss(1.1000, Direction.BULLISH, padding_pips=1.0, pip_size=0.0001) == pytest.approx(1.0999)
    assert origin_stop_loss(1.1000, Direction.BEARISH, padding_pips=1.0, pip_size=0.0001) == pytest.approx(1.1001)

    # Continuation: fixed 10 pips from entry.
    assert continuation_stop_loss(1.1000, Direction.BULLISH, pips=10, pip_size=0.0001) == pytest.approx(1.0990)

    # Tight (no-IRL continuation): 1 pip beyond the engulfed candle's own extreme.
    assert tight_stop_loss_no_irl(1.0985, Direction.BULLISH, padding_pips=1.0, pip_size=0.0001) == pytest.approx(1.0984)


def test_entry_style_prices():
    level = KeyLevel(T(0), 1.1000, "A", Direction.BEARISH)
    confirmation = C(1, 1.0995, 1.1000, 1.0980, 1.0985)

    assert aggressive_entry_price(level) == pytest.approx(1.1000)
    assert conservative_entry_price(confirmation) == pytest.approx(1.0985)
