import pandas as pd
import pytest
from slk.research_history import windows


def test_history_uses_every_day_after_warmup_without_overlap():
    first=pd.Timestamp('2023-07-07T12:00Z');end=first+pd.Timedelta(days=1200)
    w=list(windows(first,end))
    assert len(w)==10 and w[0][0]==first+pd.Timedelta(days=365) and w[-1][1]==end
    assert all(w[i][1]==w[i+1][0] for i in range(len(w)-1))
    assert sum((b-a).total_seconds()/86400 for a,b in w)==835
    assert all(b-a<=pd.Timedelta(days=90) for a,b in w)


def test_history_window_bound():
    with pytest.raises(ValueError):list(windows(pd.Timestamp('2020-01-01T00:00Z'),pd.Timestamp('2026-01-01T00:00Z'),91))
