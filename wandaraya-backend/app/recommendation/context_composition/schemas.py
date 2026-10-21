from __future__ import annotations

from datetime import datetime
from typing import Literal
from pydantic import BaseModel, Field


class ContextDimensionEvidence(BaseModel):
    status: Literal["AVAILABLE", "UNAVAILABLE", "DISABLED", "NOT_AVAILABLE", "ERROR"]
    score: float | None = None
    provenance: dict = Field(default_factory=dict)
    limitations: list[str] = Field(default_factory=list)
    details: dict = Field(default_factory=dict)


class ExperimentalCandidateEvidenceBundle(BaseModel):
    attraction_id: int
    attraction_name: str
    original_semantic_rank: int
    semantic_score: float
    semantic: ContextDimensionEvidence
    time_of_day: ContextDimensionEvidence
    holiday_event: ContextDimensionEvidence
    historical_seasonality: ContextDimensionEvidence
    group_emotion: ContextDimensionEvidence


class ExperimentalContextCompositionResponse(BaseModel):
    query: str
    travel_datetime: datetime
    activity_type_id: int
    candidates: list[ExperimentalCandidateEvidenceBundle]
    original_candidate_order: list[int]
    returned_candidate_order: list[int]
    ranking_unchanged: bool
    production_ranking_changed: bool = False
    production_reranking_enabled: bool = False
    experimental: bool = True
    service_latency_ms: float
    seasonality_latency_ms: float
    seasonality_batch_query_count: int
    errors: list[str] = Field(default_factory=list)
    flags: dict = Field(default_factory=dict)
