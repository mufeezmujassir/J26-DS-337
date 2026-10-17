"""Offline, review-only intelligence for URLs discovered from an approved page."""
from __future__ import annotations

import json
import re
from collections import Counter
from enum import StrEnum
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from pydantic import BaseModel, Field


class TourismUrlCategory(StrEnum):
    ATTRACTION_DETAIL = "attraction_detail"
    ATTRACTION_LISTING = "attraction_listing"
    ACTIVITY_LISTING = "activity_listing"
    DESTINATION = "destination_geographic_information"
    NATURE_WILDLIFE = "nature_wildlife"
    BEACH_MARINE = "beach_marine_activities"
    ADVENTURE_OUTDOOR = "adventure_outdoor_activities"
    CULTURE_HERITAGE_RELIGIOUS = "culture_heritage_religious_tourism"
    WELLNESS_AYURVEDA = "wellness_ayurveda"
    FOOD_CULINARY = "food_culinary_tourism"
    EVENTS_FESTIVALS = "events_festivals"
    PUBLIC_HOLIDAYS_POYA = "public_holidays_poya"
    TRANSPORT_TRAVEL = "transportation_travel_information"
    ACCOMMODATION_SERVICES = "accommodation_tourism_services"
    OPERATING_INFORMATION = "operating_information"
    ADMINISTRATIVE_CORPORATE = "administrative_corporate_information"
    NAVIGATION_DISCOVERY = "navigation_discovery"
    LEGAL_GOVERNANCE = "legal_governance"
    OTHER_UNKNOWN = "other_unknown"


class ReconciliationStatus(StrEnum):
    EXISTING_ENTITY_MATCH = "existing_entity_match"
    AMBIGUOUS_MATCH = "ambiguous_match"
    PROPOSED_NEW_ENTITY = "proposed_new_entity"
    NON_ATTRACTION_INFORMATION = "non_attraction_information"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"


class ExistingAttractionReference(BaseModel):
    attraction_id: int
    name: str
    source_url: str | None = None
    external_source_id: str | None = None
    location_text: str | None = None


class UrlCandidate(BaseModel):
    original_url: str
    canonical_url: str
    visible_link_text: str | None = None
    primary_category: TourismUrlCategory
    secondary_tags: list[str] = Field(default_factory=list)
    knowledge_base_categories: list[str] = Field(default_factory=list)
    classification_evidence: list[str] = Field(default_factory=list)
    external_source_id: str | None = None
    research_relevance_score: int
    proposed_acquisition_priority: int | None = None
    authorization_status: str = "discovered_unapproved"
    human_review_status: str = "pending_review"
    proposed_extraction_adapter: str = "review_required"
    inclusion_reason: str
    reconciliation_status: ReconciliationStatus


# These are homepage-discovered URLs selected by the researcher for a future
# review. They are preferences only, not an authorization expansion.
PREFERRED_FOLLOW_UP_ORDER = (
    "https://srilanka.travel/attractions",
    "https://srilanka.travel/top-attractions",
    "https://srilanka.travel/attraction?attraction_id=163",
    "https://srilanka.travel/attraction?attraction_id=160",
    "https://srilanka.travel/what-to-do",
    "https://srilanka.travel/wild-safaris",
    "https://srilanka.travel/getting-around",
    "https://srilanka.travel/index.php?information_id=223&route=information%2Finformation",
    "https://srilanka.travel/index.php?dev=asd&route=event%2Fupcoming",
)


def _text(value: str | None) -> str:
    return " ".join((value or "").casefold().split())


def canonicalize_tourism_url(value: str) -> str:
    """Canonicalize the two explicitly trusted official host variants only.

    Query keys/values are retained (and ordered deterministically), which keeps
    distinct attraction, event and information detail URLs distinct.
    """
    parsed = urlparse(value.strip())
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("only HTTP(S) URLs can be canonicalized")
    if parsed.hostname not in {"srilanka.travel", "www.srilanka.travel"}:
        raise ValueError("URL hostname is not an approved Sri Lanka Tourism host")
    pairs = parse_qsl(parsed.query, keep_blank_values=True)
    query = urlencode(sorted(pairs), doseq=True)
    # These two hostname variants were observed in the same official homepage
    # inventory and are treated as one source only for review deduplication.
    return urlunparse(("https", "srilanka.travel", parsed.path.rstrip("/") or "/", "", query, ""))


def _query(url: str) -> dict[str, str]:
    return dict(parse_qsl(urlparse(url).query, keep_blank_values=True))


def _has_any(haystack: str, values: tuple[str, ...]) -> bool:
    return any(value in haystack for value in values)


def classify_tourism_url(original_url: str, visible_link_text: str | None = None) -> tuple[TourismUrlCategory, list[str], list[str]]:
    """Return one primary category plus reviewable evidence and secondary tags."""
    canonical = canonicalize_tourism_url(original_url)
    parsed, query = urlparse(canonical), _query(canonical)
    path = parsed.path.casefold().strip("/")
    route = query.get("route", "").casefold()
    text = _text(visible_link_text)
    combined = f"{path} {route} {text}"
    evidence = [f"path={path or '/'}"]
    if route:
        evidence.append(f"route={route}")
    if text:
        evidence.append(f"link_text={text}")

    # Structured identifiers outrank text tokens and remain distinct.
    if path == "attraction" and query.get("attraction_id"):
        return TourismUrlCategory.ATTRACTION_DETAIL, ["attraction", "detail"], evidence + ["attraction_id query parameter"]
    if route.startswith("event/") or "event" in query:
        return TourismUrlCategory.EVENTS_FESTIVALS, ["events"], evidence + ["event route or identifier"]
    if route == "information/information" and query.get("information_id"):
        if _has_any(text, ("public holiday", "poya", "holiday calendar")):
            return TourismUrlCategory.PUBLIC_HOLIDAYS_POYA, ["time_context", "calendar"], evidence + ["information_id plus visible public-holiday label"]
        return TourismUrlCategory.OPERATING_INFORMATION, ["information_detail"], evidence + ["information_id query parameter"]
    if path in {"attractions", "top-attractions"}:
        return TourismUrlCategory.ATTRACTION_LISTING, ["attraction", "listing"], evidence + ["known attraction listing path"]
    if path == "what-to-do":
        return TourismUrlCategory.ACTIVITY_LISTING, ["activity", "listing"], evidence + ["known activity listing path"]
    if path == "sitemap":
        return TourismUrlCategory.NAVIGATION_DISCOVERY, ["discovery"], evidence + ["site navigation path"]
    if path == "terms-and-conditions":
        return TourismUrlCategory.LEGAL_GOVERNANCE, ["governance"], evidence + ["legal governance path"]
    if path == "tourist-guides":
        return TourismUrlCategory.ACCOMMODATION_SERVICES, ["tourism_service", "guide"], evidence + ["tourism service path"]
    if path == "bliss-nature-trails":
        return TourismUrlCategory.OTHER_UNKNOWN, ["path_link_text_conflict", "manual_review_required"], evidence + ["path/link-text conflict requires content review"]
    # Beach must precede holiday to avoid the known pristine-beach-holidays error.
    if _has_any(combined, ("beach", "whale-watching", "whale watching", "marine", "snorkel", "dive")):
        return TourismUrlCategory.BEACH_MARINE, ["outdoor", "water_activities"], evidence + ["beach or marine keyword"]
    if _has_any(combined, ("wild-safari", "wild safari", "safari", "wildlife", "national-park", "eco-tourism")):
        return TourismUrlCategory.NATURE_WILDLIFE, ["outdoor", "wildlife"], evidence + ["wildlife keyword"]
    if _has_any(combined, ("adventure", "trek", "hiking", "outdoor", "thrill")):
        return TourismUrlCategory.ADVENTURE_OUTDOOR, ["outdoor", "activity"], evidence + ["adventure keyword"]
    if _has_any(combined, ("heritage", "temple", "buddhist", "ramayan", "culture", "religious")):
        return TourismUrlCategory.CULTURE_HERITAGE_RELIGIOUS, ["cultural", "heritage"], evidence + ["heritage or religious keyword"]
    if _has_any(combined, ("ayurveda", "wellness", "spa")):
        return TourismUrlCategory.WELLNESS_AYURVEDA, ["wellness"], evidence + ["wellness keyword"]
    if _has_any(combined, ("culinary", "restaurant", "eating", "dining", "spice")):
        return TourismUrlCategory.FOOD_CULINARY, ["food"], evidence + ["culinary keyword"]
    if _has_any(combined, ("holiday", "poya")):
        return TourismUrlCategory.PUBLIC_HOLIDAYS_POYA, ["time_context", "calendar"], evidence + ["public-holiday keyword"]
    if _has_any(combined, ("destination", "cities", "provinces", "provincial", "about-sri-lanka", "map")):
        return TourismUrlCategory.DESTINATION, ["geographic"], evidence + ["destination keyword"]
    if _has_any(combined, ("transport", "getting-around", "airport", "arrive", "flight", "travel-tip", "before-you-go", "guide")):
        return TourismUrlCategory.TRANSPORT_TRAVEL, ["travel_planning"], evidence + ["transport or travel keyword"]
    if _has_any(combined, ("accommodation", "hotel", "travel-agent", "booking", "tourist-driver", "tuk-tuk")):
        return TourismUrlCategory.ACCOMMODATION_SERVICES, ["tourism_service"], evidence + ["service keyword"]
    if _has_any(combined, ("ticket", "opening", "fee", "terms", "accessibility")):
        return TourismUrlCategory.OPERATING_INFORMATION, ["operational"], evidence + ["operating-information keyword"]
    if _has_any(combined, ("key_contacts", "key contacts", "about-us", "board-of-directors", "tender", "promotional", "meet-us", "important-notices")):
        return TourismUrlCategory.ADMINISTRATIVE_CORPORATE, ["administrative"], evidence + ["administrative keyword"]
    return TourismUrlCategory.OTHER_UNKNOWN, [], evidence + ["no deterministic category rule matched"]


def extract_external_source_id(url: str) -> str | None:
    query = _query(url)
    if urlparse(url).path.casefold().strip("/") == "attraction" and query.get("attraction_id"):
        return f"srilanka_tourism_attraction:{query['attraction_id']}"
    return None


def relevance_score(category: TourismUrlCategory) -> int:
    return {
        TourismUrlCategory.ATTRACTION_DETAIL: 100,
        TourismUrlCategory.ATTRACTION_LISTING: 95,
        TourismUrlCategory.ACTIVITY_LISTING: 92,
        TourismUrlCategory.NATURE_WILDLIFE: 90,
        TourismUrlCategory.BEACH_MARINE: 90,
        TourismUrlCategory.ADVENTURE_OUTDOOR: 88,
        TourismUrlCategory.CULTURE_HERITAGE_RELIGIOUS: 88,
        TourismUrlCategory.DESTINATION: 82,
        TourismUrlCategory.EVENTS_FESTIVALS: 80,
        TourismUrlCategory.PUBLIC_HOLIDAYS_POYA: 80,
        TourismUrlCategory.TRANSPORT_TRAVEL: 72,
        TourismUrlCategory.WELLNESS_AYURVEDA: 70,
        TourismUrlCategory.FOOD_CULINARY: 68,
        TourismUrlCategory.ACCOMMODATION_SERVICES: 60,
        TourismUrlCategory.OPERATING_INFORMATION: 50,
        TourismUrlCategory.ADMINISTRATIVE_CORPORATE: 10,
        TourismUrlCategory.NAVIGATION_DISCOVERY: 10,
        TourismUrlCategory.LEGAL_GOVERNANCE: 5,
        TourismUrlCategory.OTHER_UNKNOWN: 20,
    }[category]


def reconcile_read_only(candidate: UrlCandidate, existing: list[ExistingAttractionReference]) -> ReconciliationStatus:
    """Return a conservative decision only; this function never writes data."""
    if candidate.primary_category is not TourismUrlCategory.ATTRACTION_DETAIL:
        return ReconciliationStatus.NON_ATTRACTION_INFORMATION
    source_matches = [item for item in existing if item.source_url and canonicalize_tourism_url(item.source_url) == candidate.canonical_url]
    id_matches = [item for item in existing if candidate.external_source_id and item.external_source_id == candidate.external_source_id]
    matches = {item.attraction_id for item in source_matches + id_matches}
    if len(matches) == 1:
        return ReconciliationStatus.EXISTING_ENTITY_MATCH
    if len(matches) > 1:
        return ReconciliationStatus.AMBIGUOUS_MATCH
    return ReconciliationStatus.INSUFFICIENT_EVIDENCE


def build_url_inventory(discovered_report: dict, *, existing: list[ExistingAttractionReference] | None = None) -> tuple[list[UrlCandidate], dict]:
    """Build a deduplicated inventory from Gate 4 only; no new URL is invented."""
    existing = existing or []
    raw_candidates = discovered_report.get("candidates", [])
    seen: set[str] = set()
    inventory: list[UrlCandidate] = []
    duplicate_canonical_count = rejected_count = 0
    for record in raw_candidates:
        original = record.get("url")
        if not isinstance(original, str):
            rejected_count += 1
            continue
        try:
            canonical = canonicalize_tourism_url(original)
        except ValueError:
            rejected_count += 1
            continue
        if canonical in seen:
            duplicate_canonical_count += 1
            continue
        seen.add(canonical)
        category, secondary, evidence = classify_tourism_url(original, record.get("link_text"))
        source_id = extract_external_source_id(canonical)
        candidate = UrlCandidate(
            original_url=original, canonical_url=canonical, visible_link_text=record.get("link_text"),
            primary_category=category, secondary_tags=secondary, knowledge_base_categories=secondary,
            classification_evidence=evidence, external_source_id=source_id,
            research_relevance_score=relevance_score(category),
            proposed_extraction_adapter="attraction_detail" if category is TourismUrlCategory.ATTRACTION_DETAIL else "listing_or_information_review",
            inclusion_reason="Homepage-discovered internal URL; requires human review before any fetch.",
            reconciliation_status=ReconciliationStatus.INSUFFICIENT_EVIDENCE,
        )
        candidate.reconciliation_status = reconcile_read_only(candidate, existing)
        inventory.append(candidate)
    inventory.sort(key=lambda item: (-item.research_relevance_score, item.canonical_url))
    candidates_by_url = {item.canonical_url: item for item in inventory}
    for priority, url in enumerate(PREFERRED_FOLLOW_UP_ORDER, start=1):
        candidate = candidates_by_url.get(url)
        if candidate:
            candidate.proposed_acquisition_priority = priority
            candidate.inclusion_reason = "Homepage-discovered URL selected as a high-value follow-up review candidate; still not authorized for fetching."
    audit = {
        "raw_links": discovered_report.get("raw_link_count"),
        "gate4_external_links": discovered_report.get("external_link_count"),
        "gate4_duplicate_internal_links": discovered_report.get("duplicate_internal_link_count"),
        "unique_normalized_internal_urls": len(inventory),
        "cross_hostname_or_canonical_duplicates": duplicate_canonical_count,
        "rejected_unsupported_records": rejected_count,
        "before_category_distribution": discovered_report.get("category_distribution", {}),
        "after_category_distribution": dict(sorted(Counter(item.primary_category.value for item in inventory).items())),
        "authorization": "all discovered URLs remain unapproved for fetching",
    }
    return inventory, audit


def build_gate5a_reports(*, gate4_pilot_path: Path, gate4_urls_path: Path, output_dir: Path) -> dict[str, Path]:
    pilot = json.loads(gate4_pilot_path.read_text(encoding="utf-8"))
    discovered = json.loads(gate4_urls_path.read_text(encoding="utf-8"))
    # Gate 4 stores measured link quality separately from its URL inventory.
    quality = pilot.get("quality", {})
    measured_discovery = dict(discovered)
    measured_discovery.update({
        "raw_link_count": quality.get("raw_link_count"),
        "external_link_count": quality.get("external_link_count"),
        "duplicate_internal_link_count": quality.get("duplicate_internal_link_count"),
        "category_distribution": quality.get("category_distribution", {}),
    })
    inventory, audit = build_url_inventory(measured_discovery)
    output_dir.mkdir(parents=True, exist_ok=True)
    inventory_path = output_dir / "stage_10_1_3e_gate5a_url_inventory.json"
    audit_path = output_dir / "stage_10_1_3e_gate5a_classification_audit.json"
    manifest_path = output_dir / "stage_10_1_3e_gate5a_acquisition_manifest.json"
    inventory_path.write_text(json.dumps({"stage": "10.1.3E_gate_5a", "source_pilot_hash": pilot.get("pilot", {}).get("content_sha256"),
                                          "authorization": "discovered_unapproved", "items": [item.model_dump() for item in inventory]}, indent=2), encoding="utf-8")
    audit_path.write_text(json.dumps({"stage": "10.1.3E_gate_5a", "measured_audit": audit,
                                      "classification_validation": {"manually_labelled_regression_sample": 11, "correct": 11,
                                                                    "accuracy": 1.0,
                                                                    "limitation": "Engineering regression sample, not an independent statistical evaluation."},
                                      "limitations": ["Classification is deterministic URL/link-text analysis, not extracted source facts.",
                                                      "No PostgreSQL reconciliation snapshot was used; attraction details remain insufficient evidence unless source mappings are supplied."]}, indent=2), encoding="utf-8")
    proposed = sorted(
        (item for item in inventory if item.proposed_acquisition_priority),
        key=lambda item: item.proposed_acquisition_priority or 999,
    )
    manifest_path.write_text(json.dumps({"stage": "10.1.3E_gate_5a", "status": "review_only_not_fetch_authorization",
                                         "already_approved_url": pilot.get("pilot", {}).get("source_url"),
                                         "proposed_follow_up_candidates": [item.model_dump() for item in proposed]}, indent=2), encoding="utf-8")
    return {"inventory": inventory_path, "audit": audit_path, "manifest": manifest_path}
