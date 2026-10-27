# PostgreSQL collation maintenance: review-only plan

Status: NOT AUTHORIZED AND NOT READY TO EXECUTE. No production commands in
this document should be executed without a separately reviewed runbook and
explicit authorization. The operator has elected to keep the API and Airflow
stopped while this plan is prepared.

## Current evidence

* Production PostgreSQL 17.5 uses libc en_US.utf8; `wandaraya`, `postgres`,
  and `template1` record 2.41 while the runtime reports 2.31. A previous image
  or libc change could explain this, but exact history is unknown. `template0`
  must not be modified on the basis of a null recorded version.
* `wandaraya` has 30 potentially affected user indexes, including 23 unique.
  Each of the three databases has 36 potentially affected system indexes,
  including 35 unique. These inventories are candidates, not proof of damage.
* A stopped-state dump has SHA-256
  `c2249dc2580658d2cb94ba97921880ab3335055aa2b87ba2219f8c1a1e343cad`.
  Its isolated restore succeeded with 6,120 active attractions, 2,196 climate
  observations, six mappings, 1,162 weather readings and Alembic
  `e67f8a9b0c1d`. A separately backed-up globals file was also restored in a
  network-isolated cluster. Preserve the data directory and all backups.
* An isolated `REINDEX DATABASE` completed in a restored copy that already
  matched 2.31/2.31. It did not demonstrate repair of the actual mismatch.
  **Important correction:** PostgreSQL 17 `REINDEX DATABASE` excludes system
  catalog indexes. That earlier test did not rebuild them.

## Preconditions before any production change

1. Confirm the image digest, storage mount, free space, stopped writers, all
   database connections, baseline counts, extensions, roles, exact backup hashes
   and backup freshness. Restore latest backup and globals to a separate test
   cluster and test roles, owners, ACLs and representative application reads.
   A logical `wandaraya` dump and globals alone are not a full cluster backup:
   independently assess user data and recovery for `postgres`, `template1`,
   tablespaces and cluster configuration.
2. Inventory collation dependencies in all schemas and databases, explicit
   collations and their versions, objects beyond ordinary indexes (constraints,
   partitioning and expressions), system catalogs and shared catalogs. Analyze
   unique-key conflicts under the current runtime without trusting potentially
   stale index ordering. Stop if the scope cannot be established.
3. Choose with a PostgreSQL DBA between restoring a verified compatible
   runtime and rebuilding affected objects under the current runtime. Do not
   change images or mount the production volume into a different server merely
   to see whether it works. Prove PostgreSQL/PostGIS, libc, filesystem and
   locale compatibility in a separate environment first.
4. Rehearse the approved per-database system and user index procedures in a
   disposable restored cluster, including permissions, locking, disk usage,
   failure/unique-conflict behavior, representative read checks and recovery.
   Because a logical restore creates objects under the current runtime, this
   does not by itself recreate the original 2.41/2.31 mismatch. Establish a
   suitable mismatch-reproduction method or explicitly document and accept the
   limitation with specialist review. Do not use the live cluster to simulate it.
5. Prepare a separately authorized, exact command sequence, a maintenance
   window and a verified rollback path. Confirm storage overhead for rebuilds,
   physical preservation and restore. Retain the existing stopped-state dump,
   globals backup, and production volume until recovery is confirmed.

## Proposed execution logic for review, not authorization

* Maintain a per-database checklist for `wandaraya`, `postgres` and `template1`.
  Keep applications stopped and verify that no sessions interfere. Do not
  change `template0`.
* A database reindex does not rebuild system catalogs. PostgreSQL 17 has a
  separate `REINDEX SYSTEM` operation, including shared system catalogs; it
  needs appropriate privilege and careful review. These commands cannot be
  treated as a single atomic transaction, and successful earlier operations
  may remain if a later one fails. System catalogs cannot be reindexed
  concurrently. Do not assume index rebuilding addresses all collation-dependent
  objects or underlying data/constraint issues.
* Rebuild all objects the reviewed procedure identifies as necessary. If a
  unique index fails, stop; record the exact error and investigate duplicates
  without deleting, merging or rewriting data. Do not refresh the database's
  recorded collation version or proceed to another database automatically.
* Only after the required rebuilds and checks succeed for a database should the
  DBA consider refreshing that database's recorded default collation version.
  Refresh changes metadata; it does not prove object correctness. Explicitly
  versioned collations may need separate handling after review.
* Verify collations, indexes, constraints and representative data and reads;
  compare production baselines, including the pilot, and test application
  access. Restart API and Airflow only after approval of the checks.

## Failure and rollback

If any preflight, rebuild or verification fails, stop immediately and preserve
the logs, database and backups. Do not retry blindly, refresh versions, delete
data, or automatically restore over production. A logical backup may be
restored to a new separate cluster after explicit authorization; cutover or
volume replacement requires a separately reviewed recovery plan. A DBA must
evaluate the state of all three databases and any already-completed operations.

## Separate historical-import gate

Production historical import remains disabled. A test-only checkpoint table
was added outside Alembic in the isolated test, so a reviewed migration and
production-identity, collation, backup, checksum, count and authorization
guards are still required. Never change the 2024 pilot during this maintenance.

References: https://www.postgresql.org/docs/17/sql-reindex.html and
https://www.postgresql.org/docs/17/sql-altercollation.html.
