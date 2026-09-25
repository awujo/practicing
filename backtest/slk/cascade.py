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
        """The bias AND the reason for it, both rungs accounted for."""
        lower_levels = self.lower_levels.direction()
        lower_liquidity = _as_pair(self.lower_liquidity)
        upper_levels = self.upper_levels.direction()
        upper_liquidity = _as_pair(self.upper_liquidity)

        lower = _agree(lower_levels, lower_liquidity)
        upper = _agree(upper_levels, upper_liquidity)

        lower_ev = (self.lower_levels.evidence()
                    if lower_levels is not None and
                    (lower_liquidity is None or lower_levels[1] >= lower_liquidity[1])
                    else _liquidity_evidence(self.lower_liquidity))
        upper_ev = (self.upper_levels.evidence()
                    if upper_levels is not None and
                    (upper_liquidity is None or upper_levels[1] >= upper_liquidity[1])
                    else _liquidity_evidence(self.upper_liquidity))

        if lower is not None:
            # WHICH RUNG "LEADS" IS THE LESS INTERESTING QUESTION.
            #
            # This used to answer "Daily" whenever the Daily rung had an
            # answer, which is nearly always -- so every instrument read
            # "Daily leads" and the Weekly looked like it was not in the
            # model at all. It is, and its agreement is the single thing
            # that separates a high-probability setup from one that may
            # be nothing but a retracement inside the Weekly. So the
            # alignment is what the account leads with now.
            if upper is None:
                alignment = "daily only"
                reason = ("the Weekly has not established a bias of its own "
                          "yet, so there is nothing to align with")
            elif upper != lower:
                # Bishop's own case: "those two time frames are not in
                # alignment, so that goes to the four hours ... I can
                # leave the weekly. I probably just target a good
                # liquidity" (daily-routine t=399-417) -- he still trades
                # it, and he takes less out of it.
                alignment = "not aligned"
                reason = (f"the Weekly says {upper.value} and the Daily says "
                          f"{lower.value} — they disagree, so the Weekly is "
                          f"left and the Daily leads")
            else:
                alignment = "aligned"
                reason = "the Weekly and the Daily agree"
            # Keywords, not positions. BiasAccount has ten fields and a
            # positional call put `alignment` into `weekly_structure`
            # the moment two more were added -- which surfaced as
            # "too many values to unpack" three modules away.
            return BiasAccount(
                direction=lower, rung="Daily",
                evidence=_stamp(lower_ev, "Daily", "H4"),
                other_rung="Weekly", other_direction=upper,
                other_evidence=_stamp(upper_ev, "Weekly", "Daily"),
                dropped_reason=reason, alignment=alignment,
                weekly_structure=structural_direction(self.weekly_structure),
                daily_structure=structural_direction(self.daily_structure))

        if upper is not None:
            return BiasAccount(
                direction=upper, rung="Weekly",
                evidence=_stamp(upper_ev, "Weekly", "Daily"),
                other_rung="Daily",
                dropped_reason="the Daily has not established one of its own",
                alignment="weekly only",
                weekly_structure=structural_direction(self.weekly_structure),
                daily_structure=structural_direction(self.daily_structure))
        return BiasAccount(None,
                            weekly_structure=structural_direction(self.weekly_structure),
                            daily_structure=structural_direction(self.daily_structure))


def _as_pair(route: LiquidityBias):
    """LiquidityBias answers with a direction; give it the same shape as
    BiasRoute so one rung can compare its two routes."""
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


@dataclass(frozen=True)
class BiasAccount:
    """WHY the bias is what it is, in enough detail to tell the story.

    The summary that prompted this said "key level rejected" for all 27
    instruments, because it read the Daily route every time instead of
    the one that actually carried the answer. A report that names the
    wrong cause is worse than a terse one, so this records which rung
    won, by which route, and what happened to the other rung.
    """
    direction: Direction | None
    rung: str = ""                 # "Daily" (Daily->H4) or "Weekly" (Weekly->Daily)
    evidence: object = None        # the Evidence that carried it
    other_rung: str = ""           # the rung that did not lead
    other_direction: Direction | None = None
    other_evidence: object = None
    dropped_reason: str = ""       # why the other rung is not leading
    # Each timeframe's OWN most recent break of structure, as
    # (direction, when, price) or None. "Weekly structurally bearish" is
    # a separate statement from "the weekly rejected a level" and from
    # "the weekly swept a low", and all three are things the weekly says.
    weekly_structure: object = None
    daily_structure: object = None
    # The thing that actually decides quality, and the thing a report
    # that always says "Daily leads" hides completely:
    #   "aligned"      Weekly and Daily agree -- the high-probability case
    #   "not aligned"  they disagree. Tradeable, but it may be nothing more
    #                  than a retracement inside the Weekly, and Bishop
    #                  takes a nearer target when he takes it at all
    #   "daily only"   the Weekly has established nothing yet
    #   "weekly only"  the Daily has not
    alignment: str = ""


def structural_direction(tracker):
    """A timeframe's own most recent break of structure.

    Returns (direction, when, price) or None. "Most recent" is by the
    time of the CLOSE THROUGH, not of the swing it broke -- "the most
    recent breakout is to the downside" is a statement about when price
    did something, not about when the level it did it to was formed.
    """
    best = None
    for side, at in getattr(tracker, "broke_at", {}).items():
        when, price = at
        if when is None:
            continue
        if best is None or when > best[1]:
            best = (side, when, price)
    return best


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
