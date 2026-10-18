"""Adapt calibrated weather suitability into a re-ranker dimension contract."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class WeatherDimensionResult:
    attraction_id: int
    dimension: str
    score: float | None
    confidence: float
    available: bool
    eligible: bool
    source: str
    version: str
    metadata: dict[str, Any]


class WeatherDimensionAdapter:
    """Pure transformation from Stage 9.6 output to a normalized dimension."""

    @staticmethod
    def transform(attraction: Any) -> WeatherDimensionResult:
        ranking_score = attraction.ranking_weather_score
        eligible = bool(attraction.ranking_eligible and ranking_score is not None)
        normalized_score = (
            round(ranking_score / 100.0, 4)
            if ranking_score is not None
            else None
        )

        return WeatherDimensionResult(
            attraction_id=attraction.attraction_id,
            dimension="weather",
            score=normalized_score,
            confidence=attraction.evidence_quality,
            available=attraction.available,
            eligible=eligible,
            source=attraction.weather_source,
            version=attraction.calibration_version or "unversioned",
            metadata={
                "raw_weather_score": attraction.weather_score,
                "activity_coverage_ratio": attraction.activity_coverage_ratio,
                "uncertainty_level": attraction.uncertainty_level,
                "weather_resolution": attraction.weather_resolution,
                "requires_additional_conditions": (
                    attraction.requires_additional_conditions
                ),
                "limitations": attraction.calibration_limitations,
            },
        )

    @classmethod
    def transform_batch(cls, response: Any) -> list[WeatherDimensionResult]:
        return [cls.transform(attraction) for attraction in response.results]
