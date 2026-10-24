# USDCAD zero-setup rerun: first demonstrated blocker

2026-10-24. Read-only review; no production, fixture or tolerance edits.
The scope-fix report
`reports/teacher_replay_v2_scope_fix/pdf-p15-usdcad-sell-1_source_confirmation.json.gz`
has167stories, zero setups/orders. Raw output inspected at
`/tmp/bishop_teacher_v2_scope_fix/pdf-p15-usdcad-sell-1_source_confirmation.json`.
This is an unresolved diagnostic change, not proof that source p15 is invalid.

## Exact candidate and first blocking rule

Baseline H1 SELL BO `setup_01ff39283b4f5bdcc006d909`, available Jul16
07:00UTC, chose1.40425/1.41561/1.40249. It is a family-compatible generated
candidate, **not an accepted teacher association** with printed source
1.40471/1.40539/1.40129. Its lower reaction evidence was
`bar_b2546b9968a2bd4cdb407ef9`; parent H4 BO was
`structure_event_26593a7fb18ab54798f5a808`; H4 KL was
`level_0fedb52aa06c902259837896`. New policy identity changes these policy-
dependent IDs; stable input-bar IDs and numeric/clock identities link the
compared records without pretending old and new IDs are interchangeable.

The first demonstrated new blocker occurs during **reaction construction**,
before `reaction_for`, episode retirement, risk or target planning:
`not _pool_taken_before(pool, reaction_bar, bs)` rejects the H4 pool because an
earlier H1 candle already took it. It still requires a fresh pool take in the
same lower candle that closes on the intended side of the H4 KL.

Decoded frozen H1 bars (UTC; all segment9):

| Interval Jul16 | Stable bar ID suffix/full where relevant | High | Close | Meaning |
|---|---|---:|---:|---|
|01:00–02:00|`bar_43d80260239e616a4ec0a143`|1.40499|1.40490|First strict take of1.40441 IRL, but closes above sell KL1.40472.|
|02:00–03:00|`bar_c2d6921de3eeff7db9011681`|1.40538|1.40505|Further upward excursion.|
|03:00–04:00|`bar_6136b4c444ac22f198139eb6`|1.40512|1.40468|Touches KL and closes below it; filtered because IRL was taken earlier.|
|04:00–05:00|`bar_b2546b9968a2bd4cdb407ef9`|1.40484|1.40470|Baseline reaction, also filtered for the same earlier take.|
|06:00–07:00|`bar_d0f39e0dc6c68e17dbfcb097`|1.40516|1.40419|Baseline lower BO completion; no surviving reaction now attaches.|

H4 pool1.40441 is known at Jul16 01:00UTC from the Jul15 21:00–Jul16
01:00 H4 candle`bar_8fa428ba5456c9e667cd6d1c`. The raw rerun exposes its two
BO/BOS-alias formation records:
`entry_irl_94cdcfd7ecda4f5310ff3b3f` and
`entry_irl_2ea25baf7e38bb8a038c8789`. Both share this price/candle/availability.
Baseline aliases were`entry_irl_9bb8794c2d47ce79f87902de` and
`entry_irl_796ffbe38c1a0501bb7d978d`.

Current H4 KL`level_731b853a10564dbc451ae666` at1.40472 is BUY on formation,
then changes to SELL at Jul15 21:00UTC through
`structure_event_b6b128360ab87d456efc4b90`.
The same H4 close publishes SELL BO
`structure_event_a0a36f0eedeec2f0608ddea1` at the1.40472 turn reference.
The H4 Jul16 01:00–05:00 candle has high1.40538 and close1.40470, below the KL.
No fresh H4 role-loss event between the liquidity take and05:00 was printed by
the inspected event sequence. These values were reproduced read-only from the
same frozen input/source identity/declared aggregator and current structure
primitives, not inferred from nearest source price.

## Source assessment: consumption fix is incomplete, not a proven no-trade

Source p14–15 explicitly labels H4 breakout with inducement/H4rH4 and H1
breakout CE. Directly inspected source review is
`replay_other_pairs_source_review.md`; source-specific exact bar mapping remains
unverified. The printed plan therefore cannot prove that this alternate-feed
01:00–07:00 sequence is the teacher's actual episode.

However, source E5 transcript293.6–335.9 describes waiting for H4 liquidity,
price trading into the selected KL and then giving a reaction; reaction-candle
closure is optional. E5 376.8–410.0 then seeks a lower BO or sweep+BOS **from
that reacting level**. It does not require first liquidity take, ultimate KL
rejection and lower confirmation to occupy one H1 candle. A single forming H4
reaction can span several lower candles. BE US30 transcript416.3–475.1 gives
fresh BO→liquidity→reaction at the actually used nearby KL→H1BO. T3 USDCAD
1624.0–1646.8 says a contrary H4 break alone did not invalidate the earlier
bullish idea;1651.6–1686.5 describes personal cancellation and fresh nested
reaction/confirmation, rather than a universal first-lower-close veto.

The valid principle “an already-taken pool cannot create an unrelated fresh
liquidity event” was implemented too narrowly if it discards the **first take's
causal evidence** before a later related reaction completes. The rerun's zero
therefore includes a demonstrated potential overconstraint; it is not presently
source-certified retirement of the baseline candidate. This finding neither
requires removing consumption checks nor certifies the old1.40425 entry.

## Minimal next causal rule to establish, not implemented here

Retain one immutable **first observable take** per pool and parent-break episode.
Link that event, not a fictional repeated sweep, to a subsequently observed KL
reaction in the same still-valid episode. Do not require its rejection close in
the very candle that first crossed liquidity. Reject unrelated new episodes
that try to consume the old pool again; retire linking on documented KL role
epoch loss, protected-scope invalidation, data gap, or a positively identified
replacement episode. No arbitrary age/distance, future price fitting, source TP
injection or pending-order retrospective cancellation follows from this rule.

Before implementation, independently settle episode scope and the exact meaning
of first take versus formation aliases; test first take→later reaction→BO,
first take→role loss→old-pool reuse rejected, and new pool/new episode permitted.
A parent already taken in a prior episode must stay unavailable. Source evidence
still needed for this case: FOREXCOM marked candle IDs, whether1.40472 represents
the annotated KL, actual teacher readiness/fill clocks and chosen local stop/
target references. The frozen snapshot13:35UTC cannot supply those facts.

This documents the first blocker for the named baseline candidate. It does not
prove this one predicate alone explains every missing USDCAD candidate or that
relaxing it would produce a complete source match. Preserve both frozen runs
and re-evaluate under a new implementation fingerprint only after the causal
rule and independent regressions are agreed.
