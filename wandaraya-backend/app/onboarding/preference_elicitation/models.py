"""Pydantic schemas for Progressive Preference Elicitation (PPE)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class PreferenceProfile(BaseModel):
    user_id: str
    group_type: Optional[str] = None
    trip_type: Optional[str] = None
    vibe: Optional[str] = None
    budget_per_day: Optional[float] = None
    duration_days: Optional[int] = None
    dates: Optional[Dict[str, Any]] = None
    departure_point: Optional[str] = None
    destination_shortlist: Optional[List[str]] = None
    is_complete: bool = False
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class ElicitationTurn(BaseModel):
    turn_number: int
    question: str
    user_answer: str
    extracted_fields: Dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class ElicitationState(BaseModel):
    user_id: str
    profile: PreferenceProfile
    missing_fields: List[str] = Field(default_factory=list)
    turns_used: int = 0
    max_turns: int = 5
    last_question: Optional[str] = None
    is_complete: bool = False


class ElicitationResponse(BaseModel):
    next_question: Optional[str] = None
    profile: PreferenceProfile
    is_complete: bool = False
    turns_used: int = 0
