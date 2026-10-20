# Independent final engine integration review

Reviewed the offline engine assembly, aggregate coverage, bias/target integration,
setup availability, paper execution, CLI and replay acceptance gates. These are
engineering checks; synthetic tests are not teacher examples.

## Findings

1. **Leading partial higher-timeframe bars could enter signal generation.**
   Complete coverage beginning June 1 at 00:00 UTC does not cover the opening
   three hours of the New York daily and H4 bars containing that timestamp.
   The actual retained EURGBP feed reproduced a truncated daily/H4 first bar
   entering bias analysis. The corrected engine uses
   `completed_from_complete_history` after proving global H1 coverage and drops
   each incomplete first aggregate independently. The public clock-completion
   helper retains its documented clock-only contract. Independent tests cover
   the actual-feed integration, D/H2 boundaries, an entirely partial day, H1
   preservation and a November monthly boundary spanning a closed weekend and
   the autumn DST change. All five pass.

2. **No-trade acceptance could overlook an order issued during the source
   window if its observation or fill arrived afterward.** An explicit NO_TRADE
   record could then produce a false PASS. Independent reproductions use an
   order issued at 10:15 within a 10:00–11:00 source window, observed or filled
   at 12:00. Both regression tests initially failed. The corrected gate checks
   the actionable interval from setup availability to pending end, including
   terminal expired/cancelled states; both regressions now pass.

## Other reviewed contracts

- Contexts with opposite sides published at the same clock are explicitly
  skipped rather than selecting an arbitrary direction.
- Pending expiry and story cancellation prevent subsequent fills; an already
  filled position retains its own exits. Subhour availability/cancellation
  cannot establish an H1 path and is censored.
- Costs are explicit. BUY fills use ask, SELL exits use ask, stops include
  adverse opening gaps/slippage, commission is deducted once, same-bar
  ambiguity is conservative, and fill-bar targets are censored.
- A pending order has no invented fill clock. Trade acceptance does not replace
  missing fill time with the later observation timestamp.
- Targets carry origin-timeframe role/availability; invalidated opposing levels
  are excluded. The target policy is explicitly origin KL, not a claimed
  implementation of every teacher ERL rule.

## Evidence limits

The retained input is IC Markets BID H1, not the FOREXCOM chart feed shown in
some source examples. Different feed values and the unimplemented fourth-man
CE route must remain visible explanations, not price tolerances fitted to
force a pass. All 40 teaching observations remain UNRESOLVED. No teacher
example has been promoted to a verified match by this review.

The engine computes supported, unranked paper alternatives. It is not a
portfolio, a live broker system, or complete implementation of all source
routes. Unsupported direct H4/H2, ERL, fourth-man/other continuation and finer
entry routes require separate source-grounded implementation and replay.

## Final validation

`python -m pytest -q` — **204 passed** (4.01 seconds in this workspace).
The seven tests in `tests/test_final_engine_review.py` independently cover the
leading aggregate correction and no-trade acceptance regressions. No remaining
material blocker was confirmed within this offline milestone. This does not
certify full strategy fidelity, source acceptance or live readiness.

## Subsequent source-study correction

The full-study phase re-opened PDFp8 and checked the entry lessons. “4thman's
CE” is attribution plus a high-swept/low-standing V-level description; this
label alone does not prove a distinct algorithm. The earlier reference above
to an unimplemented fourth-man route is provisional and must not be used as
an established explanation for the zero-setup diagnostic. Source-to-rule
mapping remains open. The engineering test findings are unaffected.
