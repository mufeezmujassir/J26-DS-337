from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class TravelIntent(BaseModel):
    query: str = Field(min_length=2, max_length=500)
    destination_text: str | None = Field(default=None, max_length=120)
    travel_date: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    travel_time: str | None = Field(default=None, pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    travel_end_time: str | None = Field(default=None, pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    approximate_time_period: Literal["morning", "afternoon", "evening", "night"] | None = None
    requested_activities: list[str] = Field(default_factory=list, max_length=20)
    user_interests: list[str] = Field(default_factory=list, max_length=20)
    group_size: int | None = Field(default=None, ge=1, le=100)
    trip_duration_days: int | None = Field(default=None, ge=1, le=365)
    user_preferences: dict[str, Any] = Field(default_factory=dict)
    group_preferences: dict[str, Any] = Field(default_factory=dict)
    travel_constraints: dict[str, Any] = Field(default_factory=dict)
    explicit_restrictions: list[str] = Field(default_factory=list, max_length=20)
    extraction_method: Literal["deterministic", "langchain_structured", "hybrid"] = "deterministic"
