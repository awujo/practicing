"""
Combines the 4 factors STRATEGY.md's key-level ranking discussion
surfaces (Section 5) into a scored/ranked candidate list -- and,
deliberately, does NOT hardcode a single "correct" combination rule.
STRATEGY.md never specifies how these four factors trade off when they
conflict (flagged explicitly in Section 9 as unresolved tension), and the
decision on this project has been to let backtesting resolve it
empirically rather than guess a formula. So every factor is exposed as
an independent, inspectable value on RankedCandidate, and
score_candidates() combines them via a CALLER-SUPPLIED weight dict --
DEFAULT_WEIGHTS (equal weighting) is a placeholder to have *something*
runnable, not a claim about which combination is actually correct. Sweep
the weights during backtesting; that's the whole point of exposing them
as a parameter instead of baking in a guess.

The 4 factors (STRATEGY.md Section 5):
1. imbalance_overlap   -- a key level with an overlapping imbalance/FVG
   performs better ("quality signal", Video 11).
2. recency              -- prefer the more recently disrespected level
   over a more distant "extreme" one, when both are candidates.
3. test_count (QMR)      -- a level tested/respected 2+ times before
   disrespect is preferred (~80%, Video 17) over one broken on first test.
4. imbalance_fill_size  -- a MORE DISTANT level with a LARGER unfilled
   imbalance can override the nearer candidate entirely (Bishop,
   "Repeating System") -- price skips the near one to fill the bigger gap.

Video 18's "default to the extreme when genuinely uncertain" is a
separate real-time fallback, not a 5th additive factor -- exposed here as
`default_to_extreme()`, a tie-breaker for when the weighted scores don't
clearly separate the candidates, not a competing primary rule (Section 5
already frames it that way).
"""

from dataclasses import dataclass

from .key_levels import KeyLevel
from .imbalance import Imbalance, overlaps_level

DEFAULT_WEIGHTS = {
    "imbalance_overlap": 0.25,
    "recency": 0.25,
    "test_count": 0.25,
    "imbalance_fill_size": 0.25,
}


@dataclass(frozen=True)
class RankedCandidate:
    level: KeyLevel
    imbalance_overlap: bool
    test_count: int
    recency_rank: int           # 0 = most recent among this candidate set
    imbalance_fill_size: float  # size of the largest overlapping imbalance, 0 if none
    score: float


def score_candidates(levels_with_tests: list[tuple[KeyLevel, int]],
                      imbalances: list[Imbalance],
                      weights: dict | None = None) -> list[RankedCandidate]:
    """
    levels_with_tests: (KeyLevel, test_count) pairs -- test_count from
    key_levels.count_tests_before_disrespect().

    Returns candidates sorted by score, highest (most preferred) first.
    """
    weights = weights or DEFAULT_WEIGHTS
    if not levels_with_tests:
        return []

    by_recency = sorted(levels_with_tests, key=lambda lt: lt[0].time, reverse=True)
    recency_rank_by_time = {lt[0].time: i for i, lt in enumerate(by_recency)}
    total = len(levels_with_tests)

    all_fill_sizes = [im.high - im.low for im in imbalances]
    max_fill = max(all_fill_sizes, default=0.0) or 1e-9

    ranked = []
    for level, test_count in levels_with_tests:
        overlapping = [im for im in imbalances if overlaps_level(im, level.price)]
        imbalance_overlap = len(overlapping) > 0
        fill_size = max((im.high - im.low for im in overlapping), default=0.0)

        rank = recency_rank_by_time[level.time]
        recency_score = 1.0 if total <= 1 else 1.0 - (rank / (total - 1))
        test_score = min(test_count / 2, 1.0)  # QMR threshold is 2+ -- normalize against that
        overlap_score = 1.0 if imbalance_overlap else 0.0
        fill_score = fill_size / max_fill

        score = (
            weights["imbalance_overlap"] * overlap_score
            + weights["recency"] * recency_score
            + weights["test_count"] * test_score
            + weights["imbalance_fill_size"] * fill_score
        )

        ranked.append(RankedCandidate(
            level=level,
            imbalance_overlap=imbalance_overlap,
            test_count=test_count,
            recency_rank=rank,
            imbalance_fill_size=fill_size,
            score=score,
        ))

    return sorted(ranked, key=lambda r: r.score, reverse=True)


def default_to_extreme(candidates: list[KeyLevel], current_price: float) -> KeyLevel:
    """Video 18's real-time fallback: when ranking doesn't clearly resolve
    which level price returns to, default to the most distant ('extreme')
    candidate from current price."""
    if not candidates:
        raise ValueError("candidates must be non-empty")
    return max(candidates, key=lambda lvl: abs(lvl.price - current_price))
