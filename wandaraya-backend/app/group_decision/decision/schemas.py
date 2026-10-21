"""Decision Engine Schemas.

Imports PreferenceRecord from src.conflict.schemas and defines DecisionResult.
"""

from __future__ import annotations

from typing import Any
from pydantic import BaseModel, Field

# Re-use PreferenceRecord from conflict module as required
from app.group_decision.conflict.schemas import EmotionSignal, PreferenceRecord

__all__ = [
    "PreferenceRecord",
    "EmotionSignal",
    "DecisionResult",
    "ConflictSummary",
    "ConsensusCategoryResult",
    "ConsensusResult",
]


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
    method: str = Field(..., description="Decision method name ('majority', 'preference_only', 'weighted', or 'weighted_minority')")
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
    primary_option: str | None = Field(
        default=None,
        description="Primary winning option from base decision method",
    )
    protected_members: list[dict[str, Any]] = Field(
        default_factory=list,
        description="List of uncovered members eligible for minority protection with strengths",
    )
    plan: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Compromise plan skeleton of {slot, item, reason}",
    )
    covered_members: list[str] = Field(
        default_factory=list,
        description="List of group members who have at least one liked item in the plan",
    )
    uncovered_members: list[dict[str, Any]] = Field(
        default_factory=list,
        description="List of eligible members who could not be covered with reasons",
    )
    protection_applied: bool = Field(
        default=False,
        description="True if minority protection items were added to the plan",
    )
    resolved_conflicts: list[dict[str, Any]] = Field(
        default_factory=list,
        description="List of soft conflicts resolved by the compromise plan",
    )
    unresolved_conflicts: list[dict[str, Any]] = Field(
        default_factory=list,
        description="List of conflicts remaining unresolved",
    )
    unresolved_rejection: list[dict[str, Any]] = Field(
        default_factory=list,
        description="List of members who rejected an item that is included in the plan",
    )
    explanation: list[str] = Field(
        default_factory=list,
        description="Structured plain-text summary lines",
    )
    metrics: dict[str, Any] = Field(
        default_factory=dict,
        description="Comparative metrics {coverage_before, coverage_after, min_satisfaction_before, min_satisfaction_after, plan_size}",
    )

    def to_dict(self) -> dict[str, Any]:
        """Convert decision result to dictionary."""
        return self.model_dump()


class ConflictSummary(BaseModel):
    """Structured summary of conflict counts and rejections for a category."""

    resolved_soft: int = Field(default=0, description="Count of resolved soft conflicts")
    unresolved_soft: int = Field(default=0, description="Count of unresolved soft conflicts")
    unresolved_hard: int = Field(default=0, description="Count of unresolved hard conflicts")
    unresolved_rejection_members: list[str] = Field(
        default_factory=list,
        description="Members who rejected an item included in the plan",
    )


class ConsensusCategoryResult(BaseModel):
    """Consensus and fairness metrics for a single category."""

    category: str = Field(..., description="Category name (e.g. 'Destination', 'Activity')")
    primary_option: str | None = Field(default=None, description="Primary chosen option")
    plan_items: list[str] = Field(default_factory=list, description="Items evaluated in the plan")
    mean_acceptance: float = Field(default=0.0, description="Mean member acceptance")
    min_acceptance: float = Field(default=0.0, description="Minimum member acceptance")
    consensus_level: float = Field(default=0.0, description="Overall consensus score [0.0, 1.0]")
    level_label: str = Field(default="low", description="'high', 'medium', or 'low'")
    consensus_reached: bool = Field(default=False, description="Whether consensus threshold is reached")
    consensus_primary_only: float = Field(default=0.0, description="Consensus score for primary option alone")
    consensus_gain: float = Field(default=0.0, description="consensus_level minus consensus_primary_only")
    satisfaction_gap: float = Field(default=0.0, description="Max minus min member acceptance")
    gini: float = Field(default=0.0, description="Gini coefficient of member acceptance")
    is_tie: bool = Field(default=False, description="True if top options tied")
    tied_options: list[str] = Field(default_factory=list, description="List of tied option names")
    has_majority: bool = Field(default=False, description="True if primary winner received majority")
    member_acceptance: dict[str, float] = Field(
        default_factory=dict,
        description="Mapping of member name to acceptance score",
    )
    trivial_single_member: bool = Field(default=False, description="True if only 1 member in group")
    conflict_summary: dict[str, Any] = Field(
        default_factory=dict,
        description="Summary of {resolved_soft, unresolved_soft, unresolved_hard, unresolved_rejection_members}",
    )
    notes: list[str] = Field(default_factory=list, description="Structured notes (no raw chat text)")

    def to_dict(self) -> dict[str, Any]:
        """Convert category consensus result to dictionary."""
        return self.model_dump()


class ConsensusResult(BaseModel):
    """Overall consensus outcome across all decided categories."""

    # Overall metrics
    overall_level: float = Field(default=0.0, description="Mean consensus level over decided categories")
    overall_min_level: float = Field(default=0.0, description="Minimum consensus level over decided categories")
    overall_label: str = Field(default="low", description="Overall qualitative label ('high', 'medium', 'low')")
    overall_reached: bool = Field(default=False, description="True if all decided categories reached consensus")
    categories_skipped: dict[str, str] = Field(
        default_factory=dict,
        description="Categories skipped with reason (e.g. {'Activity': 'no_positive_stance'})",
    )
    categories: dict[str, ConsensusCategoryResult] = Field(
        default_factory=dict,
        description="Per-category consensus results",
    )

    # Convenience mirrors of primary/first category for single-category evaluations
    primary_option: str | None = Field(default=None, description="Primary chosen option of main category")
    plan_items: list[str] = Field(default_factory=list, description="Items in evaluated plan")
    mean_acceptance: float = Field(default=0.0, description="Mean member acceptance")
    min_acceptance: float = Field(default=0.0, description="Minimum member acceptance")
    consensus_level: float = Field(default=0.0, description="Consensus level score [0.0, 1.0]")
    level_label: str = Field(default="low", description="Consensus qualitative label ('high', 'medium', 'low')")
    consensus_reached: bool = Field(default=False, description="True if consensus reached")
    consensus_primary_only: float = Field(default=0.0, description="Score for primary option alone")
    consensus_gain: float = Field(default=0.0, description="Consensus gain over primary option alone")
    satisfaction_gap: float = Field(default=0.0, description="Max minus min acceptance")
    gini: float = Field(default=0.0, description="Gini coefficient of member acceptances")
    is_tie: bool = Field(default=False, description="True if top options tied")
    tied_options: list[str] = Field(default_factory=list, description="Tied options list")
    has_majority: bool = Field(default=False, description="True if primary winner received majority")
    member_acceptance: dict[str, float] = Field(
        default_factory=dict,
        description="Mapping member name -> float acceptance score",
    )
    trivial_single_member: bool = Field(default=False, description="True if single member")
    conflict_summary: dict[str, Any] = Field(
        default_factory=dict,
        description="Conflict summary {resolved_soft, unresolved_soft, unresolved_hard, unresolved_rejection_members}",
    )
    notes: list[str] = Field(default_factory=list, description="Structured notes")

    @property
    def per_category(self) -> dict[str, ConsensusCategoryResult]:
        """Access per-category results dict."""
        return self.categories

    def to_dict(self) -> dict[str, Any]:
        """Convert overall consensus result to dictionary."""
        return self.model_dump()


