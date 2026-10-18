"""Contracts for Stage 10.0.2 semantic candidate weather enrichment.

These schemas deliberately keep semantic retrieval evidence and weather
evidence separate.  They are not a recommendation or re-ranking contract.
"""

from __future__ import annotations

from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.weather_model.suitability.attraction_schemas import ActivityWeatherScore


class ContextEnrichmentRequest(BaseModel):
    query: str = Field(min_length=2, max_length=500)
    travel_date: date
    top_k: int = Field(default=10, ge=1, le=50)
    forecast_mode: Literal["production", "planning"] = "production"


class SemanticRetrievalEvidence(BaseModel):
    score: float
    rank: int = Field(ge=1)
    source: str


class DescriptionProvenance(BaseModel):
    source: str | None = None
    source_url: str | None = None
    language: str | None = None
    content_hash: str | None = None


class CanonicalCandidateEnvelope(BaseModel):
    attraction_id: int
    attraction_name: str
    semantic: SemanticRetrievalEvidence
    district_id: int | None = None
    latitude: float | None = None
    longitude: float | None = None
    coordinate_source: Literal["attraction", "district_fallback", "unavailable"]
    coordinate_issue: str | None = None
    category_names: list[str] = Field(default_factory=list)
    activity_names: list[str] = Field(default_factory=list)
    supported_weather_profiles: list[str] = Field(default_factory=list)
    unsupported_activity_names: list[str] = Field(default_factory=list)
    description_provenance: list[DescriptionProvenance] = Field(default_factory=list)


class WeatherDimensionEvidence(BaseModel):
    dimension: Literal["weather"] = "weather"
    score: float | None = Field(default=None, ge=0, le=1)
    confidence: float = Field(ge=0, le=1)
    available: bool
    eligible: bool
    source: str | None = None
    version: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class WeatherContextEvidence(BaseModel):
    status: Literal["available", "unknown"]
    suitability_score: float | None = Field(default=None, ge=0, le=100)
    suitability: str
    confidence: str
    source: str | None = None
    resolution: str | None = None
    evidence_level: str = "unknown"
    message: str
    activity_scores: list[ActivityWeatherScore] = Field(default_factory=list)
    unsupported_activity_types: list[str] = Field(default_factory=list)
    risk_factors: list[str] = Field(default_factory=list)
    provenance: dict[str, Any] = Field(default_factory=dict)
    dimension: WeatherDimensionEvidence


class EnrichedSemanticCandidate(BaseModel):
    candidate: CanonicalCandidateEnvelope
    weather: WeatherContextEvidence


class ContextEnrichmentResponse(BaseModel):
    query: str
    travel_date: date
    forecast_mode: Literal["production", "planning"]
    retrieval_source: str
    candidates_retrieved: int = Field(ge=0)
    candidates_enriched: int = Field(ge=0)
    ranking_applied: Literal[False] = False
    candidates: list[EnrichedSemanticCandidate] = Field(default_factory=list)
