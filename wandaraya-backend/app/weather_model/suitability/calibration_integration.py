"""Attach experimental calibration fields to attraction batch responses."""

from app.weather_model.suitability.attraction_schemas import (
    AttractionWeatherBatchResponse,
)
from app.weather_model.suitability.calibration_schemas import WeatherCalibrationInput
from app.weather_model.suitability.calibrator import WeatherSuitabilityCalibrator


def calibrate_attraction_response(
    response: AttractionWeatherBatchResponse,
) -> AttractionWeatherBatchResponse:
    calibrator = WeatherSuitabilityCalibrator()
    for attraction in response.results:
        provenance = attraction.provenance or {}
        result = calibrator.calibrate(
            WeatherCalibrationInput(
                raw_weather_score=attraction.weather_score,
                weather_source=attraction.weather_source,
                available=attraction.available,
                activity_coverage_ratio=attraction.activity_coverage_ratio,
                missing_targets=provenance.get("missing_targets", []),
                complete_24h_coverage=provenance.get("complete_24h_coverage"),
                requires_additional_conditions=attraction.requires_additional_conditions,
            )
        )
        attraction.ranking_weather_score = result.ranking_weather_score
        attraction.evidence_quality = result.evidence_quality
        attraction.uncertainty_level = result.uncertainty_level
        attraction.ranking_eligible = result.ranking_eligible
        attraction.calibration_version = result.calibration_version
        attraction.calibration_limitations = result.limitations
    return response
