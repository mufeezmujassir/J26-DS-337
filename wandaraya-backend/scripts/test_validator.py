from __future__ import annotations

import asyncio
import json

from app.knowledge_base.processors.validator import AttractionValidation
from app.knowledge_base.processors.normalizer import AttractionNormalizer
from app.knowledge_base.connectors.google_places import GooglePlacesConnector

async def main() -> None:

    connector = GooglePlacesConnector()

    # Galle Dutch Fort
    place_id = (
        "ChIJXQLueKNz4ToR_sMWrhaKb7k"
    )


    raw_place = await connector.get_place_details(
        place_id=place_id
    )

    normalized = (
        AttractionNormalizer
        .normalize_google_place(
            raw_place
        )
    )

    print("\n==============================")
    print("NORMALIZED")
    print("==============================\n")

    print(
        json.dumps(
            normalized,
            indent=2,
            ensure_ascii=False,
        )
    )



    result = AttractionValidation.validate(
        normalized
    )

    print("\n==============================")
    print("VALIDATION")
    print("==============================")

    print(f"Valid: {result.is_valid}")

    print("\nErrors:")

    if result.errors:
        for error in result.errors:
            print(f"  - {error}")
    else:
        print("  None")

    print("\nWarnings:")

    if result.warnings:
        for warning in result.warnings:
            print(f"  - {warning}")
    else:
        print("  None")


if __name__ == "__main__":
    asyncio.run(main())