from __future__ import annotations

import asyncio
import json

from app.knowledge_base.loaders.attraction_loader import AttractionLoader
from app.knowledge_base.connectors.google_places import GooglePlacesConnector
from app.knowledge_base.processors.normalizer import AttractionNormalizer
from app.knowledge_base.processors.validator import AttractionValidation
from app.knowledge_base.processors.district_resolver import DistrictResolver
from app.knowledge_base.processors.deduplicator import AttractionDeduplicator
from app.database import AsyncSessionLocal  

async def main()->None:
    connector=GooglePlacesConnector()

    place_id = (
        "ChIJ_9U2xtQ_4ToRspMatLlWFLg"
    )

    raw_place = await connector.get_place_details(
        place_id=place_id
    )

    attraction = (
        AttractionNormalizer
        .normalize_google_place(
            raw_place
        )
    )
    validation = AttractionValidation.validate(
        attraction
    )

    if not validation.is_valid:
        print("Attraction validation failed.")

        for error in validation.errors:
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

        duplicate = await db.run_sync(
            lambda sync_db: AttractionDeduplicator.find_duplicates(
                db=sync_db,
                attraction=attraction,
            )
        )

        print("\n==============================")
        print("PRE-LOAD")
        print("==============================")

        print(
            f"Name: {attraction['name']}"
        )

        print(
            f"District: "
            f"{district.district_name}"
        )

        print(
            f"Duplicate before load: "
            f"{duplicate.is_duplicated}"
        )

        loaded = await db.run_sync(
            lambda sync_db: AttractionLoader.upsert(
                db=sync_db,
                attraction_data=attraction,
            )
        )

        await db.commit()
        await db.refresh(loaded)

        print("\n==============================")
        print("ATTRACTION SAVED")
        print("==============================")

        print(
            f"ID: {loaded.id}"
        )

        print(
            f"Name: {loaded.name}"
        )

        print(
            f"Slug: {loaded.slug}"
        )

        print(
            f"Google Place ID: "
            f"{loaded.google_place_id}"
        )

        print(
            f"District ID: "
            f"{loaded.district_id}"
        )

        print(
            f"Rating: {loaded.rating}"
        )

        print(
            f"Review Count: "
            f"{loaded.review_count}"
        )

        print("\nSUCCESS")

if __name__ == "__main__":
    asyncio.run(main())


