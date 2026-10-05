from __future__ import annotations

import argparse
import asyncio
import logging
from collections import Counter

from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.knowledge_base.connectors.google_places import GooglePlacesConnector
from app.knowledge_base.discovery.attraction_discovery import DiscoveredPlace
from app.knowledge_base.pipelines.attraction_ingestion_pipeline import (
    AttractionIngestionPipeline,
)
from app.models.attraction import Attraction

TEST_LATITUDE = 7.2906
TEST_LONGITUDE = 80.6337
TEST_RADIUS_METERS = 15_000
TEST_TYPES = [
    "tourist_attraction",
    "historical_landmark",
    "scenic_spot",
]
TEST_INGEST_LIMIT = 3

logger = logging.getLogger(__name__)


async def main(*, ingest: bool = False) -> int:
    print("=" * 75)
    print("WANDARAYA ATTRACTION DISCOVERY TEST")
    print("=" * 75)
    print(f"Latitude:  {TEST_LATITUDE}")
    print(f"Longitude: {TEST_LONGITUDE}")
    print(f"Radius:    {TEST_RADIUS_METERS} meters")
    print(f"Types:     {TEST_TYPES}")
    print(f"Ingest:    {'yes' if ingest else 'no (discovery only)'}")

    connector = GooglePlacesConnector()
    discovered: dict[str, DiscoveredPlace] = {}
    raw_result_count = 0
    type_counts: Counter[str] = Counter()
    errors: list[str] = []

    for place_type in TEST_TYPES:
        print(f"\nSearching type: {place_type}")
        try:
            results = await connector.search_nearby(
                latitude=TEST_LATITUDE,
                longitude=TEST_LONGITUDE,
                radius_meters=TEST_RADIUS_METERS,
                included_types=[place_type],
                max_results=20,
            )
        except Exception as exc:
            message = f"{place_type}: {exc}"
            errors.append(message)
            logger.exception("Google Places discovery request failed: %s", message)
            print(f"[ERROR] {message}")
            continue

        print(f"Raw results: {len(results)}")
        raw_result_count += len(results)
        type_counts[place_type] += len(results)

        for place in results:
            place_id = place.get("id")
            if not place_id:
                logger.warning("Skipping Google result without a place ID.")
                continue

            display_name = place.get("displayName")
            if isinstance(display_name, dict):
                name = display_name.get("text")
            else:
                name = str(display_name) if display_name is not None else None
            location = place.get("location") or {}

            discovered_place = discovered.get(place_id)
            if discovered_place is None:
                discovered_place = DiscoveredPlace(
                    place_id=place_id,
                    name=name,
                    latitude=location.get("latitude"),
                    longitude=location.get("longitude"),
                    primary_type=place.get("primaryType"),
                )
                discovered[place_id] = discovered_place
            discovered_place.discovered_by_types.add(place_type)

    discovered_ids = list(discovered)
    async with AsyncSessionLocal() as db:
        if discovered_ids:
            query_result = await db.execute(
                select(Attraction.google_place_id).where(
                    Attraction.google_place_id.in_(discovered_ids)
                )
            )
            existing_ids = {
                place_id for place_id in query_result.scalars() if place_id
            }
        else:
            existing_ids = set()

        new_ids = [
            place_id for place_id in discovered_ids if place_id not in existing_ids
        ]

        print("\nUNIQUE DISCOVERED PLACES")
        print("=" * 75)
        for index, place in enumerate(discovered.values(), start=1):
            print(
                f"[{index}] {place.name or 'Unnamed'} | "
                f"id={place.place_id} | "
                f"primary_type={place.primary_type} | "
                f"location={place.latitude}, {place.longitude} | "
                f"found_by={', '.join(sorted(place.discovered_by_types))}"
            )

        print("\nDISCOVERY SUMMARY")
        print("=" * 75)
        print(f"Raw Google results: {raw_result_count}")
        print(f"Unique places:      {len(discovered)}")
        print(f"Already in database: {len(existing_ids)}")
        print(f"New place IDs:      {len(new_ids)}")
        for place_type, count in type_counts.items():
            print(f"  {place_type:<25} {count}")

        if ingest and new_ids:
            ingest_ids = new_ids[:TEST_INGEST_LIMIT]
            print(
                f"\nIngesting {len(ingest_ids)} of {len(new_ids)} new places "
                f"(limit={TEST_INGEST_LIMIT})."
            )
            result = await AttractionIngestionPipeline(db=db).process_places(
                place_ids=ingest_ids,
                commit_each=True,
            )
            print(
                "Ingestion result: "
                f"total={result.total}, "
                f"successful={result.success}, "
                f"skipped={result.skipped}, "
                f"failed={result.failed}"
            )
            for item in result.results:
                if item.errors:
                    print(f"  {item.place_id}: {'; '.join(item.errors)}")
        elif ingest:
            print("\nNo new places to ingest.")
        else:
            print("\nDiscovery only; no places were ingested.")

    if errors:
        print("\nDiscovery request errors:")
        for error in errors:
            print(f"- {error}")
        return 1
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--ingest",
        action="store_true",
        help=(
            "Ingest at most three newly discovered places. "
            "Without this flag, the script only reports discoveries."
        ),
    )
    args = parser.parse_args()
    raise SystemExit(asyncio.run(main(ingest=args.ingest)))
