"""Validate immutable staging evidence before a separately authorized cutover.

This is read-only.  It cannot control Docker, PostgreSQL, or Qdrant.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_plan(plan: dict[str, Any], rebuild_hash: str, validation_hash: str) -> list[str]:
    failures: list[str] = []
    if plan.get("status") != "READY_FOR_HUMAN_CUTOVER_REVIEW":
        failures.append("cutover_plan_not_review_ready")
    if plan.get("blockers"):
        failures.append("cutover_plan_contains_blockers")
    staging = plan.get("validated_staging", {})
    if staging.get("collection") != "sri_lanka_attractions_staging":
        failures.append("unexpected_replacement_collection")
    if staging.get("point_count") != 6120:
        failures.append("unexpected_validated_scope_count")
    if staging.get("embedding_model") != "BAAI/bge-large-en-v1.5" or staging.get("vector_dimension") != 1024:
        failures.append("unexpected_embedding_contract")
    if staging.get("rebuild_report_sha256") != rebuild_hash:
        failures.append("rebuild_report_hash_mismatch")
    if staging.get("validation_report_sha256") != validation_hash:
        failures.append("validation_report_hash_mismatch")
    snapshot = staging.get("staging_snapshot", {})
    checksum = snapshot.get("checksum", "")
    if not snapshot.get("name", "").endswith(".snapshot") or len(checksum) != 64:
        failures.append("staging_snapshot_metadata_invalid")
    return failures


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cutover-plan", default="data/reports/qdrant_production_cutover_review_plan.json")
    parser.add_argument("--rebuild-report", default="data/reports/qdrant_staging_rebuild_execution.json")
    parser.add_argument("--validation-report", default="data/reports/qdrant_staging_validation.json")
    parser.add_argument("--output", default="data/reports/qdrant_production_cutover_preflight.json")
    args = parser.parse_args()
    plan_path, rebuild_path, validation_path = map(Path, (args.cutover_plan, args.rebuild_report, args.validation_report))
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    failures = validate_plan(plan, sha256(rebuild_path), sha256(validation_path))
    result = {
        "mode": "read_only_preflight",
        "status": "READY_FOR_SEPARATE_EXPLICIT_CUTOVER_EXECUTION" if not failures else "NOT_READY_FOR_CUTOVER_EXECUTION",
        "failures": failures,
        "cutover_plan_sha256": sha256(plan_path),
        "validated_scope_sha256": plan.get("validated_staging", {}).get("scope_sha256"),
        "postgresql_writes_executed": False,
        "qdrant_writes_executed": False,
        "next_action": "Requires a separate human authorization before any Docker service switch.",
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
