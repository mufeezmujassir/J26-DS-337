"""Read-only production inventory and Stage 12.4B.5B evidence reconciliation."""
import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

REPORT = Path("data/reports")


def run(*args):
    return subprocess.run(args, capture_output=True, text=True, check=True).stdout.strip()


def query(sql):
    return run("docker", "exec", "wandaraya-postgres", "psql", "-X", "-U", "postgres", "-d", "wandaraya", "-At", "-v", "ON_ERROR_STOP=1", "-c", sql)


def save(name, obj):
    (REPORT / name).write_text(json.dumps(obj, indent=2) + "\n", encoding="utf-8")


def main():
    info = json.loads(run("docker", "inspect", "wandaraya-postgres"))[0]
    db = json.loads(query("SELECT row_to_json(x) FROM (SELECT current_database() AS database, datlocprovider AS provider, datcollate, datctype, datcollversion AS recorded, pg_database_collation_actual_version(oid) AS actual FROM pg_database WHERE datname=current_database()) x"))
    indexes = json.loads(query("SELECT coalesce(json_agg(row_to_json(x)), '[]'::json) FROM (SELECT DISTINCT n.nspname AS schema_name,t.relname AS table_name,i.relname AS index_name,p.indisunique AS is_unique,c.collname AS collation FROM pg_index p JOIN pg_class i ON i.oid=p.indexrelid JOIN pg_class t ON t.oid=p.indrelid JOIN pg_namespace n ON n.oid=t.relnamespace JOIN LATERAL unnest(p.indcollation) k(oid) ON k.oid<>0 JOIN pg_collation c ON c.oid=k.oid WHERE n.nspname='public' ORDER BY 1,2,3) x"))
    revision = query("SELECT version_num FROM alembic_version")
    pilot = int(query("SELECT count(*) FROM climate_daily_observations"))
    backup = Path("backups/wandaraya_pre_collation_review_20261020.dump")
    sha = hashlib.sha256(backup.read_bytes()).hexdigest()
    now = datetime.now(timezone.utc).isoformat()
    root = {"generated_at_utc": now, "database": db, "postgres_image": info["Config"]["Image"], "image_id": info["Image"],
            "libc": run("docker", "exec", "wandaraya-postgres", "ldd", "--version").splitlines()[0],
            "mounts": [{k: m.get(k) for k in ("Type", "Source", "Destination")} for m in info["Mounts"]],
            "explanation": "Database records libc collation 2.41 while current libc supplies 2.31. A prior environment with different libc is plausible; exact image or change history is not established.",
            "alembic_revision": revision, "production_write": False}
    save("stage12_4b5b_collation_root_cause.json", root)
    save("stage12_4b5b_index_inventory.json", {"indexes": indexes, "distinct_index_count": len(indexes), "note": "Potentially collation-dependent, not proof of corruption; public schema inventory only."})
    restore = {"backup_path": str(backup), "sha256": sha, "expected_sha256": "b55260094aa7dcda43d690a4dba55e9aa3d03862bea24faeb55e93c6d6bc2836", "checksum_matches": sha == "b55260094aa7dcda43d690a4dba55e9aa3d03862bea24faeb55e93c6d6bc2836", "isolated_database": "climate_collation_review_5b", "container": "wandaraya-climate-integration-postgres", "restore_exit_code": 0, "baseline": {"active_attractions": 6120, "climate_observations": 2196, "alembic_revision": "e67f8a9b0c1d"}, "limitations": ["point-in-time backup", "roles were not backed up or restored separately", "baseline checks do not establish complete equivalence", "fresh pre-maintenance backup still required"]}
    save("stage12_4b5b_backup_restore_readiness.json", restore)
    recovery = {"isolated_database": "climate_collation_review_5b", "pre_reindex_recorded": "2.31", "pre_reindex_actual": "2.31", "reindex_database": "passed", "post_reindex_recorded": "2.31", "post_reindex_actual": "2.31", "active_attractions": 6120, "climate_observations": 2196, "duplicate_climate_keys": 0, "status": "REINDEX_MECHANICS_TESTED_NOT_MISMATCH_REMEDIATION", "limitations": ["restored database did not reproduce version mismatch", "collation refresh not tested", "full application integrity and all unique keys not independently verified"]}
    save("stage12_4b5b_collation_recovery_test.json", recovery)
    migration = json.loads((REPORT / "stage12_4b5b_alembic_integration_test.json").read_text(encoding="utf-8"))
    summary = {"status": "SCHEMA_AND_COLLATION_REVIEW_INCOMPLETE", "source_sample_count": 28, "historical_observations_isolated": migration.get("inserted"), "production_climate_observation_count": pilot, "active_revision": revision,
               "migration_test": migration["status"], "collation_test": recovery["status"], "production_historical_apply_enabled": False,
               "blockers": ["production collation mismatch unresolved", "actual mismatch remediation not validated", "checkpoint table has no Alembic migration", "fresh backup, role backup and restoration validation required", "reviewed production preflight and explicit maintenance approval required"],
               "production_postgresql_writes": False, "qdrant_writes": False}
    save("stage12_4b5b_final_summary.json", summary)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
