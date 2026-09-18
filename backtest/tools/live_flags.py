"""The strategy flags the live bots are ACTUALLY launched with.

Why this exists as its own module (2026-09-18). A diagnostic tool is
only worth anything if it runs the same strategy the bot runs. The first
version of `count_signals` took its defaults from `LiveBot`'s dataclass
fields and shipped a test asserting they matched -- which passed, and was
still wrong, because the overrides live at the LAUNCH SITE, not in the
dataclass. Both bots are started with `--origin-kind any
--close-based-sweep-break`, so the tool was quietly measuring a strategy
nobody is running and would have reported its signal count with total
confidence.

Verified from `ps -eo args` on the VPS, 2026-09-18:

    python3 -m bot.run_live ... --style aggressive --entry-order-type limit
        --min-departure-r 0.8 --origin-kind any --close-based-sweep-break
        --history-windows-config bot/history_windows.json ...
    python3 -m bot.run_live ... --style conservative
        --origin-kind any --close-based-sweep-break
        --history-windows-config bot/history_windows.json ...

Only the flags that change which SIGNALS are produced belong here.
Execution-side flags (--entry-order-type, --min-departure-r) do not:
they decide what happens to a signal after run_backtest has found it,
and no tool that counts signals should be pretending to model them.

This is a hand-maintained mirror of a deployment, so it can go stale --
which is exactly why every tool using it prints its values at the top of
its output. A number produced under flags you can see is checkable; one
produced under flags you cannot is not.
"""

from __future__ import annotations

# Passed to run_backtest() by orchestrator._check_instrument() with the
# values the deployed launch command sets.
LIVE_LAUNCH_FLAGS = {
    "origin_kind": "any",
    "close_based_sweep_break": True,
    "stop_anchor": "trigger_wick",
}

# Always-on inside _check_instrument(), not settable from the command
# line -- see the long comments there for the live incidents behind each.
LIVE_FIXED_FLAGS = {
    "avoid_rollover_entries": True,
    "min_reward_r": 1.0,
}
