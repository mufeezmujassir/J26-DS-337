from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum
from typing import Any, Literal
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field, model_validator

ENGINE_VERSION = "stage12_5_unified_context_v1"
POLICY_VERSION = "stage12_5_four_layer_reranker_v1"
CONTEXT_DIMENSIONS = ("weather", "time_of_day", "holiday_event", "historical_seasonality")


class EvidenceStatus(StrEnum):
    AVAILABLE = "AVAILABLE"
    PARTIALLY_AVAILABLE = "PARTIALLY_AVAILABLE"
    NOT_AVAILABLE = "NOT_AVAILABLE"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    STALE = "STALE"
    ERROR = "ERROR"
    UNSUPPORTED = "UNSUPPORTED"


class RerankerConfiguration(StrEnum):
    R0 = "R0_SEMANTIC_BASELINE"
    R1 = "R1_AVAILABLE_CONTEXT_EQUAL_WEIGHT"
    R2 = "R2_EVIDENCE_QUALITY_AWARE"
    R3 = "R3_WEATHER_SEASONALITY_REDUNDANCY_CONTROLLED"


class SuppliedCandidate(BaseModel):
    attraction_id: int = Field(gt=0)
    attraction_name: str | None = Field(default=None, max_length=255)
    semantic_score: float = Field(ge=-1, le=1)
    semantic_rank: int | None = Field(default=None, ge=1)
    semantic_metadata: dict[str, Any] = Field(default_factory=dict)


class ContextEvidence(BaseModel):
    dimension: Literal["weather", "time_of_day", "holiday_event", "historical_seasonality"]
    status: EvidenceStatus
    score: float | None = Field(default=None, ge=0, le=1)
    confidence: float | None = Field(default=None, ge=0, le=1)
    confidence_label: str | None = None
    source: str | None = None
    source_version: str | None = None
    evaluated_at: datetime
    travel_date: date
    provenance: dict[str, Any] = Field(default_factory=dict)
    explanation: str
    limitations: list[str] = Field(default_factory=list)
    missing_data_indicators: list[str] = Field(default_factory=list)
    fallback_used: bool = False
    fallback_reason: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def missing_evidence_has_no_score(self) -> "ContextEvidence":
        if self.status not in {EvidenceStatus.AVAILABLE, EvidenceStatus.PARTIALLY_AVAILABLE} and self.score is not None:
            raise ValueError("Unavailable evidence cannot carry a score.")
        return self


class UnifiedContextRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str = Field(min_length=2, max_length=500)
    candidates: list[SuppliedCandidate] | None = Field(default=None, max_length=50)
    travel_datetime: datetime
    activity_type_id: int | None = Field(default=None, gt=0)
    requested_activities: list[str] = Field(default_factory=list, max_length=25)
    interests: list[str] = Field(default_factory=list, max_length=25)
    user_preferences: dict[str, Any] = Field(default_factory=dict)
    group_preferences: dict[str, Any] = Field(default_factory=dict)
    constraints: dict[str, Any] = Field(default_factory=dict)
    contextual_metadata: dict[str, Any] = Field(default_factory=dict)
    limit: int = Field(default=10, ge=1, le=50)
    candidate_pool_size: int = Field(default=30, ge=1, le=50)
    visit_duration_minutes: int = Field(default=60, ge=1, le=720)
    configuration: RerankerConfiguration = RerankerConfiguration.R3
    semantic_alpha: float = Field(default=0.65, gt=0, le=1)
    experimental_evaluation_mode: bool = True

    @model_validator(mode="after")
    def validate_request(self) -> "UnifiedContextRequest":
        if self.travel_datetime.tzinfo is None or self.travel_datetime.utcoffset() is None:
            raise ValueError("travel_datetime must include an explicit timezone.")
        self.travel_datetime = self.travel_datetime.astimezone(ZoneInfo("Asia/Colombo"))
        if self.candidate_pool_size < self.limit:
            raise ValueError("candidate_pool_size must be greater than or equal to limit.")
        if self.candidates:
            ids = [item.attraction_id for item in self.candidates]
            if len(ids) != len(set(ids)):
                raise ValueError("supplied candidate attraction IDs must be unique.")
            if len(ids) < self.limit:
                self.limit = len(ids)
        if "group_emotion" in self.contextual_metadata:
            raise ValueError("group_emotion is not supported in this version of the engine.")
        return self


class ContextContribution(BaseModel):
    dimension: str
    score: float
    effective_weight: float
    weighted_value: float
    evidence_status: EvidenceStatus


class CandidateExplanation(BaseModel):
    positive_factors: list[str] = Field(default_factory=list)
    negative_factors: list[str] = Field(default_factory=list)
    missing_dimensions: list[str] = Field(default_factory=list)
    evidence_sources: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    summary: str


class UnifiedRankedCandidate(BaseModel):
    attraction_id: int
    attraction_name: str
    original_semantic_score: float
    normalized_semantic_score: float = Field(ge=0, le=1)
    original_semantic_rank: int = Field(ge=1)
    final_experimental_context_score: float = Field(ge=0, le=1)
    experimental_rank: int = Field(ge=1)
    rank_movement: int
    context_score: float | None = Field(default=None, ge=0, le=1)
    evidence: dict[str, ContextEvidence]
    contributions: list[ContextContribution] = Field(default_factory=list)
    evidence_availability: dict[str, EvidenceStatus]
    source_provenance: dict[str, Any] = Field(default_factory=dict)
    confidence: float | None = Field(default=None, ge=0, le=1)
    limitations: list[str] = Field(default_factory=list)
    explanation: CandidateExplanation
    model_version: str = ENGINE_VERSION
    policy_version: str = POLICY_VERSION
    experimental_status: str = "EXPERIMENTAL_NOT_PRODUCTION_VALIDATED"


class LatencyBreakdown(BaseModel):
    semantic_retrieval_ms: float = 0
    candidate_hydration_ms: float = 0
    weather_ms: float = 0
    time_of_day_ms: float = 0
    holiday_event_ms: float = 0
    historical_seasonality_ms: float = 0
    reranking_ms: float = 0
    end_to_end_ms: float = 0


class UnifiedContextResponse(BaseModel):
    query: str
    travel_datetime: datetime
    configuration: RerankerConfiguration
    candidates: list[UnifiedRankedCandidate]
    original_candidate_order: list[int]
    experimental_candidate_order: list[int]
    production_candidate_order: list[int]
    production_ranking_changed: Literal[False] = False
    experimental: Literal[True] = True
    engine_version: str = ENGINE_VERSION
    context_layers_integrated: int = 4
    context_layers: list[str] = Field(default_factory=lambda: list(CONTEXT_DIMENSIONS))
    excluded_components: list[str] = Field(default_factory=lambda: ["group_emotion"])
    errors: list[dict[str, Any]] = Field(default_factory=list)
    latency: LatencyBreakdown = Field(default_factory=LatencyBreakdown)
    recommendation_accuracy_status: str = "UNIFIED_RANKING_ACCURACY_NOT_YET_VALIDATED"
    limitations: list[str] = Field(default_factory=lambda: [
        "Experimental ranking is not calibrated or independently validated.",
        "Group emotional intelligence is intentionally not integrated in this version.",
    ])
