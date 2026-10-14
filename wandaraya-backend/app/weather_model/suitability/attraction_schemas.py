"""Contracts for batch attraction-level weather suitability evaluation."""

from __future__ import annotations

from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


class AttractionWeatherCandidate(BaseModel):
    attraction_id: int = Field(gt=0)
    name: str = Field(min_length=1)
    district_id: int = Field(gt=0)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    activity_types: list[str] = Field(min_length=1)
    # Set internally by the KB repository. Direct batch callers default to
    # attraction-level coordinates.
    coordinate_source: str = "attraction"

    @model_validator(mode="after")
    def validate_coordinates(self) -> "AttractionWeatherCandidate":
        if (self.latitude is None) != (self.longitude is None):
            raise ValueError(
                "Latitude and longitude must both be provided or both omitted."
            )
        return self


class AttractionWeatherBatchRequest(BaseModel):
    travel_date: date
    attractions: list[AttractionWeatherCandidate] = Field(min_length=1, max_length=50)
    forecast_mode: Literal["production", "planning"] = "production"


class ActivityWeatherScore(BaseModel):
    activity_type: str
    available: bool
    score: float | None = None
    suitability: str
    confidence: str
    risk_factors: list[str] = Field(default_factory=list)


class AttractionWeatherScore(BaseModel):
    attraction_id: int
    name: str
    district_id: int
    available: bool
    weather_score: float | None = None
    ranking_weather_score: float | None = None
    evidence_quality: float = 0.0
    uncertainty_level: str = "unavailable"
    ranking_eligible: bool = False
    calibration_version: str | None = None
    calibration_limitations: list[str] = Field(default_factory=list)
    suitability: str
    confidence: str
    activity_scores: list[ActivityWeatherScore] = Field(default_factory=list)
    total_activity_count: int = 0
    scored_activity_count: int = 0
    activity_coverage_ratio: float = 0.0
    coverage_status: str = "none"
    unsupported_activity_types: list[str] = Field(default_factory=list)
    weather_source: str
    weather_resolution: str
    weather_evidence_level: str = "unknown"
    requires_additional_conditions: bool = False
    missing_condition_types: list[str] = Field(default_factory=list)
    risk_factors: list[str] = Field(default_factory=list)
    provenance: dict[str, Any] = Field(default_factory=dict)
    message: str


class AttractionWeatherBatchResponse(BaseModel):
    travel_date: date
    total_attractions: int
    available_attractions: int
    unavailable_attractions: int
    results: list[AttractionWeatherScore]
