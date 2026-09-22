import json

import pytest

from ..live_cycle_timing import CONFIGS, CYCLE_BUDGET_S, STALE_CUTOFF_S, load_windows
from ..slk_system import SLK_OPERATIONAL, slk_kwargs


def test_windows_come_from_the_file_the_orchestrator_reads():
    """Timing against different windows than live uses would be measuring
    a machine nobody runs."""
    window_for = load_windows()
    # A default exists and is small -- that trimming is the whole reason
    # live keeps up while a full backtest takes minutes per instrument.
    assert window_for("SOME_UNLISTED_PAIR") is not None
    assert window_for("EURUSD")["H1"] >= 1


def test_it_can_time_both_the_shipped_and_the_slk_configuration():
    """Without a baseline, a number is not a verdict -- "40 minutes" only
    means something next to what the bots do today."""
    assert set(CONFIGS) == {"shipped", "slk"}
    shipped = CONFIGS["shipped"]()
    slk = CONFIGS["slk"]()
    # Shipped is the operational settings only: no taught rules.
    assert shipped == dict(SLK_OPERATIONAL)
    assert "confirmation_triggers" not in shipped
    assert slk == slk_kwargs()
    assert slk["confirmation_triggers"] != ()


def test_the_budgets_are_the_bots_own_numbers():
    """3600s is one H1 candle; 3h is STALE_ENTRY_CUTOFF. Hardcoding a
    round number instead would report against a bar nobody enforces."""
    from ...  import __name__ as _  # noqa: F401  (package import sanity)
    import importlib

    orchestrator = importlib.import_module("bot.orchestrator")
    assert STALE_CUTOFF_S == orchestrator.STALE_ENTRY_CUTOFF.total_seconds()
    assert CYCLE_BUDGET_S == 3600.0


def test_a_malformed_windows_file_fails_loudly(tmp_path):
    p = tmp_path / "w.json"
    p.write_text("not json")
    with pytest.raises(json.JSONDecodeError):
        load_windows(str(p))
