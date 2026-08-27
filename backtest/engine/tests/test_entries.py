import pandas as pd
import pytest

from ..candles import Candle
from ..structure import Direction
from ..key_levels import KeyLevel
from ..entries import (
    is_engulfing, fourth_man_confirmation_level, classify_entry_pattern, EntryPattern,
    origin_stop_loss, continuation_stop_loss, tight_stop_loss_no_irl,
    engulfing_stop_loss, fourth_man_stop_loss,
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


def test_fourth_man_confirmation_bullish_sweep_and_reclaim():
    prev = C(0, 1.1010, 1.1020, 1.1000, 1.1015)  # range 1.1000-1.1020
    curr = C(1, 1.1015, 1.1018, 1.0990, 1.1005)  # sweeps below 1.1000, closes back above it, high stays under 1.1020
    level = fourth_man_confirmation_level(prev, curr)
    assert level is not None
    assert level.shape == "V"
    assert level.default_bias == Direction.BULLISH
    assert level.price == pytest.approx(curr.close)


def test_fourth_man_confirmation_bearish_sweep_and_reclaim():
    prev = C(0, 1.1010, 1.1020, 1.1000, 1.1005)  # range 1.1000-1.1020
    curr = C(1, 1.1005, 1.1030, 1.1008, 1.1012)  # sweeps above 1.1020, closes back below it, low stays over 1.1000
    level = fourth_man_confirmation_level(prev, curr)
    assert level is not None
    assert level.shape == "A"
    assert level.default_bias == Direction.BEARISH
    assert level.price == pytest.approx(curr.close)


def test_fourth_man_confirmation_none_when_the_other_side_also_breaks():
    prev = C(0, 1.1010, 1.1020, 1.1000, 1.1015)
    # Sweeps below 1.1000 AND takes out the high (1.1020) too -- prev's
    # high isn't "still standing", so this isn't a valid 4th-man pattern.
    curr = C(1, 1.1015, 1.1025, 1.0990, 1.1022)
    assert fourth_man_confirmation_level(prev, curr) is None


def test_fourth_man_confirmation_none_without_a_sweep():
    prev = C(0, 1.1010, 1.1020, 1.1000, 1.1015)
    curr = C(1, 1.1015, 1.1018, 1.1005, 1.1010)  # stays fully inside prev's range -- no sweep either side
    assert fourth_man_confirmation_level(prev, curr) is None


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


def test_stop_loss_placements():
    # Origin: 1 pip beyond the structural extreme.
    assert origin_stop_loss(1.1000, Direction.BULLISH, padding_pips=1.0, pip_size=0.0001) == pytest.approx(1.0999)
    assert origin_stop_loss(1.1000, Direction.BEARISH, padding_pips=1.0, pip_size=0.0001) == pytest.approx(1.1001)

    # Continuation: fixed 10 pips from entry.
    assert continuation_stop_loss(1.1000, Direction.BULLISH, pips=10, pip_size=0.0001) == pytest.approx(1.0990)

    # Tight (no-IRL continuation): 1 pip beyond the engulfed candle's own extreme.
    assert tight_stop_loss_no_irl(1.0985, Direction.BULLISH, padding_pips=1.0, pip_size=0.0001) == pytest.approx(1.0984)


def test_engulfing_stop_loss_uses_the_more_extreme_of_both_wicks():
    # Engulfed candle's low (1.0980) is LOWER than the engulfing candle's
    # own low (1.0990) -- "the engulfing candle might sweep the engulfed
    # candle... the lowest btw both of them" -- so the stop must clear
    # 1.0980, not just 1.0990.
    assert engulfing_stop_loss(1.0990, 1.0980, Direction.BULLISH, padding_pips=1.0, pip_size=0.0001) \
        == pytest.approx(1.0979)
    # When the ENGULFING candle's own wick is the more extreme one instead.
    assert engulfing_stop_loss(1.0975, 1.0980, Direction.BULLISH, padding_pips=1.0, pip_size=0.0001) \
        == pytest.approx(1.0974)
    # Bearish mirror: the higher of the two highs wins.
    assert engulfing_stop_loss(1.1010, 1.1020, Direction.BEARISH, padding_pips=1.0, pip_size=0.0001) \
        == pytest.approx(1.1021)


def test_fourth_man_stop_loss_pads_beyond_the_sweeping_candles_extreme():
    assert fourth_man_stop_loss(1.0990, Direction.BULLISH, padding_pips=1.0, pip_size=0.0001) == pytest.approx(1.0989)
    assert fourth_man_stop_loss(1.1020, Direction.BEARISH, padding_pips=1.0, pip_size=0.0001) == pytest.approx(1.1021)


def test_entry_style_prices():
    level = KeyLevel(T(0), 1.1000, "A", Direction.BEARISH)
    confirmation = C(1, 1.0995, 1.1000, 1.0980, 1.0985)

    assert aggressive_entry_price(level) == pytest.approx(1.1000)
    assert conservative_entry_price(confirmation) == pytest.approx(1.0985)
