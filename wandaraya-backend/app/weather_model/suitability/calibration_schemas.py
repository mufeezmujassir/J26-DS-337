"""Typed input/output contracts for the experimental calibration layer."""

from pydantic import BaseModel, Field


class WeatherCalibrationInput(BaseModel):
    raw_weather_score: float | None = Field(default=None, ge=0, le=100)
    weather_source: str
    available: bool
    activity_coverage_ratio: float = Field(default=1.0, ge=0, le=1)
    missing_targets: list[str] = Field(default_factory=list)
    complete_24h_coverage: bool | None = None
    requires_additional_conditions: bool = False


class WeatherCalibrationResult(BaseModel):
    raw_weather_score: float | None
    ranking_weather_score: float | None
    evidence_quality: float = Field(ge=0, le=1)
    activity_coverage_ratio: float = Field(ge=0, le=1)
    evidence_level: str
    uncertainty_level: str
    requires_additional_conditions: bool
    ranking_eligible: bool
    calibration_version: str = "experimental_v1"
    limitations: list[str] = Field(default_factory=list)
