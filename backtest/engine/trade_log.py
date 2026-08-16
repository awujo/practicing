"""
Structured per-trade logging.

Built specifically so the eventual backtest dataset is more than a win/
loss tally -- it's a real feature set for training a model later. Every
closed trade gets logged with its full multi-timeframe bias context, the
key-level ranking factors that led to the entry (Phase 2's 4 factors),
the entry pattern that fired, which stop-loss rule was used, and --
critically -- MAE/MFE (max adverse/favorable excursion during the
trade's life), not just the final win/loss label. STRATEGY.md's own
honesty about near-misses ("tight stops have genuinely almost gotten
stopped out before the correct move played out", Section 6) is exactly
the kind of signal a bare win/loss label throws away; MAE captures it
directly, in R-multiples so it's comparable across instruments/pip sizes.
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

    # Entry context
    direction: object = None            # Direction
    entry_timeframe: str = ""
    entry_price: float = 0.0
    entry_pattern: str = ""             # "direct_mitigation" | "fresh_irl_required" | "nested_disrespect"
    entry_style: str = ""               # "aggressive" | "conservative"
    trade_kind: str = ""                # "origin" | "continuation" -- independent of trigger_type
    trigger_type: str = ""              # "plug_and_play" | "engulfing" | "fourth_man" -- see entries.py

    # Multi-timeframe bias context at entry
    bias_monthly: object = None         # Direction | None
    bias_weekly: object = None
    bias_daily: object = None
    bias_h4: object = None
    bias_h1: object = None
    effective_bias_timeframe: str | None = None
    aligned_timeframes: str = ""        # comma-joined subset of "Weekly,Daily,H4" -- see _aligned_timeframes()

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
