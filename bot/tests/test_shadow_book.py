"""Tests for shadow_book.ShadowBook -- the paper-trading comparison tool.

Every test constructs candles directly and drives `.consider()`/
`.reconcile()` by hand; none of this touches MT5 or the real cache, which
is the point being tested as much as the fill/outcome logic itself: a
ShadowBook must never be able to reach the broker (it has no reference to
MT5Execution at all), and it must never touch the candle cache for an
instrument it isn't tracking anything for.
"""

from dataclasses import dataclass
from datetime import timedelta
from unittest.mock import patch

import pandas as pd
import pytest

from backtest.engine.structure import Direction
from backtest.engine.trade_log import TradeRecord
from bot.audit_log import AuditLog
from bot.shadow_book import ShadowBook


@dataclass(frozen=True)
class Bar:
    time: pd.Timestamp
    open: float = 0.0
    high: float = 0.0
    low: float = 0.0
    close: float = 0.0
    volume: float = 0.0


def _t(hour):
    return pd.Timestamp(f"2026-01-01T{hour:02d}:00:00Z")


def _record(entry_time=None, entry_price=1.1000, stop_loss=1.0990, target=1.1030,
            direction=Direction.BULLISH):
    return TradeRecord(
        trade_id=1, instrument="EURUSD", entry_time=entry_time or _t(0),
        signal_time=entry_time or _t(0), direction=direction,
        entry_price=entry_price, stop_loss=stop_loss, primary_target=target,
    )


@pytest.fixture
def book(tmp_path):
    b = ShadowBook(name="test", min_departure_r=0.0,
                    audit_log=AuditLog(str(tmp_path / "shadow.db")),
                    stale_cutoff=timedelta(hours=24))
    yield b
    b.audit_log.close()


def test_consider_starts_tracking_and_writes_a_db_row(book):
    record = _record()
    book.consider("EURUSD", record)
    assert ("EURUSD", record.entry_time) in book.trades
    rows = book.audit_log.recent(10)
    assert len(rows) == 1
    assert rows[0]["decision"] == "shadow_tracking"


def test_consider_is_idempotent_for_the_same_signal(book):
    record = _record()
    book.consider("EURUSD", record)
    book.consider("EURUSD", record)
    assert len(book.audit_log.recent(10)) == 1


def test_reconcile_does_not_touch_the_cache_for_an_untracked_instrument(book):
    with patch("bot.shadow_book.load_candles") as mock_load:
        book.reconcile("EURUSD", weekend=False)
    mock_load.assert_not_called()


def test_immediate_variant_fills_on_the_very_next_retest_touch(book):
    """min_departure_r=0.0: any touch back at entry counts as a fill,
    even one candle after the signal with no departure at all."""
    record = _record(entry_time=_t(0))
    book.consider("EURUSD", record)
    candles = [
        Bar(_t(0), high=1.1005, low=1.0998),                 # signal/trigger candle
        Bar(_t(1), high=1.1002, low=1.0999),                 # retraces straight to entry
    ]
    with patch("bot.shadow_book.load_candles", return_value=candles):
        book.reconcile("EURUSD", weekend=False)
    trade = book.trades[("EURUSD", _t(0))]
    assert trade.status == "filled"
    assert trade.fill_time == _t(1)


def test_departure_gated_variant_waits_for_1r_travel_before_counting_a_fill(tmp_path):
    book = ShadowBook(name="dep1", min_departure_r=1.0,
                       audit_log=AuditLog(str(tmp_path / "shadow_dep1.db")),
                       stale_cutoff=timedelta(hours=24))
    record = _record(entry_time=_t(0), entry_price=1.1000, stop_loss=1.0990)  # risk = 10 pips
    book.consider("EURUSD", record)
    candles = [
        Bar(_t(0), high=1.1005, low=1.0998),
        Bar(_t(1), high=1.1002, low=1.0999),   # touches entry but has NOT departed 1R (1.1010) yet
    ]
    with patch("bot.shadow_book.load_candles", return_value=candles):
        book.reconcile("EURUSD", weekend=False)
    assert book.trades[("EURUSD", _t(0))].status == "pending"

    candles.append(Bar(_t(2), high=1.1012, low=1.1008))   # departs past 1.1010
    candles.append(Bar(_t(3), high=1.1004, low=1.0999))   # now retraces back to entry
    with patch("bot.shadow_book.load_candles", return_value=candles):
        book.reconcile("EURUSD", weekend=False)
    trade = book.trades[("EURUSD", _t(0))]
    assert trade.status == "filled"
    assert trade.fill_time == _t(3)
    book.audit_log.close()


def test_filled_trade_that_later_stops_out_is_closed_loss(book):
    record = _record(entry_time=_t(0), entry_price=1.1000, stop_loss=1.0990, target=1.1030)
    book.consider("EURUSD", record)
    candles = [
        Bar(_t(0), high=1.1005, low=1.0998),
        Bar(_t(1), high=1.1002, low=1.0999),   # fills
        Bar(_t(2), high=1.1001, low=1.0985),   # stops out
    ]
    with patch("bot.shadow_book.load_candles", return_value=candles):
        book.reconcile("EURUSD", weekend=False)
    assert ("EURUSD", _t(0)) not in book.trades   # resolved trades are dropped from memory
    rows = book.audit_log.recent(1)
    assert rows[0]["exit_reason"] == "stop_hit"
    assert rows[0]["r_multiple"] == pytest.approx(-1.0)


def test_filled_trade_that_reaches_target_is_closed_win(book):
    record = _record(entry_time=_t(0), entry_price=1.1000, stop_loss=1.0990, target=1.1030)
    book.consider("EURUSD", record)
    candles = [
        Bar(_t(0), high=1.1005, low=1.0998),
        Bar(_t(1), high=1.1002, low=1.0999),   # fills
        Bar(_t(2), high=1.1032, low=1.1005),   # hits target
    ]
    with patch("bot.shadow_book.load_candles", return_value=candles):
        book.reconcile("EURUSD", weekend=False)
    rows = book.audit_log.recent(1)
    assert rows[0]["exit_reason"] == "target_hit"
    assert rows[0]["r_multiple"] == pytest.approx(3.0)


def test_signal_that_never_fills_expires_past_the_stale_cutoff(tmp_path):
    book = ShadowBook(name="test", min_departure_r=0.0,
                       audit_log=AuditLog(str(tmp_path / "shadow.db")),
                       stale_cutoff=timedelta(hours=2))
    record = _record(entry_time=_t(0), entry_price=1.1000, stop_loss=1.0990)
    book.consider("EURUSD", record)
    candles = [
        Bar(_t(0), high=1.0999, low=1.0995),
        Bar(_t(3), high=1.0999, low=1.0995),   # 3h later, never touched entry again
    ]
    with patch("bot.shadow_book.load_candles", return_value=candles):
        book.reconcile("EURUSD", weekend=False)
    assert ("EURUSD", _t(0)) not in book.trades
    rows = book.audit_log.recent(1)
    assert rows[0]["exit_reason"] == "expired_unfilled"
    book.audit_log.close()


def test_signal_still_pending_expires_at_the_weekend_cutoff(book):
    record = _record(entry_time=_t(0))
    book.consider("EURUSD", record)
    candles = [Bar(_t(0), high=1.0999, low=1.0995)]
    with patch("bot.shadow_book.load_candles", return_value=candles):
        book.reconcile("EURUSD", weekend=True)
    assert ("EURUSD", _t(0)) not in book.trades
    rows = book.audit_log.recent(1)
    assert "weekend" in rows[0]["reason"] or rows[0]["exit_reason"] == "expired_unfilled"


def test_target_reached_without_ever_filling_expires_as_cancelled(book):
    """80% of target achieved before ever coming back to entry -- would
    have been cancelled, matching the operator's own rule
    (setup_validity.TARGET_ACHIEVED_FRACTION), not counted as a trade."""
    record = _record(entry_time=_t(0), entry_price=1.1000, stop_loss=1.0990, target=1.1030)
    book.consider("EURUSD", record)
    candles = [
        Bar(_t(0), high=1.1005, low=1.0998),
        Bar(_t(1), high=1.1026, low=1.1010),   # 80% of the way to target, never dipped to entry
    ]
    with patch("bot.shadow_book.load_candles", return_value=candles):
        book.reconcile("EURUSD", weekend=False)
    assert ("EURUSD", _t(0)) not in book.trades
    rows = book.audit_log.recent(1)
    assert rows[0]["exit_reason"] == "expired_unfilled"


def test_cannot_reach_mt5_by_construction(book):
    """A ShadowBook holds no mt5_exec/mt5_client reference and has no
    method that accepts one -- the strongest guarantee available short of
    a type checker that it can never place, cancel or close anything."""
    assert not hasattr(book, "mt5_exec")
    assert not hasattr(book, "mt5_client")
