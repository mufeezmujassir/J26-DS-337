"""Versioned evidence policy for Stage 12.4D.2 research evaluation.

This module deliberately separates source evidence, deterministic validation,
independent review, and evaluation eligibility.  Rule output is never described
as human verification.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import re
from typing import Any, Iterable

POLICY_VERSION = "12.4d2_v1.2"

ACTIVITY_KEYWORDS: dict[str, tuple[str, ...]] = {
    "beach_visit": ("beach", "coast", "seaside", "shore"),
    "surfing": ("surf", "wave", "surfing"),
    "swimming": ("swim", "bathing", "pool"),
    "snorkeling_diving": ("snorkel", "scuba", "diving", "dive site", "coral reef"),
    "hiking": ("hike", "hiking", "trek", "trail", "walking trail"),
    "mountain_viewing": ("mountain", "peak", "viewpoint", "summit", "rock", "hill"),
    "wildlife_safari": ("safari", "wildlife", "national park", "game drive"),
    "cultural_tour": ("heritage", "historic", "museum", "culture", "fort"),
    "archaeology": ("archaeolog", "ruins", "ancient", "historic site"),
    "religious_visit": ("temple", "kovil", "church", "mosque", "shrine", "pilgrimage", "monastery"),
    "waterfall_visit": ("waterfall", "falls", "cascade"),
    "camping": ("camp", "campsite", "campground", "overnight camping"),
    "cycling": ("cycling", "bicycle", "bike", "mountain biking", "cycle trail"),
    "photography": ("photography", "photo", "scenic"),
    "urban_visit": ("shopping", "market", "mall", "city", "urban", "bazaar"),
    "plantation_tour": ("tea estate", "tea factory", "plantation", "tea garden"),
}

CONTRADICTION_PATTERNS: dict[str, tuple[str, ...]] = {
    "camping": ("surf school", "dive school", "shopping mall", "restaurant", "junction", "temple", "church", "mosque"),
    "cycling": ("surf school", "dive school", "shopping mall", "restaurant", "junction", "temple", "church", "mosque"),
    "mountain_viewing": ("surf school", "dive school", "shopping mall", "market", "junction"),
    "urban_visit": ("national park", "forest reserve", "rainforest", "waterfall", "wilderness"),
    "archaeology": ("junction", "shopping mall", "supermarket", "restaurant"),
    "religious_visit": ("shopping mall", "supermarket", "junction"),
    "wildlife_safari": ("shopping mall", "supermarket", "junction", "restaurant"),
}


@dataclass(frozen=True)
class EvidenceDecision:
    evidence_tier: str
    evaluation_eligibility_status: str
    eligible_for_offline_evaluation: bool
    provisional_audit_class: str | None
    reason: str
    rule_ids: tuple[str, ...]
    demonstrably_unsupported: bool = False

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["rule_ids"] = list(self.rule_ids)
        return value


def _text(values: Iterable[Any]) -> str:
    parts: list[str] = []
    for value in values:
        if value is None:
            continue
        if isinstance(value, (list, tuple, set)):
            parts.extend(str(v) for v in value if v is not None)
        else:
            parts.append(str(value))
    return re.sub(r"\s+", " ", " ".join(parts).lower()).strip()


def evaluate_mapping(record: dict[str, Any]) -> EvidenceDecision:
    """Return a deterministic decision from persisted source metadata."""
    status = str(record.get("mapping_validation_status") or "").upper()
    source = str(record.get("mapping_source") or "").lower()
    method = str(record.get("mapping_method") or "").lower()
    activity = str(record.get("activity_code") or record.get("activity_type") or "").lower()
    explicit_activities = _text(record.get("explicit_activities") or [])
    evidence_text = _text([
        record.get("attraction_name"), record.get("description"),
        record.get("secondary_descriptions"), record.get("experience_tags"),
        record.get("vibe_tags"), explicit_activities,
    ])
    all_text = _text([evidence_text, record.get("primary_category"), record.get("secondary_categories")])
    activity_terms = ACTIVITY_KEYWORDS.get(activity, ())
    explicit_match = any(term in explicit_activities for term in activity_terms)
    textual_match = any(term in evidence_text for term in activity_terms)
    contradictions = tuple(p for p in CONTRADICTION_PATTERNS.get(activity, ()) if p in all_text)

    if status == "UNSUPPORTED":
        return EvidenceDecision("D", "EXCLUDED_UNSUPPORTED", False, None,
                                "Stage 12.4D.1 rule audit found absent or contradictory evidence.",
                                ("D1_UNSUPPORTED",), True)
    if source == "attraction_activity_tag" or explicit_match:
        if status == "PROVISIONAL":
            return EvidenceDecision("A", "PROVISIONAL_REVIEW_REQUIRED", False,
                                    "PROVISIONAL_WITH_SUPPORTING_EVIDENCE",
                                    "An explicit structured activity record supports the activity, but the historical mapping remains provisional pending independent review.",
                                    ("TIER_A_EXPLICIT_TAG",))
        return EvidenceDecision("A", "ELIGIBLE_HIGH_EVIDENCE", True, None,
                                "Explicit structured attraction activity evidence is present; this is rule-validated, not human-validated.",
                                ("TIER_A_EXPLICIT_TAG",))
    if status == "SUPPORTED_INFERRED":
        return EvidenceDecision("B", "ELIGIBLE_INFERRED", True, None,
                                "Deterministic name or context evidence supports the activity without an independent human label.",
                                ("TIER_B_CONTEXTUAL_INFERENCE",))
    if status == "VERIFIED":
        # Legacy VERIFIED without an explicit source is not silently promoted to Tier A.
        return EvidenceDecision("B", "ELIGIBLE_INFERRED", True, None,
                                "Legacy rule validation is retained as inferred because explicit source evidence was not identified.",
                                ("TIER_B_LEGACY_RULE",))
    if status == "PROVISIONAL" and contradictions and not textual_match:
        return EvidenceDecision("D", "EXCLUDED_UNSUPPORTED", False,
                                "PROVISIONAL_CONTRADICTORY",
                                "Attraction identity conflicts with the proposed activity and no activity-specific textual evidence offsets the conflict.",
                                tuple(f"CONTRADICTION:{p}" for p in contradictions), True)
    if status == "PROVISIONAL" and textual_match:
        return EvidenceDecision("B", "PROVISIONAL_REVIEW_REQUIRED", False,
                                "PROVISIONAL_WITH_SUPPORTING_EVIDENCE",
                                "Activity-specific name or description evidence exists, but independent review is still required.",
                                ("PROVISIONAL_CONTEXT_SUPPORT",))
    if status == "PROVISIONAL" and (source == "structured_category" or method.startswith("category:")):
        return EvidenceDecision("C", "PROVISIONAL_REVIEW_REQUIRED", False,
                                "PROVISIONAL_WEAK_EVIDENCE",
                                "A broad category is contextually related but does not establish that the activity is available at this attraction.",
                                ("TIER_C_BROAD_CATEGORY",))
    return EvidenceDecision("D", "EXCLUDED_INSUFFICIENT_EVIDENCE", False,
                            "PROVISIONAL_INSUFFICIENT_INFORMATION" if status == "PROVISIONAL" else None,
                            "Available persisted metadata is insufficient to substantiate the activity.",
                            ("TIER_D_INSUFFICIENT",))
