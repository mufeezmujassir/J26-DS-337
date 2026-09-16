from __future__ import annotations

import asyncio
import json
import sys

from app.database import AsyncSessionLocal
from app.knowledge_base.processors.district_resolver import DistrictResolver
from app.knowledge_base.connectors.google_places import GooglePlacesConnector
from app.knowledge_base.processors.normalizer import AttractionNormalizer
from app.knowledge_base.processors.validator import AttractionValidation

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

async def main()->None:
    connector=GooglePlacesConnector()

    place_id = (
        "ChIJXQLueKNz4ToR_sMWrhaKb7k"
    )

    # ==============================================
    # 1. Google Place Details
    # ==============================================

    raw_place = await connector.get_place_details(
        place_id=place_id
    )

    # ==============================================
    # 2. Normalize
    # ==============================================

    attraction = (
        AttractionNormalizer
        .normalize_google_place(
            raw_place
        )
    )

    print("\n================================")
    print("NORMALIZED")
    print("================================")

    print(
        f"Name: {attraction['name']}"
    )

    print(
        f"Latitude: {attraction['latitude']}"
    )

    print(
        f"Longitude: {attraction['longitude']}"
    )

    print(
        f"District ID before: "
        f"{attraction['district_id']}"
    )

    # ==============================================
    # 3. Validate
    # ==============================================

    validation = (
        AttractionValidation.validate(
            attraction
        )
    )

    print("\n================================")
    print("VALIDATION")
    print("================================")

    print(
        f"Valid: {validation.is_valid}"
    )

    if not validation.is_valid:

        print("\nErrors:")

        for error in validation.errors:
            print(f"- {error}")

        return

    # ==============================================
    # 4. District Resolution
    # ==============================================

    db = AsyncSessionLocal()

    try:

        district = await (
            DistrictResolver
            .apply_to_attraction(
                db=db,
                attraction=attraction,
            )
        )

        print("\n================================")
        print("DISTRICT RESOLUTION")
        print("================================")

        print(
            f"Found: {district.found}"
        )

        print(
            f"District ID: "
            f"{district.district_id}"
        )

        print(
            f"District: "
            f"{district.district_name}"
        )

        print(
            f"Province: "
            f"{district.province}"
        )

        print(
            f"Attraction district_id: "
            f"{attraction['district_id']}"
        )

        # ==========================================
        # Final normalized record
        # ==========================================

        print("\n================================")
        print("FINAL ATTRACTION")
        print("================================\n")

        print(
            json.dumps(
                attraction,
                indent=2,
                ensure_ascii=False,
            )
        )

    finally:
        await db.close()

if __name__ == "__main__":

    asyncio.run(main())