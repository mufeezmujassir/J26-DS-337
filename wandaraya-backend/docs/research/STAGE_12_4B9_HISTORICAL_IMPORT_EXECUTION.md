# Stage 12.4B.9 historical import

Status: implementation incomplete; do not execute production historical import. The existing --apply command deliberately refuses all writes. No valid production import or reconciliation commands are available yet.

The user authorized a fresh backup and isolated restore. `backups/wandaraya_stage12_4b9_20261020_134358.dump` has SHA-256 `85ce4023c38efc39fde5d151c133e9829d361fae5cc3fd3f7b68ec1441e5073e`; it was restored into a new database in the network-none test container. Revision, extension versions, public constraint definitions and selected protected-table content fingerprints match. The restore omitted ownership and ACL restoration; complete roles/application equivalence and off-host recovery were not tested. The backup is point-in-time and must be assessed for freshness at any later execution.

The actual migration chain and both historical batches were tested in a new isolated database, including 163632 insertions, idempotent repeat, failure rollback and exact synthetic protected-table fingerprint comparison. See `data/reports/stage12_4b9_integration_tests.json`.

The production importer still requires non-bypassable source/target identity checks, data version and grid provisioning, reviewed restore and baseline gates, per-sample checkpoint execution, failure handling and post-batch reconciliation. It also needs complete isolated end-to-end rejection tests. `--confirm-apply` must never bypass a failed prerequisite. Once implemented and tested, produce actual commands for read-only preflight and each batch and obtain separate explicit authorization before any historical production writes.

No production restore or schema change was performed; preserve existing backups and original PostgreSQL storage. No collation refresh or reindex was performed in this stage.
