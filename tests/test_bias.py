"""Synthetic origin/cascade clocks, not historical teacher replay passes."""
import pandas as pd
import pytest
from bishop.bias import find_candidates, find_stories


def fixture():
    index=pd.to_datetime(["2024-01-01T00:00Z","2024-01-01T01:00Z","2024-01-01T02:00Z",
                          "2024-01-01T03:00Z","2024-01-01T10:00Z"])
    origin=pd.DataFrame([(5,6.2,4.8,6),(6,6.1,4.7,5),(5,5.2,2.8,3),(3,4.2,3.0,4),(4,4.8,2.5,4.5)],
                        columns=["open","high","low","close"],index=index,dtype=float)
    origin["start"]=[index[0]-pd.Timedelta(hours=1),index[0],index[1],index[2],index[3]+pd.Timedelta(hours=1)]
    closes=[3,4,3.5,3.7,3.4,2.8,3.2,4.5,4.4,4.5,4.4,4.6]
    opens=[3]+closes[:-1]
    lower=pd.DataFrame({"open":opens,"close":closes,"high":[max(o,c)+.1 for o,c in zip(opens,closes)],
                        "low":[min(o,c)-.1 for o,c in zip(opens,closes)]},
                       index=pd.date_range(index[0],periods=len(closes),freq="h"))
    return origin,lower


def selected(stories):
    return [s for s in stories if s.origin_at.hour==10 and s.level_kind=="V"]


def test_origin_reject_needs_existing_level_and_strict_close():
    o,l=fixture()
    candidates=find_candidates(o,as_of=l.index[-1])
    assert any(c.level==3 and c.trigger=="KL_REJECTION" and c.side=="BUY" for c in candidates)
    assert all(c.level_available_at<c.origin_at for c in candidates)
    assert any(c.trigger=="CANDLE_SWEEP" for c in candidates)


def test_same_day_break_occurs_before_origin_close_but_publishes_at_close():
    o,l=fixture()
    found=selected(find_stories(o,l,as_of=l.index[-1]))
    assert len(found)==1
    s=found[0]
    assert s.confirmation_at.hour==7 and s.available_at.hour==10
    assert s.reference_available_at.hour==4
    assert s.origin_tf==s.level_tf==s.target_tf=="D"
    assert s.target_kind=="ORIGIN_KL" and s.target==5
    assert s.target_available_at<=s.available_at
    assert s.target_kind!="ERL"
    earlier=o[o.index<o.index[-1]]
    assert not selected(find_stories(earlier,l.iloc[:10],as_of=l.index[9]))


def test_missing_origin_start_cannot_infer_preclose_ordering():
    o,l=fixture()
    found=selected(find_stories(o.drop(columns="start"),l,as_of=l.index[-1]))
    assert all(s.confirmation_at > s.origin_at for s in found)
    assert selected(find_stories(o.drop(columns="start"),l.iloc[:11],as_of=l.index[10]))==[]


def test_no_break_means_unconfirmed_even_with_engulf_shape():
    o,l=fixture()
    l.loc[l.index>=l.index[7],"close"]=3.6
    l.loc[l.index>=l.index[7],"open"]=3.3
    l.loc[l.index>=l.index[7],"high"]=3.65
    l.loc[l.index>=l.index[7],"low"]=3.2
    assert selected(find_stories(o,l,as_of=l.index[-1]))==[]


def test_future_origin_levels_cannot_rewrite_frozen_target():
    o,l=fixture()
    want=selected(find_stories(o,l,as_of=l.index[-1]))
    later=o.copy()
    later.loc[pd.Timestamp("2024-01-01T12:00Z")]=[4.5,10,4,9,pd.Timestamp("2024-01-01T10:00Z")]
    assert selected(find_stories(later,l,as_of=later.index[-1]))==want
    for n in range(1,len(l)+1):
        clock=l.index[n-1]
        assert selected(find_stories(o[o.index<=clock],l.iloc[:n],as_of=clock))==[s for s in want if s.available_at<=clock]


def test_wrong_ladder_or_unknown_clock_rejected():
    o,l=fixture()
    with pytest.raises(ValueError): find_stories(o,l,confirmation_tf="H1",as_of=l.index[-1])
    with pytest.raises(ValueError): find_stories(o,l,as_of="2024-01-01T12:00")


def test_explicit_level_policy_is_reported_without_silent_tolerance():
    o,l=fixture()
    for mode in ("exact_junction","close_reference"):
        stories=find_stories(o,l,level_mode=mode,as_of=l.index[-1])
        assert all(s.level_mode==mode for s in stories)
