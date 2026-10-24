# Teacher-example replay: first pass

2026-10-24. Ten source records were exercised against existing local,
alternate-provider data. This pass found and fixed a real duplicate-order
selection bug. It also demonstrates substantive stop, target and reference
mismatches. **No exact teacher-trade match is certified.**

Of the ten source-policy runs, eight have numerical plan labels and compatible
entry resolution. None contains one causal candidate with all three printed
entry/stop/target coordinates equal. One record (p35) is context/model-only;
one (p60) requires M45 candles unavailable from H1. These literal price checks
are diagnostics across different feeds, not an assertion that all eight source
rules failed. Full trade acceptance needs source candle identities, clocks and
execution evidence. The unchanged strict fixture gate remains40unresolved,
including30source records without a matching-pair local input in this inventory.

## What ran

Independent agents reread actual source PDF pages before comparison; numeric
labels, snapshot-minute UTC conversions, routes and ambiguities are retained
in the six `knowledge-base/study/replay_*.md` reviews. The input inventory now
includes existing Kevin branch EURGBP, USDCAD, GBPJPY, USDCHF and GBPAUD exports.
No data acquisition occurred. All are IC Markets BID H1, not the source
FOREXCOM feed. Original file versions/hashes and precision limits are retained
in `additional_local_inputs.json` and the original EURGBP metadata.

Declared exploratory scan windows end at independently read source **snapshot**
minutes. Those are not setup or fill timestamps. Context starts are fixed in
the harness. Source-confirmation and owner fixed11 are separate presets; their
observations and acceptance checks are never pooled. Explicit zero costs are
an engineering hypothesis, not an estimate of trading costs or profitability.

There are ten completed source-policy reports and two completed owner-preset
reports. The optional p08 all-routes experiment exceeded120seconds; the optional
p54 owner experiment exceeded180seconds and was aborted. Both are recorded in
`run_limits.json`, not interpreted as zero signals. Future harness runs have a
180-second per-run POSIX budget by default. `0` explicitly disables the budget.

## Concrete differences

The plans below are generated diagnostic examples, **not identified source
trades**. Except p08's independently discussed13:00candidate, rows illustrate
a nearby entry in the source-named family where known. Price proximity does
not establish source candle association. Full candidate groups are archived,
so these rows do not select a passing example or hide alternatives.

| Source record | Printed source entry / stop / target | Diagnostic observation and reason |
|---|---|---|
| p08 EURGBP BUY H2 |0.85315 /0.85289 /0.85447|Jul23 13:00standing candidate0.85313 /0.85214 /0.85442. Entry−0.2pip, stop−7.5pips, target−0.5pip. Stop protects an earlier H2 observation of the H4-related reaction low0.85219 plus0.5pip buffer; source's high-swept/low-standing reference is still unmapped. |
| p15 USDCAD SELL H1 |1.40471 /1.40539 /1.40129|Jul16 07:00BO candidate1.40425 /1.41561 /1.40249. Older protected range high1.41556 dominates stop. A closer1.40465 candidate belongs to engulf/standing families, not the source-named BO. |
| p19 GBPJPY BUY first |216.877 /216.700 /218.014|Jul14 02:00BO candidate216.863 /216.367 /null. Protected pool216.372 dominates stop; valid causal ERL target absent. Not identified as the teacher's first trade. |
| p19 GBPJPY BUY second |217.255 /217.088 /218.007|Jul15 00:00BO candidate217.274 /216.931 /null. Earlier reaction low216.936 determines stop; selected entry range/target absent. Source's fresh second BO+inducement remains to be mapped. |
| p23 USDCHF SELL later |0.80736 /0.80783 /0.80535|Candidate0.80732 /0.81353 /0.80105. Different protected risk/ERL references. Source CE family/higher bias are unlabelled; neighboring Silver-page annotations cannot supply them. |
| p23 USDCHF SELL earlier |0.80736 /0.80787 /0.80532|Same alternate-feed candidate coordinates at its own earlier snapshot. The two drawings are correlated variants, not two verified executed trades or inferred amendments. |
| p35 GBPJPY BUY H1 |No numerical plan printed|Daily BUY and H1 BO families occur in the diagnostic, but source candle identity and chronology are not established. No numeric plan or fill can be graded. |
| p37 EURGBP SELL H1 |0.86580 /0.86611 /0.86451|An exact0.86580 entry occurs on BO/sweep-BOS candidates, but source names engulfing. Stop0.86719 protects May28H1high0.86714; target is absent. Exact entry alone is not a match. |
| p54 EURGBP BUY H2 |0.86609 /0.86544 /0.86975|Nearest named-BO candidate0.86626 /0.86568 /null. Another closer entry0.86604 is a standing-family candidate. Source KL and valid ERL/target are not replicated. |
| p60 GBPAUD SELL M45 |1.87881 /1.88000 /1.87390|H1 cannot produce M45 candles. Higher context only; entry replay is explicitly unavailable, not a no-trade result. |

Detailed causal IDs, primitive clock decoding and stop/target derivations for
the first cases are in
`../../knowledge-base/study/replay_first_mismatch_analysis.md`.
Source mobile paths can differ from drawn TP plans: USDCAD closes earlier,
GBPJPY shows three mobile entries beside two tools, and p37 shows a short
execution path without full accounting. Later chart traversal of a drawn
TP cannot replace the depicted early exits or establish original orders.

## Fixed selection defect

Before the fix, five equivalent p08 H2 standing candidates at13:00 were all
blocked by the exposure cap, whose slots had been consumed by repeated economic
signals under different stories. `p08_pre_dedup_baseline.json` preserves that
baseline. Operating selection now collapses the same model, TF, KL, eligibility
clock and complete order geometry into one order, retaining alias setup/story
provenance. Later confirmations remain distinct. The first causal context
continues governing cancellation; no new all-context OR cancellation is inferred.
`source_all` retains its independent alternatives.

The corrected p08 episode places one order with four aliases. It is still not
a teacher match: geometry, stop, target, source feed and execution identity differ.
Independent regressions check duplicate aliases, later legitimate confirmations,
source_all alternatives, canonical cancellation and early eligibility filtering.
The filter preserves full context and equals the previous full-result tail.

## Reproduce and inspect

From repository root, with the existing frozen local files present:

```bash
python -m reports.replay_teacher_examples_v2
python -m reports.replay_teacher_examples_v2 --case pdf-p08-eurgbp-buy-1
python -m reports.replay_teacher_examples_v2 --case pdf-p08-eurgbp-buy-1 --profile owner_fixed11
python -m reports.replay_teacher_examples_v2 --index-only
```

Default is source-confirmation only. `--full-output /local/directory` saves
large full engine traces. Frozen inputs are ignored local data; recorded hashes
allow verification but this commit does not redistribute the input exports.
Saved `.json.gz` reports use deterministic gzip and retain full diagnostic
candidate groups, risk provenance, observations and explicit limitations.
Read using `gzip -cd <report>.json.gz` or Python `gzip.decompress`.
`index.json` records their byte hashes, separate profile gates and runtime limits.
The implementation SHA256 identifies actual working-tree code; the recorded
Git commit is its base revision. Fixture and implementation hashes are checked
again after each invocation. Source expectations, tolerances and execution
claims were not changed to obtain a match.

Next work is to reconstruct the specific source CE/range/protection references,
then correct proven reference-scoping defects and rerun these frozen cases under
a new implementation identity. Do not substitute source TP for a missing ERL,
fit a wider tolerance, remove genuine losses or change the printed plans.

Validation:234repository tests pass, including30independent v2/report checks.
All12archived report byte hashes and the unchanged fixture hash were verified.
The normal compressed-output path, index-only rebuild and timed-abort path
were exercised locally. Synthetic engineering checks do not alter source gates.
