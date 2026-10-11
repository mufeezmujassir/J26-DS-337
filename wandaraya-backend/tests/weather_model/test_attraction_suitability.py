from datetime import date
from unittest.mock import AsyncMock

import pytest

from app.weather_model.context.schemas import UnifiedWeatherContext
from app.weather_model.suitability.attraction_schemas import (
    AttractionWeatherBatchRequest,
)
from app.weather_model.suitability.attraction_service import (
    AttractionWeatherSuitabilityService,
)


@pytest.fixture
def mock_context_service():
    service = AsyncMock()
    service.get_context.return_value = UnifiedWeatherContext(
        district_id=78,
        travel_date=date(2026, 10, 13),
        reference_date=date(2026, 10, 11),
        days_ahead=2,
        selected_source="live_api",
        actual_source="openweathermap",
        available=True,
        resolution="three_hourly_aggregated",
        rainfall_mm=2.19,
        rainfall_period="available_3h_intervals",
        temperature_min_c=26.9,
        temperature_max_c=30.23,
        precipitation_probability_max=0.98,
        provenance={"provider": "OpenWeatherMap"},
        message="Available",
    )
    return service


def request(*attractions) -> AttractionWeatherBatchRequest:
    return AttractionWeatherBatchRequest(
        travel_date=date(2026, 10, 13),
        attractions=list(attractions),
    )


def candidate(attraction_id: int, activities: list[str], **overrides) -> dict:
    values = {
        "attraction_id": attraction_id,
        "name": f"Attraction {attraction_id}",
        "district_id": 78,
        "latitude": 6.0535,
        "longitude": 80.2210,
        "activity_types": activities,
    }
    values.update(overrides)
    return values


@pytest.mark.asyncio
async def test_reuses_weather_context_for_same_location(mock_context_service):
    service = AttractionWeatherSuitabilityService(mock_context_service)

    result = await service.evaluate_batch(
        request(candidate(1, ["hiking"]), candidate(2, ["indoor_museum"]))
    )

    assert mock_context_service.get_context.await_count == 1
    assert result.available_attractions == 2
    assert result.results[0].weather_score == 56.42
    assert result.results[1].weather_score == 95.64


@pytest.mark.asyncio
async def test_averages_only_supported_activities(mock_context_service):
    service = AttractionWeatherSuitabilityService(mock_context_service)

    result = await service.evaluate_batch(
        request(candidate(1, ["hiking", "cultural_outdoor", "photography"]))
    )

    attraction = result.results[0]
    assert attraction.weather_score == 62.96
    assert attraction.scored_activity_count == 2
    assert attraction.unsupported_activity_types == ["photography"]


@pytest.mark.asyncio
async def test_unavailable_weather_is_propagated(mock_context_service):
    mock_context_service.get_context.return_value = UnifiedWeatherContext(
        district_id=78,
        travel_date=date(2026, 11, 15),
        reference_date=date(2026, 10, 11),
        days_ahead=35,
        selected_source="monthly_forecast",
        actual_source="monthly_forecast",
        available=False,
        resolution="unavailable",
        missing_targets=["rainfall_mm", "temperature_min_c", "temperature_max_c"],
        message="No valid production-approved monthly forecasts are available.",
    )
    service = AttractionWeatherSuitabilityService(mock_context_service)

    result = await service.evaluate_batch(request(candidate(1, ["hiking"])))

    assert result.available_attractions == 0
    assert result.results[0].weather_score is None
    assert result.results[0].suitability == "Unknown"


@pytest.mark.asyncio
async def test_different_locations_use_separate_context_lookups(mock_context_service):
    service = AttractionWeatherSuitabilityService(mock_context_service)

    await service.evaluate_batch(
        request(
            candidate(1, ["hiking"]),
            candidate(2, ["hiking"], latitude=6.1, longitude=80.3),
        )
    )

    assert mock_context_service.get_context.await_count == 2
