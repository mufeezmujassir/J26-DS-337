"""Offline-only source-specific timing adapter contracts.

The adapters validate fixtures and construct future request plans.  They do
not own credentials and deliberately contain no HTTP client or fetch method.
"""
from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from urllib.parse import urlparse

from pydantic import BaseModel, Field

from app.knowledge_base.processors.normalizer import AttractionNormalizer
from app.time_context.governance.acquisition import AcquisitionPlan, plan_acquisition
from app.time_context.governance.policy import TimingGovernancePolicy
from app.time_context.governance.schemas import (
    RetentionMetadata, ReviewStatus, ScheduleEvidenceType, SystemDerivedMetadata,
    TimingSourceEvidence, TimingSourceFacts,
)
from app.time_context.opening_hours.google_period_parser import normalize_google_regular_opening_hours
from app.time_context.opening_hours.schemas import NormalizedWeeklySchedule, ScheduleValidationStatus
from app.time_context.schemas import FreshnessStatus, TimingEvidence, TimingSourceType, VerificationStatus


GOOGLE_TIMING_FIELDS = frozenset({"id", "regularOpeningHours", "currentOpeningHours", "businessStatus"})
GOOGLE_TIMING_FIELD_MASK = ",".join(sorted(GOOGLE_TIMING_FIELDS))


class AdapterDecision(StrEnum):
    READY_FOR_MOCK_VALIDATION = "ready_for_mock_validation"
    UNAUTHORISED = "unauthorised"
    INVALID_RESPONSE = "invalid_response"
    IDENTITY_MISMATCH = "identity_mismatch"
    UNSUPPORTED = "unsupported"
    REVIEW_REQUIRED = "review_required"


class AdapterResult(BaseModel):
    decision: AdapterDecision
    evidence: TimingSourceEvidence | None = None
    schedule: NormalizedWeeklySchedule | None = None
    reason_codes: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    acquisition_plan: AcquisitionPlan | None = None
    request_metadata: dict[str, str] = Field(default_factory=dict)


class GoogleTimingRequest(BaseModel):
    attraction_id: int = Field(gt=0)
    place_id: str = Field(min_length=1)
    url_path: str
    field_mask: str = GOOGLE_TIMING_FIELD_MASK


class GooglePlacesTimingAdapter:
    source_type = TimingSourceType.GOOGLE_PLACES

    def prepare_request(self, *, attraction_id: int, place_id: str | None, policy: TimingGovernancePolicy | None) -> AdapterResult:
        plan = plan_acquisition(self.source_type, policy)
        if not place_id:
            return AdapterResult(decision=AdapterDecision.INVALID_RESPONSE, reason_codes=["missing_google_place_id"], acquisition_plan=plan)
        rule = policy.rule_for(self.source_type) if policy else None
        if not plan.fetch_authorised:
            return AdapterResult(decision=AdapterDecision.UNAUTHORISED, reason_codes=["fetch_not_authorised"], acquisition_plan=plan)
        if rule is None or not GOOGLE_TIMING_FIELDS.issubset(rule.permitted_field_scopes):
            return AdapterResult(decision=AdapterDecision.UNAUTHORISED, reason_codes=["timing_field_scope_or_billing_not_authorised"], acquisition_plan=plan)
        request = GoogleTimingRequest(attraction_id=attraction_id, place_id=place_id, url_path=f"/places/{place_id}")
        return AdapterResult(decision=AdapterDecision.READY_FOR_MOCK_VALIDATION, reason_codes=[request.field_mask], acquisition_plan=plan,
            request_metadata={"url_path": request.url_path, "field_mask": request.field_mask})

    def validate_fixture(self, *, attraction_id: int, place_id: str, payload: object, policy: TimingGovernancePolicy | None) -> AdapterResult:
        prepared = self.prepare_request(attraction_id=attraction_id, place_id=place_id, policy=policy)
        if prepared.decision is not AdapterDecision.READY_FOR_MOCK_VALIDATION:
            return prepared
        if not isinstance(payload, dict):
            return AdapterResult(decision=AdapterDecision.INVALID_RESPONSE, reason_codes=["provider_payload_not_object"], acquisition_plan=prepared.acquisition_plan)
        if payload.get("id") != place_id:
            return AdapterResult(decision=AdapterDecision.IDENTITY_MISMATCH, reason_codes=["provider_place_id_mismatch"], acquisition_plan=prepared.acquisition_plan)
        rule = policy.rule_for(self.source_type)  # policy was checked by prepare_request
        assert rule is not None
        normalized = AttractionNormalizer._normalize_opening_hours(payload.get("regularOpeningHours"))
        evidence = TimingEvidence(source_type=self.source_type, source_identifier=place_id,
            verification_status=VerificationStatus.SOURCE_REPORTED, freshness_status=FreshnessStatus.NOT_ASSESSED,
            limitations=["currentOpeningHours/openNow is retained as provider metadata and is not a future-date schedule fact."])
        schedule = normalize_google_regular_opening_hours(attraction_id=attraction_id, opening_hours=normalized, evidence=evidence)
        source_evidence = TimingSourceEvidence(evidence_id=f"google:{place_id}", source_facts=TimingSourceFacts(
            attraction_id=attraction_id, source_type=self.source_type, source_identifier=place_id,
            evidence_type=ScheduleEvidenceType.REGULAR_WEEKLY, timezone=payload.get("timeZone"),
            source_reference="Google Places API fixture", retention=RetentionMetadata(status=rule.retention_status)),
            schedule=schedule, verification_status=VerificationStatus.SOURCE_REPORTED,
            annotations={"review_status": ReviewStatus.NOT_REVIEWED},
            derived=SystemDerivedMetadata(parser_version=schedule.parser_version,
                extraction_warnings=["currentOpeningHours ignored for arbitrary future-date evaluation."] if "currentOpeningHours" in payload else []))
        decision = AdapterDecision.READY_FOR_MOCK_VALIDATION if schedule.validation_status is ScheduleValidationStatus.VALID else AdapterDecision.REVIEW_REQUIRED
        return AdapterResult(decision=decision, evidence=source_evidence, schedule=schedule,
            warnings=list(source_evidence.derived.extraction_warnings), acquisition_plan=prepared.acquisition_plan)


class OfficialOperatorConfig(BaseModel):
    source_url: str
    approved_domains: set[str] = Field(default_factory=set)
    approved_urls: set[str] = Field(default_factory=set)
    robots_permission_confirmed: bool = False
    access_permission_confirmed: bool = False
    extraction_method: str = "json_ld_openingHoursSpecification_v1"


class OfficialOperatorTimingAdapter:
    source_type = TimingSourceType.OFFICIAL_OPERATOR

    def validate_fixture(self, *, attraction_id: int, config: OfficialOperatorConfig, payload: object, policy: TimingGovernancePolicy | None) -> AdapterResult:
        plan = plan_acquisition(self.source_type, policy)
        parsed = urlparse(config.source_url)
        rule = policy.rule_for(self.source_type) if policy else None
        approved_domain = parsed.scheme == "https" and parsed.hostname in config.approved_domains and config.source_url in config.approved_urls
        if not plan.fetch_authorised or not approved_domain or not config.robots_permission_confirmed or not config.access_permission_confirmed:
            return AdapterResult(decision=AdapterDecision.UNAUTHORISED, reason_codes=["official_url_or_permission_not_authorised"], acquisition_plan=plan)
        if not isinstance(payload, dict) or payload.get("attraction_id", attraction_id) != attraction_id:
            return AdapterResult(decision=AdapterDecision.IDENTITY_MISMATCH, reason_codes=["official_source_identity_mismatch"], acquisition_plan=plan)
        specification = payload.get("openingHoursSpecification")
        periods = _official_specification_to_google_periods(specification)
        if periods is None:
            return AdapterResult(decision=AdapterDecision.UNSUPPORTED, reason_codes=["unsupported_or_invalid_official_structured_hours"], acquisition_plan=plan)
        assert rule is not None
        schedule = normalize_google_regular_opening_hours(attraction_id=attraction_id, opening_hours={"periods": periods},
            evidence=TimingEvidence(source_type=self.source_type, source_url=config.source_url, source_identifier=payload.get("source_id"), verification_status=VerificationStatus.SOURCE_REPORTED))
        record = TimingSourceEvidence(evidence_id=f"official:{payload.get('source_id', attraction_id)}", source_facts=TimingSourceFacts(
            attraction_id=attraction_id, source_type=self.source_type, source_identifier=payload.get("source_id"), source_url=config.source_url,
            evidence_type=ScheduleEvidenceType.REGULAR_WEEKLY, source_reference=config.extraction_method,
            retention=RetentionMetadata(status=rule.retention_status)), schedule=schedule,
            verification_status=VerificationStatus.SOURCE_REPORTED,
            derived=SystemDerivedMetadata(parser_version=schedule.parser_version))
        return AdapterResult(decision=AdapterDecision.READY_FOR_MOCK_VALIDATION if schedule.validation_status is ScheduleValidationStatus.VALID else AdapterDecision.REVIEW_REQUIRED,
            evidence=record, schedule=schedule, acquisition_plan=plan)


class OpenStreetMapTimingAdapter:
    source_type = TimingSourceType.OPENSTREETMAP

    def validate_fixture(self, *, attraction_id: int, element: object, policy: TimingGovernancePolicy | None) -> AdapterResult:
        plan = plan_acquisition(self.source_type, policy)
        if not plan.fetch_authorised:
            return AdapterResult(decision=AdapterDecision.UNAUTHORISED, reason_codes=["fetch_not_authorised"], acquisition_plan=plan)
        if not isinstance(element, dict) or not isinstance(element.get("id"), int):
            return AdapterResult(decision=AdapterDecision.INVALID_RESPONSE, reason_codes=["invalid_osm_element"], acquisition_plan=plan)
        tags = element.get("tags")
        if not isinstance(tags, dict) or not isinstance(tags.get("opening_hours"), str):
            return AdapterResult(decision=AdapterDecision.REVIEW_REQUIRED, reason_codes=["osm_opening_hours_missing"], acquisition_plan=plan)
        rule = policy.rule_for(self.source_type)
        assert rule is not None
        identity = f"{element.get('type', 'element')}/{element['id']}"
        record = TimingSourceEvidence(evidence_id=f"osm:{identity}", source_facts=TimingSourceFacts(
            attraction_id=attraction_id, source_type=self.source_type, source_identifier=identity,
            source_url=f"https://www.openstreetmap.org/{identity}", evidence_type=ScheduleEvidenceType.UNSUPPORTED,
            source_reference="ODbL attribution and opening_hours text retained; grammar not parsed in Gate 1.",
            retention=RetentionMetadata(status=rule.retention_status)), verification_status=VerificationStatus.SOURCE_REPORTED,
            derived=SystemDerivedMetadata(parser_version=None, extraction_warnings=[f"Unsupported OSM opening_hours grammar retained verbatim: {tags['opening_hours']}"]))
        return AdapterResult(decision=AdapterDecision.UNSUPPORTED, evidence=record, reason_codes=["osm_grammar_requires_reviewed_parser"], acquisition_plan=plan)


_WEEKDAYS = {"Sunday": 0, "Monday": 1, "Tuesday": 2, "Wednesday": 3, "Thursday": 4, "Friday": 5, "Saturday": 6}

def _official_specification_to_google_periods(value: object) -> list[dict[str, object]] | None:
    """Accept only simple JSON-LD weekly day/open/close records; no free-text parsing."""
    entries = value if isinstance(value, list) else [value]
    periods: list[dict[str, object]] = []
    for entry in entries:
        if not isinstance(entry, dict) or set(entry) - {"dayOfWeek", "opens", "closes"}:
            return None
        days = entry.get("dayOfWeek")
        days = days if isinstance(days, list) else [days]
        opens, closes = entry.get("opens"), entry.get("closes")
        if not isinstance(opens, str) or not isinstance(closes, str): return None
        try:
            open_hour, open_minute = map(int, opens.split(":")); close_hour, close_minute = map(int, closes.split(":"))
        except ValueError:
            return None
        if not all(0 <= item <= limit for item, limit in ((open_hour, 23), (close_hour, 23), (open_minute, 59), (close_minute, 59))): return None
        for day in days:
            if day not in _WEEKDAYS: return None
            number = _WEEKDAYS[day]
            periods.append({"open": {"day": number, "hour": open_hour, "minute": open_minute}, "close": {"day": number, "hour": close_hour, "minute": close_minute}})
    return periods or None
