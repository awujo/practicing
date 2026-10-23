# Handoff from the full source study to implementation

2026-10-23. This is the build contract checklist, not evidence that the current
partial engine implements the teaching. The source pass is recorded in
`FULL_STUDY_PROGRESS.md` and the expanded `../STRATEGY.md`.

## Required distinctions in the build

| Area | Source-backed requirement | What the implementation must expose |
|---|---|---|
| Price/structure | Closing-price structural references, wick liquidity, major/minor ranges; protected-origin migration after the demonstrated structural break. | Separate reference types, causal availability and initialization state. No blind latest-local-turn substitution for major structure. |
| A/V versus OC | Closing-price shapes and explicit OC candle junctions are related, distinct objects. | Formation definition and availability; no hidden universal opposite-colour or exact-shared-open rule. |
| Context | KL reaction or prior-candle sweep origins, positive lower-TF confirmation, weekly-level/Daily fallback, context-specific engulf cascade. | Story TF, level TF, confirming TF, source profile, known facts and provisional/confirmed state. |
| Clocks | Model-specific origin/breakout/reaction closure; same-day confirmation permitted; personal intrabar confirmation differs from closed H4 breakout prerequisite. | Occurrence, reaction relationship and eligibility separately. Do not require every lower pattern to begin after origin close or use old unrelated breaks. |
| Lifecycle | Origin destination does not flip automatically; positive new-direction structure required. Lower counter-break, stopped entry and context cancellation are different facts. | Story, retracement, invalidation and pending-order state with explicit reasons and times. |
| Liquidity | Single candle, later/series and structural forms; IRL/ERL roles evolve. | Source interval, reference candle/range, role and availability. No universal exactly-next inside-bar gate. |
| Entries | H4 direct, H2 direct, lower confirmation; BO, sweep+BOS, engulfed OC, high/low-standing candle routes; core engulf/retest alternatives and continuation. | Named source model and chosen operating policy, without hindsight timeframe/model selection. |
| Timeframes/assets | The material includes H3/M45/M30/M15/M5 and other refinements, metals, indices, oil, crypto and synthetics. | Explicit supported TFs/assets, base-data resolution and instrument calendar/price-unit conventions. Unsupported scope cannot silently pass examples. |
| Stops | Source structural protection, relevant liquidity/KLs and separate aggressive fixed-stop preference. | Initial stop reason and protected objects; source stop versus owner experiment. A position box is not a proven FVG definition. |
| Targets/management | Entry-TF ERL, prior extreme, story-origin KL, fixed-R routine and manual management are distinct. | Initial plan plus timestamped amendments, break-even/partials/manual exits only when actually specified. No MFE booked as realized return. |
| Orders | Missed, pending, canceled, replaced, filled, loss and retry are demonstrated. | Persistent event history; new entries require new eligibility, not automatic retries. Source case status preserved. |
| Infrastructure | Isolated Bishop persistence; shared cTrader tokens read-only; paper first. | No Kevin state changes or token refresh, no live activation during the offline build. |

## Numerical policies to specify explicitly before their code

The source does not uniquely prescribe these constants or algorithms. They
need named, auditable choices with causal behaviour; choosing them does not
make them teacher facts:

- Structural seed/turn confirmation, equal-close ties, major/local reference
  promotion and sufficient warmup; unknown initialization must stay unknown.
- Gap/equality handling for levels, competing-level ranking, reuse and prior
  sponsorship measurement. Preserve the disputed plug sentence as uncertain.
- Impulse/proximity measures and imbalance/FVG construction, overlap, fill and
  invalidation. Avoid one universal impulse cutoff: the source scopes differ.
- Candle-series liquidity grouping and competing IRL/ERL selection.
- Intrabar versus closed-bar modelling, minimum input resolution and censoring
  when OHLC cannot establish order. Never invent exact fill clocks.
- Operating preset, pending expiry, exposure/stacking caps, costs and symbol
  units/calendars. Source alternatives remain visible outside that preset.

## Build sequence following the completed source review

1. Write the causal event/data contracts and named numerical policies above.
2. Implement all source routes and their shared structure/lifecycle layer,
   preserving provenance and eligibility clocks; independently review changes.
3. Assemble offline execution and paper persistence/UI around the complete
   detector. Keep broker execution and alert activation disabled.
4. Once the system is built, replay the independently reconstructed teaching
   cases and explain/correct every mismatch. Keep source profile separate from
   the owner's aggressive preset. Do not fit expectations or tolerances.
5. Run broader chronological cost-aware backtests only with explicit coverage,
   then validate paper operation before any later activation.

Historical feed/timing facts still absent from a screenshot are later replay
reconstruction needs, not permission to invent fills or promise exact matches.
