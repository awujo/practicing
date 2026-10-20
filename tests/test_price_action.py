"""Synthetic teaching schematics and causality checks, NOT historical replays."""
import numpy as np
import pandas as pd
import pytest

from bishop.price_action import KeyLevel, classify, levels, validated_bars


def bars(rows):
    return pd.DataFrame(rows, columns=["open", "high", "low", "close"],
                        index=pd.date_range("2024-01-01", periods=len(rows), freq="h", tz="UTC"), dtype=float)


def test_two_candles_suffice_and_availability_is_second_close():
    a = bars([(1, 3, 0, 2), (2, 3, 0, 1)])
    found = levels(a, as_of=a.index[-1])
    assert found == [KeyLevel("A", 2, "SELL", a.index[0], a.index[1])]
    assert levels(a.iloc[:1], as_of=a.index[0]) == []
    v = bars([(2, 3, 0, 1), (1, 3, 0, 2)])
    assert levels(v)[0].kind == "V" and levels(v)[0].side == "BUY"


def test_open_close_same_direction_and_conservative_gap_doji_choices():
    bull = bars([(1, 3, 0, 2), (2, 4, 1, 3)])
    assert levels(bull)[0].kind == "OC" and levels(bull)[0].side == "BUY"
    bear = bars([(3, 4, 1, 2), (2, 3, 0, 1)])
    assert levels(bear)[0].kind == "OC" and levels(bear)[0].side == "SELL"
    gapped = bull.copy()
    gapped.iloc[1, 0] += 0.000001
    assert levels(gapped) == []  # No hidden epsilon to manufacture a shared junction.
    doji = bull.copy()
    doji.iloc[0, 0] = doji.iloc[0, 3]
    assert levels(doji) == []


def test_every_prefix_matches_only_levels_observable_at_that_close():
    data = bars([(1, 3, 0, 2), (2, 4, 1, 3), (3, 4, 0, 1),
                 (1, 5, 0, 4), (4, 5, 2, 3), (3, 4, 0, 2)])
    full = levels(data, as_of=data.index[-1])
    assert {x.kind for x in full} == {"A", "V", "OC"}
    for n in range(1, len(data) + 1):
        clock = data.index[n - 1]
        assert levels(data.iloc[:n], as_of=clock) == [x for x in full if x.available_at <= clock]
    changed = data.copy()
    changed.iloc[-1] = [3, 10, 0, 9]
    assert levels(data.iloc[:-1]) == levels(changed.iloc[:-1])


@pytest.mark.parametrize("side,row,kind,direction", [
    ("BUY", (2, 3, 0.9, 2), "SWEEP", "BUY"),
    ("BUY", (2, 3, 0.9, 0.95), "BREAK", "SELL"),
    ("BUY", (2, 3, 1, 2), "TOUCH", "BUY"),
    ("BUY", (2, 3, 0.9, 1), "SWEEP", "BUY"),
    ("SELL", (0.9, 1.1, 0.8, 0.9), "SWEEP", "SELL"),
    ("SELL", (0.9, 1.1, 0.8, 1.05), "BREAK", "BUY"),
    ("SELL", (0.9, 1, 0.8, 0.9), "TOUCH", "SELL"),
])
def test_wick_sweep_body_break_and_equal_touch_are_distinct(side, row, kind, direction):
    data = bars([row, row, row])
    lv = KeyLevel("OC", 1, side, data.index[0], data.index[1])
    event = classify(lv, data.iloc[2], as_of=data.index[2])
    assert event.kind == kind and event.side == direction
    assert event.occurred_at == event.available_at == data.index[2]
    assert classify(lv, data.iloc[1], as_of=data.index[1]) is None
    assert classify(lv, data.iloc[0], as_of=data.index[0]) is None


def test_no_contact_and_closed_end_column_integration():
    data = bars([(2, 3, 1.5, 2)])
    lv = KeyLevel("V", 1, "BUY", data.index[0] - pd.Timedelta(hours=2),
                  data.index[0] - pd.Timedelta(hours=1))
    assert classify(lv, data.iloc[0]) is None
    explicit = data.assign(end=data.index).reset_index(drop=True)
    assert validated_bars(explicit).index.tolist() == data.index.tolist()
    assert classify(lv, explicit.iloc[0]) is None


def test_reject_future_forming_bar_instead_of_using_its_close():
    data = bars([(1, 3, 0, 2), (2, 3, 0, 1)])
    with pytest.raises(ValueError, match="future/forming"):
        levels(data, as_of=data.index[0])
    lv = KeyLevel("V", 1, "BUY", data.index[0], data.index[0])
    with pytest.raises(ValueError, match="future/forming"):
        classify(lv, data.iloc[1], as_of=data.index[0])


@pytest.mark.parametrize("damage", ["nan", "infinite", "bounds", "duplicates", "unsorted", "naive"])
def test_malformed_feed_is_rejected(damage):
    data = bars([(1, 3, 0, 2), (2, 3, 0, 1)])
    if damage == "nan": data.iloc[0, 0] = np.nan
    elif damage == "infinite": data.iloc[0, 0] = np.inf
    elif damage == "bounds": data.iloc[0, 1] = 1.5
    elif damage == "duplicates": data.index = [data.index[0]] * 2
    elif damage == "unsorted": data = data.iloc[::-1]
    elif damage == "naive": data.index = data.index.tz_localize(None)
    with pytest.raises(ValueError):
        levels(data)


def test_empty_input_and_explicit_clock_validation():
    data = bars([])
    assert levels(data, as_of=pd.Timestamp("2024-01-01", tz="UTC")) == []
    with pytest.raises(ValueError, match="timezone"):
        levels(data, as_of="2024-01-01")
