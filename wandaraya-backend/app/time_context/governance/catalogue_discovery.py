"""Offline-first Sri Lanka Tourism attraction catalogue discovery.

This module parses only captured listing/search HTML.  It deliberately has no
network client, database session, embedding, or Qdrant dependency.
"""
from __future__ import annotations

import json
import re
from collections import defaultdict
from datetime import datetime
from hashlib import sha256
from pathlib import Path
from typing import Any, Literal
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

from bs4 import BeautifulSoup
from pydantic import BaseModel, Field

from app.time_context.governance.url_intelligence import canonicalize_tourism_url, extract_external_source_id


CATALOGUE_SEED_URLS = (
    "https://srilanka.travel/attractions",
    "https://srilanka.travel/tourist-attractions?page=2",
    "https://srilanka.travel/index.php?route=attractions%2Fattractions-search&theme=2",
)


def parse_researcher_approval_timestamp(value: str) -> datetime:
    """Parse an explicit, timezone-aware researcher approval timestamp.

    Placeholder text is rejected separately so a CMD user gets an actionable
    message rather than Python's low-level date parsing traceback.
    """
    normalized = value.strip()
    if not normalized or any(token in normalized.upper() for token in ("YOUR_", "REPLACE_", "<", ">")):
        raise ValueError(
            "placeholder timestamp supplied; use a real timezone-aware ISO-8601 value, "
            "for example 2026-10-16T23:00:00+05:30"
        )
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as error:
        raise ValueError(
            "invalid timestamp; use ISO-8601 with a timezone offset, for example "
            "2026-10-16T23:00:00+05:30"
        ) from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(
            "timestamp must include a timezone offset such as +05:30; "
            "example: 2026-10-16T23:00:00+05:30"
        )
    return parsed


def validate_approval_reference(value: str) -> str:
    normalized = value.strip()
    if not normalized or any(token in normalized.upper() for token in ("YOUR_", "REPLACE_", "<", ">")):
        raise ValueError("placeholder approval reference supplied; enter the real researcher-approved batch reference")
    return normalized


class CatalogueCard(BaseModel):
    attraction_name: str | None = None
    raw_source_name: str | None = None
    source_url: str
    canonical_detail_url: str
    external_source_id: str | None = None
    listing_description: str | None = None
    observed_theme_ids: list[str] = Field(default_factory=list)
    observed_theme_names: list[str] = Field(default_factory=list)
    observed_categories: list[str] = Field(default_factory=list)
    observed_destinations: list[str] = Field(default_factory=list)
    listing_page_number: int | None = None
    source_provenance: list[str] = Field(default_factory=list)
    extraction_status: str = "partial_source_supported"
    extraction_warnings: list[str] = Field(default_factory=list)
    card_selector: str | None = None


class CatalogueApprovedUrl(BaseModel):
    canonical_url: str
    authorization_status: Literal["approved_for_pilot", "discovered_unapproved", "rejected"] = "discovered_unapproved"


class CatalogueBatchPlan(BaseModel):
    """Researcher-owned, finite exact-URL plan for catalogue discovery."""
    batch_id: str | None = None
    source_manifest_path: str | None = None
    source_manifest_sha256: str | None = None
    approval_reference: str | None = None
    researcher_execution_approved_at: datetime | None = None
    emergency_stop: bool = False
    approved_urls: list[CatalogueApprovedUrl] = Field(default_factory=list)
    exact_urls: list[str] = Field(default_factory=list)

    def readiness_errors(self, allowed_urls: set[str], max_pages: int = 10) -> list[str]:
        errors: list[str] = []
        if self.emergency_stop:
            errors.append("emergency_stop_enabled")
        if not self.approval_reference:
            errors.append("pilot_approval_reference_missing")
        if self.researcher_execution_approved_at is None or self.researcher_execution_approved_at.tzinfo is None:
            errors.append("separate_execution_approval_missing")
        if not self.approved_urls:
            errors.append("approved_url_plan_missing")
        if not self.batch_id:
            errors.append("batch_id_missing")
        elif not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", self.batch_id):
            errors.append("batch_id_invalid")
        if not self.source_manifest_path or not self.source_manifest_sha256:
            errors.append("source_manifest_provenance_missing")
        if len(self.approved_urls) > max_pages:
            errors.append("approved_url_plan_exceeds_page_limit")
        seen: set[str] = set()
        for item in self.approved_urls:
            try:
                canonical = canonicalize_tourism_url(item.canonical_url)
            except ValueError:
                errors.append(f"unsupported_url:{item.canonical_url}")
                continue
            if canonical != item.canonical_url:
                errors.append(f"url_not_canonical:{item.canonical_url}")
            if canonical in seen:
                errors.append(f"duplicate_url:{canonical}")
            seen.add(canonical)
            if canonical not in allowed_urls:
                errors.append(f"url_not_in_catalogue_discovery_manifest:{canonical}")
            if item.authorization_status != "approved_for_pilot":
                errors.append(f"url_not_explicitly_approved:{canonical}")
        if set(self.exact_urls) != seen:
            errors.append("plan_exact_urls_do_not_match_approved_urls")
        return errors


class CataloguePageExtraction(BaseModel):
    source_url: str
    retrieved_at: datetime | None = None
    content_sha256: str
    main_content_sha256: str | None = None
    cards: list[CatalogueCard] = Field(default_factory=list)
    pagination_urls: list[str] = Field(default_factory=list)
    theme_search_urls: list[str] = Field(default_factory=list)
    category_filter_urls: list[str] = Field(default_factory=list)
    destination_filter_urls: list[str] = Field(default_factory=list)
    total_page_count: int | None = None
    total_attraction_count: int | None = None
    javascript_or_ajax_indicators: list[str] = Field(default_factory=list)
    duplicate_card_references: int = 0
    pagination_content_duplicate: bool = False
    failed: bool = False


def _absolute_canonical(href: str, source_url: str) -> str | None:
    from urllib.parse import urljoin
    try:
        return canonicalize_tourism_url(urljoin(source_url, href))
    except ValueError:
        return None


def _query_value(url: str, name: str) -> str | None:
    values = parse_qs(urlparse(url).query).get(name, [])
    return values[0] if values else None


def _page_number(url: str) -> int | None:
    value = _query_value(url, "page")
    return int(value) if value and value.isdigit() and int(value) > 0 else None


def _text(node) -> str | None:
    value = node.get_text(" ", strip=True) if node else ""
    return value or None


def _raw_and_normalized_text(node) -> tuple[str | None, str | None]:
    raw = node.get_text(" ", strip=False) if node else ""
    raw = raw or None
    return raw, " ".join(raw.split()) if raw else None


def _legacy_or_standard_detail_url(href: str, source_url: str) -> tuple[str | None, str | None]:
    """Normalize observed detail URL forms without treating unrelated links as cards."""
    candidate = _absolute_canonical(href, source_url)
    if candidate:
        source_id = extract_external_source_id(candidate)
        if source_id:
            return candidate, source_id
    match = re.search(r"(?:[?&]attraction_id=|attraction&attraction_id=)(\d+)\b", href, re.IGNORECASE)
    if not match:
        return None, None
    number = match.group(1)
    return f"https://srilanka.travel/attraction?attraction_id={number}", f"srilanka_tourism_attraction:{number}"


def _explicit_card_value(container, selectors: tuple[str, ...]) -> tuple[str | None, str | None]:
    if container is None:
        return None, None
    for selector in selectors:
        node = container.select_one(selector)
        value = _text(node)
        if value:
            return value, selector
    return None, None


def _filter_urls(soup: BeautifulSoup, source_url: str) -> tuple[set[str], set[str], set[str], set[str]]:
    pages: set[str] = set(); themes: set[str] = set(); categories: set[str] = set(); destinations: set[str] = set()
    # Controls are deliberately scoped to catalogue UI, not global navigation.
    for anchor in soup.select(".attractions-pagination a[href], .attractions-tabs a[href], #search-section a[href], .attractions-results-head a[href]"):
        url = _absolute_canonical(anchor["href"], source_url)
        if not url:
            continue
        query = parse_qs(urlparse(url).query)
        route = "".join(query.get("route", [])).casefold()
        if _page_number(url) is not None:
            pages.add(url)
        if "attractions-search" in route or "attractions-search" in url.casefold():
            if "theme" in query:
                themes.add(url)
            if "category" in query:
                categories.add(url)
            if "destination" in query:
                destinations.add(url)
    return pages, themes, categories, destinations


def _theme_names(soup: BeautifulSoup, source_url: str) -> dict[str, str]:
    """Read theme labels from the source's attraction-tab controls only."""
    values: dict[str, str] = {}
    for anchor in soup.select(".attractions-tabs a[href]"):
        url = _absolute_canonical(anchor["href"], source_url)
        theme_id = _query_value(url, "theme") if url else None
        name = _text(anchor)
        if theme_id and name:
            values[theme_id] = name
    return values


def extract_catalogue_page(*, html: bytes, source_url: str, retrieved_at: datetime | None = None) -> CataloguePageExtraction:
    """Extract listing cards and observed controls from one captured source page."""
    canonical_page = canonicalize_tourism_url(source_url)
    soup = BeautifulSoup(html.decode("utf-8", errors="replace"), "lxml")
    source_theme = _query_value(canonical_page, "theme")
    theme_names = _theme_names(soup, canonical_page)
    source_page_number = _page_number(canonical_page) or 1
    cards: list[CatalogueCard] = []
    seen: set[str] = set(); duplicates = 0
    card_nodes = soup.select(".attractions-grid > article.attraction-card")
    card_selector = ".attractions-grid > article.attraction-card"
    if not card_nodes:
        # A source-specific fallback retained for old captured layouts only.
        card_nodes = soup.select(".attractions-grid .attraction-card")
        card_selector = ".attractions-grid .attraction-card"
    for container in card_nodes:
        detail_url, source_id = None, None
        raw_href = None
        for anchor in container.select("a[href]"):
            detail_url, source_id = _legacy_or_standard_detail_url(anchor["href"], canonical_page)
            if detail_url:
                raw_href = anchor["href"]
                break
        if not detail_url or not source_id:
            continue
        if detail_url in seen:
            duplicates += 1
            continue
        seen.add(detail_url)
        raw_name, name = _raw_and_normalized_text(container.select_one(".attraction-card-body h3, h3"))
        if not name:
            raw_name, name = _raw_and_normalized_text(container.select_one("img[alt]"))
        description, description_selector = _explicit_card_value(container, (".attraction-card-body > p", ".attraction-card-body p"))
        theme_name, theme_selector = _explicit_card_value(container, ("[data-theme-name]", ".theme", ".attraction-theme"))
        category, category_selector = _explicit_card_value(container, ("[data-category]", ".category", ".attraction-category"))
        destination, destination_selector = _explicit_card_value(container, ("[data-destination]", ".destination", ".attraction-destination"))
        provenance = [f"{card_selector}: source card container", f"card detail link href={raw_href}"]
        for value, selector in ((description, description_selector), (theme_name, theme_selector), (category, category_selector), (destination, destination_selector)):
            if value and selector:
                provenance.append(f"{selector}: explicit card field")
        warnings = [] if name else ["attraction_name_unavailable_from_source_card"]
        cards.append(CatalogueCard(
            attraction_name=name, raw_source_name=raw_name, source_url=canonical_page, canonical_detail_url=detail_url, external_source_id=source_id,
            listing_description=description, observed_theme_ids=[source_theme] if source_theme else [],
            observed_theme_names=([theme_names[source_theme]] if source_theme and source_theme in theme_names else ([theme_name] if theme_name else [])), observed_categories=[category] if category else [],
            observed_destinations=[destination] if destination else [], listing_page_number=source_page_number,
            source_provenance=provenance, extraction_warnings=warnings, card_selector=card_selector,
        ))
    pages, themes, categories, destinations = _filter_urls(soup, canonical_page)
    page_markers = [_page_number(url) for url in pages]
    results_text = _text(soup.select_one(".attractions-pagination .results")) or ""
    total_match = re.search(r"\bof\s+(\d+)\s*\(\s*(\d+)\s+Pages?\s*\)", results_text, re.IGNORECASE)
    shown = re.search(r"\b(\d+)\s+shown\b", soup.get_text(" ", strip=True), re.IGNORECASE)
    indicators: list[str] = []
    if soup.select("script[src]"):
        indicators.append("script_src_present")
    if soup.select("[data-ajax], [data-load-more], .ajax, .load-more"):
        indicators.append("ajax_or_load_more_marker_present")
    main_grid = soup.select_one(".attractions-grid")
    main_fingerprint = sha256(" ".join(str(main_grid).split()).encode("utf-8")).hexdigest() if main_grid else None
    return CataloguePageExtraction(
        source_url=canonical_page, retrieved_at=retrieved_at, content_sha256=sha256(html).hexdigest(), cards=cards,
        main_content_sha256=main_fingerprint,
        pagination_urls=sorted(pages), theme_search_urls=sorted(themes), category_filter_urls=sorted(categories),
        destination_filter_urls=sorted(destinations), total_page_count=int(total_match.group(2)) if total_match else (max(page_markers) if page_markers else None),
        total_attraction_count=int(total_match.group(1)) if total_match else None,
        javascript_or_ajax_indicators=indicators, duplicate_card_references=duplicates,
    )


def build_catalogue_seed_manifest() -> dict[str, Any]:
    """Create a review-only seed manifest; no URL is automatically executable."""
    return {
        "stage": "10.1.3E_gate_5b_2", "status": "review_only_seed_manifest",
        "known_distinct_url_structures": [
            {"canonical_url": canonicalize_tourism_url(url), "authorization_status": "requires_separate_approved_batch", "observed": False}
            for url in CATALOGUE_SEED_URLS
        ],
        "limitations": ["No saved listing/search HTML was available when this manifest was generated.",
                        "Pagination, theme names, categories, destinations, page counts and catalogue totals remain unverified until captured."],
    }


def build_registry(*, pages: list[CataloguePageExtraction], preferred_names: dict[str, str] | None = None) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Merge only verified source IDs/URLs; keep records without IDs unresolved."""
    preferred_names = preferred_names or {}
    merged: dict[str, dict[str, Any]] = {}
    unresolved: list[dict[str, Any]] = []
    for page in pages:
        for card in page.cards:
            identity = card.external_source_id or card.canonical_detail_url
            if not card.external_source_id:
                unresolved.append({"canonical_source_url": card.canonical_detail_url, "reason": "missing_verified_external_source_id", "source_url": page.source_url})
                continue
            record = merged.setdefault(identity, {
                "external_source_id": card.external_source_id, "preferred_attraction_name": preferred_names.get(card.external_source_id) or card.attraction_name,
                "attraction_name": preferred_names.get(card.external_source_id) or card.attraction_name, "raw_source_names": [],
                "canonical_source_url": card.canonical_detail_url, "source_domain": "srilanka.travel",
                "discovery_method": [], "discovered_from_urls": [], "observed_theme_ids": [], "observed_theme_names": [], "observed_themes": [], "observed_destinations": [],
                "description": card.listing_description, "extraction_status": card.extraction_status,
                "provenance": [], "retrieved_at": [], "google_place_id": None, "google_place_match_status": None,
                "google_place_candidate_ids": [], "enrichment_required_fields": ["google_place_id", "coordinates", "description"],
                "enrichment_sources": ["Google Places"], "existing_kb_attraction_id": None,
                "reconciliation_status": "pending_gate_5c_read_only_reconciliation",
            })
            record["discovery_method"].append("theme_search" if card.observed_theme_ids else "listing_page")
            record["discovered_from_urls"].append(page.source_url)
            record["observed_theme_ids"].extend(card.observed_theme_ids)
            record["observed_theme_names"].extend(card.observed_theme_names)
            record["observed_themes"].extend(card.observed_theme_ids + card.observed_theme_names + card.observed_categories)
            record["observed_destinations"].extend(card.observed_destinations)
            if card.raw_source_name:
                record["raw_source_names"].append(card.raw_source_name)
            record["provenance"].extend(card.source_provenance)
            if page.retrieved_at:
                record["retrieved_at"].append(page.retrieved_at.isoformat())
            if record["attraction_name"] is None and card.attraction_name:
                record["attraction_name"] = card.attraction_name
                record["preferred_attraction_name"] = card.attraction_name
            if record["description"] is None and card.listing_description:
                record["description"] = card.listing_description
    for value in merged.values():
        for key in ("discovery_method", "discovered_from_urls", "observed_theme_ids", "observed_theme_names", "observed_themes", "observed_destinations", "provenance", "retrieved_at", "raw_source_names"):
            value[key] = sorted(set(value[key]))
    return sorted(merged.values(), key=lambda row: row["canonical_source_url"]), unresolved


def detail_name_overrides(path: Path) -> dict[str, str]:
    """Use only previously captured detail-page names as preferred display names."""
    if not path.is_file():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    overrides: dict[str, str] = {}
    for record in payload.get("records", []):
        fields = record.get("extracted_fields", {})
        source_id, name = fields.get("source_attraction_id"), fields.get("attraction_name")
        if isinstance(source_id, str) and isinstance(name, str) and name.strip():
            overrides[source_id] = " ".join(name.split())
    return overrides


def annotate_page_duplicates(pages: list[CataloguePageExtraction]) -> None:
    seen: set[str] = set()
    for page in pages:
        if page.main_content_sha256 and page.main_content_sha256 in seen:
            page.pagination_content_duplicate = True
        if page.main_content_sha256:
            seen.add(page.main_content_sha256)


def build_full_discovery_manifest(*, pages: list[CataloguePageExtraction]) -> dict[str, Any]:
    """Build a deterministic, review-only next-URL manifest from captured controls."""
    acquired = {page.source_url for page in pages}
    observed = sorted({url for page in pages for url in (page.pagination_urls + page.theme_search_urls + page.category_filter_urls + page.destination_filter_urls)})
    all_urls = sorted(set(observed) | acquired)
    remaining = [url for url in all_urls if url not in acquired]
    return {
        "stage": "10.1.3E_gate_5b_3", "status": "review_only_full_discovery_manifest",
        "acquired_urls": sorted(acquired), "discovered_urls": all_urls, "remaining_urls": remaining,
        "counters": {"discovered_urls": len(all_urls), "acquired_urls": len(acquired), "remaining_urls": len(remaining),
                     "failed_urls": len([page for page in pages if page.failed])},
        "candidates": [{"canonical_url": url, "authorization_status": "discovered_unapproved"} for url in remaining],
    }


def write_next_batch_plan(*, discovery_manifest: dict[str, Any], output_path: Path, batch_id: str, source_manifest_path: str, source_manifest_sha256: str, approval_reference: str | None = None, researcher_execution_approved_at: datetime | None = None, batch_size: int = 10) -> dict[str, Any]:
    if not 1 <= batch_size <= 10:
        raise ValueError("batch_size must be between one and ten")
    urls = discovery_manifest.get("remaining_urls", [])[:batch_size]
    status = "approved_for_pilot" if approval_reference and researcher_execution_approved_at else "discovered_unapproved"
    plan = {"batch_id": batch_id, "source_manifest_path": source_manifest_path, "source_manifest_sha256": source_manifest_sha256,
            "approval_reference": approval_reference, "researcher_execution_approved_at": researcher_execution_approved_at.isoformat() if researcher_execution_approved_at else None,
            "emergency_stop": False, "exact_urls": urls,
            "approved_urls": [{"canonical_url": url, "authorization_status": status} for url in urls]}
    output_path.write_text(json.dumps(plan, indent=2), encoding="utf-8")
    return plan


def write_catalogue_reports(*, pages: list[CataloguePageExtraction], reports_dir: Path, batch_id: str) -> dict[str, Path]:
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", batch_id):
        raise ValueError("batch_id may contain only letters, digits, underscores, and hyphens")
    reports_dir.mkdir(parents=True, exist_ok=True)
    base = f"stage_10_1_3e_gate5b2_{batch_id}"
    annotate_page_duplicates(pages)
    overrides = detail_name_overrides(reports_dir / "stage_10_1_3e_gate5b_extraction_results.json")
    registry, unresolved = build_registry(pages=pages, preferred_names=overrides)
    full_manifest = build_full_discovery_manifest(pages=pages)
    pagination = sorted({url for page in pages for url in page.pagination_urls})
    themes = sorted({url for page in pages for url in page.theme_search_urls})
    summary = {
        "status": "review_only", "pages_acquired": len(pages), "pages_discovered": full_manifest["counters"]["discovered_urls"],
        "pages_remaining": full_manifest["counters"]["remaining_urls"],
        "cards_extracted": sum(len(page.cards) for page in pages), "unique_attractions": len(registry),
        "duplicate_references": sum(page.duplicate_card_references for page in pages), "failed_pages": [page.source_url for page in pages if page.failed],
        "postgresql_writes": False, "qdrant_writes": False,
    }
    payloads = {
        "catalogue_discovery_summary": summary,
        "pagination_manifest": {"observed_pagination_urls": pagination, "observed_page_count": max((page.total_page_count or 0 for page in pages), default=0) or None,
                                "pages": [{"source_url": page.source_url, "main_content_sha256": page.main_content_sha256, "catalogue_card_count": len(page.cards), "pagination_content_duplicate": page.pagination_content_duplicate, "site_reported_total": page.total_attraction_count} for page in pages]},
        "theme_search_manifest": {"observed_theme_search_urls": themes, "pages": [page.model_dump(mode="json") for page in pages]},
        "attraction_registry": {"status": "review_only", "records": registry},
        "discovery_coverage": {**summary, "known_source_total_claimed": [page.total_attraction_count for page in pages if page.total_attraction_count is not None]},
        "unresolved_attraction_references": {"records": unresolved},
        "human_review_queue": {"items": [{"source_url": page.source_url, "javascript_or_ajax_indicators": page.javascript_or_ajax_indicators} for page in pages if page.javascript_or_ajax_indicators]},
        "full_discovery_manifest": full_manifest,
    }
    paths = {}
    for suffix, payload in payloads.items():
        path = reports_dir / f"{base}_{suffix}.json"
        path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
        paths[suffix] = path
    return paths
