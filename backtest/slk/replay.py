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

    bias        a Daily key level rejected and closed through, then H4
                breaking structure the same way (bias.py)
    setup       on H4: internal range liquidity taken, the NEAREST key
                level to it, and a rejection from that level (sweep.py)
    entry       on H1: two same-direction candles leave an open-close
                level, a later candle CLOSES THROUGH it, and price
                RETURNS to it (confirmation.py)
    stop        the engulfing candle's own far side
    target      the nearest untaken external liquidity (liquidity.py)

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
from .stream import LevelStream
from .sweep import Setup, SetupStream, level_identity


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
           h1: list[Candle], n: int) -> list[Trade]:
    """Walk H1 forward and return the trades that would have been taken.

    `n` is the swing width, and it has no default anywhere in this
    package because the course never gives one -- see stream.py.
    """
    if not h1 or not h4 or not daily:
        return []

    d_len, h4_len, h1_len = bar_length(daily), bar_length(h4), bar_length(h1)
    d_close = [closes_at(c.time, d_len) for c in daily]
    h4_close = [closes_at(c.time, h4_len) for c in h4]
    w_close = [closes_at(c.time, bar_length(weekly)) for c in weekly] if weekly else []

    daily_levels = LevelStream(n)
    h4_levels = LevelStream(n)
    setups = SetupStream()
    live: dict[object, Setup] = {}
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
        while di < len(daily) and d_close[di] <= now:
            daily_levels.push(daily[di])
            seen_daily.append(daily[di])
            di += 1
        while wi < len(weekly) and w_close[wi] <= now:
            seen_weekly.append(weekly[wi])
            wi += 1
        while h4i < len(h4) and h4_close[h4i] <= now:
            h4_levels.push(h4[h4i])
            # Bias: the most recent daily level price has rejected, with
            # H4 then breaking the same way. Recomputed only when a new
            # H4 candle closes, which is when it can change.
            was, bias = bias, _bias_now(daily_levels, seen_daily,
                                        h4[:h4i + 1], n) or bias
            if bias != was and was is not None:
                # "I had to go and cancel my limit order ... because [I]
                # was analyzing this from the three hours, it was
                # selling" -- video-03 t=1892-1914. The analysis went, so
                # everything it justified goes with it.
                live.clear()
                book.cancel_all("bias flipped")

            # The setup, in the three steps the course gives: internal
            # range liquidity taken, the NEAREST key level to it, and a
            # rejection from that level (sweep.py).
            for s in setups.push(h4[h4i], bias, h4_levels.standing()):
                live[level_identity(s.level)] = s
            for key, s in list(live.items()):
                if disrespected_by(h4[h4i], s.level):
                    del live[key]
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
            t = Trade(entry_time=bar.time, entry=fill.order.entry,
                      stop=fill.order.stop, target=fill.order.target,
                      direction=fill.order.direction,
                      level_price=fill.order.entry,
                      setup_price=fill.order.level_key[1],
                      liquidity=fill.order.liquidity,
                      same_candle_stop=fill.same_candle_stop)
            if fill.same_candle_stop:
                _close(t, bar, t.stop, "stop")
                done.append(t)
            else:
                open_trades.append(t)

        # --- new confirmations ---------------------------------------
        if prev_h1 is not None:
            formed = open_close_level(prev_h1, bar)
            if formed is not None:
                engulfs_pending.add(formed)

        for level in engulfs_pending.consume(bar.close):
            if bias is None or level.direction != bias:
                continue
            setup = _live_setup(bar, live, bias)
            if setup is None:
                continue
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
                liquidity=setup.sweep.point.price))

        prev_h1 = bar

    return done


def _bias_now(daily_levels: LevelStream, seen_daily: list[Candle],
              seen_h4: list[Candle], n: int) -> Direction | None:
    """The newest daily level that has established a bias, or None."""
    from .bias import bias_established

    for level in reversed(daily_levels.standing()):
        got = bias_established(seen_daily, seen_h4, level, n)
        if got is not None:
            return got
    return None


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
