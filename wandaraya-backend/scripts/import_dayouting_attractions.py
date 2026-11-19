"""Stage, verify and optionally promote DayOuting.lk attraction references.

Safe defaults:
* verifies the live robots/content signal before fetching;
* stages records without changing active recommendations;
* links exact, district-compatible identities to the official catalogue;
* requires ``--promote`` before creating active attractions;
* stores remote image references and attribution, never copies image files;
* never uses source content for model training.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

import psycopg
import requests
from psycopg.types.json import Jsonb

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.knowledge_base.connectors.dayouting import DayOutingCatalogue, DayOutingPlace


SOURCE_PROVIDER = "dayouting.lk"
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
DISALLOWED_TYPES = {
    "administrative_area_level_1", "administrative_area_level_2", "administrative_area_level_3",
    "country", "intersection", "locality", "neighborhood", "postal_code", "route",
    "street_address", "sublocality", "sublocality_level_1",
}
JUNK_NAME = re.compile(r"\b(junction|bus stop|railway crossing|road|roundabout|intersection)\b", re.I)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def database_dsn() -> str:
    value = os.getenv("DATABASE_URL", "postgresql://postgres:root@localhost:5432/wandaraya")
    return value.replace("postgresql+psycopg://", "postgresql://", 1)


def canonical_name(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.casefold()).strip()


def slugify(value: str, source_id: str) -> str:
    return f"{re.sub(r'[^a-z0-9]+', '-', value.casefold()).strip('-') or 'attraction'}-dayouting-{source_id}"


def fingerprint(record: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        if not raw or raw.lstrip().startswith("#") or "=" not in raw:
            continue
        key, value = raw.split("=", 1)
        # Batch commands must use the currently saved credential. Docker
        # containers can retain an older environment value after .env changes.
        os.environ[key.strip()] = value.strip().strip('"').strip("'")


def ensure_staging_table(cursor: psycopg.Cursor) -> None:
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS tourism_source_staging (
          id SERIAL PRIMARY KEY,
          source_provider VARCHAR(80) NOT NULL,
          external_source_id VARCHAR(255) NOT NULL,
          canonical_source_url TEXT NOT NULL,
          source_record_sha256 VARCHAR(64) NOT NULL,
          raw_record JSONB NOT NULL,
          mapped_theme VARCHAR(80), mapping_method VARCHAR(80),
          validation_status VARCHAR(50) NOT NULL DEFAULT 'pending',
          matched_attraction_id INTEGER REFERENCES attractions(id) ON DELETE SET NULL,
          google_place_id VARCHAR(255), google_evidence JSONB,
          import_batch_id VARCHAR(120), error_message TEXT,
          first_seen_at TIMESTAMPTZ NOT NULL, last_seen_at TIMESTAMPTZ NOT NULL,
          created_at TIMESTAMPTZ NOT NULL, updated_at TIMESTAMPTZ NOT NULL,
          CONSTRAINT uq_tourism_source_staging_identity UNIQUE(source_provider, external_source_id)
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS ix_tourism_source_staging_source_provider ON tourism_source_staging(source_provider)")
    cursor.execute("CREATE INDEX IF NOT EXISTS ix_tourism_source_staging_import_batch_id ON tourism_source_staging(import_batch_id)")


def current_attractions(cursor: psycopg.Cursor) -> dict[str, list[dict[str, Any]]]:
    cursor.execute("""
        SELECT a.id, a.name, d.name AS district
        FROM attractions a LEFT JOIN districts d ON d.id=a.district_id
        WHERE a.is_active=TRUE
    """)
    result: dict[str, list[dict[str, Any]]] = {}
    for attraction_id, name, district in cursor.fetchall():
        result.setdefault(canonical_name(name), []).append({"id": int(attraction_id), "name": name, "district": district})
    return result


def exact_identity(record: DayOutingPlace, existing: dict[str, list[dict[str, Any]]]) -> int | None:
    candidates = existing.get(canonical_name(record.name), [])
    if len(candidates) == 1:
        district = (record.district or "").casefold()
        candidate_district = (candidates[0]["district"] or "").casefold()
        if not district or not candidate_district or district == candidate_district:
            return candidates[0]["id"]
    return None


def source_quality(record: DayOutingPlace) -> tuple[str, str | None]:
    if JUNK_NAME.search(record.name):
        return "rejected_non_attraction_name", "Name indicates transport/road infrastructure, not a tourist attraction."
    if not record.district or record.district.casefold() in {"sri lanka", "unknown"}:
        return "pending_location_review", "A verified district is required."
    if not record.mapped_theme:
        return "pending_category_review", "No unambiguous WANDARAYA theme was mapped."
    if "ambiguous" in (record.mapping_method or ""):
        return "pending_category_review", "Conflicting source categories require a deterministic or human decision."
    if len(record.description.strip()) < 60:
        return "pending_content_review", "Description is too short for source-only verification."
    if record.latitude is None or record.longitude is None:
        return "pending_google_verification", "No source coordinates were available."
    return "source_verified_new", None


def stage_record(cursor: psycopg.Cursor, record: DayOutingPlace, batch_id: str, existing: dict[str, list[dict[str, Any]]]) -> str:
    raw = record.to_dict()
    matched = exact_identity(record, existing)
    status, error = ("linked_existing", None) if matched else source_quality(record)
    now = utcnow()
    cursor.execute("""
        INSERT INTO tourism_source_staging(
          source_provider, external_source_id, canonical_source_url, source_record_sha256, raw_record,
          mapped_theme, mapping_method, validation_status, matched_attraction_id, import_batch_id,
          error_message, first_seen_at, last_seen_at, created_at, updated_at
        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        ON CONFLICT(source_provider, external_source_id) DO UPDATE SET
          canonical_source_url=excluded.canonical_source_url,
          source_record_sha256=excluded.source_record_sha256,
          raw_record=excluded.raw_record,
          mapped_theme=excluded.mapped_theme,
          mapping_method=excluded.mapping_method,
          validation_status=CASE
            WHEN tourism_source_staging.validation_status IN ('promoted','google_verified_new','linked')
              THEN tourism_source_staging.validation_status
            ELSE excluded.validation_status END,
          matched_attraction_id=COALESCE(tourism_source_staging.matched_attraction_id, excluded.matched_attraction_id),
          import_batch_id=excluded.import_batch_id,
          error_message=excluded.error_message,
          last_seen_at=excluded.last_seen_at,
          updated_at=excluded.updated_at
    """, (
        SOURCE_PROVIDER, record.source_id, record.source_url, fingerprint(raw), Jsonb(raw),
        record.mapped_theme, record.mapping_method, status, matched, batch_id, error,
        now, now, now, now,
    ))
    return status


def google_verify(record: dict[str, Any], api_key: str) -> dict[str, Any]:
    query = f"{record['name']}, {record.get('city') or ''}, {record.get('district') or ''}, Sri Lanka"
    response = requests.post(
        "https://places.googleapis.com/v1/places:searchText",
        headers={
            "Content-Type": "application/json", "X-Goog-Api-Key": api_key,
            "X-Goog-FieldMask": "places.id,places.displayName,places.formattedAddress,places.location,places.primaryType,places.types,places.businessStatus",
        },
        json={"textQuery": query, "maxResultCount": 5}, timeout=30,
    )
    response.raise_for_status()
    wanted = canonical_name(record["name"])
    accepted = []
    for place in response.json().get("places", []):
        types = set(place.get("types") or [])
        if place.get("primaryType") in DISALLOWED_TYPES or types & DISALLOWED_TYPES:
            continue
        name = ((place.get("displayName") or {}).get("text") or "").strip()
        similarity = SequenceMatcher(None, wanted, canonical_name(name)).ratio()
        if similarity >= 0.72:
            accepted.append((similarity, place))
    if not accepted:
        return {}
    accepted.sort(key=lambda item: item[0], reverse=True)
    place_id = accepted[0][1]["id"]
    details = requests.get(
        f"https://places.googleapis.com/v1/places/{place_id}",
        headers={
            "X-Goog-Api-Key": api_key,
            "X-Goog-FieldMask": (
                "id,displayName,formattedAddress,addressComponents,location,primaryType,types,"
                "businessStatus,rating,userRatingCount,websiteUri,internationalPhoneNumber,"
                "regularOpeningHours,googleMapsUri"
            ),
        }, timeout=30,
    )
    details.raise_for_status()
    return {**details.json(), "identity_similarity": accepted[0][0]}


def google_place_details(place_id: str, api_key: str) -> dict[str, Any]:
    response = requests.get(
        f"https://places.googleapis.com/v1/places/{place_id}",
        headers={
            "X-Goog-Api-Key": api_key,
            "X-Goog-FieldMask": (
                "id,displayName,formattedAddress,addressComponents,location,primaryType,types,"
                "businessStatus,rating,userRatingCount,websiteUri,internationalPhoneNumber,"
                "regularOpeningHours,googleMapsUri"
            ),
        }, timeout=30,
    )
    response.raise_for_status()
    return response.json()


def refresh_promoted_google_details(cursor: psycopg.Cursor, api_key: str, limit: int, delay_seconds: float) -> dict[str, int]:
    cursor.execute("""
        SELECT id, matched_attraction_id, google_place_id, google_evidence
        FROM tourism_source_staging
        WHERE source_provider=%s AND validation_status='promoted' AND matched_attraction_id IS NOT NULL
          AND google_place_id IS NOT NULL AND NOT (google_evidence ? 'addressComponents')
        ORDER BY id LIMIT %s
    """, (SOURCE_PROVIDER, limit))
    rows = cursor.fetchall()
    stats = {"details_refreshed": 0, "details_errors": 0}
    for position, (staging_id, attraction_id, place_id, old_evidence) in enumerate(rows, 1):
        try:
            evidence = google_place_details(place_id, api_key)
        except requests.RequestException as exc:
            cursor.execute("UPDATE tourism_source_staging SET error_message=%s,updated_at=%s WHERE id=%s", (str(exc), utcnow(), staging_id))
            stats["details_errors"] += 1
        else:
            if old_evidence and old_evidence.get("identity_similarity") is not None:
                evidence["identity_similarity"] = old_evidence["identity_similarity"]
            cursor.execute("""
                UPDATE tourism_source_staging SET google_evidence=%s,error_message=NULL,updated_at=%s WHERE id=%s
            """, (Jsonb(evidence), utcnow(), staging_id))
            cursor.execute("""
                UPDATE attractions SET address=COALESCE(%s,address), latitude=COALESCE(%s,latitude),
                  longitude=COALESCE(%s,longitude), location=COALESCE(%s::json,location), rating=%s,
                  review_count=%s, phone_number=COALESCE(%s,phone_number), website_url=COALESCE(%s,website_url),
                  opening_hours=%s, updated_at=%s, last_sync_at=%s WHERE id=%s
            """, (
                evidence.get("formattedAddress"), (evidence.get("location") or {}).get("latitude"),
                (evidence.get("location") or {}).get("longitude"),
                Jsonb(evidence.get("location")) if evidence.get("location") else None,
                evidence.get("rating"), evidence.get("userRatingCount"), evidence.get("internationalPhoneNumber"),
                evidence.get("websiteUri"), Jsonb(evidence.get("regularOpeningHours")) if evidence.get("regularOpeningHours") else None,
                utcnow(), utcnow(), attraction_id,
            ))
            stats["details_refreshed"] += 1
        if position % 10 == 0 or position == len(rows):
            print(f"google details refreshed {position}/{len(rows)}", flush=True)
        if delay_seconds > 0:
            time.sleep(delay_seconds)
    return stats


def verify_staged_with_google(cursor: psycopg.Cursor, api_key: str, limit: int, delay_seconds: float = 0.4) -> dict[str, int]:
    cursor.execute("""
        SELECT id, raw_record FROM tourism_source_staging
        WHERE source_provider=%s AND validation_status IN
          ('source_verified_new','pending_google_verification','pending_location_review')
        ORDER BY id LIMIT %s
    """, (SOURCE_PROVIDER, limit))
    stats = {"google_verified": 0, "google_unmatched": 0, "google_errors": 0}
    rows = cursor.fetchall()
    for position, (staging_id, raw) in enumerate(rows, 1):
        evidence = None
        last_error = None
        for attempt in range(4):
            try:
                evidence = google_verify(raw, api_key)
                last_error = None
                break
            except requests.RequestException as exc:
                last_error = exc
                status = getattr(exc.response, "status_code", None)
                if status not in {429, 500, 502, 503, 504} or attempt == 3:
                    break
                retry_after = float(exc.response.headers.get("Retry-After", 0) or 0) if exc.response is not None else 0
                time.sleep(max(retry_after, 2 ** attempt))
        if last_error is not None:
            cursor.execute("UPDATE tourism_source_staging SET error_message=%s, updated_at=%s WHERE id=%s", (str(last_error), utcnow(), staging_id))
            stats["google_errors"] += 1
        elif evidence:
            cursor.execute("""
                UPDATE tourism_source_staging SET validation_status='google_verified_new', google_place_id=%s,
                  google_evidence=%s, error_message=NULL, updated_at=%s WHERE id=%s
            """, (evidence.get("id"), Jsonb(evidence), utcnow(), staging_id))
            stats["google_verified"] += 1
        else:
            cursor.execute("""
                UPDATE tourism_source_staging SET validation_status='pending_manual_identity_review',
                  error_message='Google Places returned no sufficiently similar non-locality attraction.', updated_at=%s WHERE id=%s
            """, (utcnow(), staging_id))
            stats["google_unmatched"] += 1
        if position % 10 == 0 or position == len(rows):
            print(f"google verified {position}/{len(rows)}", flush=True)
        if delay_seconds > 0:
            time.sleep(delay_seconds)
    return stats


def classify_staged_with_llm(cursor: psycopg.Cursor, api_key: str, limit: int, delay_seconds: float = 4.0) -> dict[str, int]:
    """Classify only ambiguous staged records; LLM output never bypasses identity checks."""
    cursor.execute("""
        SELECT id, raw_record FROM tourism_source_staging
        WHERE source_provider=%s AND validation_status='pending_category_review'
        ORDER BY id LIMIT %s
    """, (SOURCE_PROVIDER, limit))
    stats = {"llm_classified": 0, "llm_rejected": 0, "llm_errors": 0}
    allowed = list(THEME_ACTIVITIES)
    rows = cursor.fetchall()
    for position, (staging_id, raw) in enumerate(rows, 1):
        prompt = {
            "task": "Map this Sri Lankan tourist attraction to exactly one WANDARAYA theme.",
            "allowed_themes": allowed,
            "definitions": {
                "Pristine": "beaches, coast, bathing and unspoiled nature",
                "Heritage": "culture, history, archaeology and religious heritage",
                "Wild": "wildlife, bird watching and safari",
                "Thrills": "hiking, camping and adventure",
                "Bliss": "wellness, Ayurveda and relaxation",
                "Scenic": "waterfalls, viewpoints, rail journeys and landscapes",
                "Festive": "festivals and events",
                "Essence": "local food, crafts, markets and community experiences",
            },
            "record": {
                "name": raw.get("name"),
                "source_categories": raw.get("source_categories", []),
                "description_excerpt": (raw.get("description") or "")[:500],
            },
            "response_schema": {"theme": "one allowed theme", "confidence": "0..1", "reason": "short explanation"},
            "constraints": "Return JSON only. Do not invent attributes or locations.",
        }
        payload = {
            "model": os.getenv("DAYOUTING_LLM_MODEL", "openai/gpt-oss-20b"), "temperature": 0,
            "response_format": {"type": "json_object"},
            "messages": [{"role": "user", "content": json.dumps(prompt, ensure_ascii=False)}],
        }
        try:
            response = None
            for attempt in range(4):
                response = requests.post(
                    "https://api.groq.com/openai/v1/chat/completions",
                    headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                    json=payload, timeout=45,
                )
                if response.status_code != 429:
                    break
                retry_after = float(response.headers.get("Retry-After", 0) or 0)
                if attempt < 3:
                    time.sleep(max(retry_after, 2 ** attempt))
            assert response is not None
            response.raise_for_status()
            result = json.loads(response.json()["choices"][0]["message"]["content"])
            theme = result.get("theme")
            confidence = float(result.get("confidence", 0))
        except (requests.RequestException, KeyError, ValueError, TypeError, json.JSONDecodeError) as exc:
            cursor.execute("UPDATE tourism_source_staging SET error_message=%s, updated_at=%s WHERE id=%s", (f"LLM review failed: {exc}", utcnow(), staging_id))
            stats["llm_errors"] += 1
        else:
            if theme not in allowed or confidence < 0.80:
                cursor.execute("UPDATE tourism_source_staging SET error_message=%s, updated_at=%s WHERE id=%s", (f"LLM category confidence below gate: {confidence:.2f}", utcnow(), staging_id))
                stats["llm_rejected"] += 1
            else:
                raw["mapped_theme"] = theme
                raw["mapping_method"] = "llm_ambiguous_category_review"
                status = "source_verified_new" if raw.get("latitude") is not None and raw.get("longitude") is not None else "pending_google_verification"
                cursor.execute("""
                    UPDATE tourism_source_staging SET raw_record=%s, source_record_sha256=%s,
                      mapped_theme=%s, mapping_method='llm_ambiguous_category_review', validation_status=%s,
                      error_message=NULL, updated_at=%s WHERE id=%s
                """, (Jsonb(raw), fingerprint(raw), theme, status, utcnow(), staging_id))
                stats["llm_classified"] += 1
        if position % 10 == 0 or position == len(rows):
            print(f"llm reviewed {position}/{len(rows)}", flush=True)
        if delay_seconds > 0:
            time.sleep(delay_seconds)
    return stats


def ensure_source(cursor: psycopg.Cursor) -> int:
    cursor.execute("SELECT id FROM data_sources WHERE lower(name)=lower('DayOuting.lk') ORDER BY id LIMIT 1")
    row = cursor.fetchone()
    if row:
        cursor.execute("UPDATE data_sources SET source_type='supplemental_reference', base_url='https://dayouting.lk', trust_score=0.70, is_active=TRUE, last_sync_at=%s, updated_at=%s WHERE id=%s", (utcnow(), utcnow(), row[0]))
        return int(row[0])
    cursor.execute("""
        INSERT INTO data_sources(name,source_type,base_url,trust_score,is_active,created_at,last_sync_at,updated_at)
        VALUES ('DayOuting.lk','supplemental_reference','https://dayouting.lk',0.70,TRUE,%s,%s,%s) RETURNING id
    """, (utcnow(), utcnow(), utcnow()))
    return int(cursor.fetchone()[0])


def link_existing(cursor: psycopg.Cursor, source_id: int) -> int:
    cursor.execute("""
        SELECT id, external_source_id, canonical_source_url, raw_record, matched_attraction_id
        FROM tourism_source_staging
        WHERE source_provider=%s AND validation_status='linked_existing' AND matched_attraction_id IS NOT NULL
    """, (SOURCE_PROVIDER,))
    linked = 0
    for staging_id, external_id, url, raw, attraction_id in cursor.fetchall():
        cursor.execute("""
            INSERT INTO attraction_source_references(attraction_id,source_provider,external_source_id,canonical_source_url,source_title,identity_status,discovered_at,last_verified_at,created_at,updated_at)
            VALUES (%s,%s,%s,%s,%s,'exact_name_district_match',%s,%s,%s,%s)
            ON CONFLICT(source_provider,external_source_id) DO UPDATE SET attraction_id=excluded.attraction_id,
              canonical_source_url=excluded.canonical_source_url, source_title=excluded.source_title,
              last_verified_at=excluded.last_verified_at, updated_at=excluded.updated_at
        """, (attraction_id, SOURCE_PROVIDER, external_id, url, raw["name"], utcnow(), utcnow(), utcnow(), utcnow()))
        content_hash = hashlib.sha256(raw["description"].encode()).hexdigest()
        cursor.execute("""
            SELECT 1 FROM attraction_descriptions WHERE attraction_id=%s AND source_id=%s AND content_hash=%s
        """, (attraction_id, source_id, content_hash))
        if not cursor.fetchone():
            cursor.execute("""
                INSERT INTO attraction_descriptions(attraction_id,source_id,title,description,source_url,language,content_hash,retrieved_at,is_active,created_at,updated_at)
                VALUES (%s,%s,%s,%s,%s,'en',%s,%s,TRUE,%s,%s)
            """, (attraction_id, source_id, raw["name"], raw["description"], url, content_hash, utcnow(), utcnow(), utcnow()))
        cursor.execute("UPDATE tourism_source_staging SET validation_status='linked', updated_at=%s WHERE id=%s", (utcnow(), staging_id))
        linked += 1
    return linked


def promote_new(cursor: psycopg.Cursor, source_id: int, *, allow_source_only: bool) -> int:
    statuses = ["google_verified_new"]
    if allow_source_only:
        statuses.append("source_verified_new")
    cursor.execute("""
        SELECT id, external_source_id, canonical_source_url, raw_record, google_place_id, google_evidence
        FROM tourism_source_staging WHERE source_provider=%s AND validation_status=ANY(%s)
        ORDER BY id
    """, (SOURCE_PROVIDER, statuses))
    staged_rows = cursor.fetchall()
    category_ids = dict(cursor.execute("SELECT name,id FROM categories").fetchall())
    activity_ids = dict(cursor.execute("SELECT name,id FROM activities").fetchall())
    district_ids = {name.casefold(): identifier for name, identifier in cursor.execute("SELECT name,id FROM districts").fetchall()}
    district_ids["monaragala"] = district_ids.get("moneragala")
    promoted = 0
    for staging_id, external_id, url, raw, google_place_id, evidence in staged_rows:
        google = evidence or {}
        if google_place_id:
            cursor.execute("SELECT id FROM attractions WHERE google_place_id=%s", (google_place_id,))
            existing_google = cursor.fetchone()
            if existing_google:
                attraction_id = int(existing_google[0])
                cursor.execute("""
                    INSERT INTO attraction_source_references(attraction_id,source_provider,external_source_id,canonical_source_url,source_title,identity_status,discovered_at,last_verified_at,created_at,updated_at)
                    VALUES (%s,%s,%s,%s,%s,'google_place_id_match',%s,%s,%s,%s)
                    ON CONFLICT(source_provider,external_source_id) DO UPDATE SET attraction_id=excluded.attraction_id,
                      identity_status=excluded.identity_status,last_verified_at=excluded.last_verified_at,updated_at=excluded.updated_at
                """, (attraction_id, SOURCE_PROVIDER, external_id, url, raw["name"], utcnow(), utcnow(), utcnow(), utcnow()))
                content_hash = hashlib.sha256(raw["description"].encode()).hexdigest()
                cursor.execute("SELECT 1 FROM attraction_descriptions WHERE attraction_id=%s AND source_id=%s AND content_hash=%s", (attraction_id, source_id, content_hash))
                if not cursor.fetchone():
                    cursor.execute("""
                        INSERT INTO attraction_descriptions(attraction_id,source_id,title,description,source_url,language,content_hash,retrieved_at,is_active,created_at,updated_at)
                        VALUES (%s,%s,%s,%s,%s,'en',%s,%s,TRUE,%s,%s)
                    """, (attraction_id, source_id, raw["name"], raw["description"], url, content_hash, utcnow(), utcnow(), utcnow()))
                cursor.execute("UPDATE tourism_source_staging SET validation_status='linked', matched_attraction_id=%s, updated_at=%s WHERE id=%s", (attraction_id, utcnow(), staging_id))
                continue
        district_id = district_ids.get((raw.get("district") or "").casefold())
        if district_id is None:
            for component in google.get("addressComponents") or []:
                if "administrative_area_level_2" in (component.get("types") or []):
                    district_id = district_ids.get((component.get("longText") or "").casefold())
                    if district_id is not None:
                        break
        if district_id is None and google.get("formattedAddress"):
            address = google["formattedAddress"].casefold()
            matches = [identifier for name, identifier in district_ids.items() if identifier and re.search(rf"\b{re.escape(name)}\b", address)]
            if len(set(matches)) == 1:
                district_id = matches[0]
        if district_id is None or raw.get("mapped_theme") not in category_ids:
            continue
        location = google.get("location") or {}
        latitude = raw.get("latitude") if raw.get("latitude") is not None else location.get("latitude")
        longitude = raw.get("longitude") if raw.get("longitude") is not None else location.get("longitude")
        cursor.execute("""
            INSERT INTO attractions(name,slug,description,address,district_id,city,latitude,longitude,location,
              google_place_id,rating,review_count,phone_number,website_url,opening_hours,
              vibe_tags,experience_tags,is_active,created_at,updated_at,last_sync_at)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,TRUE,%s,%s,%s) RETURNING id
        """, (
            raw["name"], slugify(raw["name"], external_id), raw["description"], google.get("formattedAddress"),
            district_id, raw.get("city"), latitude, longitude,
            Jsonb({"latitude": latitude, "longitude": longitude}) if latitude is not None and longitude is not None else None,
            google_place_id, google.get("rating"), google.get("userRatingCount"),
            google.get("internationalPhoneNumber"), google.get("websiteUri") or url,
            Jsonb(google.get("regularOpeningHours")) if google.get("regularOpeningHours") else None,
            Jsonb([raw["mapped_theme"]]),
            Jsonb({"dayouting_categories": raw.get("source_categories", []), "map_url": raw.get("map_url"), "video_url": raw.get("video_url")}),
            utcnow(), utcnow(), utcnow(),
        ))
        attraction_id = int(cursor.fetchone()[0])
        content_hash = hashlib.sha256(raw["description"].encode()).hexdigest()
        cursor.execute("""
            INSERT INTO attraction_descriptions(attraction_id,source_id,title,description,source_url,language,content_hash,retrieved_at,is_active,created_at,updated_at)
            VALUES (%s,%s,%s,%s,%s,'en',%s,%s,TRUE,%s,%s)
        """, (attraction_id, source_id, raw["name"], raw["description"], url, content_hash, utcnow(), utcnow(), utcnow()))
        cursor.execute("""
            INSERT INTO attraction_source_references(attraction_id,source_provider,external_source_id,canonical_source_url,source_title,identity_status,discovered_at,last_verified_at,created_at,updated_at)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        """, (attraction_id, SOURCE_PROVIDER, external_id, url, raw["name"], "google_verified" if google_place_id else "source_coordinates_verified", utcnow(), utcnow(), utcnow(), utcnow()))
        cursor.execute("""
            INSERT INTO attraction_categories(attraction_id,category_id,is_primary,confidence_score,created_at,updated_at)
            VALUES (%s,%s,TRUE,%s,%s,%s)
        """, (attraction_id, category_ids[raw["mapped_theme"]], 0.92 if google_place_id else 0.78, utcnow(), utcnow()))
        for activity in THEME_ACTIVITIES[raw["mapped_theme"]]:
            if activity in activity_ids:
                cursor.execute("""
                    INSERT INTO attraction_activities(attraction_id,activity_id,suitability_score,is_available,created_at)
                    VALUES (%s,%s,0.75,TRUE,%s)
                """, (attraction_id, activity_ids[activity], utcnow()))
        for index, image_url in enumerate(raw.get("image_urls") or []):
            cursor.execute("""
                INSERT INTO attraction_images(attraction_id,source_id,source_type,original_url,external_image_id,attribution,is_primary,is_active,retrieved_at,last_sync_at,created_at,updated_at)
                VALUES (%s,%s,'dayouting_reference',%s,%s,%s,%s,TRUE,%s,%s,%s,%s)
            """, (attraction_id, source_id, image_url, hashlib.sha256(image_url.encode()).hexdigest(),
                  Jsonb({"source":"DayOuting.lk","source_url":url,"rights":"remote reference only; original owner retains rights"}),
                  index == 0, utcnow(), utcnow(), utcnow(), utcnow()))
        cursor.execute("UPDATE tourism_source_staging SET validation_status='promoted', matched_attraction_id=%s, updated_at=%s WHERE id=%s", (attraction_id, utcnow(), staging_id))
        promoted += 1
    return promoted


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0, help="Limit source records for a pilot; 0 means all sitemap records.")
    parser.add_argument("--delay", type=float, default=0.35)
    parser.add_argument("--skip-categories", action="store_true")
    parser.add_argument("--use-staged", action="store_true", help="Skip crawling and operate on the existing staging table.")
    parser.add_argument("--llm-review", action="store_true", help="Use the configured Groq model only for ambiguous category records.")
    parser.add_argument("--llm-limit", type=int, default=25)
    parser.add_argument("--llm-delay", type=float, default=4.0, help="Seconds between Groq review requests.")
    parser.add_argument("--google-verify", action="store_true", help="Verify staged new identities with Google Places (billable API).")
    parser.add_argument("--google-limit", type=int, default=25)
    parser.add_argument("--google-delay", type=float, default=0.4, help="Seconds between Google verification requests.")
    parser.add_argument("--refresh-promoted-details", action="store_true")
    parser.add_argument("--refresh-limit", type=int, default=100)
    parser.add_argument("--promote", action="store_true", help="Link/promote approved staged records into the active catalogue.")
    parser.add_argument("--allow-source-only", action="store_true", help="Promote records with source map coordinates without Google verification.")
    parser.add_argument("--report", type=Path, default=ROOT / "data" / "reports" / "dayouting_import_audit.json")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    load_env_file(ROOT / ".env")
    catalogue = DayOutingCatalogue(delay_seconds=args.delay)
    signals = catalogue.verify_live_policy()
    urls = [] if args.use_staged else catalogue.place_urls()
    if args.limit and not args.use_staged:
        urls = urls[: args.limit]
    memberships = {} if args.skip_categories or args.use_staged else catalogue.category_memberships()
    batch_id = f"dayouting-{utcnow().strftime('%Y%m%dT%H%M%SZ')}"
    report: dict[str, Any] = {
        "batch_id": batch_id, "content_signals": signals, "sitemap_records": len(urls),
        "policy": "reference-only; prohibited from AI training; remote images are not downloaded",
        "staged": {}, "fetch_errors": [],
    }
    with psycopg.connect(database_dsn()) as connection:
        with connection.cursor() as cursor:
            ensure_staging_table(cursor)
            existing = current_attractions(cursor)
            for index, url in enumerate(urls, 1):
                source_id = url.split("/places-to-visit/", 1)[1].split("/", 1)[0]
                try:
                    record = catalogue.fetch_place(url, memberships.get(source_id, []))
                    status = stage_record(cursor, record, batch_id, existing)
                    report["staged"][status] = report["staged"].get(status, 0) + 1
                except Exception as exc:  # one bad source record must not discard the completed audit
                    report["fetch_errors"].append({"url": url, "error": str(exc)})
                if index % 50 == 0:
                    connection.commit()
                    print(f"staged {index}/{len(urls)}", flush=True)
            llm_stats = {}
            if args.llm_review:
                api_key = os.getenv("GROQ_API_KEY", "")
                if not api_key:
                    raise RuntimeError("--llm-review requested but GROQ_API_KEY is not configured")
                llm_stats = classify_staged_with_llm(cursor, api_key, args.llm_limit, args.llm_delay)
            google_stats = {}
            refresh_stats = {}
            if args.google_verify:
                api_key = os.getenv("GOOGLE_PLACES_API_KEY", "")
                if not api_key:
                    raise RuntimeError("--google-verify requested but GOOGLE_PLACES_API_KEY is not configured")
                google_stats = verify_staged_with_google(cursor, api_key, args.google_limit, args.google_delay)
            if args.refresh_promoted_details:
                api_key = os.getenv("GOOGLE_PLACES_API_KEY", "")
                if not api_key:
                    raise RuntimeError("--refresh-promoted-details requested but GOOGLE_PLACES_API_KEY is not configured")
                refresh_stats = refresh_promoted_google_details(cursor, api_key, args.refresh_limit, args.google_delay)
            promotion = {"linked_existing": 0, "promoted_new": 0}
            if args.promote:
                data_source_id = ensure_source(cursor)
                promotion["linked_existing"] = link_existing(cursor, data_source_id)
                promotion["promoted_new"] = promote_new(cursor, data_source_id, allow_source_only=args.allow_source_only)
            connection.commit()
    report["google"] = google_stats
    report["google_refresh"] = refresh_stats
    report["llm"] = llm_stats
    report["promotion"] = promotion
    report["fetch_error_count"] = len(report["fetch_errors"])
    report["completed_at"] = utcnow().isoformat()
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if not report["fetch_errors"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
