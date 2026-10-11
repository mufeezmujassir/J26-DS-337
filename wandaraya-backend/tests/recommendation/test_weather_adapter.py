from types import SimpleNamespace

from app.recommendation.context_dimensions.weather_adapter import (
    WeatherDimensionAdapter,
)


def make_attraction(**overrides):
    data = {
        "attraction_id": 1,
        "ranking_weather_score": 64.44,
        "weather_score": 66.05,
        "evidence_quality": 0.9,
        "ranking_eligible": True,
        "available": True,
        "weather_source": "openweathermap",
        "calibration_version": "experimental_v1",
        "activity_coverage_ratio": 1.0,
        "uncertainty_level": "low",
        "weather_resolution": "three_hourly_aggregated",
        "requires_additional_conditions": False,
        "calibration_limitations": [],
    }
    data.update(overrides)
    return SimpleNamespace(**data)


def test_normalizes_weather_score():
    result = WeatherDimensionAdapter.transform(make_attraction())

    assert result.score == 0.6444
    assert result.confidence == 0.9
    assert result.dimension == "weather"
    assert result.eligible is True


def test_unavailable_weather_remains_missing():
    result = WeatherDimensionAdapter.transform(
        make_attraction(
            ranking_weather_score=None,
            weather_score=None,
            evidence_quality=0.0,
            ranking_eligible=False,
            available=False,
            weather_source="monthly_forecast",
        )
    )

    assert result.score is None
    assert result.eligible is False
    assert result.available is False


def test_marine_conditions_are_not_automatically_eligible():
    result = WeatherDimensionAdapter.transform(
        make_attraction(
            ranking_eligible=False,
            requires_additional_conditions=True,
        )
    )

    assert result.eligible is False
    assert result.metadata["requires_additional_conditions"] is True


def test_batch_preserves_attraction_identity():
    response = SimpleNamespace(
        results=[
            make_attraction(attraction_id=1),
            make_attraction(attraction_id=2, ranking_weather_score=75.0),
        ]
    )

    results = WeatherDimensionAdapter.transform_batch(response)

    assert len(results) == 2
    assert results[0].attraction_id == 1
    assert results[1].attraction_id == 2
    assert results[1].score == 0.75
