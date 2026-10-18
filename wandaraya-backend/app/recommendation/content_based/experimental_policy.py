"""Non-production, evidence-aware ordering for Stage 12.2D evaluation only."""
from __future__ import annotations

from app.recommendation.content_based.diagnostics import eligibility_review_flags
from app.recommendation.content_based.service import HydratedAttraction
from app.recommendation.content_based.schemas import ContentBasedRecommendationItem


POLICY_VERSION = "content_evidence_review_experiment_v1"


def evidence_bucket(item: ContentBasedRecommendationItem, record: HydratedAttraction) -> tuple[int, list[str]]:
    """Return a transparent ordering bucket without changing baseline scores.

    Unknown metadata is never converted into a negative preference score.  It
    is instead separated from records with positive, verified preference
    evidence. Name-based flags are review signals, never automatic deletion.
    """
    flags = eligibility_review_flags(record)
    matches = [item.category_match_score, item.activity_match_score, item.district_match_score, item.region_match_score]
    requested_evidence = [score for score in matches if score is not None]
    if any(flag == "name_requires_tourism_eligibility_review" for flag in flags):
        return 2, flags
    # Presence is not a negative preference score, but it must not promote a
    # record above one whose requested category/activity evidence is complete.
    if {"missing_category_metadata", "missing_activity_metadata"}.intersection(flags):
        return 1, flags
    if requested_evidence and all(score > 0 for score in requested_evidence):
        return 0, flags
    return 1, flags


def experimental_order(items: list[ContentBasedRecommendationItem], records: dict[int, HydratedAttraction]) -> list[dict]:
    annotated = []
    for item in items:
        record = records.get(item.attraction_id)
        if record is None:
            continue
        bucket, flags = evidence_bucket(item, record)
        annotated.append({"item": item, "eligibility_bucket": bucket, "eligibility_review_flags": flags})
    annotated.sort(key=lambda row: (row["eligibility_bucket"], -row["item"].baseline_score, row["item"].attraction_id))
    return annotated
