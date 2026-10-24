# IC Markets collection plan

2026-10-24. Authorized historical collection preparation; this planning pass made
no network, database, broker or remote calls. `reports/teacher_collection_plan.json`
is generated from the unchanged 40 fixtures and hashes their file. It inventories
23 pairs and all entry TFs (M30/M45/H1/H2/H3/H4). There are 46 grouped jobs across
M5 and H1, covering 36 dated fixtures. Four dates remain unresolved: PDFp06 EURCHF,
PDFp22 XAGUSD second plan and both native-video fixtures (XAUUSD/EURUSD). These
remain in inventory but have no guessed collection dates. Every fixture lacks
independently established setup/fill clocks. Snapshot dates select diagnostic
windows only, never an entry clock or acceptance pass.

M5 windows begin 35 calendar days before each snapshot date and finish at the
following UTC midnight plus14 days of outcome coverage (`--forward-days 14`).
Future outcome data must remain excluded from earlier replay eligibility. Overlapping windows for one pair are merged. M5 supports
M45/M30/M15/M5 and H3, but not finer M1 examples or exact intrabar sequencing.
H1 context uses 400 calendar days to provide longer D/W/monthly history without
replicating 400 days of M5. M5/H1 candle equivalence must be checked on overlap;
these are independent provider bars. 35 days is an engineering starting window,
not proof of sufficient structural initialization. 400 days yields approximately
13 monthly bars and cannot establish arbitrary long monthly structures or a
20-month ATR; those contexts remain unresolved unless history is extended.

Run `python -m bishop.collect_teacher_data --plan-only` to reproduce the plan.
Explicit acquisition: `python -m bishop.collect_teacher_data --collect --metadata
PAIR_METADATA.json --out data/teacher_icmarkets`. Optional `--pairs EURGBP GBPJPY`
or repeated `--job-id` limits the selected planned jobs. `--warmup-days` must be
at least35; `--context-days` must be at least the base warmup. Root owns remote
execution/workflows. Pair metadata must declare exact `broker_symbol`,
`calendar_id`, `anchor_id`, `calendar_version` and `asset_class`. Explicit interval
calendars also require their full `calendar` intervals. FX NY17 conventions are
an engineering hypothesis; metals/oil/indices have maintenance/holiday schedules
and broker-specific instruments. NAS100,US30,JP225,USOIL and ETHUSDT cannot be
silently substituted with differently named cash/futures/crypto CFDs. Symbol
details provide display precision/pip units but the existing client does not
export a full historical holiday/session calendar. Missing schedules prevent
complete replay coverage certification; collect raw bars without inventing them.

`HistoricalClient` restricts requests to app/account authentication, symbol
metadata and historical trendbars. It wraps shared Kevin settings read-only,
SELECTs `settings` directly without probing Bishop settings, and bypasses all
refresh/retry-with-refresh paths. Invalid access tokens fail; Kevin owns rotation.
There are no trade/account-position requests or fallback provider. Each H1 request covers seven days; each M5 request covers one day and uses the client's existing historical rate limiter. Missing
bars remain missing. The trendbar response has no pagination/completeness flag;
small request bounds reduce truncation risk but cannot prove completeness. Every
chunk records requested bounds, returned/retained row counts, first/last bar and
empty status. Job success means `RAW_COLLECTED_UNVALIDATED`, never data complete.
Volume is preserved, zero-volume rows counted, and observed FX-weekend candles
are retained and counted as diagnostics rather than discarded. `acquisition_status.json` records
per-job partial progress; failures persist exception type only. Authentication is
attempted once and fails closed with a redacted status artifact. Failed jobs do
not block independent jobs. Raw capture may declare unresolved broker schedules
and anchor; such manifests cannot supply completed replay coverage until reviewed.

Prices are decoded from protobuf integer1e-5 units through Decimal; no floating
point or six-significant-digit formatting. Validate geometry, interval alignment
and display tick grid. Gzip artifacts are deterministic and immutable; a sidecar
records compressed SHA256, stable provider/symbol/source identity, symbol details,
requested/observed bounds, case IDs and retrieval clock. Availability at historical
bar close is an explicit assumption; retrieval time is distinct. BID IC Markets
is alternate-feed diagnostic evidence for charts carrying FOREXCOM/OANDA/etc.;
calendar/anchor/feed equivalence and actual fill/status remain separate questions.
Calendar completeness is deliberately `NOT_CALENDAR_VALIDATED` at collection.

## Supplemental annotations and current schedule evidence

`--clock-annotations reports/teacher_clock_annotations.json --annotations-only`
creates an explicitly exploratory supplementary plan without changing the fixture
snapshot dates, setup/fill clocks or acceptance states. Annotation event-search
bounds and attribution remain embedded in each job; collection uses the declared
candidate collection bounds, extending only their start as needed to provide
35-day M5/400-day H1 warmup before the event-search start. The annotation's explicit
end controls this supplementary collection; default forward14 does not override
it. The saved supplemental plan has eight jobs across EURCHF/XAGUSD/XAUUSD/EURUSD.
After validating initial artifacts, the useful new-date wave is EURUSD+XAUUSD:
initial EURUSD has no job, and initial XAUUSD ends July23 before August4–8. The
initial EURCHF/XAG windows cover proposed event searches and required warmup,
although not every earlier day of the annotations' broader June1 collection
suggestions. Any additional early history should be justified by unresolved
initialization rather than duplicate acquisition by default.

`python -m bishop.collect_teacher_schedules --metadata FILE --out DIR --pairs ALL`
collects current symbol schedule fields through the same read-only authentication
wrapper. `symbol_schedules.json` and its hash contain only symbol ID/name, digits,
pip position, schedule timezone/intervals and holiday fields. Account IDs and
unrelated symbol trading/account fields are excluded. Retrieval time and the
`NOT_HISTORICAL_CALENDAR_CERTIFICATION` label remain explicit. Raw weekly offsets,
end inclusion, timezone history, historical applicability and holidays are not yet
converted to a replay calendar. The separate status file redacts auth/per-symbol
failures to their exception types. This source discovery supersedes the earlier
limitation that the existing convenience client discarded these fields; a
historical calendar still needs independent interpretation and validation.
