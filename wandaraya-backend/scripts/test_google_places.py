"""
Development test for Google Places connector.

Tests:
1. Nearby Search
2. Place Details
3. Photo metadata returned by Place Details

Nothing is inserted into PostgreSQL.
"""

from __future__ import annotations

import asyncio
import json

from app.knowledge_base.connectors.google_places import (
    GooglePlacesConnector,
)


async def main() -> None:

    connector = GooglePlacesConnector()

    # Test location: Galle area
    latitude = 6.0329
    longitude = 80.2168

    places = await connector.nearby_search(
        latitude=latitude,
        longitude=longitude,
        radius=5000,
        included_types=[
            "tourist_attraction",
        ],
        max_results=10,
    )

    print("\n========================================")
    print("NEARBY SEARCH RESULTS")
    print("========================================\n")

    print(
        json.dumps(
            places,
            indent=2,
            ensure_ascii=False,
        )
    )

    print(f"\nPlaces returned: {len(places)}")

    if not places:
        print("No places found.")
        return



    first_place = places[0]

    place_id = first_place["id"]

    print("\n========================================")
    print("SELECTED PLACE")
    print("========================================")

    print(
        f"Name: "
        f"{first_place.get('displayName', {}).get('text')}"
    )

    print(f"Place ID: {place_id}")


    details = await connector.get_place_details(
        place_id=place_id
    )

    print("\n========================================")
    print("PLACE DETAILS")
    print("========================================\n")

    print(
        json.dumps(
            details,
            indent=2,
            ensure_ascii=False,
        )
    )



    photos = details.get("photos", [])

    # WANDARAYA requirement:
    # Maximum 2 images per attraction.
    selected_photos = photos[:2]

    print("\n========================================")
    print("SELECTED PLACE PHOTOS")
    print("========================================")

    print(f"Available photos: {len(photos)}")
    print(f"Selected photos: {len(selected_photos)}")

    for index, photo in enumerate(
        selected_photos,
        start=1,
    ):
        photo_name = photo.get("name")

        if not photo_name:
            continue

        photo_result = await connector.get_photo_metadata(
            photo_name=photo_name,
            max_width=1200,
            max_height=900,
        )

        print(f"\nPhoto {index}")

        print(
            "Actual Place Image URL:",
            photo_result.get("photoUri"),
        )

        print(
            "Width:",
            photo.get("widthPx"),
        )

        print(
            "Height:",
            photo.get("heightPx"),
        )

        print(
            "Attribution:",
            photo.get("authorAttributions"),
        )


if __name__ == "__main__":
    asyncio.run(main())