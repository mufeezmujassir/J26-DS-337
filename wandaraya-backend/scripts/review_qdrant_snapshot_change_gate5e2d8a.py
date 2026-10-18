"""Gate 5E.2D.8A read-only review of the production snapshot mount change."""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from scripts.prepare_qdrant_snapshot_recovery_gate5e2d7 import (
    LEGACY_SNAPSHOT,
    REPLACEMENT_COLLECTION,
    REPLACEMENT_CONTAINER,
    REPLACEMENT_VERSION,
    SNAPSHOT_HOST_DIRECTORY,
    safe_snapshot_directory,
    storage_requirement,
)


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def inspect(name: str) -> dict[str, Any]:
    result = subprocess.run(["docker", "inspect", name], capture_output=True, text=True, check=False)
    if result.returncode:
        return {"status": "failed", "error": result.stderr.strip()}
    item = json.loads(result.stdout)[0]
    return {
        "status": "ok",
        "state": item.get("State", {}).get("Status"),
        "image": item.get("Config", {}).get("Image"),
        "mounts": [{key: value.get(key) for key in ("Type", "Name", "Source", "Destination", "RW")} for value in item.get("Mounts", [])],
    }


def proposed_diff() -> str:
    return f"""--- a/docker-compose.yml
+++ b/docker-compose.yml
@@ qdrant-production-replacement
     volumes:
       - qdrant_staging_data:/qdrant/storage
+      - ./{SNAPSHOT_HOST_DIRECTORY}:/qdrant/snapshots
"""


def markdown_review(*, compose_files: list[str], active: dict[str, Any], host_path: Path, preflight: dict[str, Any]) -> str:
    mounts = "\n".join(f"- `{item.get('Type')}` `{item.get('Name') or item.get('Source')}` → `{item.get('Destination')}`" for item in active.get("mounts", []))
    return f"""# Gate 5E.2D.8A — Final Production Snapshot Change Review

## Active configuration

- Compose service: `qdrant-production-replacement`
- Active container: `{REPLACEMENT_CONTAINER}`
- Image: `{active.get('image')}`
- Collection: `{REPLACEMENT_COLLECTION}`
- Active Compose files: {', '.join(f'`{item}`' for item in compose_files)}

### Current mounts

{mounts}

The persistent data volume remains unchanged. The proposed bind mount is additional and targets `/qdrant/snapshots`, not `/qdrant/storage`.

## Minimal reviewed diff — not applied

```diff
{proposed_diff()}```

## Host path and capacity

- Intended host snapshot directory: `{host_path}`
- Directory exists now: `{preflight['snapshot_host_directory_exists']}`
- Parent directory writable: `{preflight['snapshot_parent_writable']}`
- Free bytes: `{preflight['free_bytes']}`
- Conservative required bytes: `{preflight['required_bytes']}`

The directory must be created only during the separately authorized maintenance operation. It is deliberately not created during this review.

## Expected impact

Only the replacement Qdrant container is recreated. PostgreSQL, Redis, FastAPI, Qdrant points, and the persistent data volume are unchanged. Semantic requests can return controlled Qdrant-unavailable responses while Qdrant restarts; plan a short maintenance window. Expected interruption is normally tens of seconds, but it is not guaranteed and must be measured during execution.

## Protected legacy assets

- `{LEGACY_SNAPSHOT}` remains untouched.
- `qdrant-data-quarantine-2026-10-18` remains untouched.
- No production restore is part of this change.
"""


def execution_commands() -> str:
    return f"""# Gate 5E.2D.8A — Commands for Separately Authorized Maintenance

Run one command at a time in Windows CMD from the repository root. Do not concatenate commands.

## 1. Pre-maintenance checks

```cmd
docker compose --profile cutover ps
docker exec -it {REPLACEMENT_CONTAINER} python -c "import requests,json; r=requests.get('http://localhost:6333/collections/{REPLACEMENT_COLLECTION}',timeout=30); print(json.dumps(r.json(),indent=2)); r.raise_for_status()"
```

## 2. Apply only the reviewed mount change

Create `{SNAPSHOT_HOST_DIRECTORY}` and add the one reviewed Compose line shown in `gate5e2d8a_change_review.md`. Then validate the Compose file:

```cmd
mkdir {SNAPSHOT_HOST_DIRECTORY}
docker compose --profile cutover config --quiet
```

## 3. Recreate only replacement Qdrant

```cmd
docker compose --profile cutover up -d --force-recreate qdrant-production-replacement
```

## 4. Post-recreation health check

```cmd
docker exec -it {REPLACEMENT_CONTAINER} python -c "import requests,json; r=requests.get('http://localhost:6333/collections/{REPLACEMENT_COLLECTION}',timeout=30); print(json.dumps(r.json(),indent=2)); r.raise_for_status()"
curl.exe -sS --max-time 30 http://localhost:8000/health
```

## 5. Create and verify a durable snapshot

```cmd
docker exec -it {REPLACEMENT_CONTAINER} python -c "import requests,json; r=requests.post('http://localhost:6333/collections/{REPLACEMENT_COLLECTION}/snapshots',timeout=600); print(json.dumps(r.json(),indent=2)); r.raise_for_status()"
certutil -hashfile "{SNAPSHOT_HOST_DIRECTORY}\\<SNAPSHOT_NAME_FROM_API_RESPONSE>" SHA256
```

The API metadata checksum and `certutil` checksum must match. Any mismatch, missing host file, wrong collection name, or degraded collection stops the maintenance operation.
"""


def rollback_plan() -> str:
    return f"""# Gate 5E.2D.8A — Rollback Plan

## Configuration rollback

If the replacement fails its health check after recreation, remove only the added snapshot bind-mount line from `qdrant-production-replacement` and recreate only that service:

```cmd
docker compose --profile cutover up -d --force-recreate qdrant-production-replacement
docker exec -it {REPLACEMENT_CONTAINER} python -c "import requests; r=requests.get('http://localhost:6333/collections/{REPLACEMENT_COLLECTION}',timeout=30); print(r.status_code); r.raise_for_status()"
```

This retains `wandaraya-backend_qdrant_staging_data`; do not use `docker volume rm`, do not start the old Qdrant, and do not restore the legacy snapshot.

## Data recovery validation

Restore any newly created replacement snapshot only into a separately named disposable container and volume. A production restore requires a new, separate authorization.

## Protected assets

Keep `qdrant-data-quarantine-2026-10-18` and `{LEGACY_SNAPSHOT}` untouched throughout rollback and later review.
"""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", default=".")
    parser.add_argument("--reports-dir", default="data/reports")
    args = parser.parse_args()
    workspace = Path(args.workspace).resolve()
    reports_dir = Path(args.reports_dir)
    if not reports_dir.is_absolute():
        reports_dir = workspace / reports_dir
    compose_files = sorted(path.name for path in workspace.glob("docker-compose*.y*ml"))
    active = inspect(REPLACEMENT_CONTAINER)
    mounts = active.get("mounts", [])
    data_mount = next((item for item in mounts if item.get("Destination") == "/qdrant/storage"), None)
    snapshot_mount = next((item for item in mounts if item.get("Destination") == "/qdrant/snapshots"), None)
    intended_host_path = workspace / SNAPSHOT_HOST_DIRECTORY
    legacy = workspace / LEGACY_SNAPSHOT
    free_bytes = shutil.disk_usage(workspace).free
    required_bytes = storage_requirement(legacy.stat().st_size if legacy.is_file() else 0)
    d7_path = workspace / "data/reports/gate5e2d7_final_summary.json"
    d7 = json.loads(d7_path.read_text(encoding="utf-8")) if d7_path.exists() else {}
    preflight = {
        "generated_at_utc": now(),
        "active_container_running": active.get("state") == "running",
        "active_image_expected": active.get("image") == REPLACEMENT_VERSION,
        "compose_files": compose_files,
        "existing_data_mount": data_mount,
        "existing_data_volume_unchanged": bool(data_mount and data_mount.get("Type") == "volume" and data_mount.get("Name") == "wandaraya-backend_qdrant_staging_data"),
        "snapshot_mount_currently_absent": snapshot_mount is None,
        "snapshot_host_directory": str(intended_host_path),
        "snapshot_host_directory_exists": intended_host_path.exists(),
        "snapshot_parent_writable": os.access(workspace, os.W_OK),
        "snapshot_path_safe": safe_snapshot_directory(SNAPSHOT_HOST_DIRECTORY),
        "free_bytes": free_bytes,
        "required_bytes": required_bytes,
        "storage_sufficient": free_bytes >= required_bytes,
        "legacy_snapshot_exists": legacy.is_file(),
        "quarantine_directory_exists": (workspace / "qdrant-data-quarantine-2026-10-18").is_dir(),
        "gate5e2d7_status": d7.get("status"),
        "postgresql_writes_executed": False,
        "qdrant_writes_executed": False,
    }
    required = (
        "active_container_running", "active_image_expected", "existing_data_volume_unchanged",
        "snapshot_mount_currently_absent", "snapshot_parent_writable", "snapshot_path_safe",
        "storage_sufficient", "legacy_snapshot_exists", "quarantine_directory_exists",
    )
    blockers = [name for name in required if not preflight[name]]
    preflight["status"] = "READY_FOR_EXPLICIT_MAINTENANCE_AUTHORIZATION" if not blockers else "BLOCKED_UNSAFE_MOUNT_CONFIGURATION"
    preflight["blockers"] = blockers
    write(reports_dir / "gate5e2d8a_change_review.md", markdown_review(compose_files=compose_files, active=active, host_path=intended_host_path, preflight=preflight))
    write(reports_dir / "gate5e2d8a_preflight.json", json.dumps(preflight, indent=2, sort_keys=True) + "\n")
    write(reports_dir / "gate5e2d8a_rollback_plan.md", rollback_plan())
    write(reports_dir / "gate5e2d8a_execution_commands.md", execution_commands())
    print(json.dumps({"status": preflight["status"], "blockers": blockers, "reports_dir": str(reports_dir)}, indent=2))


if __name__ == "__main__":
    main()
