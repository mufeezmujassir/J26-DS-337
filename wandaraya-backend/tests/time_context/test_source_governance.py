from datetime import date, datetime, time, timezone

import pytest

from app.time_context.governance.acquisition import plan_acquisition
from app.time_context.governance.policy import SourceGovernanceRule, TimingGovernancePolicy
from app.time_context.governance.reconciliation import reconcile_timing_evidence
from app.time_context.governance.sampling import PilotSamplingDesign, TimingPilotCandidate, select_pilot_sample
from app.time_context.governance.schemas import (
    GovernanceReasonCode, ReconciliationDecision, RetentionMetadata, RetentionStatus,
    ScheduleEvidenceType, SystemDerivedMetadata, TimingSourceEvidence, TimingSourceFacts,
)
from app.time_context.opening_hours.schemas import (
    GoogleWeekday, NormalizedOpeningInterval, NormalizedWeeklySchedule, ScheduleValidationStatus,
)
from app.time_context.schemas import FreshnessStatus, TimingEvidence, TimingSourceType, VerificationStatus


NOW = datetime(2026, 10, 14, tzinfo=timezone.utc)


def policy(*, exception_override=False):
    return TimingGovernancePolicy(
        policy_id="research-governance-v1", approved=True, max_age_days=30,
        source_rules=[SourceGovernanceRule(source_type=TimingSourceType.GOOGLE_PLACES, refresh_eligible=True,
            retention_status=RetentionStatus.PERMITTED, allows_verified_exception_override=exception_override),
        SourceGovernanceRule(source_type=TimingSourceType.OFFICIAL_OPERATOR, refresh_eligible=True,
            retention_status=RetentionStatus.PERMITTED)],
    )


def evidence(identifier="google-1", *, source=TimingSourceType.GOOGLE_PLACES, start=time(9), end=time(17),
             evidence_type=ScheduleEvidenceType.REGULAR_WEEKLY, attraction_id=78, verification=VerificationStatus.SOURCE_REPORTED,
             retained=RetentionStatus.PERMITTED, retrieved_at=NOW, effective_from=None, effective_until=None, schedule=True):
    normalized = None
    if schedule:
        normalized = NormalizedWeeklySchedule(attraction_id=attraction_id, validation_status=ScheduleValidationStatus.VALID,
            parser_version="fixture-v1", evidence=TimingEvidence(source_type=source), intervals=[NormalizedOpeningInterval(
                start_weekday=GoogleWeekday.MONDAY, start_local_time=start, end_weekday=GoogleWeekday.MONDAY,
                end_local_time=end)])
    return TimingSourceEvidence(evidence_id=identifier, source_facts=TimingSourceFacts(attraction_id=attraction_id,
        source_type=source, source_identifier=identifier, evidence_type=evidence_type, retrieved_at=retrieved_at,
        effective_from=effective_from, effective_until=effective_until, timezone="Asia/Colombo",
        retention=RetentionMetadata(status=retained, policy_reference="fixture-policy")), schedule=normalized,
        verification_status=verification, derived=SystemDerivedMetadata(parser_version="fixture-v1", freshness_status=FreshnessStatus.NOT_ASSESSED))


def test_existing_knowledge_base_source_is_a_supported_provenance_type():
    item = evidence("kb-1", source=TimingSourceType.EXISTING_KNOWLEDGE_BASE)
    assert item.source_facts.source_type == "existing_knowledge_base"


def test_source_facts_are_separate_from_annotations_and_derived_metadata():
    item = evidence()
    assert item.source_facts.retrieved_at == NOW
    assert item.annotations.note is None
    assert item.derived.parser_version == "fixture-v1"


def test_schedule_and_source_fact_identity_must_match():
    with pytest.raises(ValueError, match="attraction_id"):
        TimingSourceEvidence(evidence_id="bad", source_facts=TimingSourceFacts(attraction_id=1,
            source_type=TimingSourceType.GOOGLE_PLACES, evidence_type=ScheduleEvidenceType.REGULAR_WEEKLY),
            schedule=evidence().schedule)


def test_no_approved_policy_is_explicitly_unresolved():
    result = reconcile_timing_evidence([evidence(), evidence("official", source=TimingSourceType.OFFICIAL_OPERATOR)], None)
    assert result.decision is ReconciliationDecision.POLICY_UNRESOLVED
    assert result.reason_codes == [GovernanceReasonCode.POLICY_NOT_APPROVED]


def test_one_source_is_insufficient_evidence():
    result = reconcile_timing_evidence([evidence()], policy())
    assert result.decision is ReconciliationDecision.INSUFFICIENT_EVIDENCE


def test_identical_independent_schedules_agree_without_a_ranked_winner():
    result = reconcile_timing_evidence([evidence(), evidence("official", source=TimingSourceType.OFFICIAL_OPERATOR)], policy())
    assert result.decision is ReconciliationDecision.CONSISTENT
    assert result.selected_evidence_id is None
    assert GovernanceReasonCode.SOURCE_AGREEMENT in result.reason_codes


def test_different_regular_schedules_are_conflicting_and_not_silently_selected():
    result = reconcile_timing_evidence([evidence(), evidence("official", source=TimingSourceType.OFFICIAL_OPERATOR, end=time(18))], policy())
    assert result.decision is ReconciliationDecision.CONFLICTING
    assert result.selected_evidence_id is None
    assert GovernanceReasonCode.NO_AUTOMATIC_WINNER in result.reason_codes


def test_source_identity_mismatch_requires_review():
    result = reconcile_timing_evidence([evidence(), evidence("other", attraction_id=79)], policy())
    assert result.decision is ReconciliationDecision.REVIEW_REQUIRED
    assert GovernanceReasonCode.SOURCE_IDENTITY_MISMATCH in result.reason_codes


@pytest.mark.parametrize("retention", [RetentionStatus.UNKNOWN, RetentionStatus.REVIEW_REQUIRED, RetentionStatus.PROHIBITED])
def test_unknown_or_prohibited_retention_never_becomes_usable(retention):
    result = reconcile_timing_evidence([evidence(retained=retention), evidence("official", source=TimingSourceType.OFFICIAL_OPERATOR)], policy())
    assert result.decision is ReconciliationDecision.REVIEW_REQUIRED


def test_missing_provenance_requires_review():
    item = evidence()
    item.source_facts.source_identifier = None
    result = reconcile_timing_evidence([item, evidence("official", source=TimingSourceType.OFFICIAL_OPERATOR)], policy())
    assert GovernanceReasonCode.MISSING_PROVENANCE in result.reason_codes


def test_unknown_freshness_policy_requires_review_instead_of_assuming_current():
    no_threshold = TimingGovernancePolicy(policy_id="unbounded", approved=True, source_rules=policy().source_rules)
    result = reconcile_timing_evidence([evidence(), evidence("official", source=TimingSourceType.OFFICIAL_OPERATOR)], no_threshold)
    assert result.decision is ReconciliationDecision.REVIEW_REQUIRED
    assert GovernanceReasonCode.FRESHNESS_UNRESOLVED in result.reason_codes


def test_stale_evidence_requires_review():
    old = datetime(2020, 1, 1, tzinfo=timezone.utc)
    result = reconcile_timing_evidence([evidence(retrieved_at=old), evidence("official", source=TimingSourceType.OFFICIAL_OPERATOR)], policy())
    assert GovernanceReasonCode.STALE_EVIDENCE in result.reason_codes


def test_non_overlapping_effective_periods_require_review_not_schedule_conflict():
    first = evidence(effective_from=date(2026, 1, 1), effective_until=date(2026, 1, 31))
    second = evidence("official", source=TimingSourceType.OFFICIAL_OPERATOR,
        effective_from=date(2026, 2, 1), effective_until=date(2026, 2, 28))
    result = reconcile_timing_evidence([first, second], policy())
    assert result.decision is ReconciliationDecision.REVIEW_REQUIRED
    assert GovernanceReasonCode.EFFECTIVE_DATES_DO_NOT_OVERLAP in result.reason_codes


def test_a_policy_can_require_verification_without_assigning_a_source_rank():
    guarded = policy()
    guarded.source_rules[0].requires_verification = True
    result = reconcile_timing_evidence([evidence(verification=VerificationStatus.UNVERIFIED), evidence("official", source=TimingSourceType.OFFICIAL_OPERATOR)], guarded)
    assert GovernanceReasonCode.VERIFICATION_REQUIRED in result.reason_codes


def test_unknown_or_missing_schedule_requires_review_not_a_predicted_schedule():
    result = reconcile_timing_evidence([evidence(schedule=False), evidence("official", source=TimingSourceType.OFFICIAL_OPERATOR)], policy())
    assert result.decision is ReconciliationDecision.REVIEW_REQUIRED
    assert GovernanceReasonCode.UNKNOWN_SCHEDULE in result.reason_codes


def test_unverified_exception_cannot_override_regular_hours():
    exception = evidence("exception", evidence_type=ScheduleEvidenceType.DATE_SPECIFIC_EXCEPTION,
        effective_from=date(2026, 10, 20), effective_until=date(2026, 10, 20), verification=VerificationStatus.SOURCE_REPORTED)
    result = reconcile_timing_evidence([exception, evidence("regular", source=TimingSourceType.OFFICIAL_OPERATOR)], policy(exception_override=True), on_date=date(2026, 10, 20))
    assert result.decision is ReconciliationDecision.REVIEW_REQUIRED
    assert result.selected_evidence_id is None


def test_verified_applicable_exception_can_override_only_when_policy_authorises_it():
    exception = evidence("exception", evidence_type=ScheduleEvidenceType.DATE_SPECIFIC_EXCEPTION,
        effective_from=date(2026, 10, 20), effective_until=date(2026, 10, 20), verification=VerificationStatus.MANUALLY_VERIFIED)
    result = reconcile_timing_evidence([exception, evidence("regular", source=TimingSourceType.OFFICIAL_OPERATOR)], policy(exception_override=True), on_date=date(2026, 10, 20))
    assert result.decision is ReconciliationDecision.CONSISTENT
    assert result.selected_evidence_id == "exception"


def test_exception_outside_effective_date_is_not_selected():
    exception = evidence("exception", evidence_type=ScheduleEvidenceType.DATE_SPECIFIC_EXCEPTION,
        effective_from=date(2026, 10, 20), effective_until=date(2026, 10, 20), verification=VerificationStatus.MANUALLY_VERIFIED)
    result = reconcile_timing_evidence([exception, evidence("regular", source=TimingSourceType.OFFICIAL_OPERATOR)], policy(exception_override=True), on_date=date(2026, 10, 21))
    assert result.decision is ReconciliationDecision.REVIEW_REQUIRED
    assert result.selected_evidence_id is None


def test_acquisition_is_disabled_without_an_approved_policy():
    plan = plan_acquisition(TimingSourceType.GOOGLE_PLACES, None)
    assert not plan.fetch_authorised and not plan.persistence_authorised


def test_acquisition_uses_explicit_policy_not_hidden_source_ranking():
    plan = plan_acquisition(TimingSourceType.GOOGLE_PLACES, policy())
    assert plan.discovery_authorised and plan.fetch_authorised and plan.persistence_authorised
    assert plan.requires_conflict_review


def test_sampling_is_seeded_deterministic_and_preserves_unknown_strata():
    candidates = [TimingPilotCandidate(attraction_id=n, district_id=78 if n < 4 else 79, category="heritage",
        managed_status="managed", hours_status="missing" if n % 2 else "valid", source_status="kb") for n in range(1, 7)]
    design = PilotSamplingDesign(seed=42, per_stratum=1)
    assert select_pilot_sample(candidates, design) == select_pilot_sample(candidates, design)
    assert all(item.attraction_id in range(1, 7) for item in select_pilot_sample(candidates, design))


def test_reconciliation_does_not_mutate_input_evidence():
    records = [evidence(), evidence("official", source=TimingSourceType.OFFICIAL_OPERATOR, end=time(18))]
    original = [item.model_dump(mode="json") for item in records]
    reconcile_timing_evidence(records, policy())
    assert [item.model_dump(mode="json") for item in records] == original
