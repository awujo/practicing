"""
The driver. One candle at a time, forward only.

Operator, 2026-09-25: "when we do backtesting manually we have a cutter
that cuts out from when we want to start backtesting and we play as we
go and not seeing into the future."

That is this. There is no series-wide precomputation anywhere in here.
Each H1 candle closes, the engine is told, and it answers with what it
would have done -- which is the same thing the live bot has to do, and
the reason a backtest that is honest is also a backtest that is fast.

WHAT A HIGHER TIMEFRAME LOOKS LIKE FROM HERE

A Daily or H4 candle is handed over only once it has CLOSED. Until
then it does not exist. This matters more than it sounds: a cached
Daily bar carries the day's FINAL high and low, so admitting it while
the day is still running hands the engine the rest of the session. That
is the single easiest way to read tomorrow by accident, and it is why
the higher series are fed by close time rather than sliced by index.

THE CASCADE, IN THE ORDER THE COURSE GIVES IT

    bias        either route: a Daily key level rejected with H4 then
                breaking the same way (bias.py), or a previous Weekly
                extreme swept with the other side standing and the Daily
                then breaking the same way (sweep.LiquidityBias). The
                Daily route wins a disagreement.
    setup       on H4: internal range liquidity taken, the NEAREST key
                level to it, and a rejection from that level (sweep.py)
    entry       on H1, any of four forms: the open-close engulf
                (confirmation.py), or inducement, breakout and
                sweep-and-break (entries.py). One order at a time per
                setup, newest confirmation winning.
    stop        the far side of the candle that confirmed -- "in the wick
                of the confirming candle", SLK_SPEC 6
    target      the nearest untaken external liquidity (liquidity.py)

A setup stays watched from the bar price reaches it until it fills, its
key level is closed through, or price reaches the external liquidity
that was its whole premise. That last one is what gives a setup a
lifetime without a candle count, and the course supplies it: after
external liquidity is taken, expect a reversal.

WHAT IS NOT MODELLED, AND IS NOT PRETENDED AWAY

Spread and slippage are absent here; every loss is exactly the distance
to the stop. The reporting layer charges spread per trade against each
trade's own risk, which is the only honest way to do it, but it is
still an assumption applied afterwards rather than a fill simulation.
"""

from __future__ import annotations

import bisect
from dataclasses import dataclass

from ..engine.candles import Candle
from ..engine.structure import Direction
from ..engine.timeframes import bar_length, closes_at
from .confirmation import OpenCloseLevel, open_close_level, stop_for
from .levels import disrespected_by, returned_to
from .liquidity import target_for
from .orders import OrderBook, PendingOrder
from .entries import InducementWatch, ReactionWatch
from .stream import LevelStream
from .cascade import Cascade
from .sweep import Setup, SetupStream, level_identity


def _tell(observer, event: str, **fields):
    """Best-effort notification. Never lets a watcher break the engine."""
    if observer is None:
        return
    handler = getattr(observer, "on_" + event, None)
    if handler is None:
        return
    try:
        handler(**fields)
    except Exception:                                  # noqa: BLE001
        import logging
        logging.getLogger("backtest.slk.replay").exception(
            "observer.on_%s raised; the replay carries on", event)


@dataclass
class Trade:
    entry_time: object
    entry: float
    stop: float
    target: float
    direction: Direction
    level_price: float
    setup_price: float = None      # the H4 key level being played
    liquidity: float = None        # the liquidity taken that entitled it
    form: str = None               # which confirmation let it in
    mitigation: float = None       # the shallow depth, for measurement
    exit_time: object = None
    exit: float = None
    outcome: str = "open"          # "target" | "stop" | "open"
    r: float = None
    same_candle_stop: bool = False


class _EngulfBook:
    """Open-close levels waiting to be closed through.

    Kept sorted by price so a candle's close can consume exactly the
    levels it passed, by bisect, instead of rescanning every level ever
    formed. Each level is consumed once, so the whole run costs O(levels)
    rather than O(bars x levels) -- the same reason the old engine
    crawled.
    """

    def __init__(self):
        self._sell: list[tuple[float, OpenCloseLevel]] = []   # engulfed by a close BELOW
        self._buy: list[tuple[float, OpenCloseLevel]] = []    # engulfed by a close ABOVE

    def add(self, level: OpenCloseLevel):
        target = self._sell if level.direction == Direction.BEARISH else self._buy
        bisect.insort(target, (level.price, level), key=lambda p: p[0])

    def consume(self, close: float) -> list[OpenCloseLevel]:
        """Every level this close engulfs, removed from the book."""
        out = []

        cut = bisect.bisect_right(self._sell, close, key=lambda p: p[0])
        out.extend(lvl for _, lvl in self._sell[cut:])
        del self._sell[cut:]

        cut = bisect.bisect_left(self._buy, close, key=lambda p: p[0])
        out.extend(lvl for _, lvl in self._buy[:cut])
        del self._buy[:cut]
        return out


def replay(weekly: list[Candle], daily: list[Candle], h4: list[Candle],
           h1: list[Candle], n: int, observer=None) -> list[Trade]:
    """Walk H1 forward and return the trades that would have been taken.

    `n` is the swing width, and it has no default anywhere in this
    package because the course never gives one -- see stream.py.

    `observer`, if given, is told about bias changes, setups going live
    and confirmations as they happen. It is how the LIVE side watches
    without there being a second copy of this loop: the live runner calls
    THIS function, on trimmed history, once per H1 close, and reports the
    events past its own watermark. A separate live implementation would
    be a second machine that could disagree with the backtest, and this
    project has paid for that twice already.

    Every observer call is wrapped: a notifier that can take down the
    engine is worse than no notifier.
    """
    if not h1 or not h4 or not daily:
        return []

    d_len, h4_len, h1_len = bar_length(daily), bar_length(h4), bar_length(h1)
    d_close = [closes_at(c.time, d_len) for c in daily]
    h4_close = [closes_at(c.time, h4_len) for c in h4]
    w_close = [closes_at(c.time, bar_length(weekly)) for c in weekly] if weekly else []

    h4_levels = LevelStream(n)
    cascade = Cascade(n)
    setups = SetupStream()
    live: dict[object, Setup] = {}
    live_erl: dict[object, float] = {}
    reaction = ReactionWatch(n)
    inducement = InducementWatch()
    watching: Setup | None = None
    engulfs_pending = _EngulfBook()
    book = OrderBook()

    di = h4i = wi = 0
    seen_daily: list[Candle] = []
    seen_weekly: list[Candle] = []
    bias: Direction | None = None
    open_trades: list[Trade] = []
    done: list[Trade] = []
    prev_h1: Candle | None = None

    for bar in h1:
        now = closes_at(bar.time, h1_len)

        # --- higher timeframes, but only what has CLOSED -------------
        while wi < len(weekly) and w_close[wi] <= now:
            cascade.push_weekly(weekly[wi], w_close[wi])
            seen_weekly.append(weekly[wi])
            wi += 1
        while di < len(daily) and d_close[di] <= now:
            cascade.push_daily(daily[di], d_close[di])
            seen_daily.append(daily[di])
            di += 1
        while h4i < len(h4) and h4_close[h4i] <= now:
            h4_levels.push(h4[h4i])
            cascade.push_h4(h4[h4i])
            # Bias, by every route the course gives on every rung it gives
            # them -- key levels or liquidity, Weekly->Daily or
            # Daily->H4, with the lower rung winning a disagreement
            # ("I can leave the weekly, I use my daily at my four hours").
            # See cascade.py; it answers in constant time.
            was = bias
            bias = cascade.direction() or bias
            if bias != was:
                _tell(observer, "bias", at=h4[h4i].time, direction=bias,
                      cascade=cascade, was=was)
            if bias != was and was is not None:
                # "I had to go and cancel my limit order ... because [I]
                # was analyzing this from the three hours, it was
                # selling" -- video-03 t=1892-1914. The analysis went, so
                # everything it justified goes with it.
                live.clear()
                live_erl.clear()
                book.cancel_all("bias flipped")

            # The setup, in the three steps the course gives: internal
            # range liquidity taken, the NEAREST key level to it, and a
            # rejection from that level (sweep.py).
            for s in setups.push(h4[h4i], bias, h4_levels.confirmed()):
                key = level_identity(s.level)
                live[key] = s
                # The setup's own premise: from this level, price expands
                # to the next external liquidity. Recorded now so that
                # reaching it later can END the setup -- "after external
                # liquidity is taken, expect a reversal" (bd2 t=615-645).
                erl = target_for(s.level.price, bias, seen_daily, seen_weekly)
                if erl is not None:
                    live_erl[key] = erl
                _tell(observer, "setup", at=h4[h4i].time, setup=s,
                      direction=bias, target=erl)
            for key, s in list(live.items()):
                if disrespected_by(h4[h4i], s.level):
                    del live[key]
                    live_erl.pop(key, None)
                    book.cancel(key, "level disrespected")
            h4i += 1

        # --- exits first: a bar can close a position and open none ---
        still_open = []
        for t in open_trades:
            outcome = _resolve(bar, t)
            if outcome is None:
                still_open.append(t)
            else:
                done.append(t)
        open_trades = still_open

        # --- fills: orders resting at their level --------------------
        for fill in book.fills(bar):
            # The setup is spent. "It's about using it when the first
            # time it presented itself" -- operator, 2026-09-22.
            live.pop(fill.order.level_key, None)
            live_erl.pop(fill.order.level_key, None)
            t = Trade(entry_time=bar.time, entry=fill.order.entry,
                      stop=fill.order.stop, target=fill.order.target,
                      direction=fill.order.direction,
                      level_price=fill.order.entry,
                      setup_price=fill.order.level_key[1],
                      liquidity=fill.order.liquidity,
                      form=fill.order.confirmation,
                      mitigation=fill.order.mitigation,
                      same_candle_stop=fill.same_candle_stop)
            if fill.same_candle_stop:
                _close(t, bar, t.stop, "stop")
                done.append(t)
            else:
                open_trades.append(t)

        # --- setups that ran without us ------------------------------
        # The premise was an expansion to the next external liquidity. If
        # price gets there and we never entered, the move happened and
        # there is nothing left to trade -- and this is what gives a
        # setup a lifetime without inventing a candle count for one.
        for key, s in list(live.items()):
            erl = live_erl.get(key)
            if erl is None:
                continue
            got_there = (bar.high >= erl if s.level.bias == Direction.BULLISH
                         else bar.low <= erl)
            if got_there:
                del live[key]
                del live_erl[key]
                book.cancel(key, "external liquidity taken without us")

        # --- which setup is being watched ----------------------------
        # The reaction that produces a confirmation happens NEAR the key
        # level, not on it -- "you're NOT setting your limit directly at
        # the four-hour key level. You're expecting price to trade into
        # your key level of interest, and then start giving you a
        # reaction from that key level" (part5 t=303-315). So the setup
        # stays watched from the bar price reaches it until it is filled,
        # disrespected, or overtaken by the expansion above.
        touched = _live_setup(bar, live, bias) if bias is not None else None
        if touched is not None:
            watching = touched
        if watching is not None and level_identity(watching.level) not in live:
            watching = None
        watched = watching.level if watching is not None else None

        # --- new confirmations ---------------------------------------
        if prev_h1 is not None:
            formed = open_close_level(prev_h1, bar)
            if formed is not None:
                engulfs_pending.add(formed)

        engulfed_here = False
        for level in engulfs_pending.consume(bar.close):
            if bias is None or level.direction != bias:
                continue
            setup = watching
            if setup is None:
                continue
            engulfed_here = True
            target = target_for(level.price, bias, seen_daily, seen_weekly)
            if target is None:
                continue
            stop = stop_for(bar, level)
            if not _stop_beyond(level.price, stop, bias):
                continue
            book.place(PendingOrder(
                # Keyed on the SETUP, not on the confirmation. One H4
                # level holds one order; a later engulf inside the same
                # reaction replaces it -- operator, 2026-09-25,
                # "newest confirmation wins, one order at a time per
                # level".
                level_key=level_identity(setup.level),
                entry=level.price, stop=stop, target=target,
                direction=bias, placed_at=bar.time, confirmation="engulf",
                liquidity=setup.sweep.point.price,
                # The shallow mitigation depth: the line-chart peak the
                # engulf leaves is the second candle's own close, and
                # 4th man's 5.1 is a return to THAT rather than to the
                # open. Recorded, not traded -- entries.py says why.
                mitigation=level.second_close))
            _tell(observer, "confirmation", at=bar.time, form="engulf",
                  direction=bias, entry=level.price, stop=stop, target=target,
                  setup=setup)

        # --- Bishop's two best forms, and 4th man's third -------------
        for got in (reaction.push(bar, bias, watched),
                    inducement.push(bar, bias, watched)):
            if got is None:
                continue
            target = target_for(got.entry, bias, seen_daily, seen_weekly)
            if target is None:
                continue
            if not _stop_beyond(got.entry, got.stop, bias):
                continue
            book.place(PendingOrder(
                level_key=level_identity(watching.level),
                entry=got.entry, stop=got.stop, target=target,
                direction=bias, placed_at=bar.time, confirmation=got.form,
                liquidity=watching.sweep.point.price))
            _tell(observer, "confirmation", at=bar.time, form=got.form,
                  direction=bias, entry=got.entry, stop=got.stop,
                  target=target, setup=watching)

        if engulfed_here:
            # The candidate inducement is the candle AFTER the engulf, so
            # this is told last and decides nothing now.
            inducement.engulfed(bar)

        prev_h1 = bar

    return done


def _live_setup(bar: Candle, live: dict[object, Setup],
                direction: Direction) -> Setup | None:
    """WHICH live setup this H1 bar is entitled to trade, or None.

    Two conditions, and the first is the one the old engine never had:
    the level must be a LIVE SETUP -- liquidity taken, and this the
    nearest key level to it, already rejected on H4 (sweep.py). Price
    merely reaching a level is not a setup, and t=465-481 is Bishop
    saying so in as many words.

    The second is that this bar has reached the level. The course puts
    the entry at the key level -- "eventually you want to see price come
    into your K level and boom, you buy" (repeating-system t=354-360) --
    and requiring the engulfing bar to be AT the level is how that is
    said without a distance threshold. It also gives the setup a
    structural lifetime: while price is away from the level there is
    nothing to enter, so no number is needed to expire it.

    Returns the setup rather than a yes/no because the level IS the
    setup, and the H1 engulf is only permission to enter it. Keying
    orders on the H1 open-close level instead produced three trades on
    one bar at entries three pips apart.

    Newest first: the level just reached is the one being traded.
    """
    for setup in reversed(list(live.values())):
        if setup.level.bias != direction:
            continue
        if returned_to(bar, setup.level):
            return setup
    return None


def _stop_beyond(entry: float, stop: float, direction: Direction) -> bool:
    return stop < entry if direction == Direction.BULLISH else stop > entry


def _resolve(bar: Candle, t: Trade) -> str | None:
    """Stop or target on this bar, stop winning a same-bar tie.

    We cannot see inside a candle, so when both are reached the
    assumption has to be the one that cannot be accused of tidying the
    result.
    """
    if t.direction == Direction.BULLISH:
        if bar.low <= t.stop:
            return _close(t, bar, t.stop, "stop")
        if bar.high >= t.target:
            return _close(t, bar, t.target, "target")
    else:
        if bar.high >= t.stop:
            return _close(t, bar, t.stop, "stop")
        if bar.low <= t.target:
            return _close(t, bar, t.target, "target")
    return None


def _close(t: Trade, bar: Candle, price: float, outcome: str) -> str:
    risk = abs(t.entry - t.stop) or 1e-9
    gain = (price - t.entry) if t.direction == Direction.BULLISH else (t.entry - price)
    t.exit_time, t.exit, t.outcome, t.r = bar.time, price, outcome, gain / risk
    return outcome
