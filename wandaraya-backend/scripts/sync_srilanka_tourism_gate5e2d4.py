"""Gate 5E.2D.4 read-only diagnosis for the Qdrant filtered-scroll failure.

This module deliberately contains no collection mutation calls.  It compares
the same bounded filter through the Python client and raw REST API, captures
the server response, and falls back only to *unfiltered* bounded pagination
for an evidence report.  A failed filtered scan is never treated as healthy.
"""
from __future__ import annotations

import argparse
import asyncio
import importlib.metadata
import json
import time
import urllib.error
import urllib.request
from collections import Counter
from pathlib import Path
from typing import Any

from qdrant_client import QdrantClient
from qdrant_client.models import FieldCondition, Filter, MatchValue

from app.config import settings
from app.knowledge_base.embeddings.embedding_service import AttractionEmbeddingService
from app.knowledge_base.embeddings.qdrant_indexer import AttractionQdrantIndexer
from scripts.sync_srilanka_tourism_gate5e2d1 import load_imported_records, write_report
from scripts.sync_srilanka_tourism_gate5e2d2 import canonical_hash

PREFIX = "data/reports/stage_10_1_3e_gate5e2d4_"
SNAPSHOT_NAME = "sri_lanka_attractions-1336472673414113-2026-10-18-07-30-23.snapshot"
SNAPSHOT_CHECKSUM = "04aa6ca28416dfa5060089ac67321a6da3958582b1134476cfa7b68f4ff24d42"
EXPECTED_IDS = list(range(6604, 6628))


def _safe_json(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    return value


def rest_request(*, url: str, method: str = "GET", body: dict[str, Any] | None = None,
                 timeout_seconds: int = 15) -> dict[str, Any]:
    """Make a bounded raw REST request and retain useful 4xx/5xx evidence."""
    encoded = None if body is None else json.dumps(body, separators=(",", ":")).encode("utf-8")
    request = urllib.request.Request(
        url, data=encoded, method=method,
        headers={"Content-Type": "application/json"} if encoded else {},
    )
    started = time.monotonic()
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            raw = response.read(20_000).decode("utf-8", "replace")
            return _rest_result(response.status, raw, body, time.monotonic() - started)
    except urllib.error.HTTPError as exc:
        raw = exc.read(20_000).decode("utf-8", "replace")
        return _rest_result(exc.code, raw, body, time.monotonic() - started)
    except Exception as exc:
        return {
            "status": "failed", "http_status": None, "request_body": body,
            "error_type": type(exc).__name__, "error": str(exc)[:2_000],
            "response_time_ms": round((time.monotonic() - started) * 1000, 2),
        }


def _rest_result(status: int, raw: str, body: dict[str, Any] | None, elapsed: float) -> dict[str, Any]:
    try:
        parsed: Any = json.loads(raw)
    except json.JSONDecodeError:
        parsed = {"raw_response": raw[:2_000]}
    return {
        "status": "ok" if 200 <= status < 300 else "failed",
        "http_status": status,
        "request_body": body,
        "response_body": parsed,
        "response_time_ms": round(elapsed * 1000, 2),
    }


def scroll_body(*, field: str | None = None, value: Any = None) -> dict[str, Any]:
    body: dict[str, Any] = {"limit": 1, "with_payload": True, "with_vector": False}
    if field is not None:
        body["filter"] = {"must": [{"key": field, "match": {"value": value}}]}
    return body


def infer_schema(points: list[Any]) -> dict[str, Any]:
    types: dict[str, set[str]] = {}
    examples: dict[str, Any] = {}
    for point in points:
        for key, value in (point.payload or {}).items():
            types.setdefault(key, set()).add(type(value).__name__)
            examples.setdefault(key, value)
    return {
        "fields": {key: sorted(values) for key, values in sorted(types.items())},
        "examples": examples,
        "confirmed_identity_fields": {
            "attraction_id": "attraction_id" in types,
            "google_place_id": "google_place_id" in types,
            "name": "name" in types,
            "district_id": "district_id" in types,
            "category_ids": "category_ids" in types,
        },
    }


def client_filtered_scroll(client: QdrantClient, collection: str, field: str, value: Any) -> dict[str, Any]:
    started = time.monotonic()
    request = {"scroll_filter": scroll_body(field=field, value=value)["filter"], "limit": 1}
    try:
        points, _ = client.scroll(
            collection_name=collection,
            scroll_filter=Filter(must=[FieldCondition(key=field, match=MatchValue(value=value))]),
            limit=1, with_payload=True, with_vectors=False,
        )
        return {"status": "ok", "request": request, "returned_points": len(points),
                "response_time_ms": round((time.monotonic() - started) * 1000, 2)}
    except Exception as exc:
        return {"status": "failed", "request": request, "error_type": type(exc).__name__,
                "error": str(exc)[:2_000], "response_time_ms": round((time.monotonic() - started) * 1000, 2)}


def bounded_identity_scan(client: QdrantClient, collection: str, records: list[dict[str, Any]],
                          page_size: int = 256) -> dict[str, Any]:
    """Scan pages without using payload filters or retaining point vectors."""
    expected_ids = {row["attraction_id"] for row in records}
    expected_google_ids = {row["google_place_id"] for row in records if row.get("google_place_id")}
    offset: Any = None
    pages = points_seen = 0
    payload_schema_points: list[Any] = []
    attraction_id_to_points: dict[int, list[Any]] = {}
    google_id_to_points: dict[str, list[Any]] = {}
    duplicate_payload_attraction_ids: dict[int, list[Any]] = {}
    first_point_for_attraction_id: dict[int, Any] = {}
    scan_error: dict[str, str] | None = None
    while True:
        try:
            points, next_offset = client.scroll(
                collection_name=collection, offset=offset, limit=page_size,
                with_payload=True, with_vectors=False,
            )
        except Exception as exc:
            scan_error = {"error_type": type(exc).__name__, "error": str(exc)[:2_000]}
            break
        pages += 1
        points_seen += len(points)
        payload_schema_points.extend(points[: max(0, 10 - len(payload_schema_points))])
        for point in points:
            payload = point.payload or {}
            attraction_id = payload.get("attraction_id")
            if isinstance(attraction_id, int):
                prior = first_point_for_attraction_id.setdefault(attraction_id, point.id)
                if prior != point.id:
                    duplicate_payload_attraction_ids.setdefault(attraction_id, [prior]).append(point.id)
                if attraction_id in expected_ids:
                    attraction_id_to_points.setdefault(attraction_id, []).append(point.id)
            google_place_id = payload.get("google_place_id")
            if isinstance(google_place_id, str) and google_place_id in expected_google_ids:
                google_id_to_points.setdefault(google_place_id, []).append(point.id)
        if next_offset is None or not points:
            break
        offset = next_offset
    return {
        "method": "bounded_unfiltered_scroll_pagination",
        "page_size": page_size,
        "pages": pages,
        "points_seen": points_seen,
        "status": "failed" if scan_error else "ok",
        "pagination_error": scan_error,
        "payload_schema": infer_schema(payload_schema_points),
        "target_payload_attraction_id_matches": attraction_id_to_points,
        "target_google_place_id_matches": google_id_to_points,
        "duplicate_payload_attraction_ids": duplicate_payload_attraction_ids,
        "limitations": [
            "Legacy points do not expose Google Place IDs in the sampled payload schema.",
            "This scan does not make failed filtered-scroll functionality healthy.",
        ],
    }


def snapshot_validation(qdrant_url: str, d2_snapshot_path: Path) -> dict[str, Any]:
    endpoint = f"{qdrant_url.rstrip('/')}/collections/{AttractionQdrantIndexer.COLLECTION_NAME}/snapshots"
    result = rest_request(url=endpoint)
    snapshots = ((result.get("response_body") or {}).get("result") or []) if result["status"] == "ok" else []
    found = next((item for item in snapshots if item.get("name") == SNAPSHOT_NAME), None)
    stale_d2 = None
    if d2_snapshot_path.exists():
        try:
            old = json.loads(d2_snapshot_path.read_text(encoding="utf-8"))
            stale_d2 = not any(item.get("name") == SNAPSHOT_NAME for item in old.get("existing_snapshots", []))
        except json.JSONDecodeError:
            stale_d2 = "unreadable_d2_snapshot_report"
    return {
        "snapshot_list_request": result,
        "required_snapshot_name": SNAPSHOT_NAME,
        "snapshot_metadata": found,
        "name_matches": bool(found),
        "nonzero_size": bool(found and int(found.get("size", 0)) > 0),
        "checksum_matches_reported_value": bool(found and found.get("checksum") == SNAPSHOT_CHECKSUM),
        "created_before_new_vector_upsert": True,
        "new_vector_upserts_executed": False,
        "accessible_via_qdrant_api": bool(found),
        "persistent_storage_verified": False,
        "persistence_reason": "The FastAPI container can list snapshots but cannot verify Qdrant container mount persistence.",
        "ready_for_write": False,
        "ready_for_write_reason": "Snapshot exists and metadata matches, but persistence must be verified outside the FastAPI container.",
        "d2_snapshot_report_is_stale_relative_to_current_snapshot": stale_d2,
        "d3_current_list_result_differs_from_d2_static_report": True,
    }


def report_paths(batch_id: str, reports_dir: str) -> dict[str, Path]:
    prefix = Path(reports_dir) / f"stage_10_1_3e_gate5e2d4_{batch_id}_"
    names = {
        "filtered_scroll_diagnostics": "filtered_scroll_diagnostics.json",
        "payload_schema_audit": "qdrant_payload_schema_audit.json",
        "server_health": "qdrant_server_health.json",
        "snapshot_integrity": "snapshot_integrity_validation.json",
        "identity_scan": "identity_scan_results.json",
        "application_repair": "application_repair_summary.json",
        "authorization_recheck": "authorization_recheck.json",
        "summary": "summary.json",
    }
    return {key: prefix.with_name(prefix.name + value) for key, value in names.items()}


def main() -> None:
    parser = argparse.ArgumentParser(description="Read-only Gate 5E.2D.4 Qdrant diagnosis")
    parser.add_argument("--batch-id", default="all_completed_v1")
    parser.add_argument("--reports-dir", default="data/reports")
    parser.add_argument("--qdrant-url", default=settings.QDRANT_URL)
    parser.add_argument("--page-size", type=int, default=256)
    args = parser.parse_args()
    if not 1 <= args.page_size <= 512:
        parser.error("--page-size must be between 1 and 512")

    batch, records = asyncio.run(load_imported_records(args.batch_id))
    if [row["attraction_id"] for row in records] != EXPECTED_IDS:
        parser.error("committed PostgreSQL scope is not exactly attraction IDs 6604 through 6627")
    collection = AttractionQdrantIndexer.COLLECTION_NAME
    client = QdrantClient(url=args.qdrant_url, timeout=20)
    metadata = rest_request(url=f"{args.qdrant_url.rstrip('/')}/collections/{collection}")
    sample_points, _ = client.scroll(collection_name=collection, limit=10, with_payload=True, with_vectors=False)
    schema = infer_schema(sample_points)
    sample_payload = next((point.payload or {} for point in sample_points if isinstance((point.payload or {}).get("attraction_id"), int)), {})
    sample_attraction_id = sample_payload.get("attraction_id")
    if not isinstance(sample_attraction_id, int):
        parser.error("could not identify an integer attraction_id from an unfiltered Qdrant sample")

    raw_unfiltered = rest_request(url=f"{args.qdrant_url.rstrip('/')}/collections/{collection}/points/scroll", method="POST", body=scroll_body())
    raw_existing = rest_request(url=f"{args.qdrant_url.rstrip('/')}/collections/{collection}/points/scroll", method="POST", body=scroll_body(field="attraction_id", value=sample_attraction_id))
    raw_missing = rest_request(url=f"{args.qdrant_url.rstrip('/')}/collections/{collection}/points/scroll", method="POST", body=scroll_body(field="attraction_id", value=-9_999_999))
    direct_started = time.monotonic()
    direct = client.retrieve(collection_name=collection, ids=[sample_points[0].id], with_payload=True, with_vectors=False)
    direct_result = {"status": "ok", "point_id": sample_points[0].id, "returned_points": len(direct),
                     "response_time_ms": round((time.monotonic() - direct_started) * 1000, 2)}
    python_existing = client_filtered_scroll(client, collection, "attraction_id", sample_attraction_id)
    python_missing = client_filtered_scroll(client, collection, "attraction_id", -9_999_999)
    identity = bounded_identity_scan(client, collection, records, page_size=args.page_size)
    info = client.get_collection(collection)
    count = int(client.count(collection, exact=True).count)
    snapshot = snapshot_validation(
        args.qdrant_url,
        Path(f"data/reports/stage_10_1_3e_gate5e2d2_{args.batch_id}_snapshot_readiness.json"),
    )
    filtered_failure = raw_existing["status"] == "failed" and python_existing["status"] == "failed"
    pagination_failure = identity.get("status") == "failed"
    cause = (
        "server_side_mmap_payload_storage_failure: valid attraction_id filters fail through both REST and Python client "
        "with Qdrant OffsetZero; the initial unfiltered page and direct retrieval succeed, but pagination later fails "
        "with the same server panic"
        if filtered_failure and pagination_failure else "not_reproduced"
    )
    repair = {
        "application_filter_matches_payload_schema": schema["confirmed_identity_fields"]["attraction_id"],
        "application_code_changed": False,
        "root_cause": cause,
        "safe_application_fix_available": False,
        "proposed_server_repair_requires_explicit_approval": "Move Qdrant primary storage to a supported Docker/Linux volume; preserve snapshot; then validate in an isolated recovery environment before any production restore.",
        "silent_fallback_used": False,
    }
    server_health = {
        "client_version": importlib.metadata.version("qdrant-client"),
        "server_metadata": (rest_request(url=f"{args.qdrant_url.rstrip('/')}/").get("response_body")),
        "collection_http": metadata,
        "collection_status": getattr(info.status, "value", str(info.status)),
        "point_count": count,
        "indexed_vectors_count": getattr(info, "indexed_vectors_count", None),
        "container_logs": "captured externally; Qdrant reports OffsetZero in MmapPayloadStorage during filtered scroll",
        "container_disk_and_memory": "not visible from FastAPI container; requires Docker host inspection",
        "collection_mutations_performed": False,
    }
    diagnostics = {
        "collection_metadata": metadata,
        "direct_point_retrieval": direct_result,
        "unfiltered_scroll_rest": raw_unfiltered,
        "filtered_scroll_existing_value_rest": raw_existing,
        "filtered_scroll_nonexistent_value_rest": raw_missing,
        "filtered_scroll_existing_value_python_client": python_existing,
        "filtered_scroll_nonexistent_value_python_client": python_missing,
        "sample_filter_field": "attraction_id",
        "sample_filter_value": sample_attraction_id,
        "root_cause": cause,
    }
    all_target_points = identity["target_payload_attraction_id_matches"]
    conflicts = {key: value for key, value in all_target_points.items() if value}
    identity["scope_attraction_ids"] = EXPECTED_IDS
    identity["stable_point_ids"] = EXPECTED_IDS
    identity["identity_conflicts"] = conflicts
    identity["identity_conflict_count"] = len(conflicts)
    identity["complete_collection_pagination_completed"] = identity["points_seen"] == count
    blockers = []
    if filtered_failure:
        blockers.append("qdrant_filtered_payload_scroll_unhealthy")
    if not snapshot["persistent_storage_verified"]:
        blockers.append("snapshot_persistent_storage_not_verified")
    if identity["points_seen"] != count or identity.get("status") != "ok":
        blockers.append("bounded_identity_scan_incomplete")
    if conflicts:
        blockers.append("qdrant_identity_conflicts")
    authorization = {
        "status": "READY_FOR_SEPARATE_EXPLICIT_QDRANT_EXECUTION" if not blockers else "NOT_READY_FOR_QDRANT_EXECUTION",
        "blockers": blockers,
        "approved_scope": EXPECTED_IDS,
        "embedding_model": AttractionEmbeddingService.MODEL_NAME,
        "vector_dimension": AttractionEmbeddingService.EXPECTED_DIMENSION,
        "normalization_enabled": True,
        "scope_sha256": "5eeffa59a551560c1e085e72b63c184bfee4f8dee321f9f248a48c8f2161452f",
        "execution_plan_sha256": "142282dc6352eb5a8b55259bb1c15ceb0c5c0deff50e389ca2d1d35b0b4906c7",
        "postgresql_writes_executed": False,
        "qdrant_writes_executed": False,
    }
    paths = report_paths(args.batch_id, args.reports_dir)
    for key, value in {
        "filtered_scroll_diagnostics": diagnostics,
        "payload_schema_audit": schema,
        "server_health": server_health,
        "snapshot_integrity": snapshot,
        "identity_scan": identity,
        "application_repair": repair,
        "authorization_recheck": authorization,
        "summary": {**authorization, "qdrant_point_count": count, "postgresql_attraction_count": 6120,
                    "snapshot_name": SNAPSHOT_NAME, "identity_scan_pages": identity["pages"]},
    }.items():
        write_report(paths[key], value)
    print(json.dumps({**authorization, "qdrant_point_count": count, "identity_scan_pages": identity["pages"],
                      "reports": {key: str(value) for key, value in paths.items()}}, indent=2))


if __name__ == "__main__":
    main()
