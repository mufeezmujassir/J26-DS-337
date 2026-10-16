"""Review-only extraction and URL inventory for an explicitly fetched homepage."""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from urllib.parse import urljoin, urlparse, urlunparse

from bs4 import BeautifulSoup
from pydantic import BaseModel, Field

from app.time_context.governance.srilanka_tourism import _is_srilanka_travel_url


class DiscoveredUrl(BaseModel):
    url: str
    link_text: str | None = None
    in_navigation: bool = False
    classification: str = "other_unclassified"
    classification_basis: str


class HomepageExtraction(BaseModel):
    source_url: str
    page_title: str | None = None
    meta_description: str | None = None
    main_headings: list[str] = Field(default_factory=list)
    navigation_links: list[DiscoveredUrl] = Field(default_factory=list)
    structured_metadata: list[dict | list] = Field(default_factory=list)
    relevant_category_labels: list[str] = Field(default_factory=list)
    parsing_warnings: list[str] = Field(default_factory=list)


class HomepageDiscoveryResult(BaseModel):
    extraction: HomepageExtraction
    internal_candidates: list[DiscoveredUrl] = Field(default_factory=list)
    external_link_count: int = 0
    duplicate_internal_link_count: int = 0
    raw_link_count: int = 0
    category_distribution: dict[str, int] = Field(default_factory=dict)
    measured: bool = True


def normalize_discovered_url(value: str, *, base_url: str) -> str:
    """Resolve a homepage link, remove fragments, and accept only approved HTTPS URLs."""
    absolute = urljoin(base_url, value.strip())
    parsed = urlparse(absolute)
    if not _is_srilanka_travel_url(absolute):
        raise ValueError("discovered URL is outside the approved Sri Lanka Tourism HTTPS domain")
    return urlunparse((parsed.scheme, parsed.netloc.lower(), parsed.path.rstrip("/") or "/", "", parsed.query, ""))


def classify_discovered_url(url: str, link_text: str | None) -> tuple[str, str]:
    """Conservative keyword classification for review; it does not authorize fetching."""
    haystack = f"{url} {link_text or ''}".casefold()
    rules = (
        ("public_holidays", ("holiday", "holidays")),
        ("events", ("event", "festival", "calendar")),
        ("attractions", ("attraction", "sight", "landmark")),
        ("destinations", ("destination", "destinations", "where-to-go")),
        ("activities", ("activity", "activities", "experience", "things-to-do")),
        ("operating_information", ("opening", "hours", "ticket", "contact", "accessibility")),
        ("travel_information", ("travel-info", "travel information", "visa", "getting-around", "guide")),
    )
    for category, tokens in rules:
        if any(token in haystack for token in tokens):
            return category, "keyword heuristic from URL or visible link text"
    return "other_unclassified", "no supported category keyword present"


def _parse_structured_metadata(soup: BeautifulSoup, warnings: list[str]) -> list[dict | list]:
    records: list[dict | list] = []
    for node in soup.find_all("script", attrs={"type": "application/ld+json"}):
        raw = node.get_text(strip=True)
        if not raw:
            continue
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            warnings.append("Malformed JSON-LD was not included in structured metadata.")
            continue
        if isinstance(parsed, (dict, list)):
            records.append(parsed)
    return records


def extract_and_discover_homepage(*, source_url: str, html: bytes | str) -> HomepageDiscoveryResult:
    """Extract supplied HTML only. This function never performs an HTTP request."""
    canonical_source = normalize_discovered_url(source_url, base_url=source_url)
    text = html.decode("utf-8", errors="replace") if isinstance(html, bytes) else html
    soup = BeautifulSoup(text, "lxml")
    warnings: list[str] = []
    title = soup.title.get_text(" ", strip=True) if soup.title else None
    meta = soup.find("meta", attrs={"name": lambda value: isinstance(value, str) and value.casefold() == "description"})
    meta_description = meta.get("content", "").strip() or None if meta else None
    headings = [node.get_text(" ", strip=True) for node in soup.find_all(["h1", "h2", "h3"]) if node.get_text(" ", strip=True)]
    if not title:
        warnings.append("Page title is absent.")
    if not meta_description:
        warnings.append("Meta description is absent.")
    extraction = HomepageExtraction(
        source_url=canonical_source,
        page_title=title,
        meta_description=meta_description,
        main_headings=headings,
        structured_metadata=_parse_structured_metadata(soup, warnings),
        parsing_warnings=warnings,
    )
    candidates: list[DiscoveredUrl] = []
    seen: set[str] = set()
    external_count = duplicate_count = raw_link_count = 0
    nav_nodes = set(soup.find_all("nav"))
    for anchor in soup.find_all("a"):
        href = anchor.get("href")
        if not isinstance(href, str) or not href.strip():
            continue
        raw_link_count += 1
        in_navigation = any(parent in nav_nodes for parent in anchor.parents)
        link_text = anchor.get_text(" ", strip=True) or None
        try:
            normalized = normalize_discovered_url(href, base_url=canonical_source)
        except ValueError:
            external_count += 1
            continue
        if normalized in seen:
            duplicate_count += 1
            continue
        seen.add(normalized)
        classification, basis = classify_discovered_url(normalized, link_text)
        candidate = DiscoveredUrl(url=normalized, link_text=link_text, in_navigation=in_navigation,
                                  classification=classification, classification_basis=basis)
        candidates.append(candidate)
        if in_navigation:
            extraction.navigation_links.append(candidate)
    counts = Counter(item.classification for item in candidates)
    extraction.relevant_category_labels = sorted(category for category in counts if category != "other_unclassified")
    return HomepageDiscoveryResult(
        extraction=extraction,
        internal_candidates=candidates,
        external_link_count=external_count,
        duplicate_internal_link_count=duplicate_count,
        raw_link_count=raw_link_count,
        category_distribution=dict(sorted(counts.items())),
    )


def write_gate4_review_artifacts(*, result: HomepageDiscoveryResult, pilot_metadata: dict, reports_dir: Path) -> tuple[Path, Path]:
    """Persist review artifacts only; callers decide when a live fetch is allowed."""
    reports_dir.mkdir(parents=True, exist_ok=True)
    pilot_path = reports_dir / "stage_10_1_3d_gate4_pilot.json"
    inventory_path = reports_dir / "stage_10_1_3d_gate4_discovered_urls.json"
    pilot_path.write_text(json.dumps({"status": "review_required", "pilot": pilot_metadata, "extraction": result.extraction.model_dump(),
                                      "quality": {"raw_link_count": result.raw_link_count, "external_link_count": result.external_link_count,
                                                  "duplicate_internal_link_count": result.duplicate_internal_link_count,
                                                  "category_distribution": result.category_distribution}}, indent=2, default=str), encoding="utf-8")
    inventory_path.write_text(json.dumps({"status": "review_only_not_fetch_authorization", "source_url": result.extraction.source_url,
                                          "candidates": [item.model_dump() for item in result.internal_candidates]}, indent=2), encoding="utf-8")
    return pilot_path, inventory_path
