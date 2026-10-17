"""Gate 5D: read-only Google Places candidate verification.

The module is intentionally split into pure scoring and an opt-in network runner.
Nothing here writes PostgreSQL, Qdrant, embeddings, or attraction records.
"""
from __future__ import annotations

import asyncio
import json
import math
import re
from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from difflib import SequenceMatcher
from hashlib import sha256
from pathlib import Path
from typing import Any, Protocol

from app.time_context.governance.catalogue_reconciliation import ExistingAttraction, normalize_name


@dataclass(frozen=True)
class Gate5DSettings:
    max_records: int = 5
    max_candidates: int = 5
    request_interval_seconds: float = 1.0
    max_retries: int = 1
    include_details: bool = False
    high_confidence_threshold: float = 0.88
    ambiguity_margin: float = 0.05

    def validate(self) -> None:
        # Offline validation may inspect the complete source queue.  Live callers
        # apply the stricter bounded pilot cap in the CLI.
        if not 1 <= self.max_records <= 500:
            raise ValueError("max_records must be between 1 and 500")
        if not 1 <= self.max_candidates <= 20:
            raise ValueError("max_candidates must be between 1 and 20")
        if self.request_interval_seconds < 0 or not 0 <= self.max_retries <= 3:
            raise ValueError("request interval must be non-negative and retries must be 0..3")


class PlacesClient(Protocol):
    async def text_search(self, *, query: str, max_results: int = 5) -> list[dict[str, Any]]: ...
    async def get_place_details(self, place_id: str) -> dict[str, Any]: ...


def build_search_query(record: dict[str, Any]) -> str:
    """Use only source-supported locality evidence; do not manufacture districts."""
    name = " ".join(str(record.get("attraction_name") or "").split())
    if not name:
        raise ValueError("queue record has no attraction_name")
    locality = record.get("district") or record.get("city")
    return f"{name}, {locality}, Sri Lanka" if locality else f"{name}, Sri Lanka"


def _distance_km(a: tuple[float, float] | None, b: tuple[float, float] | None) -> float | None:
    if not a or not b:
        return None
    lat1, lon1, lat2, lon2 = map(math.radians, (*a, *b))
    h = math.sin((lat2-lat1)/2)**2 + math.cos(lat1)*math.cos(lat2)*math.sin((lon2-lon1)/2)**2
    return 6371.0088 * 2 * math.asin(math.sqrt(h))


def _candidate_location(candidate: dict[str, Any]) -> tuple[float, float] | None:
    location = candidate.get("location") or {}
    try:
        return float(location["latitude"]), float(location["longitude"])
    except (KeyError, TypeError, ValueError):
        return None


def _source_location(record: dict[str, Any]) -> tuple[float, float] | None:
    try:
        return float(record["latitude"]), float(record["longitude"])
    except (KeyError, TypeError, ValueError):
        return None


def _name_similarity(a: str | None, b: str | None) -> float:
    return SequenceMatcher(None, normalize_name(a), normalize_name(b)).ratio() if normalize_name(a) and normalize_name(b) else 0.0


def _existing_identity(candidate_id: str | None, existing: list[ExistingAttraction]) -> list[ExistingAttraction]:
    return [item for item in existing if candidate_id and item.google_place_id == candidate_id]


_LOCALITY_TYPES = {"locality", "administrative_area_level_1", "administrative_area_level_2", "administrative_area_level_3", "country", "political", "neighborhood", "sublocality"}
_ATTRACTION_TYPES = {"tourist_attraction", "historical_landmark", "historical_place", "national_park", "museum", "hindu_temple", "buddhist_temple", "place_of_worship", "zoo", "aquarium", "park", "beach"}


def source_is_compound(name: str | None) -> bool:
    """A compound official title cannot be proved by a single Place ID."""
    return bool(name and re.search(r"\s(?:&|/|and)\s", name, re.IGNORECASE))


def consolidate_manifests(*, queue: list[dict[str, Any]], manifests: list[dict[str, Any]]) -> dict[str, Any]:
    """Merge saved live manifests only; this function never constructs a client."""
    by_source: dict[str, dict[str, Any]] = {}
    retriable: set[str] = set()
    place_sources: dict[str, set[str]] = defaultdict(set)
    for manifest in manifests:
        if manifest.get("mode") != "live":
            continue
        for result in manifest.get("results", []):
            source_id = str(result.get("external_source_id") or "")
            if not source_id:
                continue
            if result.get("classification") == "api_error":
                retriable.add(source_id); continue
            previous = by_source.get(source_id)
            if previous is None or str(result.get("created_at_utc", "")) >= str(previous.get("created_at_utc", "")):
                by_source[source_id] = result
            for candidate in result.get("candidates", []):
                if candidate.get("google_place_id"):
                    place_sources[str(candidate["google_place_id"])].add(source_id)
    queue_ids = {str(item.get("external_source_id")) for item in queue}
    completed = set(by_source)
    return {"mode": "offline_consolidation", "network_requests": 0, "postgresql_writes": False, "qdrant_writes": False,
            "completed_records": sorted(completed), "retriable_records": sorted(retriable),
            "remaining_records": sorted(queue_ids - completed),
            "results": [by_source[key] for key in sorted(by_source)],
            "duplicate_google_place_clusters": [{"google_place_id": place, "external_source_ids": sorted(ids)} for place, ids in sorted(place_sources.items()) if len(ids) > 1]}


def _candidate_kind(candidate: dict[str, Any]) -> str:
    types = {normalize_name(item) for item in candidate.get("types", []) if item}
    primary = normalize_name(candidate.get("primaryType"))
    if primary in _LOCALITY_TYPES or (types & _LOCALITY_TYPES and not types & _ATTRACTION_TYPES):
        return "locality_or_administrative_area"
    if types & _ATTRACTION_TYPES:
        return "physical_attraction"
    return "insufficient_type_evidence"


def _location_conflict(record: dict[str, Any], candidate: dict[str, Any]) -> tuple[bool, str | None]:
    """Use only explicit source locality; Delft is explicit in the official title."""
    source_name = normalize_name(record.get("attraction_name"))
    expected = [normalize_name(record.get(key)) for key in ("district", "city") if normalize_name(record.get(key))]
    if "delft" in source_name:  # An official source-title geographic qualifier, not inferred coordinates.
        expected.append("delft")
    if not expected:
        return False, None
    address = normalize_name(candidate.get("formattedAddress"))
    if address and not any(term in address for term in expected):
        return True, f"source locality evidence ({', '.join(expected)}) is absent from candidate address"
    return False, None


def score_candidate(record: dict[str, Any], candidate: dict[str, Any], existing: list[ExistingAttraction]) -> dict[str, Any]:
    """Return deterministic, inspectable evidence. Fuzzy similarity is never verification."""
    display_raw = candidate.get("displayName") or {}
    display_name = display_raw.get("text", "") if isinstance(display_raw, dict) else str(display_raw)
    source_name = record.get("attraction_name") or ""
    aliases = [source_name, *(record.get("aliases") or []), *(record.get("raw_source_names") or [])]
    name_score = max((_name_similarity(alias, display_name) for alias in aliases), default=0.0)
    candidate_id = candidate.get("id")
    direct = _existing_identity(candidate_id, existing)
    source_point, candidate_point = _source_location(record), _candidate_location(candidate)
    distance = _distance_km(source_point, candidate_point)
    geo_score = 0.0 if distance is None else (1.0 if distance <= 0.2 else 0.75 if distance <= 1 else 0.0)
    locality = normalize_name(record.get("district") or record.get("city"))
    address = normalize_name(candidate.get("formattedAddress"))
    locality_score = 1.0 if locality and locality in address else 0.0
    # Google type data is weak supporting evidence only; missing types remain neutral.
    types = {normalize_name(item) for item in candidate.get("types", []) if item}
    type_score = 0.5 if types else 0.0
    candidate_kind = _candidate_kind(candidate)
    conflict, conflict_reason = _location_conflict(record, candidate)
    type_penalty = 0.35 if candidate_kind == "locality_or_administrative_area" else 0.0
    conflict_penalty = 0.45 if conflict else 0.0
    score = 1.0 if direct else round(max(0.0, name_score * 0.75 + locality_score * 0.10 + geo_score * 0.10 + type_score * 0.05 - type_penalty - conflict_penalty), 4)
    return {
        "google_place_id": candidate_id, "display_name": display_name, "formatted_address": candidate.get("formattedAddress"),
        "coordinates": {"latitude": candidate_point[0], "longitude": candidate_point[1]} if candidate_point else None,
        "types": candidate.get("types") or [], "primary_type": candidate.get("primaryType"),
        "google_maps_uri": candidate.get("googleMapsUri"), "business_status": candidate.get("businessStatus"),
        "score": score, "candidate_kind": candidate_kind, "location_conflict": conflict, "location_conflict_reason": conflict_reason,
        "component_scores": {"name_similarity": round(name_score, 4), "locality_agreement": locality_score,
            "geographic_proximity": geo_score, "type_compatibility": type_score, "existing_google_place_id": 1.0 if direct else 0.0,
            "location_conflict_penalty": -conflict_penalty, "locality_type_penalty": -type_penalty},
        "distance_km": round(distance, 4) if distance is not None else None,
        "existing_kb_matches": [{"id": item.id, "name": item.name} for item in direct],
        "provenance": {"source": "google_places_search", "field_mask": ["id", "displayName", "formattedAddress", "location", "primaryType", "types", "businessStatus", "googleMapsUri"]},
    }


def classify_result(record: dict[str, Any], candidates: list[dict[str, Any]], existing: list[ExistingAttraction], settings: Gate5DSettings, *, error: str | None = None) -> dict[str, Any]:
    base = {"external_source_id": record.get("external_source_id"), "attraction_name": record.get("attraction_name"),
            "source_url": record.get("source_url"), "query": None, "classification": "insufficient_evidence", "candidates": [],
            "details": None, "error": error, "source_provenance": {"official_source_url": record.get("source_url"), "queue_reason": record.get("reason")},
            "google_candidate_kb_identity": "not_evaluated", "official_source_candidate_identity": "not_evaluated", "review_reasons": []}
    if error:
        base["classification"] = "api_error"; return base
    if not record.get("attraction_name"):
        return base
    base["query"] = build_search_query(record)
    ranked = sorted((score_candidate(record, item, existing) for item in candidates), key=lambda item: (-item["score"], str(item["google_place_id"])))
    base["candidates"] = ranked
    compound = source_is_compound(record.get("attraction_name"))
    base["google_candidate_kb_identity"] = "verified_existing_kb_place" if any(item["existing_kb_matches"] for item in ranked) else "no_existing_kb_place_id_match"
    if not ranked:
        base["classification"] = "no_google_place_match"
        base["official_source_candidate_identity"] = "no_candidate_returned"
    elif compound:
        base["classification"] = "high_confidence_candidate_review"
        base["official_source_candidate_identity"] = "compound_source_record_review_required"
        base["review_reasons"].append("official source title may describe multiple distinct destinations")
    elif ranked[0]["candidate_kind"] == "locality_or_administrative_area":
        base["classification"] = "related_locality_not_attraction"
        base["official_source_candidate_identity"] = "locality_only_result_not_identity_proof"
        base["review_reasons"].append("top Google result is a locality or administrative area, not a physical attraction")
    elif ranked[0]["location_conflict"]:
        base["classification"] = "high_confidence_candidate_review"
        base["official_source_candidate_identity"] = "location_conflict_review_required"
        base["review_reasons"].append(ranked[0]["location_conflict_reason"])
    elif any(item["existing_kb_matches"] for item in ranked):
        base["classification"] = "verified_existing_kb_match"
        base["official_source_candidate_identity"] = "strong_candidate_identity_evidence"
    elif len(ranked) > 1 and ranked[0]["score"] - ranked[1]["score"] < settings.ambiguity_margin:
        base["classification"] = "ambiguous_multiple_candidates"
    elif ranked[0]["score"] >= settings.high_confidence_threshold:
        base["classification"] = "high_confidence_candidate_review"
    else:
        base["classification"] = "new_google_place_candidate"
    return base


async def _call_with_retry(coro_factory, *, retries: int) -> tuple[Any | None, str | None]:
    for attempt in range(retries + 1):
        try:
            return await coro_factory(), None
        except Exception as exc:  # HTTP 429/quota and transport failures remain visible; no infinite retry.
            if attempt == retries:
                return None, f"{type(exc).__name__}: {exc}"
            await asyncio.sleep(min(2 ** attempt, 2))
    return None, "unexpected retry state"


async def process_queue(*, queue: list[dict[str, Any]], existing: list[ExistingAttraction], settings: Gate5DSettings, client: PlacesClient | None = None, live: bool = False) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    settings.validate(); selected = queue[:settings.max_records]
    results: list[dict[str, Any]] = []
    usage = {"mode": "live" if live else "offline", "selected_records": len(selected), "search_requests": 0, "details_requests": 0,
             "network_requests": 0, "max_records": settings.max_records, "max_candidates": settings.max_candidates,
             "request_interval_seconds": settings.request_interval_seconds, "max_retries": settings.max_retries}
    for index, record in enumerate(selected):
        if not live:
            item = classify_result(record, [], existing, settings)
            item["classification"] = "insufficient_evidence" if record.get("attraction_name") else item["classification"]
            item["offline_reason"] = "Google Places was not queried; live execution requires explicit flags."
            results.append(item); continue
        if client is None:
            raise ValueError("a Google Places client is required for live execution")
        query = build_search_query(record); usage["search_requests"] += 1; usage["network_requests"] += 1
        raw, error = await _call_with_retry(lambda: client.text_search(query=query, max_results=settings.max_candidates), retries=settings.max_retries)
        item = classify_result(record, raw or [], existing, settings, error=error)
        if not error and settings.include_details and item["candidates"]:
            place_id = item["candidates"][0]["google_place_id"]
            if place_id:
                usage["details_requests"] += 1; usage["network_requests"] += 1
                details, details_error = await _call_with_retry(lambda: client.get_place_details(place_id), retries=settings.max_retries)
                item["details"] = {"data": details, "error": details_error, "provenance": {"source": "google_places_details", "google_place_id": place_id}} if details or details_error else None
        results.append(item)
        if index < len(selected) - 1 and settings.request_interval_seconds:
            await asyncio.sleep(settings.request_interval_seconds)
    return results, usage


def write_gate5d_reports(*, results: list[dict[str, Any]], usage: dict[str, Any], queue_path: Path, reports_dir: Path, batch_id: str) -> dict[str, Path]:
    reports_dir.mkdir(parents=True, exist_ok=True)
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in results: groups[item["classification"]].append(item)
    place_groups: dict[str, list[str]] = defaultdict(list)
    for item in results:
        for candidate in item["candidates"]:
            if candidate.get("google_place_id"): place_groups[candidate["google_place_id"]].append(str(item["external_source_id"]))
    duplicates = [{"google_place_id": key, "external_source_ids": sorted(values)} for key, values in sorted(place_groups.items()) if len(values) > 1]
    provenance = [{"external_source_id": item["external_source_id"], "source_url": item["source_url"], "candidate_provenance": [candidate["provenance"] for candidate in item["candidates"]], "details_provenance": (item.get("details") or {}).get("provenance")} for item in results]
    prefix = f"stage_10_1_3e_gate5d_{batch_id}_google_places_"
    payloads = {
      "discovery_summary": {"status": "review_only", "queue_path": str(queue_path), "queue_sha256": sha256(queue_path.read_bytes()).hexdigest(), "processed_records": len(results), "classifications": {key: len(value) for key, value in sorted(groups.items())}, "postgresql_writes": False, "qdrant_writes": False},
      "candidate_matches": {"records": results}, "verified_existing_matches": {"records": groups["verified_existing_kb_match"]}, "ambiguous_matches": {"records": groups["ambiguous_multiple_candidates"]},
      "new_candidates": {"records": groups["new_google_place_candidate"] + groups["high_confidence_candidate_review"]}, "no_match": {"records": groups["no_google_place_match"]},
      "enrichment_results": {"records": [{"external_source_id": item["external_source_id"], "details": item.get("details")} for item in results if item.get("details")]},
      "field_provenance": {"records": provenance}, "duplicate_clusters": {"records": duplicates},
      "human_review_queue": {"records": [item for item in results if item["classification"] not in {"verified_existing_kb_match", "no_google_place_match"}]},
      "api_usage_summary": usage,
      "full_enrichment_manifest": {"batch_id": batch_id, "created_at_utc": datetime.now(UTC).isoformat(), "mode": usage["mode"], "results": results, "postgresql_writes": False, "qdrant_writes": False},
    }
    paths = {}
    for name, payload in payloads.items():
        path = reports_dir / f"{prefix}{name}.json"
        if path.exists():
            raise FileExistsError(f"Gate 5D report already exists; use a new batch_id: {path}")
        path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str), encoding="utf-8"); paths[name] = path
    return paths
