"""Gate 5E.2D.7 read-only snapshot persistence and recovery planning.

This command inspects Docker metadata and existing reports only.  It never
creates a snapshot, changes Compose, restarts a service, restores a collection,
or writes PostgreSQL/Qdrant records.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPLACEMENT_CONTAINER = "wandaraya-qdrant-replacement"
REPLACEMENT_COLLECTION = "sri_lanka_attractions_staging"
REPLACEMENT_VERSION = "qdrant/qdrant:v1.19.1"
SNAPSHOT_HOST_DIRECTORY = "qdrant-replacement-snapshots"
LEGACY_SNAPSHOT = "qdrant-snapshots/sri_lanka_attractions-1336472673414113-2026-10-18-07-30-23.snapshot"
STAGING_SNAPSHOT_NAME = "sri_lanka_attractions_staging-7337061971474120-2026-10-18-10-27-16.snapshot"
STAGING_SNAPSHOT_CHECKSUM = "a9bd120d7036c4c960494fd41a6bfdd326a4657ee418b70b1020f0c531a05e9f"
MINIMUM_SAFETY_MARGIN_BYTES = 512 * 1024 * 1024


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def safe_snapshot_directory(path: str) -> bool:
    normalized = Path(path).as_posix().strip("/").lower()
    return normalized not in {"", ".", "qdrant-data", "qdrant-data-quarantine-2026-10-18", "postgres-data"} and ".." not in normalized.split("/")


def storage_requirement(snapshot_bytes: int) -> int:
    """One exported snapshot, one isolated recovery copy, plus operational margin."""
    return (2 * max(snapshot_bytes, 1)) + MINIMUM_SAFETY_MARGIN_BYTES


def recovery_target_is_isolated(*, container: str, volume: str, production_container: str, production_volume: str) -> bool:
    return bool(container and volume and container != production_container and volume != production_volume)


def inspect_container(name: str) -> dict[str, Any]:
    completed = subprocess.run(
        ["docker", "inspect", name], capture_output=True, text=True, check=False,
    )
    if completed.returncode != 0:
        return {"status": "failed", "error": completed.stderr.strip() or "docker inspect failed"}
    payload = json.loads(completed.stdout)[0]
    mounts = payload.get("Mounts", [])
    return {
        "status": "ok",
        "name": payload.get("Name", "").lstrip("/"),
        "image": payload.get("Config", {}).get("Image"),
        "state": payload.get("State", {}).get("Status"),
        "mounts": [
            {key: mount.get(key) for key in ("Type", "Name", "Source", "Destination", "RW")}
            for mount in mounts
        ],
    }


def mount_at(mounts: list[dict[str, Any]], destination: str) -> dict[str, Any] | None:
    return next((mount for mount in mounts if mount.get("Destination") == destination), None)


def markdown_plan(*, storage: dict[str, Any], mount: dict[str, Any]) -> str:
    return f"""# Gate 5E.2D.7 — Durable Qdrant Snapshot Persistence Plan

## Current evidence

- Active replacement container: `{REPLACEMENT_CONTAINER}`
- Collection: `{REPLACEMENT_COLLECTION}`
- Data volume: `{mount.get('Name')}` mounted at `/qdrant/storage`
- A `/qdrant/snapshots` mount is currently absent.
- Legacy snapshot remains preserved at `{LEGACY_SNAPSHOT}`. It must not be used as the replacement recovery point because its isolated restore previously failed.
- The prior staging snapshot metadata is recorded, but it is not visible to the active replacement service.

## Reviewed configuration change — do not apply without separate authorization

Add this **additional** mount to `qdrant-production-replacement`; retain the existing data-volume mount unchanged:

```yaml
    volumes:
      - qdrant_staging_data:/qdrant/storage
      - ./{SNAPSHOT_HOST_DIRECTORY}:/qdrant/snapshots
```

The new host directory is dedicated to replacement snapshots. It must never be `qdrant-data`, the quarantine directory, or the legacy snapshot directory.

## Storage assessment

- Host free capacity observed: `{storage['free_bytes']}` bytes
- Conservative required capacity: `{storage['required_bytes']}` bytes
- Assessment: `{storage['status']}`

## Retention

Keep at least the two newest validated replacement snapshots and their SHA-256 manifests. Retain the quarantine directory and legacy snapshot until a separate rollback-retention sign-off. Do not overwrite a snapshot filename.
"""


def execution_plan() -> str:
    return f"""# Gate 5E.2D.7 — Separately Authorized Snapshot Execution Plan

This plan is intentionally not executed by the Gate 5E.2D.7 command.

1. Confirm the reviewed Compose mount has been applied and the replacement container has been recreated under separate authorization.
2. Verify collection identity and capacity:

```cmd
docker exec -it {REPLACEMENT_CONTAINER} python -c "import requests; r=requests.get('http://localhost:6333/collections/{REPLACEMENT_COLLECTION}',timeout=30); print(r.json())"
```

3. Create the snapshot and record the returned name/checksum:

```cmd
docker exec -it {REPLACEMENT_CONTAINER} python -c "import requests,json; r=requests.post('http://localhost:6333/collections/{REPLACEMENT_COLLECTION}/snapshots',timeout=600); print(json.dumps(r.json(),indent=2)); r.raise_for_status()"
```

4. Confirm the returned file exists under `{SNAPSHOT_HOST_DIRECTORY}` and compare the API checksum with Windows SHA-256:

```cmd
certutil -hashfile "{SNAPSHOT_HOST_DIRECTORY}\\<SNAPSHOT_NAME>" SHA256
```

5. Save the API metadata, checksum, size, timestamp, collection name, Qdrant version, and document-scope hash beside the exported snapshot. A checksum mismatch or missing file stops the process.
"""


def recovery_plan() -> str:
    return f"""# Gate 5E.2D.7 — Isolated Snapshot Recovery Validation Plan

Use a disposable container, a **new** Docker volume, and Qdrant `v1.19.1`. Never target `{REPLACEMENT_CONTAINER}` or its `qdrant_staging_data` volume.

```powershell
docker volume create wandaraya_qdrant_recovery_verify_data
docker run -d --name wandaraya-qdrant-recovery-verify -p 127.0.0.1:6336:6333 -v wandaraya_qdrant_recovery_verify_data:/qdrant/storage -v "${{PWD}}\\{SNAPSHOT_HOST_DIRECTORY}:/qdrant/snapshots:ro" {REPLACEMENT_VERSION}
```

Restore only into the disposable container using the exported snapshot. Then run the existing read-only validator against `http://localhost:6336` and `{REPLACEMENT_COLLECTION}`. Required checks are: 6,120 points, full scroll, filtered scroll, direct retrieval, 1,024 dimensions, and vector search. Destroy the disposable container/volume only after an explicit review; do not touch production.
"""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reports-dir", default="data/reports")
    parser.add_argument("--workspace", default=".")
    args = parser.parse_args()
    workspace = Path(args.workspace).resolve()
    reports_dir = Path(args.reports_dir)
    if not reports_dir.is_absolute():
        reports_dir = workspace / reports_dir

    container = inspect_container(REPLACEMENT_CONTAINER)
    mounts = container.get("mounts", []) if container.get("status") == "ok" else []
    data_mount = mount_at(mounts, "/qdrant/storage")
    snapshot_mount = mount_at(mounts, "/qdrant/snapshots")
    legacy = workspace / LEGACY_SNAPSHOT
    legacy_bytes = legacy.stat().st_size if legacy.is_file() else 0
    required_bytes = storage_requirement(legacy_bytes)
    free_bytes = shutil.disk_usage(workspace).free
    storage = {
        "free_bytes": free_bytes,
        "largest_known_snapshot_bytes": legacy_bytes,
        "required_bytes": required_bytes,
        "status": "sufficient" if free_bytes >= required_bytes else "insufficient",
    }
    d6_path = workspace / "data/reports/gate5e2d6_final_summary.json"
    d6 = json.loads(d6_path.read_text(encoding="utf-8")) if d6_path.exists() else {}
    safe_directory = safe_snapshot_directory(SNAPSHOT_HOST_DIRECTORY)
    checks = {
        "replacement_container_running": container.get("state") == "running",
        "replacement_uses_expected_image": container.get("image") == REPLACEMENT_VERSION,
        "replacement_data_volume_present": bool(data_mount and data_mount.get("Type") == "volume"),
        "replacement_snapshot_mount_absent": snapshot_mount is None,
        "legacy_snapshot_preserved": legacy.is_file(),
        "d6_semantic_status_verified": d6.get("status") == "SEMANTIC_SEARCH_VERIFIED",
        "dedicated_snapshot_host_directory_safe": safe_directory,
        "host_storage_sufficient_for_planned_snapshot_and_recovery": storage["status"] == "sufficient",
        "proposed_recovery_target_isolated": recovery_target_is_isolated(
            container="wandaraya-qdrant-recovery-verify",
            volume="wandaraya_qdrant_recovery_verify_data",
            production_container=REPLACEMENT_CONTAINER,
            production_volume=data_mount.get("Name", "") if data_mount else "",
        ),
    }
    status = "READY_FOR_SEPARATE_SNAPSHOT_AUTHORIZATION"
    blockers: list[str] = []
    if storage["status"] != "sufficient":
        status, blockers = "BLOCKED_INSUFFICIENT_STORAGE", ["insufficient_free_disk_for_snapshot_and_isolated_recovery"]
    elif not (checks["replacement_data_volume_present"] and checks["dedicated_snapshot_host_directory_safe"]):
        status, blockers = "BLOCKED_UNSAFE_MOUNT_CONFIGURATION", ["production_data_mount_or_proposed_snapshot_path_unsafe"]

    assessment = {
        "generated_at_utc": utc_now(), "mode": "read_only_infrastructure_assessment",
        "container": container, "active_data_mount": data_mount, "active_snapshot_mount": snapshot_mount,
        "snapshot_mount_persistence": "not_configured", "legacy_snapshot": {
            "path": LEGACY_SNAPSHOT, "exists": legacy.is_file(), "size_bytes": legacy_bytes,
        },
        "prior_staging_snapshot": {
            "name": STAGING_SNAPSHOT_NAME, "checksum": STAGING_SNAPSHOT_CHECKSUM,
            "visible_to_active_replacement": False,
            "reason": "The active replacement has no /qdrant/snapshots mount.",
        },
        "gate5e2d6_summary_status": d6.get("status"), "storage": storage, "checks": checks,
        "postgresql_writes_executed": False, "qdrant_writes_executed": False,
    }
    summary = {
        "generated_at_utc": utc_now(), "status": status, "blockers": blockers,
        "collection": REPLACEMENT_COLLECTION, "replacement_container": REPLACEMENT_CONTAINER,
        "storage": storage, "snapshot_mount_currently_present": snapshot_mount is not None,
        "proposed_snapshot_directory": SNAPSHOT_HOST_DIRECTORY,
        "postgresql_writes_executed": False, "qdrant_writes_executed": False,
    }
    write_json(reports_dir / "gate5e2d7_storage_assessment.json", assessment)
    (reports_dir / "gate5e2d7_snapshot_persistence_plan.md").write_text(markdown_plan(storage=storage, mount=data_mount or {}), encoding="utf-8")
    (reports_dir / "gate5e2d7_snapshot_execution_plan.md").write_text(execution_plan(), encoding="utf-8")
    (reports_dir / "gate5e2d7_recovery_validation_plan.md").write_text(recovery_plan(), encoding="utf-8")
    write_json(reports_dir / "gate5e2d7_test_results.json", {
        "mode": "offline_unit_tests_required", "test_module": "tests/time_context/test_gate5e2d7_snapshot_recovery.py",
        "runtime_safety_checks": checks, "postgresql_writes_executed": False, "qdrant_writes_executed": False,
    })
    write_json(reports_dir / "gate5e2d7_final_summary.json", summary)
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
