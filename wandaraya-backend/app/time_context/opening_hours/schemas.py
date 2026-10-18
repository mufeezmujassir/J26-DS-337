

from __future__ import annotations

from datetime import datetime, time
from enum import IntEnum, StrEnum

from pydantic import BaseModel, Field, model_validator

from app.time_context.schemas import TimingEvidence


class GoogleWeekday(IntEnum):
    SUNDAY = 0
    MONDAY = 1
    TUESDAY = 2
    WEDNESDAY = 3
    THURSDAY = 4
    FRIDAY = 5
    SATURDAY = 6


class IntervalType(StrEnum):
    REGULAR = "regular"
    OVERNIGHT = "overnight"
    ALWAYS_OPEN = "always_open"


class ScheduleValidationStatus(StrEnum):
    VALID = "valid"
    MISSING = "missing"
    MALFORMED = "malformed"
    AMBIGUOUS = "ambiguous"
    UNSUPPORTED = "unsupported"
    CONFLICTING = "conflicting"


class OpeningState(StrEnum):
    KNOWN_OPEN = "known_open"
    KNOWN_CLOSED = "known_closed"
    UNKNOWN = "unknown"


class OpeningReasonCode(StrEnum):
    SCHEDULE_VALID_REGULAR_WEEKLY_ONLY = "schedule_valid_regular_weekly_only"
    SCHEDULE_MISSING = "schedule_missing"
    SCHEDULE_MALFORMED = "schedule_malformed"
    SCHEDULE_AMBIGUOUS = "schedule_ambiguous"
    SCHEDULE_UNSUPPORTED = "schedule_unsupported"
    SCHEDULE_CONFLICTING = "schedule_conflicting"
    WITHIN_OPENING_INTERVAL = "within_opening_interval"
    OUTSIDE_OPENING_INTERVAL = "outside_opening_interval"
    DATE_EXCEPTIONS_NOT_CHECKED = "date_exceptions_not_checked"
    NAIVE_DATETIME_REJECTED = "naive_datetime_rejected"


class NormalizedOpeningInterval(BaseModel):
    start_weekday: GoogleWeekday
    start_local_time: time
    end_weekday: GoogleWeekday | None = None
    end_local_time: time | None = None
    overnight: bool = False
    interval_type: IntervalType = IntervalType.REGULAR
    source_reference: str | None = None

    @model_validator(mode="after")
    def validate_interval(self) -> "NormalizedOpeningInterval":
        if self.interval_type is IntervalType.ALWAYS_OPEN:
            if self.end_weekday is not None or self.end_local_time is not None:
                raise ValueError("always_open intervals cannot have an end")
            if self.start_weekday is not GoogleWeekday.SUNDAY or self.start_local_time != time(0, 0):
                raise ValueError("always_open must use Google Sunday 00:00 representation")
            return self
        if self.end_weekday is None or self.end_local_time is None:
            raise ValueError("regular and overnight intervals require an end")
        if self.overnight != (self.interval_type is IntervalType.OVERNIGHT):
            raise ValueError("overnight flag and interval_type must agree")
        return self


class NormalizedWeeklySchedule(BaseModel):
    attraction_id: int = Field(gt=0)
    timezone: str = "Asia/Colombo"
    intervals: list[NormalizedOpeningInterval] = Field(default_factory=list)
    source_type: str = "unknown"
    validation_status: ScheduleValidationStatus
    parser_version: str
    evidence: TimingEvidence
    warnings: list[str] = Field(default_factory=list)


class OpeningHoursEvaluation(BaseModel):
    attraction_id: int
    evaluated_local_datetime: datetime
    weekly_schedule_status: ScheduleValidationStatus
    state: OpeningState
    evidence_completeness: str
    reason_codes: list[OpeningReasonCode] = Field(default_factory=list)
    evidence: TimingEvidence
    explanation: str
