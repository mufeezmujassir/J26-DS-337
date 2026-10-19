from __future__ import annotations

from datetime import datetime
from typing import Literal
from zoneinfo import ZoneInfo

from pydantic import Field, model_validator

from app.recommendation.content_based.schemas import ContentBasedRecommendationRequest, ContentBasedRecommendationItem


class TimeAwareRecommendationRequest(ContentBasedRecommendationRequest):
    visit_datetime: datetime
    visit_duration_minutes: int = Field(default=60, ge=1, le=720)
    strict_open_now: bool = False
    # A naive timestamp is only accepted when the caller explicitly chooses Sri
    # Lanka-local semantics; otherwise timezone ambiguity is rejected.
    assume_sri_lanka_local: bool = False
    time_weight: float = Field(default=0.35, ge=0, le=1)
    include_best_time_advisory: bool = True

    @model_validator(mode="after")
    def resolve_visit_timezone(self) -> "TimeAwareRecommendationRequest":
        if self.visit_datetime.tzinfo is None or self.visit_datetime.utcoffset() is None:
            if not self.assume_sri_lanka_local:
                raise ValueError("visit_datetime must include an explicit timezone, or set assume_sri_lanka_local=true.")
            self.visit_datetime = self.visit_datetime.replace(tzinfo=ZoneInfo("Asia/Colombo"))
        return self


class TimeContextEvidenceItem(ContentBasedRecommendationItem):
    opening_status: Literal["OPEN", "CLOSED", "UNKNOWN"]
    visit_window_status: Literal["FITS", "INSUFFICIENT_TIME", "UNKNOWN"]
    time_suitability_score: float | None = Field(default=None, ge=0, le=1)
    time_context_confidence: Literal["high", "medium", "low", "unavailable"]
    time_evidence_source: str
    time_evidence_freshness: str | None = None
    time_explanation: str
    time_unavailable_dimensions: list[str] = Field(default_factory=list)
    final_experimental_score: float = Field(ge=0, le=1)
    best_time_advisory: dict | None = None


from pydantic import BaseModel


class TimeAwareResponse(BaseModel):
    visit_datetime_local: datetime
    visit_duration_minutes: int
    strict_open_now: bool
    candidates_from_content_baseline: int
    candidates_after_time_constraint: int
    recommendations: list[TimeContextEvidenceItem]
    unknown_hours_policy: str = "unknown_is_not_closure_and_is_not_penalized"
    scope: str = "Experimental time-of-day layer only; weather, holidays, seasonality, and group emotion are excluded."
