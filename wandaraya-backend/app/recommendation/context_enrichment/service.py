"""Orchestrate existing semantic retrieval and weather suitability services.

This module is read-only.  It neither changes semantic rankings nor writes to
the tourism knowledge base, weather tables, model registry, or vector store.
"""

from __future__ import annotations

from datetime import date
from typing import Iterable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.knowledge_base.retrieval.semantic_retriever import (
    SemanticAttractionRetriever,
    SemanticCandidate,
)
from app.models.activities import Activity
from app.models.attraction import Attraction
from app.models.attraction_activities import AttractionActivity
from app.models.attraction_categories import AttractionCategory
from app.models.attraction_descriptions import AttractionDescription
from app.models.categories import Category
from app.models.data_sources import DataSource
from app.models.district import District
from app.recommendation.context_dimensions.weather_adapter import WeatherDimensionAdapter
from app.recommendation.context_enrichment.schemas import (
    CanonicalCandidateEnvelope,
    ContextEnrichmentResponse,
    DescriptionProvenance,
    EnrichedSemanticCandidate,
    SemanticRetrievalEvidence,
    WeatherContextEvidence,
    WeatherDimensionEvidence,
)
from app.weather_model.suitability.activity_mapper import map_activity_to_weather_profile
from app.weather_model.suitability.attraction_schemas import (
    AttractionWeatherBatchRequest,
    AttractionWeatherCandidate,
)
from app.weather_model.suitability.attraction_service import (
    AttractionWeatherSuitabilityService,
)
from app.weather_model.suitability.calibration_integration import (
    calibrate_attraction_response,
)


class SemanticWeatherContextEnrichmentService:
    """Attach existing weather evidence to semantic candidates exactly once."""

    retrieval_source = "qdrant:sri_lanka_attractions"

    def __init__(
        self,
        db: AsyncSession,
        weather_service: AttractionWeatherSuitabilityService,
        retriever: SemanticAttractionRetriever | None = None,
    ):
        self.db = db
        self.weather_service = weather_service
        self.retriever = retriever or SemanticAttractionRetriever()

    async def enrich(
        self,
        *,
        query: str,
        travel_date: date,
        top_k: int,
        forecast_mode: str,
    ) -> ContextEnrichmentResponse:
        retrieved = await self.retriever.search(self.db, query, limit=top_k)
        ranked = self._deduplicate(retrieved)
        metadata = await self._hydrate(candidate.attraction_id for candidate, _ in ranked)

        envelopes: list[CanonicalCandidateEnvelope] = []
        batch_candidates: list[AttractionWeatherCandidate] = []
        for candidate, rank in ranked:
            item = metadata.get(candidate.attraction_id)
            if item is None:
                # The retriever already filters inactive rows.  Retaining this
                # guard makes a concurrent deactivation safely invisible.
                continue
            envelope = self._envelope(candidate, rank, item)
            envelopes.append(envelope)
            if envelope.district_id is not None and envelope.supported_weather_profiles:
                batch_candidates.append(
                    AttractionWeatherCandidate(
                        attraction_id=envelope.attraction_id,
                        name=envelope.attraction_name,
                        district_id=envelope.district_id,
                        latitude=envelope.latitude,
                        longitude=envelope.longitude,
                        activity_types=envelope.supported_weather_profiles,
                        coordinate_source=envelope.coordinate_source,
                    )
                )

        weather_by_id = {}
        if batch_candidates:
            response = await self.weather_service.evaluate_batch(
                AttractionWeatherBatchRequest(
                    travel_date=travel_date,
                    attractions=batch_candidates,
                    forecast_mode=forecast_mode,
                )
            )
            calibrated = calibrate_attraction_response(response)
            weather_by_id = {result.attraction_id: result for result in calibrated.results}

        enriched = [
            EnrichedSemanticCandidate(
                candidate=envelope,
                weather=self._weather_evidence(
                    envelope,
                    weather_by_id.get(envelope.attraction_id),
                ),
            )
            for envelope in envelopes
        ]
        return ContextEnrichmentResponse(
            query=query,
            travel_date=travel_date,
            forecast_mode=forecast_mode,
            retrieval_source=self.retrieval_source,
            candidates_retrieved=len(ranked),
            candidates_enriched=len(enriched),
            candidates=enriched,
        )

    @staticmethod
    def _deduplicate(
        candidates: Iterable[SemanticCandidate],
    ) -> list[tuple[SemanticCandidate, int]]:
        """Keep first (highest-ranked) occurrence of each canonical ID.

        Qdrant returns candidates in descending similarity order.  On equal
        scores its existing response order remains the deterministic tie-break.
        """
        seen: set[int] = set()
        unique: list[tuple[SemanticCandidate, int]] = []
        for original_rank, candidate in enumerate(candidates, start=1):
            if candidate.attraction_id in seen:
                continue
            seen.add(candidate.attraction_id)
            unique.append((candidate, original_rank))
        return unique

    async def _hydrate(self, attraction_ids: Iterable[int]) -> dict[int, dict]:
        ids = list(attraction_ids)
        if not ids:
            return {}
        attractions = (await self.db.execute(
            select(Attraction).where(Attraction.id.in_(ids), Attraction.is_active.is_(True))
        )).scalars().all()
        result = {
            attraction.id: {
                "attraction": attraction,
                "activities": [],
                "categories": [],
                "provenance": [],
                "district_coordinates": (None, None),
            }
            for attraction in attractions
        }
        if not result:
            return result

        districts = (await self.db.execute(
            select(District.id, District.latitude, District.longitude).where(
                District.id.in_([a.district_id for a in attractions if a.district_id is not None])
            )
        )).all()
        for district_id, latitude, longitude in districts:
            for attraction in attractions:
                if attraction.district_id == district_id:
                    result[attraction.id]["district_coordinates"] = (latitude, longitude)

        activity_rows = (await self.db.execute(
            select(AttractionActivity.attraction_id, Activity.name)
            .join(Activity, Activity.id == AttractionActivity.activity_id)
            .where(
                AttractionActivity.attraction_id.in_(result),
                AttractionActivity.is_available.is_(True),
                Activity.is_active.is_(True),
            )
            .order_by(AttractionActivity.attraction_id, AttractionActivity.suitability_score.desc(), Activity.id)
        )).all()
        for attraction_id, name in activity_rows:
            result[attraction_id]["activities"].append(name)

        category_rows = (await self.db.execute(
            select(AttractionCategory.attraction_id, Category.name)
            .join(Category, Category.id == AttractionCategory.category_id)
            .where(
                AttractionCategory.attraction_id.in_(result),
                Category.is_active.is_(True),
            )
            .order_by(AttractionCategory.attraction_id, AttractionCategory.is_primary.desc(), Category.name)
        )).all()
        for attraction_id, name in category_rows:
            result[attraction_id]["categories"].append(name)

        provenance_rows = (await self.db.execute(
            select(
                AttractionDescription.attraction_id,
                DataSource.name,
                AttractionDescription.source_url,
                AttractionDescription.language,
                AttractionDescription.content_hash,
            )
            .outerjoin(DataSource, DataSource.id == AttractionDescription.source_id)
            .where(
                AttractionDescription.attraction_id.in_(result),
                AttractionDescription.is_active.is_(True),
            )
            .order_by(AttractionDescription.attraction_id, AttractionDescription.id)
        )).all()
        for attraction_id, source, source_url, language, content_hash in provenance_rows:
            result[attraction_id]["provenance"].append(
                DescriptionProvenance(
                    source=source,
                    source_url=source_url,
                    language=language,
                    content_hash=content_hash,
                )
            )
        return result

    def _envelope(self, candidate: SemanticCandidate, rank: int, item: dict) -> CanonicalCandidateEnvelope:
        attraction: Attraction = item["attraction"]
        activity_names = item["activities"]
        profiles = [
            profile for name in activity_names
            if (profile := map_activity_to_weather_profile(name)) is not None
        ]
        unsupported = [
            name for name in activity_names
            if map_activity_to_weather_profile(name) is None
        ]
        latitude, longitude, coordinate_source, issue = self._coordinates(
            attraction.latitude,
            attraction.longitude,
            item["district_coordinates"],
        )
        return CanonicalCandidateEnvelope(
            attraction_id=attraction.id,
            attraction_name=attraction.name,
            semantic=SemanticRetrievalEvidence(
                score=candidate.score,
                rank=rank,
                source=self.retrieval_source,
            ),
            district_id=attraction.district_id,
            latitude=latitude,
            longitude=longitude,
            coordinate_source=coordinate_source,
            coordinate_issue=issue,
            category_names=item["categories"],
            activity_names=activity_names,
            supported_weather_profiles=profiles,
            unsupported_activity_names=unsupported,
            description_provenance=item["provenance"],
        )

    @staticmethod
    def _coordinates(
        latitude: float | None,
        longitude: float | None,
        district_coordinates: tuple[float | None, float | None],
    ) -> tuple[float | None, float | None, str, str | None]:
        if latitude is not None and longitude is not None:
            return latitude, longitude, "attraction", None
        district_latitude, district_longitude = district_coordinates
        issue = (
            "Attraction latitude and longitude must both be present."
            if (latitude is None) != (longitude is None)
            else "Attraction coordinates are unavailable."
        )
        if district_latitude is not None and district_longitude is not None:
            return district_latitude, district_longitude, "district_fallback", issue
        return None, None, "unavailable", issue

    @staticmethod
    def _weather_evidence(envelope: CanonicalCandidateEnvelope, result) -> WeatherContextEvidence:
        if result is None:
            if envelope.district_id is None:
                reason = "Weather context is unavailable because this attraction has no district assignment."
            elif not envelope.supported_weather_profiles:
                reason = "Weather context is unavailable because no attraction activity maps to a supported weather profile."
            else:
                reason = "Weather context is unavailable for this attraction."
            return WeatherContextEvidence(
                status="unknown",
                suitability="Unknown",
                confidence="unavailable",
                message=reason,
                unsupported_activity_types=envelope.unsupported_activity_names,
                provenance={"coordinate_source": envelope.coordinate_source},
                dimension=WeatherDimensionEvidence(
                    score=None,
                    confidence=0.0,
                    available=False,
                    eligible=False,
                    source=None,
                    version="unavailable",
                ),
            )

        adapted = WeatherDimensionAdapter.transform(result)
        return WeatherContextEvidence(
            status="available" if result.available else "unknown",
            suitability_score=result.weather_score,
            suitability=result.suitability,
            confidence=result.confidence,
            source=result.weather_source,
            resolution=result.weather_resolution,
            evidence_level=result.weather_evidence_level,
            message=result.message,
            activity_scores=result.activity_scores,
            unsupported_activity_types=result.unsupported_activity_types,
            risk_factors=result.risk_factors,
            provenance=result.provenance,
            dimension=WeatherDimensionEvidence(
                score=adapted.score,
                confidence=adapted.confidence,
                available=adapted.available,
                eligible=adapted.eligible,
                source=adapted.source,
                version=adapted.version,
                metadata=adapted.metadata,
            ),
        )
