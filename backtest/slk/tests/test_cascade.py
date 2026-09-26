"""
Bias by every route, on every rung -- and in constant time.
"""

from __future__ import annotations

import pandas as pd
import pytest

from ...engine.candles import Candle
from ...engine.structure import Direction
from ..cascade import BiasRoute, Cascade, _agree
from ..stream import BreakTracker

T0 = pd.Timestamp("2026-01-01")


def c(i, o, h, l, cl, unit="hours"):
    return Candle(time=T0 + pd.Timedelta(**{unit: i}), open=o, high=h, low=l,
                  close=cl, volume=0)


def rising_break(start_i, base, unit="hours"):
    """Five candles leaving an A-shape at base+0.0040, then a close above
    it. With n=2 the swing confirms two candles after it forms."""
    return [c(start_i + 0, base, base + 0.0010, base - 0.0010, base, unit),
            c(start_i + 1, base, base + 0.0020, base - 0.0005, base + 0.0010, unit),
            c(start_i + 2, base + 0.0010, base + 0.0040, base, base + 0.0030, unit),
            c(start_i + 3, base + 0.0030, base + 0.0035, base + 0.0015, base + 0.0020, unit),
            c(start_i + 4, base + 0.0020, base + 0.0025, base + 0.0010, base + 0.0015, unit),
            c(start_i + 5, base + 0.0015, base + 0.0060, base + 0.0010, base + 0.0050, unit)]


# --- the one number that replaces the rescan ---------------------------

def test_the_break_tracker_keeps_the_newest_broken_swing_s_formation_time():
    """"Is there a swing formed after T that has since been broken?" is
    answered by one number per direction. If the newest broken swing
    formed after T the answer is yes, and if it did not then no swing
    after T has been broken either -- because it is the newest."""
    t = BreakTracker(2)
    for bar in rising_break(0, 1.1000):
        t.push(bar)

    when = t.newest_break[Direction.BULLISH]
    assert when == T0 + pd.Timedelta(hours=2), "the swing FORMED at index 2"
    assert t.broke_after(T0 + pd.Timedelta(hours=1), Direction.BULLISH)
    assert not t.broke_after(T0 + pd.Timedelta(hours=3), Direction.BULLISH)


def test_a_wick_through_a_swing_is_not_a_break():
    t = BreakTracker(2)
    bars = rising_break(0, 1.1000)
    last = bars[-1]
    bars[-1] = Candle(time=last.time, open=last.open, high=last.high,
                      low=last.low, close=1.1020, volume=0)   # wick only
    for bar in bars:
        t.push(bar)
    assert Direction.BULLISH not in t.newest_break


def test_nothing_broken_is_not_a_break_after_anything():
    t = BreakTracker(2)
    for i in range(10):
        t.push(c(i, 1.10, 1.1005, 1.0995, 1.10))
    assert not t.broke_after(T0, Direction.BULLISH)
    assert not t.broke_after(T0, Direction.BEARISH)


def _install(cascade, rung: str, direction: Direction, at=None):
    """Give a rung a rejection, a confirming break, AND the matching
    structure -- which is now required for any of it to count."""
    at = at or T0
    route = getattr(cascade, rung + "_levels")
    route._rejections[direction].append(at)
    route._level_at[at] = 1.1000
    route._breaks.newest_break[direction] = at + pd.Timedelta(hours=1)
    route._breaks.broke_at[direction] = (at + pd.Timedelta(hours=2), 1.1050)
    tracker = (cascade.daily_structure if rung == "lower"
               else cascade.weekly_structure)
    tracker.broke_at[direction] = (at + pd.Timedelta(hours=2), 1.1050)


# --- one rung ----------------------------------------------------------

def test_a_rejection_alone_is_not_a_bias():
    """Condition 3 is something price must DO. bias.py says the same
    thing; this is the incremental machine agreeing with it."""
    route = BiasRoute(2)
    for bar in _daily_rejection_at(1.0900):
        route.push_higher(bar)
    assert route.direction() is None, "the lower timeframe has not spoken"


def test_the_rung_answers_once_the_lower_timeframe_breaks():
    route = BiasRoute(2)
    for bar in _daily_rejection_at(1.0900):
        route.push_higher(bar)
    # hour 120 is day 5, where the rejection landed: the break has to come
    # AFTER it, or it says nothing about what the rejection started.
    for bar in rising_break(126, 1.1000):
        route.push_lower(bar)

    got = route.direction()
    assert got is not None
    assert got[0] == Direction.BULLISH


def test_a_break_that_predates_the_rejection_does_not_count():
    """A swing broken before the rejection says nothing about what the
    rejection started."""
    route = BiasRoute(2)
    for bar in rising_break(0, 1.1000):          # the break happens first
        route.push_lower(bar)
    for bar in _daily_rejection_at(1.0900, start=20):
        route.push_higher(bar)
    assert route.direction() is None


def _daily_rejection_at(price, start=0):
    """A V-shape at `price` confirmed with n=2, then a candle that
    reaches down to it and closes back above."""
    bars = [c(start + 0, price + 0.0030, price + 0.0040, price + 0.0020, price + 0.0030, "days"),
            c(start + 1, price + 0.0030, price + 0.0035, price + 0.0010, price + 0.0015, "days"),
            c(start + 2, price + 0.0015, price + 0.0020, price, price + 0.0010, "days"),
            c(start + 3, price + 0.0010, price + 0.0025, price + 0.0005, price + 0.0020, "days"),
            c(start + 4, price + 0.0020, price + 0.0040, price + 0.0015, price + 0.0035, "days")]
    # now the rejection: down to the level, closing back above it
    bars.append(c(start + 5, price + 0.0035, price + 0.0040, price - 0.0002,
                  price + 0.0025, "days"))
    return bars


# --- the rungs together ------------------------------------------------

def test_a_rung_says_nothing_when_its_two_routes_disagree():
    """The source gives no precedence between a key level and liquidity
    at the same rung, so neither is invented. An ambiguous story is not a
    bias -- the same answer LiquidityBias gives when one candle sweeps a
    high and a low at once."""
    later = T0 + pd.Timedelta(days=1)
    assert _agree((Direction.BULLISH, T0), (Direction.BEARISH, later)) is None
    assert _agree((Direction.BULLISH, T0), None) == Direction.BULLISH
    assert _agree(None, None) is None


def test_agreeing_routes_give_the_newest_one():
    later = T0 + pd.Timedelta(days=1)
    assert _agree((Direction.BULLISH, T0),
                  (Direction.BULLISH, later)) == Direction.BULLISH


def test_all_four_routes_exist_on_the_cascade():
    """Two of these were missing: the liquidity route ran only on the
    Weekly and the key-level route only on the Daily, which was an
    accident of the order they were built in. Bishop's checklist is
    "previous daily weekly low sweep" -- daily OR weekly -- and
    repeating-system t=60-66 says bias can be built "from any
    timeframe"."""
    cascade = Cascade(2)
    assert cascade.upper_levels is not cascade.lower_levels
    assert cascade.upper_liquidity is not cascade.lower_liquidity
    assert cascade.direction() is None, "nothing pushed, nothing established"


def test_the_daily_rung_wins_a_disagreement_with_the_weekly():
    """"those two time frames are not in alignment, so that goes to the
    four hours ... I CAN LEAVE THE WEEKLY, I use my daily at my four
    hours" -- daily-routine t=399-417."""
    cascade = Cascade(2)

    # Force the two rungs to hold opposite answers by driving the routes
    # directly: this is about the precedence rule, not about detection.
    # Each rung's STRUCTURE has to agree with its route, because a
    # rejection that opposes its own timeframe's structure is no longer
    # a bias at all -- "daily reject, daily in alignment with the
    # structure".
    _install(cascade, "lower", Direction.BEARISH)
    _install(cascade, "upper", Direction.BULLISH)

    assert cascade.upper_levels.direction()[0] == Direction.BULLISH
    assert cascade.direction() == Direction.BEARISH, "the daily rung wins"


def test_the_weekly_rung_is_used_when_the_daily_has_no_answer():
    """It is a fallback, not a filter. Making the weekly a requirement
    would delete trades he explicitly still takes."""
    cascade = Cascade(2)
    _install(cascade, "upper", Direction.BULLISH)

    assert cascade.lower_levels.direction() is None
    assert cascade.direction() == Direction.BULLISH


def test_all_four_routes_actually_answer_on_real_shaped_data():
    """Two of these were missing entirely, and a route that is wired but
    never answers is dead code that looks alive. Counted over three
    fixtures: this is reachability, not a frequency claim."""
    from ..replay import replay
    from .test_replay import _agg, _random_series
    from .. import cascade as cascade_module

    answered = set()
    original = Cascade.direction

    def spy(self):
        for name in ("lower_levels", "lower_liquidity",
                     "upper_levels", "upper_liquidity"):
            route = getattr(self, name)
            got = (route.direction() if name.endswith("levels")
                   else cascade_module._as_pair(route))
            if got is not None:
                answered.add(name)
        return original(self)

    Cascade.direction = spy
    try:
        for seed in (3, 5, 11):
            h1 = _random_series(seed, 24000)
            replay(_agg(h1, 168), _agg(h1, 24), _agg(h1, 4), h1, n=2)
    finally:
        Cascade.direction = original

    assert answered == {"lower_levels", "lower_liquidity",
                        "upper_levels", "upper_liquidity"}, \
        f"never answered: {sorted({'lower_levels', 'lower_liquidity', 'upper_levels', 'upper_liquidity'} - answered)}"


# --- the timeframe's own structure --------------------------------------

def test_structural_direction_is_the_most_recent_break_of_structure():
    """Operator, 2026-09-25: "does the weekly factor in both rejection,
    breakout on the weekly, and sweep of the low?"

    Rejection and sweep were built; the timeframe's OWN breakout was not,
    and it is where Bishop's routine starts -- "weekly structurally we're
    still bearish", "we've been having breakouts to the upside, so I know
    my weekly is bullish"."""
    from ..cascade import structural_direction

    t = BreakTracker(2)
    for bar in rising_break(0, 1.1000):
        t.push(bar)

    got = structural_direction(t)
    assert got is not None
    direction, when, price = got
    assert direction == Direction.BULLISH
    assert when == T0 + pd.Timedelta(hours=5), \
        "the time of the CLOSE THROUGH, not of the swing it broke"
    assert price == pytest.approx(1.1040)


def test_no_break_of_structure_yet_is_none_not_a_guess():
    from ..cascade import structural_direction

    t = BreakTracker(2)
    for i in range(10):
        t.push(c(i, 1.10, 1.1005, 1.0995, 1.10))
    assert structural_direction(t) is None


def test_the_newest_break_wins_when_both_directions_have_one():
    """"Most recent breakout" means most recent, so a later break the
    other way replaces it."""
    from ..cascade import structural_direction

    t = BreakTracker(2)
    for bar in rising_break(0, 1.1000):
        t.push(bar)
    assert structural_direction(t)[0] == Direction.BULLISH

    # now a bearish break, later in time
    for bar in [c(6, 1.1050, 1.1055, 1.1000, 1.1005),
                c(7, 1.1005, 1.1010, 1.0960, 1.0965),
                c(8, 1.0965, 1.0970, 1.0940, 1.0945),
                c(9, 1.0945, 1.0990, 1.0940, 1.0980),
                c(10, 1.0980, 1.0985, 1.0950, 1.0955),
                c(11, 1.0955, 1.0960, 1.0900, 1.0905)]:
        t.push(bar)
    got = structural_direction(t)
    assert got[0] == Direction.BEARISH, "the later break is the current one"


def test_the_cascade_feeds_each_timeframe_its_own_structure():
    """The weekly's own candles, not only the daily's confirmations."""
    cascade = Cascade(2)
    for bar in rising_break(0, 1.1000, unit="days"):
        cascade.push_weekly(bar, bar.time)
    account = cascade.explain()
    assert account.weekly_structure is not None
    assert account.weekly_structure[0] == Direction.BULLISH
    assert account.daily_structure is None, "nothing pushed to the daily"


def test_the_account_fields_are_not_silently_shuffled():
    """BiasAccount has ten fields and was built positionally. Adding two
    put `alignment` into `weekly_structure`, which surfaced as "too many
    values to unpack" three modules away rather than anywhere near the
    cause. This pins the meaning of each field rather than its order."""
    cascade = Cascade(2)
    _install(cascade, "lower", Direction.BEARISH)

    account = cascade.explain()
    assert account.direction == Direction.BEARISH
    assert account.rung == "Daily"
    assert account.other_rung == "Weekly"
    assert isinstance(account.alignment, str), "alignment must be a string"
    assert account.alignment in {"aligned", "not aligned", "daily only",
                                 "weekly only"}
    for attr in ("weekly_structure", "daily_structure"):
        got = getattr(account, attr)
        assert got is None or len(got) == 3, \
            f"{attr} must be None or (direction, when, price), got {got!r}"


# --- structure is the frame, not a third opinion ------------------------

def test_a_rejection_against_its_own_structure_is_not_a_bias():
    """repeating-system t=421-424: "we have daily reject, daily IN
    ALIGNMENT WITH THE STRUCTURE".

    Treating rejection, sweep and structure as three independent
    direction-producers put "Weekly says bearish" and "Weekly
    structurally bullish" in the same message on EURCHF, over a chart
    that was plainly an uptrend with a two-week pullback. Three voters
    cannot help but contradict each other."""
    cascade = Cascade(2)
    _install(cascade, "lower", Direction.BEARISH)
    # ...but the Daily's own structure points the other way.
    cascade.daily_structure.broke_at[Direction.BULLISH] = \
        (T0 + pd.Timedelta(hours=3), 1.1100)

    account = cascade.explain()
    assert account.direction != Direction.BEARISH, \
        "a rejection that opposes its own structure was taken as a bias"


def test_a_rejection_with_no_structure_yet_is_not_a_bias():
    """A rejection with nothing to align to is not a bias, it is a
    rejection. Bishop starts from structure every time."""
    cascade = Cascade(2)
    route = cascade.lower_levels
    route._rejections[Direction.BEARISH].append(T0)
    route._breaks.newest_break[Direction.BEARISH] = T0 + pd.Timedelta(hours=1)

    assert cascade.explain().direction is None


def test_the_message_can_no_longer_contradict_itself():
    """The property the whole change exists for: a rung's stated
    direction and that timeframe's structural direction must agree,
    because one is now gated on the other."""
    for side in (Direction.BULLISH, Direction.BEARISH):
        cascade = Cascade(2)
        _install(cascade, "lower", side)
        account = cascade.explain()
        assert account.direction == side
        assert account.daily_structure is not None
        assert account.daily_structure[0] == side, \
            "the rung says one thing and its structure says another"


# --- structure IS the bias ----------------------------------------------

def test_structure_alone_establishes_a_bias():
    """repeating-system t=396-409: "on the weekly you can see that we are
    bullish... we've been having breakouts to the upside. So I know that
    my weekly is bullish... SO WE ARE STILL BULLISH NO MATTER WHAT."

    No key level and no sweep is named there. Requiring one is why most
    instruments reported "nothing established yet" on a weekly that
    plainly had a direction."""
    cascade = Cascade(2)
    for bar in rising_break(0, 1.1000, unit="days"):
        cascade.push_daily(bar, bar.time)

    account = cascade.explain()
    assert account.direction == Direction.BULLISH
    assert account.evidence is None, "no setup yet, and that is fine"
    assert account.daily_structure[0] == Direction.BULLISH


def test_the_weekly_carries_it_when_the_daily_has_no_structure():
    cascade = Cascade(2)
    for bar in rising_break(0, 1.1000, unit="days"):
        cascade.push_weekly(bar, bar.time)

    account = cascade.explain()
    assert account.direction == Direction.BULLISH
    assert account.rung == "Weekly"
    assert account.alignment == "weekly only"


def test_no_structure_anywhere_is_the_only_no_bias_case():
    cascade = Cascade(2)
    for i in range(10):
        cascade.push_daily(c(i, 1.10, 1.1005, 1.0995, 1.10, "days"), None)
    assert cascade.explain().direction is None


def test_a_setup_is_reported_only_when_it_agrees_with_the_structure():
    """"daily reject, daily IN ALIGNMENT WITH THE STRUCTURE". A rejection
    pointing the other way is not a bias and is not a setup either."""
    cascade = Cascade(2)
    _install(cascade, "lower", Direction.BULLISH)
    account = cascade.explain()
    assert account.direction == Direction.BULLISH
    assert account.evidence is not None, "the aligned rejection is the setup"

    against = Cascade(2)
    _install(against, "lower", Direction.BEARISH)
    against.daily_structure.broke_at[Direction.BULLISH] = \
        (T0 + pd.Timedelta(hours=9), 1.1100)
    account = against.explain()
    assert account.direction == Direction.BULLISH, "structure decides"
    assert account.evidence is None, "the bearish rejection is not a setup"


def test_the_most_recent_breakout_is_the_most_recent_one():
    """NAS100 reported "Daily structurally bearish, through 29427 on
    2026-08-20" over a chart that had since rallied a thousand points.
    `broke_at` only updated when a NEWER SWING was broken, so a fresh
    break of an older swing never registered -- a month-stale reading of
    the present."""
    t = BreakTracker(2)
    t._bump(Direction.BEARISH, T0 + pd.Timedelta(days=20),
            T0 + pd.Timedelta(days=21), 1.0900)
    # a later break, of a swing that formed EARLIER
    t._bump(Direction.BULLISH, T0 + pd.Timedelta(days=5),
            T0 + pd.Timedelta(days=40), 1.1200)

    from ..cascade import structural_direction
    got = structural_direction(t)
    assert got[0] == Direction.BULLISH, "the stale break won"
    assert got[1] == T0 + pd.Timedelta(days=40)
