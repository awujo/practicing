# Offline v2 build verification — 2026-10-23

This checkpoint follows the completed sampled-source study at `5e7b79e`.
The build is in `bishop/v2/`; the legacy engine and source fixture are unchanged.
Contracts record source mappings, timing and numerical choices. Independent
implementation review is in `build_contract_review.md`.

## Completed engineering checks

- Entire repository suite: **228 passed in 5.13 seconds**.
- Of these, 24 independent v2 regressions cover causal prefixes of a nonempty
  full pipeline, missing nominal aggregate bins, source lifecycle/counterweekly
  integration, strict invalid policies, bar identity and evidence immutability,
  delayed ATR dependencies, session gaps/availability, indexed role equivalence,
  invalid management inputs, boundary cancellation, stale paper projections,
  insufficient resolution and experimental zone-edge geometry.
- Compilation/import, actual engine → runner → SQLite persistence, duplicate
  result import and manual job state transitions checked. Delivery is disabled.
- A deterministic 180 H1-bar seed-41 synthetic full pipeline completes in
  **2.027 seconds** after role indexing. The earlier independent probe exceeded
  60 seconds. A focused entry benchmark improved 0.607→0.093 seconds with the
  entire entry-result hash unchanged. These are engineering measurements, not
  teacher-example matches or a historical-scale runtime guarantee.

## Existing frozen feed diagnostic

The actual CLI completed using the already-present EURGBP IC Markets BID H1
file, SHA256 `815f153eccb7ac981c06850bab82a5cd39dd41146810497f7b115d0839d559b0`.
No new acquisition occurred. Declared tick0.00001, distance unit0.0001,
FX NY calendar/17:00 wall anchor; context starts2026-07-20T21:00Z,
scan starts2026-07-27T00:00Z, as-of2026-07-31T21:00Z. Explicit zero-cost
hypothesis, owner_aggressive/owner_fixed11, H4 origins, H4/H2/H1 entries,
nearest ERL and cap10. This exercises feed, aggregation, route selection,
risk and executable simulation. It produces orders and retains cancellation,
expiry, censoring and open outcomes.

This is **not** a source-example replay or profitability result. The source
chart is FOREXCOM; this frozen file is IC Markets. Exact source timing and
execution remain unresolved. Repeated alternative candidates/overlapping
stories require source-case evaluation before operational selection can be
called faithful. Output is local under `/tmp/bishop_v2_frozen_diagnostic.json`;
it is not a durable uploaded artifact and may disappear with the workspace.
No teacher prices or expectations were used to construct engine signals.

## Scope and remaining work

The implementation covers local data, complete aggregates, close-line A/V and
OC, independent wick pools, scoped ranges, origin and confirmation stories,
entry families including optional nesting, selectable protection/targets,
prospective caps, strict execution, paper persistence, authenticated app and
manual local job worker. New stores use the owner's fixed-11 aggressive preset;
source protection and zone-edge experiment are explicit alternatives.

It does not establish a continuously running incremental detector, broker
readiness or teacher acceptance. Existing 40 observations retain their source
verification gaps; no fixtures, tolerances or expected prices were changed.
Source-discretionary exceptions and PDFp8 referents remain visible unresolved
support. Session boundaries must be declared; optional numerical impulse must
be declared rather than asserted as a teacher constant. Next source work is
case-level chronology/feed/geometry verification followed by strict replay and
explanation of each actual mismatch. A missing input is not an engine match.
