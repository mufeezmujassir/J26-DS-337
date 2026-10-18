"""Pydantic schemas for the Wandaraya dynamic replanning module."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Literal
from uuid import uuid4

from pydantic import BaseModel, Field

Vibe = Literal["relaxed", "active", "cultural", "mixed"]
Severity = Literal["step", "day", "plan"]
Decision = Literal["accepted", "rejected", "modified"]
NextAction = Literal["apply", "find_alternative"]

VIBES = ("relaxed", "active", "cultural", "mixed")
SEVERITIES = ("step", "day", "plan")
DECISIONS = ("accepted", "rejected", "modified")
NEXT_ACTIONS = ("apply", "find_alternative")


def _utc_now() -> datetime:
    """Return the current timezone-aware UTC timestamp."""

    return datetime.now(timezone.utc)


def _new_plan_id() -> str:
    """Return a fresh ``plan_<hex>`` identifier."""

    return f"plan_{uuid4().hex}"


class IntentAnchor(BaseModel):
    """The user's original travel intent, captured before any change."""

    user_id: str
    vibe: Vibe
    budget: float = Field(ge=0.0)
    confirmed_bookings: List[str] = Field(default_factory=list)
    must_see: List[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=_utc_now)


class AffectedElement(BaseModel):
    """The single itinerary element touched by a disruption."""

    activity_name: str
    time_slot: str = ""
    day: str = ""
    location: str = ""


class RevisedActivity(BaseModel):
    """A replacement activity proposed by the replanner."""

    activity_name: str
    time_slot: str = ""
    duration: str = ""
    reason: str = ""


class RevisedPlan(BaseModel):
    """The output of the Dynamic Replanning module."""

    plan_id: str = Field(default_factory=_new_plan_id)
    original_plan_id: str = ""
    disruption_id: str = ""
    severity: Severity
    affected_element: AffectedElement
    revised_activities: List[RevisedActivity] = Field(default_factory=list)
    preserved_elements: List[str] = Field(default_factory=list)
    requires_confirmation: bool = True
    created_at: datetime = Field(default_factory=_utc_now)


class TurnRecord(BaseModel):
    """One exchange between the user and the replanner."""

    turn_number: int = Field(ge=1)
    user_message: str = ""
    system_response: str = ""
    decision: Decision = "modified"
    timestamp: datetime = Field(default_factory=_utc_now)


class ConsistencyCheck(BaseModel):
    """The result of validating a proposed plan against the anchor."""

    consistent: bool
    reasons: List[str] = Field(default_factory=list)


class ConfirmationResult(BaseModel):
    """The user's decision on a proposed revised plan."""

    accepted: bool
    user_feedback: str = ""
    next_action: NextAction = "apply"


__all__ = [
    "VIBES",
    "SEVERITIES",
    "DECISIONS",
    "NEXT_ACTIONS",
    "Vibe",
    "Severity",
    "Decision",
    "NextAction",
    "IntentAnchor",
    "AffectedElement",
    "RevisedActivity",
    "RevisedPlan",
    "TurnRecord",
    "ConsistencyCheck",
    "ConfirmationResult",
]