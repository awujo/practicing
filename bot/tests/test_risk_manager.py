import pytest

from ..config import PhaseRules
from ..risk_manager import AccountState, Decision, OpenPosition, RiskManager

RULES = PhaseRules(
    daily_dd_limit_pct=0.04, overall_dd_limit_pct=0.10,
    risk_normal=1000.0, risk_reduced=500.0, de_risk_at_pct=0.05,
    profit_target_pct=0.08,
)


def healthy_state(**overrides):
    defaults = dict(balance=100000.0, equity=100000.0, day_start_balance=100000.0,
                     phase_start_balance=100000.0, open_positions=())
    defaults.update(overrides)
    return AccountState(**defaults)


def test_allows_a_trade_in_a_clean_healthy_state():
    rm = RiskManager(RULES, terminates_on_dd=True)
    decision = rm.check_new_entry(healthy_state())
    assert decision.decision == Decision.ALLOW
    assert decision.risk_amount == 1000.0


def test_declines_when_not_accepting_entries_phase_target_already_hit():
    rm = RiskManager(RULES, terminates_on_dd=True, accepting_entries=False)
    decision = rm.check_new_entry(healthy_state())
    assert decision.decision == Decision.DECLINE_PHASE_NOT_ACCEPTING


def test_declines_on_overall_drawdown_breach():
    rm = RiskManager(RULES, terminates_on_dd=True)
    state = healthy_state(balance=89000.0, equity=89000.0)  # -11%, past the 10% limit
    decision = rm.check_new_entry(state)
    assert decision.decision == Decision.DECLINE_OVERALL_DD


def test_personal_account_never_declines_on_overall_drawdown():
    rm = RiskManager(RULES, terminates_on_dd=False)
    state = healthy_state(balance=50000.0, equity=50000.0)  # -50%, would breach for a prop account
    decision = rm.check_new_entry(state)
    assert decision.decision != Decision.DECLINE_OVERALL_DD


def test_declines_on_live_equity_daily_breach_from_floating_loss_alone():
    # No realized loss today, but floating P&L on open positions already
    # crossed the daily limit -- this is exactly the gap the offline
    # (realized-only) analysis couldn't see, now closeable with live data.
    # $4,200 floating loss is plausible (5 open positions, $5,000 total
    # committed risk) so this must NOT be flagged as a stop-slippage
    # anomaly -- it's a real, ordinary daily-limit breach.
    rm = RiskManager(RULES, terminates_on_dd=True)
    state = healthy_state(
        balance=100000.0, equity=95800.0,  # -4.2% live equity, all floating
        open_positions=tuple(OpenPosition(i, "EURUSD", 1000.0) for i in range(5)),
    )
    decision = rm.check_new_entry(state)
    assert decision.decision == Decision.DECLINE_DAILY_EQUITY_BREACH


def test_declines_via_aggregate_risk_gate_when_realized_only_would_have_allowed_it():
    # Today's REALIZED loss alone is small, but 3 open positions already
    # commit $3,000 of fixed risk -- adding a 4th brings worst-case-if-
    # all-stop to $4,000 = 4% of $100k, at the limit.
    rm = RiskManager(RULES, terminates_on_dd=True)
    state = healthy_state(
        balance=100000.0, equity=99700.0,  # small floating loss, nowhere near the daily equity check
        day_start_balance=100000.0,
        open_positions=(
            OpenPosition(1, "EURUSD", 1000.0),
            OpenPosition(2, "GBPUSD", 1000.0),
            OpenPosition(3, "USDJPY", 1000.0),
        ),
    )
    decision = rm.check_new_entry(state)
    assert decision.decision == Decision.DECLINE_DAILY_AGGREGATE_RISK


def test_allows_when_aggregate_risk_stays_comfortably_under_the_limit():
    rm = RiskManager(RULES, terminates_on_dd=True)
    state = healthy_state(
        open_positions=(OpenPosition(1, "EURUSD", 1000.0),),  # 1 open + 1 new = $2,000 = 2%, fine
    )
    decision = rm.check_new_entry(state)
    assert decision.decision == Decision.ALLOW


def test_anomaly_halt_when_floating_loss_exceeds_what_open_stops_should_allow():
    # A single $1,000-risk position should never float worse than -$1,000
    # if its stop holds -- $1,800 floating loss means the stop slipped.
    rm = RiskManager(RULES, terminates_on_dd=True)
    state = healthy_state(
        balance=100000.0, equity=98200.0,  # -$1,800 floating
        open_positions=(OpenPosition(1, "EURUSD", 1000.0),),
    )
    decision = rm.check_new_entry(state)
    assert decision.decision == Decision.DECLINE_ANOMALY_HALT
    assert decision.is_anomaly is True


def test_no_anomaly_when_floating_loss_is_within_what_open_stops_allow():
    rm = RiskManager(RULES, terminates_on_dd=True)
    state = healthy_state(
        balance=100000.0, equity=99200.0,  # -$800 floating, within the $1,000 open risk
        open_positions=(OpenPosition(1, "EURUSD", 1000.0),),
    )
    decision = rm.check_new_entry(state)
    assert decision.decision != Decision.DECLINE_ANOMALY_HALT


def test_risk_steps_down_once_overall_drawdown_reaches_the_de_risk_threshold():
    rm = RiskManager(RULES, terminates_on_dd=True)
    state = healthy_state(balance=94500.0, equity=94500.0)  # -5.5%, past the 5% de-risk threshold
    assert rm.risk_for_next_trade(state) == 500.0


def test_risk_steps_back_up_once_equity_recovers_above_the_de_risk_threshold():
    rm = RiskManager(RULES, terminates_on_dd=True)
    state = healthy_state(balance=97000.0, equity=97000.0)  # -3%, above the 5% de-risk threshold
    assert rm.risk_for_next_trade(state) == 1000.0


def test_check_target_hit_true_once_balance_reaches_the_phase_target():
    rm = RiskManager(RULES, terminates_on_dd=True)
    state = healthy_state(balance=108500.0, equity=108500.0, phase_start_balance=100000.0)
    assert rm.check_target_hit(state) is True


def test_check_target_hit_false_below_target():
    rm = RiskManager(RULES, terminates_on_dd=True)
    state = healthy_state(balance=105000.0, equity=105000.0, phase_start_balance=100000.0)
    assert rm.check_target_hit(state) is False


def test_check_target_hit_false_when_phase_has_no_target_eg_funded():
    funded_rules = PhaseRules(daily_dd_limit_pct=0.04, overall_dd_limit_pct=0.10,
                               risk_normal=1000.0, risk_reduced=500.0, de_risk_at_pct=0.05,
                               profit_target_pct=None)
    rm = RiskManager(funded_rules, terminates_on_dd=True)
    state = healthy_state(balance=999999.0, equity=999999.0, phase_start_balance=100000.0)
    assert rm.check_target_hit(state) is False


def test_check_health_flags_an_already_realized_overall_dd_breach_without_a_pending_trade():
    rm = RiskManager(RULES, terminates_on_dd=True)
    state = healthy_state(balance=88000.0, equity=88000.0)
    decision = rm.check_health(state)
    assert decision is not None
    assert decision.decision == Decision.DECLINE_OVERALL_DD


def test_check_health_returns_none_when_everything_is_fine():
    rm = RiskManager(RULES, terminates_on_dd=True)
    assert rm.check_health(healthy_state()) is None
