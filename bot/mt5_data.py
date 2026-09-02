"""
MT5 -> Candle adapter -- the live data source, replacing Dukascopy for
everything except backtesting itself (see the module's discussion in
webapp/data_access.py and bot/config.py for why: live decisions have to be
made against the exact price stream you'll execute against).

candles.py's own docstring anticipated this split: "the exact same code
path can later replay live, just-closed MT5 bars one by one instead of an
in-memory backtest array" -- bias.py / structure.py / key_levels.py /
liquidity.py / trade_management.py are untouched by anything in this
file. This module's only job is turning MT5's bars into the same Candle
objects those modules already consume, and telling the orchestrator when
a new one has actually closed.

Genuinely UNTESTED against a live terminal -- there is no MT5 connection
reachable from the sandbox this was written in. The `mt5` module is
dependency-injected (never imported at module scope) specifically so the
conversion/detection logic below can be unit tested against a fake that
mimics the real package's documented return shapes; the actual
MetaTrader5 package's connection behavior, symbol quirks, and broker-
specific edge cases are NOT verified and need real testing against your
demo account before anything else in bot/ is trusted.

run_backtest() only ever loads D, H4, H1 (required) and W (optional) --
no Monthly, despite STRATEGY.md discussing it -- so that's the exact set
fetched here too, to keep live and backtest behaviorally identical.
"""

import logging
from dataclasses import dataclass

import pandas as pd

from backtest.engine.candles import Candle
from .config import SymbolMap
from .risk_manager import AccountState, OpenPosition

logger = logging.getLogger("bot.mt5_data")

GRANULARITIES = ("D", "H4", "H1", "W")

# MT5's TIMEFRAME_* constants are plain ints in the real package; naming
# them out here (rather than reaching into the injected module for each
# lookup) keeps this file readable and gives tests a plain dict to fake.
_TIMEFRAME_ATTR = {
    "W": "TIMEFRAME_W1",
    "D": "TIMEFRAME_D1",
    "H4": "TIMEFRAME_H4",
    "H1": "TIMEFRAME_H1",
}


class MT5ConnectionError(RuntimeError):
    pass


# Bounds a detected server UTC offset must fall within to be trusted --
# see _detect_server_utc_offset()'s docstring for why this exists. Real
# broker server clocks seen in practice sit within a couple hours of UTC
# (this one's confirmed +3, EEST); +/-6h leaves generous room for any
# broker actually encountered while still rejecting the wildly-wrong
# values a stale (market-closed) candle produces -- confirmed live
# 2026-08-30, a weekend-closed XAUUSD read produced an offset far
# outside any real timezone.
_PLAUSIBLE_OFFSET_HOURS = 6

# fetch_candles() only ever asks MT5 for CLOSED bars (start=1 explicitly
# skips the still-forming one) -- a genuinely closed candle can never be
# timestamped after "now", full stop. Confirmed live 2026-08-30: the
# weekend-offset bug fixed above (before this specific guard existed)
# had already written candles ~42h into the future into the on-disk
# cache for 20 of 25 instruments before the offset-detection fix landed
# -- silently corrupting new_candle_closed()'s "is this fresh" check
# from then on, since nothing ever compares as newer than a fake future
# timestamp. This is deliberately a SEPARATE check from the offset
# plausibility bound above: that one guards against adopting a bad
# OFFSET before it's applied; this one guards the RESULT regardless of
# which bug produced it, so a future path that corrupts timestamps a
# different way still can't get a future-dated candle into the cache.
# A few minutes of slack for ordinary clock skew between this host and
# the broker's server, not for anything larger.
_MAX_FUTURE_CANDLE_SLACK = pd.Timedelta(minutes=5)


@dataclass(frozen=True)
class ClosedDeal:
    ticket: int
    price: float
    reason: str  # "stop_hit" | "target_hit" | "manual_or_other"
    profit: float


@dataclass
class RawPosition:
    """What we need out of MT5's positions_get() rows -- deliberately not
    the raw MT5 struct, so callers/tests don't depend on its exact shape."""
    ticket: int
    symbol: str
    risk_amount: float  # |price_open - sl| * volume * (contract-adjusted) $/point, precomputed by the caller


class MT5Client:
    """Thin wrapper around the injected `mt5` module. Every call that
    touches the network can fail -- callers (the orchestrator) are
    responsible for catching MT5ConnectionError and going fail-closed
    (stop opening new trades) rather than assuming a retry will succeed."""

    def __init__(self, mt5_module, login: int, password: str, server: str, symbol_suffix: str = "",
                 symbol_overrides: dict[str, str] | None = None, terminal_path: str | None = None,
                 server_utc_offset: "pd.Timedelta | None" = None):
        self._mt5 = mt5_module
        self._login = login
        self._password = password
        self._server = server
        self._symbol_map = SymbolMap(suffix=symbol_suffix, overrides=symbol_overrides or {})
        # Which terminal.exe to target -- required when more than one MT5
        # install shares a single Wine prefix/mt5linux bridge (e.g. two
        # portable accounts on the same VPS): mt5.initialize() with no path
        # falls back to whatever terminal MT5 finds via its default
        # lookup, which silently connects to the WRONG account's terminal
        # rather than failing loudly. None keeps the old single-terminal
        # behavior (native Windows, or a VPS running only one account).
        self._terminal_path = terminal_path
        self._connected = False
        # last CLOSED candle time seen per (internal_symbol, granularity) --
        # used to detect "a new candle just closed" without re-processing
        # the same bar twice.
        self._last_closed_time: dict[tuple[str, str], pd.Timestamp] = {}
        # MT5's copy_rates_from_pos() reports candle times in the broker's
        # OWN server clock (e.g. EET/EEST), not true UTC, despite the raw
        # value looking like a plain Unix timestamp -- confirmed live:
        # MetaQuotes-Demo runs ~3 hours ahead of real UTC, and every
        # live-synced candle was silently getting that server time
        # relabeled "UTC", splicing onto Dukascopy's genuinely-UTC
        # historical data with the wrong period boundaries. None (the
        # default) auto-detects it on the first fetch_candles() call and
        # re-detects after every reconnect (a reconnect could land on a
        # different server, or span a DST transition); pass an explicit
        # value to pin it instead -- also how tests keep candle-conversion
        # fixtures independent of this detection call.
        self._server_utc_offset = server_utc_offset
        self._offset_pinned = server_utc_offset is not None

    def broker_symbol(self, internal_symbol: str) -> str:
        return self._symbol_map.broker_symbol(internal_symbol)

    def connect(self) -> None:
        initialized = self._mt5.initialize(path=self._terminal_path) if self._terminal_path \
            else self._mt5.initialize()
        if not initialized:
            raise MT5ConnectionError(f"mt5.initialize() failed: {self._mt5.last_error()}")
        if not self._mt5.login(self._login, password=self._password, server=self._server):
            raise MT5ConnectionError(f"mt5.login() failed for login {self._login}@{self._server}: "
                                      f"{self._mt5.last_error()}")
        self._connected = True
        # Re-detect on every (re)connect rather than trusting a stale
        # cached value -- a reconnect could land on a different server, or
        # span a DST transition on the same one. An explicitly pinned
        # offset (constructor arg) is left alone -- the caller asked for
        # that exact value regardless of reconnects.
        if not self._offset_pinned:
            self._server_utc_offset = None

    def disconnect(self) -> None:
        self._mt5.shutdown()
        self._connected = False

    def is_healthy(self) -> bool:
        if not self._connected:
            return False
        info = self._mt5.terminal_info()
        return info is not None and getattr(info, "connected", False)

    def _detect_server_utc_offset(self, symbol: str, real_now: pd.Timestamp | None = None) -> pd.Timedelta:
        """Compares the currently-forming M1 candle's reported open time
        (always exactly on the minute) against Python's own real UTC
        clock, rounded to the nearest hour since every broker offset seen
        in practice is a whole number of hours. `real_now` is only ever
        overridden by tests, for a deterministic comparison point.

        This assumes `rates[0]` (index 0 of copy_rates_from_pos) is
        GENUINELY forming right now -- true only while the market is
        actually open. Confirmed live 2026-08-30: called during a weekend
        closure, `rates[0]` is really the LAST bar before Friday's close,
        many hours stale, and the raw comparison against real UTC "now"
        produces a wildly wrong delta -- which then got silently cached
        and applied (as a fixed subtraction) to every candle timestamp
        fetched until the next reconnect, corrupting them all. There's no
        direct "give me the broker's wall-clock time" MT5 call this
        client has found a use for elsewhere, so instead of detecting
        market-closed directly, the RESULT is sanity-checked: a real
        broker offset is always within _PLAUSIBLE_OFFSET_HOURS of UTC
        (this one's confirmed +3); a stale weekend read produces
        something far outside that. Raises rather than returning garbage
        -- fits this client's existing fail-closed pattern exactly
        (fetch_candles/sync_recent_from_mt5 already catch
        MT5ConnectionError and skip that cycle), and is also simply
        correct: there's nothing to trade while the market is shut, so
        failing to fetch until a genuinely fresh candle exists again
        (the market reopens) is the right behavior, not a gap to paper
        over."""
        rates = self._mt5.copy_rates_from_pos(symbol, self._mt5.TIMEFRAME_M1, 0, 1)
        if not rates:
            raise MT5ConnectionError(f"copy_rates_from_pos({symbol}, M1) failed while detecting "
                                      f"server UTC offset: {self._mt5.last_error()}")
        broker_time = pd.Timestamp(rates[0]["time"], unit="s", tz="UTC")
        real_now = (real_now if real_now is not None else pd.Timestamp.now(tz="UTC")).floor("min")
        hours = round((broker_time - real_now).total_seconds() / 3600)
        if abs(hours) > _PLAUSIBLE_OFFSET_HOURS:
            raise MT5ConnectionError(
                f"detected server UTC offset of {hours}h for {symbol} is outside the plausible "
                f"+/-{_PLAUSIBLE_OFFSET_HOURS}h range -- the M1 candle used to detect it (broker "
                f"time {broker_time}) is likely stale rather than genuinely forming right now "
                f"(e.g. the market for {symbol} may be closed), so it doesn't represent \"now\" the "
                f"way this detection assumes. Not adopting a bad offset that would otherwise corrupt "
                f"every candle timestamp fetched until the next reconnect.")
        return pd.Timedelta(hours=hours)

    def fetch_candles(self, internal_symbol: str, granularity: str, count: int = 300) -> list[Candle]:
        """Returns the `count` most recent CLOSED candles, oldest first --
        MT5's copy_rates_from_pos(..., start=0, ...) includes the current,
        still-forming bar at index 0, which is deliberately dropped here
        (a strategy decision must never be made against an incomplete
        candle -- structure.py's swing/sweep logic assumes every candle
        it sees is finished)."""
        if granularity not in _TIMEFRAME_ATTR:
            raise ValueError(f"unsupported granularity {granularity!r}, expected one of {GRANULARITIES}")
        timeframe = getattr(self._mt5, _TIMEFRAME_ATTR[granularity])
        symbol = self.broker_symbol(internal_symbol)
        if self._server_utc_offset is None:
            self._server_utc_offset = self._detect_server_utc_offset(symbol)
        # start=1 skips the still-forming bar at index 0 directly, rather
        # than fetching count+1 and slicing -- one fewer thing to get
        # off-by-one wrong.
        rates = self._mt5.copy_rates_from_pos(symbol, timeframe, 1, count)
        if rates is None:
            raise MT5ConnectionError(f"copy_rates_from_pos({symbol}, {granularity}) failed: "
                                      f"{self._mt5.last_error()}")
        candles = [
            Candle(pd.Timestamp(r["time"], unit="s", tz="UTC") - self._server_utc_offset,
                   float(r["open"]), float(r["high"]),
                   float(r["low"]), float(r["close"]), float(r["tick_volume"]))
            for r in rates
        ]
        candles.sort(key=lambda c: c.time)
        # See _MAX_FUTURE_CANDLE_SLACK's comment -- a CLOSED candle can
        # never genuinely be timestamped after "now". Filtering rather
        # than raising: one bad bar in a batch of otherwise-good ones
        # shouldn't cost the rest, and the caller (sync_recent_from_mt5)
        # would otherwise persist it into the on-disk cache forever
        # (cache.append() dedupes by exact timestamp, so a bad row with
        # a unique bogus time is never naturally overwritten).
        cutoff = pd.Timestamp.now(tz="UTC") + _MAX_FUTURE_CANDLE_SLACK
        plausible = [c for c in candles if c.time <= cutoff]
        if len(plausible) != len(candles):
            dropped = [c for c in candles if c.time > cutoff]
            logger.warning(
                "dropped %d future-dated candle(s) for %s/%s that MT5 returned as CLOSED -- "
                "e.g. %s (now is %s); not caching or acting on data that can't be real",
                len(dropped), internal_symbol, granularity, dropped[0].time, pd.Timestamp.now(tz="UTC"))
        return plausible

    @staticmethod
    def _last_completed_open(granularity: str) -> "pd.Timestamp":
        """Open time of the most recent candle that MUST have finished by
        now, in UTC.

        Purely arithmetic on the clock -- no broker call. Candle times
        from `fetch_candles()` are already normalised to UTC (see
        `_detect_server_utc_offset`), so this compares like with like even
        though this terminal's own clock runs +3h.

        Weekly is floored to Monday, which is a deliberate
        under-estimate for a broker whose week opens Sunday evening: it
        can only ever cause an EXTRA fetch, never a missed candle, and
        that is the right way round for this check to be wrong.
        """
        now = pd.Timestamp.now(tz="UTC")
        if granularity == "H1":
            return now.floor("h") - pd.Timedelta(hours=1)
        if granularity == "H4":
            # H4 bars start at 00/04/08/12/16/20 UTC.
            return now.floor("4h") - pd.Timedelta(hours=4)
        if granularity == "D":
            return now.floor("D") - pd.Timedelta(days=1)
        if granularity == "W":
            monday = now.floor("D") - pd.Timedelta(days=now.weekday())
            return monday - pd.Timedelta(days=7)
        # Unknown granularity: never skip, so a new timeframe added later
        # fails safe (an extra fetch) rather than silently going blind.
        return pd.Timestamp.min.tz_localize("UTC")

    def new_candle_closed(self, internal_symbol: str, granularity: str) -> Candle | None:
        """Call this on a polling loop (fast enough to not miss a close,
        e.g. every few seconds) -- returns the newly-closed candle the
        FIRST time it's seen, then None on every subsequent call until
        another one closes. This is what should actually trigger a
        strategy re-evaluation, not a fixed timer -- see the module
        docstring on why live and backtest need to agree on this.

        Skips the broker round-trip entirely when the clock says nothing
        can have closed yet. This is the single biggest cost in the live
        loop: the orchestrator calls this per instrument per poll, so 25
        instruments on a 5-second loop is ~300 bridge calls a MINUTE, per
        bot, against an MT5 terminal running under Wine on two
        oversubscribed vCPUs. Measured effect of that queue: the bot was
        never once prompt -- zero entry attempts in its entire history
        landed within 5 minutes of a candle close (OPERATIONS_LOG
        2026-09-02), which in turn caused 41 of its 42 failed attempts.

        Almost all of those calls could not have found anything. An H1
        candle only closes on the hour, so between :00 and :59 there is
        nothing to fetch. Comparing the last candle we were given against
        the bar that must have completed by now answers that from the
        clock, for free, and only reaches the broker when the answer
        might actually have changed -- roughly a 700x reduction in bridge
        traffic at H1.

        Behaviour is unchanged: every skipped call is one that would have
        returned None anyway. If the broker's bar is late, the next poll
        five seconds later still asks.
        """
        key_check = (internal_symbol, granularity)
        seen = self._last_closed_time.get(key_check)
        if seen is not None and seen >= self._last_completed_open(granularity):
            return None

        candles = self.fetch_candles(internal_symbol, granularity, count=2)
        if not candles:
            return None
        latest = candles[-1]
        key = (internal_symbol, granularity)
        if self._last_closed_time.get(key) == latest.time:
            return None
        self._last_closed_time[key] = latest.time
        return latest

    def account_state(self, day_start_balance: float, phase_start_balance: float) -> AccountState:
        info = self._mt5.account_info()
        if info is None:
            raise MT5ConnectionError(f"mt5.account_info() failed: {self._mt5.last_error()}")
        positions = self._mt5.positions_get()
        if positions is None:
            positions = ()
        open_positions = tuple(
            OpenPosition(ticket=p.ticket, instrument=p.symbol,
                         risk_amount=self._position_risk(p))
            for p in positions
        )
        return AccountState(
            balance=float(info.balance), equity=float(info.equity),
            day_start_balance=day_start_balance, phase_start_balance=phase_start_balance,
            open_positions=open_positions,
        )

    def fetch_closed_deal(self, ticket: int) -> ClosedDeal | None:
        """The least-verified method in this module -- history_deals_get's
        exact return shape/behavior (does `position=` filter the way the
        docs suggest, is there always exactly one DEAL_ENTRY_OUT deal per
        closed position, how do partial closes show up) needs confirming
        against a real account. Returns None (not a raised error) when
        nothing is found, since "this position hasn't shown up in history
        yet" is an expected, retry-worthy state, not a connection failure."""
        deals = self._mt5.history_deals_get(position=ticket)
        if not deals:
            return None
        closing = next((d for d in deals if d.entry == self._mt5.DEAL_ENTRY_OUT), None)
        if closing is None:
            return None
        return ClosedDeal(ticket=ticket, price=closing.price,
                           reason=self._deal_reason_name(closing.reason), profit=closing.profit)

    def _deal_reason_name(self, reason_code) -> str:
        if reason_code == getattr(self._mt5, "DEAL_REASON_SL", object()):
            return "stop_hit"
        if reason_code == getattr(self._mt5, "DEAL_REASON_TP", object()):
            return "target_hit"
        return "manual_or_other"

    def _position_risk(self, position) -> float:
        """$ lost if this position's OWN stop is hit -- computed from its
        actual entry/SL and MT5's own per-point value for that symbol
        (tick_value / tick_size), not assumed to equal whatever the
        strategy originally sized it at. A position with sl == 0 (no stop
        set -- should never happen if the execution layer is doing its
        job, but a live account must not silently treat that as zero
        risk) is instead reported as its full notional exposure, which
        will correctly blow the aggregate-risk gate and block new trades
        rather than understating danger."""
        symbol_info = self._mt5.symbol_info(position.symbol)
        if position.sl == 0 or symbol_info is None:
            return abs(position.volume * position.price_open * (symbol_info.trade_contract_size
                                                                  if symbol_info else 1.0))
        points = abs(position.price_open - position.sl)
        tick_value = symbol_info.trade_tick_value
        tick_size = symbol_info.trade_tick_size or 1e-9
        return points / tick_size * tick_value * position.volume
