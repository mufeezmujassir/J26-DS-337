from datetime import date
from unittest.mock import AsyncMock

import pytest

from app.knowledge_base.retrieval.semantic_retriever import SemanticCandidate
from app.recommendation.context_enrichment.service import (
    SemanticWeatherContextEnrichmentService,
)
from app.weather_model.suitability.attraction_schemas import (
    AttractionWeatherBatchResponse,
    AttractionWeatherScore,
)


class FakeRetriever:
    def __init__(self, candidates):
        self.candidates = candidates
        self.search = AsyncMock(return_value=candidates)


def weather_result(attraction_id: int, *, available: bool = True):
    return AttractionWeatherScore(
        attraction_id=attraction_id,
        name=f"Attraction {attraction_id}",
        district_id=78,
        available=available,
        weather_score=80.0 if available else None,
        suitability="Good" if available else "Unknown",
        confidence="high" if available else "unavailable",
        weather_source="openweathermap",
        weather_resolution="three_hourly_aggregated",
        weather_evidence_level="short_term_forecast",
        activity_coverage_ratio=1.0,
        coverage_status="complete",
        message="Weather result",
    )


def hydrated(attraction_id, *, district_id=78, activities=None):
    attraction = type(
        "AttractionRow",
        (),
        {
            "id": attraction_id,
            "name": f"Attraction {attraction_id}",
            "district_id": district_id,
            "latitude": 6.05,
            "longitude": 80.22,
        },
    )()
    return {
        "attraction": attraction,
        "activities": activities if activities is not None else ["Hiking"],
        "categories": ["Nature"],
        "provenance": [],
        "district_coordinates": (6.0, 80.0),
    }


@pytest.mark.asyncio
async def test_preserves_semantic_score_rank_and_uses_existing_weather_adapter():
    retriever = FakeRetriever([
        SemanticCandidate(2, "Two", 0.93, "Galle", 78),
        SemanticCandidate(1, "One", 0.82, "Galle", 78),
    ])
    weather = AsyncMock()
    weather.evaluate_batch.return_value = AttractionWeatherBatchResponse(
        travel_date=date(2026, 10, 18),
        total_attractions=2,
        available_attractions=2,
        unavailable_attractions=0,
        results=[weather_result(2), weather_result(1)],
    )
    service = SemanticWeatherContextEnrichmentService(None, weather, retriever)
    service._hydrate = AsyncMock(return_value={1: hydrated(1), 2: hydrated(2)})

    response = await service.enrich(
        query="scenic hiking", travel_date=date(2026, 10, 18), top_k=10, forecast_mode="production"
    )

    assert [item.candidate.attraction_id for item in response.candidates] == [2, 1]
    assert [item.candidate.semantic.score for item in response.candidates] == [0.93, 0.82]
    assert [item.candidate.semantic.rank for item in response.candidates] == [1, 2]
    assert response.candidates[0].weather.suitability_score == 80.0
    # The raw 0–100 score is preserved separately. The existing calibrated
    # adapter provides the approved 0–1 dimension rather than a blind /100.
    assert response.candidates[0].weather.dimension.score == 0.77
    assert response.ranking_applied is False
    assert weather.evaluate_batch.await_count == 1


@pytest.mark.asyncio
async def test_deduplicates_canonical_attraction_id_by_first_semantic_rank():
    retriever = FakeRetriever([
        SemanticCandidate(1, "One", 0.95, "Galle", 78),
        SemanticCandidate(1, "One duplicate", 0.50, "Galle", 78),
    ])
    weather = AsyncMock()
    weather.evaluate_batch.return_value = AttractionWeatherBatchResponse(
        travel_date=date(2026, 10, 18), total_attractions=1, available_attractions=1,
        unavailable_attractions=0, results=[weather_result(1)],
    )
    service = SemanticWeatherContextEnrichmentService(None, weather, retriever)
    service._hydrate = AsyncMock(return_value={1: hydrated(1)})

    response = await service.enrich(query="temple", travel_date=date(2026, 10, 18), top_k=10, forecast_mode="production")

    assert response.candidates_retrieved == 1
    assert len(response.candidates) == 1
    assert response.candidates[0].candidate.semantic.score == 0.95
    assert response.candidates[0].candidate.semantic.rank == 1


@pytest.mark.asyncio
async def test_missing_district_and_unsupported_activities_remain_unknown_without_weather_call():
    retriever = FakeRetriever([SemanticCandidate(1, "One", 0.95, "", None)])
    weather = AsyncMock()
    service = SemanticWeatherContextEnrichmentService(None, weather, retriever)
    service._hydrate = AsyncMock(return_value={
        1: hydrated(1, district_id=None, activities=["Future Sky Activity"]),
    })

    response = await service.enrich(query="new activity", travel_date=date(2026, 10, 18), top_k=10, forecast_mode="planning")

    item = response.candidates[0]
    assert item.candidate.district_id is None
    assert item.candidate.unsupported_activity_names == ["Future Sky Activity"]
    assert item.weather.status == "unknown"
    assert item.weather.suitability_score is None
    assert item.weather.dimension.score is None
    weather.evaluate_batch.assert_not_awaited()


@pytest.mark.asyncio
async def test_empty_semantic_results_do_not_call_weather():
    retriever = FakeRetriever([])
    weather = AsyncMock()
    service = SemanticWeatherContextEnrichmentService(None, weather, retriever)
    service._hydrate = AsyncMock(return_value={})

    response = await service.enrich(query="nothing", travel_date=date(2026, 10, 18), top_k=10, forecast_mode="production")

    assert response.candidates == []
    assert response.candidates_retrieved == 0
    weather.evaluate_batch.assert_not_awaited()


@pytest.mark.asyncio
async def test_uses_explicit_district_coordinate_fallback_and_preserves_planning_mode():
    retriever = FakeRetriever([SemanticCandidate(1, "One", 0.95, "Galle", 78)])
    weather = AsyncMock()
    weather.evaluate_batch.return_value = AttractionWeatherBatchResponse(
        travel_date=date(2027, 4, 15), total_attractions=1, available_attractions=1,
        unavailable_attractions=0, results=[weather_result(1)],
    )
    metadata = hydrated(1)
    metadata["attraction"].latitude = None
    metadata["attraction"].longitude = None
    metadata["district_coordinates"] = (6.03, 80.21)
    service = SemanticWeatherContextEnrichmentService(None, weather, retriever)
    service._hydrate = AsyncMock(return_value={1: metadata})

    response = await service.enrich(query="hiking", travel_date=date(2027, 4, 15), top_k=1, forecast_mode="planning")

    candidate = response.candidates[0].candidate
    assert candidate.coordinate_source == "district_fallback"
    assert candidate.latitude == 6.03
    assert weather.evaluate_batch.await_args.args[0].forecast_mode == "planning"


@pytest.mark.asyncio
async def test_unavailable_weather_preserves_null_scores():
    retriever = FakeRetriever([SemanticCandidate(1, "One", 0.95, "Galle", 78)])
    weather = AsyncMock()
    weather.evaluate_batch.return_value = AttractionWeatherBatchResponse(
        travel_date=date(2026, 11, 30), total_attractions=1, available_attractions=0,
        unavailable_attractions=1, results=[weather_result(1, available=False)],
    )
    service = SemanticWeatherContextEnrichmentService(None, weather, retriever)
    service._hydrate = AsyncMock(return_value={1: hydrated(1)})

    response = await service.enrich(query="hiking", travel_date=date(2026, 11, 30), top_k=1, forecast_mode="production")

    assert response.candidates[0].weather.status == "unknown"
    assert response.candidates[0].weather.suitability_score is None
    assert response.candidates[0].weather.dimension.score is None
