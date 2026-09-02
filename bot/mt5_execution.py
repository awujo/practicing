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


# A failed send splits into two CATEGORICALLY different cases, and
# conflating them is what produced the 2026-09-01 CHFJPY incident (three
# 6.42-lot positions against one intended trade, all three untracked --
# see below and OPERATIONS_LOG.md).
#
# REJECTED: the broker ANSWERED and refused the order. Nothing landed, so
# re-sending cannot possibly duplicate anything -- retrying is genuinely
# safe here, and is worth doing (a requote on a fast-moving pair is
# exactly the case retrying exists for).
REJECTED_RETCODE_NAMES = {"TRADE_RETCODE_REQUOTE", "TRADE_RETCODE_PRICE_CHANGED",
                          "TRADE_RETCODE_PRICE_OFF"}

# AMBIGUOUS: NO usable answer came back. The order may have filled with
# the confirmation lost in transit, or may never have reached the broker
# at all -- and from this side those two are indistinguishable. Retrying
# treats the first case as the second and opens a duplicate.
#
# These used to sit in the same "retryable" set as the rejections above,
# with `_recover_landed_order()` below meant to make retrying safe by
# asking the broker whether a position appeared. That check is not
# sufficient and cannot be made sufficient: it queries the broker over
# the SAME link whose failure produced the ambiguity, so under exactly
# the conditions that matter it under-reads (returns "nothing landed"
# for a position that did land but hasn't propagated yet) and greenlights
# a retry. Confirmed live 2026-09-01 on CHFJPY: order_send timed out
# three times, each attempt actually filled (197.336 / 197.360 /
# 197.328), each recovery check came back empty inside its 2s settle
# window, and the loop ran to max_retries and reported "confirmed no
# position was opened" -- while three real positions sat open, untracked
# by the bot and invisible to the risk manager.
#
# So ambiguity is now terminal: verify once (adopting the position if the
# check DOES find it), and otherwise stop and surface it for
# reconciliation rather than sending again. The cost asymmetry is not
# close -- missing one entry costs a fraction of one trade's edge out of
# ~1400 trades, while a silently multiplied position carries N times the
# intended risk with a stop-loss computed for a single one.
AMBIGUOUS_RETCODE_NAMES = {"TRADE_RETCODE_TIMEOUT", "TRADE_RETCODE_CONNECTION"}

# Kept as the union for callers/tests that ask "was this failure the kind
# we handle at all", as opposed to a hard rejection (bad stops, no money,
# market closed, invalid volume) that should surface to a human.
RETRYABLE_RETCODE_NAMES = REJECTED_RETCODE_NAMES | AMBIGUOUS_RETCODE_NAMES


class ValidationError(Enum):
    SYMBOL_NOT_FOUND = "symbol_not_found"
    SYMBOL_NOT_TRADEABLE = "symbol_not_tradeable"
    LOT_BELOW_MINIMUM = "lot_below_minimum"
    STOP_TOO_CLOSE = "stop_too_close"
    SPREAD_TOO_WIDE = "spread_too_wide"
    ENTRY_PRICE_DRIFTED = "entry_price_drifted"
    PRICE_UNAVAILABLE = "price_unavailable"


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
                 max_retries: int = 3, retry_backoff_seconds: float = 1.0, magic_number: int = 20260101,
                 recovery_check_settle_seconds: float = 2.0,
                 max_entry_drift_fraction: float | None = None):
        self._mt5 = mt5_module
        self._symbol_map = SymbolMap(suffix=symbol_suffix, overrides=symbol_overrides or {})
        self._max_slippage_points = max_slippage_points
        self._max_spread_points = max_spread_points
        self._max_retries = max_retries
        self._retry_backoff_seconds = retry_backoff_seconds
        self._magic_number = magic_number
        # See _recover_landed_order()'s docstring -- confirmed live
        # 2026-08-31, a duplicate EURCAD fill (x2) and EURNZD fill (x3)
        # both slipped through partly because the "did it land?" check
        # ran with no settle time at all.
        self._recovery_check_settle_seconds = recovery_check_settle_seconds
        # How far the live market may sit from the entry price this trade's
        # stop/target were computed against, as a fraction of the intended
        # stop distance, before the trade is declined instead of sent.
        #
        # Confirmed live 2026-09-01 (CHFJPY): a 17:00 signal computed
        # entry 197.8515 / stop 198.101 (a 0.25 stop distance) and was
        # still sent at 18:58, by which time price had moved ~50 pips to
        # ~197.34. Under Market Execution the `price` field is ignored and
        # the order fills at market, but sl/tp go to the broker exactly as
        # computed -- so it filled 2x the whole stop distance away from
        # its own entry, leaving risk ~0.76 against reward ~0.23: an
        # inverted R:R the strategy never intended and the backtest never
        # modelled. STALE_ENTRY_CUTOFF (3h, orchestrator.py) is far too
        # loose to catch this on its own, and time is the wrong unit
        # anyway -- what actually matters is whether price has moved
        # enough to invalidate the stop that was sized for it.
        #
        # None (default) disables the check entirely, matching
        # max_spread_points above: opt-in at the wiring site
        # (run_live.py), so every existing caller and test keeps its
        # previous behavior rather than silently gaining a new decline
        # path. It is deliberately FAIL-CLOSED once enabled -- if the
        # live price can't be read at all the trade is declined, since
        # "couldn't check" must not read as "checked, all clear" (this
        # codebase already has one scar from exactly that conflation --
        # see _our_open_tickets()'s docstring).
        self._max_entry_drift_fraction = max_entry_drift_fraction

    def broker_symbol(self, internal_symbol: str) -> str:
        return self._symbol_map.broker_symbol(internal_symbol)

    def internal_symbol(self, broker_symbol: str) -> str:
        return self._symbol_map.internal_symbol(broker_symbol)

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

        # Entry-drift guard -- see _max_entry_drift_fraction's comment for
        # the live incident this exists to prevent.
        if self._max_entry_drift_fraction is not None:
            current = self._current_mid_price(symbol, info)
            if current is None:
                # Fail CLOSED. Not being able to see the market is exactly
                # when sending a market order with a precomputed stop is
                # least safe, and this codebase already has one scar from
                # treating "couldn't check" as "checked, all clear" (see
                # _our_open_tickets()'s docstring).
                return ValidationResult(
                    ok=False, error=ValidationError.PRICE_UNAVAILABLE,
                    reason=f"no current bid/ask available for {symbol} (symbol_info_tick and symbol_info "
                           f"both gave nothing usable) -- cannot confirm the market is still near the "
                           f"{entry_price:g} this trade's stop was sized against, so declining rather "
                           f"than sending blind",
                )
            drift = abs(current - entry_price)
            limit = points * self._max_entry_drift_fraction
            if drift > limit:
                return ValidationResult(
                    ok=False, error=ValidationError.ENTRY_PRICE_DRIFTED,
                    reason=f"{symbol} is at {current:g}, {drift:g} away from this signal's {entry_price:g} "
                           f"entry -- more than {self._max_entry_drift_fraction:.0%} of its {points:g} stop "
                           f"distance (limit {limit:g}). A market order would fill here while the "
                           f"stop/target still go out sized for {entry_price:g}, so the trade would carry "
                           f"a risk:reward it was never validated at. Declining instead.",
                )

        return ValidationResult(ok=True, lot_size=lots)

    def _current_mid_price(self, symbol: str, info) -> float | None:
        """Live mid price, or None if the broker gives nothing usable.

        Mid rather than the side-specific bid/ask because the drift this
        guards against is measured in fractions of a stop distance --
        orders of magnitude wider than any spread -- and the caller
        (`compute_lot_size`) doesn't take a direction. `symbol_info_tick`
        is the canonical source; `symbol_info`'s own bid/ask is the
        fallback for bridges that don't expose the tick call."""
        for raw_bid, raw_ask in self._price_sources(symbol, info):
            bid, ask = self._as_price(raw_bid), self._as_price(raw_ask)
            if bid is not None and ask is not None:
                return (bid + ask) / 2
            for single in (bid, ask):
                if single is not None:
                    return single
        return None

    @staticmethod
    def _as_price(value) -> float | None:
        """A positive float, or None for anything unusable (missing, zero,
        negative, or a type that isn't a number at all).

        Coerced rather than compared directly because a bridge returning
        something unexpected -- a string, a Decimal-like proxy object --
        would otherwise raise straight out of `compute_lot_size()`. That
        exception would be caught by `_check_instrument()`'s per-instrument
        isolation and skip the WHOLE instrument for that poll, which is a
        worse outcome than the clean PRICE_UNAVAILABLE decline this
        guard is supposed to produce when it can't read a price."""
        try:
            price = float(value)
        except (TypeError, ValueError):
            return None
        return price if price > 0 else None

    def _price_sources(self, symbol: str, info):
        tick = None
        getter = getattr(self._mt5, "symbol_info_tick", None)
        if getter is not None:
            try:
                tick = getter(symbol)
            except Exception:
                tick = None
        if tick is not None:
            yield getattr(tick, "bid", None), getattr(tick, "ask", None)
        yield getattr(info, "bid", None), getattr(info, "ask", None)

    def place_market_order(self, internal_symbol: str, direction: str, lot_size: float,
                            entry_price: float, stop_loss: float, target_price: float) -> ExecutionResult:
        """direction: "bullish" | "bearish" (matches structure.Direction's
        string values used throughout the rest of this codebase)."""
        symbol = self.broker_symbol(internal_symbol)
        order_type = self._mt5.ORDER_TYPE_BUY if direction == "bullish" else self._mt5.ORDER_TYPE_SELL

        # entry_price/stop_loss/target_price come straight from the
        # strategy's own pip-padding arithmetic (entries.py), which
        # routinely produces float noise (e.g. 159.44850000000002 instead
        # of 159.4485 -- ordinary binary-float behavior, not a bug in that
        # math). MT5 order_send() rejects a sl/tp that doesn't land exactly
        # on the symbol's tick grid with TRADE_RETCODE_INVALID_STOPS --
        # confirmed live 2026-08-29 (USDCHF/EURJPY/AUDCAD, all rejected
        # this way) -- so every price must be snapped to the broker's own
        # grid before it's ever sent, not just computed to "close enough."
        info = self._mt5.symbol_info(symbol)
        entry_price = self._round_price(entry_price, info)
        stop_loss = self._round_price(stop_loss, info)
        target_price = self._round_price(target_price, info)

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

        # Tickets we already own on this symbol BEFORE sending anything.
        # order_send() is NOT idempotent, and a connection-class failure
        # is ambiguous: it means "no confirmation came back", which could
        # be either "the broker never got it" or "the broker filled it and
        # the reply was lost". Retrying blind treats the second case as
        # the first and opens a duplicate position.
        #
        # This is not hypothetical -- it happened live on 2026-08-26.
        # A EURCAD entry hit TRADE_RETCODE_CONNECTION, the retry loop
        # re-sent it, and THREE 10.05-lot positions were opened against a
        # single intended trade. All three stopped out together for
        # -3,246.27 on a 100k demo account (-3.3%), while the audit log
        # recorded one "execution_failed" and the bot tracked nothing --
        # so the risk manager was blind to all of it. On a funded or
        # prop-firm account that is a hard breach.
        #
        # Comparing ticket sets is deliberately used instead of tagging
        # the order comment: brokers truncate, rewrite or drop comments,
        # so a comment is not something correctness can rest on. Position
        # tickets and the magic number are broker-maintained.
        tickets_before = self._our_open_tickets(symbol)

        attempts = 0
        while attempts < self._max_retries:
            attempts += 1
            result = self._mt5.order_send(request)

            if result is not None:
                retcode_name = self._retcode_name(result.retcode)
                if retcode_name == "TRADE_RETCODE_DONE":
                    slippage = abs(result.price - entry_price) / self._point_size(symbol)
                    return ExecutionResult(success=True, ticket=result.order, requested_price=entry_price,
                                            filled_price=result.price, slippage_points=slippage,
                                            retcode=result.retcode, retcode_name=retcode_name,
                                            attempts=attempts)
                if retcode_name in REJECTED_RETCODE_NAMES:
                    # The broker answered and refused -- nothing landed,
                    # so re-sending is safe. This is the ONLY path that
                    # loops.
                    failure = f"{retcode_name} ({getattr(result, 'comment', '')})"
                    if attempts < self._max_retries:
                        time.sleep(self._retry_backoff_seconds)
                        continue
                    return ExecutionResult(success=False, requested_price=entry_price,
                                            retcode=result.retcode, retcode_name=retcode_name,
                                            reason=f"{failure}; retries exhausted, broker rejected every "
                                                   f"attempt so nothing landed",
                                            attempts=attempts)
                if retcode_name not in AMBIGUOUS_RETCODE_NAMES:
                    # A definitive rejection (bad volume, no money, ...).
                    # The broker refused it outright, so nothing landed.
                    return ExecutionResult(success=False, requested_price=entry_price, retcode=result.retcode,
                                            retcode_name=retcode_name,
                                            reason=f"order rejected: {retcode_name} "
                                                   f"({getattr(result, 'comment', '')})",
                                            attempts=attempts)
                failure = f"{retcode_name} ({getattr(result, 'comment', '')})"
            else:
                failure = f"order_send returned None: {self._mt5.last_error()}"

            # AMBIGUOUS from here down -- no usable answer came back, so
            # this order may or may not have landed. Check ONCE (which
            # adopts the position if it's already visible), then stop
            # either way. Never loop: see AMBIGUOUS_RETCODE_NAMES.
            recovered = self._recover_landed_order(symbol, tickets_before, entry_price, attempts, failure)
            if recovered is not None:
                return recovered

            return ExecutionResult(
                success=False, requested_price=entry_price, attempts=attempts,
                reason=f"{failure}; no position found when checked, but this send was AMBIGUOUS "
                       f"(no confirmation came back) and is deliberately NOT retried -- the check "
                       f"can under-read a fill that has not propagated yet, which is exactly how "
                       f"the 2026-09-01 CHFJPY triple-fill happened. If a {symbol} position appears "
                       f"without a matching tracked trade, it came from this send.")

        return ExecutionResult(success=False, requested_price=entry_price,
                                reason="exhausted retries", attempts=attempts)

    def place_limit_order(self, internal_symbol: str, direction: str, lot_size: float,
                           entry_price: float, stop_loss: float, target_price: float,
                           expires_at=None) -> ExecutionResult:
        """Rest a limit order AT the computed entry, rather than taking
        whatever price the market happens to be at when we get around to
        sending.

        Why this exists (2026-09-02 live audit): the bot is never prompt.
        Zero entry attempts in its history landed within 5 minutes of the
        candle closing; the spread runs 5-30m through 2h+, the tail being
        catch-up after MT5 reconnect storms. Sending a MARKET order that
        late is what produced 41 of its 42 failed attempts -- 22 declined
        as stale, 12 rejected (the stop having ended up on the wrong side
        of a price that moved while the order sat unsent), 2 declined on
        drift -- and the CHFJPY fill 50 pips from its own entry.

        A resting limit makes all of that a non-issue rather than a thing
        to detect: the order sits at the level the setup was sized for, so
        it either fills at that price or does not fill. Which is also
        simply what the strategy is -- an SLK entry is a predefined key
        level that price is expected to return to, not a chase.

        Same three safety properties as place_market_order(): every price
        snapped to the broker's tick grid first (TRADE_RETCODE_INVALID_STOPS
        otherwise -- confirmed live 2026-08-29), a rejected send may retry
        because the broker answered and nothing landed, and an AMBIGUOUS
        send is NEVER retried. The ambiguity check here looks at PENDING
        ORDERS rather than positions, since that is what this send would
        have created.

        expires_at: optional datetime after which the broker itself drops
        the order. Left as None the order is GTC and must be cancelled
        explicitly. Pass it to honour "nothing rests over the weekend"
        without depending on this process being alive to clean up.
        """
        symbol = self.broker_symbol(internal_symbol)
        order_type = (self._mt5.ORDER_TYPE_BUY_LIMIT if direction == "bullish"
                      else self._mt5.ORDER_TYPE_SELL_LIMIT)

        info = self._mt5.symbol_info(symbol)
        entry_price = self._round_price(entry_price, info)
        stop_loss = self._round_price(stop_loss, info)
        target_price = self._round_price(target_price, info)

        request = {
            "action": self._mt5.TRADE_ACTION_PENDING,
            "symbol": symbol,
            "volume": lot_size,
            "type": order_type,
            # Unlike a market send, this price is the whole point: it is
            # the level, and the broker holds the order until price
            # reaches it. No `deviation` -- there is nothing to slip.
            "price": entry_price,
            "sl": stop_loss,
            "tp": target_price,
            "magic": self._magic_number,
            "comment": "slk-bot",
            "type_time": self._mt5.ORDER_TIME_GTC,
            "type_filling": self._filling_type(symbol),
        }
        if expires_at is not None:
            request["type_time"] = self._mt5.ORDER_TIME_SPECIFIED
            request["expiration"] = expires_at

        orders_before = self._our_pending_tickets(symbol)

        attempts = 0
        while attempts < self._max_retries:
            attempts += 1
            result = self._mt5.order_send(request)

            if result is not None:
                retcode_name = self._retcode_name(result.retcode)
                if retcode_name in ("TRADE_RETCODE_DONE", "TRADE_RETCODE_PLACED"):
                    return ExecutionResult(success=True, ticket=result.order,
                                            requested_price=entry_price, filled_price=None,
                                            slippage_points=0.0, retcode=result.retcode,
                                            retcode_name=retcode_name, attempts=attempts)
                if retcode_name in REJECTED_RETCODE_NAMES:
                    failure = f"{retcode_name} ({getattr(result, 'comment', '')})"
                    if attempts < self._max_retries:
                        time.sleep(self._retry_backoff_seconds)
                        continue
                    return ExecutionResult(success=False, requested_price=entry_price,
                                            retcode=result.retcode, retcode_name=retcode_name,
                                            reason=f"{failure}; retries exhausted, broker rejected "
                                                   f"every attempt so nothing was placed",
                                            attempts=attempts)
                if retcode_name not in AMBIGUOUS_RETCODE_NAMES:
                    return ExecutionResult(success=False, requested_price=entry_price,
                                            retcode=result.retcode, retcode_name=retcode_name,
                                            reason=f"limit order rejected: {retcode_name} "
                                                   f"({getattr(result, 'comment', '')})",
                                            attempts=attempts)
                failure = f"{retcode_name} ({getattr(result, 'comment', '')})"
            else:
                failure = f"order_send returned None: {self._mt5.last_error()}"

            # AMBIGUOUS -- the pending order may or may not have been
            # accepted. Check once; never loop. A duplicate RESTING order
            # is less immediately costly than a duplicate position, but it
            # is still two orders where the risk manager counted one.
            current = self._our_pending_tickets(symbol)
            if current is not None and orders_before is not None:
                landed = current - orders_before
                if landed:
                    ticket = sorted(landed)[0]
                    return ExecutionResult(success=True, ticket=ticket, requested_price=entry_price,
                                            filled_price=None, slippage_points=0.0,
                                            retcode_name="RECOVERED_AMBIGUOUS", attempts=attempts,
                                            reason=f"{failure}; the order was found resting on a "
                                                   f"follow-up check and has been adopted")
            return ExecutionResult(
                success=False, requested_price=entry_price, attempts=attempts,
                reason=f"{failure}; no pending order found when checked, but this send was "
                       f"AMBIGUOUS (no confirmation came back) and is deliberately NOT retried "
                       f"-- the check can under-read an order that has not propagated yet. If a "
                       f"{symbol} order appears without a matching tracked one, it came from here.")

        return ExecutionResult(success=False, requested_price=entry_price,
                                reason="exhausted retries", attempts=attempts)

    def cancel_pending_order(self, ticket: int) -> ExecutionResult:
        """Remove a resting order -- the setup died, or it must not be
        left over the weekend.

        Treats "the order is already gone" as SUCCESS, not failure: it may
        have filled, expired, or been cancelled by hand, and in every one
        of those cases the caller's intent ("this must not be resting any
        more") is satisfied. Reporting failure would invite a retry loop
        against an order that no longer exists.
        """
        try:
            result = self._mt5.order_send({
                "action": self._mt5.TRADE_ACTION_REMOVE,
                "order": ticket,
            })
        except Exception as exc:
            return ExecutionResult(success=False, reason=f"cancel failed: {exc!r}", attempts=1)

        if result is None:
            return ExecutionResult(success=False, attempts=1,
                                    reason=f"cancel returned None: {self._mt5.last_error()}")
        retcode_name = self._retcode_name(result.retcode)
        if retcode_name in ("TRADE_RETCODE_DONE", "TRADE_RETCODE_PLACED"):
            return ExecutionResult(success=True, ticket=ticket, retcode=result.retcode,
                                    retcode_name=retcode_name, attempts=1)
        if retcode_name in ("TRADE_RETCODE_INVALID_ORDER", "TRADE_RETCODE_ORDER_CHANGED"):
            return ExecutionResult(success=True, ticket=ticket, retcode=result.retcode,
                                    retcode_name=retcode_name, attempts=1,
                                    reason="order was already gone (filled, expired or "
                                           "cancelled elsewhere) -- nothing left to cancel")
        return ExecutionResult(success=False, ticket=ticket, retcode=result.retcode,
                                retcode_name=retcode_name, attempts=1,
                                reason=f"cancel rejected: {retcode_name} "
                                       f"({getattr(result, 'comment', '')})")

    def our_open_positions(self) -> list | None:
        """Every open position carrying our magic number, or None if the
        query failed.

        None means "can't tell", never "there are none" -- the caller
        (weekend flatten) must escalate rather than conclude the account
        is flat. Scoped by magic so a position opened by hand in the
        terminal is left alone.
        """
        try:
            positions = self._mt5.positions_get()
        except Exception:
            return None
        # `or ()` here would be a BUG, not a tidy-up: the real MT5 API
        # returns None on FAILURE and an empty tuple when there genuinely
        # are none, without raising either way. Collapsing them makes a
        # broken query indistinguishable from a flat account -- which,
        # for the weekend flatten, means reporting "nothing to close"
        # while positions sit open through the weekend.
        if positions is None:
            return None
        return [p for p in positions if getattr(p, "magic", None) == self._magic_number]

    def close_position(self, ticket: int) -> ExecutionResult:
        """Close one position at market, by opposing deal.

        MT5 has no "close" action: closing is a DEAL in the opposite
        direction carrying `position: <ticket>`, for the position's own
        volume. Getting the volume from the broker rather than from
        anything this process remembers matters -- a partially closed
        position would otherwise be over- or under-closed.

        Deliberately NOT retried on ambiguity, for the same reason sends
        aren't: a timeout here means "no answer", and re-sending a close
        against a position that already closed opens a NEW position in the
        opposite direction. That failure mode is worse than the one it
        would be trying to fix, so an ambiguous close is surfaced for a
        human instead.
        """
        try:
            matches = self._mt5.positions_get(ticket=ticket)
        except Exception as exc:
            return ExecutionResult(success=False, ticket=ticket, attempts=0,
                                    reason=f"could not read position {ticket}: {exc!r}")
        if matches is None:
            # NOT the same as "no such position": None is the API's
            # failure signal. Reporting success here would tell the
            # weekend flatten this position is dealt with when nobody
            # has looked at it.
            return ExecutionResult(success=False, ticket=ticket, attempts=0,
                                    reason=f"could not read position {ticket}: "
                                           f"{self._mt5.last_error()} -- could NOT confirm "
                                           f"whether it is open. Check it by hand.")
        if not matches:
            # Already gone -- closed by its stop, its target, or by hand.
            # The caller's intent ("this must not be open") is satisfied.
            return ExecutionResult(success=True, ticket=ticket, attempts=0,
                                    reason="position was already closed")

        position = matches[0]
        closing_type = (self._mt5.ORDER_TYPE_SELL if position.type == self._mt5.POSITION_TYPE_BUY
                        else self._mt5.ORDER_TYPE_BUY)
        request = {
            "action": self._mt5.TRADE_ACTION_DEAL,
            "symbol": position.symbol,
            "volume": position.volume,
            "type": closing_type,
            "position": ticket,
            "deviation": self._max_slippage_points,
            "magic": self._magic_number,
            "comment": "slk-bot close",
            "type_time": self._mt5.ORDER_TIME_GTC,
            "type_filling": self._filling_type(position.symbol),
        }

        result = self._mt5.order_send(request)
        if result is None:
            return ExecutionResult(success=False, ticket=ticket, attempts=1,
                                    reason=f"close returned None: {self._mt5.last_error()} -- "
                                           f"AMBIGUOUS, not retried (a repeat close against an "
                                           f"already-closed position opens a REVERSE position). "
                                           f"Verify {ticket} by hand.")
        retcode_name = self._retcode_name(result.retcode)
        if retcode_name == "TRADE_RETCODE_DONE":
            return ExecutionResult(success=True, ticket=ticket, retcode=result.retcode,
                                    retcode_name=retcode_name, attempts=1,
                                    filled_price=getattr(result, "price", None))
        if retcode_name in AMBIGUOUS_RETCODE_NAMES:
            return ExecutionResult(success=False, ticket=ticket, retcode=result.retcode,
                                    retcode_name=retcode_name, attempts=1,
                                    reason=f"{retcode_name} -- AMBIGUOUS, not retried (a repeat "
                                           f"close against an already-closed position opens a "
                                           f"REVERSE position). Verify {ticket} by hand.")
        return ExecutionResult(success=False, ticket=ticket, retcode=result.retcode,
                                retcode_name=retcode_name, attempts=1,
                                reason=f"close rejected: {retcode_name} "
                                       f"({getattr(result, 'comment', '')})")

    def pending_tickets_by_symbol(self) -> dict | None:
        """Every resting order of ours, grouped by INTERNAL symbol, or
        None if the query itself failed.

        None means "can't tell" and callers must not treat it as "nothing
        is resting" -- the same rule as `_our_open_tickets()`. Keyed by
        internal symbol so the orchestrator, which thinks in internal
        names, doesn't have to reverse the suffix/override mapping.
        """
        try:
            orders = self._mt5.orders_get()
        except Exception:
            return None
        if orders is None:      # API failure, not an empty book -- see our_open_positions()
            return None
        by_symbol: dict = {}
        for o in orders:
            if getattr(o, "magic", None) != self._magic_number:
                continue
            internal = self.internal_symbol(getattr(o, "symbol", ""))
            by_symbol.setdefault(internal, set()).add(o.ticket)
        return by_symbol

    def _our_pending_tickets(self, symbol: str) -> set | None:
        """Our resting orders on `symbol`, or None if the query itself
        failed. None means "can't tell" and must never be read as "none
        are resting" -- same rule, and the same scar, as
        `_our_open_tickets()`."""
        try:
            orders = self._mt5.orders_get()
        except Exception:
            return None
        if orders is None:      # API failure, not an empty book
            return None
        return {
            o.ticket for o in orders
            if getattr(o, "symbol", None) == symbol
            and getattr(o, "magic", None) == self._magic_number
        }

    def _our_open_tickets(self, symbol: str) -> set | None:
        """Tickets of currently-open positions on `symbol` carrying this
        bot's magic number. Returns None (NOT an empty set) if the query
        itself fails.

        Confirmed live 2026-08-31: this used to return an empty set on
        failure, which made "the verification query broke" and "verified:
        nothing landed" produce the identical signal to
        _recover_landed_order() below. That's backwards for what this
        exists to prevent -- the exact connectivity trouble that produces
        an ambiguous TIMEOUT on order_send() is often ALSO what makes
        positions_get() unreliable at that same moment, so the one check
        meant to stop a duplicate went blind precisely when it mattered
        and let the retry loop send a genuinely-duplicate order (an
        EURCAD position filled twice, an EURNZD position filled three
        times, both untracked and unmanaged by the risk manager). "Can't
        tell" must mean "can't tell" to the caller, not "assume empty"."""
        try:
            positions = self._mt5.positions_get()
        except Exception:
            return None
        if positions is None:   # API failure, not a flat account
            return None
        return {
            p.ticket for p in positions
            if getattr(p, "symbol", None) == symbol
            and getattr(p, "magic", None) == self._magic_number
        }

    def _recover_landed_order(self, symbol: str, tickets_before: set, entry_price: float,
                               attempts: int, failure: str):
        """After an ambiguous send failure, check whether a position we
        didn't have before now exists. If so the order DID fill and the
        confirmation was simply lost -- report it as the success it
        actually is, so the caller tracks it and the risk manager sees it.

        Sleeps _recovery_check_settle_seconds before checking: a fill can
        be real but not yet reflected in positions_get() immediately
        after an ambiguous failure, and checking too fast is itself part
        of what let a duplicate order through live (see this module's
        2026-08-31 comments).

        Returns an ExecutionResult (terminal -- caller must NOT retry
        further) in two cases: a landed order was found, or the
        verification query itself failed and returning None here would
        wrongly be read as "confirmed nothing landed, safe to retry" --
        see _our_open_tickets()'s docstring for why that particular
        conflation is exactly what caused the live duplicates. Returns
        None only when verification genuinely succeeded and found
        nothing -- the one case where a retry is actually safe."""
        time.sleep(self._recovery_check_settle_seconds)
        current = self._our_open_tickets(symbol)
        if current is None:
            return ExecutionResult(
                success=False, requested_price=entry_price,
                reason=f"{failure}; could NOT verify whether a position landed (positions_get() itself "
                       f"failed) -- refusing to retry blind, since that is exactly how a real duplicate "
                       f"fill happens. MANUAL RECONCILIATION REQUIRED: check the account for an "
                       f"unexpected {symbol} position before this signal is attempted again.",
                attempts=attempts)
        landed = current - tickets_before
        if not landed:
            return None
        ticket = sorted(landed)[0]
        filled = next(
            # `or ()` is SAFE here, unlike every other positions_get call
            # in this file: the position is already confirmed adopted via
            # the ticket-set diff above, and this read only decorates the
            # result with a fill price. A None here costs a log field, not
            # a correctness guarantee.
            (getattr(p, "price_open", None) for p in (self._mt5.positions_get() or ())
             if getattr(p, "ticket", None) == ticket),
            None,
        )
        slippage = (abs(filled - entry_price) / self._point_size(symbol)) if filled else None
        return ExecutionResult(
            success=True, ticket=ticket, requested_price=entry_price, filled_price=filled,
            slippage_points=slippage, attempts=attempts,
            reason=f"send reported {failure}, but the order was confirmed open on the broker "
                   f"(ticket {ticket}) -- adopted instead of retried",
        )

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

    def _round_price(self, price: float, info) -> float:
        """Snaps `price` to the symbol's actual tick grid. Prefers
        `info.digits` (the real MT5 API's own decimal-place count for this
        symbol -- always present live); falls back to deriving a grid
        from `info.point` if `digits` isn't available. Returns `price`
        unchanged if neither is (can't validate a symbol we know nothing
        about; the broker will reject it if it's genuinely bad, same as
        before this method existed)."""
        digits = getattr(info, "digits", None) if info else None
        if digits is not None:
            return round(price, digits)
        point = getattr(info, "point", None) if info else None
        if point:
            return round(round(price / point) * point, 10)
        return price

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
