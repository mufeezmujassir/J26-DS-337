"""Replace contaminated attraction data with the official Sri Lanka Tourism catalogue.

The command fetches and validates the complete catalogue before opening the
destructive database transaction.  District weather, climate/seasonality,
holiday/calendar and event tables are deliberately preserved.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
from datetime import datetime, timezone
from difflib import SequenceMatcher
from typing import Any

import psycopg
import requests
from psycopg.types.json import Jsonb
from qdrant_client import QdrantClient

from app.knowledge_base.connectors.srilanka_travel import (
    THEMES,
    OfficialAttraction,
    SriLankaTravelCatalogue,
)


DISTRICT_ALIASES = {
    "nuwaraeliya": "Nuwara Eliya", "nuwara eliya": "Nuwara Eliya",
    "trincomalee": "Trincomalee", "jaffna": "Jaffna", "galle": "Galle",
    "colombo": "Colombo", "gampaha": "Gampaha", "kalutara": "Kalutara",
    "kandy": "Kandy", "matale": "Matale", "matara": "Matara",
    "hambantota": "Hambantota", "badulla": "Badulla", "monaragala": "Monaragala",
    "ratnapura": "Ratnapura", "kegalle": "Kegalle", "kurunegala": "Kurunegala",
    "puttalam": "Puttalam", "anuradhapura": "Anuradhapura", "polonnaruwa": "Polonnaruwa",
    "batticaloa": "Batticaloa", "ampara": "Ampara", "kilinochchi": "Kilinochchi",
    "mannar": "Mannar", "mullaitivu": "Mullaitivu", "vavuniya": "Vavuniya",
    "bandarawela": "Badulla", "beruwala": "Kalutara", "dambulla": "Matale",
    "dehiwala": "Colombo", "kalpitiya": "Puttalam", "kataragama": "Moneragala",
    "negombo": "Gampaha",
}

THEME_ACTIVITIES = {
    "Pristine": ("Nature sightseeing", "Photography"),
    "Heritage": ("Cultural sightseeing", "Historical exploration"),
    "Wild": ("Wildlife observation", "Nature sightseeing"),
    "Thrills": ("Outdoor adventure", "Hiking"),
    "Bliss": ("Wellness", "Relaxation"),
    "Scenic": ("Photography", "Scenic sightseeing"),
    "Festive": ("Festival participation", "Cultural experience"),
    "Essence": ("Local experience", "Cultural sightseeing"),
}

DISALLOWED_GOOGLE_TYPES = {
    "administrative_area_level_1", "administrative_area_level_2", "administrative_area_level_3",
    "country", "intersection", "locality", "neighborhood", "postal_code", "route",
    "street_address", "sublocality", "sublocality_level_1",
}


def slugify(value: str, source_id: str) -> str:
    value = re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-")
    return f"{value or 'attraction'}-{source_id}"


def distance_km(a_lat: float, a_lon: float, b_lat: float, b_lon: float) -> float:
    p1, p2 = math.radians(a_lat), math.radians(b_lat)
    dp, dl = math.radians(b_lat - a_lat), math.radians(b_lon - a_lon)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 6371.0088 * 2 * math.asin(math.sqrt(h))


def database_dsn() -> str:
    value = os.getenv("DATABASE_URL", "postgresql://postgres:root@localhost:5432/wandaraya")
    return value.replace("postgresql+psycopg://", "postgresql://", 1)


def google_enrichment(record: OfficialAttraction, api_key: str) -> dict[str, Any]:
    query = f"{record.name}, {record.destination or ''}, Sri Lanka"
    headers = {
        "Content-Type": "application/json", "X-Goog-Api-Key": api_key,
        "X-Goog-FieldMask": "places.id,places.displayName,places.formattedAddress,places.location,places.primaryType,places.types,places.businessStatus",
    }
    response = requests.post(
        "https://places.googleapis.com/v1/places:searchText",
        headers=headers, json={"textQuery": query, "maxResultCount": 5}, timeout=30,
    )
    response.raise_for_status()
    candidates = []
    wanted = " ".join(record.name.casefold().split())
    for place in response.json().get("places", []):
        types = set(place.get("types") or [])
        primary = place.get("primaryType")
        if primary in DISALLOWED_GOOGLE_TYPES or types & DISALLOWED_GOOGLE_TYPES:
            continue
        candidate_name = ((place.get("displayName") or {}).get("text") or "").strip()
        similarity = SequenceMatcher(None, wanted, " ".join(candidate_name.casefold().split())).ratio()
        location = place.get("location") or {}
        distance = None
        if record.latitude is not None and record.longitude is not None and location.get("latitude") is not None:
            distance = distance_km(record.latitude, record.longitude, float(location["latitude"]), float(location["longitude"]))
        if similarity < 0.72 or (distance is not None and distance > 20):
            continue
        score = similarity - (min(distance, 20) / 100 if distance is not None else 0.1)
        candidates.append((score, place))
    if not candidates:
        return {}
    candidates.sort(key=lambda item: item[0], reverse=True)
    place_id = candidates[0][1]["id"]
    detail_headers = {
        "X-Goog-Api-Key": api_key,
        "X-Goog-FieldMask": "id,displayName,formattedAddress,addressComponents,location,primaryType,types,rating,userRatingCount,websiteUri,internationalPhoneNumber,regularOpeningHours,businessStatus,googleMapsUri",
    }
    detail = requests.get(f"https://places.googleapis.com/v1/places/{place_id}", headers=detail_headers, timeout=30)
    detail.raise_for_status()
    return detail.json()


def reset_attraction_domain(cursor: psycopg.Cursor) -> None:
    # CASCADE clears every table whose rows refer to an attraction, including
    # attraction-specific climate mappings, without touching district climate.
    cursor.execute("""
        TRUNCATE TABLE
          tourism_import_batches,
          attractions,
          categories,
          activities
        RESTART IDENTITY CASCADE
    """)


def seed_taxonomy(cursor: psycopg.Cursor) -> tuple[dict[str, int], dict[str, int]]:
    categories: dict[str, int] = {}
    for name in THEMES.values():
        cursor.execute(
            "INSERT INTO categories(name, description, is_active, created_at, updated_at) VALUES (%s, %s, TRUE, %s, %s) RETURNING id",
            (name, f"Official Sri Lanka Tourism travel theme: {name}.", datetime.now(timezone.utc), datetime.now(timezone.utc)),
        )
        categories[name] = cursor.fetchone()[0]
    activities: dict[str, int] = {}
    for name in sorted({item for values in THEME_ACTIVITIES.values() for item in values}):
        cursor.execute(
            "INSERT INTO activities(name, description, is_active, created_at) VALUES (%s, %s, TRUE, %s) RETURNING id",
            (name, "Deterministically mapped from the official tourism theme and description.", datetime.now(timezone.utc)),
        )
        activities[name] = cursor.fetchone()[0]
    return categories, activities


def district_ids(cursor: psycopg.Cursor) -> dict[str, int]:
    cursor.execute("SELECT id, name FROM districts")
    return {str(name).casefold(): int(identifier) for identifier, name in cursor.fetchall()}


def prepare_google(records: list[OfficialAttraction], api_key: str | None) -> tuple[dict[str, dict[str, Any]], dict[str, int]]:
    if not api_key:
        return {}, {"google_enriched": 0, "google_unmatched": 0, "google_duplicate_identity_rejected": 0, "google_errors": 0}
    prepared: dict[str, dict[str, Any]] = {}
    used: set[str] = set()
    stats = {"google_enriched": 0, "google_unmatched": 0, "google_duplicate_identity_rejected": 0, "google_errors": 0}
    for record in records:
        try:
            detail = google_enrichment(record, api_key)
        except requests.RequestException:
            stats["google_errors"] += 1
            detail = {}
        if detail.get("id") in used:
            stats["google_duplicate_identity_rejected"] += 1
            detail = {}
        if detail:
            used.add(detail["id"])
            stats["google_enriched"] += 1
        else:
            stats["google_unmatched"] += 1
        prepared[record.source_id] = detail
    return prepared, stats


def load_records(cursor: psycopg.Cursor, records: list[OfficialAttraction], google_records: dict[str, dict[str, Any]], google_stats: dict[str, int]) -> dict[str, int]:
    cursor.execute("SELECT id FROM data_sources WHERE lower(name)=lower(%s) ORDER BY id LIMIT 1", ("Sri Lanka Tourism",))
    existing_source = cursor.fetchone()
    if existing_source:
        source_id = int(existing_source[0])
        cursor.execute(
            "UPDATE data_sources SET source_type=%s, base_url=%s, trust_score=1.0, is_active=TRUE, updated_at=%s, last_sync_at=%s WHERE id=%s",
            ("official_tourism_authority", "https://srilanka.travel", datetime.now(timezone.utc), datetime.now(timezone.utc), source_id),
        )
    else:
        cursor.execute(
            "INSERT INTO data_sources(name, source_type, base_url, trust_score, is_active, created_at, updated_at, last_sync_at) VALUES (%s,%s,%s,%s,TRUE,%s,%s,%s) RETURNING id",
            ("Sri Lanka Tourism", "official_tourism_authority", "https://srilanka.travel", 1.0, datetime.now(timezone.utc), datetime.now(timezone.utc), datetime.now(timezone.utc)),
        )
        source_id = int(cursor.fetchone()[0])
    categories, activities = seed_taxonomy(cursor)
    districts = district_ids(cursor)
    stats = {"inserted": 0, "missing_district": 0, "images": 0, **google_stats}
    for record in records:
        google = google_records.get(record.source_id, {})
        location = google.get("location") or {}
        destination_key = (record.destination or "").casefold().replace("district", "").strip()
        canonical_district = DISTRICT_ALIASES.get(destination_key, record.destination or "")
        district_id = districts.get(canonical_district.casefold())
        if district_id is None:
            stats["missing_district"] += 1
        latitude = record.latitude if record.latitude is not None else location.get("latitude")
        longitude = record.longitude if record.longitude is not None else location.get("longitude")
        cursor.execute("""
            INSERT INTO attractions(
              name, slug, description, address, district_id, city, latitude, longitude, location,
              google_place_id, rating, review_count, phone_number, website_url, opening_hours,
              vibe_tags, experience_tags, is_active, created_at, updated_at, last_sync_at
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,TRUE,%s,%s,%s)
            RETURNING id
        """, (
            record.name, slugify(record.name, record.source_id), record.description,
            google.get("formattedAddress"), district_id, record.destination, latitude, longitude,
            Jsonb({"latitude": latitude, "longitude": longitude}) if latitude is not None and longitude is not None else None,
            google.get("id"), google.get("rating"), google.get("userRatingCount"),
            google.get("internationalPhoneNumber"), record.source_url,
            Jsonb(google.get("regularOpeningHours")) if google.get("regularOpeningHours") else None,
            Jsonb([record.theme] if record.theme else []),
            Jsonb({"official_theme": record.theme, "useful_information": record.useful_information}),
            datetime.now(timezone.utc), datetime.now(timezone.utc), datetime.now(timezone.utc),
        ))
        attraction_id = int(cursor.fetchone()[0])
        stats["inserted"] += 1
        description_hash = hashlib.sha256(record.description.encode("utf-8")).hexdigest()
        cursor.execute("""
            INSERT INTO attraction_descriptions(attraction_id, source_id, title, description, source_url, language, content_hash, retrieved_at, is_active, created_at, updated_at)
            VALUES (%s,%s,%s,%s,%s,'en',%s,%s,TRUE,%s,%s)
        """, (attraction_id, source_id, record.name, record.description, record.source_url, description_hash, datetime.now(timezone.utc), datetime.now(timezone.utc), datetime.now(timezone.utc)))
        cursor.execute("""
            INSERT INTO attraction_source_references(attraction_id, source_provider, external_source_id, canonical_source_url, source_title, identity_status, discovered_at, last_verified_at, created_at, updated_at)
            VALUES (%s,'srilanka.travel',%s,%s,%s,'official_source_verified',%s,%s,%s,%s)
        """, (attraction_id, record.source_id, record.source_url, record.name, datetime.now(timezone.utc), datetime.now(timezone.utc), datetime.now(timezone.utc), datetime.now(timezone.utc)))
        if record.theme:
            cursor.execute("INSERT INTO attraction_categories(attraction_id, category_id, is_primary, confidence_score, created_at, updated_at) VALUES (%s,%s,TRUE,1.0,%s,%s)", (attraction_id, categories[record.theme], datetime.now(timezone.utc), datetime.now(timezone.utc)))
            for activity in THEME_ACTIVITIES[record.theme]:
                cursor.execute("INSERT INTO attraction_activities(attraction_id, activity_id, suitability_score, is_available, created_at) VALUES (%s,%s,0.85,TRUE,%s)", (attraction_id, activities[activity], datetime.now(timezone.utc)))
        for index, image_url in enumerate(record.images):
            image_id = hashlib.sha256(image_url.encode("utf-8")).hexdigest()
            cursor.execute("""
                INSERT INTO attraction_images(attraction_id, source_id, source_type, original_url, external_image_id, attribution, is_primary, is_active, retrieved_at, last_sync_at, created_at, updated_at)
                VALUES (%s,%s,'srilanka_travel',%s,%s,%s,%s,TRUE,%s,%s,%s,%s)
            """, (attraction_id, source_id, image_url, image_id, Jsonb({"source": "Sri Lanka Tourism", "source_url": record.source_url}), index == 0, datetime.now(timezone.utc), datetime.now(timezone.utc), datetime.now(timezone.utc), datetime.now(timezone.utc)))
            stats["images"] += 1
    return stats


def clear_qdrant(urls: list[str]) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    for url in urls:
        client = QdrantClient(url=url)
        deleted = []
        for collection in client.get_collections().collections:
            if collection.name.startswith("sri_lanka_attractions"):
                client.delete_collection(collection.name)
                deleted.append(collection.name)
        result[url] = deleted
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--confirm-delete-contaminated-attractions", action="store_true")
    parser.add_argument("--google-enrich", action="store_true")
    parser.add_argument("--delay-seconds", type=float, default=0.25)
    parser.add_argument(
        "--sitemap-file",
        help="Saved srilanka.travel XML sitemap used to verify and locate the attraction catalogue.",
    )
    parser.add_argument("--qdrant-url", action="append", default=[])
    args = parser.parse_args()
    if not args.execute:
        raise SystemExit("This replacement requires --execute after a database backup is created.")
    if not args.confirm_delete_contaminated_attractions:
        raise SystemExit("Refusing cleanup without --confirm-delete-contaminated-attractions")

    sitemap_xml = None
    if args.sitemap_file:
        with open(args.sitemap_file, encoding="utf-8-sig") as sitemap_handle:
            sitemap_xml = sitemap_handle.read()
    records = SriLankaTravelCatalogue(delay_seconds=args.delay_seconds).fetch_all(sitemap_xml=sitemap_xml)
    if len(records) != 169:
        raise SystemExit(f"Expected the official 169-attraction catalogue, received {len(records)}; database unchanged.")
    google_key = os.getenv("GOOGLE_PLACES_API_KEY") if args.google_enrich else None
    if args.google_enrich and not google_key:
        raise SystemExit("--google-enrich requires GOOGLE_PLACES_API_KEY; database unchanged.")

    google_records, google_stats = prepare_google(records, google_key)

    with psycopg.connect(database_dsn()) as connection:
        with connection.cursor() as cursor:
            reset_attraction_domain(cursor)
            stats = load_records(cursor, records, google_records, google_stats)
        connection.commit()
    qdrant = clear_qdrant(args.qdrant_url) if args.qdrant_url else {}
    print(json.dumps({"official_catalogue": len(records), **stats, "qdrant_deleted": qdrant}, indent=2))


if __name__ == "__main__":
    main()
