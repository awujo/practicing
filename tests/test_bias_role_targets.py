"""A disrespected resistance cannot silently remain a sell-role destination."""
import pandas as pd

from bishop.bias import find_stories
from test_bias import fixture, selected


def test_target_does_not_reuse_an_already_invalidated_role():
    origin, lower = fixture()
    # Resistance5 is closed through before the final BUY context. It cannot
    # still be chosen as SELL resistance when price later returns below it.
    at = pd.Timestamp("2024-01-01T04:00Z")
    origin.loc[at] = [4., 5.6, 3.9, 5.5, pd.Timestamp("2024-01-01T03:00Z")]
    origin = origin.sort_index()
    stories = selected(find_stories(origin, lower, as_of=lower.index[-1]))
    assert len(stories) == 1 and stories[0].target == 6.
    assert stories[0].target != 5.
