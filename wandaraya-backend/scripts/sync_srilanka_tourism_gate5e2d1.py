"""Gate 5E.2D.1 read-only PostgreSQL-to-Qdrant synchronization preflight.

This command deliberately prepares no embeddings and never calls ``upsert``.
It validates the committed Sri Lanka Tourism import against the production
semantic-document builder and audits only the corresponding Qdrant points.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import math
from collections import Counter
from pathlib import Path
from typing import Any

from qdrant_client import QdrantClient
from sqlalchemy import func, select

from app.config import settings
from app.database import AsyncSessionLocal
from app.knowledge_base.embeddings.document_builder import AttractionDocumentBuilder
from app.knowledge_base.embeddings.embedding_service import AttractionEmbeddingService
from app.knowledge_base.embeddings.qdrant_indexer import AttractionQdrantIndexer
from app.models.attraction import Attraction
from app.models.tourism_sync import (
    AttractionFieldProvenance,
    AttractionSourceReference,
    TourismImportBatch,
    TourismSyncReview,
)

DOCUMENT_SCHEMA_VERSION = "attraction_semantic_document.v1"
SOURCE_PROVIDER = "srilanka_tourism"
EXPECTED_IMPORTED_COUNT = 24


def document_hash(text: str) -> str:
    """Return the stable SHA-256 used to detect a changed semantic document."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def point_id_for_attraction(attraction_id: int) -> int:
    """The established indexer convention: Qdrant point ID == attraction ID."""
    return int(attraction_id)


def validate_document(*, name: str | None, text: str, district: str | None,
                      categories: list[str], latitude: float | None,
                      longitude: float | None, source_reference_count: int,
                      provenance_count: int) -> tuple[list[str], list[str]]:
    """Return validation failures and absent optional semantic fields."""
    failures: list[str] = []
    missing_optional: list[str] = []
    if not name or not name.strip():
        failures.append("missing_name")
    if not text or not text.strip():
        failures.append("empty_semantic_document")
    if not district:
        failures.append("missing_district_relationship")
    if not categories:
        failures.append("missing_category_relationship")
    if source_reference_count != 1:
        failures.append("missing_or_duplicate_official_source_reference")
    if provenance_count < 1:
        failures.append("missing_field_provenance")
    if latitude is None or longitude is None:
        failures.append("missing_coordinates")
    elif (not math.isfinite(latitude) or not math.isfinite(longitude)
          or not -90 <= latitude <= 90 or not -180 <= longitude <= 180):
        failures.append("invalid_coordinates")
    if "Description:" not in text:
        missing_optional.append("verified_description")
    if "Activities:" not in text:
        missing_optional.append("activities")
    if not failures and len(text.strip()) < 20:
        failures.append("insufficient_semantic_content")
    return failures, missing_optional


def vector_config_audit(collection_info: Any) -> dict[str, Any]:
    """Normalize Qdrant's unnamed/named vector configuration without mutation."""
    vectors = collection_info.config.params.vectors
    if hasattr(vectors, "size"):
        size = int(vectors.size)
        distance = getattr(vectors.distance, "value", str(vectors.distance)).lower()
        named = False
    else:
        # A named-vector collection is deliberately incompatible with the
        # existing single-vector indexer until an explicit migration is made.
        size, distance, named = None, None, True
    return {
        "vector_dimension": size,
        "distance_metric": distance,
        "named_vectors": named,
        "compatible": (
            not named
            and size == AttractionEmbeddingService.EXPECTED_DIMENSION
            and distance == "cosine"
        ),
    }


def classify_point(*, attraction_id: int, expected_hash: str, points: list[Any]) -> dict[str, Any]:
    """Classify existing points matched through their payload attraction ID."""
    if not points:
        return {"classification": "MISSING_VECTOR", "point_ids": []}
    ids = [str(point.id) for point in points]
    matching_id_points = [point for point in points if str(point.id) == str(attraction_id)]
    if len(points) != 1 or not matching_id_points:
        return {"classification": "VECTOR_IDENTITY_CONFLICT", "point_ids": ids}
    payload = matching_id_points[0].payload or {}
    if payload.get("attraction_id") != attraction_id:
        return {"classification": "VECTOR_IDENTITY_CONFLICT", "point_ids": ids}
    existing_hash = payload.get("semantic_document_sha256")
    # Legacy vectors have no document hash. They are safely treated as stale
    # instead of being declared current without evidence.
    if existing_hash != expected_hash:
        return {
            "classification": "EXISTING_VECTOR_STALE",
            "point_ids": ids,
            "existing_document_sha256": existing_hash,
        }
    return {"classification": "EXISTING_VECTOR_CURRENT", "point_ids": ids}


def _json(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    return value


def write_report(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(_json(value), indent=2, sort_keys=True, default=str), encoding="utf-8")


async def load_imported_records(batch_id: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Read committed import membership and build documents through production code."""
    async with AsyncSessionLocal() as db:
        batch = await db.get(TourismImportBatch, batch_id)
        batch_report = {
            "batch_id": batch_id,
            "exists": batch is not None,
            "status": getattr(batch, "status", None),
            "applied_action_count": getattr(batch, "applied_action_count", None),
        }
        if batch is None:
            return batch_report, []

        rows = (await db.execute(
            select(Attraction, AttractionSourceReference)
            .join(AttractionSourceReference, AttractionSourceReference.attraction_id == Attraction.id)
            .where(
                AttractionSourceReference.source_provider == SOURCE_PROVIDER,
                AttractionSourceReference.import_batch_id == batch_id,
            )
            .order_by(Attraction.id)
        )).all()

        records: list[dict[str, Any]] = []
        for attraction, source_ref in rows:
            document = await AttractionDocumentBuilder.build(db, attraction.id)
            provenance_count = int((await db.scalar(
                select(func.count()).select_from(AttractionFieldProvenance).where(
                    AttractionFieldProvenance.attraction_id == attraction.id,
                    AttractionFieldProvenance.import_batch_id == batch_id,
                )
            )) or 0)
            source_count = int((await db.scalar(
                select(func.count()).select_from(AttractionSourceReference).where(
                    AttractionSourceReference.attraction_id == attraction.id,
                    AttractionSourceReference.source_provider == SOURCE_PROVIDER,
                )
            )) or 0)
            review = await db.scalar(select(TourismSyncReview.id).where(
                TourismSyncReview.import_batch_id == batch_id,
                TourismSyncReview.source_attraction_id == source_ref.external_source_id,
                TourismSyncReview.approval_status == "committed",
            ))
            failures, missing_optional = validate_document(
                name=attraction.name, text=document.text, district=document.district,
                categories=document.categories, latitude=attraction.latitude,
                longitude=attraction.longitude, source_reference_count=source_count,
                provenance_count=provenance_count,
            )
            records.append({
                "attraction_id": attraction.id,
                "source_attraction_id": source_ref.external_source_id,
                "source_url": source_ref.canonical_source_url,
                "name": attraction.name,
                "active": attraction.is_active,
                "district_id": attraction.district_id,
                "district": document.district,
                "city": attraction.city,
                "province": document.province,
                "category_names": document.categories,
                "activities": document.activities,
                "latitude": attraction.latitude,
                "longitude": attraction.longitude,
                "google_place_id": attraction.google_place_id,
                "semantic_text": document.text,
                "semantic_document_sha256": document_hash(document.text),
                "document_schema_version": DOCUMENT_SCHEMA_VERSION,
                "source_reference_count": source_count,
                "field_provenance_count": provenance_count,
                "committed_review_present": review is not None,
                "validation_failures": failures + ([] if attraction.is_active else ["inactive_attraction"])
                + ([] if review is not None else ["missing_committed_import_review"]),
                "missing_optional_fields": missing_optional,
            })
        return batch_report, records


def audit_qdrant(records: list[dict[str, Any]], qdrant_url: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    collection = AttractionQdrantIndexer.COLLECTION_NAME
    audit: dict[str, Any] = {
        "qdrant_url": qdrant_url,
        "collection_name": collection,
        "collection_exists": False,
        "status": "unavailable",
        "point_identity_audit_complete": False,
    }
    try:
        client = QdrantClient(url=qdrant_url)
        if not client.collection_exists(collection):
            audit.update({"status": "missing_collection", "point_count": 0})
            return audit, []
        info = client.get_collection(collection)
        config = vector_config_audit(info)
        audit.update({
            "collection_exists": True,
            "status": getattr(info.status, "value", str(info.status)),
            "point_count": int(client.count(collection, exact=True).count),
            "indexed_vectors_count": getattr(info, "indexed_vectors_count", None),
            "payload_schema": _json(getattr(info, "payload_schema", {})),
            "vector_configuration": config,
            "point_id_convention": "integer PostgreSQL attraction.id",
        })
        # Existing indexing uses a Qdrant integer point ID equal to the
        # PostgreSQL attraction ID.  ``retrieve`` therefore verifies the
        # exact stable identity for this imported scope without requiring the
        # problematic payload-filter endpoint in the currently running
        # Qdrant server. Qdrant itself guarantees uniqueness of point IDs.
        target_ids = [point_id_for_attraction(record["attraction_id"]) for record in records]
        retrieved = client.retrieve(
            collection_name=collection,
            ids=target_ids,
            with_payload=True,
            with_vectors=False,
        )
        matching_points: dict[int, list[Any]] = {target: [] for target in target_ids}
        for point in retrieved:
            if isinstance(point.id, int) and point.id in matching_points:
                matching_points[point.id].append(point)
        point_audit: list[dict[str, Any]] = []
        for record in records:
            result = classify_point(
                attraction_id=record["attraction_id"],
                expected_hash=record["semantic_document_sha256"],
                points=matching_points[point_id_for_attraction(record["attraction_id"])],
            )
            point_audit.append({"attraction_id": record["attraction_id"], **result})
        audit["point_identity_audit_complete"] = True
        audit["point_identity_audit_method"] = "direct_stable_point_id_retrieve"
        audit["payload_duplicate_scan"] = "not_run: server filtered-scroll endpoint is unhealthy"
        return audit, point_audit
    except Exception as exc:  # report an unavailable service; never create it.
        audit.update({"status": "unavailable", "error": type(exc).__name__})
        return audit, []


async def run_preflight(batch_id: str, qdrant_url: str) -> dict[str, Any]:
    batch, records = await load_imported_records(batch_id)
    qdrant_audit, point_audit = audit_qdrant(records, qdrant_url)
    point_by_id = {row["attraction_id"]: row for row in point_audit}
    for record in records:
        record["qdrant_point_id"] = point_id_for_attraction(record["attraction_id"])
        record["vector_status"] = point_by_id.get(record["attraction_id"], {}).get("classification", "NOT_AUDITED")

    classifications = Counter(row["vector_status"] for row in records)
    invalid = [row for row in records if row["validation_failures"]]
    compatible = bool(qdrant_audit.get("vector_configuration", {}).get("compatible"))
    scope_valid = (
        batch.get("status") == "completed"
        and batch.get("applied_action_count") == EXPECTED_IMPORTED_COUNT
        and len(records) == EXPECTED_IMPORTED_COUNT
        and len({row["source_attraction_id"] for row in records}) == EXPECTED_IMPORTED_COUNT
    )
    ready = [row for row in records if not row["validation_failures"] and row["vector_status"] in {
        "MISSING_VECTOR", "EXISTING_VECTOR_STALE"
    }]
    reasons: list[str] = []
    if not scope_valid:
        reasons.append("committed_import_scope_invalid")
    if invalid:
        reasons.append("invalid_semantic_documents")
    if not qdrant_audit.get("collection_exists"):
        reasons.append("qdrant_collection_unavailable")
    elif not qdrant_audit.get("point_identity_audit_complete"):
        reasons.append("qdrant_point_identity_audit_incomplete")
    elif not compatible:
        reasons.append("embedding_vector_schema_incompatible")
    if any(row["vector_status"] == "VECTOR_IDENTITY_CONFLICT" for row in records):
        reasons.append("qdrant_point_identity_conflicts")

    return {
        "batch": batch,
        "records": records,
        "qdrant_collection_audit": qdrant_audit,
        "qdrant_point_identity_audit": point_audit,
        "summary": {
            "mode": "dry_run",
            "postgresql_imported_records": len(records),
            "semantic_documents_prepared": len(records) - len(invalid),
            "missing_vectors": classifications["MISSING_VECTOR"],
            "existing_current_vectors": classifications["EXISTING_VECTOR_CURRENT"],
            "stale_vectors": classifications["EXISTING_VECTOR_STALE"],
            "identity_conflicts": classifications["VECTOR_IDENTITY_CONFLICT"],
            "invalid_semantic_documents": len(invalid),
            "ready_to_sync": len(ready) if not reasons else 0,
            "postgresql_writes_executed": False,
            "qdrant_writes_executed": False,
            "external_api_requests": 0,
            "status": "READY_FOR_EXPLICIT_QDRANT_SYNC" if not reasons else "NOT_READY_FOR_QDRANT_SYNC",
            "reasons": reasons,
        },
        "incremental_sync_plan": {
            "future_operation": "authorized_incremental_qdrant_upsert",
            "eligible_attraction_ids": [row["attraction_id"] for row in ready] if not reasons else [],
            "steps": [
                "re-read committed PostgreSQL scope",
                "rebuild deterministic semantic documents",
                "generate normalized BGE embeddings",
                "validate 1024-dimensional finite vectors",
                "upsert only missing or stale stable point IDs",
                "verify persistence and retrieval",
            ],
            "writes_executed": False,
        },
    }


def report_paths(batch_id: str, reports_dir: str) -> dict[str, Path]:
    prefix = Path(reports_dir) / f"stage_10_1_3e_gate5e2d1_{batch_id}_"
    return {name: prefix.with_name(prefix.name + filename) for name, filename in {
        "postgresql_import_validation": "postgresql_import_validation.json",
        "qdrant_collection_audit": "qdrant_collection_audit.json",
        "semantic_documents": "semantic_documents.json",
        "semantic_document_validation": "semantic_document_validation.json",
        "embedding_compatibility_audit": "embedding_compatibility_audit.json",
        "qdrant_point_identity_audit": "qdrant_point_identity_audit.json",
        "incremental_sync_plan": "incremental_sync_plan.json",
        "dry_run_summary": "dry_run_summary.json",
        "summary": "summary.json",
    }.items()}


def emit_reports(result: dict[str, Any], batch_id: str, reports_dir: str) -> dict[str, str]:
    paths = report_paths(batch_id, reports_dir)
    records = result["records"]
    write_report(paths["postgresql_import_validation"], {
        "batch": result["batch"], "scope_expected": EXPECTED_IMPORTED_COUNT,
        "records": [{key: row[key] for key in (
            "attraction_id", "source_attraction_id", "active", "district_id", "category_names",
            "google_place_id", "source_reference_count", "field_provenance_count",
            "committed_review_present", "validation_failures",
        )} for row in records],
    })
    write_report(paths["qdrant_collection_audit"], result["qdrant_collection_audit"])
    write_report(paths["semantic_documents"], {"document_schema_version": DOCUMENT_SCHEMA_VERSION, "records": [
        {key: row[key] for key in (
            "attraction_id", "source_attraction_id", "name", "semantic_text",
            "semantic_document_sha256", "document_schema_version", "missing_optional_fields",
        )} for row in records]})
    write_report(paths["semantic_document_validation"], {"records": [
        {key: row[key] for key in ("attraction_id", "source_attraction_id", "validation_failures", "missing_optional_fields")}
        for row in records]})
    write_report(paths["embedding_compatibility_audit"], {
        "embedding_model": AttractionEmbeddingService.MODEL_NAME,
        "expected_dimension": AttractionEmbeddingService.EXPECTED_DIMENSION,
        "document_prefix": None, "query_prefix": None, "normalizes_embeddings": True,
        "collection_vector_configuration": result["qdrant_collection_audit"].get("vector_configuration"),
        "embedding_generation_performed": False,
    })
    write_report(paths["qdrant_point_identity_audit"], {"records": result["qdrant_point_identity_audit"]})
    write_report(paths["incremental_sync_plan"], result["incremental_sync_plan"])
    write_report(paths["dry_run_summary"], result["summary"])
    write_report(paths["summary"], {
        **result["summary"],
        "qdrant_collection_name": AttractionQdrantIndexer.COLLECTION_NAME,
        "qdrant_point_count": result["qdrant_collection_audit"].get("point_count"),
        "embedding_model": AttractionEmbeddingService.MODEL_NAME,
        "vector_dimension": AttractionEmbeddingService.EXPECTED_DIMENSION,
    })
    return {name: str(path) for name, path in paths.items()}


def main() -> None:
    parser = argparse.ArgumentParser(description="Read-only Gate 5E.2D.1 Qdrant preflight")
    parser.add_argument("--batch-id", default="all_completed_v1")
    parser.add_argument("--dry-run", action="store_true", help="Required for clarity; dry run is always the only mode.")
    parser.add_argument("--reports-dir", default="data/reports")
    parser.add_argument("--qdrant-url", default=settings.QDRANT_URL)
    args = parser.parse_args()
    result = asyncio.run(run_preflight(args.batch_id, args.qdrant_url))
    paths = emit_reports(result, args.batch_id, args.reports_dir)
    print(json.dumps({**result["summary"], "reports": paths}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
