from __future__ import annotations

import asyncio
import json

from app.knowledge_base.connectors.google_places import GooglePlacesConnector
from app.knowledge_base.processors.normalizer import AttractionNormalizer

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
        AttractionNormalizer.normalize_google_place(
            raw_place
        )
    )

    print("\n========================================")
    print("NORMALIZED ATTRACTION")
    print("========================================\n")

    print(
        json.dumps(
            normalized,
            indent=2,
            ensure_ascii=False,
        )
    )
if __name__ == "__main__":
    asyncio.run(main())

