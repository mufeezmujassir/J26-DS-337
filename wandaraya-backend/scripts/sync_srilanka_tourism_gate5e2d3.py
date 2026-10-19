"""Gate 5E.2D.3 final read-only Qdrant authorization package.

This command cannot create a snapshot, generate a Qdrant point, or modify
PostgreSQL.  It validates D.2 evidence and captures the exact prerequisites
for the separate, explicitly-authorized D.2 executor.
"""
from __future__ import annotations

import argparse
import ast
import inspect
import json
import math
from pathlib import Path
from typing import Any

from qdrant_client import QdrantClient

from app.config import settings
from app.knowledge_base.embeddings.embedding_service import AttractionEmbeddingService
from app.knowledge_base.embeddings.qdrant_indexer import AttractionQdrantIndexer
from scripts.sync_srilanka_tourism_gate5e2d1 import EXPECTED_IMPORTED_COUNT, write_report
from scripts.sync_srilanka_tourism_gate5e2d2 import canonical_hash, qdrant_health_diagnostics, snapshot_readiness
import scripts.sync_srilanka_tourism_gate5e2d2 as executor

D2_PREFIX = "data/reports/stage_10_1_3e_gate5e2d2_"


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(str(path))
    return json.loads(path.read_text(encoding="utf-8"))


def d2_paths(batch_id: str) -> dict[str, Path]:
    return {
        "summary": Path(f"{D2_PREFIX}{batch_id}_summary.json"),
        "health": Path(f"{D2_PREFIX}{batch_id}_qdrant_health_diagnostics.json"),
        "scope": Path(f"{D2_PREFIX}{batch_id}_postgresql_scope_validation.json"),
        "documents": Path(f"{D2_PREFIX}{batch_id}_semantic_document_integrity.json"),
        "embeddings": Path(f"{D2_PREFIX}{batch_id}_embedding_generation_validation.json"),
        "identity": Path(f"{D2_PREFIX}{batch_id}_qdrant_identity_validation.json"),
        "snapshot": Path(f"{D2_PREFIX}{batch_id}_snapshot_readiness.json"),
        "plan": Path(f"{D2_PREFIX}{batch_id}_incremental_sync_plan.json"),
    }


def executor_audit() -> dict[str, Any]:
    """Verify actual implementation properties instead of trusting a document."""
    source = inspect.getsource(executor)
    required = {
        "explicit_execute_confirmation": "--confirm-execute" in source,
        "approved_count_required": "--approved-count" in source,
        "scope_hash_required": "--scope-sha256" in source,
        "plan_hash_required": "--plan-sha256" in source,
        "snapshot_name_required": "--snapshot-name" in source,
        "stable_integer_point_ids": "point_id_for_attraction" in source,
        "existing_bge_embedding_service": "AttractionEmbeddingService.encode_document" in source,
        "per_batch_post_upsert_retrieve_verification": "client.retrieve" in inspect.getsource(executor.execute_upserts),
        "partial_failure_reporting": "failed" in inspect.getsource(executor.execute_upserts),
        "postgresql_write_code_absent": "commit(" not in source and "INSERT " not in source,
        "qdrant_upsert_only_in_execute_path": "if args.execute:" in source,
    }
    return {"checks": required, "all_required_executor_checks_pass": all(required.values())}


def vector_search_health(qdrant_url: str) -> dict[str, Any]:
    """Search with an existing stored vector only; no embedding/network mutation."""
    try:
        client = QdrantClient(url=qdrant_url)
        collection = AttractionQdrantIndexer.COLLECTION_NAME
        sample, = client.retrieve(collection_name=collection, ids=[1], with_payload=False, with_vectors=True)
        vector = sample.vector
        if not isinstance(vector, list) or len(vector) != AttractionEmbeddingService.EXPECTED_DIMENSION:
            return {"status": "failed", "reason": "sample_vector_unavailable_or_wrong_dimension"}
        response = client.query_points(collection_name=collection, query=vector, limit=1, with_payload=True)
        return {"status": "ok", "returned_points": len(response.points), "sample_point_id": sample.id}
    except Exception as exc:
        return {"status": "failed", "error_type": type(exc).__name__, "error": str(exc)[:1500]}


def validate_d2(d2: dict[str, dict[str, Any]]) -> tuple[list[int], list[str]]:
    summary, scope, documents, embeddings, identity, plan = (
        d2["summary"], d2["scope"], d2["documents"], d2["embeddings"], d2["identity"], d2["plan"]
    )
    expected_ids = list(range(6604, 6628))
    scope_ids = [row.get("attraction_id") for row in scope.get("records", [])]
    document_rows = documents.get("records", [])
    embedding_rows = embeddings.get("embeddings", [])
    identity_rows = identity.get("records", [])
    failures: list[str] = []
    if summary.get("postgresql_attraction_count") != 6120:
        failures.append("unexpected_postgresql_active_attraction_count")
    if scope_ids != expected_ids:
        failures.append("approved_import_scope_is_not_exactly_6604_to_6627")
    if len(document_rows) != EXPECTED_IMPORTED_COUNT or not all(row.get("document_hash_matches_d1") for row in document_rows):
        failures.append("semantic_document_hash_integrity_failed")
    if len(embedding_rows) != EXPECTED_IMPORTED_COUNT or not all(
        row.get("valid") and row.get("dimension") == 1024 and row.get("model_name") == AttractionEmbeddingService.MODEL_NAME
        for row in embedding_rows
    ):
        failures.append("embedding_validation_failed")
    if summary.get("identity_conflicts") != 0 or any(row.get("classification") == "VECTOR_IDENTITY_CONFLICT" for row in identity_rows):
        failures.append("qdrant_point_identity_conflict")
    canonical_plan = {key: value for key, value in plan.items() if key != "plan_sha256"}
    if canonical_hash(canonical_plan) != plan.get("plan_sha256"):
        failures.append("execution_plan_hash_invalid")
    if plan.get("scope_sha256") != summary.get("scope_sha256"):
        failures.append("scope_hash_mismatch_between_d2_reports")
    if plan.get("point_ids") != expected_ids:
        failures.append("qdrant_point_scope_invalid")
    return expected_ids, failures


def final_report_paths(batch_id: str, reports_dir: str) -> dict[str, Path]:
    prefix = Path(reports_dir) / f"stage_10_1_3e_gate5e2d3_{batch_id}_"
    return {name: prefix.with_name(prefix.name + filename) for name, filename in {
        "final_health": "final_health_report.json",
        "scope_integrity": "scope_integrity_report.json",
        "embedding_validation": "embedding_validation_report.json",
        "snapshot_readiness": "snapshot_readiness_report.json",
        "authorization_package": "final_synchronization_authorization_package.json",
        "post_sync_verification_plan": "post_sync_verification_plan.json",
        "summary": "final_readiness_summary.json",
    }.items()}


def main() -> None:
    parser = argparse.ArgumentParser(description="Read-only final Gate 5E.2D.3 authorization package")
    parser.add_argument("--batch-id", default="all_completed_v1")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--reports-dir", default="data/reports")
    parser.add_argument("--qdrant-url", default=settings.QDRANT_URL)
    args = parser.parse_args()

    try:
        d2 = {name: read_json(path) for name, path in d2_paths(args.batch_id).items()}
    except FileNotFoundError as exc:
        parser.error(f"required Gate 5E.2D.2 report is missing: {exc}")
    ids, integrity_failures = validate_d2(d2)
    fresh_health = qdrant_health_diagnostics(args.qdrant_url)
    fresh_health["vector_search"] = vector_search_health(args.qdrant_url)
    fresh_snapshot = snapshot_readiness(args.qdrant_url)
    audit = executor_audit()
    blockers = list(integrity_failures)
    if not audit["all_required_executor_checks_pass"]:
        blockers.append("executor_safety_audit_failed")
    if fresh_health.get("direct_retrieve", {}).get("status") != "ok":
        blockers.append("qdrant_direct_retrieve_failed")
    if fresh_health.get("unfiltered_scroll", {}).get("status") != "ok":
        blockers.append("qdrant_unfiltered_scroll_failed")
    if fresh_health.get("filtered_scroll", {}).get("status") != "ok":
        blockers.append("qdrant_filtered_payload_scroll_unhealthy")
    if fresh_health["vector_search"].get("status") != "ok":
        blockers.append("qdrant_vector_search_failed")
    if not fresh_snapshot.get("ready_for_write"):
        blockers.append("verified_prewrite_snapshot_missing")

    plan = d2["plan"]
    auth = {
        "status": "READY_FOR_SEPARATE_EXPLICIT_QDRANT_EXECUTION" if not blockers else "NOT_READY_FOR_QDRANT_EXECUTION",
        "collection": plan["collection"],
        "attraction_ids": ids,
        "point_ids": plan["point_ids"],
        "embedding_model": plan["embedding_model"],
        "vector_dimension": plan["vector_dimension"],
        "scope_sha256": plan["scope_sha256"],
        "execution_plan_sha256": plan["plan_sha256"],
        "operation": plan["operation"],
        "blocked_reasons": blockers,
        "future_execution_command": (
            "docker exec -it wandaraya-api python -m scripts.sync_srilanka_tourism_gate5e2d2 "
            f"--batch-id {args.batch_id} --execute --confirm-execute --approved-count 24 "
            f"--scope-sha256 {plan['scope_sha256']} --plan-sha256 {plan['plan_sha256']} "
            "--snapshot-name <VERIFIED_PREWRITE_SNAPSHOT_NAME>"
        ),
        "postgresql_writes_executed": False,
        "qdrant_writes_executed": False,
    }
    post_sync_plan = {
        "command": f"docker exec -it wandaraya-api python -m scripts.verify_srilanka_tourism_gate5e2d3 --batch-id {args.batch_id}",
        "checks": ["24 stable point IDs exist", "payload attraction IDs and document hashes match", "vectors have 1024 finite dimensions", "embedding model matches", "point count is reported", "semantic exact-name retrieval is attempted", "PostgreSQL scope is read-only"],
        "writes_executed": False,
    }
    paths = final_report_paths(args.batch_id, args.reports_dir)
    write_report(paths["final_health"], fresh_health)
    write_report(paths["scope_integrity"], {"d2_scope_validation": d2["scope"], "integrity_failures": integrity_failures})
    write_report(paths["embedding_validation"], d2["embeddings"])
    write_report(paths["snapshot_readiness"], fresh_snapshot)
    write_report(paths["authorization_package"], {"executor_audit": audit, **auth})
    write_report(paths["post_sync_verification_plan"], post_sync_plan)
    summary = {**auth, "qdrant_point_count": fresh_health.get("point_count"), "qdrant_health_status": fresh_health.get("health_status"), "recovery_ready": fresh_snapshot.get("ready_for_write"), "ready_to_sync_count": len(ids) if not blockers else 0}
    write_report(paths["summary"], summary)
    print(json.dumps({**summary, "reports": {key: str(value) for key, value in paths.items()}}, indent=2))


if __name__ == "__main__":
    main()
