from __future__ import annotations

import asyncio
import json

from app.knowledge_base.processors.deduplicator import AttractionDeduplicator
from app.models.attraction import Attraction
from app.knowledge_base.processors.normalizer import AttractionNormalizer
from app.knowledge_base.connectors.google_places import GooglePlacesConnector
from app.knowledge_base.processors.validator import AttractionValidation
from app.knowledge_base.processors.district_resolver import DistrictResolver
from app.database import AsyncSessionLocal
async def main()->None:
    connector=GooglePlacesConnector()
    place_id = (
        "ChIJXQLueKNz4ToR_sMWrhaKb7k"
    )
    raw_place=await connector.get_place_details(
        place_id=place_id
    )

    attraction=(
        AttractionNormalizer.normalize_google_place(
            raw_place
        )
    )

    validator=AttractionValidation.validate(
        attraction
    )

    if not validator.is_valid:
        print("INVALID ATTTRACTION")
        for error in validator.errors:
            print(f"- {error}")

        return

    async with AsyncSessionLocal() as db:
        district = await DistrictResolver.apply_to_attraction(
            db=db,
            attraction=attraction,
        )

        if not district.found:
            print("District could not be resolved.")
            return

        result = await db.run_sync(
            lambda sync_db: AttractionDeduplicator.find_duplicates(
                db=sync_db,
                attraction=attraction,
            )
        )

        print("\n================================")
        print("DEDUPLICATION RESULT")
        print("================================")

        print(
            f"Name: {attraction['name']}"
        )

        print(
            f"Google Place ID: "
            f"{attraction['google_place_id']}"
        )

        print(
            f"District: {district.district_name}"
        )

        print(
            f"Is Duplicate: {result.is_duplicated}"
        )

        print(
            f"Match Type: {result.match_types}"
        )

        if result.existing_attraction:

            print(
                f"Existing Attraction ID: "
                f"{result.existing_attraction.id}"
            )

            print(
                f"Existing Name: "
                f"{result.existing_attraction.name}"
            )

        if result.distance_meter is not None:

            print(
                f"Distance: "
                f"{result.distance_meter:.2f} m"
            )


if __name__ == "__main__":
    asyncio.run(main())
        