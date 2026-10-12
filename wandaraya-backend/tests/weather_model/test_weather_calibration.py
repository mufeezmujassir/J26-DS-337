import pytest

from app.weather_model.suitability.calibration_schemas import WeatherCalibrationInput
from app.weather_model.suitability.calibrator import WeatherSuitabilityCalibrator


@pytest.fixture
def calibrator():
    return WeatherSuitabilityCalibrator()


def test_complete_live_forecast_uses_live_quality(calibrator):
    result = calibrator.calibrate(
        WeatherCalibrationInput(
            raw_weather_score=66.05,
            weather_source="openweathermap",
            available=True,
            complete_24h_coverage=True,
        )
    )
    assert result.evidence_quality == 0.9
    assert result.ranking_weather_score == 64.44
    assert result.ranking_eligible is True


def test_climatology_shrinks_toward_neutral(calibrator):
    result = calibrator.calibrate(
        WeatherCalibrationInput(
            raw_weather_score=100.0,
            weather_source="historical_climatology",
            available=True,
        )
    )
    assert result.evidence_quality == 0.35
    assert result.ranking_weather_score == 67.5
    assert result.uncertainty_level == "high"


def test_missing_targets_reduce_evidence_quality(calibrator):
    result = calibrator.calibrate(
        WeatherCalibrationInput(
            raw_weather_score=100.0,
            weather_source="openweathermap",
            available=True,
            complete_24h_coverage=True,
            missing_targets=["rainfall_mm", "temperature_min_c"],
        )
    )
    assert result.evidence_quality == 0.66
    assert result.ranking_weather_score == 83.0


def test_activity_coverage_is_applied_separately(calibrator):
    result = calibrator.calibrate(
        WeatherCalibrationInput(
            raw_weather_score=100.0,
            weather_source="openweathermap",
            available=True,
            complete_24h_coverage=True,
            activity_coverage_ratio=0.5,
        )
    )
    assert result.evidence_quality == 0.9
    assert result.ranking_weather_score == 72.5
    assert "Some attraction activities" in result.limitations[0]


def test_unavailable_weather_is_not_ranked(calibrator):
    result = calibrator.calibrate(
        WeatherCalibrationInput(
            raw_weather_score=None,
            weather_source="monthly_forecast",
            available=False,
        )
    )
    assert result.ranking_weather_score is None
    assert result.ranking_eligible is False


def test_marine_activity_requires_extra_conditions(calibrator):
    result = calibrator.calibrate(
        WeatherCalibrationInput(
            raw_weather_score=90.0,
            weather_source="openweathermap",
            available=True,
            complete_24h_coverage=True,
            requires_additional_conditions=True,
        )
    )
    assert result.requires_additional_conditions is True
    assert result.ranking_eligible is False


def test_unknown_source_is_not_ranked(calibrator):
    result = calibrator.calibrate(
        WeatherCalibrationInput(
            raw_weather_score=75.0,
            weather_source="unknown_provider",
            available=True,
        )
    )
    assert result.ranking_weather_score is None
    assert result.ranking_eligible is False


def test_score_remains_within_bounds(calibrator):
    for score in (0.0, 25.0, 50.0, 75.0, 100.0):
        result = calibrator.calibrate(
            WeatherCalibrationInput(
                raw_weather_score=score,
                weather_source="openweathermap",
                available=True,
                complete_24h_coverage=True,
            )
        )
        assert result.ranking_weather_score is not None
        assert 0 <= result.ranking_weather_score <= 100
