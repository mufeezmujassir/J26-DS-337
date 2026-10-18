

from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, Field, field_validator, model_validator


class TimingSourceType(StrEnum):
    EXISTING_KNOWLEDGE_BASE = "existing_knowledge_base"
    GOOGLE_PLACES = "google_places"
    OFFICIAL_OPERATOR = "official_operator"
    OPENSTREETMAP = "openstreetmap"
    MANUAL_VERIFICATION = "manual_verification"
    UNKNOWN = "unknown"


class VerificationStatus(StrEnum):
    UNVERIFIED = "unverified"
    SOURCE_REPORTED = "source_reported"
    MANUALLY_VERIFIED = "manually_verified"
    CONFLICTING = "conflicting"
    UNKNOWN = "unknown"


class FreshnessStatus(StrEnum):
    CURRENT = "current"
    STALE = "stale"
    NOT_ASSESSED = "not_assessed"
    UNKNOWN = "unknown"


class TimingEvidence(BaseModel):
    """Source facts only; absent facts remain absent rather than estimated."""

    source_type: TimingSourceType = TimingSourceType.UNKNOWN
    source_identifier: str | None = None
    source_url: str | None = None
    retrieved_at: datetime | None = None
    effective_from: date | None = None
    effective_until: date | None = None
    verification_status: VerificationStatus = VerificationStatus.UNKNOWN
    freshness_status: FreshnessStatus = FreshnessStatus.NOT_ASSESSED
    limitations: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_effective_range(self) -> "TimingEvidence":
        if (
            self.effective_from is not None
            and self.effective_until is not None
            and self.effective_until < self.effective_from
        ):
            raise ValueError("effective_until must not precede effective_from")
        return self


class TimeContextRequest(BaseModel):
    attraction_id: int = Field(gt=0)
    planned_visit_at: datetime
    timezone: str = "Asia/Colombo"
    activity_identifier: str | None = Field(default=None, min_length=1, max_length=255)
    intended_visit_duration_minutes: int | None = Field(default=None, gt=0, le=1440)

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as exc:
            raise ValueError("timezone must be a valid IANA timezone") from exc
        return value

    @model_validator(mode="after")
    def validate_aware_visit_datetime(self) -> "TimeContextRequest":
        if self.planned_visit_at.tzinfo is None or self.planned_visit_at.utcoffset() is None:
            raise ValueError("planned_visit_at must be timezone-aware")
        return self
