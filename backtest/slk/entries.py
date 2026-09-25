"""
The other confirmation forms. Four were missing; three are here.

Bishop enumerates his, twice in one breath, entries-part5 t=664-681:

    "Either you see your BREAKOUT, your breakout structure [= sweep and
     break], your ENGULFING -- engulfed open close key levels -- or this
     whereby the LOW OF THIS CANDLE IS S[WEP]T AND THE HIGH IS STILL
     STANDING, giving you a V-shape key level"

4th man gives three, video-14 t=494-497, "not going to be more than
these three things", and they are a FALLBACK SEQUENCE on one key level
rather than rivals -- t=534-538: "IF PRICE DOESN'T DO THIS, the second
thing that we are most likely going to see price do is ...".

Only the engulfed open-close level (5.2) was built. This module adds:

    inducement   4th man's third: after the engulf, the next candle
                 trades close to the key level WITHOUT tapping it, so
                 that candle becomes the liquidity. Price takes it, then
                 plays the key level.        (video-14 t=679-702)

    breakout     Bishop's first: the reaction at the key level leaves a
                 minor swing, and price closes through it.
                                             (part5 t=376-401)

    sweep_break  Bishop's second: the same break, but the reaction first
                 comes back and takes out its own earlier extreme.
                                             (part5 t=401-409)

He rates the last two above everything else: "if you ask me which ones
are likely best, personally I would tell you these two ... you might
take losses, but your losses are going to be minimal compared to other
forms of confirmation entry" (t=409-431).

WHY 5.1 IS NOT A FOURTH ORDER HERE, AND WHAT IS DONE INSTEAD

4th man's first form is a direct mitigation of "another A shape" that
the engulf creates -- video-14 t=505-524: "if you see that price has
actually engulfed and you move to the LINE CHART, you will see that what
price has actually created for us is another A shape ... price is going
to play a direct mitigation of that particular A shape key level".

A line chart plots closes. The peak it shows before an engulf down is
the last close before closes turned, which for the two consecutive up
candles of 5.2 is the SECOND CANDLE'S CLOSE. So on the chart 4th man is
looking at, 5.1 and 5.2 are the same event at two depths: the shallow
return to that close, and the deeper return to the open-close level
itself. That is exactly why he presents them as "if price doesn't do
this, the second thing".

The operator specified the deeper one, in their own words, 2026-09-25:
"we wait for price to return back to the open close that the engulfing
closed, putting your SL at the low of the engulf". Placing a second
order at the shallower depth would break "one order at a time per
level", and swapping the operator's depth for mine is the exact move I
was told to stop making. So `mitigation_price` computes the shallow
depth and it is recorded on the order for MEASUREMENT -- how often price
turned at the close without ever reaching the open -- which is the thing
that would settle whether the shallow depth is worth trading. It is a
number to produce, not a rule to assume.

STOPS COME FROM ONE PRINCIPLE, AND IT IS BISHOP'S

SLK_SPEC 6: "the stop sits where the setup is INVALIDATED, which is
beyond the structure that defines it", and for a confirmation entry
specifically, "in the wick of the confirming candle" -- next t=435,
"stop loss just above this high". So every form here stops at the far
side of the candle that confirmed it, unpadded. 4th man's "10 to 11 pips
is enough" is his practice and the operator ruled it out by name.

NO FUTURE

Every watch takes one closed candle and answers from state it already
had. The minor swings come from LevelStream, which cannot emit a swing
until n candles sit either side of it, so a break is never measured
against a swing the market had not yet made.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..engine.candles import Candle
from ..engine.structure import Direction
from .levels import KeyLevel
from .stream import LevelStream


@dataclass(frozen=True)
class Confirmation:
    """Permission to enter, and where.

    `entry` is where the limit rests and `stop` where the setup is
    invalidated. `form` is carried so the report can separate them:
    Bishop rates breakout and sweep-and-break above the rest, and the
    only way to know whether that holds here is to count them apart.
    """
    form: str                  # "inducement" | "breakout" | "sweep_break"
    entry: float
    stop: float
    at: object                 # the candle that confirmed


def mitigation_price(before: list[Candle], direction: Direction) -> float | None:
    """The line-chart peak an engulfing move leaves behind -- 4th man's
    "another A shape", and the shallow depth of 5.1.

    `before` is the candles up to and excluding the engulfing one, in
    order. Walk back while the closes are still rising (for a bearish
    engulf) and the last one before the turn is the peak the line chart
    draws. No window and no count: the turn is where it is.

    Recorded on the order rather than traded -- see the module note.
    """
    if not before:
        return None
    rising = direction == Direction.BEARISH      # up closes precede a sell
    peak = before[-1].close
    for candle in reversed(before[:-1]):
        if rising and candle.close < peak:
            break
        if not rising and candle.close > peak:
            break
        peak = candle.close
    return peak


def _toward(bar: Candle, direction: Direction) -> float:
    """The extreme of `bar` on the side the key level sits.

    A sell level is above, so the candle reaches for it with its high.
    """
    return bar.high if direction == Direction.BEARISH else bar.low


def _extreme(bars: list[Candle], direction: Direction) -> float | None:
    """The furthest the reaction got on the trade's side.

    For a buy that is the lowest low, which is the first low 5.5's sweep
    goes beneath.
    """
    if not bars:
        return None
    reaches = [_toward(c, direction) for c in bars]
    return min(reaches) if direction == Direction.BULLISH else max(reaches)


def _reaches(price: float, level_price: float, direction: Direction) -> bool:
    """Has `price` got to `level_price` from the trading side?"""
    return (price >= level_price if direction == Direction.BEARISH
            else price <= level_price)


class InducementWatch:
    """4th man's third form: the near-miss candle becomes the liquidity.

    video-14 t=679-702:

        "After price engulfs, the next one hour or 30 minutes candle is
         going to trade very close to the V shape or the A shape key
         level. BUT IT'S NOT GOING TO TAP INTO IT, which means that this
         next candle is going to serve as our INTERNAL RANGE LIQUIDITY.
         So we want to see price attack that liquidity, play out from
         this particular key level and price will continue to move to the
         downside."

    "Very close" is a distance and the course gives no number for it, so
    it is not the condition. "NOT GOING TO TAP INTO IT" is, and that is a
    comparison against the level rather than a threshold. The cost is
    that a candle stopping far short also qualifies; the alternative was
    inventing a proximity, which is not on offer.

    The entry is the KEY LEVEL -- "play out from this particular key
    level" -- and so the order is placed only once a candle has reached
    the level after the liquidity went, because that candle's far side is
    the first structure beyond the entry and therefore the only stop
    available without a pad.
    """

    def __init__(self):
        self._level: KeyLevel | None = None
        self._armed_at: object = None     # the engulf's bar time
        self._inducement: float | None = None
        self._taken = False

    def reset(self, level: KeyLevel | None):
        self._level = level
        self._armed_at = None
        self._inducement = None
        self._taken = False

    def engulfed(self, bar: Candle):
        """Tell it an engulf closed on this bar. The NEXT candle is the
        candidate, so nothing is decided here.

        It deliberately does NOT clear a sequence already in progress.
        Engulfs are frequent -- 46 of them inside 314 watched bars on one
        fixture -- so clearing here meant every pending inducement was
        wiped before it could complete: 9 candidates, 0 entries. That is
        the same self-erasing shape as the old sweep_break, which fired
        once in 2,063 trades because the rally that proved it deleted it.
        A newer candidate REPLACES the older one in `push` instead, which
        is "newest wins" without destroying a live sequence to get there.
        """
        self._armed_at = bar.time

    def push(self, bar: Candle, direction: Direction,
             level: KeyLevel) -> Confirmation | None:
        """One closed candle of the entry timeframe."""
        if level is None:
            self.reset(None)
            return None
        if self._level is None or level.price != self._level.price:
            self.reset(level)          # a new setup is a new story
            return None

        # The candidate is the one candle after the engulf, and only it.
        # A newer engulf's candidate replaces whatever was pending.
        if self._armed_at is not None and bar.time > self._armed_at:
            reach = _toward(bar, direction)
            self._armed_at = None
            if _reaches(reach, level.price, direction):
                return None               # it tapped the level: not inducement
            self._inducement = reach
            self._taken = False
            return None

        if self._inducement is None:
            return None

        if not self._taken:
            if _reaches(_toward(bar, direction), self._inducement, direction):
                self._taken = True
            else:
                return None

        # Taken. Now the level has to be played.
        if not _reaches(_toward(bar, direction), level.price, direction):
            return None
        stop = bar.high if direction == Direction.BEARISH else bar.low
        self._inducement = None
        self._taken = False
        return Confirmation("inducement", level.price, stop, bar.time)


class ReactionWatch:
    """Bishop's two best forms: the reaction breaks its own structure.

    part5 t=376-409, bullish case, the two drawn side by side so they can
    be compared:

        "the first thing you would be looking for is you want price to
         give you a BREAKOUT from this level ... Another thing you would
         want to see is something like this, whereby price gives you what
         a SWEEP OF LIQUIDITY AND A BREAK OF STRUCTURE"

    What differs is one leg. Both have price react at the key level, lift
    leaving a minor swing, and then close through that swing. The sweep
    version first comes back down and takes out its own earlier low. The
    frames the spec measured put the first low at ~1.86660 and the second
    at ~1.86570, which is the leg, and the break that follows is the same
    break in both.

    So this is one detector with a flag, not two detectors. The flag is
    reported rather than filtered on, because "which ones are likely
    best" is his judgement and the point of building it is to check it.

    The broken swing then behaves the way every disrespected level in
    this course behaves -- bias-1 t=195-300, "that's when we now use it
    for a buy" -- so the entry is the return to it. That also makes this
    the first place the polarity flip is actually TRADED rather than only
    honoured as an ending.

    WHY THE REACTION'S BARS ARE KEPT

    A swing is only confirmed n bars after it formed, so at the moment
    the minor swing appears, the sweep leg may ALREADY have happened --
    in the gap between the swing forming and confirming. A running
    "lowest low so far" therefore cannot tell the first low from the
    sweep of it: it just keeps getting lower, and 5.5 degenerates into
    5.4. The bars since the reaction started are kept so that, once the
    swing confirms, the first extreme can be read from before its time
    and the sweep from after it.

    That is a fact about the past arriving late, not a look-ahead. The
    BREAK is still only acted on from confirmation onward, because a
    swing cannot be traded before it exists.
    """

    def __init__(self, n: int):
        self.n = n
        self._level: KeyLevel | None = None
        self._swings = LevelStream(n)
        self._bars: list[Candle] = []           # the reaction so far
        self._first: float | None = None        # its first extreme
        self._minor: KeyLevel | None = None     # the swing to be broken
        self._swept = False

    def reset(self, level: KeyLevel | None):
        self._level = level
        self._swings = LevelStream(self.n)
        self._bars = []
        self._first = None
        self._minor = None
        self._swept = False

    def push(self, bar: Candle, direction: Direction,
             level: KeyLevel) -> Confirmation | None:
        """One closed candle of the entry timeframe.

        A new setup level restarts the watch: the reaction being measured
        is the reaction at THAT level, and carrying swings across from a
        different one would break structure against the wrong reference.
        """
        if level is None:
            self.reset(None)
            return None
        if self._level is None or level.price != self._level.price:
            self.reset(level)

        self._bars.append(bar)
        found = self._swings.push(bar)

        # The minor swing the break is measured against: the one pointing
        # AGAINST the trade, because that is what a breakout in the
        # trade's direction goes through. Newest wins if several confirm.
        wanted = "A" if direction == Direction.BULLISH else "V"
        for lvl in found:
            if lvl.shape != wanted:
                continue
            self._minor = lvl
            before = [c for c in self._bars if c.time < lvl.time]
            after = [c for c in self._bars if c.time > lvl.time]
            self._first = _extreme(before, direction)
            self._swept = self._first is not None and any(
                _reaches(_toward(c, direction), self._first, direction)
                and _toward(c, direction) != self._first for c in after)

        if self._minor is None:
            return None

        # The sweep leg may also arrive after the swing confirmed.
        if self._first is not None and not self._swept:
            reach = _toward(bar, direction)
            if bar.time > self._minor.time and \
                    _reaches(reach, self._first, direction) and \
                    reach != self._first:
                self._swept = True

        through = (bar.close > self._minor.price if direction == Direction.BULLISH
                   else bar.close < self._minor.price)
        if not through:
            return None

        stop = bar.low if direction == Direction.BULLISH else bar.high
        form = "sweep_break" if self._swept else "breakout"
        entry = self._minor.price
        self._minor = None
        self._swept = False
        self._first = None
        # That reaction is over. Keeping its bars would let the NEXT
        # swing's first extreme be read from long before it, which pushes
        # `_first` so far out that nothing ever sweeps it -- 5.5 would
        # then quietly never fire again at this level.
        self._bars = [c for c in self._bars if c.time > bar.time]
        return Confirmation(form, entry, stop, bar.time)
