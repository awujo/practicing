# Independent teacher-case replay readiness audit

2026-10-23. Audited all40 retained observations in `tests/bishop_examples.json` against their actual metadata and the full-study case catalogues. No fixtures, expected values, tolerances or engine code changed. This is readiness review, not replay acceptance.

## What is ready and what remains missing

All40 fixture records have `verification=unresolved`, null UTC setup/fill windows, null bias, and null numerical tolerances. None currently qualifies for exact historical trade acceptance.38 are labelled ILLUSTRATIVE_PLAN, one PENDING, one OPEN_POSITION; those statuses must not be converted to40 filled trades. The GBPNZD chart-plan record coexists with actual broker history on its source page, but its chart prices are not that broker execution.

Common exact-replay prerequisites **C** apply to every row: independently identified origin/confirmation/entry bars and model; causal UTC setup availability; actual participation/order type and fill/management interval (or explicitly pending/missed/no-trade outcome); exact provider/instrument and quote basis; broker timezone/candle anchor; complete historical input/warmup; independently justified fixed tolerances. Numerical labels alone do not satisfy C. Where a source never states a fill, retain a plan/checkpoint rather than demand an invented fill timestamp.

A chart's screenshot-creation date, drawing anchor and broker wall-clock timestamp are three different clocks. `trigger=engulfing/breakout` alone does not resolve the named source route. `mode=teacher_source_stop` preserves an illustrated boundary; it does not establish an executable universal stop algorithm or prove the zone-edge experiment.

The generic “independent second review missing” reason is partly stale: p8 has numeric-only agreement already recorded. This audit independently corroborates p31 broker fields and native E5t1065 numerical labels below. These narrow checks do not promote their whole fixtures.

## Direct primary-source checks during this audit

- PDFp31 rendered directly from the original retained PDF: chart H1 FOREXCOM plan2.29993/2.29842/2.30503; broker `GBPNZD.pi buy0.33`, open2.30008, close2.30172, open wall clock2026.06.10 07:20:15, close2026.06.10 17:03:04, SL2.30017, TP2.30672, commission−2.31, profit31.52. Broker timezone is not printed. SL above original fill is managed; original risk cannot be reconstructed from it. Broker suffix/feed must not be collapsed into FOREXCOM.
- PDFp6 rendered directly: EURCHF.x M30 BUY LIMIT0.91 at0.93193, SL0.93147, TP0.93704, with live quote above the limit. The axis shows28–29July, but neither UTC issuance nor eventual fill is demonstrated. PDFp5's different TP0.93498 remains a separate plan.
- PDFp40 rendered directly: left AUDCAD2h FOREXCOM “H2 Breakout Confirmation Entry,” “H4 breakout with idm/H4RH4,” “Daily bullish breakout/PDL swept/Daily reject Daily.” Right AUDCADm H1 mobile feed has arrows, not independent exact fill metadata. Left header29May2026 13:52UTC+1 is creation time, not entry.
- Native E5PTS1065 frame inspected directly: Saxo XAUUSD3h, entry4079.56, stop4064.31, target4165.88, displayedRR5.66/stop15.25; drawing anchorWed05Aug26 02:00 in displayed UTC+1. Transcript1033.1–1042.8 says engulf at2am and conditional “might have taken”;1057.8–1085 discusses changing hypothetical stop/target. This is a missed/illustrated alternative, not proof of filled participation. The full session ledger distinguishes H3 miss, H1 no retest, M45 no retest and M30 retest.

## Per-record classification

Every row still needs C. “Checkpoint” means a source-derived visual/sequence assertion suitable for reconstruction and comparison; it is not a historical engine PASS. Source page context is cross-checked against `full_supplement_study.md`pp1–60 catalogue and detailed examples; video segments against `full_session_study.md`E5.

| Record | Useful checkpoint / strongest known fact | Additional record-specific blocker |
|---|---|---|
| `pdf-p02-eurcad-buy-1` | p1D/H4 context → p2H2 engulf plan | Broker arrow≈1.61274 differs from chart entry; establish which object is compared. |
| `pdf-p03-eurjpy-buy-1` | p3D bullish + H2 engulf; p4H4 context | Do not infer actual participation from plotted long box. |
| `pdf-p05-eurchf-buy-1` | p5M30 long plan | TP0.93498 differs from pending broker TP0.93704; keep separate. |
| `pdf-p06-eurchf-buy-1` | Directly verified pending BUY LIMIT0.91 | Year/timezone/issuance missing; no later fill or result shown. |
| `pdf-p08-eurgbp-buy-1` | p7D/H4 bullish; p8standing-extreme/V annotation | Exact high/low referent pair unresolved; fourth_man attribution is not a separate algorithm. |
| `pdf-p10-usoil-buy-1` | First H2 engulf plan after p9D/H4 context | Oil scale≈8100 versus broker≈81; stacked target association unresolved. |
| `pdf-p10-usoil-buy-2` | Second H2 breakout plan | Separate entry/stop from first; stacked target/scale mapping unresolved. |
| `pdf-p11-xauusd-sell-1` | Community XAUUSDH1 short drawing | mindguy0x attribution; trigger/feed not established as Bishop personal execution. |
| `pdf-p13-eurnzd-sell-1` | D bearish → H4with-idm → H3engulf | Need H3 anchor and named engulf/OC mapping. |
| `pdf-p15-usdcad-sell-1` | p14D/H4 bearish → H1breakout | Broker and chart participation cannot be merged from arrows. |
| `pdf-p17-audusd-buy-1` | p16D/H4 bullish → M30engulf | Entry appears15July versus snapshot16July; reconstruct actual bars. |
| `pdf-p19-gbpjpy-buy-1` | First H1breakout after p18D/H4 context | Stacked TP218.014/218.007 association unresolved. |
| `pdf-p19-gbpjpy-buy-2` | Second H1breakout-with-idm | Not duplicate first order; own stop/target association needed. |
| `pdf-p20-xagusd-sell-1` | Left XAGUSDH4 short plan | No named CE trigger; Saxo calendar/units distinct from FX. |
| `pdf-p20-usoil-buy-2` | Right USOILH4 long plan | Separate instrument from left; no named CE; validate oil units. |
| `pdf-p22-xagusd-sell-1` | p21D/H4 bearish → H2engulf plan | Chart risk/target differ from broker position on same page. |
| `pdf-p22-xagusd-sell-2` | Broker OPEN_POSITION sell0.06 at59.655 | Broker SL unreadable/null; TP58.534; cannot borrow chart stop or infer closed result. |
| `pdf-p23-usdchf-sell-1` | Left short variant | Same setup as right variant, not independent fill; different boundaries. |
| `pdf-p23-usdchf-sell-2` | Right short variant | Do not double-count variants as two executions. |
| `pdf-p25-audusd-sell-1` | Weekly bearish, recentD bullish → H2sell to nearer liquidity | Retracement/dominant-direction relationship explicit; not universal W-veto evidence. |
| `pdf-p27-gbpusd-sell-1` | p26D/H4 bearish → H1breakout | Correct source entry1.31932; arrow execution remains separate. |
| `pdf-p29-chfjpy-sell-1` | p28D/H4 bearish → H1engulf plan | Broker fills distinct from chart prices. |
| `pdf-p31-gbpnzd-buy-1` | p30D/H4 bullish → H1engulf; actual broker history also visible | Chart fixture prices differ from broker; timezone and initial broker SL unknown. |
| `pdf-p33-gbpcad-buy-1` | p32D/PDLsweep → H4context → H2breakout | Distinguish breakout entry from direct-H2 context path. |
| `pdf-p35-gbpjpy-buy-1` | p34D/H4 bullish → H1breakout annotation | Entry/stop/target ALL null; no numeric box; sequence checkpoint only until independently measured. |
| `pdf-p37-eurgbp-sell-1` | D bearish/PDHsweep/D rejection → H4 → H1engulf | Map prior-candle-sweep and KL origins independently, not mandatory conjunction. |
| `pdf-p38-us30-buy-1` | H4bullish → M30engulf plan | Index provider/contract/calendar and source entry50816.7. |
| `pdf-p40-audcad-buy-1` | Directly inspected D/PDLsweep → H4idm → H2breakout | Right broker is H1/AUDCADm, different feed/TF from H2chart. |
| `pdf-p42-usoil-sell-1` | p41D bearish/H4extreme rejection → H3engulf | Oil scale/calendar and H3anchor unresolved. |
| `pdf-p44-ethusdt-sell-1` | p43D/H4 bearish → H1breakout | Bybit ETHUSDT.P perpetual identity differs from generic ETHUSDT/broker screen. |
| `pdf-p46-eurjpy-buy-1` | p45Dold-low sweep/H4idm → M45breakout | Broker M30 differs from chartM45; appears26May versus27May snapshot. |
| `pdf-p47-gbpcad-buy-1` | D bullish + p48H4idm → H2engulf | Retain corrected chart entry1.84768; exact trigger bars unindexed. |
| `pdf-p50-nas100-buy-1` | p49D/H4 bullish → H1long drawing | No named CE; origin appears20May versus21May snapshot; index contract/calendar. |
| `pdf-p52-nas100-sell-1` | p51D/H4 bearish → H1breakout | Correct source stop29060.5; contract/session identity unresolved. |
| `pdf-p54-eurgbp-buy-1` | p53D/PDLsweep/rejection → H2breakout | Correct source entry0.86609; exact bars and participation missing. |
| `pdf-p55-us30-buy-1` | D bullish → p56H4context → H1breakout | p56context repeats thesis, not another fill; index session/contract. |
| `pdf-p58-jp225-buy-1` | p57D/H4 bullish → H1breakout | Entry appears13May, snapshot14May; correct stop62813; index contract. |
| `pdf-p60-gbpaud-sell-1` | p59D/H4 bearish → second M45break-with-idm | First/second setup relationship and M45anchor; target1.87390. |
| `video-entries5-native-t1065-xauusd` | Native H3plan + spoken missed H3/H1/M45 versus M30retouch | Drawing anchor is not execution; Saxo feed; subsequent plan adjustments. |
| `video-entries5-native-t1410-eurusd` | Native H2final illustrative plan after transient dragging | Narrator uncertain original TF/model; conditional personally would; no exact executed route. |

## Three first reconstruction priorities

1. **GBPNZD p30–31:** strongest actual execution chronology among the40. Reconstruct chart plan and broker execution as two linked observations; verify broker timezone, symbol mapping and original SL from independent retained evidence before exact-risk replay. Immediately test that a moved SL above fill does not become the initial risk and that chart TP is not replaced by broker TP. Exact full-trade pass remains blocked.
2. **EURCHF p5–6:** strongest explicit order-state checkpoint. Reconstruct the pending limit/SL/TP and distinguish chart TP from broker TP. Identify issuance/observation timezone and later outcome only if a source provides them. A paper simulator filling an earlier historical touch before order issuance would be a mismatch; the screenshot alone supplies no issuance time.
3. **E5 XAUUSD source859.9–1180.4/nativePTS1065:** strongest narrated multi-timeframe participation sequence. Reconstruct H3miss, H1no-retest, M45no-retest, M30retest with source bar anchors, retaining illustrative versus personal participation. Compare causal eligibility/missed handling before exact numerical fills. Native drawing labels are independently legible, but anchor time cannot substitute for trigger/fill.

For an uncomplicated visual structure/entry checkpoint after these, prioritize AUDCADp39–40 (D→H4→H2 labels directly present). Its mobile H1 arrow cannot supply the H2chart's exact execution clock.

## Scope beyond these40 records

The40 retained observations are not the complete teaching catalogue. `full_session_study.md` catalogs61 pair/story segments, explicitly including losses, missed entries, cancellations, replacement and open positions; `full_entry_study.md` has course14/15 examples, including Gold break-even outcomes despite favourable3R/4R excursions. T3AUDCHF loss, corrected NZDCHFH2loss, USDJPYmanual2R and USDCADcancel/replacement/open chain are high-value source-behaviour checks even though absent from this fixture file. Add new independently reconstructed cases only as new records, without silently repurposing these40 chart plans.

Replay harness review is recorded below. Require actual detector output, fixed input/policy hashes, causal plans versus fills, full-field mismatch reasons and explicit unresolved source facts. Never treat successful harness execution or40UNRESOLVED results as40matches.

## Parallel independent source-review updates

The saved `replay_p08_source_review.md` independently verifies p7Daily BUY context, p8H2 identity and0.85315/0.85289/0.85447, while retaining unnumbered sweep/standing referents and missing execution clocks. `replay_eurgbp_other_source_review.md` directly inspects p36–37/p53–54 and corroborates p37SELL/H1engulf prices0.86580/0.86611/0.86451 and p54BUY/H2breakout prices0.86609/0.86544/0.86975. These resolve narrow extraction-review needs, not UTC/feed/model/participation acceptance. Fixture generic reason strings are unchanged; review consumers should read the precise signoff scope rather than treating all numeric review as still absent or all trade fields as verified.

## Prospective duplicate-crowding review during baseline replay

Code review shows setup identity includes story_id even when the economic entry is otherwise identical. Independent deterministic72H1-bar source_all probe (seed41, fixed11/fixed3R; engineering-only data) produces120eligible candidates but70 unique economic groups,23duplicate groups, up to5aliases. One aggressive H1entry992/stop981/target1025 at2026-01-02 17:00UTC appears under4story IDs.

This is evidence of candidate/provenance duplication, not four source-authorized later entries. A prospective selector may group by instrument, side, named model, entryTF, selectedKL, pattern/eligibility clock and frozen entry/stop/target, while retaining all story/evidence aliases. Do not erase the diagnostic candidates or alter their source interpretation. Source-permitted stacking remains distinct: a newly eligible later pattern has its own causal confirmation and eligibility clock. Different risk/target plans or different named models remain competing alternatives under an explicit operating-selection policy.

Freeze the actual source baseline before changing selection, then replay the same feed/policy window and report both the crowding change and remaining price/stop/target/sequence mismatches. Deduplication does not make the source's numerical values match.

Independent `test_eligibility_start_equals_filtering_full_nonempty_entry_history` passes: with all context retained, cutoff48h yields exactly the full nonempty72h result's eligible-time-filtered setups/events; support and imbalances remain identical. This optimization equivalence does not verify any teacher example.

## Saved replay harness review

Reviewed `reports/replay_teacher_examples_v2.py` after it was saved. It invokes the actual v2 engine on the declared frozen ICMarkets BID feed, reports FOREXCOM mismatch, source snapshot-only clocks and exploratory scan windows, fixed source/owner profiles, zero-cost diagnostic hypothesis, input/policy/code hashes, plan differences, and strict unresolved source results. It does not substitute source drawings for detector output or alter fixtures/tolerances. No exact historical acceptance is supported by these runs.

The two reported harness issues are now corrected in saved code: final evaluation is separated by case/profile and a final implementation rehash rejects code changes during a run. Source and owner reports remain distinct. Including the harness itself in provenance remains useful; no source acceptance follows from either correction.

The pre-dedup source baseline is retained at `reports/teacher_replay_v2/p08_pre_dedup_baseline.json`. Independent prospective selection tests now pass: two same-clock same-economic setups from different stories create one order plus a retained alias; a later confirmation remains a separate order; source_all preserves diagnostic alternatives. The declared first-causal-context cancellation policy remains explicit—alias invalidation does not invent an all-context OR rule. Dedup changes exposure admission only; the previously observed plan-price/stop/target mismatches remain separate findings.


## Local-input inventory correction — 2026-10-24

Independently opened all eight local gzip CSVs in `/workspace/kevin-review/data/examples` read-only. Each contains29,864 rows with header `t,open,high,low,close`, first recorded timestamp2022-01-02 23:00UTC and last2026-10-20 10:00UTC. These are observed file endpoints, not certification of continuous interval coverage, publication clocks, source-feed equivalence or timestamp start/end semantics. Root is freezing Bishop-local copies and provenance manifests; the Kevin files are unchanged.

| Local frozen filename | SHA256 | Relevant retained cases / resolution |
|---|---|---|
| EURGBP_H1.csv.gz | `257ea6b66bd6c9fc46f421abe358ea792ae50319a38a900d1c4d7b49402fcad6` | p8H2,p37H1,p54H2; this original gzip hash differs from the existing transformed Bishop fixture's815f…hash. Preserve both identities. |
| GBPJPY_H1.csv.gz | `2a887f2e9efedad07aca002876fbd6408dbdbe7ae0b0006c19cd6d9777d303a6` | p19first+secondH1 and p35H1context; H1resolution sufficient for these entry TFs, but p35numeric plan remains absent. |
| USDCAD_H1.csv.gz | `cf63446d2b5c53bf7159ff3878ae1fbbe59f5e33fc2d93146ee9ffb564bf72ca` | p15H1breakout; alternate-feed diagnostic can be attempted after manifest/coverage checks. |
| USDCHF_H1.csv.gz | `2ee48edf15bde5a6c65387c56e84081c2f671b2131398beacf9827843024bf01` | p23left/rightH1variants; compare variants without counting two independently demonstrated fills. |
| GBPAUD_H1.csv.gz | `c18d2aeba6cfdd148c440192bbef3bf933090077a1defea979f7e38278d44b93` | p60M45entry **cannot** be reconstructed from H1. D/H4context diagnostics are possible; entry remains UNRESOLVED_RESOLUTION. |
| CADJPY_H1.csv.gz | `22000d751b1f077f843d15c697be48d94d10c4618fba3ca481cf4e97833fa064` | No matching pair in these40 records; potentially useful for separately catalogued session cases after date/model reconstruction. |
| EURAUD_H1.csv.gz | `834c5df15202c45fe7d475d688268fd34e10e2ae6e68984d336813d3a0e0b33d` | No matching pair in these40; E5EURAUD session narrative exists, with separate participation/model uncertainty. |
| USDJPY_H1.csv.gz | `e41abcc0e66b824307503d5333b05b69628b1b6570d44038f8bf20603093fa60` | No matching pair in these40; T3USDJPY manual-exit source segment is separately catalogued. |

Thus10 of40 retained records now have a matching-pair local alternate H1 input candidate:3EURGBP,3GBPJPY,1USDCAD,2USDCHF,1GBPAUD. Nine have base resolution compatible with their declared entry TF; GBPAUDM45 has only higher-TF/context support. Thirty records lack a matching pair in this specific eight-file inventory. These are input-availability counts, not successful replay, complete coverage, exact source-feed matches or verified fixtures.

The prior harness index's blanket `NO_LOCAL_FROZEN_PAIR_INPUT` for every non-EURGBP record is now factually obsolete for the seven additional records above. Use distinct reasons: `LOCAL_ALTERNATE_INPUT_NOT_RUN`, `UNRESOLVED_RESOLUTION`, `SOURCE_METADATA_UNRESOLVED`, or no matching local pair. Root's forthcoming data catalogue should supply authoritative copied paths/hashes and coverage; do not silently claim these files are FOREXCOM or the teacher's broker candles.

Revised p8 admission after dedup remains an engineering-selection correction. Retain the frozen pre-dedup baseline and revised source/owner reports separately; admitted orders do not erase the source entry/stop/target differences or unresolved model referents and execution clocks.

## Independent literal-plan diagnostic review — 2026-10-24

Reviewed harness `plan_checkpoints(report)`. It requires entry, stop and target equality within one causal plan, reports source-route identity separately, exits early for unavailable entry resolution, and labels null-price cases as context-only. An identical numerical triple is expressly `EXACT_NUMERIC_PLAN_PRESENT_NOT_TRADE_ACCEPTANCE`; it does not establish source-candle identity, execution participation, timing or exact historical acceptance. Named-family compatibility remains a separate count, so an exact triple from another family must not be described as a matched source model.

Added three independent tests in `tests/test_teacher_replay_diagnostics.py`: separate candidates cannot contribute one matching price each to fabricate a complete plan; null source labels remain context-only; unsupported entry resolution never matches even if supplied candidate labels are identical. Positive control confirms one complete triple produces only the qualified numerical-plan status. **3 passed**. No source fixtures, tolerance values or production code changed.
