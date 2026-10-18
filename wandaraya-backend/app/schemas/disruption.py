"""Pydantic schemas for the Wandaraya disruption detection module."""

from __future__ import annotations

from datetime import datetime
from typing import List

from pydantic import BaseModel, Field

#: Allowed values for Disruption.source.
SOURCES = ("weather", "places", "complaint", "gps")

#: Allowed values for Disruption.category.
CATEGORIES = ("weather", "attraction", "transport", "user_report")

#: Allowed values for Disruption.severity, ordered weakest first.
SEVERITIES = ("step", "day", "plan")


class AffectedElement(BaseModel):
    """Itinerary element impacted by a disruption."""

    activity_name: str
    time_slot: str
    day: str
    location: str


class DisruptionReason(BaseModel):
    """Human-readable reason for a disruption."""

    short: str
    description: str
    details: str


class Disruption(BaseModel):
    """Structured disruption object consumed by the replanning pipeline."""

    disruption_id: str
    source: str
    category: str
    severity: str
    affected_element: AffectedElement
    reason: DisruptionReason
    confidence: float = Field(ge=0.0, le=1.0)
    requires_confirmation: bool
    detected_at: datetime


class DisruptionBatch(BaseModel):
    """Collection of disruptions detected in one pass."""

    disruptions: List[Disruption]
    detected_at: datetime


__all__ = [
    "SOURCES",
    "CATEGORIES",
    "SEVERITIES",
    "AffectedElement",
    "DisruptionReason",
    "Disruption",
    "DisruptionBatch",
]