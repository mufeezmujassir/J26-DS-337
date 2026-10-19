"""Source-data quality signals for tourism events, not recommendation relevance."""
from __future__ import annotations

from .schemas import EventRecord


def assess_event_quality(record: EventRecord) -> dict:
    flags: list[str] = []
    if not record.title.strip():
        flags.append("missing_title")
    if record.start_datetime is None:
        flags.append("missing_start_date")
    if record.end_datetime and record.start_datetime and record.end_datetime < record.start_datetime:
        flags.append("invalid_date_range")
    if not record.source_url.startswith("https://lankaevents.lk/"):
        flags.append("invalid_source_url")
    if not record.category:
        flags.append("missing_category")
    if not record.venue:
        flags.append("missing_venue")
    if record.location_confidence == "unresolved":
        flags.append("location_unresolved")
    if not record.organizer:
        flags.append("missing_organizer")
    if not record.description:
        flags.append("missing_description")
    score = max(0, 100 - len(flags) * 10)
    return {"source_event_id": record.source_event_id, "quality_score": score, "quality_flags": flags}
