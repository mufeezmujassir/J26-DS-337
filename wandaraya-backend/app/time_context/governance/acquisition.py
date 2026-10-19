from __future__ import annotations

from typing import Protocol

from pydantic import BaseModel, Field

from app.time_context.governance.policy import TimingGovernancePolicy
from app.time_context.governance.schemas import RetentionStatus, TimingSourceEvidence
from app.time_context.schemas import TimingSourceType


class RateLimitConfiguration(BaseModel):
    requests_per_minute: int | None = Field(default=None, gt=0)
    retry_after_seconds: int | None = Field(default=None, ge=0)


class AcquisitionPlan(BaseModel):
    source_type: TimingSourceType
    discovery_authorised: bool = False
    fetch_authorised: bool = False
    persistence_authorised: bool = False
    requires_conflict_review: bool = True
    rate_limit: RateLimitConfiguration = Field(default_factory=RateLimitConfiguration)
    steps: tuple[str, ...] = ("discover", "fetch", "extract", "validate", "normalise", "reconcile", "review", "persist")


class FutureTimingConnector(Protocol):
    """Planning-only contract. Implementations require separate authorisation."""
    source_type: TimingSourceType
    def discover(self, attraction_id: int) -> object: ...
    def fetch(self, source_identifier: str) -> object: ...
    def extract(self, raw_payload: object) -> TimingSourceEvidence: ...


def plan_acquisition(source_type: TimingSourceType, policy: TimingGovernancePolicy | None) -> AcquisitionPlan:
    if policy is None or not policy.approved:
        return AcquisitionPlan(source_type=source_type)
    rule = policy.rule_for(source_type)
    if rule is None:
        return AcquisitionPlan(source_type=source_type)
    retention_ok = rule.retention_status is RetentionStatus.PERMITTED
    return AcquisitionPlan(source_type=source_type, discovery_authorised=rule.refresh_eligible,
        fetch_authorised=rule.refresh_eligible, persistence_authorised=retention_ok,
        requires_conflict_review=True)
