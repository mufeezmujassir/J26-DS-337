from __future__ import annotations

import json
from datetime import date

from app.time_context.governance.policy import TimingGovernancePolicy, evidence_applies_on, evidence_freshness
from app.time_context.governance.schemas import (
    GovernanceReasonCode,
    ReconciliationDecision,
    RetentionStatus,
    ScheduleEvidenceType,
    TimingReconciliationResult,
    TimingSourceEvidence,
)
from app.time_context.opening_hours.schemas import ScheduleValidationStatus
from app.time_context.schemas import VerificationStatus


def _signature(record: TimingSourceEvidence) -> str | None:
    if record.schedule is None or record.schedule.validation_status is not ScheduleValidationStatus.VALID:
        return None
    # The normalised representation makes comparison deterministic and source-order independent.
    intervals = [item.model_dump(mode="json", exclude_none=True) for item in record.schedule.intervals]
    return json.dumps(sorted(intervals, key=lambda item: json.dumps(item, sort_keys=True)), sort_keys=True)


def _effective_ranges_overlap(records: list[TimingSourceEvidence]) -> bool:
    """Only compare bounded date claims; unbounded facts remain reviewable elsewhere."""
    bounded = [record.source_facts for record in records if record.source_facts.effective_from and record.source_facts.effective_until]
    if len(bounded) < 2:
        return True
    latest_start = max(record.effective_from for record in bounded)
    earliest_end = min(record.effective_until for record in bounded)
    return latest_start <= earliest_end


def reconcile_timing_evidence(
    records: list[TimingSourceEvidence], policy: TimingGovernancePolicy | None, *, on_date: date | None = None
) -> TimingReconciliationResult:
    """Compare offline evidence conservatively; never silently select a winner."""
    ids = [record.evidence_id for record in records]
    attraction_id = records[0].source_facts.attraction_id if records else 0
    if not policy or not policy.approved:
        return TimingReconciliationResult(attraction_id=attraction_id, decision=ReconciliationDecision.POLICY_UNRESOLVED,
            reason_codes=[GovernanceReasonCode.POLICY_NOT_APPROVED], considered_evidence_ids=ids,
            message="No approved timing-source governance policy is available.")
    if len(records) < 2:
        return TimingReconciliationResult(attraction_id=attraction_id, decision=ReconciliationDecision.INSUFFICIENT_EVIDENCE,
            reason_codes=[GovernanceReasonCode.INSUFFICIENT_SOURCES], considered_evidence_ids=ids,
            message="At least two evidence records are required for offline reconciliation.")
    if any(record.source_facts.attraction_id != attraction_id for record in records):
        return TimingReconciliationResult(attraction_id=attraction_id, decision=ReconciliationDecision.REVIEW_REQUIRED,
            reason_codes=[GovernanceReasonCode.SOURCE_IDENTITY_MISMATCH], considered_evidence_ids=ids,
            message="Evidence records identify different canonical attractions.")
    reasons: list[GovernanceReasonCode] = []
    for record in records:
        facts = record.source_facts
        rule = policy.rule_for(facts.source_type)
        if not facts.source_identifier and not facts.source_url and not facts.source_reference:
            reasons.append(GovernanceReasonCode.MISSING_PROVENANCE)
        if facts.retention.status in {RetentionStatus.UNKNOWN, RetentionStatus.REVIEW_REQUIRED}:
            reasons.append(GovernanceReasonCode.RETENTION_UNRESOLVED)
        if facts.retention.status is RetentionStatus.PROHIBITED:
            reasons.append(GovernanceReasonCode.RETENTION_PROHIBITED)
        if rule and rule.requires_verification and record.verification_status is VerificationStatus.UNVERIFIED:
            reasons.append(GovernanceReasonCode.VERIFICATION_REQUIRED)
        freshness = evidence_freshness(facts.retrieved_at, policy)
        if freshness == "unresolved": reasons.append(GovernanceReasonCode.FRESHNESS_UNRESOLVED)
        if freshness == "stale": reasons.append(GovernanceReasonCode.STALE_EVIDENCE)
        if _signature(record) is None:
            reasons.append(GovernanceReasonCode.UNSUPPORTED_SCHEDULE if facts.evidence_type is ScheduleEvidenceType.UNSUPPORTED else GovernanceReasonCode.UNKNOWN_SCHEDULE)
    if reasons:
        return TimingReconciliationResult(attraction_id=attraction_id, decision=ReconciliationDecision.REVIEW_REQUIRED,
            reason_codes=list(dict.fromkeys(reasons)), considered_evidence_ids=ids,
            message="Evidence cannot be reconciled until provenance, retention, freshness, and schedule completeness are reviewed.")
    if not _effective_ranges_overlap(records):
        return TimingReconciliationResult(attraction_id=attraction_id, decision=ReconciliationDecision.REVIEW_REQUIRED,
            reason_codes=[GovernanceReasonCode.EFFECTIVE_DATES_DO_NOT_OVERLAP, GovernanceReasonCode.NO_AUTOMATIC_WINNER],
            considered_evidence_ids=ids, message="Evidence records apply to non-overlapping effective periods.")

    exceptions = [r for r in records if r.source_facts.evidence_type is ScheduleEvidenceType.DATE_SPECIFIC_EXCEPTION]
    regular = [r for r in records if r.source_facts.evidence_type is ScheduleEvidenceType.REGULAR_WEEKLY]
    if exceptions and regular:
        exception = exceptions[0]
        rule = policy.rule_for(exception.source_facts.source_type)
        applicable = evidence_applies_on(exception.source_facts.effective_from, exception.source_facts.effective_until, on_date)
        verified = exception.verification_status is policy.minimum_exception_verification
        if rule and rule.allows_verified_exception_override and applicable and verified:
            return TimingReconciliationResult(attraction_id=attraction_id, decision=ReconciliationDecision.CONSISTENT,
                reason_codes=[GovernanceReasonCode.EXCEPTION_OVERRIDE_AUTHORISED], considered_evidence_ids=ids,
                selected_evidence_id=exception.evidence_id, message="A verified applicable exception is authorised by the approved policy.")
        reasons = [GovernanceReasonCode.EXCEPTION_NOT_APPLICABLE if not applicable else GovernanceReasonCode.EXCEPTION_NOT_VERIFIED,
                   GovernanceReasonCode.NO_AUTOMATIC_WINNER]
        return TimingReconciliationResult(attraction_id=attraction_id, decision=ReconciliationDecision.REVIEW_REQUIRED,
            reason_codes=reasons, considered_evidence_ids=ids, message="An exception cannot override regular hours without explicit applicable verified policy.")
    signatures = {_signature(record) for record in records}
    if len(signatures) == 1:
        return TimingReconciliationResult(attraction_id=attraction_id, decision=ReconciliationDecision.CONSISTENT,
            reason_codes=[GovernanceReasonCode.SOURCE_AGREEMENT], considered_evidence_ids=ids,
            message="Independent evidence records agree on the normalised schedule.")
    return TimingReconciliationResult(attraction_id=attraction_id, decision=ReconciliationDecision.CONFLICTING,
        reason_codes=[GovernanceReasonCode.DIRECT_SCHEDULE_CONFLICT, GovernanceReasonCode.NO_AUTOMATIC_WINNER],
        considered_evidence_ids=ids, message="Evidence schedules conflict; no source was selected automatically.")
