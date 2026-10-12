"""Stable Weather Context Layer contract consumed by a future re-ranker.

This module deliberately performs no ranking.  It exposes the independently
calculated 0–1 weather dimension, including its availability and provenance,
so a later Context Re-Ranker can combine it with other dimensions explicitly.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from app.weather_model.context_scoring.schemas import AttractionWeatherScore


class WeatherContextDimension(BaseModel):
    attraction_id: int
    dimension: Literal["weather"] = "weather"
    available: bool
    eligible: bool
    score: float | None = Field(default=None, ge=0, le=1)
    level: str
    source: str | None = None
    resolution: str | None = None
    reliability_level: str
    explanation: str
    factors: list[dict] = Field(default_factory=list)
    contract_version: Literal["weather-context-v1"] = "weather-context-v1"


def to_weather_context_dimension(score: AttractionWeatherScore) -> WeatherContextDimension:
    """Adapt an explainable weather score without inventing a fallback score."""
    available = score.status == "available" and score.suitability_score is not None
    return WeatherContextDimension(
        attraction_id=score.attraction_id,
        available=available,
        eligible=available,
        score=score.suitability_score if available else None,
        level=score.suitability_level,
        source=score.forecast_source,
        resolution=score.weather_resolution,
        reliability_level=score.reliability_level,
        explanation=score.explanation,
        factors=[factor.model_dump(mode="json") for factor in score.factors],
    )
