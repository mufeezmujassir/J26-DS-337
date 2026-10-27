# Stage 12.4B.7: historical import readiness

Status: HISTORICAL_IMPORT_ENGINEERING_BLOCKED. Production apply remains disabled.

## Read-only evidence

Run `docker exec wandaraya-api-cutover python -m scripts.stage12_4b7_readonly_audit` to collect a consistent read-only snapshot. It fingerprints the pilot observations, pilot dataset and grid, all climate attraction mappings and the three weather tables. Each row is PostgreSQL 17 jsonb text with UTC timezone and C-order sorting; its byte length and bytes are streamed to SHA-256. No columns are excluded. Different PostgreSQL versions, schema, serialization or modifications to legitimate operational weather records can change the hashes. This is a baseline, not historical proof of unchanged data.

The named collation scan found 873 mismatches and no catalog index, column, or pg_depend references. Dynamic SQL, application-generated queries and non-catalog use require review. Do not refresh all named collations automatically. Locate independent production rebuild/refresh execution evidence and request DBA review before any remediation.

## Backup plan — separately authorize before execution

During an approved window, stop writers, verify disk space, create a uniquely named custom-format database dump and separate protected globals dump without overwriting existing files. Record revision, time, size and checksums; copy securely to independent storage. Globals can contain sensitive password hashes. Copy the archive to a newly provisioned isolated matching PostgreSQL/PostGIS environment with separate storage and no public network; restore without touching production, then compare extensions, roles, migration revision, constraints, row counts, representative application queries and content fingerprints. Record restore errors and limitations. The pre-checkpoint backup does not contain the new schema and is not a current recovery point.

Rollback is an operator-reviewed recovery into separate storage, with the original production storage retained; never automatically restore over the active database. Take an up-to-date restore-tested backup immediately before any separately authorized future import.

## Test commands

`python -m pytest tests/climate/test_stage12_4b7_guards.py tests/climate/test_historical_executor.py tests/climate/test_stage12_4b5a_safety.py -q` exercises pure guard and transaction unit tests.

`python -m scripts.test_stage12_4b7_isolated_import` creates a specifically named new test database in the inspected loopback-only integration container, runs the Alembic chain, imports and repeats both batches, and injects rollback. It refuses to reuse an existing test database. It does not exercise all Stage 12.4B.7 requirements; see the integration report limitations.

The production CLI does not use the new pure guard. A production-aware fail-closed preflight, independently configured identity verification, explicit operator authorization and integrated guard tests remain to be implemented. No production historical import is permitted in this stage.
