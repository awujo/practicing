"""A minimal fake of the `MetaTrader5` package's documented API surface,
just enough to unit-test mt5_data.py's conversion/detection logic without
a real terminal. Return shapes (dict rows for copy_rates_from_pos, simple
namespaces for account_info/positions_get/symbol_info/terminal_info)
mirror what the real package documents, but this is NOT a substitute for
testing against an actual MT5 connection."""

from types import SimpleNamespace


class FakeMT5:
    TIMEFRAME_W1 = "W1"
    TIMEFRAME_D1 = "D1"
    TIMEFRAME_H4 = "H4"
    TIMEFRAME_H1 = "H1"

    def __init__(self):
        self.initialized = False
        self.logged_in = False
        self.terminal_connected = True
        self.rates_by_symbol_timeframe: dict[tuple[str, str], list[dict]] = {}
        self.account = SimpleNamespace(balance=100000.0, equity=100000.0)
        self.positions: list = []
        self.symbols: dict[str, SimpleNamespace] = {}
        self._last_error = (0, "no error")
        self._fail_init = False
        self._fail_login = False

    def initialize(self):
        if self._fail_init:
            self._last_error = (1, "init failed")
            return False
        self.initialized = True
        return True

    def login(self, login, password, server):
        if self._fail_login:
            self._last_error = (2, "login failed")
            return False
        self.logged_in = True
        return True

    def shutdown(self):
        self.initialized = False
        self.logged_in = False

    def terminal_info(self):
        if not self.initialized:
            return None
        return SimpleNamespace(connected=self.terminal_connected)

    def last_error(self):
        return self._last_error

    def copy_rates_from_pos(self, symbol, timeframe, start, count):
        rows = self.rates_by_symbol_timeframe.get((symbol, timeframe))
        if rows is None:
            self._last_error = (3, f"unknown symbol {symbol}")
            return None
        return rows[start:start + count]

    def account_info(self):
        return self.account

    def positions_get(self):
        return self.positions

    def symbol_info(self, symbol):
        return self.symbols.get(symbol)


def make_rate(time_unix, o, h, l, c, tick_volume=1000):
    return {"time": time_unix, "open": o, "high": h, "low": l, "close": c, "tick_volume": tick_volume}


def make_position(ticket, symbol, price_open, sl, volume):
    return SimpleNamespace(ticket=ticket, symbol=symbol, price_open=price_open, sl=sl, volume=volume)


def make_symbol_info(trade_tick_value=1.0, trade_tick_size=0.0001, trade_contract_size=100000.0):
    return SimpleNamespace(trade_tick_value=trade_tick_value, trade_tick_size=trade_tick_size,
                            trade_contract_size=trade_contract_size)
