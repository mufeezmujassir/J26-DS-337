"""Create a review-only production cutover package from validated staging evidence.

This command is deliberately incapable of calling Qdrant, Docker, PostgreSQL,
or a network service.  It verifies report files and records a human-review
plan.  It does not perform a cutover.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

EXPECTED_COLLECTION = "sri_lanka_attractions_staging"
EXPECTED_MODEL = "BAAI/bge-large-en-v1.5"
EXPECTED_DIMENSION = 1024


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return value


def validate_evidence(rebuild: dict[str, Any], validation: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if rebuild.get("status") != "STAGING_REBUILD_COMPLETED":
        errors.append("staging_rebuild_not_completed")
    if rebuild.get("failures"):
        errors.append("staging_rebuild_has_failures")
    if validation.get("status") != "STAGING_VALIDATED":
        errors.append("staging_validation_not_passed")
    if rebuild.get("collection") != EXPECTED_COLLECTION or validation.get("collection") != EXPECTED_COLLECTION:
        errors.append("unexpected_staging_collection")
    if rebuild.get("embedding_model") != EXPECTED_MODEL:
        errors.append("unexpected_embedding_model")
    if rebuild.get("vector_dimension") != EXPECTED_DIMENSION:
        errors.append("unexpected_rebuild_dimension")
    checks = validation.get("checks", {})
    required = ("collection", "direct_retrieve", "filtered_scroll_existing", "filtered_scroll_absent", "full_unfiltered_scroll", "vector_dimension", "vector_search")
    if any(checks.get(name, {}).get("status") != "ok" for name in required):
        errors.append("staging_read_validation_incomplete")
    rebuilt = rebuild.get("postgresql_active_attractions")
    validated = validation.get("expected_postgresql_active_attractions")
    points = checks.get("collection", {}).get("points_count")
    scrolled = checks.get("full_unfiltered_scroll", {}).get("unique_point_ids")
    if not all(isinstance(value, int) and value > 0 for value in (rebuilt, validated, points, scrolled)):
        errors.append("invalid_scope_counts")
    elif len({rebuilt, validated, points, scrolled}) != 1:
        errors.append("staging_scope_count_mismatch")
    return errors


def build_plan(*, rebuild_path: Path, validation_path: Path, snapshot_name: str, snapshot_checksum: str) -> dict[str, Any]:
    rebuild = read_json(rebuild_path)
    validation = read_json(validation_path)
    blockers = validate_evidence(rebuild, validation)
    if not snapshot_name.endswith(".snapshot"):
        blockers.append("invalid_staging_snapshot_name")
    if len(snapshot_checksum) != 64 or any(char not in "0123456789abcdefABCDEF" for char in snapshot_checksum):
        blockers.append("invalid_staging_snapshot_checksum")
    count = rebuild.get("postgresql_active_attractions")
    return {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "mode": "review_only_cutover_plan",
        "status": "READY_FOR_HUMAN_CUTOVER_REVIEW" if not blockers else "NOT_READY_FOR_CUTOVER_REVIEW",
        "blockers": sorted(set(blockers)),
        "validated_staging": {
            "collection": EXPECTED_COLLECTION,
            "point_count": count,
            "embedding_model": EXPECTED_MODEL,
            "vector_dimension": EXPECTED_DIMENSION,
            "scope_sha256": rebuild.get("scope_sha256"),
            "rebuild_report": str(rebuild_path).replace("\\", "/"),
            "rebuild_report_sha256": file_sha256(rebuild_path),
            "validation_report": str(validation_path).replace("\\", "/"),
            "validation_report_sha256": file_sha256(validation_path),
            "staging_snapshot": {"name": snapshot_name, "checksum": snapshot_checksum.lower()},
        },
        "production_protection": {
            "broken_production_collection_must_remain_stopped": True,
            "production_qdrant_writes_executed": False,
            "postgresql_writes_executed": False,
            "quarantine_directory_must_be_retained": "qdrant-data-quarantine-2026-10-18",
            "snapshot_file_must_be_retained": "qdrant-snapshots/sri_lanka_attractions-1336472673414113-2026-10-18-07-30-23.snapshot",
        },
        "required_human_authorizations_before_execution": [
            "Approve the immutable report hashes and staging snapshot checksum.",
            "Approve a new production collection configuration pointing to a new named volume, never the quarantined volume.",
            "Approve application configuration change to the reviewed replacement collection name.",
            "Approve post-cutover retrieval smoke tests and a rollback window.",
        ],
        "required_execution_steps_not_performed": [
            "Stop staging only after its snapshot is confirmed available.",
            "Create a new production service or named volume from the reviewed staging state; do not overwrite qdrant_data.",
            "Switch the application collection configuration only after the replacement passes health checks.",
            "Keep the previous production and quarantine volumes until rollback sign-off is complete.",
        ],
        "post_cutover_acceptance_criteria": [
            f"Collection count equals approved scope: {count}.",
            "Full unfiltered scroll completes.",
            "Existing and absent filtered payload scrolls succeed.",
            "Direct retrieval, vector search, payload identity, and 1024-dimensional vectors succeed.",
            "Semantic API smoke test succeeds with the new collection configuration.",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rebuild-report", default="data/reports/qdrant_staging_rebuild_execution.json")
    parser.add_argument("--validation-report", default="data/reports/qdrant_staging_validation.json")
    parser.add_argument("--staging-snapshot-name", required=True)
    parser.add_argument("--staging-snapshot-checksum", required=True)
    parser.add_argument("--output", default="data/reports/qdrant_production_cutover_review_plan.json")
    args = parser.parse_args()
    plan = build_plan(
        rebuild_path=Path(args.rebuild_report),
        validation_path=Path(args.validation_report),
        snapshot_name=args.staging_snapshot_name,
        snapshot_checksum=args.staging_snapshot_checksum,
    )
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(plan, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(plan, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
