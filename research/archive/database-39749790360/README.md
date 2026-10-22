Research database archive. One compressed SQL file per experiment run ID.
Restore into a separate research database: gunzip -c <run-id>.sql.gz | mysql <database>
UTC timestamps and UTF-8 payload bytes are preserved. manifest.json contains file hashes and row counts.
Contains research data only; no user profiles, settings, live biases, entries, orders or credentials.
