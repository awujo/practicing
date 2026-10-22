# Research archives

`database-<workflow-run>/` contains one `.sql.gz` per experiment run_id exported from MySQL research_records.
Each directory includes a file/row/hash manifest and complete disposable-MySQL restoration verification.
The workflow publishes the archive commit before removing matching research records. Live and user tables
are excluded. A failed or changed row is preserved rather than deleted; successful cleanup has cleanup-result.json.

To restore: create a separate UTF-8 research database, then
`gunzip -c database-<workflow-run>/<run-id>.sql.gz | mysql <research-database>`.
The dumps use UTC and hex strings to preserve JSON, Unicode, quotes and newlines exactly.

`full-history-2026-10-20.zip` preserves all28 full-history study result archives and analysis, including
ledgers that were never published to MySQL because of its128MiB research storage cap. These are result
ledgers/reports, not the complete source candle history. Archive database counts only describe DB-published
records, not all experimental outputs. See research/results/2026-10-20/ANALYSIS.md and the target-ladder report.

MySQL research publication/pruning share GET_LOCK('slk_research_records',10), released on connection close,
and workflow concurrency slk-research-publication. Do not write this table via external scripts bypassing that lock.
No automatic re-publication is scheduled. Future manual study publication would use database capacity again.
