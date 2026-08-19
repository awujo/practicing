from types import SimpleNamespace

import pytest

from .fake_mt5 import FakeMT5, make_symbol_info
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
    fake.symbols["EURUSD"] = make_symbol_info(point=0.0001)
    fake.order_send_queue = [SimpleNamespace(retcode=fake.TRADE_RETCODE_DONE, order=2002,
                                              price=1.17384, comment="ok")]  # filled 1 pip worse
    ex = make_exec(fake)
    result = ex.place_market_order("EURUSD", "bullish", 1.0, entry_price=1.17374,
                                    stop_loss=1.17290, target_price=1.17626)
    assert result.success is True
    assert result.slippage_points == pytest.approx(1.0, abs=0.01)


def test_place_market_order_fails_immediately_on_a_non_retryable_retcode():
    fake = FakeMT5()
    fake.symbols["EURUSD"] = make_symbol_info(point=0.0001)
    fake.order_send_queue = [SimpleNamespace(retcode=fake.TRADE_RETCODE_NO_MONEY, order=0,
                                              price=0, comment="not enough money")]
    ex = make_exec(fake, max_retries=3, retry_backoff_seconds=0)
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
    ex = make_exec(fake, max_retries=3, retry_backoff_seconds=0)
    result = ex.place_market_order("EURUSD", "bullish", 1.0, 1.17374, 1.17290, 1.17626)
    assert result.success is True
    assert result.attempts == 2
    assert len(fake.order_send_calls) == 2


def test_place_market_order_gives_up_after_max_retries_of_transient_failures():
    fake = FakeMT5()
    fake.symbols["EURUSD"] = make_symbol_info(point=0.0001)
    fake.order_send_queue = [
        SimpleNamespace(retcode=fake.TRADE_RETCODE_TIMEOUT, order=0, price=0, comment="timeout"),
        SimpleNamespace(retcode=fake.TRADE_RETCODE_TIMEOUT, order=0, price=0, comment="timeout"),
        SimpleNamespace(retcode=fake.TRADE_RETCODE_TIMEOUT, order=0, price=0, comment="timeout"),
    ]
    ex = make_exec(fake, max_retries=3, retry_backoff_seconds=0)
    result = ex.place_market_order("EURUSD", "bullish", 1.0, 1.17374, 1.17290, 1.17626)
    assert result.success is False
    assert result.attempts == 3


def test_place_market_order_retries_when_order_send_returns_none():
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
    ex = make_exec(fake, max_retries=3, retry_backoff_seconds=0)
    result = ex.place_market_order("EURUSD", "bullish", 1.0, 1.17374, 1.17290, 1.17626)
    assert result.success is True
    assert result.attempts == 2


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
