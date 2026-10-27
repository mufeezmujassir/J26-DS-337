# Stage 12.4B.5B: collation and schema readiness

Status: SCHEMA_AND_COLLATION_REVIEW_INCOMPLETE. Historical production apply remains disabled.

The active database records libc collation 2.41 while the current container provides 2.31. A changed container or libc is a plausible explanation, not an established history. The database revision e67f8a9b0c1d is an Alembic schema revision, not a libc version. Do not rerun or downgrade it to repair collation.

The public-index inventory is in the generated JSON. Indexes listed have collation-bearing keys and are candidates for review, not proven corrupted. Unique indexes require special attention because a rebuild can fail if keys compare equal under the current collation. Review non-public schemas, explicit per-collation versions, constraints and application traffic before maintenance.

The existing point-in-time logical dump was checksum-verified and restored into the separate network-isolated `climate_collation_review_5b` database. Its sampled counts matched; roles and complete application equivalence were not tested in that specific test. The new database was created directly with recorded and actual collation 2.31. `REINDEX DATABASE` completed there and pilot counts remained unchanged; PostgreSQL 17 excludes system catalog indexes from that operation. This does not reproduce or demonstrate repair of the active mismatch; a collation refresh was not tested. The later globals and stopped-state restore evidence and cluster-wide scope are described in STAGE_12_4B5B_PRODUCTION_COLLATION_MAINTENANCE_PLAN.md.

The actual Alembic chain reached e67f8a9b0c1d in `climate_alembic_5b_test`. The 163,632-row import and repeat passed there only after a checkpoint table was created separately for testing. A reviewed Alembic migration for this table and further production-safety work are required; it must not be applied automatically.

## Backup and maintenance preparation

Arrange a maintenance window, stop application writers, confirm storage capacity, and obtain explicit approval for a new timestamped custom-format `pg_dump`, a separate `pg_dumpall --globals-only` roles backup, secure off-host copies and SHA-256 checks. Do not overwrite previous backups or remove the original Docker volume. Record PostgreSQL/PostGIS versions and extension inventory. Restore both into an isolated compatible PostgreSQL/PostGIS instance, validate row counts, ownership, constraints, extensions and application read-only queries, and retain rollback resources.

An illustrative backup command must use a new filename and requires separate approval:

```cmd
docker exec wandaraya-postgres pg_dump -U postgres -Fc -f /tmp/wandaraya_pre_maintenance_NEW_TIMESTAMP.dump wandaraya
docker cp wandaraya-postgres:/tmp/wandaraya_pre_maintenance_NEW_TIMESTAMP.dump backups/wandaraya_pre_maintenance_NEW_TIMESTAMP.dump
certutil -hashfile backups\wandaraya_pre_maintenance_NEW_TIMESTAMP.dump SHA256
```

Replace NEW_TIMESTAMP with a unique value after checking that neither destination exists. Separately capture and protect roles with `pg_dumpall --globals-only`; it can contain sensitive password hashes. Check `pg_dump`/`pg_restore` exit codes and compare container and host hashes. Restore to a separate container and storage; never restore over the active volume.

Only after a DBA reviews scope, index dependencies, potential uniqueness collisions, locking/downtime, verified recovery and explicit authorization should they choose a compatible-runtime migration or a rebuild-and-refresh procedure. Rebuilding must precede any collation-version refresh; a refresh alone does not repair index ordering. Any failure stops maintenance and triggers the reviewed rollback plan. Do not treat this isolated rehearsal as production authorization.
