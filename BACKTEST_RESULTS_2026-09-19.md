# First honest backtest, 2026-09-19

The first measurement of this strategy taken after the 2026-09-18 review
removed the look-ahead. Every number this project produced before today
was computed by an engine that could see up to a week past its own entry
(see CODE_REVIEW_2026-09-18.md, finding 1) and none of them are
comparable to these.

Run on the VPS with the bots stopped for the weekend, over full cached
Dukascopy history, with the flags the live bots actually launch with:
`origin_kind=any`, close-based sweep breaks, `avoid_rollover_entries`,
`min_reward_r=1.0`, `stop_anchor=trigger_wick`.

## Pooled, every instrument

| period | trades | win | total | R/trade | net |
|---|---:|---:|---:|---:|---:|
| 2025 | 475 | 41.9% | +173.4R | 0.37 | **0.25** |
| 2026 (9 months) | 342 | 41.5% | +114.6R | 0.34 | **0.22** |
| all-time | 9,616 | 41.0% | +3,116.1R | 0.32 | **0.20** |

`net` subtracts a flat 0.12R per round trip for spread, which the engine
does not model. It is an assumption, not a measurement.

**The thing that matters most here is not the size of the edge, it is
that the three rows agree.** 9,616 trades say 0.32 R/trade; the last
twelve months say 0.34; last year says 0.37. A strategy that made its
money in some old regime and nothing since would show a strong all-time
row and flat recent ones. This does not.

41% win rate with a positive expectancy is the expected shape: targets
are 3:1 capped at the nearest external liquidity, so the winners are
bigger than the losers.

## Per instrument (swing, full history)

Every pair measured was positive. Best to worst:

    NZDUSD 0.51   AUDCAD 0.47   EURGBP 0.45   GBPAUD 0.44   USDCHF 0.42
    USDJPY 0.40   EURUSD 0.37   GBPJPY 0.37   USDCAD 0.34   GBPCHF 0.31
    GBPUSD 0.29   EURCHF 0.29   EURCAD 0.29   GBPCAD 0.29   EURNZD 0.27
    EURJPY 0.25   AUDUSD 0.21   GBPNZD 0.20

(R/trade gross. Subtract ~0.12 for spread; GBPNZD and AUDUSD are then
marginal at best, and GBPNZD is also the instrument that never converged
on a bounded history window -- see OPERATIONS_LOG 2026-09-13.)

## What this does NOT account for

Stated plainly, because a 3,116R headline invites over-reading:

- **No slippage.** The 54-point GBPAUD fill that turned $1,000 of
  intended risk into a $1,530 loss cannot happen in this engine.
- **No correlation.** EURUSD, GBPUSD and AUDUSD losing together on one
  dollar move is invisible here, and it is exactly what a 4% daily
  drawdown limit is sensitive to.
- **No concurrency or margin limit.** It records how many positions were
  open and never refuses a trade because of it.
- **Idealised fills** at the trigger candle's close.
- **Spread is a flat guess**, kinder than reality on GBPNZD and harsher
  on EURUSD.

## What it does mean

~475 trades a year pooled, at ~0.25R net, is on the order of 100R of
expectancy a year across the portfolio. Per pair it is thin -- about 13
setups a year -- which is the frequency complaint, and it is legitimate.
The portfolio is the unit, not the pair.

## Open question this does not answer

Whether ~13 setups per pair per year is the strategy or the
implementation. The engine currently sources post-breakout liquidity
from a fractal SWING detector, not from single candle liquidity, because
the single-candle implementation measured worse and was parked. If the
taught method fires more often than this, the missing setups are most
likely there. That is what the video study is for.
