"""Gate 5E.2C.2 offline metadata enrichment and quarantine resolution.

This is deliberately a *read-only* preparation command.  It consumes the
immutable Gate 5E.2B evidence already saved locally, may read district
boundaries/category taxonomy from PostgreSQL, and creates review reports.  It
never calls an external provider and never writes PostgreSQL or Qdrant.
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import json
import os
from hashlib import sha256
from pathlib import Path
from typing import Any


B6 = "data/reports/stage_10_1_3e_gate5e2b6_all_completed_v1_"
B5 = "data/reports/stage_10_1_3e_gate5e2b5_all_completed_v1_verification_checkpoint.json"
B1 = "data/reports/stage_10_1_3e_gate5e2b1_all_completed_v1_identity_evidence_manifest.json"
GATE5D = "data/reports/stage_10_1_3e_gate5d_final_82_consolidated_google_places_consolidation.json"


def digest(value: Any) -> str:
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True), encoding="utf-8")
    os.replace(temporary, path)


def valid_coordinate(location: Any) -> tuple[float | None, float | None]:
    if not isinstance(location, dict):
        return None, None
    try:
        latitude, longitude = float(location["latitude"]), float(location["longitude"])
    except (KeyError, TypeError, ValueError):
        return None, None
    # Sri Lanka bounding box check is validation, not a district inference.
    if not (5.0 <= latitude <= 10.1 and 79.0 <= longitude <= 82.2):
        return None, None
    return latitude, longitude


def category_candidate(*, official_name: str | None, google_name: str | None = None, google_types: list[str], categories: dict[str, int]) -> tuple[str | None, int | None, str]:
    """Map only explicit official terms or Google types to the live taxonomy.

    ``tourist_attraction`` alone is intentionally not enough: it describes a
    broad place class, not an activity/category in WANDARAYA's taxonomy.
    """
    by_name = {name.casefold(): (name, category_id) for name, category_id in categories.items()}
    types = {str(item).casefold() for item in google_types}
    title = (official_name or "").casefold()
    google_title = (google_name or "").casefold()

    def mapped(name: str, evidence: str) -> tuple[str | None, int | None, str]:
        value = by_name.get(name.casefold())
        return (value[0], value[1], evidence) if value else (None, None, "required_taxonomy_category_not_active")

    # Specific Google place types are the strongest category evidence.
    if types & {"buddhist_temple", "hindu_temple", "place_of_worship", "mosque", "church"}:
        return mapped("Religious & Spiritual", "stored_google_religious_place_type")
    if types & {"historical_landmark", "historical_place", "archaeological_site"}:
        return mapped("History & Archaeology", "stored_google_historical_place_type")
    if types & {"national_park", "wildlife_park", "zoo", "safari_park"}:
        return mapped("Wildlife & Safari", "stored_google_wildlife_or_park_type")
    if "beach" in types:
        return mapped("Beaches & Coastal", "stored_google_beach_type")
    if types & {"hiking_area", "trailhead", "climbing_area"}:
        return mapped("Adventure & Outdoor", "stored_google_outdoor_activity_type")
    if types & {"island", "lake", "waterfall", "mountain_peak", "natural_feature"}:
        return mapped("Nature & Landscapes", "stored_google_natural_feature_type")

    # Strong official-source title terms are useful when Google supplies only
    # the generic tourist_attraction type.  We do not classify generic names.
    if any(term in title for term in ("temple", "viharaya", "kovil", "kovil", "amman", "buddha statue")):
        return mapped("Religious & Spiritual", "official_title_religious_term")
    if any(term in title for term in ("fortress", "lighthouse", "archaeological", "historical")):
        return mapped("History & Archaeology", "official_title_historical_term")
    if "ambalama" in title:
        return mapped("Culture & Heritage", "official_title_heritage_term")
    if "hot water spring" in title or "hot springs" in google_title:
        return mapped("Wellness & Ayurveda", "official_and_google_title_hot_spring_term")
    if "beach" in title:
        return mapped("Beaches & Coastal", "official_title_beach_term")
    if any(term in title for term in ("water fall", "waterfall", "mountain", "island", "lake", "tree")) or "waterfall" in google_title or " falls" in google_title:
        return mapped("Nature & Landscapes", "official_title_natural_feature_term")
    return None, None, "no_unambiguous_source_supported_mapping_to_existing_taxonomy"


def physical_attraction_candidate(types: list[str]) -> bool:
    """A locality/administrative result cannot supply an attraction identity."""
    normalized = {str(item).casefold() for item in types}
    if normalized & {"locality", "political", "administrative_area_level_1", "administrative_area_level_2", "country"}:
        return False
    return bool(normalized & {
        "tourist_attraction", "historical_landmark", "historical_place", "museum",
        "national_park", "park", "hindu_temple", "buddhist_temple", "beach",
        # Natural attractions have valid physical coordinates even when Google
        # does not label them with the generic tourist_attraction type.
        "hiking_area", "natural_feature", "island", "lake", "waterfall", "mountain",
    })


async def read_only_snapshot() -> tuple[dict[str, int], dict[str, list[dict[str, Any]]]]:
    from sqlalchemy import select
    from app.database import AsyncSessionLocal
    from app.models.attraction import Attraction
    from app.models.categories import Category

    async with AsyncSessionLocal() as session:
        categories = dict((await session.execute(select(Category.name, Category.id).where(Category.is_active.is_(True)))).all())
        rows = (await session.execute(select(
            Attraction.id, Attraction.name, Attraction.google_place_id, Attraction.district_id,
            Attraction.latitude, Attraction.longitude,
        ).where(Attraction.is_active.is_(True)))).all()
    by_place: dict[str, list[dict[str, Any]]] = {}
    for attraction_id, name, place_id, district_id, latitude, longitude in rows:
        if place_id:
            by_place.setdefault(place_id, []).append({"attraction_id": attraction_id, "name": name, "district_id": district_id, "latitude": latitude, "longitude": longitude})
    return categories, by_place


async def district_for_point(latitude: float | None, longitude: float | None, *, tolerance_meters: float = 75.0) -> dict[str, Any]:
    if latitude is None or longitude is None:
        return {"district_id": None, "district_name": None, "status": "unavailable", "reason": "no_stored_coordinate"}
    from sqlalchemy import text
    from app.database import AsyncSessionLocal
    try:
        async with AsyncSessionLocal() as session:
            result = await session.execute(text("""
                SELECT id, name FROM districts
                WHERE is_active = TRUE
                  AND ST_Covers(boundary, ST_SetSRID(ST_MakePoint(:longitude, :latitude), 4326))
                ORDER BY id LIMIT 2
            """), {"latitude": latitude, "longitude": longitude})
            rows = result.mappings().all()
        if len(rows) == 1:
            return {"district_id": rows[0]["id"], "district_name": rows[0]["name"], "status": "verified", "reason": "postgis_boundary_contains_stored_google_coordinate"}
        if len(rows) > 1:
            return {"district_id": None, "district_name": None, "status": "ambiguous", "reason": "coordinate_matches_multiple_boundaries"}
        # GPS precision and polygon digitisation can differ slightly at a border.
        # A bounded geodesic tolerance produces a review candidate, never an
        # automatic verified assignment or a silent cross-district substitution.
        async with AsyncSessionLocal() as session:
            near = await session.execute(text("""
                SELECT id, name,
                       ST_Distance(boundary::geography, ST_SetSRID(ST_MakePoint(:longitude, :latitude), 4326)::geography) AS distance_meters
                FROM districts
                WHERE is_active = TRUE
                  AND ST_DWithin(boundary::geography, ST_SetSRID(ST_MakePoint(:longitude, :latitude), 4326)::geography, :tolerance_meters)
                ORDER BY distance_meters, id LIMIT 2
            """), {"latitude": latitude, "longitude": longitude, "tolerance_meters": tolerance_meters})
            nearby = near.mappings().all()
        if len(nearby) == 1:
            return {"district_id": nearby[0]["id"], "district_name": nearby[0]["name"], "status": "near_boundary_review_required", "reason": "coordinate_within_configured_boundary_tolerance", "distance_meters": round(float(nearby[0]["distance_meters"]), 2), "tolerance_meters": tolerance_meters}
        if len(nearby) > 1:
            return {"district_id": None, "district_name": None, "status": "ambiguous", "reason": "coordinate_is_within_tolerance_of_multiple_boundaries", "tolerance_meters": tolerance_meters}
        return {"district_id": None, "district_name": None, "status": "unavailable", "reason": "stored_coordinate_not_covered_by_active_boundary_or_tolerance", "tolerance_meters": tolerance_meters}
    except Exception as exc:  # Boundary availability must block rather than guess.
        return {"district_id": None, "district_name": None, "status": "unavailable", "reason": f"district_boundary_lookup_unavailable:{type(exc).__name__}"}


def cluster_for(source_id: str, clusters: list[dict[str, Any]]) -> dict[str, Any] | None:
    return next((cluster for cluster in clusters if source_id in cluster.get("source_attraction_ids", [])), None)


async def enrich(*, manifest: dict[str, Any], prior: dict[str, dict[str, Any]], checkpoint: dict[str, Any], gate5d: dict[str, Any], clusters: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    categories, kb_by_place = await read_only_snapshot()
    live = {item["source_attraction_id"]: item for item in checkpoint.get("results", [])}
    gate5d_by_id = {item.get("external_source_id"): item for item in gate5d.get("results", [])}
    records: list[dict[str, Any]] = []
    for approval in manifest.get("records", []):
        source_id = approval["source_attraction_id"]
        original = prior.get(source_id, {})
        live_result = live.get(source_id)
        historical = gate5d_by_id.get(source_id, {})
        details = (live_result or {}).get("shortlisted_details") or (historical.get("details") or {}).get("data") or {}
        candidates = (live_result or {}).get("candidates") or historical.get("candidates") or []
        candidate = candidates[0] if candidates else {}
        types = details.get("types") or candidate.get("types") or []
        usable_google_evidence = bool(live_result) or physical_attraction_candidate(types)
        latitude, longitude = valid_coordinate(details.get("location") or candidate.get("coordinates")) if usable_google_evidence else (None, None)
        district = await district_for_point(latitude, longitude)
        google_name = (details.get("displayName") or {}).get("text") or candidate.get("display_name")
        category_name, category_id, category_reason = category_candidate(
            official_name=original.get("official_name"), google_name=google_name, google_types=types, categories=categories,
        )
        google_place_id = (live_result or {}).get("shortlisted_place_id") or candidate.get("google_place_id") or original.get("google_place_id")
        matches = kb_by_place.get(google_place_id, [])
        cluster = cluster_for(source_id, clusters)
        conflicts: list[str] = []
        if not usable_google_evidence:
            conflicts.append("no_stored_physical_attraction_google_evidence_for_this_source_record")
        elif not live_result:
            conflicts.append("district_derived_from_saved_gate5d_evidence_requires_reapproval")
        if district["status"] != "verified": conflicts.append("missing_verified_district")
        if not category_id: conflicts.append("missing_verified_category")
        if len(matches) > 1: conflicts.append("multiple_existing_kb_records_share_google_place_id")
        if cluster and cluster.get("resolution") != "RESOLVED": conflicts.append("unresolved_duplicate_cluster")
        original_hash = approval["final_proposal_sha256"]
        payload = {"source_attraction_id": source_id, "official_name": original.get("official_name"), "official_source_url": original.get("official_source_url"), "google_place_id": google_place_id, "latitude": latitude, "longitude": longitude, "district_id": district["district_id"], "category_id": category_id}
        material_change = any(payload[key] is not None for key in ("latitude", "longitude", "district_id", "category_id"))
        readiness = "READY_FOR_REAPPROVAL" if material_change and not conflicts else "QUARANTINED"
        record = {
            **payload,
            "source_attraction_id": source_id,
            "google_name": google_name,
            "google_types": types,
            "district_evidence": district,
            "proposed_category_name": category_name,
            "category_evidence": category_reason,
            "identity_assessment": (live_result or {}).get("assessment") or historical.get("classification") or original.get("classification") or "evidence_incomplete",
            "existing_kb_duplicates": matches,
            "duplicate_cluster": {"cluster_id": cluster.get("cluster_id"), "resolution": cluster.get("resolution")} if cluster else None,
            "metadata_completeness": {"coordinates": latitude is not None, "district": district["status"] == "verified", "category": category_id is not None},
            "conflicts": conflicts,
            "original_approval_hash": original_hash,
            "checkpoint_sha256": approval.get("checkpoint_sha256"),
            "enrichment_evidence_sha256": digest({"prior": original, "live": live_result, "gate5d": historical, "district": district, "category": [category_name, category_id]}),
            "revised_proposal_sha256": digest(payload) if material_change else None,
            "reapproval_required": material_change,
            "readiness": readiness,
        }
        records.append(record)
    return records, {"active_categories_loaded": len(categories), "google_details_used": sum(item["latitude"] is not None for item in records), "gate5d_saved_records_available": len(gate5d_by_id)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch-id", default="all_completed_v1")
    parser.add_argument("--manifest", default=B6 + "approved_action_manifest.json")
    parser.add_argument("--prior-evidence", default=B1)
    parser.add_argument("--checkpoint", default=B5)
    parser.add_argument("--gate5d-consolidation", nargs="+", default=[GATE5D], help="One or more saved Gate 5D consolidations; no provider call is made.")
    parser.add_argument("--duplicate-clusters", default=B6 + "duplicate_cluster_review.json")
    parser.add_argument("--reports-dir", default="data/reports")
    args = parser.parse_args()
    manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    prior = {item["external_source_id"]: item for item in json.loads(Path(args.prior_evidence).read_text(encoding="utf-8")).get("records", [])}
    checkpoint = json.loads(Path(args.checkpoint).read_text(encoding="utf-8"))
    # New bounded batches add evidence; they must not erase the original
    # consolidation merely because a later batch has only five results.
    combined_results: dict[str, dict[str, Any]] = {}
    for path_string in args.gate5d_consolidation:
        for item in json.loads(Path(path_string).read_text(encoding="utf-8")).get("results", []):
            source_id = item.get("external_source_id")
            if source_id:
                combined_results[source_id] = item
    gate5d = {"results": list(combined_results.values())}
    clusters = json.loads(Path(args.duplicate_clusters).read_text(encoding="utf-8")).get("clusters", [])
    records, snapshot = asyncio.run(enrich(manifest=manifest, prior=prior, checkpoint=checkpoint, gate5d=gate5d, clusters=clusters))
    prefix = Path(args.reports_dir) / f"stage_10_1_3e_gate5e2c2_{args.batch_id}_"
    quarantined = [item for item in records if item["readiness"] == "QUARANTINED"]
    reapproval = [item for item in records if item["reapproval_required"]]
    ready = [item for item in records if item["readiness"] == "READY_FOR_REAPPROVAL"]
    district_results = [{"source_attraction_id": item["source_attraction_id"], **item["district_evidence"]} for item in records]
    category_results = [{"source_attraction_id": item["source_attraction_id"], "category_id": item["category_id"], "category_name": item["proposed_category_name"], "reason": item["category_evidence"]} for item in records]
    identity = [{"source_attraction_id": item["source_attraction_id"], "assessment": item["identity_assessment"], "conflicts": item["conflicts"], "existing_kb_duplicates": item["existing_kb_duplicates"]} for item in records]
    duplicate = {"clusters": [{**cluster, "members": [item for item in records if item["source_attraction_id"] in cluster.get("source_attraction_ids", [])]} for cluster in clusters]}
    preflight = {"dry_run": True, "postgresql_writes": False, "qdrant_writes": False, "status": "NOT_READY_FOR_WRITE" if quarantined else "READY_FOR_REAPPROVAL", "reasons": ["quarantined actions require verified metadata or cluster resolution"] if quarantined else []}
    payloads = {
        "metadata_enrichment_manifest": {"records": records, "read_only_snapshot": snapshot},
        "district_verification_results": {"records": district_results},
        "category_verification_results": {"records": category_results},
        "identity_revalidation_results": {"records": identity},
        "existing_kb_duplicate_audit": {"records": identity},
        "duplicate_cluster_resolution_proposals": duplicate,
        "reapproval_required_actions": {"records": reapproval},
        "enriched_sync_proposals": {"records": ready, "writes_executed": False},
        "remaining_quarantined_actions": {"records": quarantined},
        "ready_for_dry_run_actions": {"records": ready},
        "gate5e2c1_repreflight": preflight,
        "summary": {"approved_actions_examined": len(records), "reapproval_required": len(reapproval), "ready_for_dry_run": len(ready), "remaining_quarantined": len(quarantined), "external_api_requests": 0, "postgresql_writes": False, "qdrant_writes": False},
    }
    paths = {}
    for name, payload in payloads.items():
        path = prefix.with_name(prefix.name + name + ".json"); write_json(path, payload); paths[name] = str(path)
    csv_path = prefix.with_name(prefix.name + "reviewer_resolution_workbook.csv")
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["source_attraction_id", "official_name", "readiness", "conflicts", "reviewer_resolution", "notes"])
        writer.writeheader()
        for item in records:
            writer.writerow({"source_attraction_id": item["source_attraction_id"], "official_name": item["official_name"], "readiness": item["readiness"], "conflicts": "; ".join(item["conflicts"]), "reviewer_resolution": "DEFER", "notes": ""})
    paths["reviewer_resolution_workbook"] = str(csv_path)
    print(json.dumps({"mode": "offline_metadata_enrichment", "summary": payloads["summary"], "preflight": preflight, "reports": paths}, indent=2))


if __name__ == "__main__":
    main()
