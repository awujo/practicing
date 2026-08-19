import pytest

from .fake_mt5 import FakeMT5, make_rate, make_position, make_symbol_info, make_deal
from ..mt5_data import MT5Client, MT5ConnectionError

DAY = 86400


def make_client(fake, suffix=""):
    return MT5Client(fake, login=12345, password="pw", server="Demo-Server", symbol_suffix=suffix)


def test_connect_succeeds_and_marks_healthy():
    fake = FakeMT5()
    client = make_client(fake)
    client.connect()
    assert client.is_healthy() is True


def test_connect_raises_on_initialize_failure():
    fake = FakeMT5()
    fake._fail_init = True
    client = make_client(fake)
    with pytest.raises(MT5ConnectionError, match="initialize"):
        client.connect()


def test_connect_raises_on_login_failure():
    fake = FakeMT5()
    fake._fail_login = True
    client = make_client(fake)
    with pytest.raises(MT5ConnectionError, match="login"):
        client.connect()


def test_is_healthy_false_before_connecting():
    client = make_client(FakeMT5())
    assert client.is_healthy() is False


def test_is_healthy_false_when_terminal_reports_disconnected():
    fake = FakeMT5()
    client = make_client(fake)
    client.connect()
    fake.terminal_connected = False
    assert client.is_healthy() is False


def test_broker_symbol_appends_the_configured_suffix():
    client = make_client(FakeMT5(), suffix=".a")
    assert client.broker_symbol("EURUSD") == "EURUSD.a"


def test_broker_symbol_with_no_suffix_configured():
    client = make_client(FakeMT5(), suffix="")
    assert client.broker_symbol("EURUSD") == "EURUSD"


def test_fetch_candles_converts_rows_and_sorts_oldest_first():
    # Row 0 is the still-forming current bar (real MT5 convention) --
    # fetch_candles must skip it and return only the closed ones after it.
    fake = FakeMT5()
    fake.rates_by_symbol_timeframe[("EURUSD", "H1")] = [
        make_rate(4 * DAY, 1.12, 1.14, 1.11, 1.13),  # forming, must not appear below
        make_rate(2 * DAY, 1.10, 1.12, 1.09, 1.11),
        make_rate(3 * DAY, 1.11, 1.13, 1.10, 1.12),
    ]
    client = make_client(fake)
    candles = client.fetch_candles("EURUSD", "H1", count=2)
    assert len(candles) == 2
    assert candles[0].time < candles[1].time
    assert candles[0].close == 1.11
    assert candles[1].open == 1.11


def test_fetch_candles_skips_the_still_forming_bar_via_start_offset():
    # copy_rates_from_pos is called with start=1 -- this test verifies
    # that convention by checking the fake only serves rows[1:], i.e.
    # index 0 (the forming bar) is never included in what fetch_candles returns.
    fake = FakeMT5()
    forming = make_rate(3 * DAY, 999, 999, 999, 999)  # would stick out if it leaked through
    fake.rates_by_symbol_timeframe[("EURUSD", "H1")] = [
        forming, make_rate(2 * DAY, 1.10, 1.12, 1.09, 1.11),
    ]
    client = make_client(fake)
    candles = client.fetch_candles("EURUSD", "H1", count=5)
    assert all(c.close != 999 for c in candles)


def test_fetch_candles_raises_on_unknown_symbol():
    client = make_client(FakeMT5())
    with pytest.raises(MT5ConnectionError):
        client.fetch_candles("NOTREAL", "H1")


def test_fetch_candles_rejects_an_unsupported_granularity():
    client = make_client(FakeMT5())
    with pytest.raises(ValueError):
        client.fetch_candles("EURUSD", "M15")


def test_new_candle_closed_returns_it_once_then_none_until_a_new_one_appears():
    fake = FakeMT5()
    fake.rates_by_symbol_timeframe[("EURUSD", "H1")] = [
        make_rate(1 * DAY, 1.09, 1.10, 1.08, 1.09),
        make_rate(2 * DAY, 1.10, 1.12, 1.09, 1.11),
    ]
    client = make_client(fake)

    first = client.new_candle_closed("EURUSD", "H1")
    assert first is not None
    assert first.close == 1.11

    again = client.new_candle_closed("EURUSD", "H1")
    assert again is None  # same data, nothing new

    fake.rates_by_symbol_timeframe[("EURUSD", "H1")].append(make_rate(3 * DAY, 1.11, 1.13, 1.10, 1.12))
    fresh = client.new_candle_closed("EURUSD", "H1")
    assert fresh is not None
    assert fresh.close == 1.12


def test_account_state_builds_balance_equity_and_open_positions():
    fake = FakeMT5()
    fake.account.balance = 108288.79
    fake.account.equity = 107500.0
    fake.positions = [make_position(1, "EURUSD", price_open=1.1737, sl=1.1729, volume=1.25)]
    fake.symbols["EURUSD"] = make_symbol_info(trade_tick_value=1.0, trade_tick_size=0.0001)
    client = make_client(fake)
    client.connect()

    state = client.account_state(day_start_balance=105288.79, phase_start_balance=100000.0)
    assert state.balance == 108288.79
    assert state.equity == 107500.0
    assert state.day_start_balance == 105288.79
    assert len(state.open_positions) == 1
    pos = state.open_positions[0]
    assert pos.ticket == 1
    assert pos.instrument == "EURUSD"
    # |1.1737 - 1.1729| / 0.0001 * 1.0 * 1.25 = 8 pips * $1/pip * 1.25 lots = $10
    assert pos.risk_amount == pytest.approx(10.0)


def test_account_state_raises_when_account_info_unavailable():
    fake = FakeMT5()
    fake.account = None
    client = make_client(fake)
    with pytest.raises(MT5ConnectionError):
        client.account_state(day_start_balance=100000.0, phase_start_balance=100000.0)


def test_position_risk_falls_back_to_notional_exposure_when_stop_is_zero():
    # A position with no stop set should never read as zero risk -- that
    # would let the aggregate-risk gate silently ignore real exposure.
    fake = FakeMT5()
    fake.positions = [make_position(2, "XAUUSD", price_open=2000.0, sl=0, volume=0.1)]
    fake.symbols["XAUUSD"] = make_symbol_info(trade_contract_size=100.0)
    client = make_client(fake)
    client.connect()
    state = client.account_state(day_start_balance=100000.0, phase_start_balance=100000.0)
    pos = state.open_positions[0]
    assert pos.risk_amount == pytest.approx(0.1 * 2000.0 * 100.0)


def test_fetch_closed_deal_returns_the_exit_deal_reporting_a_stop_hit():
    fake = FakeMT5()
    fake.deals_by_position[42] = (
        make_deal(entry=fake.DEAL_ENTRY_IN, price=1.1737, profit=0.0, reason=0),
        make_deal(entry=fake.DEAL_ENTRY_OUT, price=1.1729, profit=-1000.0, reason=fake.DEAL_REASON_SL),
    )
    client = make_client(fake)
    deal = client.fetch_closed_deal(42)
    assert deal is not None
    assert deal.price == 1.1729
    assert deal.profit == -1000.0
    assert deal.reason == "stop_hit"


def test_fetch_closed_deal_reports_a_target_hit():
    fake = FakeMT5()
    fake.deals_by_position[43] = (
        make_deal(entry=fake.DEAL_ENTRY_OUT, price=1.1826, profit=3000.0, reason=fake.DEAL_REASON_TP),
    )
    client = make_client(fake)
    deal = client.fetch_closed_deal(43)
    assert deal.reason == "target_hit"


def test_fetch_closed_deal_returns_none_when_no_history_found_yet():
    client = make_client(FakeMT5())
    assert client.fetch_closed_deal(999) is None


def test_fetch_closed_deal_returns_none_when_only_an_entry_deal_exists_no_exit_yet():
    fake = FakeMT5()
    fake.deals_by_position[44] = (make_deal(entry=fake.DEAL_ENTRY_IN, price=1.1737, profit=0.0, reason=0),)
    client = make_client(fake)
    assert client.fetch_closed_deal(44) is None
