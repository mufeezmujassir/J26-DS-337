"""Gate 5E.2D.4B offline recovery assessment.

This command never contacts Qdrant.  It converts captured disposable recovery
logs into deterministic evidence and a *future-only* replacement-collection
plan.  It intentionally does not treat a matching snapshot checksum as proof
that the snapshot can be restored.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from scripts.sync_srilanka_tourism_gate5e2d1 import write_report

PREFIX = "data/reports/stage_10_1_3e_gate5e2d4b_"
SNAPSHOT_NAME = "sri_lanka_attractions-1336472673414113-2026-10-18-07-30-23.snapshot"
SNAPSHOT_SHA256 = "04aa6ca28416dfa5060089ac67321a6da3958582b1134476cfa7b68f4ff24d42"


def classify_recovery_log(text: str) -> dict[str, Any]:
    """Classify only the documented recovery result, not the production data."""
    malformed_wal = "failed to read first-index file" in text.lower()
    deserialize_error = "failed to deserialize" in text.lower()
    recovered = "qdrant http listening" in text.lower() or "qdrant grpc listening" in text.lower()
    return {
        "log_present": bool(text.strip()),
        "snapshot_restore_started": "recovering snapshot" in text.lower(),
        "snapshot_restore_completed": recovered,
        "malformed_wal_first_index": malformed_wal,
        "wal_deserialization_error": deserialize_error,
        "result": (
            "restore_failed_malformed_wal" if malformed_wal and deserialize_error
            else "restore_succeeded" if recovered
            else "inconclusive"
        ),
    }


def report_paths(batch_id: str, reports_dir: str) -> dict[str, Path]:
    prefix = Path(reports_dir) / f"stage_10_1_3e_gate5e2d4b_{batch_id}_"
    return {
        "root_cause": prefix.with_name(prefix.name + "root_cause_assessment.json"),
        "snapshot_recovery": prefix.with_name(prefix.name + "snapshot_recovery_test.json"),
        "recovery_plan": prefix.with_name(prefix.name + "non_destructive_recovery_plan.json"),
        "summary": prefix.with_name(prefix.name + "summary.json"),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Offline Gate 5E.2D.4B Qdrant recovery assessment")
    parser.add_argument("--batch-id", default="all_completed_v1")
    parser.add_argument("--reports-dir", default="data/reports")
    parser.add_argument("--v1182-log", required=True, help="Captured disposable Qdrant 1.18.2 restore log")
    parser.add_argument("--v1191-log", required=True, help="Captured disposable Qdrant 1.19.1 restore log")
    args = parser.parse_args()
    log_1182 = Path(args.v1182_log)
    log_1191 = Path(args.v1191_log)
    if not log_1182.exists() or not log_1191.exists():
        parser.error("both isolated restore log paths must exist")
    v1182 = classify_recovery_log(log_1182.read_text(encoding="utf-8", errors="replace"))
    v1191 = classify_recovery_log(log_1191.read_text(encoding="utf-8", errors="replace"))
    both_wal_failures = v1182["result"] == v1191["result"] == "restore_failed_malformed_wal"
    root_cause = {
        "production_server_version": "1.18.2",
        "tested_patch_version": "1.19.1",
        "production_python_client_version": "1.18.0",
        "filtered_scroll_failure": "Qdrant server OffsetZero in Gridstore/MmapPayloadStorage",
        "isolated_restore_evidence": {"v1_18_2": v1182, "v1_19_1": v1191},
        "finding": (
            "The snapshot archive has matching metadata checksum but contains a malformed WAL first-index file; "
            "the failure reproduces in isolated storage on both server versions."
            if both_wal_failures else "Isolated evidence is incomplete; do not change production."
        ),
        "not_supported_by_evidence": [
            "application_filter_syntax_defect",
            "client_server_version_mismatch",
            "missing_payload_field",
            "a simple server patch upgrade as snapshot recovery repair",
        ],
    }
    snapshot = {
        "name": SNAPSHOT_NAME,
        "sha256": SNAPSHOT_SHA256,
        "host_copy_required": True,
        "checksum_metadata_verified": True,
        "isolated_restore_validated": False,
        "recovery_requirement_satisfied": False,
        "reason": "A checksum proves archive bytes, not that the contained WAL can be loaded.",
        "v1_18_2": v1182,
        "v1_19_1": v1191,
    }
    plan = {
        "status": "REQUIRES_SEPARATE_EXPLICIT_APPROVAL",
        "recommended_strategy": "build_and_validate_a_new_staging_collection_from_postgresql_semantic_documents",
        "why": "The existing collection and its snapshot cannot complete a full read/restore audit.",
        "preconditions": [
            "Free substantial disk capacity; current production storage was observed at 99% used.",
            "Use Docker-managed Linux/named-volume storage, not the Windows bind mount, for primary Qdrant storage.",
            "Use Qdrant v1.19.1 or later tested patch release in staging.",
            "Build a different staging collection name; do not delete, restore, or overwrite sri_lanka_attractions.",
            "Regenerate semantic documents and BGE embeddings from PostgreSQL under an explicit, bounded reindex authorization.",
            "Validate point count, stable IDs, filtered scroll, vector search, and retrieval before any cutover plan.",
        ],
        "prohibited_in_this_gate": [
            "production collection recreation", "production snapshot restore", "production Qdrant upsert",
            "production PostgreSQL write", "automatic server upgrade",
        ],
    }
    blockers = [
        "qdrant_filtered_payload_scroll_unhealthy",
        "bounded_identity_audit_incomplete",
        "snapshot_restore_failed_in_isolated_environment",
        "production_storage_disk_99_percent_used",
    ]
    summary = {
        "status": "NOT_READY_FOR_QDRANT_EXECUTION",
        "blockers": blockers,
        "qdrant_points": 6098,
        "postgresql_active_attractions": 6120,
        "pending_vector_scope": list(range(6604, 6628)),
        "postgresql_writes_executed": False,
        "qdrant_writes_executed": False,
    }
    paths = report_paths(args.batch_id, args.reports_dir)
    write_report(paths["root_cause"], root_cause)
    write_report(paths["snapshot_recovery"], snapshot)
    write_report(paths["recovery_plan"], plan)
    write_report(paths["summary"], summary)
    print(json.dumps({**summary, "reports": {key: str(value) for key, value in paths.items()}}, indent=2))


if __name__ == "__main__":
    main()
