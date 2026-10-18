"""Gate 5E.2D.2 controlled BGE/Qdrant incremental synchronization.

Dry-run is the default and is deliberately read-only.  The optional executor
is retained for a separately authorized stage; this module never invokes it
unless every explicit authorization switch and integrity hash is supplied.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import importlib.metadata
import json
import math
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from qdrant_client import QdrantClient
from qdrant_client.models import PointStruct
from sqlalchemy import func, select

from app.config import settings
from app.database import AsyncSessionLocal
from app.knowledge_base.embeddings.embedding_service import AttractionEmbeddingService
from app.knowledge_base.embeddings.qdrant_indexer import AttractionQdrantIndexer
from app.models.attraction import Attraction
from app.models.attraction_categories import AttractionCategory
from scripts.sync_srilanka_tourism_gate5e2d1 import (
    DOCUMENT_SCHEMA_VERSION,
    EXPECTED_IMPORTED_COUNT,
    audit_qdrant,
    document_hash,
    load_imported_records,
    point_id_for_attraction,
    write_report,
)

BASE = "data/reports/stage_10_1_3e_gate5e2d1_"


def canonical_hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


def vector_validation(vector: list[float], expected_dimension: int = 1024) -> dict[str, Any]:
    values = [float(value) for value in vector]
    norm = math.sqrt(sum(value * value for value in values))
    reasons: list[str] = []
    if len(values) != expected_dimension:
        reasons.append("unexpected_dimension")
    if not all(math.isfinite(value) for value in values):
        reasons.append("non_finite_vector_value")
    if not math.isfinite(norm) or norm <= 0:
        reasons.append("zero_or_invalid_vector_norm")
    # SentenceTransformer receives normalize_embeddings=True.  Allow tiny
    # floating point error but reject a non-normalized accidental embedding.
    if norm > 0 and abs(norm - 1.0) > 1e-3:
        reasons.append("embedding_not_normalized")
    return {"valid": not reasons, "dimension": len(values), "norm": norm, "reasons": reasons}


def deterministic_payload(record: dict[str, Any], category_ids: list[int]) -> dict[str, Any]:
    """Preserve legacy payload keys and add only backward-compatible metadata."""
    return {
        "attraction_id": record["attraction_id"],
        "name": record["name"],
        "city": record["city"],
        "district": record["district"],
        "province": record["province"],
        "categories": record["category_names"],
        "activities": record["activities"],
        "district_id": record["district_id"],
        "category_ids": sorted(category_ids),
        "latitude": record["latitude"],
        "longitude": record["longitude"],
        "google_place_id": record["google_place_id"],
        "is_active": True,
        "semantic_document_sha256": record["semantic_document_sha256"],
        "embedding_model": AttractionEmbeddingService.MODEL_NAME,
        "document_schema_version": DOCUMENT_SCHEMA_VERSION,
        "source_provider": "srilanka_tourism",
        "source_attraction_id": record["source_attraction_id"],
    }


def _http_get(url: str) -> tuple[int | None, str | None, str | None]:
    try:
        with urllib.request.urlopen(url, timeout=10) as response:
            return response.status, response.read(20_000).decode("utf-8", "replace"), None
    except (urllib.error.URLError, TimeoutError, ValueError) as exc:
        return None, None, f"{type(exc).__name__}: {exc}"


def qdrant_health_diagnostics(qdrant_url: str) -> dict[str, Any]:
    """Perform only GET/read requests and preserve the exact filter failure."""
    base = qdrant_url.rstrip("/")
    root_code, root_body, root_error = _http_get(base + "/")
    result: dict[str, Any] = {
        "qdrant_url": qdrant_url,
        "client_version": importlib.metadata.version("qdrant-client"),
        "server_root_http_status": root_code,
        "server_root_error": root_error,
        "server_metadata": None,
        "unfiltered_scroll": {"status": "not_run"},
        "filtered_scroll": {"status": "not_run"},
        "direct_retrieve": {"status": "not_run"},
        "disk_space": "unavailable_from_fastapi_container: qdrant storage is not mounted here",
    }
    if root_body:
        try:
            result["server_metadata"] = json.loads(root_body)
        except json.JSONDecodeError:
            result["server_metadata"] = {"raw_response": root_body[:500]}
    try:
        client = QdrantClient(url=qdrant_url)
        collection = AttractionQdrantIndexer.COLLECTION_NAME
        info = client.get_collection(collection)
        result["collection_status"] = getattr(info.status, "value", str(info.status))
        result["point_count"] = int(client.count(collection, exact=True).count)
        result["indexed_vectors_count"] = getattr(info, "indexed_vectors_count", None)
        points, _ = client.scroll(collection_name=collection, limit=1, with_payload=True, with_vectors=False)
        result["unfiltered_scroll"] = {"status": "ok", "sample_points": len(points)}
        direct = client.retrieve(collection_name=collection, ids=[6604], with_payload=True, with_vectors=False)
        result["direct_retrieve"] = {"status": "ok", "returned_points": len(direct)}
        # This deliberately probes the known problem using a payload filter.
        # D.1 avoided relying on it; D.2 records its exact server response.
        from qdrant_client.models import FieldCondition, Filter, MatchValue
        try:
            client.scroll(collection_name=collection, scroll_filter=Filter(must=[FieldCondition(
                key="attraction_id", match=MatchValue(value=6604)
            )]), limit=1, with_payload=True, with_vectors=False)
            result["filtered_scroll"] = {"status": "ok"}
        except Exception as exc:  # Qdrant error body is relevant operational evidence.
            result["filtered_scroll"] = {
                "status": "failed",
                "error_type": type(exc).__name__,
                "error": str(exc)[:2000],
            }
    except Exception as exc:
        result["client_connection_error"] = f"{type(exc).__name__}: {exc}"
    compatible_minor_gap = None
    server_version = (result.get("server_metadata") or {}).get("version")
    if server_version:
        try:
            client_minor = int(result["client_version"].split(".")[1])
            server_minor = int(str(server_version).split(".")[1])
            compatible_minor_gap = abs(client_minor - server_minor) <= 1
        except (IndexError, ValueError):
            pass
    result["client_server_minor_versions_compatible"] = compatible_minor_gap
    result["health_status"] = (
        "degraded" if result["filtered_scroll"].get("status") != "ok"
        else "healthy"
    )
    return result


def snapshot_readiness(qdrant_url: str) -> dict[str, Any]:
    """Inspect snapshots without creating one; a later execution must name one."""
    url = f"{qdrant_url.rstrip('/')}/collections/{AttractionQdrantIndexer.COLLECTION_NAME}/snapshots"
    code, body, error = _http_get(url)
    snapshots: list[Any] = []
    if body:
        try:
            payload = json.loads(body)
            snapshots = payload.get("result", []) if isinstance(payload, dict) else []
        except json.JSONDecodeError:
            error = "invalid_snapshot_list_response"
    return {
        "inspection_http_status": code,
        "inspection_error": error,
        "existing_snapshots": snapshots,
        "snapshot_creation_performed": False,
        "ready_for_write": bool(snapshots),
        "requirement": "A separately authorized pre-write collection snapshot must be present and named before live upsert.",
    }


async def category_ids_by_attraction(attraction_ids: list[int]) -> dict[int, list[int]]:
    async with AsyncSessionLocal() as db:
        rows = (await db.execute(select(AttractionCategory.attraction_id, AttractionCategory.category_id).where(
            AttractionCategory.attraction_id.in_(attraction_ids)
        ))).all()
    values: dict[int, list[int]] = {attraction_id: [] for attraction_id in attraction_ids}
    for attraction_id, category_id in rows:
        values[attraction_id].append(category_id)
    return values


async def active_attraction_count() -> int:
    async with AsyncSessionLocal() as db:
        return int((await db.scalar(select(func.count()).select_from(Attraction).where(
            Attraction.is_active.is_(True)
        ))) or 0)


def read_d1_hashes(batch_id: str) -> dict[int, str]:
    path = Path(f"{BASE}{batch_id}_semantic_documents.json")
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return {int(row["attraction_id"]): row["semantic_document_sha256"] for row in payload.get("records", [])}


def generate_embeddings(records: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Local BGE work only.  This does not contact Qdrant or providers."""
    successes, failures = [], []
    for record in records:
        try:
            embedding = AttractionEmbeddingService.encode_document(record["semantic_text"])
            validation = vector_validation(embedding.vector, AttractionEmbeddingService.EXPECTED_DIMENSION)
            row = {"attraction_id": record["attraction_id"], "model_name": embedding.model_name, **validation}
            if validation["valid"]:
                # Never put vectors in reports; they are large and can be
                # deterministically regenerated from the documented text hash.
                row["vector_sha256"] = hashlib.sha256(
                    json.dumps(embedding.vector, separators=(",", ":")).encode()
                ).hexdigest()
                successes.append({**row, "vector": embedding.vector})
            else:
                failures.append(row)
        except Exception as exc:
            failures.append({"attraction_id": record["attraction_id"], "valid": False,
                             "reasons": [f"embedding_generation_failed:{type(exc).__name__}"]})
    return successes, failures


def _canonical_scope(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{key: row[key] for key in (
        "attraction_id", "source_attraction_id", "semantic_document_sha256", "qdrant_point_id", "payload"
    )} for row in sorted(records, key=lambda value: value["attraction_id"])]


def future_authorization_errors(args: argparse.Namespace, scope_hash: str, plan_hash: str,
                                snapshot: dict[str, Any], ready_count: int) -> list[str]:
    errors = []
    if not args.confirm_execute:
        errors.append("missing_confirm_execute")
    if args.approved_count != ready_count:
        errors.append("approved_count_mismatch")
    if args.scope_sha256 != scope_hash:
        errors.append("scope_hash_mismatch")
    if args.plan_sha256 != plan_hash:
        errors.append("plan_hash_mismatch")
    if not args.snapshot_name:
        errors.append("missing_snapshot_name")
    elif args.snapshot_name not in {item.get("name") for item in snapshot.get("existing_snapshots", [])}:
        errors.append("verified_snapshot_not_found")
    return errors


def execute_upserts(*, records: list[dict[str, Any]], embeddings: dict[int, list[float]], qdrant_url: str,
                    batch_size: int = 8) -> dict[str, Any]:
    """Future-only resumable batches; callers must have passed all gates."""
    client = QdrantClient(url=qdrant_url)
    collection = AttractionQdrantIndexer.COLLECTION_NAME
    completed, failed = [], []
    for start in range(0, len(records), batch_size):
        batch = records[start:start + batch_size]
        try:
            client.upsert(collection_name=collection, points=[PointStruct(
                id=row["qdrant_point_id"], vector=embeddings[row["attraction_id"]], payload=row["payload"]
            ) for row in batch], wait=True)
            verified = client.retrieve(collection_name=collection, ids=[row["qdrant_point_id"] for row in batch],
                                       with_payload=True, with_vectors=False)
            by_id = {point.id: point for point in verified}
            for row in batch:
                point = by_id.get(row["qdrant_point_id"])
                if not point or (point.payload or {}).get("attraction_id") != row["attraction_id"]:
                    failed.append({"attraction_id": row["attraction_id"], "reason": "post_upsert_identity_verification_failed"})
                else:
                    completed.append(row["attraction_id"])
        except Exception as exc:
            failed.extend({"attraction_id": row["attraction_id"], "reason": f"batch_upsert_failed:{type(exc).__name__}"} for row in batch)
    return {"completed_attraction_ids": completed, "failed": failed, "globally_atomic": False,
            "retry_guidance": "Re-run only failed stable point IDs after inspecting the execution audit."}


def report_paths(batch_id: str, reports_dir: str) -> dict[str, Path]:
    prefix = Path(reports_dir) / f"stage_10_1_3e_gate5e2d2_{batch_id}_"
    return {name: prefix.with_name(prefix.name + filename) for name, filename in {
        "qdrant_health_diagnostics": "qdrant_health_diagnostics.json",
        "postgresql_scope_validation": "postgresql_scope_validation.json",
        "semantic_document_integrity": "semantic_document_integrity.json",
        "embedding_generation_validation": "embedding_generation_validation.json",
        "qdrant_identity_validation": "qdrant_identity_validation.json",
        "snapshot_readiness": "snapshot_readiness.json",
        "incremental_sync_plan": "incremental_sync_plan.json",
        "execution_authorization_requirements": "execution_authorization_requirements.json",
        "dry_run_summary": "dry_run_summary.json",
        "summary": "summary.json",
    }.items()}


async def prepare(batch_id: str, qdrant_url: str, generate: bool = True) -> dict[str, Any]:
    batch, records = await load_imported_records(batch_id)
    d1_hashes = read_d1_hashes(batch_id)
    category_ids = await category_ids_by_attraction([row["attraction_id"] for row in records])
    active_count = await active_attraction_count()
    for row in records:
        row["qdrant_point_id"] = point_id_for_attraction(row["attraction_id"])
        row["payload"] = deterministic_payload(row, category_ids[row["attraction_id"]])
        row["d1_document_hash"] = d1_hashes.get(row["attraction_id"])
        row["document_hash_matches_d1"] = row["d1_document_hash"] == row["semantic_document_sha256"]
    health = qdrant_health_diagnostics(qdrant_url)
    snapshot = snapshot_readiness(qdrant_url)
    _, identity_rows = audit_qdrant(records, qdrant_url)
    identity_by_id = {row["attraction_id"]: row for row in identity_rows}
    for row in records:
        row["vector_status"] = identity_by_id.get(row["attraction_id"], {}).get("classification", "NOT_AUDITED")
    valid_records = [row for row in records if not row["validation_failures"] and row["document_hash_matches_d1"]]
    missing_or_stale = [row for row in valid_records if row["vector_status"] in {"MISSING_VECTOR", "EXISTING_VECTOR_STALE"}]
    embeddings, embedding_failures = generate_embeddings(missing_or_stale) if generate else ([], [])
    embedding_by_id = {row["attraction_id"]: row for row in embeddings}
    ready = [row for row in missing_or_stale if row["attraction_id"] in embedding_by_id]
    scope_hash = canonical_hash(_canonical_scope(ready))
    plan = {
        "operation": "incremental_qdrant_upsert",
        "collection": AttractionQdrantIndexer.COLLECTION_NAME,
        "embedding_model": AttractionEmbeddingService.MODEL_NAME,
        "vector_dimension": AttractionEmbeddingService.EXPECTED_DIMENSION,
        "point_ids": [row["qdrant_point_id"] for row in ready],
        "scope_sha256": scope_hash,
        "batch_size": 8,
        "global_transaction": False,
        "post_upsert_verification_required": True,
    }
    plan_hash = canonical_hash(plan)
    plan["plan_sha256"] = plan_hash
    issues: list[str] = []
    if batch.get("status") != "completed" or len(records) != EXPECTED_IMPORTED_COUNT:
        issues.append("committed_import_scope_invalid")
    if any(not row["document_hash_matches_d1"] for row in records):
        issues.append("semantic_document_hash_changed_since_d1")
    if any(row["validation_failures"] for row in records):
        issues.append("invalid_postgresql_scope_record")
    if embedding_failures:
        issues.append("embedding_generation_or_validation_failed")
    if any(row["vector_status"] == "VECTOR_IDENTITY_CONFLICT" for row in records):
        issues.append("qdrant_identity_conflict")
    if health.get("unfiltered_scroll", {}).get("status") != "ok" or health.get("direct_retrieve", {}).get("status") != "ok":
        issues.append("qdrant_core_read_health_failed")
    # Filter failure does not prevent a scoped direct-ID upsert, but it is a
    # material unresolved collection-wide duplicate-audit limitation.
    if health.get("filtered_scroll", {}).get("status") != "ok":
        issues.append("filtered_payload_scroll_unhealthy")
    if not snapshot.get("ready_for_write"):
        issues.append("prewrite_snapshot_required")
    return {
        "batch": batch, "records": records, "health": health, "snapshot": snapshot,
        "identity_rows": identity_rows, "embeddings": embeddings, "embedding_failures": embedding_failures,
        "ready": ready, "scope_hash": scope_hash, "plan": plan, "plan_hash": plan_hash,
        "issues": issues, "active_attraction_count": active_count,
    }


def emit(result: dict[str, Any], batch_id: str, reports_dir: str) -> dict[str, str]:
    paths = report_paths(batch_id, reports_dir)
    records = result["records"]
    write_report(paths["qdrant_health_diagnostics"], result["health"])
    write_report(paths["postgresql_scope_validation"], {"batch": result["batch"], "records": [
        {key: row[key] for key in ("attraction_id", "source_attraction_id", "active", "district_id", "category_names",
                                   "source_reference_count", "field_provenance_count", "committed_review_present", "validation_failures")}
        for row in records]})
    write_report(paths["semantic_document_integrity"], {"records": [
        {key: row[key] for key in ("attraction_id", "semantic_document_sha256", "d1_document_hash", "document_hash_matches_d1")}
        for row in records]})
    write_report(paths["embedding_generation_validation"], {"embeddings": [
        {key: value for key, value in row.items() if key != "vector"} for row in result["embeddings"]
    ], "failures": result["embedding_failures"], "embeddings_persisted": False})
    write_report(paths["qdrant_identity_validation"], {"records": result["identity_rows"]})
    write_report(paths["snapshot_readiness"], result["snapshot"])
    write_report(paths["incremental_sync_plan"], result["plan"])
    requirements = {
        "required_flags": ["--execute", "--confirm-execute", "--batch-id all_completed_v1", "--approved-count 24", "--scope-sha256", "--plan-sha256", "--snapshot-name"],
        "scope_sha256": result["scope_hash"], "plan_sha256": result["plan_hash"],
        "required_snapshot": "A verified pre-write Qdrant snapshot, created only under separate authorization.",
        "writes_executed": False,
    }
    write_report(paths["execution_authorization_requirements"], requirements)
    summary = {
        "mode": "dry_run", "postgresql_attraction_count": result["active_attraction_count"],
        "qdrant_point_count": result["health"].get("point_count"),
        "ready_attraction_ids": [row["attraction_id"] for row in result["ready"]],
        "embedding_model": AttractionEmbeddingService.MODEL_NAME,
        "vector_dimension": AttractionEmbeddingService.EXPECTED_DIMENSION,
        "documents_validated": len([row for row in records if row["document_hash_matches_d1"]]),
        "embeddings_generated": len(result["embeddings"]),
        "missing_vectors": sum(row["vector_status"] == "MISSING_VECTOR" for row in records),
        "existing_vectors": sum(row["vector_status"] == "EXISTING_VECTOR_CURRENT" for row in records),
        "identity_conflicts": sum(row["vector_status"] == "VECTOR_IDENTITY_CONFLICT" for row in records),
        "qdrant_health_status": result["health"].get("health_status"),
        "filtered_scroll_status": result["health"].get("filtered_scroll", {}).get("status"),
        "snapshot_ready": result["snapshot"].get("ready_for_write"),
        "scope_sha256": result["scope_hash"], "execution_plan_sha256": result["plan_hash"],
        "postgresql_writes_executed": False, "qdrant_writes_executed": False, "external_api_requests": 0,
        "final_authorization_readiness": "READY" if not result["issues"] else "NOT_READY",
        "blockers": result["issues"],
    }
    write_report(paths["dry_run_summary"], summary)
    write_report(paths["summary"], summary)
    return {key: str(value) for key, value in paths.items()}


def main() -> None:
    parser = argparse.ArgumentParser(description="Controlled Gate 5E.2D.2 Qdrant synchronization")
    parser.add_argument("--batch-id", default="all_completed_v1")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--confirm-execute", action="store_true")
    parser.add_argument("--approved-count", type=int)
    parser.add_argument("--scope-sha256")
    parser.add_argument("--plan-sha256")
    parser.add_argument("--snapshot-name")
    parser.add_argument("--reports-dir", default="data/reports")
    parser.add_argument("--qdrant-url", default=settings.QDRANT_URL)
    args = parser.parse_args()
    result = asyncio.run(prepare(args.batch_id, args.qdrant_url, generate=True))
    paths = emit(result, args.batch_id, args.reports_dir)
    if args.execute:
        # Do not weaken health/snapshot gates even when hashes are correct.
        authorization_errors = future_authorization_errors(args, result["scope_hash"], result["plan_hash"], result["snapshot"], len(result["ready"]))
        if result["issues"] or authorization_errors:
            parser.error("execution blocked: " + ", ".join(result["issues"] + authorization_errors))
        execution = execute_upserts(records=result["ready"], embeddings={
            row["attraction_id"]: row["vector"] for row in result["embeddings"]
        }, qdrant_url=args.qdrant_url)
        print(json.dumps({"mode": "executed", **execution, "postgresql_writes_executed": False,
                          "qdrant_writes_executed": bool(execution["completed_attraction_ids"]), "reports": paths}, indent=2))
        return
    print(json.dumps({**json.loads(Path(paths["summary"]).read_text(encoding="utf-8")), "reports": paths}, indent=2))


if __name__ == "__main__":
    main()
