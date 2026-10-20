"""Decision Engine Schemas.
"""

from __future__ import annotations

from typing import Any
from pydantic import BaseModel, Field

# Re-use PreferenceRecord from conflict module as required
from app.group_decision.conflict.schemas import EmotionSignal, PreferenceRecord

__all__ = ["PreferenceRecord", "EmotionSignal", "DecisionResult"]


class DecisionResult(BaseModel):
    """Schema representing the outcome of a decision method for a category."""

    category: str = Field(..., description="Decision category ('Destination' or 'Activity')")
    chosen_option: str | None = Field(
        default=None,
        description="Selected winning option (or None if no positive preference exists)",
    )
    ranking: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Ranked list of options, e.g. [{'option': str, 'score': float}]",
    )
    scores: dict[str, float] = Field(
        default_factory=dict,
        description="Mapping of each candidate option to its computed score",
    )
    is_tie: bool = Field(
        default=False,
        description="True if multiple options tied for the top score",
    )
    tied_options: list[str] = Field(
        default_factory=list,
        description="List of options tied for the top score (empty if no tie)",
    )
    has_majority: bool = Field(
        default=False,
        description="True if winner's share of total votes is strictly above 0.5",
    )
    method: str = Field(..., description="Decision method name ('majority', 'preference_only', or 'weighted')")
    config: dict[str, Any] = Field(
        default_factory=dict,
        description="Configuration parameters used during decision execution",
    )
    reason: str | None = Field(
        default=None,
        description="Explanation when chosen_option is None or an edge case occurred",
    )
    contributions: list[dict[str, Any]] = Field(
        default_factory=list,
        description="List of per-record/member contributions {member, option, stance, emotion, intensity, agreement, weight, contribution, reason}",
    )
    outcome_changed_vs_preference_only: bool = Field(
        default=False,
        description="Flag indicating if chosen_option changed compared to preference-only aggregation",
    )

    def to_dict(self) -> dict[str, Any]:
        """Convert decision result to dictionary."""
        return self.model_dump()
