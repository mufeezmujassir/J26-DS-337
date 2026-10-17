"""Gate 5B bounded acquisition, extraction and review-only reporting."""
from __future__ import annotations

import json
import re
from datetime import date, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

from bs4 import BeautifulSoup
from pydantic import BaseModel, Field

from app.time_context.governance.live_pilot import ControlledSriLankaTourismFetcher, LivePilotSettings, SourceAuthorizationConfiguration, StagedTourismChange
from app.time_context.governance.url_intelligence import ExistingAttractionReference, ReconciliationStatus, TourismUrlCategory, UrlCandidate, canonicalize_tourism_url, extract_external_source_id, reconcile_read_only


class UrlAuthorizationStatus(StrEnum):
    DISCOVERED_UNAPPROVED = "discovered_unapproved"
    APPROVED_FOR_PILOT = "approved_for_pilot"
    REJECTED = "rejected"


class ProcessingStatus(StrEnum):
    PENDING_REVIEW = "pending_review"
    FETCHED = "fetched"
    EXTRACTION_REVIEW_REQUIRED = "extraction_review_required"


class ApprovedPilotUrl(BaseModel):
    canonical_url: str
    authorization_status: UrlAuthorizationStatus = UrlAuthorizationStatus.DISCOVERED_UNAPPROVED
    researcher_review_status: ProcessingStatus = ProcessingStatus.PENDING_REVIEW
    approval_reference: str | None = None


class Gate5BPilotPlan(BaseModel):
    """Researcher-owned approval plan, separate from source permission."""
    approval_reference: str | None = None
    researcher_execution_approved_at: datetime | None = None
    approved_urls: list[ApprovedPilotUrl] = Field(default_factory=list)
    emergency_stop: bool = False

    def readiness_errors(self, manifest_urls: set[str]) -> list[str]:
        errors: list[str] = []
        if self.emergency_stop:
            errors.append("emergency_stop_enabled")
        if self.researcher_execution_approved_at is None or self.researcher_execution_approved_at.tzinfo is None:
            errors.append("separate_execution_approval_missing")
        if not self.approval_reference:
            errors.append("pilot_approval_reference_missing")
        if not self.approved_urls:
            errors.append("approved_url_plan_missing")
        if len(self.approved_urls) > 3:
            errors.append("first_pilot_exceeds_three_url_limit")
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
            if canonical not in manifest_urls:
                errors.append(f"url_not_in_gate5a_manifest:{canonical}")
            if item.authorization_status is not UrlAuthorizationStatus.APPROVED_FOR_PILOT:
                errors.append(f"url_not_explicitly_approved:{canonical}")
        return errors


class FieldProvenance(BaseModel):
    field_name: str
    selector_or_basis: str
    source_excerpt: str | None = None


class ReviewExtractionRecord(BaseModel):
    source_url: str
    canonical_url: str
    source_domain: str = "srilanka.travel"
    source_attribution: str = "Sri Lanka Tourism (srilanka.travel)"
    source_page_category: TourismUrlCategory
    http_status: int | None = None
    retrieved_at: datetime | None = None
    content_sha256: str
    extraction_adapter_version: str = "gate5b_v2"
    extracted_fields: dict[str, Any] = Field(default_factory=dict)
    field_provenance: list[FieldProvenance] = Field(default_factory=list)
    selector_diagnostics: list[str] = Field(default_factory=list)
    validation_warnings: list[str] = Field(default_factory=list)
    extraction_confidence: str = "review_required"
    authorization_reference: str | None = None
    authorization_status: UrlAuthorizationStatus = UrlAuthorizationStatus.APPROVED_FOR_PILOT
    processing_status: ProcessingStatus = ProcessingStatus.EXTRACTION_REVIEW_REQUIRED
    reconciliation_status: ReconciliationStatus = ReconciliationStatus.INSUFFICIENT_EVIDENCE
    production_write_performed: bool = False
    qdrant_write_performed: bool = False


def load_manifest_candidates(path: Path) -> dict[str, dict]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return {item["canonical_url"]: item for item in payload.get("proposed_follow_up_candidates", []) if isinstance(item, dict) and isinstance(item.get("canonical_url"), str)}


def _text(node) -> str | None:
    value = node.get_text(" ", strip=True) if node else ""
    return value or None


def _add(fields: dict[str, Any], evidence: list[FieldProvenance], name: str, value: Any, selector: str, excerpt: str | None = None) -> None:
    fields[name] = value
    if value is not None and value != []:
        evidence.append(FieldProvenance(field_name=name, selector_or_basis=selector, source_excerpt=excerpt))


def _listing_references(soup: BeautifulSoup) -> tuple[list[dict[str, str | None]], int]:
    items: list[dict[str, str | None]] = []
    seen: set[str] = set()
    duplicates = 0
    for anchor in soup.select("a[href]"):
        href = anchor.get("href")
        if not isinstance(href, str):
            continue
        try:
            canonical = canonicalize_tourism_url(href if href.startswith("http") else f"https://srilanka.travel/{href.lstrip('/')}")
        except ValueError:
            continue
        source_id = extract_external_source_id(canonical)
        if not source_id:
            continue
        if canonical in seen:
            duplicates += 1
            continue
        seen.add(canonical)
        original_text = anchor.get_text(" ", strip=False) or None
        normalized_text = " ".join(original_text.split()) if original_text else None
        items.append({"source_url": canonical, "source_attraction_id": source_id, "link_text_original": original_text,
                      "link_text_normalized": normalized_text})
    return items, duplicates


def _exact_iso_dates(text: str) -> list[str]:
    results: list[str] = []
    for value in re.findall(r"\b\d{4}-\d{2}-\d{2}\b", text):
        try:
            date.fromisoformat(value)
        except ValueError:
            continue
        results.append(value)
    return sorted(set(results))


def _labelled_values(soup: BeautifulSoup) -> dict[str, list[tuple[str, str]]]:
    """Read only visible label/value structures; no text is inferred from layout."""
    values: dict[str, list[tuple[str, str]]] = {}
    for row in soup.select("tr"):
        label, value = _text(row.find("th")), _text(row.find("td"))
        if label and value:
            values.setdefault(" ".join(label.casefold().split()), []).append((value, "table th/td"))
    for term in soup.select("dt"):
        label, value = _text(term), _text(term.find_next_sibling("dd"))
        if label and value:
            values.setdefault(" ".join(label.casefold().split()), []).append((value, "definition-list dt/dd"))
    return values


def _first_labelled(values: dict[str, list[tuple[str, str]]], labels: tuple[str, ...]) -> tuple[str | None, str]:
    for label in labels:
        matches = values.get(label)
        if matches:
            return matches[0]
    return None, "explicit labelled source field not found"


def _listing_page_description(soup: BeautifulSoup) -> tuple[str | None, str]:
    """Allow only listing-scoped intro selectors; card paragraphs are excluded."""
    node = soup.select_one("main > header p, main > .listing-intro p, main > .page-intro p, .listing-header p")
    return _text(node), "listing-scoped intro selector" if node else "no reliable listing-scoped description selector matched"


def _detail_description(soup: BeautifulSoup) -> tuple[str | None, str, list[str]]:
    """Try only explicit detail-page/structured-data description containers."""
    selectors = ("[data-attraction-description]", ".attraction-description", ".attraction-details .description",
                 "#attraction-description", "[itemprop='description']")
    diagnostics: list[str] = []
    for selector in selectors:
        node = soup.select_one(selector)
        diagnostics.append(f"checked:{selector}:{'found' if node else 'absent'}")
        value = _text(node)
        if value:
            return value, selector, diagnostics
    for node in soup.find_all("script", attrs={"type": "application/ld+json"}):
        try:
            payload = json.loads(node.get_text(strip=True))
        except json.JSONDecodeError:
            diagnostics.append("checked:json_ld:malformed")
            continue
        records = payload if isinstance(payload, list) else [payload]
        for record in records:
            if isinstance(record, dict) and isinstance(record.get("description"), str) and record["description"].strip():
                diagnostics.append("checked:json_ld:description_found")
                return record["description"].strip(), "application/ld+json description", diagnostics
    diagnostics.append("checked:json_ld:description_absent")
    return None, "no known attraction-detail description selector matched", diagnostics


def prepare_detail_reconciliation(record: ReviewExtractionRecord, existing: list[ExistingAttractionReference]) -> ReconciliationStatus:
    """Read-only bridge to existing source mappings; never inserts or updates data."""
    if record.source_page_category is not TourismUrlCategory.ATTRACTION_DETAIL:
        return ReconciliationStatus.NON_ATTRACTION_INFORMATION
    candidate = UrlCandidate(
        original_url=record.source_url, canonical_url=record.canonical_url,
        primary_category=TourismUrlCategory.ATTRACTION_DETAIL,
        external_source_id=record.extracted_fields.get("source_attraction_id"), research_relevance_score=0,
        inclusion_reason="read-only reconciliation preparation", reconciliation_status=ReconciliationStatus.INSUFFICIENT_EVIDENCE,
    )
    return reconcile_read_only(candidate, existing)


def extract_review_record(*, fetched: StagedTourismChange, candidate: dict, authorization_reference: str | None) -> ReviewExtractionRecord:
    """Extract only explicit HTML evidence supplied by the guarded fetcher."""
    if fetched.raw_content is None:
        raise ValueError("captured HTML is required for offline extraction")
    category = TourismUrlCategory(candidate["primary_category"])
    soup = BeautifulSoup(fetched.raw_content.decode("utf-8", errors="replace"), "lxml")
    fields: dict[str, Any] = {}
    evidence: list[FieldProvenance] = []
    warnings: list[str] = []
    heading = soup.find("h1")
    title = _text(heading) or _text(soup.title)
    selector_diagnostics: list[str] = []
    if category is TourismUrlCategory.ATTRACTION_DETAIL:
        description, description_selector, selector_diagnostics = _detail_description(soup)
    else:
        description_node = soup.select_one("main p, article p, .description, [itemprop='description']")
        description, description_selector = _text(description_node), "main p, article p, .description, [itemprop=description]"
    if not title:
        warnings.append("No page title or H1 was found.")
        if category is TourismUrlCategory.ATTRACTION_DETAIL:
            warnings.append("missing_attraction_name")
    if not description and category is not TourismUrlCategory.ATTRACTION_LISTING:
        warnings.append("No supported main description selector matched.")
    _add(fields, evidence, "title", title, "h1 or title", title)
    if category is not TourismUrlCategory.ATTRACTION_LISTING:
        _add(fields, evidence, "description", description, description_selector, description)
    full_text = soup.get_text(" ", strip=True)
    if category is TourismUrlCategory.ATTRACTION_DETAIL:
        labelled = _labelled_values(soup)
        source_id = extract_external_source_id(fetched.source_url)
        _add(fields, evidence, "source_attraction_id", source_id, "attraction_id URL query parameter", source_id)
        if source_id is None:
            warnings.append("malformed_or_incomplete_source_attraction_id")
        _add(fields, evidence, "attraction_name", title, "h1 or title", title)
        label_map = {
            "location_text": ("location", "geographic location", "address"),
            "district": ("district",), "attraction_category": ("category", "attraction category"),
            "activities": ("activities",), "features_highlights": ("features", "highlights"),
            "opening_hours": ("opening hours", "opening time"), "closing_days": ("closing days", "closed days"),
            "entry_fees": ("entry fee", "entrance fee", "fees"), "ticketing_information": ("ticketing", "tickets"),
            "recommended_visiting_periods": ("recommended visiting period", "best time to visit"),
            "seasonal_guidance": ("seasonal guidance", "seasonality"), "accessibility_information": ("accessibility",),
            "contact_details": ("contact", "contact details", "telephone"),
        }
        for field_name, labels in label_map.items():
            value, selector = _first_labelled(labelled, labels)
            _add(fields, evidence, field_name, value, selector, value)
        location_values = labelled.get("location", []) + labelled.get("geographic location", [])
        if len({value for value, _ in location_values}) > 1:
            warnings.append("conflicting_location_evidence")
        opening_hours = fields.get("opening_hours")
        if opening_hours and not re.search(r"\d|open|close", opening_hours, re.IGNORECASE):
            warnings.append("unparseable_operating_hours")
        if fields.get("entry_fees") is None:
            warnings.append("missing_fee_information")
        if fields.get("district") is not None and not re.fullmatch(r"[A-Za-z .'-]+", fields["district"]):
            warnings.append("unsupported_district_assignment")
        if description is None and not any(value for key, value in fields.items() if key not in {"title", "source_attraction_id", "attraction_name"}):
            warnings.append("detail_content_not_found_by_known_selectors_or_labels_possible_javascript_dependency")
    elif category is TourismUrlCategory.ATTRACTION_LISTING:
        refs, duplicate_references = _listing_references(soup)
        _add(fields, evidence, "listing_title", title, "h1 or title", title)
        listing_description, listing_selector = _listing_page_description(soup)
        _add(fields, evidence, "listing_description", listing_description, listing_selector, listing_description)
        if listing_description is None:
            warnings.append("listing_description_unavailable_or_card_scope_rejected")
        if duplicate_references:
            warnings.append(f"duplicate_attraction_references_detected:{duplicate_references}")
        _add(fields, evidence, "referenced_attractions", refs, "a[href] with attraction_id URL parameter")
        _add(fields, evidence, "pagination_indicators", [], "not asserted without explicit pagination marker")
        _add(fields, evidence, "total_count", None, "not asserted unless explicitly stated")
    elif category is TourismUrlCategory.PUBLIC_HOLIDAYS_POYA:
        dates = _exact_iso_dates(full_text)
        _add(fields, evidence, "holiday_name", title, "h1 or title", title)
        _add(fields, evidence, "exact_dates", dates, "explicit ISO date text", ", ".join(dates) if dates else None)
        _add(fields, evidence, "holiday_type", None, "not inferred from category")
        _add(fields, evidence, "poya_indicator", True if "poya" in full_text.casefold() else None, "explicit page text contains poya")
    elif category is TourismUrlCategory.EVENTS_FESTIVALS:
        dates = _exact_iso_dates(full_text)
        _add(fields, evidence, "event_name", title, "h1 or title", title)
        _add(fields, evidence, "exact_dates", dates, "explicit ISO date text", ", ".join(dates) if dates else None)
        _add(fields, evidence, "location", None, "not asserted without explicit labelled source field")
        _add(fields, evidence, "organizer", None, "not asserted without explicit labelled source field")
    elif category is TourismUrlCategory.TRANSPORT_TRAVEL:
        modes = [mode for mode in ("bus", "train", "taxi", "tuk tuk", "flight", "cruise") if mode in full_text.casefold()]
        _add(fields, evidence, "transport_modes", modes, "explicit mode terms in page text", ", ".join(modes) if modes else None)
        for name in ("route_or_service_details", "published_schedules", "fare_information"):
            _add(fields, evidence, name, None, "not asserted without explicit labelled source field")
    else:
        _add(fields, evidence, "page_title", title, "h1 or title", title)
        _add(fields, evidence, "page_description", description, "main description selector", description)
    return ReviewExtractionRecord(source_url=fetched.source_url, canonical_url=fetched.source_url, source_page_category=category,
        http_status=fetched.http_status, retrieved_at=fetched.retrieved_at, content_sha256=fetched.content_sha256,
        extracted_fields=fields, field_provenance=evidence, selector_diagnostics=selector_diagnostics,
        validation_warnings=warnings, authorization_reference=authorization_reference)


def _batch_report_path(reports_dir: Path, batch_id: str | None, suffix: str) -> Path:
    if batch_id is None:
        return reports_dir / f"stage_10_1_3e_gate5b_{suffix}.json"
    if not re.fullmatch(r"[a-zA-Z0-9_-]{1,80}", batch_id):
        raise ValueError("batch_id may contain only letters, digits, underscores, and hyphens")
    return reports_dir / f"stage_10_1_3e_gate5b_{batch_id}_{suffix}.json"


def write_gate5b_reports(*, records: list[ReviewExtractionRecord], plan: Gate5BPilotPlan, reports_dir: Path, batch_id: str | None = None) -> dict[str, Path]:
    reports_dir.mkdir(parents=True, exist_ok=True)
    result_path = _batch_report_path(reports_dir, batch_id, "acquisition_results")
    extraction_path = _batch_report_path(reports_dir, batch_id, "extraction_results")
    completeness_path = _batch_report_path(reports_dir, batch_id, "field_completeness")
    queue_path = _batch_report_path(reports_dir, batch_id, "human_review_queue")
    reconciliation_path = _batch_report_path(reports_dir, batch_id, "candidate_reconciliation")
    result_path.write_text(json.dumps({"status": "review_only", "plan_reference": plan.approval_reference, "records": [{"source_url": r.source_url, "http_status": r.http_status, "content_sha256": r.content_sha256, "retrieved_at": r.retrieved_at, "processing_status": r.processing_status} for r in records]}, indent=2, default=str), encoding="utf-8")
    extraction_path.write_text(json.dumps({"status": "review_only", "records": [r.model_dump() for r in records]}, indent=2, default=str), encoding="utf-8")
    total_fields = sum(len(r.extracted_fields) for r in records)
    populated = sum(1 for r in records for value in r.extracted_fields.values() if value not in (None, [], ""))
    completeness_path.write_text(json.dumps({"records": len(records), "fields_observed_or_null": total_fields, "populated_source_supported_fields": populated, "missing_or_unknown_fields": total_fields - populated}, indent=2), encoding="utf-8")
    queue_path.write_text(json.dumps({"status": "human_review_required", "items": [{"source_url": r.source_url, "category": r.source_page_category, "warnings": r.validation_warnings, "reconciliation": r.reconciliation_status} for r in records]}, indent=2), encoding="utf-8")
    reconciliation_path.write_text(json.dumps({"status": "read_only_preparation", "records": [{"source_url": r.source_url,
        "external_source_id": r.extracted_fields.get("source_attraction_id"), "attraction_name": r.extracted_fields.get("attraction_name"),
        "reconciliation_status": r.reconciliation_status, "note": "No PostgreSQL write was performed."} for r in records]}, indent=2), encoding="utf-8")
    return {"acquisition": result_path, "extraction": extraction_path, "completeness": completeness_path, "review_queue": queue_path, "reconciliation": reconciliation_path}


def capture_batch_directory(*, capture_root: Path, batch_id: str) -> Path:
    """Return the immutable destination for one capture batch."""
    if not re.fullmatch(r"[a-zA-Z0-9_-]{1,80}", batch_id):
        raise ValueError("batch_id may contain only letters, digits, underscores, and hyphens")
    return capture_root / batch_id


def write_captured_html_fixtures(*, fetched: list[StagedTourismChange], capture_root: Path, batch_id: str) -> Path:
    """Persist exact fetched HTML once for offline, reproducible review.

    A batch directory is immutable: callers must choose a new batch identifier
    for a re-acquisition rather than overwriting prior evidence.
    """
    batch_dir = capture_batch_directory(capture_root=capture_root, batch_id=batch_id)
    if batch_dir.exists():
        raise FileExistsError(f"capture batch already exists: {batch_dir}")
    batch_dir.mkdir(parents=True)
    artifacts = []
    for index, item in enumerate(fetched, start=1):
        if item.raw_content is None:
            raise ValueError("cannot capture missing raw HTML")
        source_id = extract_external_source_id(item.source_url) or f"page_{index}"
        filename = f"{source_id.replace(':', '_')}_{item.content_sha256}.html"
        path = batch_dir / filename
        path.write_bytes(item.raw_content)
        artifacts.append({"source_url": item.source_url, "file": filename, "content_sha256": item.content_sha256,
                          "http_status": item.http_status, "content_type": item.content_type,
                          "response_size_bytes": item.response_size_bytes, "retrieved_at": item.retrieved_at})
    manifest_path = batch_dir / "capture_manifest.json"
    manifest_path.write_text(json.dumps({"batch_id": batch_id, "artifacts": artifacts}, indent=2, default=str), encoding="utf-8")
    return manifest_path


def repair_listing_scope_contamination(*, extraction_path: Path, completeness_path: Path, review_queue_path: Path) -> int:
    """Repair prior review artifacts whose generic description came from a card.

    This is a report-only correction based on the stored selector provenance. It
    never changes a source page or production record.
    """
    payload = json.loads(extraction_path.read_text(encoding="utf-8"))
    repaired = 0
    for record in payload.get("records", []):
        if record.get("source_page_category") != TourismUrlCategory.ATTRACTION_LISTING.value:
            continue
        fields = record.setdefault("extracted_fields", {})
        if "description" in fields:
            fields.pop("description", None)
            record["field_provenance"] = [item for item in record.get("field_provenance", []) if item.get("field_name") != "description"]
            record.setdefault("validation_warnings", []).append("listing_card_description_removed_from_page_scope")
            repaired += 1
        fields.setdefault("listing_description", None)
        for reference in fields.get("referenced_attractions", []):
            raw = reference.pop("link_text", None)
            if raw is not None:
                reference["link_text_original"] = raw
                reference["link_text_normalized"] = " ".join(raw.split())
    extraction_path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    total_fields = sum(len(item.get("extracted_fields", {})) for item in payload.get("records", []))
    populated = sum(1 for item in payload.get("records", []) for value in item.get("extracted_fields", {}).values() if value not in (None, [], ""))
    completeness_path.write_text(json.dumps({"records": len(payload.get("records", [])), "fields_observed_or_null": total_fields,
                                              "populated_source_supported_fields": populated, "missing_or_unknown_fields": total_fields - populated,
                                              "report_repairs": repaired}, indent=2), encoding="utf-8")
    queue = json.loads(review_queue_path.read_text(encoding="utf-8")) if review_queue_path.exists() else {"items": []}
    for item in queue.get("items", []):
        if item.get("category") == TourismUrlCategory.ATTRACTION_LISTING.value:
            item.setdefault("warnings", []).append("listing_card_description_removed_from_page_scope")
    review_queue_path.write_text(json.dumps(queue, indent=2), encoding="utf-8")
    return repaired


async def execute_approved_pilot(*, authorization: SourceAuthorizationConfiguration, plan: Gate5BPilotPlan, manifest: dict[str, dict], capture_root: Path | None = None, batch_id: str | None = None) -> list[ReviewExtractionRecord]:
    errors = plan.readiness_errors(set(manifest)) + authorization.readiness_errors(LivePilotSettings(emergency_stop=plan.emergency_stop))
    if errors:
        raise PermissionError("Gate 5B acquisition blocked: " + ", ".join(sorted(set(errors))))
    # Fail before making a request when an immutable evidence directory already
    # exists. This prevents an accidental duplicate live acquisition with the
    # same batch identifier.
    if capture_root is not None:
        if batch_id is None:
            raise ValueError("batch_id is required when fixture capture is enabled")
        if capture_batch_directory(capture_root=capture_root, batch_id=batch_id).exists():
            raise FileExistsError(f"capture batch already exists: {capture_batch_directory(capture_root=capture_root, batch_id=batch_id)}")
    effective = authorization.model_copy(update={"exact_urls": [item.canonical_url for item in plan.approved_urls]})
    fetched = await ControlledSriLankaTourismFetcher(effective, LivePilotSettings(emergency_stop=plan.emergency_stop)).fetch_exact_urls(execute=True)
    if capture_root is not None:
        write_captured_html_fixtures(fetched=fetched, capture_root=capture_root, batch_id=batch_id)
    return [extract_review_record(fetched=item, candidate=manifest[item.source_url], authorization_reference=plan.approval_reference) for item in fetched]
