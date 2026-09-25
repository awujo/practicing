"""
The L in SLK: liquidity, and the story that says which key level to take.

This is the piece the old engine never had, and its absence is why that
engine took every level price touched. Bishop does not trade a key level
because price reached it. He trades the key level that the liquidity
price just took is RESTING CLOSEST TO -- and he refuses the others by
name.

TWO TYPES, ONE CANDLE -- video-18 t=282-338

    "the two types of liquidity is internal range and external range ...
     we use the single candle formation as our explanation for the
     various forms of liquidity, so we said this particular single
     candle is going to represent both the monthly, represents the
     weekly, going to represent the daily, it's going to represent the
     four hours, the two hours and even the one hour as well ... so if
     it is a BULLISH formation this LOW is going to be the INTERNAL
     range, the HIGH is going to be the EXTERNAL range; if it's a
     BEARISH formation this HIGH is going to be the INTERNAL range, this
     LOW is going to be the EXTERNAL range"

So a liquidity point is not a special object that needs finding. Every
candle rests two of them, and which one is internal is a function of the
bias standing at the moment one gets taken. That is why `role` is
decided at take time here rather than stored on the point.

It also means "single candle liquidity", "a series of candles" and
"structural liquidity" are one mechanism, not three -- repeating-system
t=267-354: "it's not all the time your form of liquidity is going to be
a single candle, sometimes it can be more than one candle, sometimes you
can have a series of candles ... sometimes it's also going to be like
structural liquidity". A swing's extreme is some candle's extreme, and a
series of candles at one price is several points within a pip of each
other. Registering every candle's high and low covers all three without
a separate detector for each, and the only thing a caller must not do is
count a series as several setups.

WHAT THE TAKE MEANS -- video-18 t=418-446

    "for every external range liquidity that is taken, price will
     reverse ... every external range liquidity taken is going to lead
     to a RETRACEMENT and every internal range liquidity [leads] towards
     an EXPANSION"

and then, decisively, t=457-489:

    "you know that for example we are bullish ... maybe there is a
     particular key level that is actually resting somewhere around here
     like a V-shaped key level. But you know that THE REASON WHY YOU'RE
     NOT GOING TO TAKE this V-shaped key level or any key level that is
     resting is because you can actually pay attention to the story ...
     An external range liquidity has been taken, definitely we want to
     see this particular low go next. And the moment this particular low
     go[es] next, price will look for the nearest liquidity, that is the
     NEAREST KEY LEVEL THAT THIS LOW IS RESTING CLOSE TO, and after it
     looks for it, [you] begin to see price rally to the upside"

Bishop states the same rule from the other end in repeating-system
t=105-139, as his own routine:

    "what I want to see is a single candle to be used as liquidity ...
     And then I now want to play the next, the CLOSEST KEY LEVEL CLOSE
     TO IT. But while I'm doing that, I would want to wait for a
     REJECTION from that particular key level. Then I look for
     confirmation entry on the lower timeframe."

Two sources, independently, the same three steps. So:

    1. an INTERNAL range liquidity point is taken     (expansion is due)
    2. the eligible key level is the NEAREST one to that point -- not
       any level price happens to reach
    3. price must REJECT from it before the lower timeframe matters

Step 2 is the whole filter, and it is an argmin, not a distance
threshold. There is no number in this module.

"TAKEN" IS A TRADE THROUGH

video-18 t=366-371 says "price now sweeps this particular four hour high
and it closes below", which could be read as requiring the close back.
It is not the definition used here, for two reasons. The phrase
everywhere else is "take out" ("this high now has been taken", t=1062;
"take out our low", t=390), and at t=395-404 the SAME candle is allowed
to take the high and then go for the low -- one candle cannot close back
on both sides. So a point is taken the moment price trades through it,
which is also how liquidity.py reads its targets, and the two halves of
the strategy must not disagree about what a sweep is.

NO FUTURE

`LiquidityStream.push` and `SetupStream.push` take one closed candle.
A candle's own extremes are registered AFTER that candle has been used
to consume resting points, so no candle can take its own liquidity, and
nothing in here can see the candle that has not arrived.

WHAT IS NOT BUILT HERE, AND IS NOT PRETENDED AWAY

A level that gets closed through stops being a level on that side, and
this module remembers that and refuses to arm it again. What it does NOT
do is USE it the other way. bias-1 t=195-300 says a disrespected sell
level becomes a buy level, and levels.flip exists for exactly that, but
the level stream never feeds a flip back in, so from here a disrespected
level is simply gone. That is a missing entry, not a wrong one.

The other absence: the ERL half of the cycle is read but not acted on.
t=1077-1090 has the single candle's own opposite extreme as the target
of the expansion, while liquidity.py takes targets from Daily and Weekly
periods only. Both are untaken extremes beyond entry, so they are the
same kind of object, and whether the setup timeframe's own extremes
belong in that search is a question to MEASURE, not to settle here by
quietly adding a series to the call.

THE ONE AMBIGUITY, NAMED

A single candle can both take the liquidity and reject the level, and
four numbers cannot say in which order. The source blesses the same
candle doing two things (t=395-404), so it is allowed, and `same_candle`
on the emitted Setup marks it -- countable, the same way `Fill` marks a
fill that also reached its stop.
"""

from __future__ import annotations

import bisect
from dataclasses import dataclass

from ..engine.candles import Candle
from ..engine.structure import Direction
from .bias import rejected_at
from .levels import KeyLevel, disrespected_by
from .stream import BreakTracker


@dataclass(frozen=True)
class LiquidityPoint:
    """One extreme of one candle, resting until price trades through it."""
    time: object
    price: float
    kind: str                  # "high" | "low"


@dataclass(frozen=True)
class Sweep:
    """A resting liquidity point that price has just taken."""
    point: LiquidityPoint
    taken_at: object
    role: str                  # "internal" | "external", for the bias then


@dataclass(frozen=True)
class Setup:
    """Liquidity taken, and the nearest key level to it has rejected.

    This is what the course calls having "played the key level", and it
    is the precondition for looking at the lower timeframe at all.
    """
    level: KeyLevel
    sweep: Sweep
    rejected_at: object
    same_candle: bool          # one candle both took and rejected


def internal_kind(bias: Direction) -> str:
    """Which extreme is internal range liquidity under this bias.

    video-18 t=321-331, quoted in full above: bullish formation, the low
    is internal; bearish formation, the high is internal.
    """
    return "low" if bias == Direction.BULLISH else "high"


def external_kind(bias: Direction) -> str:
    """The other one. Kept as its own function because the asymmetry is
    the entire content of the rule and a caller writing `not internal`
    inline is a caller about to get it backwards."""
    return "high" if bias == Direction.BULLISH else "low"


def role_of(kind: str, bias: Direction) -> str:
    return "internal" if kind == internal_kind(bias) else "external"


def bias_from_internal(kind: str) -> Direction:
    """The formation in which `kind` is the internal range -- the inverse
    of `internal_kind`. A low taken is a bullish story, a high taken a
    bearish one."""
    return Direction.BULLISH if kind == "low" else Direction.BEARISH


class LiquidityStream:
    """Resting single-candle liquidity on one timeframe.

    Feed it closed candles; it reports which resting points each one
    took. Points are held sorted by price and consumed by bisect, so a
    run costs O(points) rather than O(bars x points) -- the same reason
    the level detector is a stream and not a rescan.

    Deliberately bias-free. A high is a high; whether it was internal or
    external range liquidity depends on the formation standing when it
    was taken, and that is not this class's business.
    """

    def __init__(self):
        self._highs: list[tuple[float, LiquidityPoint]] = []
        self._lows: list[tuple[float, LiquidityPoint]] = []

    def __len__(self):
        return len(self._highs) + len(self._lows)

    def resting(self) -> list[LiquidityPoint]:
        return [p for _, p in self._highs] + [p for _, p in self._lows]

    def push(self, candle: Candle) -> list[Sweep]:
        """Take what this candle takes, then rest what it leaves.

        Returns the points taken, without a role -- `role_of` needs the
        bias, and callers that have one use `SetupStream` instead.
        Consuming before registering is what stops a candle taking its
        own high or low.
        """
        taken = []

        cut = bisect.bisect_right(self._highs, candle.high, key=lambda p: p[0])
        taken.extend(Sweep(p, candle.time, "") for _, p in self._highs[:cut])
        del self._highs[:cut]

        cut = bisect.bisect_left(self._lows, candle.low, key=lambda p: p[0])
        taken.extend(Sweep(p, candle.time, "") for _, p in self._lows[cut:])
        del self._lows[cut:]

        bisect.insort(self._highs,
                      (candle.high, LiquidityPoint(candle.time, candle.high, "high")),
                      key=lambda p: p[0])
        bisect.insort(self._lows,
                      (candle.low, LiquidityPoint(candle.time, candle.low, "low")),
                      key=lambda p: p[0])
        return taken


def nearest_level(point: LiquidityPoint, levels: list[KeyLevel],
                  bias: Direction) -> KeyLevel | None:
    """The key level this liquidity point is resting closest to.

    "the nearest key level that this low is resting close to"
    (video-18 t=481-489) / "the next, the closest key level close to it"
    (repeating-system t=120-128).

    Only levels used in the trade's own direction are candidates -- a
    buy is taken from a level that is currently a buy level. No side
    constraint beyond that: the source says "resting close to", which is
    symmetric, and the operator's own refinement on 2026-09-22 was that
    a return may overshoot the level rather than stop at it, so a level
    just above a swept low is not disqualified for being above it.

    None when no level in that direction exists yet, which early in a
    series is the honest answer.
    """
    candidates = [l for l in levels if l.bias == bias]
    if not candidates:
        return None
    return min(candidates, key=lambda l: abs(l.price - point.price))


@dataclass
class _Pending:
    """Liquidity taken, waiting on the level to reject or be lost."""
    level: KeyLevel
    sweep: Sweep
    born_at: object


def level_identity(level: KeyLevel) -> object:
    """What "one setup per level" is counted on.

    The level, not the sweep that entitled it. A retracement takes a
    string of lower lows, each of which is liquidity, and every one of
    them has the same key level as its nearest -- so keying on the sweep
    produced several identical setups on one candle. That is the same
    mistake that put three orders three pips apart on one H1 bar, and it
    has the same answer: THE LEVEL IS THE SETUP.

    First arming wins, and later sweeps into a level already armed are
    the same event arriving again -- the operator on 2026-09-22, against
    caging a level in a window: "it's about using it when the first time
    it presented itself".
    """
    return (level.time, level.price, level.bias)


class SetupStream:
    """The three steps, one closed candle at a time.

    Fed the SETUP timeframe (H4 in the cascade the course teaches) along
    with the bias standing at that candle's close and the key levels
    confirmed so far. Emits a Setup the moment price rejects from the
    nearest key level to liquidity it has taken.

    Bias is a push argument rather than state because it is not this
    object's to remember -- it comes from the Daily, and a Setup armed
    under a bias that has since flipped is the order book's problem to
    cancel, not this detector's to hide.
    """

    def __init__(self):
        self._liquidity = LiquidityStream()
        self._pending: dict[object, _Pending] = {}
        self._lost: set[object] = set()

    def __len__(self):
        return len(self._pending)

    def pending(self) -> list[_Pending]:
        return list(self._pending.values())

    def push(self, candle: Candle, bias: Direction | None,
             levels: list[KeyLevel]) -> list[Setup]:
        """One closed candle. Returns the setups that just became live.

        With no bias there is no internal range -- which extreme is
        internal is a function of the formation, and without one the
        question has no answer. Resting liquidity is still updated, so
        the points are there when a bias arrives.

        A pending setup whose level does not belong to the bias standing
        now is dropped, which covers both the bias going away and the
        bias flipping: video-03 t=1892-1914 is Bishop cancelling a limit
        order because the analysis that justified it had changed, and a
        setup armed under the old read is the same thing one step
        earlier.
        """
        self._pending = {k: p for k, p in self._pending.items()
                         if p.level.bias == bias}
        if bias is None:
            self._liquidity.push(candle)
            return []

        # 1. liquidity this candle took, internal ones only: an external
        #    take means a retracement is due, and buying into a
        #    retracement is the mistake t=465-481 exists to prevent.
        for sweep in self._liquidity.push(candle):
            if role_of(sweep.point.kind, bias) != "internal":
                continue
            level = nearest_level(sweep.point, levels, bias)
            if level is None:
                continue
            key = level_identity(level)
            if key in self._lost or key in self._pending:
                continue
            self._pending[key] = _Pending(
                level, Sweep(sweep.point, sweep.taken_at, "internal"),
                candle.time)

        # 2. rejection, or the level lost. New pendings are included, so
        #    one candle may both take and reject -- t=395-404 allows it,
        #    and `same_candle` records that it happened.
        live = []
        for key, p in list(self._pending.items()):
            if disrespected_by(candle, p.level):
                del self._pending[key]
                self._lost.add(key)           # closed through: not a level now
            elif rejected_at(candle, p.level):
                live.append(Setup(p.level, p.sweep, candle.time,
                                  same_candle=p.born_at == candle.time))
                del self._pending[key]
        return live


class LiquidityBias:
    """Bias from Bishop's own checklist, which is not the key-level one.

    bias-1 t=380-413 builds bias WITH KEY LEVELS: rejection, closure,
    breakout on the next timeframe down (bias.py). That is one of the
    two routes. His morning routine uses the other, and he reads it off
    the same checklist three times in one video:

        "I have my CHECKLIST: previous daily weekly low sweep, what's
         daily breakout to the upside"      (daily-routine t=534-540)

        "structure bearish, we had a PREVIOUS WEEKLY HIGH SWEEP WITH A
         LOW STANDING, let's go to the daily. What's daily doing? Daily
         also broke out to the downside"    (daily-routine t=1012-1024)

        "we had this previous weekly [high] sweep ... that's good, so the
         daily timeframe, I see ... bearish breakout"   (t=782-793)

    Two items, not three, and the first is LIQUIDITY rather than a key
    level. Same shape as the other route -- the higher timeframe does
    something, the next one down breaks structure to confirm it -- which
    is why both live behind one name in the driver. S, L and K are three
    ways in, not a conjunction, and requiring a key level AND a sweep
    would be inventing an "and" nobody said.

    WHICH DIRECTION A SWEEP MEANS

    Exactly the rule from video-18 t=321-331 again: a low taken is the
    internal range of a bullish formation, a high taken the internal
    range of a bearish one. "Previous weekly high sweep" -> bearish. And
    "WITH A LOW STANDING" is the other half of the same single-candle
    formation still untaken, which is what makes the expansion down to it
    the thing to expect. A candle that takes both extremes of a previous
    period leaves no story, and establishes nothing here.

    THE WEEKLY IS NOT A GATE

    It was tempting to require the Daily to agree with the Weekly. The
    source forbids it, in as many words -- daily-routine t=399-417:

        "daily is now saying bearish, in that case now those two time
         frames are not in alignment, so that goes to the four hours ...
         I CAN LEAVE THE WEEKLY, I use my daily at my four hours. I
         probably just target a good liquidity"

    So a disagreement drops the weekly and trades daily-to-H4, which is
    what the driver does anyway, and the one consequence he names is on
    the TARGET -- take a nearer liquidity -- which liquidity.py already
    does by always taking the nearest. Making the weekly a filter would
    have deleted trades he explicitly still takes.

    THE AMBIGUITY, NAMED

    A weekly candle says a low was swept during that week; it cannot say
    on which day. So a daily break inside the same week might have come
    BEFORE the sweep that is supposed to have caused it. `push` therefore
    takes the week's CLOSE time and only daily candles after it count.
    That loses some of his same-week entries, and it is still the right
    way round: an engine that cannot tell cause from coincidence should
    err towards fewer trades, not towards flattering ones.
    """

    def __init__(self, n: int):
        self._stream = LiquidityStream()
        self._taken: set[tuple[object, str]] = set()
        self.latest: tuple[Direction, object] | None = None
        self._breaks = BreakTracker(n)

    def push(self, candle: Candle, closed_at: object) -> None:
        """One CLOSED higher-timeframe candle, and the time it closed.

        `closed_at` is passed rather than derived because the caller has
        already computed it to decide this candle had closed at all, and
        recomputing it here would be a second place to get it wrong.
        """
        sweeps = self._stream.push(candle)
        for s in sweeps:
            self._taken.add((s.point.time, s.point.kind))

        implied = set()
        for s in sweeps:
            other = "high" if s.point.kind == "low" else "low"
            if (s.point.time, other) in self._taken:
                continue                  # both sides gone: no story left
            implied.add(bias_from_internal(s.point.kind))

        if len(implied) == 1:
            self.latest = (implied.pop(), closed_at)
        elif implied:
            self.latest = None            # a high and a low: no story

    def push_lower(self, candle: Candle) -> None:
        """One CLOSED candle of the next timeframe down -- the one that has
        to break structure for the checklist's second item."""
        self._breaks.push(candle)

    def direction(self) -> Direction | None:
        """The bias this sweep has established, once the lower timeframe
        has confirmed it.

        None until it breaks structure the same way: the second checklist
        item is something price must DO, the same as condition 3 of the
        key-level route.

        Answered from BreakTracker's one number per direction rather than
        by rescanning the lower series. The rescan was quadratic and it is
        what made a 24k-bar replay take 33 seconds -- see cascade.py.
        """
        if self.latest is None:
            return None
        direction, when = self.latest
        return direction if self._breaks.broke_after(when, direction) else None
