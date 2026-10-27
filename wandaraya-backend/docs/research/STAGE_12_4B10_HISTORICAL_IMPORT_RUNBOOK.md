# Stage 12.4B.10: historical import

Status: **not ready for production import**. The current CLI rejects `--apply` even with `--confirm-apply`. No production batch import or reconciliation commands are currently supported; do not invent flags or disable the hard stop.

The actual CLI now supports `--isolated-test` for a narrowly defined loopback test database. Its two-batch insertion and repeat test passed: see `data/reports/stage12_4b10_cli_isolated_test.json`. This is not a production command. Ed25519 verification has been tested with synthetic keys but is not connected to production execution; no independent production trust key is provisioned.

The following supported commands perform file-only validation, not a full database preflight:

```cmd
docker exec -it wandaraya-api-cutover python -m scripts.ingest_stage12_4b5_historical --manifest data/reports/stage12_4b5_source_provenance.json --dataset-version nasa_power_daily_v2.10.0_historical_2010_2025_batch01 --dry-run
docker exec -it wandaraya-api-cutover python -m scripts.ingest_stage12_4b5_historical --manifest data/reports/stage12_4b5_source_provenance.json --dataset-version nasa_power_daily_v2.10.0_historical_2010_2025_batch02 --dry-run
```

Expected historical counts are 17532 and 146100, combined 163632. The pilot must remain 2196. Inspect production checkpoints with:

```cmd
docker exec wandaraya-postgres psql -X -U postgres -d wandaraya -c "SELECT COUNT(*) AS checkpoints FROM climate_historical_import_checkpoints; SELECT v.product_version, COUNT(o.id) FROM climate_dataset_versions v LEFT JOIN climate_daily_observations o ON o.dataset_version_id=v.id GROUP BY v.product_version ORDER BY v.product_version;"
```

The Stage 12.4B.9 archive and isolated restoration are documented in `data/reports/stage12_4b9_backup_readiness.json`; the archive SHA-256 is `85ce4023c38efc39fde5d151c133e9829d361fae5cc3fd3f7b68ec1441e5073e`. Restore used --no-owner --no-acl, so role and permission equivalence was not tested. A protected off-host copy and an operator-reviewed role/ACL recovery plan are needed for disaster recovery. Recheck backup freshness, current target identity, constraints and content baseline immediately before any later approved execution.

Current recovery: do not automatically restore over the active production volume. Preserve backups, failed import reports, checkpoints and the database; seek operator review before any recovery action. The isolated primitive can resume/repeat samples, but a production CLI retry and post-batch reconciliation do not yet exist and must not be claimed as available.

Missing work: integrate and test the complete production authorization-bound orchestration, database identity, sources, schema and collation, backup and baseline verification, exact transaction scope, durable reporting and post-import reconciliation. Only after the entire isolated CLI suite passes should separate explicit production import authorization be requested.
