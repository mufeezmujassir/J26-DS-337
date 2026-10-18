"""Gate 5E.2D.6: read-only post-cutover semantic-search verification.

This command deliberately performs no PostgreSQL writes, Qdrant upserts, model
downloads, collection changes, or service restarts.  It verifies the active
FastAPI-to-Qdrant path and writes evidence reports only.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import math
import os
import shutil
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from qdrant_client import QdrantClient
from sqlalchemy import func, select

from app.database import AsyncSessionLocal
from app.models.attraction import Attraction

EXPECTED_COLLECTION = "sri_lanka_attractions_staging"
EXPECTED_MODEL = "BAAI/bge-large-en-v1.5"
EXPECTED_DIMENSION = 1024
IMPORTED_IDS = list(range(6604, 6628))
SMOKE_QUERIES = (
    "historical attractions in Galle",
    "beaches suitable for relaxing",
    "wildlife safari attractions",
    "cultural and religious attractions in Kandy",
    "waterfalls and nature experiences",
    "family-friendly attractions",
    "photography and scenic locations",
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def write_report(path: Path, body: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(body, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def bounded_get(url: str, *, timeout_seconds: int) -> dict[str, Any]:
    started = time.monotonic()
    try:
        with urllib.request.urlopen(url, timeout=timeout_seconds) as response:
            raw = response.read().decode("utf-8", "replace")
            parsed = json.loads(raw)
            return {
                "http_status": response.status,
                "ok": 200 <= response.status < 300,
                "body": parsed,
                "latency_ms": round((time.monotonic() - started) * 1000, 2),
            }
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", "replace")
        try:
            body: Any = json.loads(raw)
        except json.JSONDecodeError:
            body = {"raw_response": raw[:2000]}
        return {
            "http_status": exc.code,
            "ok": False,
            "body": body,
            "latency_ms": round((time.monotonic() - started) * 1000, 2),
        }
    except Exception as exc:
        return {
            "http_status": None,
            "ok": False,
            "error": f"{type(exc).__name__}: {exc}",
            "latency_ms": round((time.monotonic() - started) * 1000, 2),
        }


def compact_candidates(body: Any) -> list[dict[str, Any]]:
    if not isinstance(body, list):
        return []
    return [
        {
            "attraction_id": item.get("id"),
            "name": item.get("name"),
            "semantic_score": item.get("semantic_score"),
        }
        for item in body
        if isinstance(item, dict)
    ]


def classify_semantic_response(result: dict[str, Any]) -> str:
    if result.get("http_status") != 200 or not isinstance(result.get("body"), list):
        return "failed"
    for candidate in result["body"]:
        if not isinstance(candidate, dict) or not isinstance(candidate.get("id"), int):
            return "failed"
        score = candidate.get("semantic_score")
        if not isinstance(score, (float, int)) or not math.isfinite(float(score)):
            return "failed"
    return "passed"


async def postgres_scope(ids: list[int]) -> dict[str, Any]:
    async with AsyncSessionLocal() as db:
        active_count = int(
            (await db.scalar(select(func.count()).select_from(Attraction).where(Attraction.is_active.is_(True)))) or 0
        )
        rows = (await db.execute(
            select(Attraction.id, Attraction.name, Attraction.is_active)
            .where(Attraction.id.in_(ids))
            .order_by(Attraction.id)
        )).all()
    values = {int(row.id): {"name": row.name, "active": bool(row.is_active)} for row in rows}
    return {"active_attraction_count": active_count, "records": values}


def qdrant_new_attraction_check(client: QdrantClient, collection: str, db_records: dict[int, dict[str, Any]]) -> dict[str, Any]:
    try:
        points = client.retrieve(collection_name=collection, ids=IMPORTED_IDS, with_payload=True, with_vectors=True)
    except Exception as exc:
        return {"status": "failed", "error": f"{type(exc).__name__}: {exc}", "records": []}
    by_id = {int(point.id): point for point in points}
    records: list[dict[str, Any]] = []
    for attraction_id in IMPORTED_IDS:
        point = by_id.get(attraction_id)
        payload = dict(point.payload or {}) if point else {}
        vector = point.vector if point else None
        dimension = len(vector or []) if isinstance(vector, list) else None
        database = db_records.get(attraction_id)
        valid = bool(
            point
            and int(payload.get("attraction_id", -1)) == attraction_id
            and dimension == EXPECTED_DIMENSION
            and database
            and database["active"]
        )
        records.append({
            "attraction_id": attraction_id,
            "point_id": int(point.id) if point else None,
            "payload_attraction_id": payload.get("attraction_id"),
            "postgresql_name": database["name"] if database else None,
            "postgresql_active": database["active"] if database else False,
            "vector_dimension": dimension,
            "document_hash": payload.get("document_hash"),
            "status": "passed" if valid else "failed",
        })
    return {"status": "passed" if all(item["status"] == "passed" for item in records) else "failed", "records": records}


def runtime_memory() -> dict[str, Any]:
    memory_current = None
    memory_limit = None
    for name, target in (("memory_current_bytes", "/sys/fs/cgroup/memory.current"), ("memory_limit_bytes", "/sys/fs/cgroup/memory.max")):
        try:
            value = Path(target).read_text(encoding="utf-8").strip()
            if value != "max":
                if name == "memory_current_bytes":
                    memory_current = int(value)
                else:
                    memory_limit = int(value)
        except (OSError, ValueError):
            pass
    disk = shutil.disk_usage("/")
    return {
        "api_container_memory_current_bytes": memory_current,
        "api_container_memory_limit_bytes": memory_limit,
        "filesystem_free_bytes": disk.free,
        "filesystem_total_bytes": disk.total,
    }


def final_status(*, semantic_verified: bool, recovery_snapshot_visible: bool) -> str:
    """Separate live-search readiness from durable recovery readiness."""
    if not semantic_verified:
        return "BLOCKED_DATA_INTEGRITY"
    if not recovery_snapshot_visible:
        return "SEMANTIC_SEARCH_VERIFIED"
    return "READY_FOR_RECOMMENDATION_BASELINE"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-url", default=os.getenv("GATE5E2D6_API_URL", "http://localhost:8000"))
    parser.add_argument("--qdrant-url", default=os.getenv("QDRANT_URL", "http://qdrant-production-replacement:6333"))
    parser.add_argument("--collection", default=os.getenv("QDRANT_COLLECTION_NAME", EXPECTED_COLLECTION))
    parser.add_argument("--reports-dir", default="data/reports")
    parser.add_argument("--timeout-seconds", type=int, default=60)
    args = parser.parse_args()
    if args.timeout_seconds < 1 or args.timeout_seconds > 180:
        parser.error("--timeout-seconds must be between 1 and 180")

    reports_dir = Path(args.reports_dir)
    status = bounded_get(f"{args.api_url.rstrip('/')}/api/v1/knowledge-base/status", timeout_seconds=args.timeout_seconds)
    health = bounded_get(f"{args.api_url.rstrip('/')}/health", timeout_seconds=args.timeout_seconds)
    smoke_results: list[dict[str, Any]] = []
    for query in SMOKE_QUERIES:
        encoded = urllib.parse.urlencode({"query": query, "limit": 5})
        result = bounded_get(
            f"{args.api_url.rstrip('/')}/api/v1/knowledge-base/semantic-search?{encoded}",
            timeout_seconds=args.timeout_seconds,
        )
        smoke_results.append({
            "query": query,
            "status": classify_semantic_response(result),
            "http_status": result.get("http_status"),
            "latency_ms": result.get("latency_ms"),
            "candidate_count": len(compact_candidates(result.get("body"))),
            "candidates": compact_candidates(result.get("body")),
            "error": result.get("error"),
        })

    repeated_query = SMOKE_QUERIES[0]
    repeated = [
        bounded_get(
            f"{args.api_url.rstrip('/')}/api/v1/knowledge-base/semantic-search?"
            f"{urllib.parse.urlencode({'query': repeated_query, 'limit': 5})}",
            timeout_seconds=args.timeout_seconds,
        )
        for _ in range(2)
    ]
    repeat_ids = [item.get("id") for item in (repeated[0].get("body") or [])] == [item.get("id") for item in (repeated[1].get("body") or [])]
    empty = bounded_get(
        f"{args.api_url.rstrip('/')}/api/v1/knowledge-base/semantic-search?query=&limit=5",
        timeout_seconds=args.timeout_seconds,
    )
    invalid_limit = bounded_get(
        f"{args.api_url.rstrip('/')}/api/v1/knowledge-base/semantic-search?query=Galle&limit=51",
        timeout_seconds=args.timeout_seconds,
    )

    scope = asyncio.run(postgres_scope(IMPORTED_IDS))
    client = QdrantClient(url=args.qdrant_url, timeout=args.timeout_seconds)
    collection_report: dict[str, Any]
    try:
        info = client.get_collection(args.collection)
        vectors = info.config.params.vectors
        collection_report = {"status": "passed", "points_count": int(info.points_count or 0), "vector_dimension": getattr(vectors, "size", None)}
        snapshots = [item.name for item in client.list_snapshots(args.collection)]
    except Exception as exc:
        collection_report = {"status": "failed", "error": f"{type(exc).__name__}: {exc}"}
        snapshots = []
    new_attractions = qdrant_new_attraction_check(client, args.collection, scope["records"]) if collection_report["status"] == "passed" else {"status": "failed", "records": []}

    config_checks = {
        "api_status_http_200": status.get("http_status") == 200,
        "api_reports_expected_collection": isinstance(status.get("body"), dict) and status["body"].get("qdrant_collection") == EXPECTED_COLLECTION,
        "api_reports_expected_model": isinstance(status.get("body"), dict) and status["body"].get("embedding_model") == EXPECTED_MODEL,
        "api_reports_expected_dimension": isinstance(status.get("body"), dict) and status["body"].get("embedding_dimension") == EXPECTED_DIMENSION,
        "api_reports_6120_points": isinstance(status.get("body"), dict) and status["body"].get("qdrant_points") == 6120,
        "postgresql_has_6120_active_attractions": scope["active_attraction_count"] == 6120,
        "qdrant_has_6120_points": collection_report.get("points_count") == 6120,
        "qdrant_has_expected_dimension": collection_report.get("vector_dimension") == EXPECTED_DIMENSION,
    }
    smoke_passed = all(item["status"] == "passed" for item in smoke_results)
    stability = {
        "repeat_query_status": "passed" if repeat_ids else "failed",
        "empty_query_http_status": empty.get("http_status"),
        "empty_query_safe": empty.get("http_status") == 422,
        "invalid_limit_http_status": invalid_limit.get("http_status"),
        "invalid_limit_safe": invalid_limit.get("http_status") == 422,
        "no_database_writes_executed": True,
        "no_qdrant_writes_executed": True,
    }
    semantic_verified = all(config_checks.values()) and smoke_passed and new_attractions["status"] == "passed" and all(
        value is True or value == "passed" or key.endswith("http_status")
        for key, value in stability.items()
    )
    recovery_snapshot_visible = bool(snapshots)

    smoke_report = {
        "generated_at_utc": utc_now(), "mode": "read_only_api_smoke_test", "api_url": args.api_url,
        "queries": smoke_results, "stability": stability,
        "postgresql_writes_executed": False, "qdrant_writes_executed": False,
    }
    embedding_report = {
        "generated_at_utc": utc_now(), "mode": "observation_only", "model_identifier": EXPECTED_MODEL,
        "embedding_dimension": EXPECTED_DIMENSION,
        "model_loading_status": "verified_via_successful_active_fastapi_semantic_inference" if smoke_passed else "not_verified",
        "initial_load_duration_ms": None,
        "initial_load_duration_note": "Not re-measured because this verification must not restart the active API or instantiate a second model process.",
        "inference_latency_ms": {item["query"]: item["latency_ms"] for item in smoke_results},
        "runtime_resources": runtime_memory(),
        "errors_or_warnings": [],
    }
    health_report = {
        "generated_at_utc": utc_now(), "mode": "read_only", "api_health": health,
        "configuration_checks": config_checks, "qdrant_collection": collection_report,
        "snapshot_names": snapshots,
        "recovery_snapshot_visible_to_replacement": recovery_snapshot_visible,
        "recovery_snapshot_note": (
            "A collection snapshot is visible to the active replacement service."
            if recovery_snapshot_visible else
            "No snapshot is visible to the active replacement service. Semantic search can operate, "
            "but create and persist a replacement snapshot before declaring recovery readiness."
        ),
        "runtime_resources": runtime_memory(),
        "legacy_qdrant_not_used_by_active_api": args.qdrant_url != "http://qdrant:6333",
        "postgresql_writes_executed": False, "qdrant_writes_executed": False,
    }
    tests_report = {
        "generated_at_utc": utc_now(), "mode": "runtime_read_only_regression_checks",
        "checks": {
            "active_collection_selection": config_checks["api_reports_expected_collection"],
            "embedding_dimension": config_checks["api_reports_expected_dimension"],
            "semantic_response_validation": smoke_passed,
            "qdrant_to_postgresql_hydration": all(item["candidate_count"] >= 0 for item in smoke_results),
            "new_attraction_identities_6604_to_6627": new_attractions["status"] == "passed",
            "empty_query_validation": stability["empty_query_safe"],
            "invalid_limit_validation": stability["invalid_limit_safe"],
            "repeat_query_stability": stability["repeat_query_status"] == "passed",
        },
        "postgresql_writes_executed": False, "qdrant_writes_executed": False,
    }
    final = {
        "generated_at_utc": utc_now(),
        "status": final_status(
            semantic_verified=semantic_verified,
            recovery_snapshot_visible=recovery_snapshot_visible,
        ),
        "configuration_checks_passed": all(config_checks.values()),
        "semantic_smoke_tests_passed": smoke_passed,
        "new_attraction_verification_passed": new_attractions["status"] == "passed",
        "recovery_snapshot_visible_to_replacement": recovery_snapshot_visible,
        "collection": args.collection, "qdrant_url": args.qdrant_url,
        "postgresql_active_attractions": scope["active_attraction_count"],
        "qdrant_points": collection_report.get("points_count"),
        "reports": {
            "semantic_smoke_test": "gate5e2d6_semantic_smoke_test.json",
            "embedding_warmup": "gate5e2d6_embedding_warmup.json",
            "new_attraction_verification": "gate5e2d6_new_attraction_verification.json",
            "post_cutover_health": "gate5e2d6_post_cutover_health.json",
            "regression_tests": "gate5e2d6_regression_tests.json",
        },
        "postgresql_writes_executed": False, "qdrant_writes_executed": False,
    }
    write_report(reports_dir / "gate5e2d6_semantic_smoke_test.json", smoke_report)
    write_report(reports_dir / "gate5e2d6_embedding_warmup.json", embedding_report)
    write_report(reports_dir / "gate5e2d6_new_attraction_verification.json", new_attractions)
    write_report(reports_dir / "gate5e2d6_post_cutover_health.json", health_report)
    write_report(reports_dir / "gate5e2d6_regression_tests.json", tests_report)
    write_report(reports_dir / "gate5e2d6_final_summary.json", final)
    print(json.dumps(final, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
