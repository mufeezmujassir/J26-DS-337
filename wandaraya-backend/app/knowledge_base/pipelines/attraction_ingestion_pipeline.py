from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.knowledge_base.connectors.google_places import GooglePlacesConnector
from app.knowledge_base.processors.normalizer import AttractionNormalizer
from app.knowledge_base.processors.validator import AttractionValidation
from app.knowledge_base.processors.district_resolver import DistrictResolver
from app.knowledge_base.processors.deduplicator import AttractionDeduplicator

from app.knowledge_base.loaders.attraction_loader import AttractionLoader
from app.knowledge_base.loaders.mapping_loader import MappingLoader

from app.knowledge_base.enrichment.wikipedia_enricher import WikipediaEnricher
from app.knowledge_base.enrichment.wikivoyage_enricher import WikivoyageEnricher

from app.knowledge_base.processors.category_activity_mapper import (
    CategoryActivityMapper,
)

from app.knowledge_base.embeddings.document_builder import (
    AttractionDocumentBuilder,
)
from app.knowledge_base.embeddings.embedding_service import (
    AttractionEmbeddingService,
)
from app.knowledge_base.embeddings.qdrant_indexer import (
    AttractionQdrantIndexer,
)

# Backwards-compatible alias for older code paths
QdrantIndexer = AttractionQdrantIndexer

logger = logging.getLogger(__name__)

class PipelineStatus(str,Enum):
    SUCCESS = "SUCCESS"
    SKIPPED = "SKIPPED"
    FAILED = "FAILED"


@dataclass
class AttractionPipelineResult:
    place_id: str
    status: PipelineStatus

    attraction_id: int | None = None
    attraction_name: str | None = None

    district: str | None = None
    district_name: str | None = None

    wikipedia_enriched: bool = False
    wikivoyage_enriched: bool = False
    categories_mapped: int = 0
    activities_mapped: int = 0
    semantic_document_created: bool = False
    embedding_created: bool = False

    indexed_in_qdrant: bool = False

    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)



@dataclass
class BatchPipelineResult:


    total: int = 0
    success: int = 0
    skipped: int = 0
    failed: int = 0

    results: list[AttractionPipelineResult] = field(
        default_factory=list
    )

    def add(self, result: AttractionPipelineResult) -> None:

        self.total += 1
        self.results.append(result)

        if result.status == PipelineStatus.SUCCESS:
            self.success += 1

        elif result.status == PipelineStatus.SKIPPED:
            self.skipped += 1

        elif result.status == PipelineStatus.FAILED:
            self.failed += 1

    @property
    def successful(self) -> int:
        return self.success

class AttractionIngestionPipeline:
    """
    Complete attraction ingestion pipeline.

    Flow
    ----

    Google Place Details ->  Normalization->Validation -> District Resolution
    -> Deduplication -> PostgreSQL Upsert -> Wikipedia Enrichment -> Wikivoyage Enrichment 
    -> Category / Activity Mapping -> Persistence -> Semantic Document -> BGE Embedding -> Qdrant Upsert

    """

    def __init__(
        self,
        db: Session,
        google_places: GooglePlacesConnector | None = None,
    ) -> None:

        self.db = db


        self.google_places = (
            google_places or GooglePlacesConnector()
        )

       

        self.normalizer = AttractionNormalizer()

        self.validator = AttractionValidation()

        self.district_resolver = DistrictResolver()

        self.deduplicator = AttractionDeduplicator()

        self.attraction_loader = AttractionLoader()

        self.mapping_loader = MappingLoader()

        self.wikipedia_enricher = WikipediaEnricher()

        self.wikivoyage_enricher = WikivoyageEnricher()

        self.mapper = CategoryActivityMapper()

        self.document_builder = AttractionDocumentBuilder()

        self.embedding_service = AttractionEmbeddingService()

        self.qdrant_indexer = QdrantIndexer()



    async def process_place(
        self,
        place_id: str,
    ) -> AttractionPipelineResult:
        """
        Process a single Google Place through the complete pipeline.
        """

        logger.info(
            "Starting attraction pipeline | place_id=%s",
            place_id,
        )

        result = AttractionPipelineResult(
            place_id=place_id,
            status=PipelineStatus.FAILED,
        )

        try:


            logger.info(
                "[1/13] Fetching Google Place Details"
            )

            place_details = (
                await self.google_places.get_place_details(
                    place_id
                )
            )

            if not place_details:

                result.status = PipelineStatus.SKIPPED

                result.errors.append(
                    "Google Place Details returned no data."
                )

                logger.warning(
                    "No Google data | place_id=%s",
                    place_id,
                )

                return result


            logger.info(
                "[2/13] Normalizing attraction"
            )

            normalized = self.normalizer.normalize_google_place(
                place_details
            )

            if not normalized:

                result.status = PipelineStatus.SKIPPED

                result.errors.append(
                    "Normalizer returned no attraction data."
                )

                return result

            result.attraction_name = normalized.get("name")


            logger.info(
                "[3/13] Validating attraction | name=%s",
                result.attraction_name,
            )

            validation = self.validator.validate(
                normalized
            )

            # Your ValidationResult may expose warnings.
            validation_warnings = getattr(
                validation,
                "warnings",
                [],
            )

            if validation_warnings:
                result.warnings.extend(
                    str(w)
                    for w in validation_warnings
                )

            if not validation.is_valid:

                result.status = PipelineStatus.SKIPPED

                validation_errors = getattr(
                    validation,
                    "errors",
                    [],
                )

                result.errors.extend(
                    str(error)
                    for error in validation_errors
                )

                logger.warning(
                    "Validation rejected attraction | "
                    "place_id=%s name=%s",
                    place_id,
                    result.attraction_name,
                )

                return result



            logger.info(
                "[4/13] Resolving district"
            )

            latitude = normalized.get("latitude")
            longitude = normalized.get("longitude")

            district = await self.district_resolver.resolve_attraction(
                db=self.db,
                attraction=normalized,
            )

            if not district.found:

                result.status = PipelineStatus.SKIPPED

                result.errors.append(
                    "Unable to resolve Sri Lankan district."
                )

                logger.warning(
                    "District resolution failed | "
                    "name=%s lat=%s lon=%s",
                    result.attraction_name,
                    latitude,
                    longitude,
                )

                return result

            normalized["district_id"] = district.district_id

            result.district = district.district_name
            result.district_name = district.district_name


            logger.info(
                "[5/13] Checking duplicates"
            )

            duplicate = await self.db.run_sync(
                lambda sync_db: AttractionDeduplicator.find_duplicates(
                    db=sync_db,
                    attraction=normalized,
                )
            )

            existing = duplicate.existing_attraction if duplicate.is_duplicated else None

            if existing:

                logger.info(
                    "Existing attraction found | "
                    "existing_id=%s",
                    existing.id,
                )


            logger.info(
                "[6/13] Upserting attraction"
            )

            attraction = await self.db.run_sync(
                lambda sync_db: AttractionLoader.upsert(
                    db=sync_db,
                    attraction_data=normalized,
                    existing=existing,
                )
            )

            # Flush so ID exists before descriptions/mappings.
            await self.db.flush()

            result.attraction_id = attraction.id
            result.attraction_name = attraction.name

            logger.info(
                "Attraction persisted | id=%s name=%s",
                attraction.id,
                attraction.name,
            )


            logger.info(
                "[7/13] Wikipedia enrichment"
            )

            try:

                wikipedia_record = await self.wikipedia_enricher.enrich(
                    self.db,
                    attraction,
                )

                result.wikipedia_enriched = wikipedia_record is not None

                await self.db.flush()

            except Exception as exc:

                logger.exception(
                    "Wikipedia enrichment failed | "
                    "attraction_id=%s",
                    attraction.id,
                )

                # Wikipedia failure should NOT destroy the
                # entire attraction.
                result.warnings.append(
                    f"Wikipedia enrichment failed: {exc}"
                )

            logger.info(
                "[8/13] Wikivoyage enrichment"
            )

            try:

                wikivoyage_record = await self.wikivoyage_enricher.enrich(
                    self.db,
                    attraction,
                )

                result.wikivoyage_enriched = wikivoyage_record is not None

                await self.db.flush()

            except Exception as exc:

                logger.exception(
                    "Wikivoyage enrichment failed | "
                    "attraction_id=%s",
                    attraction.id,
                )

                result.warnings.append(
                    f"Wikivoyage enrichment failed: {exc}"
                )


            logger.info(
                "[9/13] Generating semantic mappings"
            )

            mappings = self.mapper.map(
                normalized
            )

            result.categories_mapped = len(mappings.categories)
            result.activities_mapped = len(mappings.activities)

            logger.info(
                "Semantic mappings generated | "
                "categories=%s activities=%s",
                result.categories_mapped,
                result.activities_mapped,
            )

            logger.info(
                "[10/13] Persisting mappings"
            )

            await self.mapping_loader.load(
                db=self.db,
                attraction_id=attraction.id,
                mapping=mappings,
            )

            await self.db.flush()

            logger.info(
                "[11/13] Building semantic document"
            )

            semantic_document = (
                await self.document_builder.build(
                    self.db,
                    attraction.id,
                )
            )

            if not semantic_document:

                raise RuntimeError(
                    "Semantic document builder "
                    "returned empty document."
                )


            if isinstance(
                semantic_document,
                str,
            ):
                document_text = semantic_document

            else:
                document_text = getattr(
                    semantic_document,
                    "text",
                    None,
                )

            if not document_text:

                raise RuntimeError(
                    "Semantic document contains no text."
                )

  
            logger.info(
                "[12/13] Creating BGE embedding"
            )

            vector = (
                self.embedding_service.encode_document(
                    document_text
                )
            )

            if vector is None:

                raise RuntimeError(
                    "Embedding service returned None."
                )

            if hasattr(vector, "vector"):
                vector_values = vector.vector
            else:
                vector_values = vector

            if hasattr(vector_values, "tolist"):
                vector_values = vector_values.tolist()

            if len(vector_values) != 1024:

                raise RuntimeError(
                    "Invalid BGE embedding dimension. "
                    f"Expected 1024, received {len(vector_values)}."
                )


            logger.info(
                "[13/13] Indexing attraction in Qdrant"
            )

            indexed = self.qdrant_indexer.index(
                document=semantic_document,
                embedding=vector,
            )

            result.indexed_in_qdrant = bool(indexed.indexed)

            if not result.indexed_in_qdrant:

                raise RuntimeError(
                    "Qdrant indexing failed."
                )

            result.embedding_created = True
            result.semantic_document_created = True

            result.status = PipelineStatus.SUCCESS

            logger.info(
                "Attraction pipeline completed | "
                "id=%s name=%s",
                attraction.id,
                attraction.name,
            )

            return result

        except Exception as exc:

            logger.exception(
                "Attraction pipeline failed | "
                "place_id=%s",
                place_id,
            )

            result.status = PipelineStatus.FAILED

            result.errors.append(str(exc))

            return result


    async def process_places(
        self,
        place_ids: list[str],
        *,
        commit_each: bool = True,
    ) -> BatchPipelineResult:
        

        batch = BatchPipelineResult()

        # Remove duplicates while preserving input order.
        unique_place_ids = list(
            dict.fromkeys(place_ids)
        )

        logger.info(
            "Starting multi-attraction ingestion | count=%s",
            len(unique_place_ids),
        )

        for number, place_id in enumerate(
            unique_place_ids,
            start=1,
        ):

            logger.info(
                "Processing attraction %s/%s | %s",
                number,
                len(unique_place_ids),
                place_id,
            )

            try:

                result = await self.process_place(
                    place_id
                )

                if result.status == PipelineStatus.SUCCESS:

                    if commit_each:
                        await self.db.commit()

                elif result.status == PipelineStatus.SKIPPED:

                    # Clear pending transaction changes from
                    # this attraction.
                    await self.db.rollback()

                else:

                    await self.db.rollback()

                batch.add(result)

            except Exception as exc:

                await self.db.rollback()

                logger.exception(
                    "Unexpected batch error | place_id=%s",
                    place_id,
                )

                batch.add(
                    AttractionPipelineResult(
                        place_id=place_id,
                        status=PipelineStatus.FAILED,
                        errors=[str(exc)],
                    )
                )

        # If transaction-per-attraction is disabled,
        # commit the whole successful batch here.
        if not commit_each:

            try:
                await self.db.commit()

            except Exception:

                await self.db.rollback()

                logger.exception(
                    "Final batch commit failed."
                )

                raise

        logger.info(
            "Batch ingestion completed | "
            "total=%s success=%s skipped=%s failed=%s",
            batch.total,
            batch.success,
            batch.skipped,
            batch.failed,
        )

        return batch           
