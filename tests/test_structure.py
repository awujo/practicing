"""Synthetic close-line schematics; not historical teacher-trade replays."""
import pandas as pd
from bishop.structure import turning_points, events


def bars(closes, highs=None, lows=None):
    opens = [closes[0]] + closes[:-1]
    return pd.DataFrame({"open": opens, "close": closes,
                         "high": highs or [max(o,c)+.1 for o,c in zip(opens,closes)],
                         "low": lows or [min(o,c)-.1 for o,c in zip(opens,closes)]},
                        index=pd.date_range("2024-01-01", periods=len(closes), freq="h", tz="UTC"))


def test_turns_are_known_only_on_reversal_and_ties_use_last_plateau():
    b = bars([1,3,3,2,1,2])
    points = turning_points(b, as_of=b.index[-1])
    assert [(p.kind,p.price,p.formed_at,p.available_at) for p in points] == [
        ("H",3,b.index[2],b.index[3]),("L",1,b.index[4],b.index[5])]
    assert turning_points(b.iloc[:3], as_of=b.index[2]) == []


def test_wick_is_sweep_not_body_break_and_cannot_self_confirm():
    b=bars([1,3,2,2.5,3.5],highs=[1.1,3.1,3.2,3.4,3.6])
    found=events(b,as_of=b.index[-1])
    assert not any(e.occurred_at == b.index[2] for e in found)
    assert any(e.kind=="SWEEP" and e.side=="SELL" and e.occurred_at==b.index[3] for e in found)
    assert any(e.kind=="BREAKOUT" and e.side=="BUY" and e.occurred_at==b.index[4] for e in found)


def test_opposite_extreme_sweep_then_later_break_has_known_reference():
    b=bars([2,4,3,3.5,3.2,4.5], lows=[1.9,1.9,2.9,2.9,2.8,3.1])
    found=events(b,as_of=b.index[-1])
    event=[e for e in found if e.kind=="SWEEP_BOS" and e.side=="BUY"][-1]
    assert event.sweep_at < event.available_at
    assert event.reference_available_at < event.available_at
    assert event.reference==3.5  # Explicit latest-local-turn policy, not assumed major high.


def test_every_prefix_is_identical_to_observable_full_events():
    b=bars([2,4,3,3.5,3.2,4.5,4,5,3,2])
    full=events(b,as_of=b.index[-1])
    fullpoints=turning_points(b,as_of=b.index[-1])
    for n in range(1,len(b)+1):
        at=b.index[n-1]
        assert events(b.iloc[:n],as_of=at)==[e for e in full if e.available_at<=at]
        assert turning_points(b.iloc[:n],as_of=at)==[e for e in fullpoints if e.available_at<=at]
    assert len({(e.reference_formed_at,e.side) for e in full if e.kind!="SWEEP"}) == len([e for e in full if e.kind!="SWEEP"])
