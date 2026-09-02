"""
The live loop. Ties together everything else in bot/: on every new H1
candle close for a tracked instrument, refresh that instrument's cache
from MT5, call run_backtest() (unmodified -- see live_cache_sync.py for
why), and act on whatever it produced since the last candle this
instrument was actually checked on -- see _check_instrument's own
docstring for why "since last checked" and not "at this exact candle."

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
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pandas as pd

from backtest.engine.candles import load_candles
from backtest.engine.runner import run_backtest
from backtest.engine.trade_log import TradeRecord

from .audit_log import AuditLog, DecisionRecord
from .config import AccountProfile
from .diagnostics import resource_snapshot
from .live_cache_sync import sync_recent_from_mt5
from .live_strategy import HUNTING, HTFContext, build_htf_context, storyline_at
from .mt5_data import MT5Client, MT5ConnectionError
from .mt5_execution import MT5Execution
from .risk_manager import Decision, OpenPosition, RiskManager
from .setup_validity import check_setup

logger = logging.getLogger("bot.orchestrator")

# Exponential backoff between actual reconnect attempts -- see
# _try_reconnect()'s docstring for why this exists. First retry is
# immediate (matches the old fixed-5s-forever behavior for a one-off
# blip); the delay only grows for a genuinely sustained outage.
RECONNECT_BACKOFF_BASE_SECONDS = 5
RECONNECT_BACKOFF_MAX_SECONDS = 60

# How far back _storyline_hunted_anywhere_in_gap() will replay the
# storyline gate when catching up after a skipped stretch. A real outage
# skips a handful of H1 candles at most (the worst measured one, 150/158
# failed reconnects, spanned under 15 minutes -- OPERATIONS_LOG.md); this
# is a defensive cap against a pathologically stale watermark, not a
# number the codebase has ever actually needed. 72 H1 candles = 3 days.
STORYLINE_GAP_LOOKBACK_CANDLES = 72

# How old a caught-up signal's own entry candle is allowed to be, versus
# the candle that just closed, before it's declined instead of traded.
# Confirmed live 2026-08-29: EURJPY's 16:00/17:00 UTC candles from the
# PREVIOUS day were still attempted as live market orders at 07:17 the
# NEXT day -- 14-15 hours after their entry/stop/target math was
# computed, against a materially different current price. The watermark-
# widening (2026-08-28) and storyline-gap-replay (2026-08-29) fixes both
# exist specifically so a missed signal is never silently dropped -- but
# "still report it" and "still trade it" are different things once
# enough time has passed that the setup's own thesis (the levels it was
# reacting to) may no longer hold. 3 hours = generous room for a real
# reconnect storm's recovery (the worst measured one resolved in
# minutes) while reliably excluding "yesterday afternoon." Direct
# 2026-08-29 request: "leave the trade if it have passed" -- declined,
# not silently dropped: still logged with the full reasoning, just
# tagged decline_stale_signal instead of executed.
STALE_ENTRY_CUTOFF = timedelta(hours=3)


# The weekend rule: nothing open and nothing resting when the market
# closes -- direct operator requirement 2026-09-02 ("we will not be
# leaving any trades over the weekend especially in the geopolitical
# situation"), the concern being gap risk over a closed weekend, which a
# stop-loss cannot protect against because there is no price to fill at.
#
# The broker closes with the New York exchange: 17:00 Friday, New York
# time. That is NOT a fixed UTC hour -- it is 21:00 UTC under EDT and
# 22:00 UTC under EST, so it must be computed in the New York zone and
# converted, or it is an hour wrong for half the year. zoneinfo carries
# the DST rules; hard-coding either number would be a bug twice a year.
WEEKEND_CLOSE_ZONE = ZoneInfo("America/New_York")
WEEKEND_CLOSE_WEEKDAY = 4       # Monday=0, so 4 = Friday
WEEKEND_CLOSE_LOCAL_HOUR = 17

# Flatten an hour before the close rather than at it. Spreads widen
# sharply into the Friday close (STRATEGY.md Section 8, and the measured
# 54-point GBPAUD slippage at rollover that avoid_rollover_entries exists
# for), and closing a position needs the market still open enough to fill
# -- leaving it to the last minute risks paying the worst spread of the
# week, or not getting out at all.
FLATTEN_MINUTES_BEFORE_CLOSE = 60

# Stop opening new trades well before that. A position opened at 16:00
# Friday that gets force-closed at 16:00 is closed by the clock rather
# than by its own stop or target -- it books whatever noise it happens to
# be sitting on, which is neither the strategy's edge nor its risk model.
# Four hours is a judgment call, not a measured number: long enough for a
# typical H1 setup to resolve, short enough not to write off Friday.
NO_NEW_ENTRIES_MINUTES_BEFORE_CLOSE = 240


@dataclass
class TrackedPosition:
    row_id: int              # audit_log row for this trade's entry, to fill in the outcome later
    instrument: str
    ticket: int
    risk_amount: float
    entry_price: float


@dataclass
class PendingEntry:
    """A limit order resting at its setup's entry level.

    Held separately from TrackedPosition because a resting order is not a
    position: it carries no risk until it fills, the risk manager must not
    count it as exposure, and it needs the setup's own numbers kept around
    so validity can be re-checked on later polls.
    """
    row_id: int
    instrument: str
    ticket: int
    risk_amount: float
    entry_price: float
    stop_loss: float
    target: float
    direction: object
    signal_time: object


@dataclass
class LiveBot:
    profile: AccountProfile
    mt5_client: MT5Client
    mt5_exec: MT5Execution
    audit_log: AuditLog
    instruments: tuple[str, ...]
    entry_style: str = "conservative"
    source: str = "dukascopy"
    # "market" (default, unchanged behavior) or "limit". Opt-in at the
    # wiring site, matching max_spread_points/max_entry_drift_fraction,
    # so enabling this is a deliberate act and every existing caller and
    # test keeps its previous behavior.
    entry_order_type: str = "market"

    risk_manager: RiskManager = field(init=False)
    day_start_balance: float = field(init=False)
    phase_start_balance: float = field(init=False)
    today: object = field(init=False, default=None)
    tracked_positions: dict[tuple[str, int], TrackedPosition] = field(init=False, default_factory=dict)
    # Limit orders currently resting, keyed the same way. In-memory only:
    # a restart loses the mapping but NOT the orders, which is why
    # _reconcile_pending_entries() reports anything resting at the broker
    # that this process doesn't recognise rather than assuming it owns
    # everything -- same stance as _reconcile_closed_positions() takes
    # for untracked positions.
    pending_entries: dict[tuple[str, int], PendingEntry] = field(init=False, default_factory=dict)
    halted: bool = field(init=False, default=False)
    # Cached Weekly/Daily/H4 bias context per instrument, plus the last
    # storyline stage logged for it -- see _storyline_says_hunt().
    _htf_contexts: dict[str, HTFContext] = field(init=False, default_factory=dict)
    _storyline_stage: dict[str, str] = field(init=False, default_factory=dict)
    # Untracked-position tickets already warned about, so the warning
    # fires on discovery rather than every poll for as long as it's open.
    _reported_untracked: set = field(init=False, default_factory=set)
    # The entry_time of the newest candle actually evaluated for entries,
    # per instrument -- see _check_instrument's docstring for why this
    # exists and what it fixes. Unset until the first real check for that
    # instrument in this process's lifetime, so a fresh process never
    # replays history (only a full process restart resets it; an
    # in-process reconnect does not).
    _last_entry_time: dict[str, object] = field(init=False, default_factory=dict)
    # instrument (H1) or "instrument:granularity" (storyline's W/D/H4
    # checks) keys currently in a new_candle_closed() failure state --
    # so a SUSTAINED failure (e.g. weekend market closure hitting the
    # server-offset plausibility check) logs ONCE for the whole outage,
    # not once per poll. Confirmed live 2026-08-30: ~2,800 Telegram
    # messages in 3 hours from this exact path with no dedup at all.
    # An earlier version of this dedup compared the failure MESSAGE
    # text instead of tracking failing/recovered state -- wrong, because
    # the offset-detection error text drifts roughly hourly (it's
    # derived from real-time "now", see mt5_data.py's docstring), and
    # since ~25 instruments' stale candles cluster within the same few
    # minutes of each other, that drift crossed all of their thresholds
    # within the same ~15-second window once an hour: still a 25-message
    # burst, still confirmed live as "still spamming." Tracking failing
    # vs. recovered state instead means one message per instrument per
    # OUTAGE (logged again only after a real recovery), regardless of
    # how the message text itself drifts while it's ongoing.
    _candle_error_active: set = field(init=False, default_factory=set)
    # Reconnect backoff state -- see _try_reconnect().
    _reconnect_attempts: int = field(init=False, default=0)
    _next_reconnect_at: object = field(init=False, default=None)

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
        # Before the health gate: resting orders must still be cancelled
        # when the setup dies or the weekend arrives even while halted --
        # a halt stops new entries, it does not license leaving orders
        # parked at the broker unattended.
        try:
            self._reconcile_pending_entries(state)
        except Exception:
            logger.exception("pending-order reconcile failed; continuing")

        # Flatten before the health gate too: a halt stops new entries, it
        # does not license carrying positions through a closed weekend.
        # Gap risk is exactly what a stop-loss cannot protect against --
        # there is no price to fill at until Monday.
        if self._weekend_is_close():
            try:
                self._flatten_for_weekend(state)
            except Exception:
                logger.exception("WEEKEND FLATTEN FAILED -- check the account by hand")

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

    def _log_candle_error_if_new(self, key: str, message: str):
        """Logs `message` at WARNING (and so to Telegram, see
        telegram_notify.py) only the FIRST time `key` enters a failure
        state -- not on every repeat of an ongoing one, and not again
        just because the message text drifted. See
        `_candle_error_active`'s comment for why text-based dedup
        wasn't enough."""
        if key not in self._candle_error_active:
            logger.warning(message)
            self._candle_error_active.add(key)

    def _clear_candle_error(self, key: str):
        self._candle_error_active.discard(key)

    def _check_instrument(self, instrument: str, state):
        """`mt5_client.new_candle_closed()` reports only the SINGLE most
        recently seen H1 bar -- see its own docstring -- not every bar
        that closed since the last successful call. If this instrument
        wasn't checked for a stretch (an MT5 reconnect storm, an
        unhealthy iteration, anything that makes run_once() return
        early), and TWO OR MORE H1 candles close in that stretch, only
        the newest is ever reported here. Matching entries against ONLY
        that one candle's time -- as this used to do -- means a real
        signal on any earlier candle in the gap is silently and
        permanently lost: no exception, no log line, no audit row,
        because _consider_entry() is never even called for it.

        Confirmed live 2026-08-27/28: 6 real signals across both bots (12
        rows in the reference feed, both entry styles), 0 reached either
        audit database -- coinciding with MT5 reconnect storms of
        150/158 failed re-authorizations in that window
        (bot/OPERATIONS_LOG.md has the detail). run_backtest() had them
        the whole time; every one of those calls just filtered on the
        wrong candle.

        So instead of matching the one candle that just closed, this
        matches everything since `_last_entry_time[instrument]` -- the
        newest candle actually evaluated last time -- up to and including
        this one.

        `_last_entry_time` itself lives only in memory, so a full process
        restart used to reset it to cold-start (exact-match-only,
        because matching "everything run_backtest() has ever produced"
        on a truly blank slate would replay every historical trade back
        to whenever the cache begins). Confirmed live 2026-08-30/31: a
        Dukascopy-reference comparison found 9 of 11 signals with ZERO
        trace in either audit database over a period that included
        several restarts -- a restart is exactly when a deploy happens,
        which is one of the most common times for this to bite. The
        watermark is no longer purely in-memory: if there's nothing
        cached for this instrument yet, `audit_log.last_entry_time()`
        reconstructs it from the most recent entry_attempt actually
        logged (durable, survives a restart) before falling back to a
        genuine cold start only when the audit database has never seen
        this instrument at all. An in-process reconnect never hit this
        gap in the first place -- `_last_entry_time` stays intact for
        those, this only ever changes what happens right after a fresh
        process start.

        The storyline gate itself has the same "only checked at the
        recovery candle" problem this method fixes for entries -- and it
        WAS confirmed live 2026-08-29: NZDUSD's 13:00 UTC candle passed
        the gate at the time, but the recovery poll after a reconnect
        storm (spanning that exact window) landed on a later candle where
        the gate had moved back to WAITING, so the whole entry search was
        skipped and the signal never had a chance to be found -- unlike
        the entry-matching bug above, there was no watermark to widen
        because run_backtest() was never even called.
        `_storyline_hunted_anywhere_in_gap()` closes this the same way:
        replay the (cheap) gate at every H1 candle since the watermark,
        not just the newest one."""
        try:
            new_candle = self.mt5_client.new_candle_closed(instrument, "H1")
        except MT5ConnectionError as exc:
            self._log_candle_error_if_new(instrument, f"new_candle_closed({instrument}) failed: {exc}")
            return
        self._clear_candle_error(instrument)
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
        # never suppress a signal run_backtest() would have produced --
        # AT the single instant it's asked about. See this method's own
        # docstring for why that's not the same as "since we last checked."
        watermark = self._last_entry_time.get(instrument)
        if watermark is None:
            persisted = self.audit_log.last_entry_time(instrument)
            if persisted is not None:
                watermark = pd.Timestamp(persisted)
        if not self._storyline_hunted_anywhere_in_gap(instrument, watermark, new_candle.time):
            return

        # avoid_rollover_entries=True: confirmed live 2026-08-31, a GBPAUD
        # entry at 22:00 UTC filled 54 points worse than requested (Market
        # Execution mode gives no slippage cap), turning $1,000 of intended
        # risk into a realized $1,530.32 loss -- exactly the risk
        # STRATEGY.md Section 8 already names ("spread widens sharply
        # around session rollover"). A 2026-09-01 A/B backtest over
        # 2025-2026 showed this window's signals are decent on paper
        # (+216.7R of the +2,668.2R total, ~8%) -- but that comparison
        # can't see the reason to skip it: the backtest has NO slippage
        # model at all, so it can't price in the exact execution risk this
        # flag exists to avoid. Live execution risk (demonstrated) wins
        # over an unmeasurable backtest opportunity cost (the simulation
        # structurally cannot validate either way), per direct instruction.
        # min_reward_r=1.0: direct 2026-09-01 question, "a trade of less
        # than 1R doesn't make sense to hold." A/B backtest over 2025-2026
        # confirmed it: the 65 trades this filter removes were net LOSERS
        # (-16.1R combined, 44.6% win rate vs. 51.7% overall) -- skipping
        # them raised total R (2,668.2 -> 2,684.3), win rate (51.7% ->
        # 51.9%), and avg R/trade (0.990 -> 1.020), all at once. Unlike
        # avoid_rollover_entries above, this isn't a safety-vs-opportunity
        # tradeoff -- it's a clean improvement the backtest can measure
        # directly (no slippage model needed to judge "is a sub-1R target
        # worth the risk").
        records = run_backtest(instrument, self.entry_style, source=self.source,
                                avoid_rollover_entries=True, min_reward_r=1.0)
        if watermark is None:
            fresh = [r for r in records if r.entry_time == new_candle.time]
        else:
            fresh = [r for r in records if watermark < r.entry_time <= new_candle.time]
        for record in fresh:
            staleness = new_candle.time - record.entry_time
            if staleness > STALE_ENTRY_CUTOFF:
                # See STALE_ENTRY_CUTOFF's own comment. Declined, not
                # silently dropped -- full reasoning still logged/audited,
                # just never reaches the risk manager or MT5.
                self._log_event(
                    "entry_attempt", "decline_stale_signal",
                    f"signal candle is {staleness} old (cutoff {STALE_ENTRY_CUTOFF}) -- "
                    f"market has likely moved past this level, not attempting it late",
                    state, instrument=instrument, trade_id=str(record.trade_id),
                    **_audit_fields_from_trade_record(record),
                )
                continue
            self._consider_entry(instrument, record, state)
        self._last_entry_time[instrument] = new_candle.time

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
            key = f"{instrument}:{granularity}"
            try:
                closed[granularity] = self.mt5_client.new_candle_closed(instrument, granularity)
                self._clear_candle_error(key)
            except MT5ConnectionError as exc:
                self._log_candle_error_if_new(
                    key, f"new_candle_closed({instrument}, {granularity}) failed: {exc}")
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
            # Direct 2026-08-30 request: "let me know if what's logged is
            # current candle and not some past candle" -- the line used to
            # say e.g. "Weekly/Daily/H4 aligned bullish" with no way to
            # tell whether each one was actually recent. Each timeframe's
            # OWN confirmation date is free here (already fetched by
            # storyline_at() to decide alignment in the first place).
            confirmed = [
                f"{tf}@{t}" for tf, t in (
                    ("Weekly", getattr(storyline, "weekly_confirmed_at", None)),
                    ("Daily", getattr(storyline, "daily_confirmed_at", None)),
                    ("H4", getattr(storyline, "h4_confirmed_at", None)),
                ) if t is not None
            ]
            suffix = f" ({', '.join(confirmed)})" if confirmed else ""
            logger.info("%s: %s -- %s%s", instrument, storyline.stage, storyline.reason, suffix)
            self._storyline_stage[instrument] = storyline.stage
        return storyline.stage == HUNTING

    def _storyline_hunted_anywhere_in_gap(self, instrument: str, watermark, new_candle_time) -> bool:
        """True if the storyline gate says HUNT at `new_candle_time`, OR
        said HUNT at any H1 candle strictly between `watermark` and
        `new_candle_time`. The gate is only ever cheap to check at a
        single instant; a gap wider than one candle means a poll was
        skipped (reconnect storm, unhealthy iteration -- same cause as
        _check_instrument's own watermark gap), and a signal whose OWN
        candle passed the gate can still be missed if the bias has since
        moved on by the time polling resumes. Confirmed live 2026-08-29:
        NZDUSD's 13:00 UTC candle passed the gate; the recovery poll
        landed on a later candle where it no longer did, so the whole
        entry search for that hour was skipped -- run_backtest() was
        never even called, so there was no watermark-widening left to
        catch it (unlike the bug _check_instrument's docstring covers).

        Checks `new_candle_time` FIRST -- the fast, common-case path,
        identical cost to before this existed. The gap replay below only
        runs when that single check comes back False AND there's an
        actual gap to replay, so steady-state polling pays nothing extra."""
        if self._storyline_says_hunt(instrument, new_candle_time):
            return True
        if watermark is None:
            return False
        try:
            h1 = load_candles(self.source, instrument, "H1")
        except FileNotFoundError:
            return False
        gap_candles = [c for c in h1 if watermark < c.time < new_candle_time]
        for c in gap_candles[-STORYLINE_GAP_LOOKBACK_CANDLES:]:
            if self._storyline_says_hunt(instrument, c.time):
                return True
        return False

    def _consider_entry(self, instrument: str, record: TradeRecord, state):
        risk = self.risk_manager.risk_for_next_trade(state)
        decision = self.risk_manager.check_new_entry(state)

        base_fields = _audit_fields_from_trade_record(record)

        if self._too_late_to_open():
            minutes = self._minutes_to_weekend_close()
            self._log_event("entry_attempt", "decline_weekend_close", state=state,
                             reason=f"{minutes:.0f} minutes to the Friday "
                                    f"{WEEKEND_CLOSE_LOCAL_HOUR}:00 New York close -- a trade "
                                    f"opened now would be flattened by the clock rather than "
                                    f"resolved on its own stop or target",
                             instrument=instrument, trade_id=str(record.trade_id),
                             risk=risk, **base_fields)
            return

        if decision.decision != Decision.ALLOW:
            self._log_event("entry_attempt", decision.decision.value, decision.reason, state,
                             instrument=instrument, trade_id=str(record.trade_id), risk=risk, **base_fields)
            return

        sizing = self.mt5_exec.compute_lot_size(instrument, risk, record.entry_price, record.stop_loss)
        if not sizing.ok:
            self._log_event("entry_attempt", "decline_sizing_" + sizing.error.value, sizing.reason, state,
                             instrument=instrument, trade_id=str(record.trade_id), risk=risk, **base_fields)
            return

        direction = record.direction.value if hasattr(record.direction, "value") else record.direction

        if self.entry_order_type == "limit":
            self._place_limit_entry(instrument, record, state, risk, sizing.lot_size,
                                     direction, base_fields)
            return

        result = self.mt5_exec.place_market_order(instrument, direction,
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

    def _candles_since(self, instrument: str, signal_time):
        """H1 candles that closed AFTER the signal candle, oldest first.

        Read from the same cache `sync_recent_from_mt5()` has just
        refreshed from MT5 in `_check_instrument()`, so these are live
        bars, not stale history.
        """
        try:
            h1 = load_candles(self.source, instrument, "H1")
        except FileNotFoundError:
            return []
        return [c for c in h1 if c.time > signal_time]

    def _place_limit_entry(self, instrument, record, state, risk, lot_size,
                            direction, base_fields):
        """Rest a limit at the setup's own entry level, once the setup has
        been re-checked against everything price has done since it fired.

        This is the answer to the finding that the bot is never prompt
        (see setup_validity.py). A market order sent 40 minutes late buys
        at whatever price exists then; a limit sits at the level the stop
        was sized for. What age DOES change is whether the setup is still
        worth taking at all, and that is a question about price, not the
        clock -- so it is asked of the candles, not of a cutoff.
        """
        # A resting order is not exposure -- until it fills. `_account_state()`
        # reads positions_get() only, so without this a batch of limits could
        # all be approved against the same headroom and then all fill within
        # the same minute, blowing straight through the daily cap. So the
        # aggregate check is re-run counting every order already resting as
        # though it were already open: the worst case IS that they all fill.
        #
        # Deliberately re-uses RiskManager rather than reimplementing the
        # arithmetic here -- the risk rules must have exactly one definition.
        if self.pending_entries:
            committed = replace(state, open_positions=state.open_positions + tuple(
                OpenPosition(ticket=p.ticket, instrument=p.instrument, risk_amount=p.risk_amount)
                for p in self.pending_entries.values()))
            decision = self.risk_manager.check_new_entry(committed)
            if decision.decision != Decision.ALLOW:
                self._log_event("entry_attempt", decision.decision.value,
                                 f"{decision.reason} (counting {len(self.pending_entries)} "
                                 f"resting order(s) as though already filled)", state,
                                 instrument=instrument, trade_id=str(record.trade_id),
                                 risk=risk, **base_fields)
                return

        verdict = check_setup(record.entry_price, record.stop_loss, record.primary_target,
                              record.direction, self._candles_since(instrument, record.entry_time))
        if not verdict.alive:
            self._log_event("entry_attempt", f"decline_setup_{verdict.validity.value}",
                             verdict.reason, state, instrument=instrument,
                             trade_id=str(record.trade_id), risk=risk, **base_fields)
            return

        result = self.mt5_exec.place_limit_order(instrument, direction, lot_size,
                                                  record.entry_price, record.stop_loss,
                                                  record.primary_target)
        row_id = self._log_event(
            "entry_attempt", "allow_pending" if result.success else "execution_failed",
            f"limit resting at {record.entry_price} -- {verdict.reason}"
            if result.success else result.reason,
            state, instrument=instrument, trade_id=str(record.trade_id), risk=risk,
            requested_price=result.requested_price, **base_fields,
        )
        if result.success:
            self.pending_entries[(instrument, result.ticket)] = PendingEntry(
                row_id=row_id, instrument=instrument, ticket=result.ticket,
                risk_amount=risk, entry_price=record.entry_price,
                stop_loss=record.stop_loss, target=record.primary_target,
                direction=record.direction, signal_time=record.entry_time,
            )

    def _weekend_close_at(self, now) -> datetime:
        """The next Friday 17:00 New York, as UTC.

        Computed in the New York zone and converted, never as a fixed UTC
        hour -- the close is 21:00 UTC under EDT and 22:00 under EST.
        """
        local = now.astimezone(WEEKEND_CLOSE_ZONE)
        days_ahead = (WEEKEND_CLOSE_WEEKDAY - local.weekday()) % 7
        close = (local + timedelta(days=days_ahead)).replace(
            hour=WEEKEND_CLOSE_LOCAL_HOUR, minute=0, second=0, microsecond=0)
        if close < local:
            close += timedelta(days=7)
        return close.astimezone(timezone.utc)

    def _minutes_to_weekend_close(self, now=None) -> float:
        now = now or datetime.now(timezone.utc)
        return (self._weekend_close_at(now) - now).total_seconds() / 60.0

    def _market_closed_for_weekend(self, now=None) -> bool:
        """True while the market is actually shut: Friday's close through
        Sunday's open, both 17:00 New York.

        Needed as its own case because `_minutes_to_weekend_close()` rolls
        forward to NEXT Friday the moment this Friday's close passes -- so
        on a Saturday it reports six days, and a window measured purely as
        "minutes until close" reads the weekend itself as the safest time
        of the week. Anything found resting after a restart over the
        weekend still has to be cancelled.
        """
        local = (now or datetime.now(timezone.utc)).astimezone(WEEKEND_CLOSE_ZONE)
        after_friday_close = (local.weekday() == WEEKEND_CLOSE_WEEKDAY
                              and local.hour >= WEEKEND_CLOSE_LOCAL_HOUR)
        saturday = local.weekday() == 5
        sunday_before_open = local.weekday() == 6 and local.hour < WEEKEND_CLOSE_LOCAL_HOUR
        return after_friday_close or saturday or sunday_before_open

    def _weekend_is_close(self, now=None) -> bool:
        """True inside the flatten window, or once the market has actually
        closed -- everything must be closed and cancelled (operator
        requirement, 2026-09-02)."""
        return (self._minutes_to_weekend_close(now) <= FLATTEN_MINUTES_BEFORE_CLOSE
                or self._market_closed_for_weekend(now))

    def _too_late_to_open(self, now=None) -> bool:
        """True once a new trade would be force-closed by the clock rather
        than resolved on its own terms."""
        return self._minutes_to_weekend_close(now) <= NO_NEW_ENTRIES_MINUTES_BEFORE_CLOSE

    def _flatten_for_weekend(self, state):
        """Close every position we own before the market closes.

        Scoped to OUR magic number: a position opened by hand in the
        terminal is the operator's business, not this loop's, and closing
        someone else's trade is not a mistake that can be undone. Those
        are surfaced loudly instead.

        Untracked positions carrying our magic ARE closed -- they came
        from a send whose confirmation was lost (the 2026-09-01 CHFJPY
        triple-fill is exactly this), so they are ours whether or not this
        process remembers placing them, and they are precisely the
        positions most likely to be left sitting over a weekend.
        """
        ours = self.mt5_exec.our_open_positions()
        if ours is None:
            logger.error("WEEKEND FLATTEN: could not read open positions -- cannot confirm "
                          "the account is flat. CHECK BY HAND before the close.")
            return
        for position in ours:
            instrument = self.mt5_exec.internal_symbol(position.symbol)
            result = self.mt5_exec.close_position(position.ticket)
            if result.success:
                self._log_event("exit", "weekend_flatten",
                                 f"closed before the Friday {WEEKEND_CLOSE_LOCAL_HOUR}:00 New York "
                                 f"close -- nothing is held over the weekend", state,
                                 instrument=instrument, trade_id=str(position.ticket))
                self.tracked_positions.pop((instrument, position.ticket), None)
            else:
                logger.error("WEEKEND FLATTEN: could not close %s on %s: %s -- CLOSE IT BY HAND",
                              position.ticket, instrument, result.reason)

    def _reconcile_pending_entries(self, state):
        """Keep resting orders honest: promote fills, cancel the dead.

        Three things can happen to an order between polls, and each needs
        a different answer:
          - it filled           -> a position now exists; start tracking it
          - the setup died      -> cancel, the thesis is gone
          - the weekend is here -> cancel, nothing rests over it

        Anything resting at the broker that this process doesn't recognise
        is REPORTED rather than adopted or ignored -- a restart loses the
        in-memory mapping but not the orders, and silently assuming
        ownership is the same conflation that produced untracked
        positions on 2026-08-31.
        """
        if not self.pending_entries and self.entry_order_type != "limit":
            return

        resting = self.mt5_exec.pending_tickets_by_symbol()
        weekend = self._weekend_is_close()
        open_tickets = {p.ticket for p in state.open_positions}

        for key, pending in list(self.pending_entries.items()):
            instrument, ticket = key

            # Gone from the broker's book: it filled, expired, or someone
            # removed it. A matching position means it filled.
            if resting is not None and ticket not in resting.get(instrument, set()):
                del self.pending_entries[key]
                filled = open_tickets - {t for _, t in self.tracked_positions}
                if filled:
                    new_ticket = sorted(filled)[0]
                    self.tracked_positions[(instrument, new_ticket)] = TrackedPosition(
                        row_id=pending.row_id, instrument=instrument, ticket=new_ticket,
                        risk_amount=pending.risk_amount, entry_price=pending.entry_price,
                    )
                    logger.info("limit order %s on %s filled -> position %s at %s",
                                ticket, instrument, new_ticket, pending.entry_price)
                else:
                    logger.info("limit order %s on %s is no longer resting and no position "
                                "appeared -- expired or cancelled elsewhere", ticket, instrument)
                continue

            if weekend:
                self._cancel_pending(key, pending, state,
                                     "weekend cutoff reached -- nothing rests over the weekend")
                continue

            verdict = check_setup(pending.entry_price, pending.stop_loss, pending.target,
                                   pending.direction,
                                   self._candles_since(instrument, pending.signal_time))
            if not verdict.alive:
                self._cancel_pending(key, pending, state, verdict.reason)

        # Orders at the broker that this process has no record of.
        if resting is not None:
            known = {(i, t) for (i, t) in self.pending_entries}
            for instrument, tickets in resting.items():
                for ticket in tickets:
                    if (instrument, ticket) not in known and ticket not in self._reported_untracked:
                        self._reported_untracked.add(ticket)
                        logger.warning(
                            "UNTRACKED resting order %s on %s -- this process did not place it "
                            "(or was restarted since). It will NOT be cancelled automatically; "
                            "check it by hand.", ticket, instrument)

    def _cancel_pending(self, key, pending: PendingEntry, state, reason: str):
        result = self.mt5_exec.cancel_pending_order(pending.ticket)
        if result.success:
            del self.pending_entries[key]
            self._log_event("entry_cancelled", "cancel_pending", reason, state,
                             instrument=pending.instrument, risk=pending.risk_amount)
        else:
            logger.warning("could not cancel resting order %s on %s: %s -- will retry next poll",
                           pending.ticket, pending.instrument, result.reason)

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
        # The one event type that does NOT go through _log_event() (this
        # updates an existing row rather than creating one), so it needs
        # its own line -- without it, a trade CLOSING (the win/loss, not
        # just the entry) would never reach the standard logger, and
        # therefore never reach a TelegramHandler either.
        r_text = f"{r_multiple:+.2f}R" if r_multiple is not None else "R n/a"
        # deal.reason is already "stop_hit" | "target_hit" | "manual_or_other"
        # (MT5Client._deal_reason_name -- not a raw MT5 enum), so this
        # reads unambiguously as a stop or a target without translation.
        logger.info("%s: closed ticket %s -- %s | entry %s -> exit %s | %s, $%+.2f",
                    tracked.instrument, tracked.ticket, deal.reason,
                    tracked.entry_price, deal.price, r_text, deal.profit)
        if self.risk_manager.check_target_hit(state):
            self.risk_manager.accepting_entries = False
            self._log_event("phase_transition", "phase_target_hit",
                             f"balance {state.balance:,.2f} reached the phase target", state)

    def _try_reconnect(self):
        """Backs off between actual reconnect attempts rather than firing
        one on every single poll (previously every flat POLL_SECONDS,
        forever). Confirmed live 2026-08-27/28: a real outage produced
        150 and 158 consecutive `mt5.initialize()` failures across the
        two bots, each fired every 5 seconds with no backoff -- 12+
        minutes of IPC/network calls thrown at an already-failing
        terminal on a VPS with documented resource contention
        (OPERATIONS_LOG.md), during precisely the window it needed that
        load least.

        This does NOT fix the underlying cause of the auth failures --
        that's still undiagnosed, and might be broker-side (a free demo
        pool), might be VPS-side (the terminal missing the broker's
        keepalive under load), and nothing here can tell those apart.
        It only stops adding load during the outage. First retry after
        going unhealthy is still immediate; the delay only grows on
        repeated failure, doubling from RECONNECT_BACKOFF_BASE_SECONDS
        up to RECONNECT_BACKOFF_MAX_SECONDS, and resets the moment a
        reconnect actually succeeds.

        A resource_snapshot() (bot/diagnostics.py) is logged on the FIRST
        failure of a new outage, and again on recovery -- not on every
        attempt, since a real storm can be 150+ of them and that would
        just be noise. This is the actual diagnostic for the paragraph
        above: high load/swap at failure time points at the VPS: clean
        numbers at failure time point at the broker. Direct 2026-08-29
        request -- settle which one it is with data instead of leaving
        both as standing guesses forever."""
        now = datetime.now(timezone.utc)
        if self._next_reconnect_at is not None and now < self._next_reconnect_at:
            return
        was_mid_outage = self._reconnect_attempts > 0
        try:
            self.mt5_client.connect()
            logger.info("reconnected to MT5")
            if was_mid_outage:
                logger.info("resources at recovery: %s", resource_snapshot())
            self._reconnect_attempts = 0
            self._next_reconnect_at = None
        except MT5ConnectionError as exc:
            if not was_mid_outage:
                logger.warning("resources at first failure of this outage: %s", resource_snapshot())
            self._reconnect_attempts += 1
            delay = min(RECONNECT_BACKOFF_BASE_SECONDS * (2 ** (self._reconnect_attempts - 1)),
                        RECONNECT_BACKOFF_MAX_SECONDS)
            self._next_reconnect_at = now + timedelta(seconds=delay)
            logger.warning("reconnect failed (attempt %d, next retry in %ds): %s",
                            self._reconnect_attempts, delay, exc)

    def _log_event(self, event_type, decision, reason, state, instrument="", trade_id="", risk=0.0,
                    requested_price=None, filled_price=None, slippage_points=None, **kwargs) -> int:
        # Every entry decision, decline, health halt and phase transition
        # funnels through here -- one logger.info() call covers all of
        # them, rather than adding one at each of the several call
        # sites. This is what a TelegramHandler (telegram_notify.py)
        # actually receives; without it, the only things visible outside
        # the audit database would be reconnects, storyline transitions
        # and per-instrument exceptions, missing every real trade
        # decision entirely.
        logger.info(_describe_event(event_type, decision, reason, instrument, risk, kwargs))
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


def _describe_event(event_type, decision, reason, instrument, risk, kwargs) -> str:
    """The human-readable line every entry decision, decline, health
    halt and phase transition gets logged as -- written to answer WHY,
    not just what. For an entry_attempt, `kwargs` already carries the
    strategy's full read of the setup (_audit_fields_from_trade_record):
    bias per timeframe, which one is effective, which timeframes
    aligned, the confirmation trigger that fired, the key level, and the
    stop/target -- present whether the entry was ultimately allowed,
    declined, or failed to place, since the risk manager's decision is a
    separate question from what the strategy saw. Direct request: "log
    everything ... thought process, structure alignment, confirmation,
    entry, exit stop loss" -- this is that, one event at a time."""
    head = f"{instrument or event_type}: {event_type}" + (f" ({decision})" if decision else "")
    lines = [f"{head} -- {reason}"]
    if event_type == "entry_attempt" and kwargs.get("trigger_type"):
        if kwargs.get("entry_time"):
            # Distinct from this log line's own timestamp on purpose: a
            # signal caught up after an outage (watermark-widening,
            # storyline-gap-replay) is legitimately acted on well after
            # its own candle closed. Without this line there was no way
            # to tell "fresh" from "stale catch-up" from Telegram alone --
            # directly raised 2026-08-29.
            lines.append(f"  signal candle: {kwargs['entry_time']}")
        bias = ", ".join(f"{tf}={kwargs[field]}" for tf, field in
                          (("Weekly", "bias_weekly"), ("Daily", "bias_daily"), ("H4", "bias_h4"))
                          if kwargs.get(field))
        lines.append(f"  {kwargs.get('direction', '?')} | confirmation: {kwargs['trigger_type']} "
                    f"({kwargs.get('entry_pattern', '?')}) | effective bias: "
                    f"{kwargs.get('effective_bias_timeframe', '?')} | aligned: "
                    f"{kwargs.get('aligned_timeframes', '?')}")
        if bias:
            lines.append(f"  bias by timeframe: {bias}")
        lines.append(f"  entry {kwargs.get('entry_price', '?')} | stop {kwargs.get('stop_loss', '?')} "
                    f"({kwargs.get('stop_kind', '?')}) | target {kwargs.get('primary_target', '?')} "
                    f"| key level {kwargs.get('key_level_price', '?')} ({kwargs.get('key_level_shape', '?')})")
        if risk:
            lines.append(f"  risking ${risk:,.2f}")
    return "\n".join(lines)


def _audit_fields_from_trade_record(record: TradeRecord) -> dict:
    """Pulls the strategy feature-context fields off a TradeRecord into
    the flat kwargs DecisionRecord/AuditLog expects -- kept as a plain
    function (not a method) since it's a pure data-shape translation with
    no orchestrator state involved."""
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
