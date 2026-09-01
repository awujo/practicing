from types import SimpleNamespace

import pytest

from .fake_mt5 import FakeMT5, make_position, make_symbol_info
from .. import mt5_execution as mt5_execution_module
from ..mt5_execution import MT5Execution, ValidationError


def make_exec(fake, **kwargs):
    return MT5Execution(fake, **kwargs)


# ---- compute_lot_size ----

def test_compute_lot_size_converts_dollar_risk_into_a_valid_lot_size():
    fake = FakeMT5()
    fake.symbols["EURUSD"] = make_symbol_info(trade_tick_value=1.0, trade_tick_size=0.0001,
                                               volume_step=0.01, volume_max=500.0)
    ex = make_exec(fake)
    # 8 pips risk, $1/pip/lot -> $8/lot -> $1000 risk / $8 = 125 lots... use realistic numbers:
    result = ex.compute_lot_size("EURUSD", risk_amount=1000.0, entry_price=1.17374, stop_loss=1.17290)
    assert result.ok is True
    # points = 0.00084, value_per_lot = 0.00084/0.0001*1.0 = 8.4 -> raw_lots = 1000/8.4 = 119.04..
    assert result.lot_size == pytest.approx(119.04, abs=0.01)


def test_compute_lot_size_rounds_down_to_the_volume_step_never_over_risking():
    fake = FakeMT5()
    fake.symbols["EURUSD"] = make_symbol_info(trade_tick_value=10.0, trade_tick_size=0.0001, volume_step=0.1)
    ex = make_exec(fake)
    # value_per_lot = 0.001/0.0001*10 = 100 -> raw_lots = 1000/100 = 10.0 exactly -> no rounding surprise;
    # use a case that doesn't land on a step boundary instead:
    result = ex.compute_lot_size("EURUSD", risk_amount=950.0, entry_price=1.1750, stop_loss=1.1740)
    # value_per_lot = 0.001/0.0001*10 = 100 -> raw = 9.5 -> floor to nearest 0.1 = 9.5 (already aligned)
    assert result.ok is True
    assert result.lot_size <= 9.5 + 1e-9


def test_compute_lot_size_declines_rather_than_round_up_below_minimum():
    fake = FakeMT5()
    fake.symbols["XAUUSD"] = make_symbol_info(trade_tick_value=1.0, trade_tick_size=0.01,
                                               volume_min=1.0, volume_step=1.0)
    ex = make_exec(fake)
    # Tiny risk relative to tick value -> raw lots far below the 1.0 minimum.
    result = ex.compute_lot_size("XAUUSD", risk_amount=1.0, entry_price=2000.0, stop_loss=1990.0)
    assert result.ok is False
    assert result.error == ValidationError.LOT_BELOW_MINIMUM


def test_compute_lot_size_clamps_to_volume_max():
    fake = FakeMT5()
    fake.symbols["EURUSD"] = make_symbol_info(trade_tick_value=0.01, trade_tick_size=0.0001,
                                               volume_max=5.0, volume_step=0.01)
    ex = make_exec(fake)
    result = ex.compute_lot_size("EURUSD", risk_amount=1000000.0, entry_price=1.1750, stop_loss=1.1740)
    assert result.ok is True
    assert result.lot_size == 5.0


def test_compute_lot_size_symbol_not_found():
    ex = make_exec(FakeMT5())
    result = ex.compute_lot_size("NOTREAL", 1000.0, 1.0, 0.99)
    assert result.ok is False
    assert result.error == ValidationError.SYMBOL_NOT_FOUND


def test_compute_lot_size_symbol_trading_disabled():
    fake = FakeMT5()
    fake.symbols["EURUSD"] = make_symbol_info(trade_mode=0)
    ex = make_exec(fake)
    result = ex.compute_lot_size("EURUSD", 1000.0, 1.1750, 1.1740)
    assert result.ok is False
    assert result.error == ValidationError.SYMBOL_NOT_TRADEABLE


def test_compute_lot_size_rejects_zero_stop_distance():
    fake = FakeMT5()
    fake.symbols["EURUSD"] = make_symbol_info()
    ex = make_exec(fake)
    result = ex.compute_lot_size("EURUSD", 1000.0, 1.1750, 1.1750)
    assert result.ok is False
    assert result.error == ValidationError.STOP_TOO_CLOSE


def test_compute_lot_size_rejects_a_stop_closer_than_the_brokers_minimum():
    fake = FakeMT5()
    fake.symbols["EURUSD"] = make_symbol_info(point=0.0001, trade_stops_level=50)  # 5 pips minimum
    ex = make_exec(fake)
    result = ex.compute_lot_size("EURUSD", 1000.0, 1.17500, 1.17480)  # 2 pips, under the 5 pip minimum
    assert result.ok is False
    assert result.error == ValidationError.STOP_TOO_CLOSE


def test_compute_lot_size_declines_on_spread_too_wide_when_configured():
    fake = FakeMT5()
    fake.symbols["EURUSD"] = make_symbol_info(spread=50)
    ex = make_exec(fake, max_spread_points=20)
    result = ex.compute_lot_size("EURUSD", 1000.0, 1.1750, 1.1740)
    assert result.ok is False
    assert result.error == ValidationError.SPREAD_TOO_WIDE


def test_compute_lot_size_skips_spread_check_when_not_configured():
    fake = FakeMT5()
    fake.symbols["EURUSD"] = make_symbol_info(spread=500)  # very wide
    ex = make_exec(fake, max_spread_points=None)
    result = ex.compute_lot_size("EURUSD", 1000.0, 1.1750, 1.1740)
    assert result.ok is True


# ---- place_market_order ----

def test_place_market_order_succeeds_on_first_attempt():
    fake = FakeMT5()
    fake.symbols["EURUSD"] = make_symbol_info(point=0.0001)
    ex = make_exec(fake)
    result = ex.place_market_order("EURUSD", "bullish", 1.0, entry_price=1.17374,
                                    stop_loss=1.17290, target_price=1.17626)
    assert result.success is True
    assert result.ticket == 1001
    assert result.attempts == 1
    assert result.slippage_points == 0.0


def test_place_market_order_computes_slippage_from_the_actual_fill_price():
    fake = FakeMT5()
    # 5-digit broker convention (point=0.00001), matching this test's own
    # price literals below -- point=0.0001 would round entry_price's 5th
    # decimal away before computing slippage, which is what this test is
    # actually checking.
    fake.symbols["EURUSD"] = make_symbol_info(point=0.00001, digits=5)
    fake.order_send_queue = [SimpleNamespace(retcode=fake.TRADE_RETCODE_DONE, order=2002,
                                              price=1.17384, comment="ok")]  # filled 1 pip (10 points) worse
    ex = make_exec(fake)
    result = ex.place_market_order("EURUSD", "bullish", 1.0, entry_price=1.17374,
                                    stop_loss=1.17290, target_price=1.17626)
    assert result.success is True
    # 1 pip = 0.0001 = 10 points on a 5-digit (point=0.00001) broker.
    assert result.slippage_points == pytest.approx(10.0, abs=0.01)


def test_place_market_order_snaps_prices_to_the_symbols_tick_grid():
    # Confirmed live 2026-08-29: USDCHF/EURJPY/AUDCAD orders all rejected
    # with TRADE_RETCODE_INVALID_STOPS. entry_price/stop_loss/target_price
    # come from the strategy's own pip-padding arithmetic, which routinely
    # produces float noise (e.g. 159.44850000000002) that doesn't land
    # exactly on the broker's tick grid -- MT5 rejects that outright.
    fake = FakeMT5()
    fake.symbols["USDJPY"] = make_symbol_info(point=0.001, digits=3)
    fake.order_send_queue = [SimpleNamespace(retcode=fake.TRADE_RETCODE_DONE, order=3001,
                                              price=159.449, comment="ok")]
    ex = make_exec(fake)
    result = ex.place_market_order(
        "USDJPY", "bullish", 1.0,
        entry_price=159.44850000000002, stop_loss=159.39800000000002, target_price=159.601,
    )
    assert result.success is True
    sent = fake.order_send_calls[-1]
    assert sent["price"] == 159.449
    assert sent["sl"] == 159.398
    assert sent["tp"] == 159.601


def test_place_market_order_fails_immediately_on_a_non_retryable_retcode():
    fake = FakeMT5()
    fake.symbols["EURUSD"] = make_symbol_info(point=0.0001)
    fake.order_send_queue = [SimpleNamespace(retcode=fake.TRADE_RETCODE_NO_MONEY, order=0,
                                              price=0, comment="not enough money")]
    ex = make_exec(fake, max_retries=3, retry_backoff_seconds=0, recovery_check_settle_seconds=0)
    result = ex.place_market_order("EURUSD", "bullish", 1.0, 1.17374, 1.17290, 1.17626)
    assert result.success is False
    assert result.retcode_name == "TRADE_RETCODE_NO_MONEY"
    assert result.attempts == 1  # did not retry a non-transient failure


def test_place_market_order_retries_a_requote_and_then_succeeds():
    fake = FakeMT5()
    fake.symbols["EURUSD"] = make_symbol_info(point=0.0001)
    fake.order_send_queue = [
        SimpleNamespace(retcode=fake.TRADE_RETCODE_REQUOTE, order=0, price=0, comment="requote"),
        SimpleNamespace(retcode=fake.TRADE_RETCODE_DONE, order=3003, price=1.17374, comment="ok"),
    ]
    ex = make_exec(fake, max_retries=3, retry_backoff_seconds=0, recovery_check_settle_seconds=0)
    result = ex.place_market_order("EURUSD", "bullish", 1.0, 1.17374, 1.17290, 1.17626)
    assert result.success is True
    assert result.attempts == 2
    assert len(fake.order_send_calls) == 2


def test_place_market_order_gives_up_after_max_retries_of_rejected_sends():
    # REQUOTE is a REJECTED-class failure: the broker answered and refused,
    # so nothing landed and re-sending cannot duplicate. This is the one
    # path that still loops, and it must still give up at max_retries.
    fake = FakeMT5()
    fake.symbols["EURUSD"] = make_symbol_info(point=0.0001)
    fake.order_send_queue = [
        SimpleNamespace(retcode=fake.TRADE_RETCODE_REQUOTE, order=0, price=0, comment="requote"),
        SimpleNamespace(retcode=fake.TRADE_RETCODE_REQUOTE, order=0, price=0, comment="requote"),
        SimpleNamespace(retcode=fake.TRADE_RETCODE_REQUOTE, order=0, price=0, comment="requote"),
    ]
    ex = make_exec(fake, max_retries=3, retry_backoff_seconds=0, recovery_check_settle_seconds=0)
    result = ex.place_market_order("EURUSD", "bullish", 1.0, 1.17374, 1.17290, 1.17626)
    assert result.success is False
    assert result.attempts == 3
    assert len(fake.order_send_calls) == 3


def test_an_ambiguous_timeout_is_sent_exactly_once_even_when_nothing_landed():
    # THE regression test for the 2026-09-01 CHFJPY triple-fill. A TIMEOUT
    # gives no answer, so "nothing landed" is not knowable -- the recovery
    # check returning empty is NOT proof, because a real fill may simply
    # not have propagated yet. Live, that check came back empty three
    # times while three 6.42-lot positions were actually opening.
    #
    # So: exactly ONE send, no matter how many retries are configured.
    # This deliberately gives up a genuinely-recoverable transient failure
    # (see the renamed test below) -- that trade-off is the fix.
    fake = FakeMT5()
    fake.symbols["EURUSD"] = make_symbol_info(point=0.0001)
    fake.positions = []
    fake.order_send_queue = [
        SimpleNamespace(retcode=fake.TRADE_RETCODE_TIMEOUT, order=0, price=0, comment="timeout"),
        SimpleNamespace(retcode=fake.TRADE_RETCODE_TIMEOUT, order=0, price=0, comment="timeout"),
        SimpleNamespace(retcode=fake.TRADE_RETCODE_TIMEOUT, order=0, price=0, comment="timeout"),
    ]
    ex = make_exec(fake, max_retries=3, retry_backoff_seconds=0, recovery_check_settle_seconds=0)
    result = ex.place_market_order("EURUSD", "bullish", 1.0, 1.17374, 1.17290, 1.17626)

    assert len(fake.order_send_calls) == 1, "an ambiguous send must NEVER be re-sent"
    assert result.attempts == 1
    assert result.success is False
    assert "NOT retried" in result.reason


def test_order_send_returning_none_is_also_ambiguous_and_not_retried():
    # order_send() returning None is the most ambiguous outcome there is:
    # no retcode, no confirmation, nothing. It used to be retried (and the
    # retry could succeed, which is what this test used to assert) -- but
    # "no answer" cannot be distinguished from "filled, reply lost", so it
    # now takes the same terminal path as an explicit TIMEOUT.
    fake = FakeMT5()
    fake.symbols["EURUSD"] = make_symbol_info(point=0.0001)

    calls = {"n": 0}
    real_send = fake.order_send

    def flaky_send(request):
        calls["n"] += 1
        if calls["n"] == 1:
            return None
        return real_send(request)

    fake.order_send = flaky_send
    ex = make_exec(fake, max_retries=3, retry_backoff_seconds=0, recovery_check_settle_seconds=0)
    result = ex.place_market_order("EURUSD", "bullish", 1.0, 1.17374, 1.17290, 1.17626)
    assert calls["n"] == 1, "a None reply must not be re-sent"
    assert result.success is False
    assert result.attempts == 1


def test_sell_order_uses_order_type_sell():
    fake = FakeMT5()
    fake.symbols["EURUSD"] = make_symbol_info(point=0.0001)
    ex = make_exec(fake)
    ex.place_market_order("EURUSD", "bearish", 1.0, 1.17374, 1.17458, 1.17122)
    assert fake.order_send_calls[-1]["type"] == fake.ORDER_TYPE_SELL


def test_broker_symbol_suffix_is_applied_to_orders():
    fake = FakeMT5()
    fake.symbols["EURUSD.a"] = make_symbol_info(point=0.0001)
    ex = make_exec(fake, symbol_suffix=".a")
    ex.place_market_order("EURUSD", "bullish", 1.0, 1.17374, 1.17290, 1.17626)
    assert fake.order_send_calls[-1]["symbol"] == "EURUSD.a"


def test_broker_symbol_override_takes_priority_over_suffix_in_execution_too():
    ex = make_exec(FakeMT5(), symbol_suffix=".a", symbol_overrides={"NAS100": "USTEC"})
    assert ex.broker_symbol("NAS100") == "USTEC"
    assert ex.broker_symbol("EURUSD") == "EURUSD.a"


# ---- filling mode selection ----
# Confirmed live on MetaQuotes-Demo: hardcoding ORDER_FILLING_IOC gets a
# real order rejected with TRADE_RETCODE_INVALID_FILL on brokers that only
# support "Market execution" (Return). type_filling must be picked from
# the symbol's own filling_mode bitmask, not assumed.

def test_order_uses_ioc_when_the_symbol_supports_it():
    fake = FakeMT5()
    fake.symbols["EURUSD"] = make_symbol_info(point=0.0001, filling_mode=2)  # IOC bit only
    ex = make_exec(fake)
    ex.place_market_order("EURUSD", "bullish", 1.0, 1.17374, 1.17290, 1.17626)
    assert fake.order_send_calls[-1]["type_filling"] == fake.ORDER_FILLING_IOC


def test_order_falls_back_to_fok_when_ioc_is_not_supported():
    fake = FakeMT5()
    fake.symbols["EURUSD"] = make_symbol_info(point=0.0001, filling_mode=1)  # FOK bit only
    ex = make_exec(fake)
    ex.place_market_order("EURUSD", "bullish", 1.0, 1.17374, 1.17290, 1.17626)
    assert fake.order_send_calls[-1]["type_filling"] == fake.ORDER_FILLING_FOK


def test_order_falls_back_to_return_when_neither_fok_nor_ioc_is_supported():
    # This is the exact case hit against the real MetaQuotes-Demo broker --
    # filling_mode with neither bit set means "Market execution" only.
    fake = FakeMT5()
    fake.symbols["EURUSD"] = make_symbol_info(point=0.0001, filling_mode=0)
    ex = make_exec(fake)
    ex.place_market_order("EURUSD", "bullish", 1.0, 1.17374, 1.17290, 1.17626)
    assert fake.order_send_calls[-1]["type_filling"] == fake.ORDER_FILLING_RETURN


# ---- idempotency: never duplicate an order that actually landed ----
#
# Regression tests for the 2026-08-26 live incident. A EURCAD entry hit
# TRADE_RETCODE_CONNECTION, the retry loop re-sent the identical request,
# and THREE 10.05-lot positions were opened for one intended trade. They
# stopped out together for -3,246.27 on a 100k demo account, while the
# audit log recorded a single "execution_failed" and the bot tracked
# none of them -- leaving the risk manager blind to the whole position.

def _connection_failure(fake):
    return SimpleNamespace(retcode=fake.TRADE_RETCODE_CONNECTION, order=0, price=0,
                            comment="Request rejected due to absence of network connection")


def test_a_connection_failure_whose_order_actually_landed_is_not_retried():
    # The exact live scenario: the broker DID fill it, the confirmation
    # was lost. Retrying here is what opened the duplicates.
    fake = FakeMT5()
    fake.symbols["EURCAD"] = make_symbol_info(point=0.0001)
    fake.order_send_queue = [_connection_failure(fake)]

    def fill_after_send(request):
        fake.order_send_calls.append(request)
        # The position exists on the broker despite the failed reply.
        fake.positions = [make_position(9001, "EURCAD", 1.61707, 1.61562, 10.05)]
        return fake.order_send_queue.pop(0)

    fake.order_send = fill_after_send
    ex = make_exec(fake, max_retries=3, retry_backoff_seconds=0, recovery_check_settle_seconds=0)
    result = ex.place_market_order("EURCAD", "bullish", 10.05, 1.61707, 1.61562, 1.61990)

    assert len(fake.order_send_calls) == 1, "must NOT re-send an order that already landed"
    assert result.success is True          # it really did open -- report it as such
    assert result.ticket == 9001           # so the caller tracks it and risk sees it
    assert "confirmed open on the broker" in result.reason


def test_a_connection_failure_that_truly_failed_is_NOT_retried_anymore():
    # DELIBERATE REVERSAL of this test's original assertion (it used to
    # require the retry, asserting 2 sends and an eventual success).
    #
    # The original reasoning was that if nothing landed, retrying is free.
    # That is true -- but only if you can TELL that nothing landed, and
    # 2026-09-01 proved you cannot: the check that answers that question
    # queries the broker over the same link whose failure caused the
    # ambiguity, so it reports "nothing landed" for fills that simply have
    # not propagated. Acting on that answer opened three real CHFJPY
    # positions against one intended trade, none of them tracked.
    #
    # So this case -- a connection failure where genuinely nothing landed
    # -- now costs a missed entry instead of a retry. That is the accepted
    # price: one missed trade out of ~1400 is a rounding error against a
    # silently tripled position carrying a stop sized for a single one.
    fake = FakeMT5()
    fake.symbols["EURCAD"] = make_symbol_info(point=0.0001)
    fake.positions = []  # nothing ever opens
    fake.order_send_queue = [
        _connection_failure(fake),
        SimpleNamespace(retcode=fake.TRADE_RETCODE_DONE, order=9002, price=1.61707, comment="ok"),
    ]
    ex = make_exec(fake, max_retries=3, retry_backoff_seconds=0, recovery_check_settle_seconds=0)
    result = ex.place_market_order("EURCAD", "bullish", 10.05, 1.61707, 1.61562, 1.61990)

    assert len(fake.order_send_calls) == 1, "the queued success must never be reached"
    assert result.success is False
    assert result.ticket is None


def test_a_pre_existing_position_on_the_same_symbol_is_not_mistaken_for_our_fill():
    # We already hold a EURCAD position from an earlier trade. A genuinely
    # failed send must not "recover" that unrelated ticket and report a
    # fill that never happened.
    fake = FakeMT5()
    fake.symbols["EURCAD"] = make_symbol_info(point=0.0001)
    fake.positions = [make_position(7777, "EURCAD", 1.60000, 1.59900, 1.0)]
    fake.order_send_queue = [_connection_failure(fake)] * 3
    ex = make_exec(fake, max_retries=3, retry_backoff_seconds=0, recovery_check_settle_seconds=0)
    result = ex.place_market_order("EURCAD", "bullish", 10.05, 1.61707, 1.61562, 1.61990)

    assert result.success is False
    assert result.ticket is None
    assert "NOT retried" in result.reason


def test_a_position_from_another_bot_is_not_adopted():
    # Same symbol, different magic number -- someone else's position (or a
    # manual trade). Never claim it as ours.
    fake = FakeMT5()
    fake.symbols["EURCAD"] = make_symbol_info(point=0.0001)
    fake.order_send_queue = [_connection_failure(fake)] * 3

    def foreign_position_appears(request):
        fake.order_send_calls.append(request)
        fake.positions = [make_position(8888, "EURCAD", 1.61707, 1.61562, 10.05, magic=99999999)]
        return fake.order_send_queue.pop(0)

    fake.order_send = foreign_position_appears
    ex = make_exec(fake, max_retries=3, retry_backoff_seconds=0, recovery_check_settle_seconds=0)
    result = ex.place_market_order("EURCAD", "bullish", 10.05, 1.61707, 1.61562, 1.61990)

    assert result.success is False
    assert result.ticket is None


def test_a_definitive_rejection_is_never_probed_or_retried():
    # NO_MONEY etc. are unambiguous -- the broker refused it, nothing
    # landed, and it must fail fast without extra queries.
    fake = FakeMT5()
    fake.symbols["EURCAD"] = make_symbol_info(point=0.0001)
    fake.order_send_queue = [SimpleNamespace(retcode=fake.TRADE_RETCODE_NO_MONEY, order=0,
                                              price=0, comment="no money")]
    ex = make_exec(fake, max_retries=3, retry_backoff_seconds=0, recovery_check_settle_seconds=0)
    result = ex.place_market_order("EURCAD", "bullish", 10.05, 1.61707, 1.61562, 1.61990)

    assert result.success is False
    assert len(fake.order_send_calls) == 1


# ---- confirmed live 2026-08-31: a duplicate EURCAD fill (x2) and an
# EURNZD fill (x3, all within the same second) both slipped through this
# retry loop after an ambiguous TIMEOUT. Root cause: _our_open_tickets()
# returned an empty set both when it genuinely found nothing AND when
# positions_get() itself failed -- the exact connectivity trouble that
# produces a TIMEOUT often also makes positions_get() unreliable at that
# same moment, so the "did it land?" check went blind precisely when it
# mattered and let the loop retry (and re-fill) a request that had
# already gone through.

def test_when_positions_get_itself_fails_the_order_is_not_retried_blind():
    # Retrying here is exactly how the live duplicates happened: the
    # order may well have landed, we just couldn't verify it -- the only
    # safe thing to do is stop and demand a human look, not guess again.
    fake = FakeMT5()
    fake.symbols["EURCAD"] = make_symbol_info(point=0.0001)
    fake.order_send_queue = [_connection_failure(fake)]

    def positions_get_broken():
        raise RuntimeError("terminal unreachable")

    fake.positions_get = positions_get_broken
    ex = make_exec(fake, max_retries=3, retry_backoff_seconds=0, recovery_check_settle_seconds=0)
    result = ex.place_market_order("EURCAD", "bullish", 10.05, 1.61707, 1.61562, 1.61990)

    assert result.success is False
    assert len(fake.order_send_calls) == 1, "must NOT retry when it cannot verify whether the first attempt landed"
    assert "could NOT verify" in result.reason
    assert "MANUAL RECONCILIATION" in result.reason


def test_a_fill_that_only_appears_after_the_settle_delay_is_recovered_not_retried(monkeypatch):
    # Confirmed live: a fill can be real but not yet reflected in
    # positions_get() the instant an ambiguous failure comes back --
    # checking too fast is itself part of what let a duplicate through.
    # Simulates the broker's position list catching up DURING the settle
    # sleep, so the check right after it must see the real fill instead
    # of concluding nothing landed and retrying into a duplicate.
    fake = FakeMT5()
    fake.symbols["EURCAD"] = make_symbol_info(point=0.0001)
    fake.order_send_queue = [_connection_failure(fake)]
    fake.positions = []  # nothing visible yet the instant the ambiguous failure returns

    slept = []

    def fake_sleep(seconds):
        slept.append(seconds)
        fake.positions = [make_position(9009, "EURCAD", 1.61707, 1.61562, 10.05)]

    monkeypatch.setattr(mt5_execution_module.time, "sleep", fake_sleep)
    ex = make_exec(fake, max_retries=3, retry_backoff_seconds=0, recovery_check_settle_seconds=5)
    result = ex.place_market_order("EURCAD", "bullish", 10.05, 1.61707, 1.61562, 1.61990)

    assert slept == [5], "the settle delay must actually be waited out, not skipped"
    assert len(fake.order_send_calls) == 1, "must NOT retry -- the settle delay is what revealed the real fill"
    assert result.success is True
    assert result.ticket == 9009


# ---- entry-drift guard (max_entry_drift_fraction) ----
#
# Confirmed live 2026-09-01 (CHFJPY): a 17:00 signal computing entry
# 197.8515 / stop 198.101 was still sent at 18:58, filling ~197.34 --
# about 2x its own stop distance away -- while sl/tp went to the broker
# sized for 197.8515. Result: risk ~0.76 vs reward ~0.23, an inverted
# R:R the strategy never intended. Opt-in (None by default), matching
# max_spread_points; wired on at 0.25 in run_live.py.

def _info_with_price(bid, ask, **kwargs):
    info = make_symbol_info(**kwargs)
    info.bid = bid
    info.ask = ask
    return info


def test_entry_drift_guard_is_off_unless_configured():
    # Default None must not introduce a new decline path for callers that
    # never asked for it -- the market here is miles from the entry.
    fake = FakeMT5()
    fake.symbols["EURUSD"] = _info_with_price(1.20000, 1.20002)
    ex = make_exec(fake)
    assert ex.compute_lot_size("EURUSD", 1000.0, 1.17374, 1.17290).ok is True


def test_entry_drift_guard_allows_a_market_still_near_the_computed_entry():
    # Stop distance 0.00084; drift limit at 25% is 0.00021. Market is
    # 0.00010 away -- comfortably inside.
    fake = FakeMT5()
    fake.symbols["EURUSD"] = _info_with_price(1.17383, 1.17385)
    ex = make_exec(fake, max_entry_drift_fraction=0.25)
    assert ex.compute_lot_size("EURUSD", 1000.0, 1.17374, 1.17290).ok is True


def test_entry_drift_guard_declines_once_price_has_moved_too_far():
    # Same 0.00084 stop distance, but the market has moved 0.00050 away --
    # past the 0.00021 limit. A market order would fill here carrying a
    # stop sized for 1.17374.
    fake = FakeMT5()
    fake.symbols["EURUSD"] = _info_with_price(1.17423, 1.17425)
    ex = make_exec(fake, max_entry_drift_fraction=0.25)
    result = ex.compute_lot_size("EURUSD", 1000.0, 1.17374, 1.17290)
    assert result.ok is False
    assert result.error is ValidationError.ENTRY_PRICE_DRIFTED


def test_entry_drift_guard_reproduces_the_chfjpy_incident():
    # The real numbers: entry 197.8515, stop 198.101 (distance 0.2495),
    # market already down at ~197.34 by send time (drift ~0.51, over 2x
    # the whole stop distance). This must never be sent.
    fake = FakeMT5()
    fake.symbols["CHFJPY"] = _info_with_price(197.336, 197.340,
                                               trade_tick_size=0.001, point=0.001, digits=3)
    ex = make_exec(fake, max_entry_drift_fraction=0.25)
    result = ex.compute_lot_size("CHFJPY", 1000.0, 197.8515, 198.101)
    assert result.ok is False
    assert result.error is ValidationError.ENTRY_PRICE_DRIFTED


def test_entry_drift_guard_prefers_symbol_info_tick_over_symbol_info():
    # symbol_info carries a stale price; the tick call is the live one and
    # must win. Here the tick says we're still near the entry.
    fake = FakeMT5()
    fake.symbols["EURUSD"] = _info_with_price(1.19000, 1.19002)  # stale/wrong
    fake.symbol_info_tick = lambda symbol: SimpleNamespace(bid=1.17373, ask=1.17375)
    ex = make_exec(fake, max_entry_drift_fraction=0.25)
    assert ex.compute_lot_size("EURUSD", 1000.0, 1.17374, 1.17290).ok is True


def test_entry_drift_guard_fails_closed_when_no_price_is_available():
    # "Couldn't check" must not read as "checked, all clear" -- the same
    # conflation that caused the live duplicate fills via
    # _our_open_tickets(). No bid/ask anywhere => decline.
    fake = FakeMT5()
    fake.symbols["EURUSD"] = make_symbol_info()  # no bid/ask attributes at all
    ex = make_exec(fake, max_entry_drift_fraction=0.25)
    result = ex.compute_lot_size("EURUSD", 1000.0, 1.17374, 1.17290)
    assert result.ok is False
    assert result.error is ValidationError.PRICE_UNAVAILABLE


def test_entry_drift_guard_survives_a_throwing_symbol_info_tick():
    # A bridge that raises on symbol_info_tick must fall back to
    # symbol_info rather than taking the whole entry path down.
    fake = FakeMT5()
    fake.symbols["EURUSD"] = _info_with_price(1.17373, 1.17375)

    def boom(symbol):
        raise RuntimeError("bridge lost the connection")

    fake.symbol_info_tick = boom
    ex = make_exec(fake, max_entry_drift_fraction=0.25)
    assert ex.compute_lot_size("EURUSD", 1000.0, 1.17374, 1.17290).ok is True


def test_entry_drift_guard_at_the_production_setting_still_blocks_the_chfjpy_fill():
    # run_live.py wires 1.0 -- a FULL stop distance. The live CHFJPY fill
    # drifted ~2x its stop distance, so it must still be refused at the
    # value actually shipped, not just at the tighter one used above.
    fake = FakeMT5()
    fake.symbols["CHFJPY"] = _info_with_price(197.336, 197.340,
                                               trade_tick_size=0.001, point=0.001, digits=3)
    ex = make_exec(fake, max_entry_drift_fraction=1.0)
    result = ex.compute_lot_size("CHFJPY", 1000.0, 197.8515, 198.101)
    assert result.ok is False
    assert result.error is ValidationError.ENTRY_PRICE_DRIFTED


def test_entry_drift_guard_at_production_tolerates_ordinary_execution_latency():
    # The failure mode of setting this too tight: declining good trades in
    # bulk and looking identical to "found no setups". A 10-pip SLK stop
    # with the market 4 pips off entry -- well within normal drift between
    # candle close and send -- must still trade at 1.0.
    fake = FakeMT5()
    fake.symbols["EURUSD"] = _info_with_price(1.17414, 1.17416)  # 4 pips above entry
    ex = make_exec(fake, max_entry_drift_fraction=1.0)
    result = ex.compute_lot_size("EURUSD", 1000.0, 1.17374, 1.17274)  # 10 pip stop
    assert result.ok is True


def test_entry_drift_guard_treats_an_unusable_price_type_as_unavailable_not_a_crash():
    # A bridge handing back a string (or anything non-numeric) must produce
    # the clean PRICE_UNAVAILABLE decline, NOT an exception -- an exception
    # here escapes compute_lot_size and gets swallowed by _check_instrument's
    # per-instrument isolation, skipping the whole instrument for that poll.
    fake = FakeMT5()
    fake.symbols["EURUSD"] = _info_with_price("not-a-price", None)
    ex = make_exec(fake, max_entry_drift_fraction=1.0)
    result = ex.compute_lot_size("EURUSD", 1000.0, 1.17374, 1.17290)
    assert result.ok is False
    assert result.error is ValidationError.PRICE_UNAVAILABLE


def test_entry_drift_guard_ignores_zero_and_negative_quotes():
    # MT5 can report 0.0 bid/ask for a symbol with no live quote. That is
    # "no price", not "price is zero" -- treating it numerically would make
    # every entry look infinitely drifted.
    fake = FakeMT5()
    fake.symbols["EURUSD"] = _info_with_price(0.0, -1.0)
    ex = make_exec(fake, max_entry_drift_fraction=1.0)
    result = ex.compute_lot_size("EURUSD", 1000.0, 1.17374, 1.17290)
    assert result.ok is False
    assert result.error is ValidationError.PRICE_UNAVAILABLE
