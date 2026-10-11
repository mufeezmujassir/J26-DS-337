"""Conservative, explainable shrinkage of raw weather suitability scores."""

from app.weather_model.suitability.calibration_config import (
    DEFAULT_CALIBRATION,
    CalibrationConfig,
)
from app.weather_model.suitability.calibration_schemas import (
    WeatherCalibrationInput,
    WeatherCalibrationResult,
)


class WeatherSuitabilityCalibrator:
    """Experimental calibration, not a probability or a safety assessment."""

    def __init__(self, config: CalibrationConfig = DEFAULT_CALIBRATION):
        self.config = config

    def calibrate(self, data: WeatherCalibrationInput) -> WeatherCalibrationResult:
        if not data.available or data.raw_weather_score is None:
            return WeatherCalibrationResult(
                raw_weather_score=data.raw_weather_score,
                ranking_weather_score=None,
                evidence_quality=0.0,
                activity_coverage_ratio=data.activity_coverage_ratio,
                evidence_level="unavailable",
                uncertainty_level="unavailable",
                requires_additional_conditions=data.requires_additional_conditions,
                ranking_eligible=False,
                limitations=["Weather data is unavailable; no ranking score was produced."],
            )

        limitations: list[str] = []
        if data.weather_source == "openweathermap":
            quality = self.config.live_base_quality
            evidence_level = "short_term_forecast"
            uncertainty_level = "low"
            if data.complete_24h_coverage is not True:
                uncertainty_level = "moderate"
                limitations.append("Live forecast does not provide complete 24-hour coverage.")
        elif data.weather_source == "monthly_forecast":
            quality = self.config.monthly_base_quality
            evidence_level = "monthly_prediction"
            uncertainty_level = "moderate"
            limitations.append("Monthly predictions cannot describe day-specific conditions.")
        elif data.weather_source == "historical_climatology":
            quality = self.config.climatology_base_quality
            evidence_level = "seasonal_baseline"
            uncertainty_level = "high"
            limitations.append(
                "Historical climatology describes typical seasonal conditions, not daily weather."
            )
        else:
            return WeatherCalibrationResult(
                raw_weather_score=data.raw_weather_score,
                ranking_weather_score=None,
                evidence_quality=0.0,
                activity_coverage_ratio=data.activity_coverage_ratio,
                evidence_level="unknown",
                uncertainty_level="unavailable",
                requires_additional_conditions=data.requires_additional_conditions,
                ranking_eligible=False,
                limitations=["Unrecognized weather source."],
            )

        quality -= len(set(data.missing_targets)) * self.config.missing_target_penalty
        quality = max(0.0, min(1.0, quality))
        quality = round(quality, 4)

        if data.activity_coverage_ratio < 1.0:
            limitations.append("Some attraction activities were not scored.")
        if data.requires_additional_conditions:
            limitations.append("Additional activity-specific safety conditions must be checked.")

        # Coverage is distinct from weather evidence: it independently reduces
        # the influence of the raw attraction score in downstream ranking.
        effective_quality = quality * data.activity_coverage_ratio
        ranking_score = (
            effective_quality * data.raw_weather_score
            + (1.0 - effective_quality) * self.config.neutral_score
        )
        ranking_score = max(self.config.min_score, min(self.config.max_score, ranking_score))

        return WeatherCalibrationResult(
            raw_weather_score=data.raw_weather_score,
            ranking_weather_score=round(ranking_score, 2),
            evidence_quality=quality,
            activity_coverage_ratio=data.activity_coverage_ratio,
            evidence_level=evidence_level,
            uncertainty_level=uncertainty_level,
            requires_additional_conditions=data.requires_additional_conditions,
            ranking_eligible=not data.requires_additional_conditions,
            limitations=limitations,
        )
