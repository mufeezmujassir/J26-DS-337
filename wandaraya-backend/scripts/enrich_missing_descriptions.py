"""Backfill missing Wikimedia descriptions without repeating Google ingestion.

This command only touches missing Wikipedia/Wikivoyage descriptions.  When a
description is saved, it rebuilds the existing semantic document and upserts
the corresponding BGE vector into Qdrant.  It never creates attractions,
downloads Google details/photos, changes district assignment, or rewrites
category/activity mappings.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
from dataclasses import dataclass

from sqlalchemy import exists, or_, select

from app.database import AsyncSessionLocal
from app.knowledge_base.embeddings.document_builder import AttractionDocumentBuilder
from app.knowledge_base.embeddings.embedding_service import AttractionEmbeddingService
from app.knowledge_base.embeddings.qdrant_indexer import AttractionQdrantIndexer
from app.knowledge_base.enrichment.wikipedia_enricher import WikipediaEnricher
from app.knowledge_base.enrichment.wikivoyage_enricher import WikivoyageEnricher
from app.models.attraction import Attraction
from app.models.attraction_descriptions import AttractionDescription
from app.models.data_sources import DataSource

logger = logging.getLogger(__name__)

SOURCE_NAMES = ("Wikipedia", "Wikivoyage")


@dataclass
class BackfillSummary:
    selected: int = 0
    selected_ids: list[int] | None = None
    wikipedia_saved: int = 0
    wikivoyage_saved: int = 0
    no_safe_match: int = 0
    source_failures: int = 0
    reindexed: int = 0
    reindex_failures: int = 0


async def _source_ids() -> dict[str, int]:
    async with AsyncSessionLocal() as db:
        rows = await db.execute(select(DataSource.name, DataSource.id).where(DataSource.name.in_(SOURCE_NAMES)))
        source_ids = dict(rows.all())
    missing = set(SOURCE_NAMES) - set(source_ids)
    if missing:
        raise RuntimeError(f"Missing required data_sources rows: {', '.join(sorted(missing))}")
    return source_ids


async def _target_ids(source_ids: dict[str, int], limit: int, start_after_id: int) -> list[int]:
    missing_source_clauses = [
        ~exists(select(AttractionDescription.id).where(
            AttractionDescription.attraction_id == Attraction.id,
            AttractionDescription.source_id == source_id,
            AttractionDescription.is_active.is_(True),
        ))
        for source_id in source_ids.values()
    ]
    async with AsyncSessionLocal() as db:
        rows = await db.execute(
            select(Attraction.id)
            .where(Attraction.is_active.is_(True), Attraction.id > start_after_id, or_(*missing_source_clauses))
            .order_by(Attraction.id)
            .limit(limit)
        )
        return list(rows.scalars().all())


async def _missing_for_attraction(attraction_id: int, source_ids: dict[str, int]) -> set[str]:
    async with AsyncSessionLocal() as db:
        rows = await db.execute(select(AttractionDescription.source_id).where(
            AttractionDescription.attraction_id == attraction_id,
            AttractionDescription.source_id.in_(source_ids.values()),
            AttractionDescription.is_active.is_(True),
        ))
        present_ids = set(rows.scalars().all())
    return {name for name, source_id in source_ids.items() if source_id not in present_ids}


async def process_one(attraction_id: int, source_ids: dict[str, int], summary: BackfillSummary) -> None:
    missing_sources = await _missing_for_attraction(attraction_id, source_ids)
    if not missing_sources:
        return
    saved = False
    async with AsyncSessionLocal() as db:
        attraction = await db.get(Attraction, attraction_id)
        if attraction is None or not attraction.is_active:
            return
        if "Wikipedia" in missing_sources:
            try:
                saved_record = await WikipediaEnricher().enrich(db, attraction)
                if saved_record is None:
                    summary.no_safe_match += 1
                else:
                    summary.wikipedia_saved += 1
                    saved = True
            except Exception:
                summary.source_failures += 1
                logger.exception("Wikipedia description backfill failed | attraction_id=%s", attraction_id)
        if "Wikivoyage" in missing_sources:
            try:
                saved_record = await WikivoyageEnricher().enrich(db, attraction)
                if saved_record is None:
                    summary.no_safe_match += 1
                else:
                    summary.wikivoyage_saved += 1
                    saved = True
            except Exception:
                summary.source_failures += 1
                logger.exception("Wikivoyage description backfill failed | attraction_id=%s", attraction_id)
        try:
            await db.commit()
        except Exception:
            await db.rollback()
            raise

    if not saved:
        return
    # Re-open after the commit so the document builder reads exactly the saved
    # description set. Qdrant is updated only after the relational save succeeds.
    try:
        async with AsyncSessionLocal() as db:
            document = await AttractionDocumentBuilder.build(db, attraction_id)
        embedding = AttractionEmbeddingService.encode_document(document.text)
        result = AttractionQdrantIndexer().index(document=document, embedding=embedding)
        if result.indexed:
            summary.reindexed += 1
    except Exception:
        summary.reindex_failures += 1
        logger.exception("Semantic/Qdrant rebuild failed after saved description | attraction_id=%s", attraction_id)


async def run(limit: int, start_after_id: int) -> BackfillSummary:
    source_ids = await _source_ids()
    target_ids = await _target_ids(source_ids, limit, start_after_id)
    summary = BackfillSummary(selected=len(target_ids), selected_ids=target_ids)
    for number, attraction_id in enumerate(target_ids, start=1):
        logger.info("Description backfill %s/%s | attraction_id=%s", number, len(target_ids), attraction_id)
        await process_one(attraction_id, source_ids, summary)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill missing Wikimedia descriptions and reindex only changed attractions.")
    parser.add_argument("--limit", type=int, default=20, help="Maximum attractions per run; use small batches to respect Wikimedia.")
    parser.add_argument("--start-after-id", type=int, default=0, help="Resume after a known attraction ID.")
    args = parser.parse_args()
    if args.limit <= 0 or args.start_after_id < 0:
        parser.error("--limit must be positive and --start-after-id must be zero or positive")
    summary = asyncio.run(run(args.limit, args.start_after_id))
    print("=== DESCRIPTION BACKFILL ===")
    print(f"Selected attractions: {summary.selected}")
    if summary.selected_ids:
        print(f"Processed ID range: {summary.selected_ids[0]} to {summary.selected_ids[-1]}")
    print(f"Wikipedia descriptions saved/refreshed: {summary.wikipedia_saved}")
    print(f"Wikivoyage descriptions saved/refreshed: {summary.wikivoyage_saved}")
    print(f"No sufficiently safe match: {summary.no_safe_match}")
    print(f"Source request failures: {summary.source_failures}")
    print(f"Semantic documents + Qdrant points rebuilt: {summary.reindexed}")
    print(f"Semantic/Qdrant rebuild failures: {summary.reindex_failures}")


if __name__ == "__main__":
    main()
