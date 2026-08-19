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

from dataclasses import dataclass

import pandas as pd

from backtest.engine.candles import Candle
from .risk_manager import AccountState, OpenPosition

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

    def __init__(self, mt5_module, login: int, password: str, server: str, symbol_suffix: str = ""):
        self._mt5 = mt5_module
        self._login = login
        self._password = password
        self._server = server
        self._symbol_suffix = symbol_suffix
        self._connected = False
        # last CLOSED candle time seen per (internal_symbol, granularity) --
        # used to detect "a new candle just closed" without re-processing
        # the same bar twice.
        self._last_closed_time: dict[tuple[str, str], pd.Timestamp] = {}

    def broker_symbol(self, internal_symbol: str) -> str:
        return f"{internal_symbol}{self._symbol_suffix}"

    def connect(self) -> None:
        if not self._mt5.initialize():
            raise MT5ConnectionError(f"mt5.initialize() failed: {self._mt5.last_error()}")
        if not self._mt5.login(self._login, password=self._password, server=self._server):
            raise MT5ConnectionError(f"mt5.login() failed for login {self._login}@{self._server}: "
                                      f"{self._mt5.last_error()}")
        self._connected = True

    def disconnect(self) -> None:
        self._mt5.shutdown()
        self._connected = False

    def is_healthy(self) -> bool:
        if not self._connected:
            return False
        info = self._mt5.terminal_info()
        return info is not None and getattr(info, "connected", False)

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
        # start=1 skips the still-forming bar at index 0 directly, rather
        # than fetching count+1 and slicing -- one fewer thing to get
        # off-by-one wrong.
        rates = self._mt5.copy_rates_from_pos(symbol, timeframe, 1, count)
        if rates is None:
            raise MT5ConnectionError(f"copy_rates_from_pos({symbol}, {granularity}) failed: "
                                      f"{self._mt5.last_error()}")
        candles = [
            Candle(pd.Timestamp(r["time"], unit="s", tz="UTC"), float(r["open"]), float(r["high"]),
                   float(r["low"]), float(r["close"]), float(r["tick_volume"]))
            for r in rates
        ]
        candles.sort(key=lambda c: c.time)
        return candles

    def new_candle_closed(self, internal_symbol: str, granularity: str) -> Candle | None:
        """Call this on a polling loop (fast enough to not miss a close,
        e.g. every few seconds) -- returns the newly-closed candle the
        FIRST time it's seen, then None on every subsequent call until
        another one closes. This is what should actually trigger a
        strategy re-evaluation, not a fixed timer -- see the module
        docstring on why live and backtest need to agree on this."""
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
