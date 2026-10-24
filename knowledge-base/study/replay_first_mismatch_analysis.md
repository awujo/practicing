# First alternate-feed replay mismatch analysis

2026-10-24. Read-only diagnosis of saved `reports/teacher_replay_v2/` outputs.
No engine, source fixture, tolerance or policy changed during the fingerprint-
guarded run. This note compares causal records with the independent PDF reviews;
it does not promote numerically close candidates to teacher matches.

## Frozen scope and interpretation

Read source-confirmation reports for `pdf-p08-eurgbp-buy-1`,
`pdf-p37-eurgbp-sell-1`, `pdf-p15-usdcad-sell-1`, and the subsequently arrived
`pdf-p19-gbpjpy-buy-1`. All are explicitly
`ALTERNATE_FEED_PLAN_DIAGNOSTIC_NOT_ACCEPTANCE`, with strict replay UNRESOLVED.
They identify commit7fe38461f729e32b9bcefcf882d46ee398981413 and implementation
SHA2563a69a2f5f6f1b2b468daea0b3175a8f586ea2703ea77a9013432c68d9cd506bd.
The confirmation profile uses `context_liquidity` protection, `nearest_erl`,
0.5unit structural padding, exact OC, and explicit OUR CHOICE detector geometry.
It does **not** inject each example's printed teacher stop. Observation field
`mode=teacher_source_stop` is a legacy risk-to-replay mapping, not evidence the
source stop was reproduced; `risk_profile` and actual coordinates are decisive.

Source FOREXCOM differs from the frozen alternate BID feed. Scan starts are
exploratory windows; as_of is the converted source snapshot minute, not verified
setup/fill time. H1 resolution cannot establish finer ordering. Generated
stories include many H4-local origins alongside Daily stories; aggregate signal
or profitable-outcome counts are not source-example fidelity measures.
Plan groups include unresolved/unselected candidates as well as executable
orders; a group is not proof of a fill or teacher participation.

To decode selected causal IDs, read the frozen input with its recorded source
identity and existing aggregator (plus structure primitives for TURN_LEG IDs).
These read-only operations reproduced the exact IDs cited below. No new
acquisition, candle edits, alternative anchor or source-price fitting occurred.
Primary source reviews: `replay_p08_source_review.md`,
`replay_eurgbp_other_source_review.md`, `replay_other_pairs_source_review.md`.

## p08: adjacent standing-pattern candidate, old reaction wick controls risk

The report records H2 BUY `confirmation_standing_extreme` at
2026-07-23 13:00UTC:

- setup`setup_07769fe0ff024bf492b17bfc`,
  story`story_882d701445d50bd5134d376e`,
  KL`level_ac8cb2a8d64877c00adcf5d2`;
- generated0.85313 /0.85214 /0.85442 versus source0.85315 /0.85289 /0.85447;
- entry difference−0.2pip, stop−7.5pips, target−0.5pip. Generated risk9.9pips
  differs from source2.6pips, irrespective of the near entry/target coordinates.

The mechanism is explicit, not an unexplained feed discrepancy. Pattern
reference`bar_6e8eb9c3601b97e018cbda0d` is H2 Jul23 09:00–11:00UTC with
low0.85298/high0.85370/close0.85313. Following
`bar_3bea7a3ca9d271a39d6d07e4` is11:00–13:00 with
low0.85284/high0.85335/close0.85327. The latter takes the former **low** and
leaves its **high** standing: the implemented restricted adjacent E5 V-buy
geometry. Source p08 says **High swept / Low standing / V-shaped KL / 4thman's
CE**. Its exact reference pair remains unresolved. Therefore this generated
route cannot be called the source's named candle sequence merely because it
buys near0.85315. The report itself preserves `pdf_p8_mapping=UNRESOLVED`.

Risk includes three distinct sources of protection:

1. H2 range protected pool`turn_pool_9ffcede7681643053d85f7fa` at0.85248,
   formed Jul22 15:00 and available17:00UTC;
2. earlier H4-related reaction evidence, recorded as `pattern_wick`,
   `bar_5cbd2dbd369d30a1dd5833f8` at0.85219. Decoding confirms this is a
   **lower H2 observation** Jul22 21:00–23:00UTC, not literally an H4 bar;
3. the later H2 pattern wicks0.85298/0.85284 and nearby objects.

Minimum protected value0.85219 minus5ticks (0.5pip) yields the actual0.85214
stop. Thus the old reaction linked to H4 context, rather than only the new
standing pattern's low, materially widens the stop. The current implementation
carries that reaction wick into risk; the PDF does not prove that the teacher
selected the same old protection boundary. This is a concrete risk-association
question to inspect after the run, not permission to move the stop to fit p08.

Target0.85442 comes from H2 endpoint
`turn_pool_f3603f190d6c5598ee30837b` (HIGH formed Jul23 07:00, available09:00),
range`range_07447273a49744ced4520e66`,
version`range_version_9180eccdb960582cf17ad7c4`.
This is an explicit generated entry-TF ERL. Story destination is null; it was
not the source0.85447 inserted as a target. Feed/endpoint selection can explain
a small coordinate difference, but source endpoint identity is still unverified.

## p37: exact printed entry, different family, unresolved ERL

Two H1 SELL groups at May29 15:00UTC exactly print0.86580:

- BO`setup_12bc98e395e9f1c0869408b6`, event
  `structure_event_0ba4e7dd935dfca73ff48890`;
- sweep+BOS`setup_17eccf81d9f4b5f1fac4994e`, event
  `structure_event_2e02ab425ff43687bd869a72`.

Both use KL`level_4967b4c03b31d8be3d21b106`, generated stop0.86719 and null
target. Source p37 explicitly labels **H1 Engulfing Confirmation Entry** with
stop0.86611/target0.86451. BO or sweep+BOS is not an engulf match. Nor does a
May29 generated eligibility become the teacher's decision time from a Jun01
snapshot; source clock association remains unverified.

Their risk maximum is `pattern_wick`
`bar_34b8b5818240780098359df9` at0.86714 (decoded H1 May28
16:00–17:00UTC), plus0.5pip→0.86719. The other pattern bar high0.86685 and
nearby KLs are lower and do not determine the stop. This produces13.9pip risk
instead of source3.1pips; stop is10.8pips higher than the printed source stop.
Both records show `entry_range_id=null`, empty `target_candidates` and
`target_unresolved`. They remain UNRESOLVED; the engine did not simply use the
printed0.86451 to make an order.

The same batch has `confirmation_engulfed_oc` at0.86588, but that is another
KL/model and still lacks target. A Jun01 09:00 engulfed-OC group at0.86588 has
stop0.86821 and entry-ERL0.86513, again a distinct plan. Source “engulfing” does
not by itself identify whether core A-mitigation or OC-disrespect is intended.
The source's drawn completed short and mobile connected entry/exit evidence
must be causally mapped; no exact-price or best-return selection can do that.

## p15: source breakout exists as a family, but no exact plan association

There are32 H1 SELL plan groups in the saved report; none has printed entry
1.40471. Source is H1 breakout CE1.40471 /1.40539 /1.40129, with mobile close
around1.4024 distinct from the later chart-target excursion.

One numerical neighbor at Jul16 09:00UTC is
`engulf_av_retest`, `setup_05acbffa67443c4616be875e`:
1.40465 /1.41561 /1.40249. Another group at the same entry is standing-extreme
`setup_15a5e59b54a64e1d2fd58580`. A0.6pip entry difference does not associate
these **wrong-family** candidates with the source's breakout entry. Both stops
are102.2pips above the source stop and target12pips above source TP.

A same-date family-compatible BO at07:00UTC,
`setup_01ff39283b4f5bdcc006d909`, instead chooses1.40425 /1.41561 /1.40249.
Entry differs−4.6pips and protection again differs materially. This is a
candidate for inspecting structure/KL lineage, not an accepted source match.
Later BO groups move the chosen entry to1.40410 (10:00),1.40342 (12:00), and
1.40322 (13:00, target unresolved). The declining sequence shows distinct
positive break episodes and selected levels, not one recovered source order.

The large1.41561 stop has a precise cause:
`turn_pool_7a2ab7844ae8cff5ba011134`, H1 HIGH1.41556, formed Jul13
23:00 and available Jul14 00:00UTC, remains the selected range's protected wick.
Its0.5pip pad yields1.41561. Range lineage is
`range_60ff7458117191719cb975ac`. For the09:00 standing group its version is
`range_version_676e7965453beaddc31af953`. At earlier01:00/04:00 candidates an
older reaction observation`bar_a70f1c5cbe924838e2b5fde6` (H1 Jul13
19:00–20:00, high1.41602) dominates instead, producing1.41607. These are
three-day-old protected/reaction references carried into Jul16 entry risk,
not rounding discrepancies in the local1.40539 source stop.

Target1.40249 is endpoint LOW
`turn_pool_ad71e3447bbacabbdc8fa83c`, formed Jul15 18:00, available19:00UTC.
This is generated local ERL12pips nearer than the source1.40129. It happens to
be near the qualitative mobile exit around1.4024; that resemblance **does not**
prove the bot recovered discretionary teacher management. The source's original
plan target and depicted mobile close remain different observations. Some
story destinations are higher opposite-side prices; they are recorded
separately and are not used as these entry targets.

## Early p19 diagnostic, not a first/second source mapping

The first p19 source report arrived during this review. Its strict result is
also UNRESOLVED. Source two H1 plans are216.877/216.700/218.014 and
217.255/217.088/218.007, independently distinguished in the source review.
The report contains different BO episodes; illustrative examples include:

| Generated episode | Plan | Causal risk/target issue |
|---|---|---|
| Jul14 02:00, `setup_195e137c7ee4155a8827a692` |216.863 /216.367 /null| Protected`turn_pool_5a3dede285cef7b40bfa4c9d`216.372 determines stop after−0.005; active range`range_b721da4c5a89c1bccaa607a4` exists but no valid target candidate. |
| Jul15 00:00, `setup_001b89a46bee12fe2d872621` |217.274 /216.931 /null| Reaction`bar_70e4e0434e7c037bfd983e8e`216.936 determines stop after−0.005; entry range null and target unresolved. |

Those entry coordinates lie near separate source drawings, but neither has a
source target, source stop or verified source clock/candle linkage. They are
not promoted as the first and second teacher entries. The second-specific
report and stronger source mapping should be assessed separately. Source phone
has three entries and an exit below both tools; two boxes are not two verified
bot execution matches.

## Conclusions supported by these records

The mismatch is not simply “no setups”: the diagnostic produces many named
families and near/exact entries. Demonstrated problems are (a) family/reference
identity unverified or different, especially p08/p37; (b) old reaction/protected
range objects materially dominating stop selection; (c) nearer or unavailable
causal ERL instead of the source drawn target; (d) missing source setup clocks
and cross-feed/candle alignment. Which differences are detector-policy defects
versus incorrect source association requires the explicit source candle mapping;
this note does not claim the feed alone caused them.

After all fingerprint-guarded runs finish, independently inspect the invariant
that entry protection uses the intended **entry episode's** relevant old/nearby
objects, and whether major-range migration/reaction renewal selected the right
scope. Audit source model/candle pair before changing engulf/standing geometry.
Then add causal regression checks for proven defects and rerun the same frozen
cases with new implementation identity. Do not change printed prices, invent
setup timestamps, widen tolerances, turn missing ERL into source TP, or label
the nearest generated candidate a pass. Owner fixed11 is a separate operating
result and cannot repair teacher-source-stop fidelity.
