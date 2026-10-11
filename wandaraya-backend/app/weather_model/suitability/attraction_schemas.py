"""Contracts for batch attraction-level weather suitability evaluation."""

from __future__ import annotations

from datetime import date
from typing import Any

from pydantic import BaseModel, Field, model_validator


class AttractionWeatherCandidate(BaseModel):
    attraction_id: int = Field(gt=0)
    name: str = Field(min_length=1)
    district_id: int = Field(gt=0)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    activity_types: list[str] = Field(min_length=1)

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
    suitability: str
    confidence: str
    activity_scores: list[ActivityWeatherScore] = Field(default_factory=list)
    scored_activity_count: int = 0
    unsupported_activity_types: list[str] = Field(default_factory=list)
    weather_source: str
    weather_resolution: str
    risk_factors: list[str] = Field(default_factory=list)
    provenance: dict[str, Any] = Field(default_factory=dict)
    message: str


class AttractionWeatherBatchResponse(BaseModel):
    travel_date: date
    total_attractions: int
    available_attractions: int
    unavailable_attractions: int
    results: list[AttractionWeatherScore]
