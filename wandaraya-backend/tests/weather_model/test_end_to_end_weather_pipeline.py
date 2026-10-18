"""Stage 9.8.12 controlled end-to-end weather-context checks."""

from __future__ import annotations

import asyncio
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from app.recommendation.context_dimensions.weather_context_contract import to_weather_context_dimension
from app.weather_model.context.live_weather_client import LiveWeatherClient
from app.weather_model.context.schemas import LiveWeatherDay, LiveWeatherResult
from app.weather_model.context.weather_context_service import WeatherContextService
from app.weather_model.context_scoring.schemas import AttractionWeatherRequest, WeatherConditions
from app.weather_model.context_scoring.weather_suitability import WeatherSuitabilityEngine
from app.weather_model.forecasting.forecast_service import ForecastService
from app.weather_model.validation import end_to_end_report


class _ControlledLiveClient:
    def __init__(self, result: LiveWeatherResult) -> None:
        self.result = result

    def get_forecast(self, **_kwargs: object) -> LiveWeatherResult:
        return self.result


def _live_result(*, available: bool = True) -> LiveWeatherResult:
    return LiveWeatherResult(
        latitude=6.0535,
        longitude=80.2210,
        requested_date=date(2026, 10, 13),
        available=available,
        generated_at_utc=datetime(2026, 10, 12, tzinfo=timezone.utc),
        forecast=LiveWeatherDay(
            date=date(2026, 10, 13), temperature_min_c=24.0, temperature_max_c=30.0,
            precipitation_mm_forecast=22.0, max_precipitation_probability=0.8,
            forecast_intervals=8,
        ) if available else None,
        message="controlled provider response" if available else "controlled provider failure",
    )


def test_controlled_live_provider_to_context_score_to_reranker_contract() -> None:
    """Exercise provider routing, suitability rules, and the independent contract."""
    service = WeatherContextService(live_client=_ControlledLiveClient(_live_result()))
    context = asyncio.run(service.get_context(
        district_id=78, travel_date=date(2026, 10, 13), reference_date=date(2026, 10, 12),
        latitude=6.0535, longitude=80.2210,
    ))
    weather = WeatherConditions(
        status="available" if context.available else "unavailable", source=context.actual_source,
        resolution=context.resolution, reliability_level="live_provider" if context.available else "unavailable",
        rainfall_mm=context.rainfall_mm, rainfall_period=context.rainfall_period,
        precipitation_probability=context.precipitation_probability_max,
        temperature_min_c=context.temperature_min_c, temperature_max_c=context.temperature_max_c,
    )
    score = WeatherSuitabilityEngine().score(AttractionWeatherRequest(
        attraction_id=102, activity="hiking", travel_date=context.travel_date, weather=weather,
    ))
    dimension = to_weather_context_dimension(score)

    assert context.actual_source == "openweathermap"
    assert context.resolution == "three_hourly_aggregated"
    assert score.status == "available"
    assert score.suitability_score is not None and score.suitability_score < 1
    assert dimension.dimension == "weather"
    assert dimension.score == score.suitability_score
    assert dimension.eligible is True
    assert dimension.contract_version == "weather-context-v1"


@pytest.mark.parametrize("activity", ["hiking", "beach", "wildlife_safari", "heritage_site", "water_activities", "indoor_attraction"])
def test_all_required_activity_categories_receive_deterministic_daily_weather_scores(activity: str) -> None:
    score = WeatherSuitabilityEngine().score(AttractionWeatherRequest(
        attraction_id=101,
        activity=activity,
        travel_date=date(2026, 10, 13),
        weather=WeatherConditions(
            status="available", source="fixture", resolution="daily", reliability_level="live_provider",
            rainfall_mm=30.0, rainfall_period="daily", precipitation_probability=0.8,
            temperature_min_c=24.0, temperature_max_c=31.0,
        ),
    ))
    assert score.status == "available"
    assert score.suitability_score is not None
    assert 0 <= score.suitability_score <= 1


def test_provider_failure_stays_unknown_through_the_reranker_contract() -> None:
    service = WeatherContextService(live_client=_ControlledLiveClient(_live_result(available=False)))
    context = asyncio.run(service.get_context(
        district_id=78, travel_date=date(2026, 10, 13), reference_date=date(2026, 10, 12),
        latitude=6.0535, longitude=80.2210,
    ))
    score = WeatherSuitabilityEngine().score(AttractionWeatherRequest(
        attraction_id=102, activity="beach", travel_date=context.travel_date,
        weather=WeatherConditions(status="unavailable"),
    ))
    dimension = to_weather_context_dimension(score)
    assert context.available is False
    assert score.status == "unknown" and score.suitability_score is None
    assert dimension.available is False and dimension.score is None and dimension.eligible is False


def test_reliability_service_enforces_the_five_day_live_horizon() -> None:
    client = _ControlledLiveClient(_live_result())
    service = ForecastService(Path("does-not-exist.json"), client)  # No approved model can be loaded.
    live = service.get_forecast(
        district_id=78, target="rainfall_mm", forecast_date=date(2026, 10, 13),
        reference_date=date(2026, 10, 12), latitude=6.0535, longitude=80.2210,
    )
    beyond = service.get_forecast(
        district_id=78, target="rainfall_mm", forecast_date=date(2026, 10, 18),
        reference_date=date(2026, 10, 12), latitude=6.0535, longitude=80.2210,
    )
    assert live.status == "available" and live.source == "openweathermap"
    assert beyond.status == "unavailable"
    assert "requested_date_outside_live_provider_horizon" in beyond.reliability.reason


def test_validation_report_never_claims_airflow_task_execution(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    root = tmp_path
    (root / "data/weather/artifacts/candidates").mkdir(parents=True)
    (root / "data/weather/reports/registry").mkdir(parents=True)
    (root / "data/weather/reports/backtesting").mkdir(parents=True)
    (root / "dags").mkdir()
    for dag_id, filename, _schedule in end_to_end_report.DAG_SPECS:
        (root / "dags" / filename).write_text(
            f'@dag(dag_id="{dag_id}", is_paused_upon_creation=True)\n@task(retries=1, execution_timeout=x)',
            encoding="utf-8",
        )
    (root / "data/weather/reports/registry/weather_model_registry.json").write_text(
        '{"entries": [], "production_approved": false}', encoding="utf-8",
    )
    (root / "data/weather/reports/backtesting/district_coverage_audit.json").write_text("[]", encoding="utf-8")
    monkeypatch.setattr(end_to_end_report, "PROJECT_ROOT", root)
    monkeypatch.setattr(end_to_end_report, "REGISTRY_PATH", root / "data/weather/reports/registry/weather_model_registry.json")
    monkeypatch.setattr(end_to_end_report, "COVERAGE_PATH", root / "data/weather/reports/backtesting/district_coverage_audit.json")
    report = end_to_end_report.build_report()
    assert report["readiness"] == "conditionally_ready"
    assert all(item["task_execution_status"] == "not_claimed_by_static_validation" for item in report["airflow_dags"])
