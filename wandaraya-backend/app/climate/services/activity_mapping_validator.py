"""Attraction-Activity Semantic Mapping Validator (Stage 12.4D.1 Task D).

Provides deterministic, versioned validation rules to audit attraction-to-activity mappings,
preventing spurious cross-domain inferences (e.g. heritage sites to mountain viewing,
nature reserves to urban shopping, beaches to surfing/diving without wave/swell evidence).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence


RULE_VERSION = "v1.1"


@dataclass(frozen=True)
class MappingValidationResult:
    is_valid: bool
    status: str  # 'VERIFIED', 'SUPPORTED_INFERRED', 'PROVISIONAL', 'AMBIGUOUS', 'UNSUPPORTED'
    reason: str
    rule_id: str
    is_eligible_for_seasonality: bool


# Prohibited activity codes for specific attraction archetypes
PROHIBITED_ARCHETYPES = {
    "mountain_viewing": {
        "disallowed_category_keywords": ["culture & heritage", "history & archaeology", "museum", "shopping", "religious"],
        "disallowed_name_keywords": ["fort", "museum", "clock tower", "ruins", "palace", "kovil", "vihara", "mosque", "church", "bazaar", "market"],
        "disallowed_district_ids": [77],  # Colombo metro flatland
    },
    "urban_visit": {
        "disallowed_category_keywords": ["nature & landscapes", "wildlife & safari"],
        "disallowed_name_keywords": ["national park", "forest reserve", "rainforest", "sanctuary", "waterfall", "falls", "nature reserve", "jungle"],
    },
    "surfing": {
        "requires_explicit_evidence": True,
        "valid_activity_tags": ["surfing"],
        "valid_name_keywords": ["surf", "surf break", "surfing point"],
    },
    "snorkeling_diving": {
        "requires_explicit_evidence": True,
        "valid_activity_tags": ["snorkeling", "scuba diving"],
        "valid_name_keywords": ["snorkeling", "diving", "dive center", "reef", "coral"],
    },
    "swimming": {
        "disallowed_name_keywords": ["waterfall", "falls", "rapid", "chasm", "reservoir", "dam"],
    },
}


def validate_attraction_activity_mapping(
    attraction_id: int,
    attraction_name: str,
    activity_code: str,
    mapping_source: str,
    mapping_method: str,
    evidence_reference: str,
    district_id: int,
    categories: Sequence[str],
    primary_category: str | None,
    activity_tags: Sequence[str],
) -> MappingValidationResult:
    """Audit and validate an attraction-activity mapping link deterministically."""
    name_lower = attraction_name.lower()
    cats_lower = [c.lower() for c in categories]
    primary_cat_lower = (primary_category or "").lower()
    act_tags_lower = [a.lower() for a in activity_tags]

    # Rule 1: Galle Dutch Fort / Heritage sites must not be Mountain Sightseeing
    if activity_code == "mountain_viewing":
        # Check if the site is a coastal fort, heritage site, or museum
        is_heritage = any(
            k in name_lower for k in ["fort", "palace", "ruins", "museum", "clock tower"]
        ) or any("history" in c or "culture" in c for c in cats_lower)
        
        has_mountain_keyword = any(
            k in name_lower for k in ["peak", "mountain", "rock", "gap", "viewpoint", "world's end", "knuckles", "range", "hill", "ridge"]
        )
        
        if is_heritage and not has_mountain_keyword:
            return MappingValidationResult(
                is_valid=False,
                status="UNSUPPORTED",
                reason="Heritage, fortification, or museum site cannot be classified as mountain viewing without physical mountain topography.",
                rule_id="RULE_REJECT_HERITAGE_TO_MOUNTAIN",
                is_eligible_for_seasonality=False,
            )

    # Rule 2: Nature Reserves / National Parks must not be Urban Sightseeing & Shopping
    if activity_code == "urban_visit":
        is_nature_reserve = any(
            k in name_lower for k in ["national park", "forest reserve", "rainforest", "sanctuary", "nature reserve", "jungle", "wildlife"]
        ) or "nature & landscapes" in primary_cat_lower or "wildlife & safari" in primary_cat_lower
        
        has_urban_keyword = any(
            k in name_lower for k in ["mall", "shopping", "market", "bazaar", "arcade", "supermarket", "plaza", "store"]
        )
        
        if is_nature_reserve and not has_urban_keyword:
            return MappingValidationResult(
                is_valid=False,
                status="UNSUPPORTED",
                reason="Protected nature reserves, national parks, and rainforests cannot be mapped to urban sightseeing and shopping.",
                rule_id="RULE_REJECT_NATURE_RESERVE_TO_URBAN",
                is_eligible_for_seasonality=False,
            )

    # Rule 3: Surfing requires explicit surf evidence (activity tag or surf break in name)
    if activity_code == "surfing":
        has_surf_tag = any("surf" in t for t in act_tags_lower)
        has_surf_name = any(k in name_lower for k in ["surf", "surf break", "surf point", "surfing"])
        if not (has_surf_tag or has_surf_name):
            return MappingValidationResult(
                is_valid=False,
                status="UNSUPPORTED",
                reason="Surfing requires explicit surf activity tag or verified surf break point; cannot be inferred solely from generic coastal category.",
                rule_id="RULE_REJECT_UNVERIFIED_SURFING",
                is_eligible_for_seasonality=False,
            )

    # Rule 4: Snorkeling & Diving requires explicit marine/dive evidence
    if activity_code == "snorkeling_diving":
        has_dive_tag = any("snorkeling" in t or "diving" in t for t in act_tags_lower)
        has_dive_name = any(k in name_lower for k in ["snorkeling", "scuba", "diving", "dive center", "reef", "coral", "pigeon island"])
        if not (has_dive_tag or has_dive_name):
            return MappingValidationResult(
                is_valid=False,
                status="UNSUPPORTED",
                reason="Snorkeling and scuba diving require verified dive sites or marine activity tags; cannot be inferred from generic coastal category.",
                rule_id="RULE_REJECT_UNVERIFIED_DIVING",
                is_eligible_for_seasonality=False,
            )

    # Rule 5: Generic 'Family & Recreation' category alone must NOT become Cultural & Heritage Sightseeing
    if activity_code == "cultural_tour" and mapping_source == "structured_category" and "Family & Recreation" in mapping_method:
        has_culture_tag = any(t in act_tags_lower for t in ["historical exploration", "museum visit", "heritage exploration", "cultural experience", "sightseeing"])
        has_culture_cat = any("culture" in c or "history" in c or "heritage" in c for c in cats_lower)
        has_culture_name = any(k in name_lower for k in ["temple", "fort", "museum", "palace", "ruins", "monument", "memorial", "ancient", "heritage"])
        
        if not (has_culture_tag or has_culture_cat or has_culture_name):
            return MappingValidationResult(
                is_valid=False,
                status="UNSUPPORTED",
                reason="Family & Recreation category alone without cultural, historical, or museum metadata cannot substantiate cultural sightseeing.",
                rule_id="RULE_REJECT_SPURIOUS_FAMILY_TO_CULTURE",
                is_eligible_for_seasonality=False,
            )

    # Rule 6: Open water swimming at waterfalls or dangerous waters
    if activity_code == "swimming":
        is_waterfall = any(k in name_lower for k in ["waterfall", "falls", "ella"])
        has_explicit_swim_tag = any("swimming" in t for t in act_tags_lower)
        if is_waterfall and not has_explicit_swim_tag:
            return MappingValidationResult(
                is_valid=False,
                status="UNSUPPORTED",
                reason="Waterfall locations cannot be mapped to open water swimming without explicit, verified safe bathing confirmation.",
                rule_id="RULE_REJECT_WATERFALL_SWIMMING",
                is_eligible_for_seasonality=False,
            )

    # Positive classification evaluations
    # 1. Direct explicit activity tag
    if mapping_source == "attraction_activity_tag":
        return MappingValidationResult(
            is_valid=True,
            status="VERIFIED",
            reason=f"Explicit attraction activity tag matched: {mapping_method}",
            rule_id="RULE_ACCEPT_EXPLICIT_ACTIVITY_TAG",
            is_eligible_for_seasonality=True,
        )

    # 2. Contextual name heuristic with domain support
    if mapping_source == "name_heuristic":
        return MappingValidationResult(
            is_valid=True,
            status="SUPPORTED_INFERRED",
            reason=f"Authoritative name contains validated domain keyword: {mapping_method}",
            rule_id="RULE_ACCEPT_CONTEXTUAL_NAME_HEURISTIC",
            is_eligible_for_seasonality=True,
        )

    # 3. Structured category concordance
    if mapping_source == "structured_category":
        if primary_category and any(c.lower() in primary_cat_lower for c in ["culture", "history", "religious", "wildlife", "tea", "beaches"]):
            return MappingValidationResult(
                is_valid=True,
                status="SUPPORTED_INFERRED",
                reason=f"Primary category '{primary_category}' is directly concordant with {activity_code}.",
                rule_id="RULE_ACCEPT_PRIMARY_CATEGORY_CONCORDANCE",
                is_eligible_for_seasonality=True,
            )
        else:
            return MappingValidationResult(
                is_valid=True,
                status="PROVISIONAL",
                reason=f"Secondary category provides provisional support for {activity_code} pending manual review.",
                rule_id="RULE_ACCEPT_PROVISIONAL_CATEGORY",
                is_eligible_for_seasonality=True,
            )

    # Default fallback
    return MappingValidationResult(
        is_valid=True,
        status="PROVISIONAL",
        reason="Mapping accepted provisionally under v1.1 audit standards.",
        rule_id="RULE_ACCEPT_DEFAULT_PROVISIONAL",
        is_eligible_for_seasonality=True,
    )
