# Teacher outcome and posttrade review

2026-10-24. Read-only annotation of **all40 existing fixture observations**, with separate source-supported narrated wins, losses, manual exits, break-even exits and passes. Companion machine-readable file: `tests/bishop_teacher_outcome_annotations.json`. Original fixtures and production code are unchanged; no historical example is promoted to acceptance and no thresholds are fitted to winners.

## What was reviewed and what the inventory means

Read all40 records in `tests/bishop_examples.json`, the PDF page-by-page outcome/management observations in `full_supplement_study.md`, relevant example reviews in `full_session_study.md` and `full_entry_study.md`, and the canonical transcript passages quoted below. Independently rendered/inspected actual PDFp31 andp44 for strongest broker outcome/adverse-attempt evidence in this pass. Prior current-task source reviews directly inspected p7–8,p15,p22–23,p59–60; see `replay_p08_source_review.md`, `replay_chf_aud_source_review.md`, and `protection_scope_source_audit.md`. The other PDF outcomes below are explicitly ledger-based in this pass; this is not a claim to have newly re-viewed all60pages or broker history.

The40 records contain **38 PDF source observations and2 native-video plan observations**, not40 independently executed trades. They include one explicit pending order and one open broker-position observation. Most records describe an illustrative chart plan, even where an adjacent broker screenshot supplies a separately observed trade leg. Duplicate USDCHF snapshots, stacked drawings and differing chart/broker counts must not inflate the number of independent trades. A position-tool target reached by price is favorable excursion, not proof a live order filled/closed there.

Outcome dimensions must remain independent: source plan, actual order/participation, realized outcome, exit cause, model compliance and mentor critique. A loss does not establish deviation. No diagnosed deviation does not establish full compliance or mathematical unavoidability. A winning future does not validate an otherwise missing preentry predicate.

## Stronger outcome evidence and mentor reviews

Canonical transcript slugs below are under `knowledge-base/videos/`; literal quotes retain some ASR imperfections. Event UTC, precise fills/costs and matched historical bars remain unresolved unless explicitly stated. The companion JSON stores full source paths and exact ranges.

| Source case | Supported outcome/review | What can be learned causally | What must remain unresolved |
|---|---|---|---|
| **PDFp31 GBPNZD** | Actual broker history: buy0.33, open2.30008, close2.30172, profit31.52, commission−2.31. Chart plan is2.29993/2.29842/2.30503. | Positive close is supported for that broker record; displayed managed SL2.30017 lies above entry. | Original risk/R and close cause unknown; not a chart-TP win. Broker dates have no established timezone. |
| **PDFp44 ETH** | Actual broker arrows show short near2078 closing adversely near2086, then subsequent shorts near2076/2074 closing favorably near2051. | Both adverse and favorable attempts must survive reconstruction; retries are separate. | Arrows do not prove SL cause, exact fill count, original protection or compliance. Main Bybit perpetual plan and broker contract differ. No case-specific spoken mistake review identified. |
| **BE US30**,398.4–428.6 | “I got stopped out … but that did not mean my bias was wrong”; later fresh bullish breakout/liquidity. | Record first loss; later entry needs fresh setup. A trade loss does not alone reverse story. | No source-diagnosed rule deviation here; cannot declare the loss independently fully compliant/unavoidable without exact evidence. |
| **T3 AUDCHF**,577.9–677.3 | “I took a loss”; W/D bullish, H4 breakout/liquidity and H1 engulf described.636.6–647.5: “I don't actually use that … if that was the reason why I took a loss, then that's fine by me.” | Teacher accepts the chosen system's loss and rejects adding an external-breakout filter merely to explain it. | Full numerical compliance not independently established; no basis to claim an unavoidable market loss or invent a universal external filter. |
| **T3 NZDCHF**,719.3–728.8,856.6–902.8 | “I should have waited for a new breakout … But I now daily reject daily instead”; immediate loss acknowledged. | Case-specific mentor critique points to waiting for fresh Daily evidence before this attempt. This missing evidence is conceptually observable before entry. | Exact context/reference/clocks need aligned candles; unclear closure wording at708–719 must not become a universal new-Daily-break veto. |
| **T3 GBPUSD**,1287.7–1348.1 | “price has every right to come to this liquidity”; narrower stops on one/two accounts lost by1–2pips, wider protection survives/target discussed. | Nearby already-known H4 liquidity/KL may require protection beyond engulf high. This is a preentry protection decision. | Preserve all account outcomes; do not replace losing stops with a wider counterfactual, or include all unrelated old highs. Exact account fills/management unresolved. |
| **T3 USDJPY**,1089.1–1105.7 | “If you just trade3R, it gave it3R. But I closed around2R … did not trust … consolidations.” | Record manual profitable exit around2R separately from available3R. | No numerical stalling detector supplied; later move does not justify inventing one or replacing actual exit with maximum excursion. |
| **Core14 Gold two buys**,1236.3–1259.3 | “both did a one to three … went break even on the two … didn't even take partials … trade took me out … break even.” | Both realized exits remain narrated BE; store BE amendments/no partials. | Claimed summed8R is excursion arithmetic, not realized profit. Costs and exact BE amendment clocks unknown. |
| **Core13 Gold student**,1955.3–2156.8 | Entered lower KL, stop beyond another KL while stronger high remained; stopped. Teacher recommends referenced high plus0.5/1pip. | Strong protective high versus entry KL is a case-specific preentry scope distinction. | Numerical candle identity and applicable padding need evidence; not a rule to protect every later visible high. |
| **T3 USDCHF**,1455.0–1508.5 | Taken H2 engulf after renewed H4 reaction; “this was my entry … immediately price reached that target … reversal.” | Source-supported favorable case, with target chosen before described reaction and fresh entry chain. | Approximate3.5–4R narration is not audited realized accounting or universal Thursday rule. It is not automatically PDFp23. |
| **Routine USDCAD**,1812.7–1828.5 | “very clean breakout … no h4 reject h4 … I let this guy slide … played out quite well.” | A compliant pass stays a pass despite favorable future. Do not relax chosen reaction checklist to fit a winner. | Alternative source approaches are allowed, but not retrospectively substituted for this person's selection. |

BE = `bishop-defi-bishop-study-10-minute-series-part-1-bias-entries-amp-confirmation-entries-combined`; T3 = canonical `bishop-defi-bishop-study-20-minute-series-part-3-trades-breakdown-bias-to-entry-case-study-gb` (not duplicated `-1`); Routine = `bishop-defi-bishop-study-daily-routine-x-trade-breakdown-how-do-i-manage-trading-multiple-pairs-wha`; Core13/14 use descriptive-slug transcripts. These supplemental narrated reviews are **not** extra historical acceptance fixtures and are not mapped to similar-looking PDF examples without dates/feed proof.

The native XAU H3 plan observation is a missed opportunity: E5@1033.1–1042.8, “Price engulfed at2a.m. … I wasn't even home.” At1057.8–1085 the tool is adjusted while discussing hypothetical5/8/19R. EURUSD E5@1403–1418 explicitly says “personally, I would have done something like this.” Neither plan establishes that plotted R was realized.

## Complete40-observation inventory

Each JSON annotation retains original source references, chart/broker distinction and unresolved coverage. The short outcomes below describe source observations, not all-case historical passes. Original fixture execution labels remain unchanged.

| Observation ID | Source outcome boundary |
|---|---|
| pdf-p02-eurcad-buy-1 | Broker linked exit below chart target; exact plan execution unmapped. |
| pdf-p03-eurjpy-buy-1 | Chart extended beyond target. |
| pdf-p05-eurchf-buy-1 | Chart plan; broker pending target differs. |
| pdf-p06-eurchf-buy-1 | BUY LIMIT remains pending at snapshot. |
| pdf-p08-eurgbp-buy-1 | Later upper wick beyond target; fill unknown. |
| pdf-p10-usoil-buy-1 | Multiple broker legs precede final rise; two chart plans not one-to-one mapped. |
| pdf-p10-usoil-buy-2 | Multiple broker legs precede final rise; two chart plans not one-to-one mapped. |
| pdf-p11-xauusd-sell-1 | Later same-thesis chart extends below target. |
| pdf-p13-eurnzd-sell-1 | Latest market remains above short target; eventual TP unproved. |
| pdf-p15-usdcad-sell-1 | Chart wick beyond TP; broker linked exit earlier than chart TP. |
| pdf-p17-audusd-buy-1 | Chart above TP then reverses; broker linked exit near but not proved equal TP. |
| pdf-p19-gbpjpy-buy-1 | Two chart plans versus three broker entry arrows; exits near217.8. |
| pdf-p19-gbpjpy-buy-2 | Two chart plans versus three broker entry arrows; exits near217.8. |
| pdf-p20-xagusd-sell-1 | Chart directional travel only; no broker execution proof. |
| pdf-p20-usoil-buy-2 | Chart directional travel only; no broker execution proof. |
| pdf-p22-xagusd-sell-1 | Chart below target; broker active short still above broker TP. |
| pdf-p22-xagusd-sell-2 | Chart below target; broker active short still above broker TP. |
| pdf-p23-usdchf-sell-1 | Later left chart below target; earlier right still developing. |
| pdf-p23-usdchf-sell-2 | Later left chart below target; earlier right still developing. |
| pdf-p25-audusd-sell-1 | Chart reaches short target region. |
| pdf-p27-gbpusd-sell-1 | Chart strong decline; broker linked short/exit differs in feed/time. |
| pdf-p29-chfjpy-sell-1 | Broker linked favorable short leg; exact planned TP mapping unknown. |
| pdf-p31-gbpnzd-buy-1 | Broker history confirms closed profitable buy; chart TP differs. |
| pdf-p33-gbpcad-buy-1 | Chart target tagged by wick; paired broker favorable leg separate. |
| pdf-p35-gbpjpy-buy-1 | Advance shown; no numeric risk/target or broker. |
| pdf-p37-eurgbp-sell-1 | Chart below TP; broker favorable linked short leg. |
| pdf-p38-us30-buy-1 | Wick reaches top target region; no broker closure. |
| pdf-p40-audcad-buy-1 | Chart reaches target; broker has two entries versus one drawing. |
| pdf-p42-usoil-sell-1 | Wick through target then rebounds; no exact broker closure proof. |
| pdf-p44-ethusdt-sell-1 | Broker adverse first short leg then favorable subsequent legs; main chart distinct. |
| pdf-p46-eurjpy-buy-1 | Chart wick reaches target; broker M30 differs from M45 chart. |
| pdf-p47-gbpcad-buy-1 | Latest market below target though earlier wick near top; no broker history. |
| pdf-p50-nas100-buy-1 | Long drawing; no broker execution record. |
| pdf-p52-nas100-sell-1 | Chart selling to target zone then rebound; no broker record. |
| pdf-p54-eurgbp-buy-1 | Chart beyond target; no broker evidence. |
| pdf-p55-us30-buy-1 | Chart wick above target; no broker history. |
| pdf-p58-jp225-buy-1 | Chart target region then retracement; linked broker exit approximate. |
| pdf-p60-gbpaud-sell-1 | Chart beyond target; no broker order record. |
| video-entries5-native-t1065-xauusd | Teacher absent for2am H3 engulf; later5R/8R/19R tool adjustments are hypothetical. |
| video-entries5-native-t1410-eurusd | Personally I would have plan; exact remembered earlier personal model uncertain; not a proven5R realization. |

## Replay and causal review protocol

A source-comparison replay must first reconstruct the selected source profile, model/TF, known context and protection, order existence/clock and actual management. Outcome is then assessed against ordered matching data with costs. If missing evidence prevents that reconstruction, retain UNRESOLVED rather than reclassifying a loss/win from chart appearance.

For each adverse result, compare the original decision against the rule facts available **at that decision**. A teacher's critique can nominate a check (fresh Daily break, relevant protective high), but subsequent price cannot establish that the check was satisfied or absent before entry. Distinguish (a) independently proved deviation, (b) teacher-identified candidate deviation awaiting clocks/data, (c) no identified deviation under chosen system, and (d) indeterminate. Never label category(c) “unavoidable compliant loss” unless compliance is actually proved; even proved compliance establishes a permitted losing outcome, not that no possible alternative could profit.

For favorable outcomes, apply the same standards: a passed winner stays passed, missed limits stay missed, manual2R stays manual2R, BE after4R stays BE, and broker early exits stay separate from a later chart TP. Do not preferentially select entryTF, stop width, target, retry or optional filter using eventual outcome. Prefix-only replay must preserve original plan/amendment history.

Coverage limits remain source feed/contract/scale, candle anchor/calendar, supported entry resolution (H1 cannot reconstruct M45/M30), actual setup/placement/management/fill clocks, spread/costs and intrabar sequence. Chart headers are snapshot minutes only. No numerical source tolerance or new source filter is established by this annotation file. The fixture inventory hash in JSON records exactly which40 observations were annotated.
