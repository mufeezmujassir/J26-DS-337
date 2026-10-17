"""Read-only Gate 5C reconciliation of Sri Lanka Tourism catalogue records."""
from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from hashlib import sha256
from pathlib import Path
from typing import Any

from sqlalchemy import text

from app.database import AsyncSessionLocal


def normalize_name(value: str | None) -> str:
    return " ".join(re.sub(r"[^a-z0-9]+", " ", (value or "").casefold()).split())


def _distance_km(a_lat: float, a_lon: float, b_lat: float, b_lon: float) -> float:
    radius = 6371.0088
    d_lat, d_lon = math.radians(b_lat - a_lat), math.radians(b_lon - a_lon)
    h = math.sin(d_lat / 2) ** 2 + math.cos(math.radians(a_lat)) * math.cos(math.radians(b_lat)) * math.sin(d_lon / 2) ** 2
    return radius * 2 * math.asin(math.sqrt(h))


@dataclass(frozen=True)
class ExistingAttraction:
    id: int
    name: str
    slug: str | None
    google_place_id: str | None
    district_id: int | None
    district_name: str | None
    city: str | None
    latitude: float | None
    longitude: float | None
    categories: tuple[str, ...]
    aliases: tuple[str, ...]
    external_source_urls: tuple[str, ...]


async def load_existing_attractions() -> list[ExistingAttraction]:
    """Load only fields that actually exist in the current PostgreSQL schema."""
    statement = text("""
        SELECT
          a.id, a.name, a.slug, a.google_place_id, a.district_id, d.name AS district_name,
          a.city, a.latitude, a.longitude,
          COALESCE(array_agg(DISTINCT c.name) FILTER (WHERE c.name IS NOT NULL), ARRAY[]::text[]) AS categories,
          COALESCE(array_agg(DISTINCT ad.title) FILTER (WHERE ad.title IS NOT NULL), ARRAY[]::text[]) AS description_titles,
          COALESCE(array_agg(DISTINCT ad.source_url) FILTER (WHERE ad.source_url IS NOT NULL), ARRAY[]::text[]) AS source_urls
        FROM attractions a
        LEFT JOIN districts d ON d.id = a.district_id
        LEFT JOIN attraction_categories ac ON ac.attraction_id = a.id
        LEFT JOIN categories c ON c.id = ac.category_id
        LEFT JOIN attraction_descriptions ad ON ad.attraction_id = a.id
        WHERE a.is_active = TRUE
        GROUP BY a.id, d.name
        ORDER BY a.id
    """)
    async with AsyncSessionLocal() as session:
        rows = (await session.execute(statement)).mappings().all()
    result: list[ExistingAttraction] = []
    for row in rows:
        aliases = {str(row["name"]), str(row["slug"] or "").replace("-", " ")}
        aliases.update(str(item) for item in row["description_titles"] if item)
        result.append(ExistingAttraction(
            id=int(row["id"]), name=str(row["name"]), slug=row["slug"], google_place_id=row["google_place_id"],
            district_id=row["district_id"], district_name=row["district_name"], city=row["city"],
            latitude=float(row["latitude"]) if row["latitude"] is not None else None,
            longitude=float(row["longitude"]) if row["longitude"] is not None else None,
            categories=tuple(sorted(str(item) for item in row["categories"] if item)),
            aliases=tuple(sorted(item for item in aliases if item)),
            external_source_urls=tuple(sorted(str(item) for item in row["source_urls"] if item)),
        ))
    return result


def _evidence(existing: ExistingAttraction, method: str, confidence: float, value: str | None = None) -> dict[str, Any]:
    return {"method": method, "confidence": confidence, "matched_value": value, "kb_attraction_id": existing.id,
            "kb_name": existing.name, "kb_district_id": existing.district_id, "kb_district_name": existing.district_name}


def reconcile_record(record: dict[str, Any], existing: list[ExistingAttraction]) -> dict[str, Any]:
    """Classify one record. Fuzzy matching never returns an automatic merge."""
    source_id = record.get("external_source_id")
    url = record.get("canonical_source_url")
    name = record.get("preferred_attraction_name") or record.get("attraction_name")
    name_key = normalize_name(name)
    district = record.get("district") or record.get("district_name")
    district_key = normalize_name(district)
    discovered_google = record.get("google_place_id")
    latitude, longitude = record.get("latitude"), record.get("longitude")

    # Existing external evidence lives in description source URLs in this schema.
    external = [item for item in existing if url and url in item.external_source_urls]
    if len(external) == 1:
        classification, evidence = "existing_kb_match", [_evidence(external[0], "exact_source_url", 1.0, url)]
    elif len(external) > 1:
        classification, evidence = "ambiguous_multiple_matches", [_evidence(item, "exact_source_url", 1.0, url) for item in external]
    else:
        google = [item for item in existing if discovered_google and item.google_place_id == discovered_google]
        if len(google) == 1:
            classification, evidence = "existing_kb_match", [_evidence(google[0], "exact_google_place_id", 1.0, discovered_google)]
        elif len(google) > 1:
            classification, evidence = "ambiguous_multiple_matches", [_evidence(item, "exact_google_place_id", 1.0, discovered_google) for item in google]
        else:
            exact = [item for item in existing if name_key and normalize_name(item.name) == name_key]
            if len(exact) == 1:
                classification, evidence = "existing_kb_match", [_evidence(exact[0], "exact_normalized_name", 0.95, name)]
            elif len(exact) > 1:
                classification, evidence = "ambiguous_multiple_matches", [_evidence(item, "exact_normalized_name", 0.95, name) for item in exact]
            else:
                aliases = [item for item in existing if name_key and any(normalize_name(alias) == name_key for alias in item.aliases)]
                if len(aliases) == 1:
                    classification, evidence = "existing_kb_match", [_evidence(aliases[0], "exact_alias", 0.90, name)]
                elif len(aliases) > 1:
                    classification, evidence = "ambiguous_multiple_matches", [_evidence(item, "exact_alias", 0.90, name) for item in aliases]
                else:
                    district_matches = [item for item in existing if name_key and district_key and normalize_name(item.name) == name_key and (normalize_name(item.district_name) == district_key or normalize_name(item.city) == district_key)]
                    if len(district_matches) == 1:
                        classification, evidence = "existing_kb_match", [_evidence(district_matches[0], "exact_name_plus_district", 0.97, f"{name} | {district}")]
                    else:
                        nearby = []
                        if latitude is not None and longitude is not None:
                            for item in existing:
                                if item.latitude is not None and item.longitude is not None:
                                    distance = _distance_km(float(latitude), float(longitude), item.latitude, item.longitude)
                                    if distance <= 1.0:
                                        nearby.append((item, distance))
                        if len(nearby) == 1:
                            item, distance = nearby[0]
                            classification, evidence = "probable_match_review_required", [_evidence(item, "geographic_proximity", 0.75, f"{distance:.3f} km")]
                        elif len(nearby) > 1:
                            classification, evidence = "ambiguous_multiple_matches", [_evidence(item, "geographic_proximity", 0.75, f"{distance:.3f} km") for item, distance in nearby]
                        elif not name_key:
                            classification, evidence = "insufficient_evidence", []
                        else:
                            fuzzy = [(item, SequenceMatcher(None, name_key, normalize_name(item.name)).ratio()) for item in existing]
                            fuzzy = [(item, score) for item, score in fuzzy if score >= 0.84]
                            fuzzy.sort(key=lambda pair: (-pair[1], pair[0].id))
                            if len(fuzzy) == 1 or (len(fuzzy) > 1 and fuzzy[0][1] - fuzzy[1][1] >= 0.05):
                                item, score = fuzzy[0]
                                classification, evidence = "probable_match_review_required", [_evidence(item, "fuzzy_name_candidate", round(score, 4), name)]
                            elif fuzzy:
                                classification, evidence = "ambiguous_multiple_matches", [_evidence(item, "fuzzy_name_candidate", round(score, 4), name) for item, score in fuzzy[:5]]
                            else:
                                classification, evidence = "new_attraction_candidate", []
    return {
        "external_source_id": source_id, "preferred_attraction_name": name, "canonical_source_url": url,
        "classification": classification, "match_evidence": evidence, "source_provenance": record.get("provenance", []),
        "raw_source_names": record.get("raw_source_names", []), "source_record": record,
    }


def reconcile_registry(*, registry: dict[str, Any], existing: list[ExistingAttraction]) -> list[dict[str, Any]]:
    seen: set[str] = set(); output: list[dict[str, Any]] = []
    for record in registry.get("records", []):
        source_id, url = record.get("external_source_id"), record.get("canonical_source_url")
        identity = source_id or url
        if not identity or identity in seen:
            continue
        seen.add(identity)
        output.append(reconcile_record(record, existing))
    return sorted(output, key=lambda item: (str(item["external_source_id"]), str(item["canonical_source_url"])))


def validate_catalogue_registry(registry: dict[str, Any]) -> dict[str, Any]:
    """Record integrity issues without changing or dropping source records."""
    source_ids: dict[str, int] = {}; urls: dict[str, int] = {}
    missing_names: list[str] = []; missing_provenance: list[str] = []
    for index, record in enumerate(registry.get("records", [])):
        source_id, url = record.get("external_source_id"), record.get("canonical_source_url")
        if isinstance(source_id, str): source_ids[source_id] = source_ids.get(source_id, 0) + 1
        if isinstance(url, str): urls[url] = urls.get(url, 0) + 1
        if not normalize_name(record.get("preferred_attraction_name") or record.get("attraction_name")):
            missing_names.append(str(source_id or url or index))
        if not record.get("provenance"):
            missing_provenance.append(str(source_id or url or index))
    return {"input_records": len(registry.get("records", [])), "duplicate_external_source_ids": sorted(key for key, count in source_ids.items() if count > 1),
            "duplicate_canonical_source_urls": sorted(key for key, count in urls.items() if count > 1),
            "missing_normalized_name": missing_names, "missing_source_provenance": missing_provenance}


def write_reconciliation_reports(*, results: list[dict[str, Any]], registry_path: Path, reports_dir: Path, batch_id: str, existing_count: int, registry_validation: dict[str, Any]) -> dict[str, Path]:
    reports_dir.mkdir(parents=True, exist_ok=True)
    groups = {key: [item for item in results if item["classification"] == key] for key in (
        "existing_kb_match", "probable_match_review_required", "ambiguous_multiple_matches", "new_attraction_candidate", "insufficient_evidence")}
    queue = [{"external_source_id": item["external_source_id"], "attraction_name": item["preferred_attraction_name"], "source_url": item["canonical_source_url"],
              "district": item["source_record"].get("district"), "latitude": item["source_record"].get("latitude"), "longitude": item["source_record"].get("longitude"),
              "google_place_id": None, "google_place_candidate_ids": [], "reason": item["classification"]}
             for item in results if item["classification"] != "existing_kb_match"]
    provenance = [{"external_source_id": item["external_source_id"], "source_url": item["canonical_source_url"], "source_provenance": item["source_provenance"],
                   "match_evidence": item["match_evidence"]} for item in results]
    summary = {"status": "review_only", "registry_path": str(registry_path), "registry_sha256": sha256(registry_path.read_bytes()).hexdigest(),
               "existing_kb_active_attractions": existing_count, "discovered_registry_records": len(results),
               "classifications": {key: len(value) for key, value in groups.items()}, "google_places_queue_count": len(queue),
               "registry_validation": registry_validation,
               "postgresql_writes": False, "qdrant_writes": False,
               "schema_limitations": ["No dedicated attraction alias or external-source-reference table exists; description titles and source URLs were used as available evidence."]}
    payloads = {"existing_attraction_matches": {"records": groups["existing_kb_match"]}, "probable_matches_review_required": {"records": groups["probable_match_review_required"]},
                "ambiguous_matches": {"records": groups["ambiguous_multiple_matches"]}, "new_attraction_candidates": {"records": groups["new_attraction_candidate"]},
                "insufficient_evidence": {"records": groups["insufficient_evidence"]}, "google_places_enrichment_queue": {"status": "not_fetched", "records": queue},
                "field_level_source_provenance": {"records": provenance}, "reconciliation_coverage_summary": summary}
    payloads["catalogue_registry_validation"] = registry_validation
    paths = {}
    for suffix, payload in payloads.items():
        path = reports_dir / f"stage_10_1_3e_gate5c_{batch_id}_{suffix}.json"
        path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
        paths[suffix] = path
    return paths
