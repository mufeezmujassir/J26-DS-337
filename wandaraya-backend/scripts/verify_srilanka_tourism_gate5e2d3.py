"""Read-only post-upsert verification for the separately authorized D.2 run."""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from qdrant_client import QdrantClient

from app.config import settings
from app.knowledge_base.embeddings.qdrant_indexer import AttractionQdrantIndexer
from scripts.sync_srilanka_tourism_gate5e2d1 import write_report


def main() -> None:
    parser = argparse.ArgumentParser(description="Read-only Gate 5E.2D.3 post-sync verification")
    parser.add_argument("--batch-id", default="all_completed_v1")
    parser.add_argument("--reports-dir", default="data/reports")
    parser.add_argument("--qdrant-url", default=settings.QDRANT_URL)
    args = parser.parse_args()
    plan_path = Path(f"data/reports/stage_10_1_3e_gate5e2d2_{args.batch_id}_incremental_sync_plan.json")
    documents_path = Path(f"data/reports/stage_10_1_3e_gate5e2d1_{args.batch_id}_semantic_documents.json")
    plan, documents = json.loads(plan_path.read_text(encoding="utf-8")), json.loads(documents_path.read_text(encoding="utf-8"))
    expected_hashes = {row["attraction_id"]: row["semantic_document_sha256"] for row in documents["records"]}
    client = QdrantClient(url=args.qdrant_url)
    points = client.retrieve(collection_name=plan["collection"], ids=plan["point_ids"], with_payload=True, with_vectors=True)
    by_id = {point.id: point for point in points}
    records = []
    for attraction_id in plan["point_ids"]:
        point = by_id.get(attraction_id)
        payload, vector = ((point.payload or {}), point.vector) if point else ({}, None)
        vector_valid = isinstance(vector, list) and len(vector) == plan["vector_dimension"] and all(math.isfinite(float(value)) for value in vector)
        records.append({"attraction_id": attraction_id, "exists": point is not None, "point_id_matches": bool(point and point.id == attraction_id), "payload_identity_matches": payload.get("attraction_id") == attraction_id, "document_hash_matches": payload.get("semantic_document_sha256") == expected_hashes[attraction_id], "embedding_model_matches": payload.get("embedding_model") == plan["embedding_model"], "vector_valid": vector_valid})
    report = {"collection": plan["collection"], "collection_point_count": client.count(plan["collection"], exact=True).count, "records": records, "all_valid": all(all(row[key] for key in ("exists", "point_id_matches", "payload_identity_matches", "document_hash_matches", "embedding_model_matches", "vector_valid")) for row in records), "postgresql_writes_executed": False, "qdrant_writes_executed": False}
    output = Path(args.reports_dir) / f"stage_10_1_3e_gate5e2d3_{args.batch_id}_post_sync_verification.json"
    write_report(output, report)
    print(json.dumps({**report, "report": str(output)}, indent=2))


if __name__ == "__main__":
    main()
