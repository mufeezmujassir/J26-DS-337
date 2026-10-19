"""Rebuild a disposable Qdrant staging collection from PostgreSQL.

This command is intentionally isolated from the production Qdrant collection.
It defaults to a read-only planning run.  Its execute path can create and
upsert only a collection whose name starts with ``sri_lanka_attractions_staging``.
It never issues PostgreSQL writes and never reads a Qdrant snapshot.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams
from sqlalchemy import func, select

from app.database import AsyncSessionLocal
from app.knowledge_base.embeddings.document_builder import AttractionDocumentBuilder
from app.knowledge_base.embeddings.embedding_service import AttractionEmbeddingService
from app.models.attraction import Attraction

STAGING_COLLECTION_PREFIX = "sri_lanka_attractions_staging"
DEFAULT_COLLECTION = "sri_lanka_attractions_staging"
DEFAULT_URL = "http://qdrant-staging:6333"
VECTOR_SIZE = 1024


def canonical_hash(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    ).hexdigest()


def require_staging_collection(collection: str) -> None:
    if not collection.startswith(STAGING_COLLECTION_PREFIX):
        raise ValueError(
            "Refusing to target a non-staging collection. "
            f"Collection must start with {STAGING_COLLECTION_PREFIX!r}."
        )


def validate_vector(vector: list[float]) -> dict[str, Any]:
    values = [float(value) for value in vector]
    norm = math.sqrt(sum(value * value for value in values))
    reasons: list[str] = []
    if len(values) != VECTOR_SIZE:
        reasons.append("unexpected_dimension")
    if not all(math.isfinite(value) for value in values):
        reasons.append("non_finite_value")
    if not math.isfinite(norm) or norm <= 0:
        reasons.append("invalid_norm")
    elif abs(norm - 1.0) > 1e-3:
        reasons.append("not_normalized")
    return {"valid": not reasons, "dimension": len(values), "norm": norm, "reasons": reasons}


def payload_for(document: Any, document_sha256: str) -> dict[str, Any]:
    return {
        "attraction_id": document.attraction_id,
        "name": document.name,
        "city": document.city,
        "district": document.district,
        "province": document.province,
        "categories": document.categories,
        "activities": document.activities,
        "semantic_document_sha256": document_sha256,
        "embedding_model": AttractionEmbeddingService.MODEL_NAME,
        "document_schema_version": "staging_rebuild_v1",
        "is_active": True,
    }


async def active_ids() -> list[int]:
    async with AsyncSessionLocal() as db:
        rows = await db.execute(
            select(Attraction.id)
            .where(Attraction.is_active.is_(True))
            .order_by(Attraction.id)
        )
        return [int(item) for item in rows.scalars().all()]


async def active_count() -> int:
    async with AsyncSessionLocal() as db:
        return int(
            (await db.scalar(select(func.count()).select_from(Attraction).where(Attraction.is_active.is_(True))))
            or 0
        )


async def build_document(attraction_id: int) -> tuple[Any, str]:
    async with AsyncSessionLocal() as db:
        document = await AttractionDocumentBuilder.build(db, attraction_id)
    document_sha256 = hashlib.sha256(document.text.encode("utf-8")).hexdigest()
    return document, document_sha256


def ensure_staging_collection(client: QdrantClient, collection: str) -> None:
    require_staging_collection(collection)
    if not client.collection_exists(collection):
        client.create_collection(
            collection_name=collection,
            vectors_config=VectorParams(size=VECTOR_SIZE, distance=Distance.COSINE),
        )
        return
    info = client.get_collection(collection)
    vectors = info.config.params.vectors
    size = getattr(vectors, "size", None)
    if size != VECTOR_SIZE:
        raise ValueError(f"Staging collection vector size is {size}; expected {VECTOR_SIZE}.")


def current_payloads(client: QdrantClient, collection: str, ids: list[int]) -> dict[int, dict[str, Any]]:
    result: dict[int, dict[str, Any]] = {}
    for start in range(0, len(ids), 128):
        points = client.retrieve(
            collection_name=collection,
            ids=ids[start : start + 128],
            with_payload=True,
            with_vectors=False,
        )
        for point in points:
            result[int(point.id)] = dict(point.payload or {})
    return result


async def rebuild(*, collection: str, qdrant_url: str, execute: bool, batch_size: int) -> dict[str, Any]:
    require_staging_collection(collection)
    ids = await active_ids()
    report: dict[str, Any] = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "mode": "execute" if execute else "dry_run",
        "qdrant_url": qdrant_url,
        "collection": collection,
        "postgresql_active_attractions": len(ids),
        "embedding_model": AttractionEmbeddingService.MODEL_NAME,
        "vector_dimension": VECTOR_SIZE,
        "postgresql_writes_executed": False,
        "production_qdrant_writes_executed": False,
        "staging_qdrant_writes_executed": False,
        "processed": 0,
        "upserted": 0,
        "reused_current": 0,
        "failures": [],
    }
    if not execute:
        report["scope_sha256"] = canonical_hash(ids)
        report["status"] = "READY_FOR_EXPLICIT_STAGING_REBUILD"
        return report

    client = QdrantClient(url=qdrant_url)
    ensure_staging_collection(client, collection)
    existing = current_payloads(client, collection, ids)
    pending: list[PointStruct] = []
    planned: list[dict[str, Any]] = []

    for attraction_id in ids:
        report["processed"] += 1
        try:
            document, document_sha256 = await build_document(attraction_id)
            current = existing.get(attraction_id, {})
            if (
                current.get("semantic_document_sha256") == document_sha256
                and current.get("embedding_model") == AttractionEmbeddingService.MODEL_NAME
            ):
                report["reused_current"] += 1
                planned.append({"attraction_id": attraction_id, "document_sha256": document_sha256, "operation": "reuse"})
                continue
            embedding = AttractionEmbeddingService.encode_document(document.text)
            validation = validate_vector(embedding.vector)
            if not validation["valid"]:
                raise ValueError("invalid_embedding:" + ",".join(validation["reasons"]))
            payload = payload_for(document, document_sha256)
            pending.append(PointStruct(id=attraction_id, vector=embedding.vector, payload=payload))
            planned.append({"attraction_id": attraction_id, "document_sha256": document_sha256, "operation": "upsert"})
            if len(pending) >= batch_size:
                client.upsert(collection_name=collection, points=pending, wait=True)
                report["upserted"] += len(pending)
                pending = []
        except Exception as exc:
            report["failures"].append({"attraction_id": attraction_id, "error": f"{type(exc).__name__}: {exc}"})

    if pending:
        client.upsert(collection_name=collection, points=pending, wait=True)
        report["upserted"] += len(pending)

    report["staging_qdrant_writes_executed"] = report["upserted"] > 0
    report["scope_sha256"] = canonical_hash(planned)
    report["status"] = "STAGING_REBUILD_COMPLETED" if not report["failures"] else "STAGING_REBUILD_COMPLETED_WITH_FAILURES"
    return report


def write_report(report: dict[str, Any], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(description=__doc__)
    value.add_argument("--collection", default=DEFAULT_COLLECTION)
    value.add_argument("--qdrant-url", default=DEFAULT_URL)
    value.add_argument("--batch-size", type=int, default=16)
    value.add_argument("--output", default="data/reports/qdrant_staging_rebuild.json")
    value.add_argument("--execute", action="store_true")
    value.add_argument("--confirm-execute", action="store_true")
    return value


def main() -> None:
    args = parser().parse_args()
    if args.batch_size < 1 or args.batch_size > 128:
        raise SystemExit("--batch-size must be between 1 and 128")
    if args.execute and not args.confirm_execute:
        raise SystemExit("Refusing staging writes without --confirm-execute")
    if not args.execute and args.confirm_execute:
        raise SystemExit("--confirm-execute requires --execute")
    try:
        report = asyncio.run(
            rebuild(
                collection=args.collection,
                qdrant_url=args.qdrant_url,
                execute=args.execute,
                batch_size=args.batch_size,
            )
        )
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    write_report(report, Path(args.output))
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
