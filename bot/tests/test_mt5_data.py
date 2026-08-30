import pandas as pd
import pytest

from .fake_mt5 import FakeMT5, make_rate, make_position, make_symbol_info, make_deal
from ..mt5_data import MT5Client, MT5ConnectionError

DAY = 86400


def make_client(fake, suffix="", overrides=None):
    # Pinned to 0 so these fixtures stay independent of the broker-clock
    # offset detection (see the dedicated server_utc_offset tests below) --
    # candle-conversion/sorting behavior shouldn't need an M1 fixture too.
    return MT5Client(fake, login=12345, password="pw", server="Demo-Server",
                      symbol_suffix=suffix, symbol_overrides=overrides,
                      server_utc_offset=pd.Timedelta(0))


def test_connect_succeeds_and_marks_healthy():
    fake = FakeMT5()
    client = make_client(fake)
    client.connect()
    assert client.is_healthy() is True


def test_connect_with_no_terminal_path_calls_initialize_with_no_args():
    fake = FakeMT5()
    client = make_client(fake)
    client.connect()
    assert fake.initialize_path is None


def test_connect_passes_terminal_path_through_to_initialize():
    # Required when more than one MT5 install shares a single Wine
    # prefix/mt5linux bridge (e.g. two portable accounts on the same VPS)
    # -- without this, initialize() falls back to whatever terminal MT5
    # finds by default, silently connecting to the WRONG account.
    fake = FakeMT5()
    client = MT5Client(fake, login=12345, password="pw", server="Demo-Server",
                        terminal_path=r"C:\MT5-Aggressive\terminal64.exe")
    client.connect()
    assert fake.initialize_path == r"C:\MT5-Aggressive\terminal64.exe"


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


# ---- broker server-clock offset (MT5 reports candle times in the
# broker's own server clock, e.g. EET/EEST, not true UTC -- confirmed
# live, MetaQuotes-Demo runs ~3 hours ahead of real UTC) ----

def test_detect_server_utc_offset_rounds_to_the_nearest_hour():
    fake = FakeMT5()
    # M1 forming-candle open time reported by the broker: 09:00:00.
    fake.rates_by_symbol_timeframe[("EURUSD", "M1")] = [make_rate(9 * 3600, 1, 1, 1, 1)]
    client = MT5Client(fake, login=1, password="pw", server="Demo")  # offset NOT pinned

    # 06:14 real UTC -> 2h46m raw gap, which rounds to the nearest hour (3h).
    real_now = pd.Timestamp(6 * 3600 + 14 * 60, unit="s", tz="UTC")
    offset = client._detect_server_utc_offset("EURUSD", real_now=real_now)
    assert offset == pd.Timedelta(hours=3)


def test_detect_server_utc_offset_rejects_a_stale_weekend_candle(monkeypatch):
    # Confirmed live 2026-08-30: called during a weekend closure,
    # rates[0] isn't genuinely forming -- it's the last bar before
    # Friday's close, many hours stale. The raw comparison against real
    # "now" then produces a wildly wrong delta, which used to get
    # silently applied to every subsequent candle timestamp. Real broker
    # offsets are always within a couple hours of UTC; this must reject
    # anything implausible rather than adopt it.
    fake = FakeMT5()
    # Friday 20:00 UTC "forming" candle (really just the last one before close).
    fake.rates_by_symbol_timeframe[("XAUUSD", "M1")] = [make_rate(4 * DAY + 20 * 3600, 1, 1, 1, 1)]
    client = MT5Client(fake, login=1, password="pw", server="Demo")  # offset NOT pinned

    # Saturday 10:00 UTC real time -- 14h after that stale candle.
    real_now = pd.Timestamp(5 * DAY + 10 * 3600, unit="s", tz="UTC")
    with pytest.raises(MT5ConnectionError, match="outside the plausible"):
        client._detect_server_utc_offset("XAUUSD", real_now=real_now)


def test_fetch_candles_fails_closed_rather_than_apply_an_implausible_offset(monkeypatch):
    # Same scenario, exercised through fetch_candles() -- the real call
    # path. Must raise, not silently return candles timestamped with a
    # garbage offset.
    fake = FakeMT5()
    fake.rates_by_symbol_timeframe[("XAUUSD", "M1")] = [make_rate(4 * DAY + 20 * 3600, 1, 1, 1, 1)]
    fake.rates_by_symbol_timeframe[("XAUUSD", "H1")] = [
        make_rate(4 * DAY + 20 * 3600, 1, 1, 1, 1),  # forming, skipped
        make_rate(4 * DAY + 19 * 3600, 1, 1, 1, 1),
    ]
    client = MT5Client(fake, login=1, password="pw", server="Demo")
    monkeypatch.setattr(pd.Timestamp, "now",
                         classmethod(lambda cls, tz=None: pd.Timestamp(5 * DAY + 10 * 3600, unit="s", tz=tz)))

    with pytest.raises(MT5ConnectionError, match="outside the plausible"):
        client.fetch_candles("XAUUSD", "H1", count=1)


def test_fetch_candles_auto_detects_and_applies_the_offset_when_not_pinned(monkeypatch):
    fake = FakeMT5()
    # M1 (offset detection) and H1 candle both dated on day 2, matching
    # the mocked "now" below -- a real MT5 connection fetches both from
    # the same broker at the same real moment, so a self-consistent
    # timeline here is what actually reflects production, not a gap
    # across days. (A previous version of this test had the M1 read on
    # day 0 while the H1 candle it offset-corrected landed on day 2 --
    # harmless before fetch_candles() started rejecting future-dated
    # candles against real "now", but that same day of the H1 candle
    # jump made it look like a future candle once fetch_candles() has
    # its own real-now to compare against.)
    fake.rates_by_symbol_timeframe[("EURUSD", "M1")] = [make_rate(2 * DAY + 9 * 3600, 1, 1, 1, 1)]
    fake.rates_by_symbol_timeframe[("EURUSD", "H1")] = [
        make_rate(4 * DAY, 1.12, 1.14, 1.11, 1.13),  # forming, skipped
        make_rate(2 * DAY + 9 * 3600, 1.10, 1.12, 1.09, 1.11),  # broker-labeled 09:00 on day 2
    ]
    client = MT5Client(fake, login=1, password="pw", server="Demo")  # offset NOT pinned
    monkeypatch.setattr(pd.Timestamp, "now",
                         classmethod(lambda cls, tz=None: pd.Timestamp(2 * DAY + 6 * 3600, unit="s", tz=tz)))

    candles = client.fetch_candles("EURUSD", "H1", count=1)
    assert len(candles) == 1
    # 3-hour offset subtracted: broker-labeled 09:00 on day 2 -> real 06:00 on day 2.
    assert candles[0].time == pd.Timestamp(2 * DAY + 6 * 3600, unit="s", tz="UTC")


def test_fetch_candles_drops_a_future_dated_candle_mt5_reports_as_closed(monkeypatch, caplog):
    # Confirmed live 2026-08-30: leftover corruption from the (now
    # separately fixed) weekend server-clock-offset bug had already
    # written candles ~42h into the future into the on-disk cache for 20
    # of 25 instruments before that fix landed -- and once one exists
    # there, cache.append()'s dedupe-by-exact-timestamp means it's never
    # naturally overwritten, so new_candle_closed() never sees anything
    # as "newer" again. A CLOSED candle (this method explicitly skips
    # the still-forming one) can never legitimately be timestamped after
    # "now", regardless of which bug produced one -- this is deliberately
    # independent of the offset-plausibility check above, so it also
    # catches a future timestamp from any OTHER source.
    fake = FakeMT5()
    fake.rates_by_symbol_timeframe[("EURUSD", "H1")] = [
        make_rate(2 * DAY - 3600, 1.10, 1.12, 1.09, 1.11),          # forming, skipped (start=1)
        make_rate(2 * DAY, 1.10, 1.12, 1.09, 1.11),                 # real
        make_rate(2 * DAY + 42 * 3600, 1.10, 1.12, 1.09, 1.11),     # bogus, ~42h in the future
    ]
    client = MT5Client(fake, login=1, password="pw", server="Demo",
                        server_utc_offset=pd.Timedelta(0))  # offset pinned -- isolate this check
    monkeypatch.setattr(pd.Timestamp, "now",
                         classmethod(lambda cls, tz=None: pd.Timestamp(2 * DAY, unit="s", tz=tz)))

    with caplog.at_level("WARNING", logger="bot.mt5_data"):
        candles = client.fetch_candles("EURUSD", "H1", count=2)

    assert len(candles) == 1
    assert candles[0].time == pd.Timestamp(2 * DAY, unit="s", tz="UTC")
    assert any("dropped 1 future-dated candle" in r.getMessage() for r in caplog.records)


def test_fetch_candles_only_detects_the_offset_once_and_caches_it(monkeypatch):
    fake = FakeMT5()
    fake.rates_by_symbol_timeframe[("EURUSD", "M1")] = [make_rate(9 * 3600, 1, 1, 1, 1)]
    fake.rates_by_symbol_timeframe[("EURUSD", "H1")] = [make_rate(2 * DAY, 1.1, 1.1, 1.1, 1.1)]
    client = MT5Client(fake, login=1, password="pw", server="Demo")
    monkeypatch.setattr(pd.Timestamp, "now", classmethod(lambda cls, tz=None: pd.Timestamp(6 * 3600, unit="s", tz=tz)))

    client.fetch_candles("EURUSD", "H1", count=1)
    assert client._server_utc_offset == pd.Timedelta(hours=3)

    # Even if the broker's M1 candle changes (as it would minute to minute
    # in reality), a second fetch must NOT re-detect -- the cached value
    # from the first call stays in effect.
    fake.rates_by_symbol_timeframe[("EURUSD", "M1")] = [make_rate(0, 1, 1, 1, 1)]
    client.fetch_candles("EURUSD", "H1", count=1)
    assert client._server_utc_offset == pd.Timedelta(hours=3)


def test_connect_resets_an_auto_detected_offset_but_not_a_pinned_one():
    fake = FakeMT5()

    auto = MT5Client(fake, login=1, password="pw", server="Demo")
    auto._server_utc_offset = pd.Timedelta(hours=3)  # simulate a prior detection
    auto.connect()
    assert auto._server_utc_offset is None  # re-detects fresh next fetch -- could be a different server/DST now

    pinned = MT5Client(fake, login=1, password="pw", server="Demo", server_utc_offset=pd.Timedelta(hours=2))
    pinned.connect()
    assert pinned._server_utc_offset == pd.Timedelta(hours=2)  # caller's explicit value survives reconnect


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


def test_broker_symbol_override_takes_priority_over_suffix():
    client = make_client(FakeMT5(), suffix=".a", overrides={"NAS100": "USTEC"})
    assert client.broker_symbol("NAS100") == "USTEC"
    assert client.broker_symbol("EURUSD") == "EURUSD.a"
