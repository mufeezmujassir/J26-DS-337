from app.time_context.governance.adapters import (
    AdapterDecision, GOOGLE_TIMING_FIELDS, GooglePlacesTimingAdapter, OfficialOperatorConfig,
    OfficialOperatorTimingAdapter, OpenStreetMapTimingAdapter,
)
from app.time_context.governance.pipeline import assess_offline_acquisition
from app.time_context.governance.pilot_manifest import build_planned_manifest
from app.time_context.governance.policy import SourceGovernanceRule, TimingGovernancePolicy
from app.time_context.governance.schemas import RetentionStatus
from app.time_context.governance.sampling import PilotSamplingDesign, TimingPilotCandidate
from app.time_context.schemas import TimingSourceType


def approved_policy(*sources):
    return TimingGovernancePolicy(policy_id="gate-1-fixture", approved=True, max_age_days=30, source_rules=[
        SourceGovernanceRule(source_type=source, refresh_eligible=True, retention_status=RetentionStatus.PERMITTED,
            permitted_field_scopes=set(GOOGLE_TIMING_FIELDS) if source is TimingSourceType.GOOGLE_PLACES else set())
        for source in sources
    ])


def google_payload(**extra):
    return {"id": "place-1", "regularOpeningHours": {"periods": [{"open": {"day": 1, "hour": 9, "minute": 0}, "close": {"day": 1, "hour": 17, "minute": 0}}]}, **extra}


def test_google_field_mask_is_minimal_and_contains_no_credential():
    result = GooglePlacesTimingAdapter().prepare_request(attraction_id=1, place_id="place-1", policy=approved_policy(TimingSourceType.GOOGLE_PLACES))
    assert result.decision is AdapterDecision.READY_FOR_MOCK_VALIDATION
    assert set(result.reason_codes[0].split(",")) == GOOGLE_TIMING_FIELDS
    assert result.request_metadata["url_path"] == "/places/place-1"
    assert "key" not in result.reason_codes[0].lower()


def test_google_missing_id_unauthorised_scope_identity_and_missing_hours_are_explicit():
    adapter = GooglePlacesTimingAdapter()
    policy = approved_policy(TimingSourceType.GOOGLE_PLACES)
    assert adapter.prepare_request(attraction_id=1, place_id=None, policy=policy).decision is AdapterDecision.INVALID_RESPONSE
    assert adapter.prepare_request(attraction_id=1, place_id="p", policy=None).decision is AdapterDecision.UNAUTHORISED
    assert adapter.validate_fixture(attraction_id=1, place_id="place-1", payload={"id": "other"}, policy=policy).decision is AdapterDecision.IDENTITY_MISMATCH
    missing = adapter.validate_fixture(attraction_id=1, place_id="place-1", payload={"id": "place-1"}, policy=policy)
    assert missing.schedule.validation_status.value == "missing"


def test_google_current_hours_are_not_future_date_schedule_evidence():
    result = GooglePlacesTimingAdapter().validate_fixture(attraction_id=1, place_id="place-1", payload=google_payload(currentOpeningHours={"openNow": True}), policy=approved_policy(TimingSourceType.GOOGLE_PLACES))
    assert result.decision is AdapterDecision.READY_FOR_MOCK_VALIDATION
    assert "currentOpeningHours ignored" in result.warnings[0]


def test_google_unapproved_billing_scope_and_unknown_retention_fail_closed():
    scope = TimingGovernancePolicy(policy_id="scope", approved=True, source_rules=[SourceGovernanceRule(source_type=TimingSourceType.GOOGLE_PLACES, refresh_eligible=True, retention_status=RetentionStatus.PERMITTED)])
    assert GooglePlacesTimingAdapter().prepare_request(attraction_id=1, place_id="p", policy=scope).decision is AdapterDecision.UNAUTHORISED
    unknown = approved_policy(TimingSourceType.GOOGLE_PLACES)
    unknown.source_rules[0].retention_status = RetentionStatus.UNKNOWN
    assert GooglePlacesTimingAdapter().prepare_request(attraction_id=1, place_id="p", policy=unknown).acquisition_plan.persistence_authorised is False


def test_official_adapter_enforces_allowlist_permissions_and_json_ld_fixture():
    adapter = OfficialOperatorTimingAdapter(); policy = approved_policy(TimingSourceType.OFFICIAL_OPERATOR)
    config = OfficialOperatorConfig(source_url="https://operator.example/hours", approved_domains={"operator.example"}, approved_urls={"https://operator.example/hours"}, robots_permission_confirmed=True, access_permission_confirmed=True)
    payload = {"attraction_id": 1, "source_id": "official-1", "openingHoursSpecification": {"dayOfWeek": "Monday", "opens": "09:00", "closes": "17:00"}}
    assert adapter.validate_fixture(attraction_id=1, config=config, payload=payload, policy=policy).decision is AdapterDecision.READY_FOR_MOCK_VALIDATION
    config.approved_urls = set()
    assert adapter.validate_fixture(attraction_id=1, config=config, payload=payload, policy=policy).decision is AdapterDecision.UNAUTHORISED


def test_official_invalid_data_and_identity_mismatch_are_rejected():
    config = OfficialOperatorConfig(source_url="https://operator.example/hours", approved_domains={"operator.example"}, approved_urls={"https://operator.example/hours"}, robots_permission_confirmed=True, access_permission_confirmed=True)
    adapter = OfficialOperatorTimingAdapter(); policy = approved_policy(TimingSourceType.OFFICIAL_OPERATOR)
    assert adapter.validate_fixture(attraction_id=1, config=config, payload={"attraction_id": 2}, policy=policy).decision is AdapterDecision.IDENTITY_MISMATCH
    assert adapter.validate_fixture(attraction_id=1, config=config, payload={"attraction_id": 1, "openingHoursSpecification": "free text"}, policy=policy).decision is AdapterDecision.UNSUPPORTED


def test_osm_preserves_identity_attribution_and_marks_grammar_unsupported():
    policy = approved_policy(TimingSourceType.OPENSTREETMAP)
    result = OpenStreetMapTimingAdapter().validate_fixture(attraction_id=1, element={"type": "node", "id": 77, "tags": {"opening_hours": "Mo-Fr 09:00-17:00"}}, policy=policy)
    assert result.decision is AdapterDecision.UNSUPPORTED
    assert result.evidence.source_facts.source_identifier == "node/77"
    assert "ODbL" in result.evidence.source_facts.source_reference


def test_shared_pipeline_never_persists_and_does_not_choose_conflicting_sources():
    google = GooglePlacesTimingAdapter().validate_fixture(attraction_id=1, place_id="place-1", payload=google_payload(), policy=approved_policy(TimingSourceType.GOOGLE_PLACES))
    assessment = assess_offline_acquisition([google], approved_policy(TimingSourceType.GOOGLE_PLACES))
    assert assessment.persistence_eligible is False
    assert assessment.reconciliation.decision.value == "insufficient_evidence"


def test_pilot_manifest_reuses_seeded_sampling_and_keeps_authorisation_disabled():
    candidates = [TimingPilotCandidate(attraction_id=1, district_id=78, category="heritage", hours_status="valid", source_status="google"), TimingPilotCandidate(attraction_id=2, district_id=79, category="nature", hours_status="missing", source_status="google")]
    entries = build_planned_manifest(candidates, PilotSamplingDesign(seed=1013, per_stratum=1), intended_source="google_places")
    assert [entry.attraction_id for entry in entries] == [1, 2]
    assert all(entry.authorization_status == "not_authorised_for_fetch_or_persistence" for entry in entries)
