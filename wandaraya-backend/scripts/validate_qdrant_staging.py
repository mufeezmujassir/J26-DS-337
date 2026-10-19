"""Read-only integrity validation for a rebuilt Qdrant staging collection."""
from __future__ import annotations

import argparse
import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from qdrant_client import QdrantClient
from qdrant_client.models import FieldCondition, Filter, MatchValue
from sqlalchemy import func, select

from app.database import AsyncSessionLocal
from app.models.attraction import Attraction
from scripts.rebuild_qdrant_staging import (
    DEFAULT_COLLECTION,
    DEFAULT_URL,
    STAGING_COLLECTION_PREFIX,
    VECTOR_SIZE,
    require_staging_collection,
)


async def source_scope() -> tuple[int, int | None]:
    async with AsyncSessionLocal() as db:
        count = int(
            (await db.scalar(select(func.count()).select_from(Attraction).where(Attraction.is_active.is_(True))))
            or 0
        )
        first_id = await db.scalar(
            select(Attraction.id).where(Attraction.is_active.is_(True)).order_by(Attraction.id).limit(1)
        )
        return count, int(first_id) if first_id is not None else None


def full_scroll_ids(client: QdrantClient, collection: str, limit: int = 256) -> tuple[set[int], str | None]:
    ids: set[int] = set()
    offset = None
    try:
        while True:
            points, offset = client.scroll(
                collection_name=collection,
                offset=offset,
                limit=limit,
                with_payload=True,
                with_vectors=False,
            )
            ids.update(int(point.id) for point in points)
            if offset is None:
                return ids, None
    except Exception as exc:
        return ids, f"{type(exc).__name__}: {exc}"


def validate(*, qdrant_url: str, collection: str) -> dict[str, Any]:
    require_staging_collection(collection)
    expected_count, sample_id = asyncio.run(source_scope())
    result: dict[str, Any] = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "mode": "read_only_validation",
        "qdrant_url": qdrant_url,
        "collection": collection,
        "expected_postgresql_active_attractions": expected_count,
        "postgresql_writes_executed": False,
        "qdrant_writes_executed": False,
        "checks": {},
        "blockers": [],
    }
    client = QdrantClient(url=qdrant_url)
    try:
        info = client.get_collection(collection)
        result["checks"]["collection"] = {"status": "ok", "points_count": int(info.points_count or 0)}
        vectors = info.config.params.vectors
        vector_size = getattr(vectors, "size", None)
        result["checks"]["vector_dimension"] = {"status": "ok" if vector_size == VECTOR_SIZE else "failed", "actual": vector_size, "expected": VECTOR_SIZE}
        if vector_size != VECTOR_SIZE:
            result["blockers"].append("unexpected_vector_dimension")
    except Exception as exc:
        result["checks"]["collection"] = {"status": "failed", "error": f"{type(exc).__name__}: {exc}"}
        result["blockers"].append("collection_unavailable")
        result["status"] = "STAGING_NOT_READY"
        return result

    ids, scroll_error = full_scroll_ids(client, collection)
    result["checks"]["full_unfiltered_scroll"] = {
        "status": "ok" if scroll_error is None else "failed",
        "unique_point_ids": len(ids),
        "error": scroll_error,
    }
    if scroll_error:
        result["blockers"].append("unfiltered_scroll_failed")
    if len(ids) != expected_count:
        result["blockers"].append("point_count_does_not_match_postgresql_scope")

    if sample_id is not None:
        try:
            direct = client.retrieve(collection_name=collection, ids=[sample_id], with_payload=True, with_vectors=True)
            point = direct[0] if direct else None
            payload = dict(point.payload or {}) if point else {}
            result["checks"]["direct_retrieve"] = {
                "status": "ok" if point and payload.get("attraction_id") == sample_id and len(point.vector or []) == VECTOR_SIZE else "failed",
                "sample_id": sample_id,
                "payload_attraction_id": payload.get("attraction_id"),
                "vector_dimension": len(point.vector or []) if point else None,
            }
            if not point:
                result["blockers"].append("sample_point_missing")
            else:
                condition = Filter(must=[FieldCondition(key="attraction_id", match=MatchValue(value=sample_id))])
                filtered, _ = client.scroll(collection_name=collection, scroll_filter=condition, limit=2, with_payload=True, with_vectors=False)
                result["checks"]["filtered_scroll_existing"] = {"status": "ok" if any(int(p.id) == sample_id for p in filtered) else "failed", "returned": len(filtered)}
                absent_filter = Filter(must=[FieldCondition(key="attraction_id", match=MatchValue(value=-9999999))])
                absent, _ = client.scroll(collection_name=collection, scroll_filter=absent_filter, limit=1, with_payload=True, with_vectors=False)
                result["checks"]["filtered_scroll_absent"] = {"status": "ok" if not absent else "failed", "returned": len(absent)}
                queried = client.query_points(collection_name=collection, query=point.vector, limit=1, with_payload=True)
                top = queried.points[0] if queried.points else None
                result["checks"]["vector_search"] = {"status": "ok" if top and int(top.id) == sample_id else "failed", "top_id": int(top.id) if top else None}
        except Exception as exc:
            result["checks"]["identity_filter_and_search"] = {"status": "failed", "error": f"{type(exc).__name__}: {exc}"}
            result["blockers"].append("direct_retrieve_filter_or_search_failed")

    for check in result["checks"].values():
        if check.get("status") == "failed":
            result["blockers"].append("staging_validation_check_failed")
            break
    result["blockers"] = sorted(set(result["blockers"]))
    result["status"] = "STAGING_VALIDATED" if not result["blockers"] else "STAGING_NOT_READY"
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--collection", default=DEFAULT_COLLECTION)
    parser.add_argument("--qdrant-url", default=DEFAULT_URL)
    parser.add_argument("--output", default="data/reports/qdrant_staging_validation.json")
    args = parser.parse_args()
    report = validate(qdrant_url=args.qdrant_url, collection=args.collection)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
