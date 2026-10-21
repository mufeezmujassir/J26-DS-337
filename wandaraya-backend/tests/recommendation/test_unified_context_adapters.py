from datetime import date, datetime, timezone
from types import SimpleNamespace

import pytest

from app.recommendation.unified_context.adapters.holiday_event import HolidayEventAdapter
from app.recommendation.unified_context.adapters.seasonality import SeasonalityAdapter
from app.recommendation.unified_context.adapters.time_of_day import TimeOfDayAdapter
from app.recommendation.unified_context.adapters.weather import WeatherAdapter
from app.recommendation.unified_context.schemas import EvidenceStatus
from app.weather_model.context.schemas import UnifiedWeatherContext


class AsyncService:
    def __init__(self, result):
        self.result = result

    async def score(self, request):
        return self.result

    async def score_batch(self, requests):
        return self.result


class WeatherContextStub:
    def __init__(self, result):
        self.result = result

    async def get_context(self, **kwargs):
        return self.result


def attraction(**overrides):
    values = {
        "id": 1, "district_id": 1, "latitude": 6.0, "longitude": 80.0,
        "opening_hours": None,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def weather_context(**overrides):
    values = {
        "district_id": 1, "travel_date": date(2027, 1, 1), "reference_date": date(2026, 12, 30),
        "days_ahead": 2, "selected_source": "live_api", "actual_source": "openweathermap",
        "available": True, "resolution": "three_hourly_aggregated", "latitude": 6.0, "longitude": 80.0,
        "rainfall_mm": 0, "rainfall_period": "available_3h_intervals",
        "temperature_min_c": 23, "temperature_max_c": 28, "precipitation_probability_max": 0,
        "provenance": {"generated_at_utc": "2026-12-30T00:00:00Z"}, "message": "available",
    }
    values.update(overrides)
    return UnifiedWeatherContext(**values)


@pytest.mark.asyncio
async def test_weather_requires_activity_without_inference():
    adapter = WeatherAdapter.__new__(WeatherAdapter)
    result = await adapter.score_batch([attraction()], date(2027, 1, 1), None)
    assert result[1].status is EvidenceStatus.NOT_AVAILABLE
    assert result[1].score is None


@pytest.mark.asyncio
async def test_weather_requires_verified_district():
    adapter = WeatherAdapter.__new__(WeatherAdapter)
    result = await adapter.score_batch([attraction(district_id=None)], date(2027, 1, 1), "hiking")
    assert result[1].missing_data_indicators == ["district_id"]


@pytest.mark.asyncio
async def test_live_weather_is_scored_with_provenance():
    adapter = WeatherAdapter.__new__(WeatherAdapter)
    adapter.context_service = WeatherContextStub(weather_context())
    from app.weather_model.context_scoring.weather_suitability import WeatherSuitabilityEngine
    adapter.scorer = WeatherSuitabilityEngine()
    result = (await adapter.score_batch([attraction()], date(2027, 1, 1), "hiking"))[1]
    assert result.status is EvidenceStatus.AVAILABLE
    assert result.score is not None
    assert result.source == "openweathermap"


@pytest.mark.asyncio
async def test_climatology_is_not_misrepresented_as_weather_forecast():
    adapter = WeatherAdapter.__new__(WeatherAdapter)
    adapter.context_service = WeatherContextStub(weather_context(
        selected_source="climatology", actual_source="historical_climatology",
        resolution="calendar_month", days_ahead=400,
    ))
    result = (await adapter.score_batch([attraction()], date(2027, 1, 1), "hiking"))[1]
    assert result.status is EvidenceStatus.NOT_AVAILABLE
    assert result.score is None
    assert "not used as a date-specific weather forecast" in result.limitations[0]


@pytest.mark.asyncio
async def test_unavailable_weather_remains_null():
    adapter = WeatherAdapter.__new__(WeatherAdapter)
    adapter.context_service = WeatherContextStub(weather_context(available=False, resolution="unavailable"))
    result = (await adapter.score_batch([attraction()], date(2027, 1, 1), "beach"))[1]
    assert result.score is None


@pytest.mark.asyncio
async def test_missing_opening_hours_are_unknown_not_open():
    result = (await TimeOfDayAdapter().score_batch(
        [attraction()], datetime(2027, 1, 1, 8, tzinfo=timezone.utc), 60
    ))[1]
    assert result.status is EvidenceStatus.NOT_AVAILABLE
    assert result.details["opening_status"] == "UNKNOWN"


@pytest.mark.asyncio
async def test_seasonality_without_activity_id_is_unavailable():
    adapter = SeasonalityAdapter.__new__(SeasonalityAdapter)
    result = await adapter.score_batch([1, 2], None, date(2027, 1, 1))
    assert all(item.status is EvidenceStatus.NOT_AVAILABLE for item in result.values())
    assert all(item.score is None for item in result.values())


@pytest.mark.asyncio
async def test_holiday_adapter_preserves_missing_evidence():
    score = SimpleNamespace(
        attraction_id=1, context_suitability_score=None, context_confidence="INSUFFICIENT_EVIDENCE",
        evidence_sources=[], explanation="No eligible evidence.", uncertainty_flags=[],
        missing_features=["holiday"], model_dump=lambda **kwargs: {},
    )
    response = SimpleNamespace(scores=[score], scoring_version="test_v1")
    adapter = HolidayEventAdapter.__new__(HolidayEventAdapter)
    adapter.service = AsyncService(response)
    result = (await adapter.score_batch([1], date(2027, 1, 1), []))[1]
    assert result.status is EvidenceStatus.NOT_AVAILABLE
    assert result.score is None


@pytest.mark.asyncio
async def test_holiday_adapter_maps_only_real_service_score():
    score = SimpleNamespace(
        attraction_id=1, context_suitability_score=.7, context_confidence="MEDIUM",
        evidence_sources=["calendar"], explanation="Verified evidence.", uncertainty_flags=[],
        missing_features=[], model_dump=lambda **kwargs: {"context_suitability_score": .7},
    )
    response = SimpleNamespace(scores=[score], scoring_version="test_v1")
    adapter = HolidayEventAdapter.__new__(HolidayEventAdapter)
    adapter.service = AsyncService(response)
    result = (await adapter.score_batch([1], date(2027, 1, 1), []))[1]
    assert result.status is EvidenceStatus.AVAILABLE
    assert result.score == .7
    assert result.confidence == .65
