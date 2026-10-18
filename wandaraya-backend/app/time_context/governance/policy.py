from __future__ import annotations

from datetime import date, datetime, timezone

from pydantic import BaseModel, Field

from app.time_context.governance.schemas import RetentionStatus
from app.time_context.schemas import TimingSourceType, VerificationStatus


class SourceGovernanceRule(BaseModel):
    source_type: TimingSourceType
    refresh_eligible: bool = False
    retention_status: RetentionStatus = RetentionStatus.UNKNOWN
    requires_verification: bool = False
    allows_verified_exception_override: bool = False
    # Technical scope must be separately approved from source access.  Empty
    # means that no billable/provider field may be requested.
    permitted_field_scopes: set[str] = Field(default_factory=set)
    approved_domains: set[str] = Field(default_factory=set)
    robots_permission_confirmed: bool = False
    access_permission_confirmed: bool = False


class TimingGovernancePolicy(BaseModel):
    """A configuration contract, intentionally unapproved by default."""

    policy_id: str = Field(min_length=1)
    approved: bool = False
    source_rules: list[SourceGovernanceRule] = Field(default_factory=list)
    max_age_days: int | None = Field(default=None, ge=0)
    minimum_exception_verification: VerificationStatus = VerificationStatus.MANUALLY_VERIFIED

    def rule_for(self, source_type: TimingSourceType) -> SourceGovernanceRule | None:
        return next((rule for rule in self.source_rules if rule.source_type == source_type), None)


def evidence_freshness(retrieved_at: datetime | None, policy: TimingGovernancePolicy, now: datetime | None = None) -> str:
    """Returns current/stale/unresolved without inventing a policy threshold."""
    if policy.max_age_days is None or retrieved_at is None:
        return "unresolved"
    reference = now or datetime.now(timezone.utc)
    if retrieved_at.tzinfo is None:
        return "unresolved"
    return "current" if (reference - retrieved_at).days <= policy.max_age_days else "stale"


def evidence_applies_on(record_from: date | None, record_until: date | None, on_date: date | None) -> bool | None:
    if on_date is None:
        return None
    if record_from is None and record_until is None:
        return None
    return (record_from is None or record_from <= on_date) and (record_until is None or on_date <= record_until)
