from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from app.agents.recommendation_graph.schemas.intent import TravelIntent
from app.recommendation.unified_context.schemas import RerankerConfiguration, UnifiedRankedCandidate


class ItineraryStop(BaseModel):
    order: int = Field(ge=1)
    visit_date: str
    start_time: str
    end_time: str
    attraction_id: int
    attraction_name: str
    location: str | None = None
    description: str | None = None
    expected_behavior: str | None = None
    reason: str
    transfer_from_previous_minutes: int = Field(default=0, ge=0)
    transfer_note: str | None = None


class NotRecommendedPlace(BaseModel):
    attraction_id: int
    attraction_name: str
    location: str | None = None
    reason: str
    weather_summary: str


class AgenticRecommendationResponse(BaseModel):
    session_id: str
    request_id: str
    graph_status: Literal["CLARIFICATION_REQUIRED", "COMPLETED", "PARTIAL", "FAILED"]
    parsed_intent: TravelIntent | None = None
    clarification_required: bool = False
    clarification_question: str | None = None
    reranker_configuration: RerankerConfiguration
    recommendations: list[UnifiedRankedCandidate] = Field(default_factory=list)
    itinerary: list[ItineraryStop] = Field(default_factory=list)
    not_recommended: list[NotRecommendedPlace] = Field(default_factory=list)
    original_candidate_order: list[int] = Field(default_factory=list)
    experimental_candidate_order: list[int] = Field(default_factory=list)
    production_candidate_order: list[int] = Field(default_factory=list)
    missing_dimensions: dict[int, list[str]] = Field(default_factory=dict)
    human_readable_response: str | None = None
    errors: list[dict[str, Any]] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    nodes_executed: list[str] = Field(default_factory=list)
    tool_calls: list[str] = Field(default_factory=list)
    latency_ms: float = 0
    experimental: Literal[True] = True
    production_ranking_changed: Literal[False] = False
    group_emotion_status: Literal["DEFERRED_NOT_INTEGRATED"] = "DEFERRED_NOT_INTEGRATED"
    checkpoint_mode: Literal["development_in_memory"] = "development_in_memory"
