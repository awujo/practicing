import pandas as pd
import pytest

from ..run_slk import _curve_stats, _sort_key, _stats
from ..slk_system import SLK_OPERATIONAL, SLK_SYSTEM, SLK_VARIANTS, slk_kwargs


class Rec:
    def __init__(self, r, exit_reason="target_hit", entry=0, exit=None,
                 trigger_type="breakout"):
        b = pd.Timestamp("2026-01-01", tz="UTC")
        self.r_multiple = r
        self.exit_reason = exit_reason
        self.entry_time = b + pd.Timedelta(hours=entry)
        self.exit_time = b + pd.Timedelta(hours=exit if exit is not None else entry + 1)
        self.trigger_type = trigger_type


def L(r=-1.0, **kw):
    return Rec(r, exit_reason="stop_hit", **kw)


def test_drawdown_is_peak_to_trough_not_the_final_total():
    """A system can end well up and still have had a hole in it deep
    enough to stop you trading. The total cannot show that."""
    trades = [Rec(3.0, entry=0), L(entry=1), L(entry=2), L(entry=3), Rec(5.0, entry=4)]
    dd, streak = _curve_stats(trades, spread=0.0)
    assert dd == pytest.approx(3.0), "peak 3.0 -> trough 0.0"
    assert streak == 3
    assert sum(t.r_multiple for t in trades) == pytest.approx(5.0)


def test_the_curve_is_walked_in_EXIT_order():
    """A trade that opens early and closes late belongs where its result
    landed. Sorting by entry shows a smoother curve than anyone lived."""
    # Opens first, closes last -- its loss must land at the END.
    slow_loser = L(entry=0, exit=100)
    quick_win = Rec(4.0, entry=1, exit=2)
    by_exit = sorted([slow_loser, quick_win], key=_sort_key)
    assert by_exit == [quick_win, slow_loser]
    dd, _ = _curve_stats([slow_loser, quick_win], spread=0.0)
    assert dd == pytest.approx(1.0), "peak 4.0 after the win, then -1.0"


def test_spread_is_charged_inside_the_drawdown_too():
    """Charging it only on the average would understate the hole."""
    trades = [L(entry=i) for i in range(5)]
    plain, _ = _curve_stats(trades, spread=0.0)
    with_spread, _ = _curve_stats(trades, spread=0.1)
    assert plain == pytest.approx(5.0)
    assert with_spread == pytest.approx(5.5)


def test_profit_factor_and_averages():
    s = _stats([Rec(3.0, entry=0), Rec(2.0, entry=1), L(entry=2), L(entry=3)], spread=0.0)
    assert s["n"] == 4
    assert s["win"] == pytest.approx(50.0)
    assert s["avg_win"] == pytest.approx(2.5)
    assert s["avg_loss"] == pytest.approx(1.0)
    assert s["profit_factor"] == pytest.approx(2.5)


def test_open_trades_are_excluded():
    s = _stats([Rec(3.0, entry=0), Rec(None, exit_reason="still_open", entry=1)], spread=0.0)
    assert s["n"] == 1


def test_the_system_is_the_taught_rules_and_nothing_unsourced():
    """Every key here has a citation in slk_system.py. A setting nobody
    can cite is not part of the system."""
    from ...engine.runner import TRIGGERS_TAUGHT

    assert SLK_SYSTEM == {
        "confirmation_triggers": TRIGGERS_TAUGHT,
        "erl_mode": "target",
        "bias_caveat": True,
        "liquidity_mode": "both",
    }


def test_filters_are_variants_never_part_of_the_system():
    assert "require_qmr" not in SLK_SYSTEM
    assert "require_imbalance_overlap" not in SLK_SYSTEM
    assert set(SLK_VARIANTS) == {"qmr", "imbalance"}
    assert "require_qmr" not in slk_kwargs()
    assert slk_kwargs(**SLK_VARIANTS["qmr"])["require_qmr"] is True


def test_operational_settings_are_kept_separate_from_taught_ones():
    """The rollover skip and the 1R floor came from live incidents and
    direct instructions, not from the course. Mixing them in would let
    a future reader cite the course for them."""
    assert "avoid_rollover_entries" in SLK_OPERATIONAL
    assert "min_reward_r" in SLK_OPERATIONAL
    assert not (set(SLK_SYSTEM) & set(SLK_OPERATIONAL))
    # slk_kwargs still merges both, since run_backtest needs them.
    assert set(slk_kwargs()) >= set(SLK_SYSTEM) | set(SLK_OPERATIONAL)


def test_the_taught_system_contains_no_number_i_chose():
    """The rule this bundle exists to enforce.

    Two settings here were numbers I picked, not rules anyone taught:
    min_stop_pips=2.0 and min_reward_r=3.0. Operator, 2026-09-23: "I
    invented that number -- what the heck is this guy. Is this what you
    were taught?" No. A filter nobody taught is not a fix, it is the
    course being overruled by a guess, and it is exactly how a system
    stops being the one that was taught.

    The reward floor that remains is 1.0, from LIVE_FIXED_FLAGS, and
    that one IS sourced -- "a trade of less than 1R doesn't make sense
    to hold" (2026-09-01)."""
    from ..slk_system import SLK_TAUGHT_OVERRIDES

    assert "min_stop_pips" not in SLK_TAUGHT_OVERRIDES
    assert "min_reward_r" not in SLK_TAUGHT_OVERRIDES
    assert slk_kwargs()["min_reward_r"] == 1.0
    assert "min_stop_pips" not in slk_kwargs()

    # What is left must be mechanism, not magnitude: every value here is
    # a switch, never a threshold someone has to justify.
    assert all(isinstance(v, bool) for v in SLK_TAUGHT_OVERRIDES.values()), \
        SLK_TAUGHT_OVERRIDES
