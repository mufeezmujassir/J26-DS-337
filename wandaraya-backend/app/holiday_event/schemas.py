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
    description: str | None = None
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
    original_category: str | None = None
    start_datetime: datetime | None = None
    end_datetime: datetime | None = None
    timezone: str = "Asia/Colombo"
    venue: str | None = None
    address: str | None = None
    city: str | None = None
    province: str | None = None
    location_confidence: Literal["verified", "source_explicit", "unresolved"] = "unresolved"
    district_id: int | None = None
    organizer: str | None = None
    event_url: str | None = None
    registration_url: str | None = None
    ticket_url: str | None = None
    price_information: str | None = None
    currency: str | None = None
    is_free: bool | None = None
    event_notes: str | None = None
    hashtags: list[str] = Field(default_factory=list)
    status: EventStatus = "unknown"
    source_url: str
    source_updated_at: datetime | None = None
    extraction_method: Literal["deterministic", "llm_assisted"] = "deterministic"
    extraction_confidence: float | None = Field(default=None, ge=0, le=1)
    extraction_evidence: dict[str, str] = Field(default_factory=dict)


class LLMEventField(BaseModel):
    value: str | None = None
    evidence: str | None = None


class LLMEventExtraction(BaseModel):
    title: LLMEventField = Field(default_factory=LLMEventField)
    description: LLMEventField = Field(default_factory=LLMEventField)
    start_date: LLMEventField = Field(default_factory=LLMEventField)
    end_date: LLMEventField = Field(default_factory=LLMEventField)
    start_time: LLMEventField = Field(default_factory=LLMEventField)
    end_time: LLMEventField = Field(default_factory=LLMEventField)
    venue: LLMEventField = Field(default_factory=LLMEventField)
    city: LLMEventField = Field(default_factory=LLMEventField)
    district: LLMEventField = Field(default_factory=LLMEventField)
    province: LLMEventField = Field(default_factory=LLMEventField)
    organizer: LLMEventField = Field(default_factory=LLMEventField)
    category: LLMEventField = Field(default_factory=LLMEventField)
    ticket_information: LLMEventField = Field(default_factory=LLMEventField)
    registration_url: LLMEventField = Field(default_factory=LLMEventField)
    hashtags: LLMEventField = Field(default_factory=LLMEventField)


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
