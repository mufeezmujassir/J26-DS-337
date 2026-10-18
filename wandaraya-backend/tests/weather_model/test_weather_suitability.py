from datetime import date

import pytest

from app.weather_model.suitability.schemas import WeatherSuitabilityInput
from app.weather_model.suitability.scorer import WeatherSuitabilityScorer


TRAVEL_DATE = date(2026, 10, 13)


def make_input(activity_type: str, **kwargs) -> WeatherSuitabilityInput:
    values = {
        "district_id": 78,
        "travel_date": TRAVEL_DATE,
        "activity_type": activity_type,
        "weather_source": "openweathermap",
        "rainfall_mm": 12.0,
        "rainfall_period": "available_3h_intervals",
        "temperature_min_c": 26.0,
        "temperature_max_c": 30.0,
        "precipitation_probability_max": 0.9,
    }
    values.update(kwargs)
    return WeatherSuitabilityInput(**values)


def test_hiking_is_more_weather_sensitive_than_museum():
    hiking = WeatherSuitabilityScorer.score(make_input("hiking"))
    museum = WeatherSuitabilityScorer.score(make_input("indoor_museum"))

    assert hiking.score < museum.score


def test_verified_galle_live_example_has_expected_baseline_scores():
    hiking = WeatherSuitabilityScorer.score(
        make_input(
            "hiking",
            rainfall_mm=2.19,
            temperature_min_c=26.9,
            temperature_max_c=30.23,
            precipitation_probability_max=0.98,
        )
    )
    museum = WeatherSuitabilityScorer.score(
        make_input(
            "indoor_museum",
            rainfall_mm=2.19,
            temperature_min_c=26.9,
            temperature_max_c=30.23,
            precipitation_probability_max=0.98,
        )
    )

    assert hiking.score == 56.42
    assert hiking.suitability == "Moderate"
    assert museum.score == 95.64
    assert museum.suitability == "Suitable"


def test_monthly_rainfall_is_not_used_as_daily_rainfall():
    result = WeatherSuitabilityScorer.score(
        make_input(
            "beach",
            weather_source="monthly_forecast",
            rainfall_mm=500.0,
            rainfall_period="calendar_month",
            precipitation_probability_max=None,
        )
    )

    assert result.score == 100.0
    assert "Monthly rainfall" in result.risk_factors[0]


def test_temperature_outside_ideal_range_reduces_score():
    result = WeatherSuitabilityScorer.score(
        make_input(
            "beach",
            rainfall_mm=None,
            precipitation_probability_max=None,
            temperature_min_c=18.0,
        )
    )

    assert result.score == 80.4
    assert result.suitability == "Suitable"


def test_unknown_activity_is_rejected():
    with pytest.raises(ValueError, match="Unsupported activity type"):
        WeatherSuitabilityScorer.score(make_input("skiing"))


def test_missing_weather_returns_no_score():
    result = WeatherSuitabilityScorer.score(
        make_input(
            "hiking",
            rainfall_mm=None,
            temperature_min_c=None,
            temperature_max_c=None,
            precipitation_probability_max=None,
        )
    )

    assert result.score is None
    assert result.confidence == "unavailable"
    assert result.suitability == "Unknown"
