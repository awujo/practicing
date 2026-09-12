"""
Paper-trade an alternate `min_departure_r` alongside the real live
decision, on the exact signals `run_backtest()` already produced for the
real trade -- no extra `run_backtest()` call, so this adds no CPU cost to
the per-instrument replay budget the rest of this project has been
fighting to reduce (bot/OPERATIONS_LOG.md, 2026-09-11/12).

Motivation (operator, 2026-09-12): pushed back hard on requiring a full
1.0R travel before a limit order rests at all, from direct SLK experience
that a lot of real entries retrace on the very next candle, well under 1R.
Backtested numbers say the departure requirement wins on paper (see
sweep_departure.py and the 2026-09 log entries) -- but the operator does
not trust a backtest over their own experience, reasonably: a backtest's
own assumptions (H1 resolution, no intrabar sequencing) are exactly the
kind of thing a live comparison can catch that a backtest cannot. Direct
request: run the operator's own idea forward on REAL incoming candles,
store it exactly like a real trade (DB + Telegram), but NEVER touch MT5 --
"I never hit mt5 for a real trade because I'm finding it hard to believe
your numbers."

A ShadowBook is that: it watches the same signals the real bot acts on,
decides -- using the exact same `check_setup`-family logic, just with a
different min_departure_r -- whether ITS variant would have rested an
order, when it would have filled, and how it would have closed, and
writes that to its own SQLite db (via the same AuditLog/DecisionRecord
schema real trades use, so the two are directly comparable) and to the
same Telegram channel (via the normal "bot.*" logger hierarchy
telegram_notify.py already listens on), clearly tagged so it's never
mistaken for a real trade. It holds no reference to MT5Execution and
cannot place, cancel, or close anything -- there is no method here that
could.

Reuses `_resting_limit_outcome()` and `_resolve_trade_outcome()` from
backtest/engine/runner.py, the exact functions the backtest itself uses
to simulate a resting limit's fill and a filled trade's stop/target race,
rather than re-deriving that sequencing a second time with a fresh chance
to get the departed-then-revisited ordering subtly wrong (see
setup_validity.check_setup()'s own docstring for why that ordering is
easy to get wrong).

NOT modeled (documented rather than silently wrong): a shadow trade
already "filled" is not force-closed at the weekend flatten the way a
real position would be -- it keeps walking forward through Monday's
candles. Rare (weekly at most) and visible in the data (an open shadow
trade spanning a weekend gap), not hidden.
"""

import logging
from dataclasses import dataclass, field
from datetime import timedelta

from backtest.engine.candles import load_candles
from backtest.engine.runner import _resolve_trade_outcome, _resting_limit_outcome
from backtest.engine.trade_log import TradeRecord

from .audit_log import AuditLog, DecisionRecord
from .setup_validity import TARGET_ACHIEVED_FRACTION

logger = logging.getLogger("bot.shadow_book")


def _audit_fields_from_trade_record(record: TradeRecord) -> dict:
    """Duplicated from orchestrator.py's own free function of the same
    name rather than imported, to keep this module importable (and
    testable) without pulling in orchestrator.py's MT5-facing surface."""
    def _s(value):
        return value.value if hasattr(value, "value") else (value or "")

    return dict(
        entry_time=str(record.entry_time),
        direction=_s(record.direction), entry_timeframe=record.entry_timeframe,
        entry_price=record.entry_price, entry_pattern=record.entry_pattern,
        trigger_type=record.trigger_type,
        bias_monthly=_s(record.bias_monthly), bias_weekly=_s(record.bias_weekly),
        bias_daily=_s(record.bias_daily), bias_h4=_s(record.bias_h4), bias_h1=_s(record.bias_h1),
        effective_bias_timeframe=record.effective_bias_timeframe or "",
        aligned_timeframes=record.aligned_timeframes,
        key_level_price=record.key_level_price, key_level_shape=record.key_level_shape,
        ranking_score=record.ranking_score, stop_loss=record.stop_loss, stop_kind=record.stop_kind,
        primary_target=record.primary_target, erl_price=record.erl_price, erl_capped=record.erl_capped,
    )


@dataclass
class ShadowTrade:
    instrument: str
    signal_time: object
    direction: object
    entry_price: float
    stop_loss: float
    target: float
    row_id: int
    status: str = "pending"   # pending | filled
    fill_idx: int | None = None
    fill_time: object = None


def _r_multiple(entry_price, stop_loss, exit_price, direction) -> float:
    from backtest.engine.structure import Direction
    risk = abs(entry_price - stop_loss) or 1e-9
    signed = (exit_price - entry_price) if direction == Direction.BULLISH else (entry_price - exit_price)
    return signed / risk


@dataclass
class ShadowBook:
    """One paper-traded variant. `name` shows up in every log line and DB
    row so multiple variants (this bot's real behavior included) can be
    told apart at a glance."""
    name: str
    min_departure_r: float
    audit_log: AuditLog
    stale_cutoff: timedelta
    source: str = "dukascopy"
    trades: dict = field(default_factory=dict)   # (instrument, signal_time) -> ShadowTrade

    def consider(self, instrument: str, record: TradeRecord) -> None:
        """Start tracking a freshly-seen signal, if not already tracking it."""
        key = (instrument, record.entry_time)
        if key in self.trades:
            return
        base_fields = _audit_fields_from_trade_record(record)
        row_id = self.audit_log.append(DecisionRecord(
            event_type="entry_attempt", decision="shadow_tracking",
            reason=f"[shadow:{self.name}] signal seen, min_departure_r={self.min_departure_r} "
                   f"-- watching for the hypothetical fill, not placing anything",
            instrument=instrument, trade_id=str(record.trade_id), **base_fields,
        ))
        self.trades[key] = ShadowTrade(
            instrument=instrument, signal_time=record.entry_time, direction=record.direction,
            entry_price=record.entry_price, stop_loss=record.stop_loss,
            target=record.primary_target, row_id=row_id,
        )
        logger.info("[SHADOW:%s] %s: tracking new signal at %s (stop %s, target %s)",
                    self.name, instrument, record.entry_price, record.stop_loss, record.primary_target)

    def reconcile(self, instrument: str, weekend: bool) -> None:
        """Advance every trade of this instrument by whatever new candles
        have arrived since the last poll. Cheap no-op when nothing of
        this instrument is being tracked -- does not read the cache at
        all in that case."""
        active = [t for t in self.trades.values() if t.instrument == instrument]
        if not active:
            return
        try:
            h1 = load_candles(self.source, instrument, "H1")
        except (FileNotFoundError, OSError):
            return
        if not h1:
            return
        now = h1[-1].time
        index_by_time = {c.time: i for i, c in enumerate(h1)}

        for trade in active:
            if trade.status == "pending" and weekend:
                self._expire(trade, "weekend cutoff reached -- nothing would be left "
                                     "resting over the weekend")
                continue
            trigger_idx = index_by_time.get(trade.signal_time)
            if trigger_idx is None:
                continue  # this instrument's cache doesn't (yet) include the signal candle
            if trade.status == "pending":
                if now - trade.signal_time > self.stale_cutoff:
                    self._expire(trade, f"never filled within {self.stale_cutoff}")
                    continue
                self._advance_pending(trade, h1, trigger_idx)
            if trade.status == "filled":
                self._advance_filled(trade, h1)

    def _advance_pending(self, trade: ShadowTrade, h1, trigger_idx: int) -> None:
        max_lookahead = len(h1) - trigger_idx - 1
        if max_lookahead <= 0:
            return
        fill_idx, cancel_reason = _resting_limit_outcome(
            h1, trigger_idx, trade.entry_price, trade.stop_loss, trade.target,
            trade.direction, max_lookahead, TARGET_ACHIEVED_FRACTION,
            min_departure_r=self.min_departure_r,
        )
        if fill_idx is not None:
            trade.status = "filled"
            trade.fill_idx = fill_idx
            trade.fill_time = h1[fill_idx].time
            logger.info("[SHADOW:%s] %s: would have FILLED at %s on the candle closing %s",
                        self.name, trade.instrument, trade.entry_price, trade.fill_time)
        elif cancel_reason == "target_achieved_unfilled":
            self._expire(trade, "target reached without ever coming back to fill -- "
                                 "would have been cancelled, not taken")
        # "never_filled" (within the lookahead available so far) means
        # still waiting -- nothing to do until either more candles or the
        # stale cutoff above resolves it.

    def _advance_filled(self, trade: ShadowTrade, h1) -> None:
        outcome, exit_price, exit_time, mae_r, mfe_r = _resolve_trade_outcome(
            trade.entry_price, trade.stop_loss, trade.target, trade.direction, h1[trade.fill_idx:])
        if outcome == "still_open":
            return
        r_multiple = _r_multiple(trade.entry_price, trade.stop_loss, exit_price, trade.direction)
        status = "closed_win" if outcome == "target_hit" else "closed_loss"
        logger.info("[SHADOW:%s] %s: hypothetical trade closed %s at %s (%.2fR)",
                    self.name, trade.instrument, status, exit_price, r_multiple)
        self.audit_log.update_outcome(trade.row_id, exit_price=exit_price, exit_reason=outcome,
                                       r_multiple=r_multiple, realized_pnl=None,
                                       mae_r=mae_r, mfe_r=mfe_r)
        del self.trades[(trade.instrument, trade.signal_time)]

    def _expire(self, trade: ShadowTrade, reason: str) -> None:
        logger.info("[SHADOW:%s] %s: signal from %s expired -- %s",
                    self.name, trade.instrument, trade.signal_time, reason)
        self.audit_log.update_outcome(trade.row_id, exit_price=None, exit_reason="expired_unfilled",
                                       r_multiple=0.0, realized_pnl=0.0)
        del self.trades[(trade.instrument, trade.signal_time)]
