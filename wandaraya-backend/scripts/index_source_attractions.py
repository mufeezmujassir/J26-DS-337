"""Index active attractions from one provenance source into configured Qdrant."""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

from sqlalchemy import text

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.database import AsyncSessionLocal
from app.knowledge_base.embeddings.document_builder import AttractionDocumentBuilder
from app.knowledge_base.embeddings.embedding_service import AttractionEmbeddingService
from app.knowledge_base.embeddings.qdrant_indexer import AttractionQdrantIndexer


async def source_ids(source_provider: str, new_only: bool) -> list[int]:
    condition = "AND r.identity_status IN ('google_verified','source_coordinates_verified')" if new_only else ""
    async with AsyncSessionLocal() as db:
        rows = await db.execute(text(f"""
            SELECT DISTINCT a.id
            FROM attractions a
            JOIN attraction_source_references r ON r.attraction_id=a.id
            WHERE a.is_active=TRUE AND r.source_provider=:provider {condition}
            ORDER BY a.id
        """), {"provider": source_provider})
        return [int(value) for value in rows.scalars().all()]


async def run(source_provider: str, new_only: bool) -> None:
    ids = await source_ids(source_provider, new_only)
    indexer = AttractionQdrantIndexer(url=os.getenv("QDRANT_URL", "http://qdrant:6333"))
    for position, attraction_id in enumerate(ids, 1):
        async with AsyncSessionLocal() as db:
            document = await AttractionDocumentBuilder.build(db, attraction_id)
        embedding = AttractionEmbeddingService.encode_document(document.text)
        indexer.index(document, embedding)
        print(f"indexed {position}/{len(ids)} attraction_id={attraction_id}", flush=True)
    print(f"indexed_total={len(ids)} collection={indexer.COLLECTION_NAME}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-provider", required=True)
    parser.add_argument("--new-only", action="store_true")
    args = parser.parse_args()
    asyncio.run(run(args.source_provider, args.new_only))


if __name__ == "__main__":
    main()
