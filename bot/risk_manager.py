"""
Real-time risk manager -- the live version of the offline simulate_v2_safe.py
analysis, but driven entirely by ACCOUNT STATE THE CALLER SUPPLIES rather
than an internal ledger. This module never talks to MT5 directly and never
remembers what it did last time; every call is given a fresh AccountState
and returns a decision. That's deliberate: MT5's own account/position
report is the single source of truth for a live account (a manual trade
you placed yourself, a stop-out, a broker margin call -- all show up
there), and a risk manager that trusted its own memory over the broker's
live state would drift out of sync exactly when it matters most (after a
reconnect, a restart, or any gap in connectivity). The caller (the live
orchestrator, not written yet) is responsible for pulling account_info()
and positions_get() from MT5 and building an AccountState from them on
every check.

Three layers of protection, from the two prior analysis passes:

  1. DETERMINISTIC pre-trade gate (the one that actually held up): decline
     a new trade unless -- even if every currently open position AND the
     new one all hit their exact, already-fixed stop today -- today's
     total loss would still stay under the daily limit. This only needs
     each open position's fixed worst case (its own stop distance), never
     a noisy floating reading, so it can never be fooled by a trade that
     looks bad now but recovers.
  2. LIVE EQUITY circuit breaker: unlike the offline analysis (which only
     had realized P&L to look at), a live account gives us real floating
     P&L continuously. If TODAY'S ACTUAL EQUITY has already dropped to
     the daily limit -- whether from realized losses, floating losses, or
     (critically) a stop that gapped/slipped past its intended price in a
     live market, which the backtest's idealized fills never have to
     account for -- that's real, not speculative, and blocks all new
     entries immediately. This does NOT force-close open positions (that
     was the move that backfired in the offline test); it only stops
     opening new risk.
  3. OVERALL drawdown check, equity-based, against the phase's starting
     balance -- same idea, whole-phase horizon instead of one day.

A live equity reading matching or exceeding what the deterministic gate
assumed as the WORST case (i.e. actual damage exceeds every open
position's stop distance) is flagged as an anomaly, not just a regular
decline -- it means a stop didn't hold as intended (slippage/gap), and
the account should hard-stop pending human review rather than silently
continue.
"""

from dataclasses import dataclass, field
from enum import Enum

from .config import PhaseRules


class Decision(Enum):
    ALLOW = "allow"
    DECLINE_PHASE_NOT_ACCEPTING = "decline_phase_not_accepting"
    DECLINE_DAILY_AGGREGATE_RISK = "decline_daily_aggregate_risk"
    DECLINE_DAILY_EQUITY_BREACH = "decline_daily_equity_breach"
    DECLINE_OVERALL_DD = "decline_overall_dd"
    DECLINE_ANOMALY_HALT = "decline_anomaly_halt"


@dataclass(frozen=True)
class OpenPosition:
    ticket: int
    instrument: str
    risk_amount: float  # $ committed if this position is stopped out at its OWN, actual stop-loss price


@dataclass(frozen=True)
class AccountState:
    balance: float              # realized balance (MT5 account_info().balance) -- excludes floating P&L
    equity: float                # balance + floating P&L (MT5 account_info().equity) -- real-time
    day_start_balance: float     # snapshotted by the caller at each new UTC day
    phase_start_balance: float   # snapshotted by the caller when the current phase began
    open_positions: tuple[OpenPosition, ...] = ()


@dataclass(frozen=True)
class RiskDecision:
    decision: Decision
    reason: str
    risk_amount: float = 0.0
    is_anomaly: bool = False


class RiskManager:
    """One instance per active phase -- construct a new one (with that
    phase's PhaseRules) whenever config.AccountProfile's active_phase
    changes, same as the MT5 connection itself does."""

    def __init__(self, rules: PhaseRules, terminates_on_dd: bool, accepting_entries: bool = True):
        self.rules = rules
        self.terminates_on_dd = terminates_on_dd
        self.accepting_entries = accepting_entries  # False once this phase's profit target has been hit

    def risk_for_next_trade(self, state: AccountState) -> float:
        """$ risk to use for the NEXT trade, based on live overall
        drawdown from this phase's starting balance -- checked fresh on
        every call, so it steps back up automatically if equity recovers
        above the de-risk threshold, and back down if it dips again."""
        overall_dd = self._overall_dd(state)
        return self.rules.risk_reduced if overall_dd >= self.rules.de_risk_at_pct else self.rules.risk_normal

    def check_new_entry(self, state: AccountState) -> RiskDecision:
        """Call this BEFORE sending any new order. Does not know or care
        what the proposed trade's direction/instrument is -- only its
        dollar risk, computed from `risk_for_next_trade` using the
        position's actual planned stop distance once you know the entry/
        stop prices, same convention as the rest of this codebase."""
        anomaly = self._check_anomaly(state)
        if anomaly is not None:
            return anomaly

        if not self.accepting_entries:
            return RiskDecision(Decision.DECLINE_PHASE_NOT_ACCEPTING,
                                 "phase target already hit -- no new entries until the next phase begins")

        overall_dd = self._overall_dd(state)
        if self.terminates_on_dd and overall_dd >= self.rules.overall_dd_limit_pct:
            return RiskDecision(Decision.DECLINE_OVERALL_DD,
                                 f"overall drawdown {overall_dd:.2%} already at/past the "
                                 f"{self.rules.overall_dd_limit_pct:.0%} limit")

        risk = self.risk_for_next_trade(state)

        equity_dd_today = self._daily_equity_dd(state)
        if equity_dd_today >= self.rules.daily_dd_limit_pct:
            return RiskDecision(Decision.DECLINE_DAILY_EQUITY_BREACH,
                                 f"today's LIVE equity is already down {equity_dd_today:.2%} "
                                 f"against the {self.rules.daily_dd_limit_pct:.0%} daily limit "
                                 f"(realized + floating, not just closed trades)", risk_amount=risk)

        open_risk = sum(p.risk_amount for p in state.open_positions)
        realized_today = state.balance - state.day_start_balance
        aggregate_worst_case = realized_today - open_risk - risk
        aggregate_worst_case_pct = -aggregate_worst_case / state.day_start_balance
        if aggregate_worst_case_pct >= self.rules.daily_dd_limit_pct:
            return RiskDecision(
                Decision.DECLINE_DAILY_AGGREGATE_RISK,
                f"if every currently-open position ({len(state.open_positions)}, ${open_risk:,.0f} "
                f"committed) plus this trade (${risk:,.0f}) all hit their stops today, combined with "
                f"today's realized P&L (${realized_today:+,.0f}), that reaches {aggregate_worst_case_pct:.2%} "
                f"-- at/past the {self.rules.daily_dd_limit_pct:.0%} daily limit",
                risk_amount=risk,
            )

        return RiskDecision(Decision.ALLOW, "passed all gates", risk_amount=risk)

    def check_target_hit(self, state: AccountState) -> bool:
        """Call after every position close. Returns True the moment this
        phase's profit target is first reached -- the caller should stop
        opening new trades (set accepting_entries=False on this instance)
        the moment this fires, and let any still-open positions resolve
        normally rather than abandoning them."""
        if self.rules.profit_target_pct is None:
            return False
        return state.balance >= state.phase_start_balance * (1 + self.rules.profit_target_pct)

    def check_health(self, state: AccountState) -> RiskDecision | None:
        """Call continuously (not just before a new entry) -- e.g. on
        every price tick or every few seconds. Returns a decline/anomaly
        if the account has ALREADY breached a hard limit, so the caller
        can hard-stop even between new-entry checks (a live equity crash
        doesn't wait for you to consider a new trade)."""
        anomaly = self._check_anomaly(state)
        if anomaly is not None:
            return anomaly
        overall_dd = self._overall_dd(state)
        if self.terminates_on_dd and overall_dd >= self.rules.overall_dd_limit_pct:
            return RiskDecision(Decision.DECLINE_OVERALL_DD,
                                 f"overall drawdown breach: {overall_dd:.2%} >= {self.rules.overall_dd_limit_pct:.0%}")
        daily_dd = self._daily_equity_dd(state)
        if daily_dd >= self.rules.daily_dd_limit_pct:
            return RiskDecision(Decision.DECLINE_DAILY_EQUITY_BREACH,
                                 f"daily drawdown breach: {daily_dd:.2%} >= {self.rules.daily_dd_limit_pct:.0%}")
        return None

    def _overall_dd(self, state: AccountState) -> float:
        if state.phase_start_balance <= 0:
            return 0.0
        return max(0.0, (state.phase_start_balance - state.equity) / state.phase_start_balance)

    def _daily_equity_dd(self, state: AccountState) -> float:
        if state.day_start_balance <= 0:
            return 0.0
        return max(0.0, (state.day_start_balance - state.equity) / state.day_start_balance)

    def _check_anomaly(self, state: AccountState) -> RiskDecision | None:
        """A stop that gapped/slipped past its intended price means real
        floating damage can exceed what every open position's fixed risk
        implied was the worst possible loss -- something the deterministic
        gate assumes can't happen. If current floating P&L is already
        worse than -(sum of open positions' committed risk), a stop
        didn't hold as intended, and that's a broken assumption worth a
        hard stop over -- not something the caller should keep trading
        through as if it were a routine decline. (Not conditioned on
        today's realized P&L: the gap can be mid-flight, before the stop
        order has even filled and turned into a realized loss.)"""
        open_risk = sum(p.risk_amount for p in state.open_positions)
        floating_today = state.equity - state.balance
        if floating_today < -open_risk - 1.0:  # $1 tolerance for float rounding
            return RiskDecision(
                Decision.DECLINE_ANOMALY_HALT,
                f"live floating loss (${floating_today:+,.0f}) exceeds what open positions' fixed "
                f"stops (${open_risk:,.0f} total) should allow -- a stop likely slipped/gapped past "
                f"its price. Halting new entries pending review.",
                is_anomaly=True,
            )
        return None
