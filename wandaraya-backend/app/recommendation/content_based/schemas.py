"""Public contracts for the Stage 12.1 content-based baseline.

The contract deliberately contains no weather, calendar, group-emotion, or
other contextual dimensions.  Those are separate layers, not hidden inputs to
this baseline.
"""

from __future__ import annotations

from pydantic import BaseModel, Field, model_validator


DEFAULT_SCORE_CONFIGURATION_VERSION = "content_baseline_v1"


class ContentBasedWeights(BaseModel):
    """Relative weights; unavailable metadata dimensions are re-normalized."""

    semantic: float = Field(default=0.60, ge=0)
    category: float = Field(default=0.20, ge=0)
    activity: float = Field(default=0.15, ge=0)
    district: float = Field(default=0.05, ge=0)

    @model_validator(mode="after")
    def has_positive_weight(self) -> "ContentBasedWeights":
        if self.semantic + self.category + self.activity + self.district <= 0:
            raise ValueError("At least one scoring weight must be greater than zero.")
        if self.semantic <= 0:
            raise ValueError("semantic weight must be greater than zero for this semantic baseline.")
        return self


class ContentBasedHardFilters(BaseModel):
    """Constraints which must be proven from stored attraction metadata.

    If a requested field is missing, the attraction is excluded.  This avoids
    treating unknown data as a match.
    """

    district_ids: list[int] = Field(default_factory=list, max_length=25)
    region_names: list[str] = Field(default_factory=list, max_length=25)
    category_names: list[str] = Field(default_factory=list, max_length=25)
    activity_names: list[str] = Field(default_factory=list, max_length=25)
    max_price_level: int | None = Field(default=None, ge=0, le=4)


class ContentBasedRecommendationRequest(BaseModel):
    interests: str = Field(min_length=2, max_length=500)
    preferred_categories: list[str] = Field(default_factory=list, max_length=25)
    preferred_activities: list[str] = Field(default_factory=list, max_length=25)
    preferred_district_ids: list[int] = Field(default_factory=list, max_length=25)
    preferred_regions: list[str] = Field(
        default_factory=list,
        max_length=25,
        description="Verified PostgreSQL district province names; this baseline does not infer regions.",
    )
    travel_style: str | None = Field(default=None, min_length=2, max_length=120)
    hard_filters: ContentBasedHardFilters = Field(default_factory=ContentBasedHardFilters)
    weights: ContentBasedWeights = Field(default_factory=ContentBasedWeights)
    limit: int = Field(default=10, ge=1, le=20)
    candidate_pool_size: int = Field(default=50, ge=1, le=100)

    @model_validator(mode="after")
    def candidate_pool_covers_result_limit(self) -> "ContentBasedRecommendationRequest":
        if self.candidate_pool_size < self.limit:
            raise ValueError("candidate_pool_size must be greater than or equal to limit.")
        return self


class ContentBasedRecommendationItem(BaseModel):
    attraction_id: int
    attraction_name: str
    district_id: int | None = None
    baseline_score: float = Field(ge=0, le=1)
    semantic_relevance_score: float = Field(ge=0, le=1)
    raw_semantic_similarity: float
    category_match_score: float | None = Field(default=None, ge=0, le=1)
    activity_match_score: float | None = Field(default=None, ge=0, le=1)
    district_match_score: float | None = Field(default=None, ge=0, le=1)
    region_match_score: float | None = Field(default=None, ge=0, le=1)
    applied_hard_filters: list[str] = Field(default_factory=list)
    matched_preference_evidence: dict[str, object] = Field(default_factory=dict)
    ranking_explanation: str
    score_configuration_version: str = DEFAULT_SCORE_CONFIGURATION_VERSION


class ContentBasedRecommendationResponse(BaseModel):
    interests: str
    retrieval_query: str
    retrieval_source: str = "qdrant_semantic_retriever"
    candidate_pool_requested: int
    candidates_retrieved: int
    candidates_after_hard_filters: int
    recommendations: list[ContentBasedRecommendationItem] = Field(default_factory=list)
    score_configuration_version: str = DEFAULT_SCORE_CONFIGURATION_VERSION
    scoring_policy: str = "shifted_cosine_and_available_metadata_weighted_average"
    excluded_candidate_counts: dict[str, int] = Field(default_factory=dict)
    baseline_scope: str = (
        "Semantic similarity and verified category/activity/district metadata only; "
        "weather, holiday, seasonality, time-of-day, group emotion, and itinerary "
        "optimization are not applied."
    )
