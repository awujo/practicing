"""
The live loop. Ties together everything else in bot/: on every new H1
candle close for a tracked instrument, refresh that instrument's cache
from MT5, call run_backtest() (unmodified -- see live_cache_sync.py for
why), and if it produced a fresh signal at that exact candle, run it
through the risk manager and, if allowed, place it.

Every method that touches MT5 (via the injected mt5_client/mt5_exec) can
fail -- this loop is written to fail CLOSED throughout: a health check
failure, a data fetch failure, or an execution failure all result in "do
nothing new this iteration," never "assume the last known state is still
good and proceed." A live account with real money does not get the
benefit of the doubt a backtest does.

Position-close outcome reconciliation (matching a ticket that's no longer
in positions_get() back to its realized P&L via MT5's trade history) is
intentionally the SIMPLEST piece here -- it's the one part of this whole
module I have the least confidence is exactly right without testing
against a real account's actual history_deals_get() behavior, and I'd
rather say that plainly than paper over it with untested precision.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone

from backtest.engine.runner import run_backtest
from backtest.engine.trade_log import TradeRecord

from .audit_log import AuditLog, DecisionRecord
from .config import AccountProfile
from .live_cache_sync import sync_recent_from_mt5
from .live_strategy import HUNTING, HTFContext, build_htf_context, storyline_at
from .mt5_data import MT5Client, MT5ConnectionError
from .mt5_execution import MT5Execution
from .risk_manager import Decision, RiskManager

logger = logging.getLogger("bot.orchestrator")


@dataclass
class TrackedPosition:
    row_id: int              # audit_log row for this trade's entry, to fill in the outcome later
    instrument: str
    ticket: int
    risk_amount: float
    entry_price: float


@dataclass
class LiveBot:
    profile: AccountProfile
    mt5_client: MT5Client
    mt5_exec: MT5Execution
    audit_log: AuditLog
    instruments: tuple[str, ...]
    entry_style: str = "conservative"
    source: str = "dukascopy"

    risk_manager: RiskManager = field(init=False)
    day_start_balance: float = field(init=False)
    phase_start_balance: float = field(init=False)
    today: object = field(init=False, default=None)
    tracked_positions: dict[tuple[str, int], TrackedPosition] = field(init=False, default_factory=dict)
    halted: bool = field(init=False, default=False)
    # Cached Weekly/Daily/H4 bias context per instrument, plus the last
    # storyline stage logged for it -- see _storyline_says_hunt().
    _htf_contexts: dict[str, HTFContext] = field(init=False, default_factory=dict)
    _storyline_stage: dict[str, str] = field(init=False, default_factory=dict)
    # Untracked-position tickets already warned about, so the warning
    # fires on discovery rather than every poll for as long as it's open.
    _reported_untracked: set = field(init=False, default_factory=set)

    def __post_init__(self):
        self.risk_manager = RiskManager(self.profile.active_rules, self.profile.terminates_on_dd)
        self.phase_start_balance = self.profile.starting_balance
        self.day_start_balance = self.profile.starting_balance

    def _roll_day_if_needed(self, state):
        today = datetime.now(timezone.utc).date()
        if self.today != today:
            self.today = today
            self.day_start_balance = state.balance

    def _account_state(self):
        return self.mt5_client.account_state(self.day_start_balance, self.phase_start_balance)

    def run_once(self):
        """One iteration -- call this on a short poll loop (a few seconds).
        Cheap when nothing has happened (a handful of MT5 calls); the
        expensive part (run_backtest) only runs on an actual new candle
        close per instrument, not every iteration."""
        if not self.mt5_client.is_healthy():
            self._try_reconnect()
            return  # fail closed -- do nothing else this iteration

        try:
            state = self._account_state()
        except MT5ConnectionError as exc:
            logger.warning("account_state fetch failed, skipping this iteration: %s", exc)
            return

        self._roll_day_if_needed(state)
        self._reconcile_closed_positions(state)

        health = self.risk_manager.check_health(state)
        if health is not None:
            if not self.halted:
                self.halted = True
                self._log_event("health_halt", health.decision.value, health.reason, state)
                logger.error("HALTED: %s", health.reason)
            return
        elif self.halted:
            self.halted = False  # equity recovered above the limit on its own -- log the all-clear implicitly via the next normal decision

        for instrument in self.instruments:
            try:
                self._check_instrument(instrument, state)
            except Exception:
                # Confirmed live: an uncaught exception anywhere in one
                # instrument's check (e.g. a cache/data edge case) used to
                # kill the entire process -- including every OTHER
                # instrument's checks and all future iterations. One bad
                # instrument must degrade to "skip it this iteration," not
                # take the whole live bot down.
                logger.exception("unexpected error checking %s -- skipping this instrument this iteration",
                                  instrument)

    def _check_instrument(self, instrument: str, state):
        try:
            new_candle = self.mt5_client.new_candle_closed(instrument, "H1")
        except MT5ConnectionError as exc:
            logger.warning("new_candle_closed(%s) failed: %s", instrument, exc)
            return
        if new_candle is None:
            return

        try:
            sync_recent_from_mt5(self.mt5_client, instrument, source=self.source)
        except MT5ConnectionError as exc:
            logger.warning("cache sync failed for %s, skipping this candle: %s", instrument, exc)
            return

        # The storyline gate -- see live_strategy.py. Running the full
        # entry search on every instrument every hour is what buried the
        # VPS (OPERATIONS_LOG.md, 2026-08-26); a manual trader doesn't
        # re-analyse a pair whose Daily and 4H haven't aligned yet, and
        # neither should this. Costs well under a millisecond, versus
        # tens of seconds for the run_backtest() below, and is tested to
        # never suppress a signal run_backtest() would have produced.
        if not self._storyline_says_hunt(instrument, new_candle.time):
            return

        records = run_backtest(instrument, self.entry_style, source=self.source)
        fresh = [r for r in records if r.entry_time == new_candle.time and r.status != "still_open"]
        for record in fresh:
            self._consider_entry(instrument, record, state)

    def _storyline_says_hunt(self, instrument: str, as_of_time) -> bool:
        """Is this instrument in the hunting stage (Daily and H4 aligned,
        higher-timeframe bias agreeing) at `as_of_time`?

        The Weekly/Daily/H4 context this reads only changes when one of
        THOSE timeframes closes, so it's cached per instrument and rebuilt
        only then -- roughly 7 times a day rather than the 24 full
        run_backtest() calls it replaces. H4 counts as a rebuild trigger
        because the Daily cascade's flip test consumes H4 confirmations
        (see live_strategy.needs_rebuild)."""
        closed = {}
        for granularity in ("W", "D", "H4"):
            try:
                closed[granularity] = self.mt5_client.new_candle_closed(instrument, granularity)
            except MT5ConnectionError as exc:
                logger.warning("new_candle_closed(%s, %s) failed: %s", instrument, granularity, exc)
                closed[granularity] = None

        ctx = self._htf_contexts.get(instrument)
        if ctx is None or any(c is not None for c in closed.values()):
            ctx = build_htf_context(instrument, source=self.source)
            if ctx is None:
                logger.debug("%s: no higher-timeframe structure to bootstrap a bias from", instrument)
                self._htf_contexts.pop(instrument, None)
                return False
            self._htf_contexts[instrument] = ctx

        storyline = storyline_at(ctx, as_of_time)
        previous = self._storyline_stage.get(instrument)
        if storyline.stage != previous:
            # Only log the transition, not every hour it stays put --
            # this is the "red flag" list becoming visible in the log.
            logger.info("%s: %s -- %s", instrument, storyline.stage, storyline.reason)
            self._storyline_stage[instrument] = storyline.stage
        return storyline.stage == HUNTING

    def _consider_entry(self, instrument: str, record: TradeRecord, state):
        risk = self.risk_manager.risk_for_next_trade(state)
        decision = self.risk_manager.check_new_entry(state)

        base_fields = _audit_fields_from_trade_record(record)
        if decision.decision != Decision.ALLOW:
            self._log_event("entry_attempt", decision.decision.value, decision.reason, state,
                             instrument=instrument, trade_id=str(record.trade_id), risk=risk, **base_fields)
            return

        sizing = self.mt5_exec.compute_lot_size(instrument, risk, record.entry_price, record.stop_loss)
        if not sizing.ok:
            self._log_event("entry_attempt", "decline_sizing_" + sizing.error.value, sizing.reason, state,
                             instrument=instrument, trade_id=str(record.trade_id), risk=risk, **base_fields)
            return

        result = self.mt5_exec.place_market_order(instrument, record.direction.value if hasattr(record.direction, "value") else record.direction,
                                                    sizing.lot_size, record.entry_price, record.stop_loss, record.primary_target)
        row_id = self._log_event(
            "entry_attempt", "allow" if result.success else "execution_failed",
            "placed" if result.success else result.reason, state,
            instrument=instrument, trade_id=str(record.trade_id), risk=risk,
            requested_price=result.requested_price, filled_price=result.filled_price,
            slippage_points=result.slippage_points, **base_fields,
        )
        if result.success:
            self.tracked_positions[(instrument, result.ticket)] = TrackedPosition(
                row_id=row_id, instrument=instrument, ticket=result.ticket,
                risk_amount=risk, entry_price=result.filled_price or record.entry_price,
            )

    def _reconcile_closed_positions(self, state):
        """Best-effort: anything we're tracking that's no longer in MT5's
        open positions has closed. Getting its exact realized P&L needs
        mt5.history_deals_get(ticket=...) -- written per the documented
        API but NOT verified against a live account's actual return
        shape, which is exactly the kind of thing that needs real-account
        testing before this is trusted."""
        open_tickets = {p.ticket for p in state.open_positions}

        # Positions the account holds that this process didn't record.
        # The risk manager still counts them (it reads MT5's own position
        # report, not this bot's memory), so they are NOT invisible to
        # risk -- but nothing will ever log their outcome, and the bot
        # can't manage what it doesn't know it owns. Confirmed live on
        # 2026-08-26: three duplicate EURCAD positions opened by a retried
        # order_send whose confirmation had been lost, and the bot, having
        # been told the send failed, tracked none of them. Surfacing this
        # loudly is the backstop for anything that opens a position
        # without this loop knowing.
        untracked = open_tickets - {ticket for _, ticket in self.tracked_positions}
        if untracked != self._reported_untracked:
            for ticket in sorted(untracked - self._reported_untracked):
                logger.warning(
                    "position %s is open on the account but NOT tracked by this process -- its "
                    "outcome will not be recorded. Check for a duplicate/orphaned order.", ticket)
            self._reported_untracked = set(untracked)

        closed = [key for key in self.tracked_positions if key[1] not in open_tickets]
        for key in closed:
            tracked = self.tracked_positions.pop(key)
            self._record_closed_trade(tracked, state)

    def _record_closed_trade(self, tracked: TrackedPosition, state):
        deal = self.mt5_client.fetch_closed_deal(tracked.ticket)
        if deal is None:
            logger.warning("could not find closed-deal info for ticket %s (%s) -- outcome not recorded",
                            tracked.ticket, tracked.instrument)
            return
        r_multiple = deal.profit / tracked.risk_amount if tracked.risk_amount else None
        self.audit_log.update_outcome(tracked.row_id, exit_price=deal.price,
                                       exit_reason=deal.reason, r_multiple=r_multiple,
                                       realized_pnl=deal.profit)
        if self.risk_manager.check_target_hit(state):
            self.risk_manager.accepting_entries = False
            self._log_event("phase_transition", "phase_target_hit",
                             f"balance {state.balance:,.2f} reached the phase target", state)

    def _try_reconnect(self):
        try:
            self.mt5_client.connect()
            logger.info("reconnected to MT5")
        except MT5ConnectionError as exc:
            logger.warning("reconnect failed: %s", exc)

    def _log_event(self, event_type, decision, reason, state, instrument="", trade_id="", risk=0.0,
                    requested_price=None, filled_price=None, slippage_points=None, **kwargs) -> int:
        open_risk = sum(p.risk_amount for p in state.open_positions)
        record = DecisionRecord(
            event_type=event_type, decision=decision, reason=reason,
            instrument=instrument, trade_id=trade_id, risk_amount=risk,
            requested_price=requested_price, filled_price=filled_price, slippage_points=slippage_points,
            phase=self.profile.active_phase or "personal",
            balance=state.balance, equity=state.equity,
            day_start_balance=state.day_start_balance, phase_start_balance=state.phase_start_balance,
            open_positions_count=len(state.open_positions), open_risk_total=open_risk,
            **kwargs,
        )
        return self.audit_log.append(record)


def _audit_fields_from_trade_record(record: TradeRecord) -> dict:
    """Pulls the strategy feature-context fields off a TradeRecord into
    the flat kwargs DecisionRecord/AuditLog expects -- kept as a plain
    function (not a method) since it's a pure data-shape translation with
    no orchestrator state involved."""
    def _s(value):
        return value.value if hasattr(value, "value") else (value or "")

    return dict(
        direction=_s(record.direction), entry_timeframe=record.entry_timeframe,
        entry_price=record.entry_price, entry_pattern=record.entry_pattern,
        trade_kind=record.trade_kind, trigger_type=record.trigger_type,
        bias_monthly=_s(record.bias_monthly), bias_weekly=_s(record.bias_weekly),
        bias_daily=_s(record.bias_daily), bias_h4=_s(record.bias_h4), bias_h1=_s(record.bias_h1),
        effective_bias_timeframe=record.effective_bias_timeframe or "",
        aligned_timeframes=record.aligned_timeframes,
        key_level_price=record.key_level_price, key_level_shape=record.key_level_shape,
        ranking_score=record.ranking_score, stop_loss=record.stop_loss, stop_kind=record.stop_kind,
        primary_target=record.primary_target, erl_price=record.erl_price, erl_capped=record.erl_capped,
    )
