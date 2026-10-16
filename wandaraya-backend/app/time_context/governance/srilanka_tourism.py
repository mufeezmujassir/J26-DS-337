"""Offline-only contracts for researcher-reported Sri Lanka Tourism material."""
from __future__ import annotations

from datetime import date
from enum import StrEnum
from urllib.parse import urlparse, urlunparse

from bs4 import BeautifulSoup

from pydantic import BaseModel, Field, HttpUrl, field_validator

from app.time_context.opening_hours.google_period_parser import normalize_google_regular_opening_hours
from app.time_context.schemas import FreshnessStatus, TimingEvidence, TimingSourceType, VerificationStatus


class PermissionEvidenceStatus(StrEnum):
    UNDOCUMENTED = "undocumented"
    WRITTEN_CONFIRMED = "written_confirmed"


class SriLankaTourismPermission(BaseModel):
    organization: str = "Sri Lanka Tourism"
    domain: str = "srilanka.travel"
    permission_type: str = "researcher_confirmed_verbal_permission"
    evidence_status: PermissionEvidenceStatus = PermissionEvidenceStatus.UNDOCUMENTED
    academic_research_purpose: bool = True
    written_scope_confirmation: date | None = None
    granted_by: str | None = None
    verbal_discussion_date: date | None = None
    reported_scope: str | None = None
    follow_up_contact: str | None = None
    automated_fetch_allowed: bool = False
    persistent_storage_allowed: bool = False
    embeddings_allowed: bool = False
    redistribution_allowed: bool = False
    commercial_reuse_approved: bool = False
    attribution_requirements: str | None = None
    # Separate technical confirmation prevents verbal scope claims from
    # silently launching a crawler.
    technical_execution_approved: bool = False
    bulk_automated_collection_reported: bool = False
    research_processing_allowed: bool = False


class TourismPageType(StrEnum):
    ATTRACTION = "attraction"
    ACTIVITY = "activity"
    DESTINATION = "destination"
    EVENT = "event"
    PUBLIC_HOLIDAY = "public_holiday"
    TRAVEL_INFORMATION = "travel_information"
    OPERATING_INFORMATION = "operating_information"


class TourismSourceRecord(BaseModel):
    page_type: TourismPageType
    source_url: str
    title: str | None = None
    name: str | None = None
    location_text: str | None = None
    description: str | None = None
    categories: list[str] = Field(default_factory=list)
    activities: list[str] = Field(default_factory=list)
    opening_hours: dict | None = None
    entrance_fee: str | None = None
    visitor_restrictions: list[str] = Field(default_factory=list)
    event_date: date | None = None
    holiday_date: date | None = None
    seasonality_notes: str | None = None
    ticket_url: str | None = None
    published_or_updated_date: date | None = None
    extraction_warnings: list[str] = Field(default_factory=list)


class EntityMatchDecision(StrEnum):
    EXISTING_MATCH = "existing_match"
    AMBIGUOUS_MATCH = "ambiguous_match"
    PROPOSED_NEW_ENTITY = "proposed_new_entity"


class ExistingEntityCandidate(BaseModel):
    attraction_id: int
    name: str
    location_text: str | None = None


class EntityMatchResult(BaseModel):
    decision: EntityMatchDecision
    candidate_ids: list[int] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)


def _is_srilanka_travel_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme == "https" and parsed.hostname in {"srilanka.travel", "www.srilanka.travel"}


def extract_fixture(payload: object, page_type: TourismPageType) -> TourismSourceRecord:
    """Validate only explicitly provided fixture fields; never parse HTML or fetch."""
    if not isinstance(payload, dict):
        raise ValueError("source fixture must be an object")
    source_url = payload.get("source_url")
    if not isinstance(source_url, str) or not _is_srilanka_travel_url(source_url):
        raise ValueError("source_url must be an approved https srilanka.travel URL")
    supported = set(TourismSourceRecord.model_fields) - {"page_type", "extraction_warnings"}
    unknown = sorted(set(payload) - supported)
    values = {key: value for key, value in payload.items() if key in supported}
    values["page_type"] = page_type
    values["extraction_warnings"] = [f"Unsupported fixture field omitted: {key}" for key in unknown]
    return TourismSourceRecord(**values)


def match_entity(record: TourismSourceRecord, candidates: list[ExistingEntityCandidate]) -> EntityMatchResult:
    """Conservative offline matching: exact normalised name and compatible location only."""
    if not record.name:
        return EntityMatchResult(decision=EntityMatchDecision.PROPOSED_NEW_ENTITY, reasons=["source record has no entity name"])
    name = " ".join(record.name.casefold().split())
    matches = [item for item in candidates if " ".join(item.name.casefold().split()) == name]
    if record.location_text:
        location = record.location_text.casefold()
        matches = [item for item in matches if item.location_text and item.location_text.casefold() in location or item.location_text and location in item.location_text.casefold()]
    if len(matches) == 1:
        return EntityMatchResult(decision=EntityMatchDecision.EXISTING_MATCH, candidate_ids=[matches[0].attraction_id], reasons=["normalised name and location evidence identify one candidate"])
    if len(matches) > 1:
        return EntityMatchResult(decision=EntityMatchDecision.AMBIGUOUS_MATCH, candidate_ids=[item.attraction_id for item in matches], reasons=["more than one candidate has matching identity evidence"])
    return EntityMatchResult(decision=EntityMatchDecision.PROPOSED_NEW_ENTITY, reasons=["no sufficiently supported existing match; no database insert was performed"])


def normalize_explicit_official_hours(*, attraction_id: int, record: TourismSourceRecord):
    if record.opening_hours is None:
        return None
    return normalize_google_regular_opening_hours(attraction_id=attraction_id, opening_hours=record.opening_hours,
        evidence=TimingEvidence(source_type=TimingSourceType.OFFICIAL_OPERATOR, source_url=record.source_url,
            verification_status=VerificationStatus.SOURCE_REPORTED, freshness_status=FreshnessStatus.NOT_ASSESSED,
            limitations=["Fixture-only official source evidence; no live permission or freshness validation occurred."]))


def extract_html_fixture(*, html: str, source_url: str, page_type: TourismPageType) -> TourismSourceRecord:
    """Deterministic, bounded HTML extraction for approved future page shapes.

    This function accepts caller-provided HTML only; it does not fetch URLs.
    """
    if not _is_srilanka_travel_url(source_url):
        raise ValueError("source_url must be an approved https srilanka.travel URL")
    soup = BeautifulSoup(html, "lxml")
    title = soup.title.get_text(" ", strip=True) if soup.title else None
    canonical = soup.find("link", rel="canonical")
    canonical_url = canonical.get("href") if canonical and isinstance(canonical.get("href"), str) else source_url
    if not _is_srilanka_travel_url(canonical_url):
        canonical_url = source_url
    heading = soup.find("h1")
    description_node = soup.select_one("main p, article p, .description")
    json_ld = soup.find("script", attrs={"type": "application/ld+json"})
    warnings = []
    if json_ld is None:
        warnings.append("No JSON-LD fixture metadata found; only verified structural selectors were used.")
    return TourismSourceRecord(page_type=page_type, source_url=canonical_url, title=title,
        name=heading.get_text(" ", strip=True) if heading else None,
        description=description_node.get_text(" ", strip=True) if description_node else None,
        extraction_warnings=warnings)
