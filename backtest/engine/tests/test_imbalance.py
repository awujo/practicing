import pandas as pd
import pytest

from ..candles import Candle
from ..structure import Direction
from ..imbalance import detect_imbalances, overlaps_level


def C(i, o, h, l, c):
    return Candle(pd.Timestamp("2024-01-01") + pd.Timedelta(hours=i), o, h, l, c, 1000)


def test_detects_bullish_gap():
    # candle A's high (1.100) < candle C's low (1.108) -- untraded gap in between.
    candles = [
        C(0, 1.095, 1.100, 1.090, 1.098),   # A
        C(1, 1.098, 1.115, 1.097, 1.112),   # B -- the displacement candle
        C(2, 1.112, 1.118, 1.108, 1.115),   # C
    ]
    gaps = detect_imbalances(candles)
    assert len(gaps) == 1
    assert gaps[0].direction == Direction.BULLISH
    assert gaps[0].low == pytest.approx(1.100)
    assert gaps[0].high == pytest.approx(1.108)


def test_detects_bearish_gap():
    candles = [
        C(0, 1.115, 1.120, 1.110, 1.112),   # A: low = 1.110
        C(1, 1.112, 1.113, 1.095, 1.098),   # B
        C(2, 1.098, 1.102, 1.090, 1.100),   # C: high = 1.102
    ]
    gaps = detect_imbalances(candles)
    assert len(gaps) == 1
    assert gaps[0].direction == Direction.BEARISH
    assert gaps[0].low == pytest.approx(1.102)
    assert gaps[0].high == pytest.approx(1.110)


def test_no_gap_when_candles_overlap():
    candles = [
        C(0, 1.100, 1.105, 1.095, 1.102),
        C(1, 1.102, 1.106, 1.098, 1.104),
        C(2, 1.104, 1.107, 1.100, 1.103),
    ]
    assert detect_imbalances(candles) == []


def test_overlaps_level():
    candles = [
        C(0, 1.095, 1.100, 1.090, 1.098),
        C(1, 1.098, 1.115, 1.097, 1.112),
        C(2, 1.112, 1.118, 1.108, 1.115),
    ]
    gap = detect_imbalances(candles)[0]
    assert overlaps_level(gap, 1.104) is True   # inside [1.100, 1.108]
    assert overlaps_level(gap, 1.050) is False
