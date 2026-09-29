"""
Bias, one rung of the cascade, answered in constant time.

WHY THIS EXISTS

bias.py holds the rules, as pure predicates over a list of candles, each
one cited. That is the right shape for saying what the rule IS and for
testing it, and the wrong shape for asking it thirty thousand times.
`bias_established` scans the higher series for a rejection and then calls
`breakout_after`, which rebuilds every swing in the lower series from
scratch and rescans for a close beyond each one. Asked once per H4 close,
over a series that keeps growing, that is quadratic:

     3000 H1 bars    0.53s
     6000 H1 bars    2.13s
    12000 H1 bars    8.09s
    24000 H1 bars   32.93s

Four times the work for twice the history. EURUSD's cached H1 is about
155k rows, which extrapolates to roughly 23 minutes for one instrument
and most of a day for all 27 -- and the whole reason this package walks
forward one candle at a time is that the old engine did exactly this and
took most of an hour per instrument. stream.py promises "each new candle
does a fixed amount of work regardless of how much history precedes it".
_bias_now was the one place breaking that promise.

HOW THE SAME ANSWER IS REACHED WITHOUT THE RESCAN

Two observations turn the whole thing into two bisects.

  A LEVEL IS REJECTED AT ONCE, AND ONLY THE FIRST TIME COUNTS. So the
  rejection time can be recorded when it happens, as higher candles
  arrive, instead of being searched for afterwards.

  "IS THERE A SWING FORMED AFTER TIME T THAT HAS SINCE BEEN BROKEN?" is
  answered by ONE number per direction: the formation time of the NEWEST
  broken swing. If that is later than T the answer is yes, and if it is
  not, then no swing after T has been broken either -- because it is the
  newest. No scan.

Then "the newest rejection whose breakout has happened" is a binary
search over rejection times, not a walk.

WHAT IS DELIBERATELY NOT REPRODUCED

`bias_established` measures "after the rejection" from the first lower
candle at or after the rejection time, and requires the swing to form
strictly after THAT candle. Here it is measured from the rejection time
itself, which is a hair more permissive and is the thing the rule
actually says -- a swing formed after the rejection. bias.py stays as
written, because it is what the tests and the citations hang on.

NO FUTURE

Every push takes one closed candle. A swing cannot be broken before
LevelStream has confirmed it, and it cannot be confirmed until n candles
sit either side, so nothing here can react to a swing the market has not
finished making.
"""

from __future__ import annotations

import bisect
from dataclasses import dataclass, replace

from ..engine.candles import Candle
from ..engine.structure import Direction
from .bias import rejected_at
from .levels import KeyLevel
from .stream import BreakTracker, LevelStream
from .sweep import Evidence, LiquidityBias


def _as_pair(route: LiquidityBias):
    """LiquidityBias answers with a direction; give it the same shape as
    BiasRoute so a rung can compare its two routes."""
    got = route.direction()
    if got is None or route.latest is None:
        return None
    return (got, route.latest[1])


def _liquidity_evidence(route: LiquidityBias):
    """That route's evidence, with the confirming break filled in."""
    got = route.direction()
    if got is None or route.evidence is None:
        return None
    confirmed = route.confirmation(got) or (None, None)
    return replace(route.evidence, confirmed_at=confirmed[0],
                    confirmed_price=confirmed[1])


def structural_direction(tracker):
    """A timeframe's own most recent break of structure.

    Returns (direction, when, price) or None. "Most recent" is by the
    time of the CLOSE THROUGH, not of the swing it broke -- "the most
    recent breakout is to the downside" is a statement about when price
    did something, not about when the level it did it to was formed.

    A tie -- both directions broken at the same instant, which happens
    when one candle closes through swings on both sides -- answers None,
    the same way `_agree` below and `LiquidityBias` already answer an
    ambiguous story. The dict is iterated in insertion order, so without
    this the winner would be whichever direction happened to be bumped
    first, and two runs over the same candles could disagree.
    """
    best = None
    tied = False
    for side, at in sorted(getattr(tracker, "broke_at", {}).items(),
                           key=lambda kv: str(kv[0])):
        when, price = at
        if when is None:
            continue
        if best is None or when > best[1]:
            best = (side, when, price)
            tied = False
        elif when == best[1]:
            tied = True
    return None if tied else best


@dataclass(frozen=True)
class BiasAccount:
    """WHY the bias is what it is, in enough detail to tell the story."""
    direction: Direction | None
    rung: str = ""                 # which timeframe carries the bias
    evidence: object = None        # the SETUP inside it, if one has shown
    other_rung: str = ""
    other_direction: Direction | None = None
    other_evidence: object = None
    dropped_reason: str = ""
    # aligned | not aligned | daily only | weekly only
    alignment: str = ""
    # Each timeframe's own most recent break of structure, as
    # (direction, when, price) or None. THIS IS THE BIAS -- see
    # Cascade.explain.
    weekly_structure: object = None
    daily_structure: object = None


class BiasRoute:
    """One rung: something happens on the higher timeframe, the next one
    down breaks structure the same way.

    Both taught routes have this shape, which is why they share a class:

        key levels   a level rejected and closed back from
                                                    (bias-1 t=380-413)
        liquidity    a previous period's extreme swept with the other side
                     standing              (daily-routine t=534-540, and
                                            sweep.LiquidityBias)

    This class carries the key-level route; `LiquidityBias` carries the
    other, and `Cascade` below runs both on both rungs.
    """

    def __init__(self, n: int):
        self.n = n
        self._levels = LevelStream(n)
        self._seen: set = set()                  # levels already rejected at
        self._breaks = BreakTracker(n)
        # Rejection times per direction, ascending. Ascending so the
        # newest one before a given moment is a bisect rather than a walk.
        self._rejections: dict[Direction, list] = {
            Direction.BULLISH: [], Direction.BEARISH: []}
        # time -> the level price rejected there, so the route can say
        # WHICH level it was and not merely that one was. Named apart
        # from `_levels` (the LevelStream) on purpose: shadowing it was
        # an instant AttributeError, which is the good kind of mistake.
        self._level_at: dict[object, float] = {}

    def push_higher(self, candle: Candle):
        """One closed candle of the timeframe the levels live on."""
        self._levels.push(candle)
        for level in self._levels.standing():
            key = (level.time, level.price, level.bias)
            if key in self._seen:
                continue
            if rejected_at(candle, level):
                self._seen.add(key)
                self._rejections[level.bias].append(candle.time)
                self._level_at[candle.time] = level.price

    def push_lower(self, candle: Candle):
        """One closed candle of the next timeframe down."""
        self._breaks.push(candle)

    def direction(self):
        """The newest rejection that the lower timeframe has confirmed.

        Returns (direction, rejection time) or None. The time comes back
        so a caller running several rungs can prefer the most recent
        story rather than the first one it happened to ask.
        """
        best = None
        for side, times in self._rejections.items():
            newest_break = self._breaks.newest_break.get(side)
            if newest_break is None or not times:
                continue
            # The newest rejection that happened BEFORE that break: any
            # later rejection has nothing confirming it yet.
            idx = bisect.bisect_left(times, newest_break)
            if idx == 0:
                continue
            when = times[idx - 1]
            if best is None or when > best[1]:
                best = (side, when)
        return best

    def evidence(self):
        """The rejection currently carrying this rung, described.

        Returns an Evidence or None. Built on demand rather than stored,
        because `direction()` decides which rejection is the live one and
        that answer can change as the lower timeframe breaks again."""
        got = self.direction()
        if got is None:
            return None
        side, when = got
        confirmed = self._breaks.broke_at.get(side) or (None, None)
        return Evidence(kind="rejection", direction=side, at=when,
                        level=self._level_at.get(when),
                        confirmed_at=confirmed[0], confirmed_price=confirmed[1])


class Cascade:
    """Bias, by every route the course gives, on every rung it gives them.

    Four combinations, and before this only two were wired:

        Weekly level rejected   -> Daily breaks         key levels, upper
        Weekly liquidity swept  -> Daily breaks         liquidity, upper
        Daily level rejected    -> H4 breaks            key levels, lower
        Daily liquidity swept   -> H4 breaks            liquidity, lower

    The liquidity route ran only on the Weekly and the key-level route
    only on the Daily, which was an accident of the order they were built
    in rather than anything the source says. Bishop's checklist is
    "previous daily weekly low sweep, what's daily breakout to the upside"
    (daily-routine t=534-540) -- daily OR weekly -- and repeating-system
    t=60-66 is explicit that bias can be built "from any timeframe".

    PRECEDENCE

    The lower rung wins, because that is what he does when the two
    disagree: "those two time frames are not in alignment, so that goes to
    the four hours ... I CAN LEAVE THE WEEKLY, I use my daily at my four
    hours" (daily-routine t=399-417).

    Within one rung the source gives no precedence between a key level and
    liquidity, so neither is invented: if both answer and they DISAGREE,
    the rung says nothing. An ambiguous story is not a bias, which is the
    same answer LiquidityBias already gives when one candle sweeps a high
    and a low at once.
    """

    def __init__(self, n: int):
        self.upper_levels = BiasRoute(n)           # Weekly levels, Daily breaks
        self.lower_levels = BiasRoute(n)           # Daily levels, H4 breaks
        self.upper_liquidity = LiquidityBias(n)    # Weekly sweeps, Daily breaks
        self.lower_liquidity = LiquidityBias(n)    # Daily sweeps, H4 breaks
        # THE TIMEFRAME'S OWN STRUCTURE, which is where Bishop's routine
        # actually starts: "weekly structurally we're still bearish",
        # "we've been having breakouts to the upside, so I know my weekly
        # is bullish" (repeating-system t=388-402, daily-routine
        # t=765-788). Both routes above use a timeframe as the place a
        # level or a sweep lives, and neither reads its own most recent
        # break of structure. That is a third thing the weekly says and
        # it was missing entirely.
        self.weekly_structure = BreakTracker(n)
        self.daily_structure = BreakTracker(n)

    def push_weekly(self, candle: Candle, closed_at):
        self.upper_levels.push_higher(candle)
        self.upper_liquidity.push(candle, closed_at)
        self.weekly_structure.push(candle)

    def push_daily(self, candle: Candle, closed_at):
        # The Daily is the lower rung of the Weekly's routes and the
        # higher rung of its own, which is the cascade being fractal
        # rather than a special case.
        self.upper_levels.push_lower(candle)
        self.upper_liquidity.push_lower(candle)
        self.lower_levels.push_higher(candle)
        self.lower_liquidity.push(candle, closed_at)
        self.daily_structure.push(candle)

    def push_h4(self, candle: Candle):
        self.lower_levels.push_lower(candle)
        self.lower_liquidity.push_lower(candle)

    def direction(self):
        """The bias standing now, or None."""
        account = self.explain()
        return account.direction

    def explain(self) -> BiasAccount:
        """The bias AND the reason for it.

        STRUCTURE IS THE BIAS. Not a filter on one, not a third opinion
        alongside the rejection and the sweep -- the bias itself.
        repeating-system t=396-409, on US30:

            "on the weekly timeframe you can see that we are bullish...
             we've been having breakouts to the upside. So I know that my
             weekly is bullish. My daily... the recent breakout was still
             to the upside. At no point was there a bearish breakout. SO
             WE ARE STILL BULLISH NO MATTER WHAT."

        and only THEN, t=415-424:

            "price eventually came and rejected off this key level. So
             now we have daily reject, DAILY IN ALIGNMENT WITH THE
             STRUCTURE."

        So the order is: structure says which way, and a key level
        rejected or liquidity swept in agreement with it is the SETUP
        inside that direction. This had it inverted -- it required a
        rejection or a sweep and used structure only to veto them, which
        is why most instruments reported "nothing established yet" on a
        weekly that plainly had a direction.

        The Daily carries the operative bias when it has structure,
        because the H4 setup hangs off it; the Weekly's agreement is the
        probability statement, exactly as Bishop reads it.
        """
        weekly_struct = structural_direction(self.weekly_structure)
        daily_struct = structural_direction(self.daily_structure)

        if daily_struct is None and weekly_struct is None:
            return BiasAccount(None)

        # The SETUP inside that direction: a key level rejected or
        # liquidity swept, in alignment with the structure. Reported as
        # supporting detail, never as a competing direction. Computed
        # BEFORE the account is built -- it used to be passed positionally
        # into BiasAccount after two more fields were added, so a setup
        # landed in `weekly_structure` and Telegram died with "too many
        # values to unpack" on every structure-only bias (which, now that
        # structure alone carries the direction, is most of them).
        # Everything below builds BiasAccount by KEYWORD for that reason.
        if daily_struct is not None:
            direction = daily_struct[0]
            rung, other_rung = "Daily", "Weekly"
            other_direction = weekly_struct[0] if weekly_struct else None
            if weekly_struct is None:
                alignment = "daily only"
                reason = ("the Weekly has not broken structure either way "
                          "yet, so there is nothing to align with")
            elif other_direction != direction:
                # daily-routine t=399-417: "those two time frames are not
                # in alignment, so that goes to the four hours ... I can
                # leave the weekly. I probably just target a good
                # liquidity."
                alignment = "not aligned"
                reason = (f"the Weekly is {other_direction.value} and the "
                          f"Daily is {direction.value} — they disagree, so "
                          f"the Weekly is left and the Daily leads")
            else:
                alignment = "aligned"
                reason = "the Weekly and the Daily agree"
        else:
            direction = weekly_struct[0]
            rung, other_rung = "Weekly", "Daily"
            other_direction = None
            alignment = "weekly only"
            reason = "the Daily has not broken structure either way yet"

        setup = _setup_evidence(self, rung, direction)
        other_setup = _setup_evidence(self, other_rung, other_direction)

        return BiasAccount(
            direction=direction, rung=rung, evidence=setup,
            other_rung=other_rung, other_direction=other_direction,
            other_evidence=other_setup, dropped_reason=reason,
            alignment=alignment, weekly_structure=weekly_struct,
            daily_structure=daily_struct)


def _setup_evidence(cascade, rung: str, direction):
    """A rejection or a sweep on `rung`, but only in `direction`.

    None when that rung has nothing pointing the same way as the
    structure -- which is a real answer: the bias stands on the
    structure, and the setup simply has not presented itself yet.
    """
    if direction is None or rung not in ("Daily", "Weekly"):
        return None
    prefix = "lower" if rung == "Daily" else "upper"
    lower_name = "H4" if rung == "Daily" else "Daily"

    levels = getattr(cascade, prefix + "_levels")
    liquidity = getattr(cascade, prefix + "_liquidity")

    from_levels = levels.direction()
    if from_levels is not None and from_levels[0] == direction:
        return _stamp(levels.evidence(), rung, lower_name)

    got = _as_pair(liquidity)
    if got is not None and got[0] == direction:
        return _stamp(_liquidity_evidence(liquidity), rung, lower_name)
    return None


def _stamp(evidence, higher: str, lower: str):
    """Tell a piece of evidence which timeframes it belongs to, so a
    sentence about it does not have to be told separately."""
    if evidence is None:
        return None
    return replace(evidence, higher=higher, lower=lower)


def _agree(*answers):
    """One rung's answer: the newest, unless its routes contradict.

    None when they disagree. The course gives no tie-break between a key
    level and liquidity at the same rung, and picking one would be exactly
    the kind of number-free-looking invention this package exists to stop.
    """
    got = [a for a in answers if a is not None]
    if not got:
        return None
    if len({a[0] for a in got}) > 1:
        return None
    return max(got, key=lambda a: a[1])[0]
