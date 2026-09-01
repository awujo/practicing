from unittest.mock import patch

from .. import check_recent_signals as check_recent_signals_module


def test_main_asks_run_backtest_for_both_live_safety_filters(monkeypatch, tmp_path):
    # Must match orchestrator.py's _check_instrument() call exactly --
    # otherwise this reference feed includes signals the live bots now
    # deliberately skip (avoid_rollover_entries=True, min_reward_r=1.0,
    # both enabled 2026-09-01) before run_backtest() even returns them
    # as candidates. Since no audit row is ever logged for a filtered-out
    # signal (not even a decline), reconcile_signals.py would report
    # every one of them as MISSING -- identical in appearance to the
    # real "the bot never saw it" bug this feed exists to catch.
    monkeypatch.setattr(
        check_recent_signals_module, "DUKASCOPY_INSTRUMENTS", {"EURUSD": "x"})
    monkeypatch.setattr(
        "sys.argv",
        ["check_recent_signals", "--since", "2026-01-01T00:00:00",
         "--instruments", "EURUSD", "--styles", "conservative"],
    )

    with patch.object(check_recent_signals_module, "run_backtest", return_value=[]) as mock_rb:
        check_recent_signals_module.main()

    mock_rb.assert_called_once()
    assert mock_rb.call_args.kwargs.get("avoid_rollover_entries") is True
    assert mock_rb.call_args.kwargs.get("min_reward_r") == 1.0
