"""Pure, review-only helpers for Stage 12.2C recommendation diagnostics."""
from __future__ import annotations

from app.recommendation.content_based.service import HydratedAttraction


LOW_QUALITY_NAME_MARKERS = ("junction", "travel sri lanka offers", "travel agency", "bus stand")


def eligibility_review_flags(record: HydratedAttraction) -> list[str]:
    """Heuristics for review queues only; never eligibility decisions."""
    flags: list[str] = []
    name = record.attraction.name.casefold()
    if any(marker in name for marker in LOW_QUALITY_NAME_MARKERS):
        flags.append("name_requires_tourism_eligibility_review")
    if not record.category_names:
        flags.append("missing_category_metadata")
    if not record.activity_names:
        flags.append("missing_activity_metadata")
    if record.attraction.district_id is None:
        flags.append("missing_district_metadata")
    return flags


def requested_metadata_coverage(record: HydratedAttraction, *, wants_category: bool, wants_activity: bool, wants_district: bool) -> float:
    dimensions: list[bool] = []
    if wants_category:
        dimensions.append(bool(record.category_names))
    if wants_activity:
        dimensions.append(bool(record.activity_names))
    if wants_district:
        dimensions.append(record.attraction.district_id is not None)
    return 1.0 if not dimensions else sum(dimensions) / len(dimensions)
