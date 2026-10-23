# Bishop SLK — source specification v0.2

2026-10-23. All 28 unique canonical video transcripts have end-to-end study
ledgers. Systematic visual coverage, the full-source synthesis and independent
cross-checks are recorded below; their exact coverage is authoritative. Further
engine implementation has remained paused during the owner's study-first phase.
Independent review now accepts the declared source-coverage pass and handoff to
named implementation contracts. The existing partial engine is not a source of
trading rules or a certified replication; remaining source uncertainty and
automation choices stay explicit.

The unchanged prior rulebook is preserved as
[STRATEGY_LEGACY.md](study/STRATEGY_LEGACY.md), SHA256
`e1f8568259fccba2e742d53e92417278b58b38ff2de840db557fdb9576ec3a5a`.
Its “fully processed / zero contradictions / knowledge base complete” claims are
superseded by the explicit coverage below.

## 1. Evidence, scope and acceptance contract

Full-study ledgers distinguish actual source coverage from interpretation:

- [Inventory and progress](study/FULL_STUDY_PROGRESS.md),
  [hashed source inventory](study/full_source_inventory.json) and
  [working synthesis](study/FULL_SOURCE_SYNTHESIS.md).
- [Course 1–8](study/full_course_01_08.md), plus
  [course 4–6 visual supplement](study/full_course_04_06_visual_supplement.md).
- [Bias/story course 9–13,16–18](study/full_bias_story_study.md), plus
  [course 9/18 visual supplement](study/full_course_09_18_visual_supplement.md).
- [Entry 14–15 and plug](study/full_entry_study.md).
- [Nine Bishop sessions](study/full_session_study.md), plus
  [BuildingBias2/routine visual supplement](study/full_session_b2_routine_visual_supplement.md).
- [All supplementary notes,60PDFpages and four original images](study/full_supplement_study.md).
- [Independent targeted verification](study/full_study_verification.md) and
  [primary cross-check](study/full_primary_crosscheck.md).

The earlier `course_verified.md`, `bishop_verified.md`, `plug_verified.md` and
`source_crosscheck.md` remain first-pass evidence ledgers, not full-study
certificates. `C01…C27`/`B01…B15` below retain those original citation IDs; full
ledgers provide expanded rules, source qualifications and chronological examples.
Confirmed/corrected/new are source-review labels, not engine replay passes.

All course/plug and Bishop frame sets now use actual sourcePTS timestamps.
[Course manifest](study/course_frame_manifest.json) records 19 assets, 2,481 frames
and 630 sheets; [Bishop manifest](study/bishop_frame_manifest.json) records nine
unique sessions, 964 frames/244 sheets plus the duplicate Part3. Total unique
coverage available is 3,445 sampled frames/874 sheets across 28 videos.
Old course-image citations refer to Gitcommit`dd91b14`; oldfps pictures could
be around 7.5 seconds later than burned labels. Reader ledgers explicitly
distinguish versions actually viewed. Corrected publishing does not certify
continuous native-video inspection or exact intrabar fill times.

**Hard acceptance requirement (owner): every verified teaching example must
match its documented model.** A full match includes directional context, setup
sequence/timing, instrument and timeframe, execution or missed/no-trade status,
entry, stop and target. Partial field agreement is not a full pass. Record losses
and missed entries too. Never widen tolerances or rewrite expected source values
to obtain a pass. Missing/unreadable facts stay unresolved; they are not passes.
Fixtures need independent source verification before promotion to historical
acceptance cases. Synthetic rule tests cannot stand in for actual chart replay.

## 2. Price representation and primitives

| Rule | Status | Source-backed definition | Evidence |
|---|---|---|---|
| S01 | confirmed | KLs are specific body/closing prices: A peaks, V troughs, and open-close junctions of consecutive same-direction candles. Do not replace them with whole order-block boxes. Use wicks separately for tap/sweep evidence. | C11; v11@60–145,488–491; F v11/sheet_003; B01 |
| S02 | confirmed | A normally sells; V normally buys; bullish/bearish OC levels are also usable. An impulsive body close through a level changes its usable role for retest. Keep shape, formation time, role and role-change time auditable. | C12–C13; v11@151–406; B01 |
| S03 | confirmed | Bullish structure HH/HL; bearish LH/LL. In bullish context HH is ERL and HL is IRL/structural reference; mirror for bearish. Liquidity roles depend on the range stage. | C01,C27; v3@48–170,246–284; v18@94–118,248–320 |
| S04 | corrected | Structural break requires a body close beyond the reference; wick excursion with close back inside is a sweep. One or two structural points may be broken; two is not universally required. | C02–C03; v3@298–323,427–535,566–642 |
| S05 | confirmed | A defined range starts with sweep+break. Price progression IRL→ERL→new IRL; external sweep and external body breakout are different events. Consolidation alone has no direction; manipulation+displacement and direct breakout+retest are alternative exits. | C04,C06; v3@647–993; v7@305–326,1683–1734,1866–2026 |
| S06 | confirmed | Previous D/W/M candle highs/lows and Asian highs/lows are liquidity forms and potential draws. A low sweep can imply high as draw, mirrored bearish, subject to structural context and nearer-target guard. | C07; v5@1100–1313; B04,B13 |
| S07 | corrected | Single next candle is one liquidity model, not a universal detector: a candle series or advanced structure may supply liquidity. A candle that first takes ERL may subsequently supply IRL. | B09; repeat@263.9–355.9; P@1000–1051,1114–1248; C27 |

Exact pivot/fractal order, impulse size, shared-price tolerances and mathematical
imbalance boundaries are unresolved numerical definitions (§8). A detector using
such values must label them implementation choices instead of source facts.

## 3. Establishing directional context (initial stories)

The following routes are distinct. Preserve the **story origin timeframe** and
**level origin timeframe** separately. A Daily story using a Weekly level is
not proof that Weekly direction itself has been confirmed.

| Rule | Status | Required sequence | Evidence |
|---|---|---|---|
| D01 | confirmed | Origin-TF KL rejection and candle close; check the next lower TF for a related positive breakout OR sweep+break/BOS in the proposed direction, observable before eligibility. A wick reaction alone is unconfirmed. Main ladders include M→W, W→D and D→H4. | C09,C14; v9@76–151,574–672; B02; P@547–601,744–756 |
| D02 | confirmed | Alternative origin: sweep previous candle high/low, close appropriately, and check for related next-lower-TF breakout OR sweep+BOS observable before eligibility. Do not require a KL rejection AND a prior-candle sweep for every case. | B04; bias2@408.5–478.4,536.4–615.8; P@618–650,696–738 |
| D03 | corrected | Earlier course passages permit an engulfing pathway. Later clarification: W rejection→D engulf is context; descend further and require H4 breakout or sweep+break for synchronization. Do not treat engulfing alone as a completed structural flip. | C24; v17@1133–1191,1280–1318 |
| D04 | new | If W rejection never gets its D breakout, a D rejection from that same W level can anchor a Daily story, requiring H4 breakout/sweep+break. Plug-and-play specifically describes at least two D rejections; do not silently generalize that count to every earlier example. | B03; bias1@774.6–847.6; P@1482–1504,1538–1564,1603–1629 |
| D05 | corrected | Same-day OR next-day lower-TF breakout can confirm a D rejection. Do not port Kevin's next-day-only default. | C25; v17@1248–1272 |
| D06 | corrected | Higher-TF agreement is preferred context, but universal W>D veto is contradicted by explicit counter-weekly/D+H4 teaching examples. Keep `aligned` and `counter_weekly/retracement` routes distinguishable. Selecting aligned-only operation does not remove exception examples from validation. | C10; v9@754–828; B05; routine@394.1–421.5; what-next@455.2–480.0 |

Candle completion is attached to each event's own timeframe. A closed H1 bar
cannot establish that its enclosing H4/D/W candle has closed. The engine must
never use future closes or a pivot before its confirmation becomes observable.
Narrative “then check the lower TF” does not impose that its confirming pattern
starts strictly after the origin candle closes; preserve same-day source
allowance and separate occurrence, relation-to-reaction and availability clocks.

## 4. Continuing and ending a story

| Rule | Status | Required behavior | Evidence |
|---|---|---|---|
| L01 | confirmed | A continuation can retest a level previously used against the move and subsequently disrespected by a directional body close. Nearby liquidity and imbalance overlap support selection; the most recent breakout establishes direction but is not always the exact entry level. | C16,C26; v14@263–355; v18@1402–1449; P@841–983 |
| L02 | corrected | Existing story reaching another KL on its origin TF and rejecting does not flip automatically. Require next-lower-TF breakout or sweep+break in the new direction. Engulfing/OC disrespect alone may supply a retracement entry but cannot validate the flip. | C23; v17@1203–1234,1339–1454 |
| L03 | confirmed | Next KL on the STORY ORIGIN TF is an ideal story destination: D→next D KL, H4→next H4 KL even if entry is H1. Keep story destination separate from nearer ERL trade target and fixed-R management. | C22; v16@822–970 |
| L04 | confirmed | A missed retest remains missed. Subsequent new breakout can produce a new setup. New valid continuation/confirmation may add another position; one trade per story is not a universal teacher rule. | C19; v14@376–419,787–825; B15 |
| L05 | corrected | A counter-structural sweep must not assume a full opposite-range target. Nearby liquidity/KL may stop the retracement before dominant flow resumes. | B13; bias2@815.5–890.0,960.5–980.5 |

An automated expiry or maximum holding period is an implementation policy until
source evidence settles it; it must not silently masquerade as a teaching event.

## 5. Entry models (separate named paths)

| Model | Status | Observable sequence | Evidence |
|---|---|---|---|
| `direct_h4` | confirmed | H4 breakout and liquidity formation, relevant H4 KL; direct limit anticipates sweep and expansion. The liquidity pool must be known before order placement; its future sweep need not already have occurred. | B07; entries5@156.9–221.2 |
| `direct_h2` | confirmed | H4 breakout candle CLOSED; scale to H2 for breakout/sweep+break plus single-candle or structural liquidity; direct entry at relevant H2 KL. Do not add an invented extra H2 confirmation layer. | B06; entries5@85.8–135.5,225.9–291.1 |
| `confirmation` | confirmed | Wait for H4 KL reaction, then lower-TF breakout, sweep+BOS, or engulfing. Bishop states waiting for the H4 REACTION candle to close is a personal choice; this does not cancel `direct_h2`'s explicit BREAKOUT-close requirement. | B08; entries5@293.6–453.1 |
| `engulf_retest` | confirmed | Core course: engulfing forms new A/V, then direct retest. H4 setup may confirm on H1/M30. | C18; v14@456–533,616–636 |
| `oc_break_retest` | confirmed | Two consecutive counter-direction candles form OC; engulfing/body close disrespects OC; retest broken OC. It need not engulf both earlier bodies. | C13,C18; v11@348–406; v14@533–658 |
| `engulf_irl_retest` | confirmed | Engulfing, next candle approaches new A/V WITHOUT tapping it (becomes IRL), then sweep that candle and tap level. This is an alternative to direct retest, not an extra condition imposed on every entry. | C18; v14@666–753 |
| `candle_sweep_retest` | confirmed family, exact mapping open | Bishop describes low-swept/high-standing with V-level buy; bearish mirror described separately. Do not require standard same-TF engulfing or mandatory half-TF engulfing. | RS@153.6–230.1; E5@589.3–716.6; DR@2151.8–2184.0; full session ledger21–24 |
| `aggressive_direct` | confirmed | Core alternative: valid KL overlapping imbalance may be entered without waiting for inducement/confirmation. Approximate 10–11-pip breathing-room stop is described. Keep this distinct from Bishop's H4/H2 liquidity-specific examples. | C05; v3@1002–1078 |

Corrections needed to avoid silently excluding teaching examples:

- **No universal extra-IRL gate:** after HTF level test and suitable close,
  lower-TF engulf→A/V retest may be valid without new IRL (C17;
  v12@1600–1704,1802–1828,1899–1915).
- **No universal FVG gate for every origin:** core v14@102–179 explicitly permits
  complete AMS without overlap and a nearby OC after liquidity sweep (C15).
  That does not remove overlap from models which expressly require it.
- **No universal exactly-next inside candle:** single-candle containment is one
  plug model; Bishop also teaches candle-series/structural liquidity (S07).
- **No H2-only universe:** P@1999–2057 includes H3 missed limit then M30 replacement;
  B08 lists multiple confirmation TFs. A bot's restricted TF preset cannot claim
  to match examples outside its supported models.
- **Timeframe choice:** P@1271–1299 scans H4→H3→H2; B11/trades3@476.6–520.0
  chooses H2 over genuinely simultaneous H1. Do not use later H2 evidence to
  retrospectively suppress an earlier valid H1 entry.
- **Consistent selection:** core v15@52–167 advises picking an entry system and
  staying with it (C20). Store model choice and eligibility, rather than choosing
  whichever past trade looks profitable.

Prior price sponsorship is a preferred continuation clue (P@841–983). The
canonical ASR at P@2049–2053 renders the M30 example as “does not sponsor any
sale,” but the alternate transcript and forced-English small/medium rechecks
do not reliably resolve that negation. This is neither a proven exception nor
a justification for a universal hard filter; retain the disputed phrase and
the source's broader preference separately.

## 6. Stops, trade targets and owner operating profile

A source-example replay uses the source example's **own documented model**, not
an arbitrary operating default.

| Profile/rule | Status | Stop/target behavior | Evidence |
|---|---|---|---|
| Core origin structural stop | confirmed | Beyond strong sweep high/low; lower-TF confirmation uses relevant wick; 0.5 or 1 pip padding explicitly discussed. A 5-pip near-miss is acknowledged. | C21; v13@307–332,1717–1936,2142–2157 |
| Core fixed-stop alternative | confirmed | Approximate 10–11p for aggressive direct style and continuation personal preference; not every historical trade's exact stop. | C05,C16,C21; v3@1022–1078; v13@1924–1936; v14@345–355 |
| Bishop structural protection | confirmed | Stops beyond indicated high/KL or nearby liquidity+KL because a normal sweep may precede the move. Exact zone construction still needs chart derivation. | B14; trades3@1287.7–1348.1; repeat@638.7–648.3; bias-entries@208.8–224.2 |
| Bishop nearest ERL target | corrected | Nearest external liquidity is personally selected; R is resulting target distance/risk, not always fixed 3R. Counter-structure guard uses nearer liquidity. Record the initially stated plan and any later observable management changes separately. | B12–B13; bias-entries@319.4–337.6; repeat@593.6–648.3; trades3@430.6–456.5 |
| Core routine RR | confirmed | 3R is routine; 4R also mentioned. Keep separate from structural story destination and source-specific ERL target. Win-rate quotes are claims, not measured bot results. | C22; v4@126–194; v14@295–370 |
| Owner operating preset | owner choice / not historical truth | Aggressive/direct default, fixed approximately 10–11p stop retained per handoff. Zone-edge/structural alternative selectable and backtested separately. Exact fixed default value, zone construction and fixed-vs-ERL target policy remain explicit configuration choices. | HANDOVER; owner conversation; source distinctions above |

A position box alone does not establish why its stop boundary was selected.
A red/teal position-tool box's far red edge is the drawn stop **by construction**;
that observation is not independent evidence that the stop is the far edge of an
imbalance/FVG. Those underlying boundaries must be identified separately. A
fixture uses `teacher_source_stop` to preserve only the source's selected price;
independently verified zone geometry is still required before asserting an
FVG-edge stop rule. The earlier `teacher_zone_edge` label and “35/35” claim
must not be used as proof of a universal rule.
A fixed-stop experiment producing a different stop is a different policy result,
not an exact teacher match. Report teacher-profile fidelity and owner-policy
performance separately; do not alter source fixtures to reconcile them.

## 7. Sessions and operating workflow

| Rule | Status | Definition / limit | Evidence |
|---|---|---|---|
| O01 | new, boundary unresolved | Core Asia illustration says 17:00→midnight, New York UTC−4 at recording. Indicator visibly reads 17:00–00:15; speaker says disregard “15.” End inclusion and year-round DST policy require explicit decision. | C08; v6@728–797; F v6/sheet_013@750/765 |
| O02 | corrected | Do not impose universal overnight prohibition: plug-and-play expressly mentions limits triggering at night. Session restrictions must be model/source-specific, not silently inherited from Kevin or the old draft. | P@1293–1299; plug_verified “Stops and targets” |
| O03 | confirmed | Flag a pair when daily direction exists, monitor missing H4 breakout/liquidity/reaction, keep missed setups distinct from subsequent continuation. | B15; routine@438.9–474.1,552.0–579.4 |
| O04 | confirmed caution | News can disrupt structural expectations; NFP example requires higher-TF context. No precise calendar-based blackout duration is established by checked passages. | C-ledger targeted v8@1615–1759 |

Paper trading precedes any broker execution (owner handoff). Reuse Kevin's candle,
storage and UI infrastructure only after adapting Bishop table namespaces,
read-only shared-token policy and separate owner alerts. Those engineering
requirements are not additional trading-pattern evidence.

## 8. Unsettled definitions and implementation-choice register

Before a detector can claim source fidelity, its exact behavior needs a setting,
choice label, causal tests and case coverage for each unresolved item:

| Topic | What is still unverified or chosen |
|---|---|
| Swing/structure | Turning-point initialization, active major vs local structural reference, equal-price ties, fractal order. Core allows one/two breaks but does not uniquely define a numeric detector. |
| Impulse | Body/range/ATR threshold and lookback; “impulsive” is stated without a numeric ratio. |
| Engulfing | Body-to-body/range definitions vs close through OC; different patterns cannot be merged solely on the word engulf. |
| Imbalance | Complete mathematical gap boundaries, min width, wick/body treatment, fill percentage, freshness, invalidation, and KL overlap tolerance. |
| Liquidity | Exact candle-series segmentation, inside containment equality, IRL/ERL state transitions, distance meaning of “near.” |
| KL selection | Shared open/close tolerance, level freshness/reuse count, competing level ranking and extreme fallback. No unconditional nearest/farthest rule. |
| Timing | Broker candle alignment, DST/session end boundary, entry before/after reaction candle close by model, expiry and hold limits. |
| Risk | Exact aggressive stop default, zone-edge construction, padding selection, stacking/exposure cap, partial sizing, break-even policy. |
| Execution/data | Broker feed and symbol mapping, real vs assumed spread, slippage/commission, limit fill rules, gap behavior, stop-vs-target ordering on ambiguous bars. |
| Scope | Supported assets/TFs, counter-weekly operating switch, model priority, duplicate chart examples, taken versus hypothetical orders. |

Backtest implementation choices on frozen chronological data with costs, as the
handoff requests (all supported pairs, 2018+ when data exist). Do not optimize
expectations against future outcomes or call exploratory parameters teaching.
A green workflow or a synthetic golden test alone does not prove fidelity.

## 9. Completion gate and remaining work

Before calling Bishop “built and matching,” all of the following must be concrete:

1. Source coverage manifest lists every unique lesson and frame range reviewed,
   with independent verifier findings and unresolved disagreements.
2. Historical example fixtures identify source, actual symbol/feed/date/TF,
   observed sequence, entry/stop/target, execution status and field uncertainty.
   Re-extract unreadable frames before asserting exact numbers. Keep schematics
   in a distinct class and preserve real losses/misses/no-trades.
3. Run the actual causal detector on frozen candles through each verified case.
   Required output includes all expected fields, no future data. Every promoted
   example passes without relaxing expectations. All unresolved candidates remain
   visible and prevent a claim that the whole teaching set is complete.
4. Independent code review, meaningful regression tests and a prefix-only replay
   demonstrate correct completed-candle timing, no lookahead and stable optimized
   results. Reviewers report remaining issues; their existence does not guarantee
   zero bugs.
5. Teacher-profile replay and aggressive-preset backtests are reported separately.
   Historical costs and feed limitations are explicit; paper operation is validated
   before activating delivery or broker paths.

**Current status:** full-source consolidation with explicit interpretation gaps. The engine, complete
numeric historical fixtures, independent verification of all rules/examples,
full replay and multi-pair backtests are not certified by this document.

## 10. Initial implementation coverage

`bishop/structure.py` implements provisional local close turns and causal
sweep/break observations. `bishop/bias.py` implements D01/D02 initial routes,
with same-day confirmation published only after origin closure. An already
broken reference cannot provide a fresh confirmation. Destination roles broken
before eligibility are retired; the frozen destination is an opposing origin-TF
KL, explicitly not Bishop's nearest ERL.

`bishop/setups.py` implements `engulf_retest` and `oc_break_retest` formation,
with declared wick-based and separate fixed-stop profiles. The default
exact-junction policy is preserved; explicit `close_reference` uses the first
close across an opening gap without averaging it or fitting a tolerance.

`bishop/engine.py` assembles these routes on completed candles and records all
choices/unsupported branches. Conservative operating retirement at a target,
origin invalidation or opposite confirmation is not certification of the full
L02 structural storyline-flip model. Conflicting opposite contexts observed at
one clock do not automatically place orders. Concurrent pattern alternatives
remain unranked candidates, not a position-selection or exposure policy.

`bishop/execution.py` provides declared-cost H1 paper observations only. Finer
execution, the remaining §5 models, weekly fallback/alignment, source-specific
ERL selection and full lifecycle remain open. Retained teacher observations
are unchanged; no exact historical match has been promoted by these additions.

## 11. Full-study corrections that constrain the eventual build

- A/V are source closing-price/line shapes; OC has explicit consecutive-candle
  open/close language. The old engine's opposite-colour/exact-junction or
  first-close-across-gap rules are provisional policies, not established
  definitions of every taught A/V. See independent verification§3.
- A high/low-standing candle pattern is not automatically same-TF engulfing.
  PDFp8 is a LONG/V labelled high-swept/low-standing; attribution and this
  referent must be reconstructed before applying a simple directional mirror.
  “4thman's CE” alone is not a separately defined algorithm. The prior zero-setup
  explanation based on a missing named fourth-man route was too strong.
- Core v16 says a small Daily KL breach alone does not establish continued
  buying and prefers momentum/context; Bishop accepts a small H4 break after
  Daily bearish context. Neither supplies a universal impulse threshold.
- Course14's two Gold entries are narrated as break-even exits after favourable
  excursions, not realized3R/4R wins. Session trades include stops, manual2R
  exit, misses, cancellation and nested replacement. PDF charts and broker
  positions sometimes differ in TF, count, fills and exits.
- Plug's M30 sponsored-sales negation is disputed across ASR versions. Treat
  prior sponsorship as source-described preference with that sentence unresolved;
  do not assert a proven exception from corrupt wording.
- Dense native-frame review resolves v7's old/new-high referents: OLD protected
  high remains after a wick-only weak-low sweep; NEW lower candidate is liquidity,
  with migration illustrated after body-close break. Numeric major/local
  selection, equality/plateau rules and displacement thresholds remain unspecified.

No fixture expectations or engine outputs are changed by these study corrections.
