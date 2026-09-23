"""
Structured per-trade logging.

Built specifically so the eventual backtest dataset is more than a win/
loss tally -- it's a real feature set for training a model later. Every
closed trade gets logged with its full multi-timeframe bias context
(including `aligned_timeframes`, which of Weekly/Daily/H4 confirmed
independently -- entry-gate rebuild part 1), the key-level ranking
factors that led to the entry (Phase 2's 4 factors), the entry pattern
that fired, `trigger_type` (which of the 4 confirmation-entry triggers
actually fired -- entry-gate rebuild part 5) and a stop/target DECISION
audit trail (the trigger's own natural stop-loss vs. what was actually
used, whether the universal 4H-KL fallback fired, the plain rr target
vs. the ERL cap that was actually applied -- entry-gate rebuild parts
5-6) -- not just the final numbers, so the empirical claims behind these
mechanized rules (e.g. "the KL fallback almost never gets revisited
deeply, maybe 1 or 2 out of 10") can eventually be validated against real
data, not just assumed. And -- critically -- MAE/MFE (max adverse/
favorable excursion during the trade's life), not just the final win/loss
label. STRATEGY.md's own honesty about near-misses ("tight stops have
genuinely almost gotten stopped out before the correct move played out",
Section 6) is exactly the kind of signal a bare win/loss label throws
away; MAE captures it directly, in R-multiples so it's comparable across
instruments/pip sizes.
"""

from dataclasses import dataclass, fields
from enum import Enum
import csv


def _serialize(value):
    if value is None:
        return ""
    if isinstance(value, Enum):
        return value.value
    # NOTE: pandas Timestamp also exposes a `.value` attribute (raw int
    # nanoseconds) -- an earlier duck-typed `hasattr(value, "value")` check
    # here misfired on Timestamp objects. isinstance(Enum) above is exact.
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


@dataclass
class TradeRecord:
    # Identity
    trade_id: int
    instrument: str
    entry_time: object
    exit_time: object = None
    # The candle whose confirmation produced the signal. Equal to
    # entry_time in every fill model EXCEPT entry_fill="limit", where the
    # order rests at the trigger and fills on some later candle -- so the
    # two come apart, and telling them apart is the whole point of
    # inspecting a limit trade: did price actually come back to the level?
    signal_time: object = None
    # The earliest moment this record could have been COMPUTED at all --
    # its birth time, as distinct from the candle it is stamped for.
    #
    # They are not the same and the gap is what kept the live bot from
    # trading (2026-09-18 review). Entry detection needs candles AFTER
    # the entry candle: `classify_entry_pattern()` reads up to
    # FOLLOWING_LOOKAHEAD of them, and returns None with nothing after
    # the entry at all, so the newest candle can never produce a signal.
    # A signal stamped 13:00 may genuinely not exist until 16:00.
    #
    # The live loop measured staleness as `now - entry_time`, i.e.
    # counting age the signal spent not existing, and declined it against
    # a three-hour cutoff it had already burnt before anyone could see
    # it. Measured against `signal_known_at` instead, the question
    # becomes "how long has this been ACTIONABLE", which is what the
    # cutoff was always meant to ask.
    #
    # None means "not recorded" and callers must fall back to
    # `entry_time` -- the pre-2026-09-18 reading, and the pessimistic one.
    signal_known_at: object = None

    # Entry context
    direction: object = None            # Direction
    entry_timeframe: str = ""
    entry_price: float = 0.0
    entry_pattern: str = ""             # "direct_mitigation" | "fresh_irl_required" | "nested_disrespect"
    entry_style: str = ""               # "aggressive" | "conservative"
    trigger_type: str = ""              # "plug_and_play" | "engulfing" | "fourth_man" -- see entries.py

    # Multi-timeframe bias context at entry
    bias_monthly: object = None         # Direction | None
    bias_weekly: object = None
    bias_daily: object = None
    bias_h4: object = None
    bias_h1: object = None
    effective_bias_timeframe: str | None = None
    aligned_timeframes: str = ""        # comma-joined subset of "Weekly,Daily,H4" -- see _aligned_timeframes()

    # THE SETUP ITSELF -- what price came for, and when.
    #
    # Added 2026-09-23 because none of it was recorded, and that made
    # every rendered chart unreadable. The operator, looking at one:
    # "I couldn't even understand what was going on. I couldn't
    # understand where single candle liquidity was." It was not a
    # drawing problem. The liquidity pool, the sweep that took it and
    # the H4 breakout that opened the window had no columns, so nothing
    # downstream could show them, and a trade drawn without them is an
    # entry arrow with no reason attached.
    #
    # These are what the strategy is ABOUT -- price leaving a breakout,
    # coming back for the liquidity that breakout left behind, and
    # reacting off a key level -- so they belong in the log beside the
    # entry they produced.
    setup_id: int = 0                   # one setup may be re-entered; this shows it
    liquidity_price: float = 0.0        # the pool price came back to take
    liquidity_time: object = None       # when the candle forming that pool opened
    sweep_time: object = None           # when price actually took it
    level_touch_time: object = None     # when price then reached the key level
    h4_breakout_time: object = None     # the breakout that opened this window

    # Key-level ranking factors (Phase 2)
    key_level_price: float = 0.0
    key_level_shape: str = ""
    imbalance_overlap: bool = False
    qmr_test_count: int = 0
    recency_rank: int = 0
    imbalance_fill_size: float = 0.0
    ranking_score: float = 0.0

    # Risk/target mechanics
    stop_loss: float = 0.0
    stop_kind: str = ""                 # "plug_and_play" | "engulfing" | "fourth_man" | "*_kl_fallback"
    risk_pips: float = 0.0
    primary_target: float = 0.0

    # Stop/target decision audit trail -- persisted specifically so the
    # backtest dataset can validate the empirical claims behind these
    # mechanized rules (not just assume them), and so a future "intelligent
    # system" pass has real features to train on rather than only the
    # final win/loss outcome. NOT yet persisted: whether price later
    # revisited an unused natural/default level even after the trade
    # closed (would need a post-close forward scan -- a real follow-up,
    # not implemented here).
    natural_stop_loss: float = 0.0      # what the trigger's own rule would have placed, before any fallback
    stop_fallback_used: bool = False    # True when natural_stop_loss was too wide and the KL fallback fired
    raw_target: float = 0.0             # the plain rr target, before any ERL cap
    erl_price: float | None = None      # the nearest untaken ERL used to cap the target, if any
    erl_capped: bool = False            # True when raw_target was reduced to erl_price

    # Stacking context
    concurrent_open_positions_at_entry: int = 0

    # Outcome
    exit_price: float | None = None
    exit_reason: str | None = None      # "target_hit" | "stop_hit" | "still_open"
    r_multiple: float | None = None
    mae_r: float | None = None          # max adverse excursion, in R
    mfe_r: float | None = None          # max favorable excursion, in R
    status: str = "open"                # "open" | "closed_win" | "closed_loss" | "closed_breakeven"


def write_trade_log(records: list[TradeRecord], path: str):
    if not records:
        return
    fieldnames = [f.name for f in fields(TradeRecord)]
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in records:
            row = {name: _serialize(getattr(r, name)) for name in fieldnames}
            writer.writerow(row)


def summarize(records: list[TradeRecord]) -> dict:
    """Basic aggregate stats -- a starting point, not the full metrics
    Phase 5's runner will eventually report (drawdown, profit factor, etc.)."""
    closed = [r for r in records if r.status in ("closed_win", "closed_loss", "closed_breakeven")]
    wins = [r for r in closed if r.status == "closed_win"]
    r_values = [r.r_multiple for r in closed if r.r_multiple is not None]
    total_r = sum(r_values)

    return {
        "total_trades": len(records),
        "closed_trades": len(closed),
        "wins": len(wins),
        "win_rate": (len(wins) / len(closed)) if closed else None,
        "total_r": total_r,
        "avg_r": (total_r / len(r_values)) if r_values else None,
    }
