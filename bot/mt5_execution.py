"""
MT5 order execution -- lot sizing, slippage/spread handling, order-limit
validation, and retries. Same caveat as mt5_data.py: the `mt5` module is
dependency-injected so the sizing/validation/retry logic is unit-testable
against a fake, but the real package's connection behavior and broker-
specific quirks are NOT verified here. Test against a demo account first.

Backtests size positions as a continuous dollar amount ($1,000 risk).
Live brokers only accept lots in discrete steps (`volume_step`, often
0.01), so the intended risk and the actual live risk can differ slightly
once rounded. This module rounds DOWN to the nearest step (never risk
MORE than intended) and, if that rounds below the broker's minimum lot
size entirely, DECLINES the trade rather than silently accepting more
risk than the risk manager approved -- the risk manager's gates are only
as good as the guarantee that a position's real risk never exceeds what
it was told.
"""

import time
from dataclasses import dataclass
from enum import Enum

from .config import SymbolMap


# A conservative allowlist, not "retry everything" -- retcodes here are
# transient/broker-side (requote, timeout, connection issue) and retrying
# is safe. Anything else (bad stops, no money, market closed, invalid
# volume) is a real problem retrying won't fix and should surface as a
# hard failure for a human to look at, not get silently retried into
# eventually placing a wrong order.
RETRYABLE_RETCODE_NAMES = {"TRADE_RETCODE_REQUOTE", "TRADE_RETCODE_TIMEOUT", "TRADE_RETCODE_CONNECTION",
                           "TRADE_RETCODE_PRICE_CHANGED", "TRADE_RETCODE_PRICE_OFF"}


class ValidationError(Enum):
    SYMBOL_NOT_FOUND = "symbol_not_found"
    SYMBOL_NOT_TRADEABLE = "symbol_not_tradeable"
    LOT_BELOW_MINIMUM = "lot_below_minimum"
    STOP_TOO_CLOSE = "stop_too_close"
    SPREAD_TOO_WIDE = "spread_too_wide"


@dataclass(frozen=True)
class ValidationResult:
    ok: bool
    error: ValidationError | None = None
    reason: str = ""
    lot_size: float = 0.0


@dataclass(frozen=True)
class ExecutionResult:
    success: bool
    ticket: int | None = None
    requested_price: float | None = None
    filled_price: float | None = None
    slippage_points: float | None = None
    retcode: int | None = None
    retcode_name: str = ""
    reason: str = ""
    attempts: int = 0


class MT5Execution:
    def __init__(self, mt5_module, symbol_suffix: str = "", symbol_overrides: dict[str, str] | None = None,
                 max_slippage_points: float = 10, max_spread_points: float | None = None,
                 max_retries: int = 3, retry_backoff_seconds: float = 1.0, magic_number: int = 20260101):
        self._mt5 = mt5_module
        self._symbol_map = SymbolMap(suffix=symbol_suffix, overrides=symbol_overrides or {})
        self._max_slippage_points = max_slippage_points
        self._max_spread_points = max_spread_points
        self._max_retries = max_retries
        self._retry_backoff_seconds = retry_backoff_seconds
        self._magic_number = magic_number

    def broker_symbol(self, internal_symbol: str) -> str:
        return self._symbol_map.broker_symbol(internal_symbol)

    def compute_lot_size(self, internal_symbol: str, risk_amount: float,
                          entry_price: float, stop_loss: float) -> ValidationResult:
        """Converts a $ risk amount into a broker-valid lot size, using
        the symbol's own tick value/size (NOT a hardcoded pip-value
        assumption -- forex majors, JPY pairs, metals, indices, and
        crypto all price risk differently, and symbol_info is the only
        source of truth for how much one lot's stop distance is actually
        worth for THIS specific symbol on THIS specific broker)."""
        symbol = self.broker_symbol(internal_symbol)
        info = self._mt5.symbol_info(symbol)
        if info is None:
            return ValidationResult(ok=False, error=ValidationError.SYMBOL_NOT_FOUND,
                                     reason=f"{symbol} not found in Market Watch -- check the symbol suffix")
        if not getattr(info, "trade_mode", 1):  # SYMBOL_TRADE_MODE_DISABLED == 0
            return ValidationResult(ok=False, error=ValidationError.SYMBOL_NOT_TRADEABLE,
                                     reason=f"{symbol} trading is disabled on this account/session")

        points = abs(entry_price - stop_loss)
        if points <= 0:
            return ValidationResult(ok=False, error=ValidationError.STOP_TOO_CLOSE,
                                     reason="entry price equals stop-loss price")

        value_per_lot = points / info.trade_tick_size * info.trade_tick_value
        raw_lots = risk_amount / value_per_lot if value_per_lot else 0.0

        step = info.volume_step
        lots = (raw_lots // step) * step  # round DOWN -- never risk more than intended
        lots = round(lots, 8)

        if lots < info.volume_min:
            return ValidationResult(
                ok=False, error=ValidationError.LOT_BELOW_MINIMUM,
                reason=f"${risk_amount:,.0f} risk needs {raw_lots:.4f} lots on {symbol}, but the broker's "
                       f"minimum is {info.volume_min} -- taking the minimum would risk more than intended, "
                       f"so this trade is declined rather than silently oversized",
            )
        lots = min(lots, info.volume_max)

        min_stop_distance = info.trade_stops_level * info.point if hasattr(info, "point") else 0
        if min_stop_distance and points < min_stop_distance:
            return ValidationResult(ok=False, error=ValidationError.STOP_TOO_CLOSE,
                                     reason=f"stop is {points:g} away, broker requires >= {min_stop_distance:g}")

        if self._max_spread_points is not None:
            spread_points = getattr(info, "spread", 0)
            if spread_points > self._max_spread_points:
                return ValidationResult(
                    ok=False, error=ValidationError.SPREAD_TOO_WIDE,
                    reason=f"{symbol} spread is {spread_points} points, over the {self._max_spread_points} limit "
                           f"-- likely news/thin liquidity, skipping rather than paying it",
                )

        return ValidationResult(ok=True, lot_size=lots)

    def place_market_order(self, internal_symbol: str, direction: str, lot_size: float,
                            entry_price: float, stop_loss: float, target_price: float) -> ExecutionResult:
        """direction: "bullish" | "bearish" (matches structure.Direction's
        string values used throughout the rest of this codebase)."""
        symbol = self.broker_symbol(internal_symbol)
        order_type = self._mt5.ORDER_TYPE_BUY if direction == "bullish" else self._mt5.ORDER_TYPE_SELL

        request = {
            "action": self._mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": lot_size,
            "type": order_type,
            "price": entry_price,
            "sl": stop_loss,
            "tp": target_price,
            "deviation": self._max_slippage_points,
            "magic": self._magic_number,
            "comment": "slk-bot",
            "type_time": self._mt5.ORDER_TIME_GTC,
            "type_filling": self._filling_type(symbol),
        }

        attempts = 0
        last_result = None
        while attempts < self._max_retries:
            attempts += 1
            result = self._mt5.order_send(request)
            last_result = result
            if result is None:
                if attempts < self._max_retries:
                    time.sleep(self._retry_backoff_seconds)
                    continue
                return ExecutionResult(success=False, requested_price=entry_price,
                                        reason=f"order_send returned None: {self._mt5.last_error()}",
                                        attempts=attempts)

            retcode_name = self._retcode_name(result.retcode)
            if retcode_name == "TRADE_RETCODE_DONE":
                slippage = abs(result.price - entry_price) / self._point_size(symbol)
                return ExecutionResult(success=True, ticket=result.order, requested_price=entry_price,
                                        filled_price=result.price, slippage_points=slippage,
                                        retcode=result.retcode, retcode_name=retcode_name, attempts=attempts)

            if retcode_name in RETRYABLE_RETCODE_NAMES and attempts < self._max_retries:
                time.sleep(self._retry_backoff_seconds)
                continue

            return ExecutionResult(success=False, requested_price=entry_price, retcode=result.retcode,
                                    retcode_name=retcode_name,
                                    reason=f"order rejected: {retcode_name} ({getattr(result, 'comment', '')})",
                                    attempts=attempts)

        return ExecutionResult(success=False, requested_price=entry_price,
                                reason="exhausted retries", attempts=attempts)

    def _filling_type(self, symbol: str) -> int:
        """Picks a filling mode the symbol/broker actually supports rather
        than assuming IOC everywhere -- `symbol_info().filling_mode` is a
        bitmask (SYMBOL_FILLING_FOK=1, SYMBOL_FILLING_IOC=2) of what's
        allowed for that symbol; some brokers (confirmed on MetaQuotes-
        Demo) support neither and require "Market execution" (RETURN)
        instead. Sending an unsupported mode gets the whole order rejected
        with TRADE_RETCODE_INVALID_FILL, not silently downgraded."""
        info = self._mt5.symbol_info(symbol)
        mode = getattr(info, "filling_mode", 0) if info else 0
        if mode & 2:
            return self._mt5.ORDER_FILLING_IOC
        if mode & 1:
            return self._mt5.ORDER_FILLING_FOK
        return self._mt5.ORDER_FILLING_RETURN

    def _point_size(self, symbol: str) -> float:
        info = self._mt5.symbol_info(symbol)
        return info.point if info and getattr(info, "point", 0) else 1.0

    def _retcode_name(self, retcode: int) -> str:
        """Maps an int retcode back to its constant name by reading the
        injected module's own attributes -- avoids hardcoding MT5's
        numeric values here, which have historically been broker/version
        inconsistent in some third-party docs."""
        for name in dir(self._mt5):
            if name.startswith("TRADE_RETCODE_") and getattr(self._mt5, name) == retcode:
                return name
        return f"UNKNOWN_RETCODE_{retcode}"
