"""Contracts shared by ingestion, APIs, and the holiday context scorer."""
from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field


ConfirmationStatus = Literal["tentative", "confirmed", "revised", "unknown"]
EventStatus = Literal["scheduled", "cancelled", "postponed", "unknown", "review_required"]


class HolidayRecord(BaseModel):
    holiday_date: date
    holiday_name: str = Field(min_length=1, max_length=255)
    holiday_type: str | None = None
    poya_name: str | None = None
    religious_category: str | None = None
    is_public_holiday: bool = False
    is_bank_holiday: bool | None = None
    is_mercantile_holiday: bool | None = None
    confirmation_status: ConfirmationStatus = "unknown"
    source_url: str
    source_updated_at: datetime | None = None
    source_record_id: str | None = None


class EventRecord(BaseModel):
    source_event_id: str
    title: str = Field(min_length=1, max_length=500)
    description: str | None = None
    category: str | None = None
    start_datetime: datetime | None = None
    end_datetime: datetime | None = None
    timezone: str = "Asia/Colombo"
    venue: str | None = None
    address: str | None = None
    city: str | None = None
    district_id: int | None = None
    organizer: str | None = None
    event_url: str | None = None
    registration_url: str | None = None
    price_information: str | None = None
    event_notes: str | None = None
    hashtags: list[str] = Field(default_factory=list)
    status: EventStatus = "unknown"
    source_url: str
    source_updated_at: datetime | None = None


class HolidayContextResponse(BaseModel):
    visit_datetime: datetime
    attraction_id: int | None = None
    holiday_context: list[dict]
    active_events: list[dict]
    cultural_relevance: float | None = None
    holiday_suitability_score: float | None = None
    evidence_confidence: Literal["high", "medium", "low", "unknown"]
    source_provenance: list[str]
    context_explanation: str
    limitations: list[str] = Field(default_factory=list)
