"""Evidence-preserving location assessment for tourism events.

This module deliberately returns an unresolved/candidate result when a source
mentions a venue name but does not publish traceable coordinates or a verified
district.  It never geocodes or guesses a venue as part of matching.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from app.models.holiday_event import TourismEvent


LocationStatus = Literal["VERIFIED", "CANDIDATE", "UNRESOLVED", "CONFLICTED"]


class GeographicEvidence(BaseModel):
    latitude: float | None = None
    longitude: float | None = None
    district_id: int | None = None
    venue_name: str | None = None
    location_source_url: str
    location_evidence_type: str
    location_confidence: LocationStatus
    verification_status: LocationStatus
    verification_method: str
    uncertainty_flags: list[str] = Field(default_factory=list)


def resolve_event_location(event: TourismEvent) -> GeographicEvidence:
    """Resolve only information already present and traceable in the event."""
    if event.district_id is not None and event.location_confidence in {"verified", "source_explicit"}:
        return GeographicEvidence(
            district_id=event.district_id,
            venue_name=event.venue,
            location_source_url=event.source_url,
            location_evidence_type="source_supported_district",
            location_confidence="VERIFIED",
            verification_status="VERIFIED",
            verification_method="stored_source_district",
        )
    if event.venue or event.address or event.city or event.province:
        return GeographicEvidence(
            venue_name=event.venue,
            location_source_url=event.source_url,
            location_evidence_type="source_venue_or_region_mention",
            location_confidence="CANDIDATE",
            verification_status="CANDIDATE",
            verification_method="stored_source_text",
            uncertainty_flags=["venue_or_region_requires_independent_geographic_verification"],
        )
    return GeographicEvidence(
        location_source_url=event.source_url,
        location_evidence_type="none",
        location_confidence="UNRESOLVED",
        verification_status="UNRESOLVED",
        verification_method="no_traceable_location_evidence",
        uncertainty_flags=["event_location_unresolved"],
    )
