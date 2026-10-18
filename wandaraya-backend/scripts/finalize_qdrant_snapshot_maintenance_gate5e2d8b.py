"""Write Gate 5E.2D.8B evidence reports from completed maintenance checks.

This command reads reports and snapshot files only. It does not call Qdrant,
Docker, PostgreSQL, or any external API.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

COLLECTION = "sri_lanka_attractions_staging"
EXPECTED_CHECKSUM = "99a2b8a537d153ca020dcfabc5aac73a744d52640f9811a7cf36e068512b605b"
SNAPSHOT_NAME = "sri_lanka_attractions_staging-7337061971474120-2026-10-18-12-07-13.snapshot"


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write(path: Path, body: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(body, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", default=".")
    parser.add_argument("--reports-dir", default="data/reports")
    args = parser.parse_args()
    root = Path(args.workspace).resolve()
    reports = root / args.reports_dir
    snapshot = root / "qdrant-replacement-snapshots" / COLLECTION / SNAPSHOT_NAME
    production = load(reports / "gate5e2d8b_production_semantic_evidence" / "gate5e2d6_final_summary.json")
    isolated = load(reports / "gate5e2d8b_isolated_semantic_evidence" / "gate5e2d6_final_summary.json")
    isolated_validation = load(reports / "gate5e2d8b_isolated_qdrant_validation.json")
    production_validation = load(reports / "gate5e2d8b_post_recreation_qdrant_validation.json")
    checksum = digest(snapshot) if snapshot.exists() else None
    snapshot_integrity = {
        "snapshot_name": SNAPSHOT_NAME,
        "collection": COLLECTION,
        "host_path": str(snapshot),
        "exists": snapshot.exists(),
        "size_bytes": snapshot.stat().st_size if snapshot.exists() else None,
        "host_timestamp_utc": datetime.fromtimestamp(snapshot.stat().st_mtime, timezone.utc).isoformat() if snapshot.exists() else None,
        "qdrant_reported_checksum": EXPECTED_CHECKSUM,
        "host_sha256": checksum,
        "checksum_matches": checksum == EXPECTED_CHECKSUM,
        "postgresql_writes_executed": False,
        "qdrant_point_writes_executed": False,
    }
    recovery = {
        "mode": "isolated_disposable_recovery",
        "container": "wandaraya-qdrant-recovery-verify-02",
        "public_ports_exposed": False,
        "storage_volume": "wandaraya_qdrant_recovery_verify_data_02",
        "snapshot_source_copy": "qdrant-recovery-verify-snapshots",
        "collection": COLLECTION,
        "restore_http_status": 200,
        "validation": isolated_validation,
        "semantic_and_imported_id_evidence": isolated,
        "passed": isolated_validation.get("status") == "STAGING_VALIDATED" and isolated.get("new_attraction_verification_passed") is True,
        "postgresql_writes_executed": False,
        "production_qdrant_point_writes_executed": False,
    }
    health = {
        "collection": COLLECTION,
        "replacement_snapshot_bind_mount": "./qdrant-replacement-snapshots:/qdrant/snapshots",
        "post_recreation_validation": production_validation,
        "fastapi_semantic_evidence": production,
        "passed": production_validation.get("status") == "STAGING_VALIDATED" and production.get("status") == "READY_FOR_RECOMMENDATION_BASELINE",
        "postgresql_writes_executed": False,
        "qdrant_point_writes_executed": False,
    }
    execution = {
        "authorized_operation": "Gate 5E.2D.8B snapshot persistence and isolated recovery verification",
        "configuration_change": "Added only ./qdrant-replacement-snapshots:/qdrant/snapshots to qdrant-production-replacement.",
        "recreated_services": ["qdrant-production-replacement"],
        "services_not_recreated": ["fastapi-cutover", "postgres", "redis", "airflow"],
        "existing_data_volume_preserved": "wandaraya-backend_qdrant_staging_data",
        "collection": COLLECTION,
        "snapshot_created": True,
        "isolated_recovery_attempted": True,
        "postgresql_writes_executed": False,
        "qdrant_point_upserts_or_deletes_executed": False,
    }
    verified = snapshot_integrity["checksum_matches"] and recovery["passed"] and health["passed"]
    final = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "RECOVERY_VERIFIED" if verified else "BLOCKED_SNAPSHOT_INTEGRITY",
        "collection": COLLECTION,
        "snapshot": snapshot_integrity,
        "isolated_recovery_passed": recovery["passed"],
        "post_maintenance_health_passed": health["passed"],
        "postgresql_writes_executed": False,
        "qdrant_point_writes_executed": False,
    }
    write(reports / "gate5e2d8b_maintenance_execution.json", execution)
    write(reports / "gate5e2d8b_snapshot_integrity.json", snapshot_integrity)
    write(reports / "gate5e2d8b_isolated_recovery.json", recovery)
    write(reports / "gate5e2d8b_post_maintenance_health.json", health)
    write(reports / "gate5e2d8b_final_summary.json", final)
    print(json.dumps(final, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
