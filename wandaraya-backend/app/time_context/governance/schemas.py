from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum

from pydantic import BaseModel, Field, model_validator

from app.time_context.opening_hours.schemas import NormalizedWeeklySchedule
from app.time_context.schemas import FreshnessStatus, TimingSourceType, VerificationStatus


class ScheduleEvidenceType(StrEnum):
    REGULAR_WEEKLY = "regular_weekly"
    DATE_SPECIFIC_EXCEPTION = "date_specific_exception"
    TEMPORARY_CLOSURE = "temporary_closure"
    LAST_ENTRY = "last_entry"
    UNSUPPORTED = "unsupported"


class RetentionStatus(StrEnum):
    PERMITTED = "permitted"
    PROHIBITED = "prohibited"
    UNKNOWN = "unknown"
    REVIEW_REQUIRED = "review_required"


class ReviewStatus(StrEnum):
    NOT_REVIEWED = "not_reviewed"
    REVIEW_REQUIRED = "review_required"
    REVIEWED = "reviewed"
    REJECTED = "rejected"


class ReconciliationDecision(StrEnum):
    CONSISTENT = "consistent"
    CONFLICTING = "conflicting"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    REVIEW_REQUIRED = "review_required"
    POLICY_UNRESOLVED = "policy_unresolved"


class GovernanceReasonCode(StrEnum):
    POLICY_NOT_APPROVED = "policy_not_approved"
    INSUFFICIENT_SOURCES = "insufficient_sources"
    SOURCE_IDENTITY_MISMATCH = "source_identity_mismatch"
    SOURCE_AGREEMENT = "source_agreement"
    DIRECT_SCHEDULE_CONFLICT = "direct_schedule_conflict"
    EFFECTIVE_DATES_DO_NOT_OVERLAP = "effective_dates_do_not_overlap"
    EFFECTIVE_DATE_UNKNOWN = "effective_date_unknown"
    EXCEPTION_NOT_APPLICABLE = "exception_not_applicable"
    EXCEPTION_NOT_VERIFIED = "exception_not_verified"
    EXCEPTION_OVERRIDE_AUTHORISED = "exception_override_authorised"
    MISSING_PROVENANCE = "missing_provenance"
    FRESHNESS_UNRESOLVED = "freshness_unresolved"
    STALE_EVIDENCE = "stale_evidence"
    VERIFICATION_REQUIRED = "verification_required"
    RETENTION_UNRESOLVED = "retention_unresolved"
    RETENTION_PROHIBITED = "retention_prohibited"
    UNSUPPORTED_SCHEDULE = "unsupported_schedule"
    UNKNOWN_SCHEDULE = "unknown_schedule"
    NO_AUTOMATIC_WINNER = "no_automatic_winner"


class SourceSpecificQuality(BaseModel):
    """Only source facts that are actually supplied; no inferred score."""

    place_version: str | None = None
    osm_object_version: int | None = Field(default=None, ge=1)
    official_publication_date: date | None = None
    manual_verification_reference: str | None = None


class RetentionMetadata(BaseModel):
    status: RetentionStatus = RetentionStatus.UNKNOWN
    policy_reference: str | None = None
    expires_at: datetime | None = None


class TimingSourceFacts(BaseModel):
    attraction_id: int = Field(gt=0)
    source_type: TimingSourceType
    source_identifier: str | None = None
    source_url: str | None = None
    evidence_type: ScheduleEvidenceType
    retrieved_at: datetime | None = None
    effective_from: date | None = None
    effective_until: date | None = None
    timezone: str | None = None
    source_reference: str | None = None
    quality: SourceSpecificQuality = Field(default_factory=SourceSpecificQuality)
    retention: RetentionMetadata = Field(default_factory=RetentionMetadata)

    @model_validator(mode="after")
    def validate_dates(self) -> "TimingSourceFacts":
        if self.effective_from and self.effective_until and self.effective_until < self.effective_from:
            raise ValueError("effective_until must not precede effective_from")
        return self


class ResearcherAnnotation(BaseModel):
    note: str | None = None
    review_status: ReviewStatus = ReviewStatus.NOT_REVIEWED
    reviewed_by_reference: str | None = None


class SystemDerivedMetadata(BaseModel):
    parser_version: str | None = None
    extraction_warnings: list[str] = Field(default_factory=list)
    freshness_status: FreshnessStatus = FreshnessStatus.NOT_ASSESSED


class TimingSourceEvidence(BaseModel):
    """Separates immutable source facts from researcher and system annotations."""

    evidence_id: str = Field(min_length=1, max_length=255)
    source_facts: TimingSourceFacts
    schedule: NormalizedWeeklySchedule | None = None
    verification_status: VerificationStatus = VerificationStatus.UNKNOWN
    annotations: ResearcherAnnotation = Field(default_factory=ResearcherAnnotation)
    derived: SystemDerivedMetadata = Field(default_factory=SystemDerivedMetadata)

    @model_validator(mode="after")
    def validate_schedule_identity(self) -> "TimingSourceEvidence":
        if self.schedule and self.schedule.attraction_id != self.source_facts.attraction_id:
            raise ValueError("schedule attraction_id must match source facts")
        return self


class TimingReconciliationResult(BaseModel):
    attraction_id: int
    decision: ReconciliationDecision
    reason_codes: list[GovernanceReasonCode] = Field(default_factory=list)
    considered_evidence_ids: list[str] = Field(default_factory=list)
    selected_evidence_id: str | None = None
    message: str
