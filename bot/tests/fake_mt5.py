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
    TIMEFRAME_M1 = "M1"

    ORDER_TYPE_BUY = 0
    ORDER_TYPE_SELL = 1
    TRADE_ACTION_DEAL = 1
    ORDER_TIME_GTC = 0
    ORDER_FILLING_FOK = 0
    ORDER_FILLING_IOC = 1
    ORDER_FILLING_RETURN = 2

    TRADE_RETCODE_DONE = 10009
    TRADE_RETCODE_REQUOTE = 10004
    TRADE_RETCODE_TIMEOUT = 10012
    TRADE_RETCODE_CONNECTION = 10031
    TRADE_RETCODE_PRICE_CHANGED = 10020
    TRADE_RETCODE_PRICE_OFF = 10021
    TRADE_RETCODE_INVALID_STOPS = 10016
    TRADE_RETCODE_NO_MONEY = 10019

    DEAL_ENTRY_IN = 0
    DEAL_ENTRY_OUT = 1
    DEAL_REASON_SL = 3
    DEAL_REASON_TP = 4

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
        self.initialize_path = None  # last `path=` value initialize() was called with, for assertions
        self.initialize_calls = 0

        # order_send scripting: a queue of results to return in sequence
        # (lets tests simulate "requote then success", etc.); if empty,
        # falls back to a plain successful fill at the requested price.
        self.order_send_queue: list = []
        self.order_send_calls: list[dict] = []
        self.deals_by_position: dict[int, tuple] = {}

    def order_send(self, request):
        self.order_send_calls.append(request)
        if self.order_send_queue:
            return self.order_send_queue.pop(0)
        return SimpleNamespace(retcode=self.TRADE_RETCODE_DONE, order=1001,
                                price=request["price"], comment="ok")

    def initialize(self, path=None):
        self.initialize_calls += 1
        self.initialize_path = path
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

    def history_deals_get(self, position=None):
        return self.deals_by_position.get(position, ())


def make_rate(time_unix, o, h, l, c, tick_volume=1000):
    return {"time": time_unix, "open": o, "high": h, "low": l, "close": c, "tick_volume": tick_volume}


def make_position(ticket, symbol, price_open, sl, volume, magic=20260101):
    return SimpleNamespace(ticket=ticket, symbol=symbol, price_open=price_open, sl=sl,
                            volume=volume, magic=magic)


def make_deal(entry, price, profit, reason):
    return SimpleNamespace(entry=entry, price=price, profit=profit, reason=reason)


def make_symbol_info(trade_tick_value=1.0, trade_tick_size=0.0001, trade_contract_size=100000.0,
                      trade_mode=1, volume_min=0.01, volume_max=100.0, volume_step=0.01,
                      point=0.0001, trade_stops_level=0, spread=10, filling_mode=3, digits=4):
    return SimpleNamespace(trade_tick_value=trade_tick_value, trade_tick_size=trade_tick_size,
                            trade_contract_size=trade_contract_size, trade_mode=trade_mode,
                            volume_min=volume_min, volume_max=volume_max, volume_step=volume_step,
                            point=point, trade_stops_level=trade_stops_level, spread=spread,
                            filling_mode=filling_mode, digits=digits)
