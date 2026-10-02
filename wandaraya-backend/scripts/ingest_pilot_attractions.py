from __future__ import annotations
import asyncio
from app.database import AsyncSessionLocal

from app.knowledge_base.pipelines.attraction_ingestion_pipeline import AttractionIngestionPipeline

PILOT_PLACE_IDS = [

    # ---------------------------------------------
    # HERITAGE / ARCHAEOLOGY
    # ---------------------------------------------

    # Galle Dutch Fort
    "ChIJXQLueKNz4ToR_sMWrhaKb7k",

    # Add exact IDs:
    # Sigiriya
    "ChIJs5pMcluh_DoRUg03WydxF6s",
    # Anuradhapura
    "ChIJWeFgk_n0_DoRDs9tvJ7-EcE",
    # Polonnaruwa
    "ChIJJ84WO7pE-zoRfCsDs6KXScM",
    # Dambulla Cave Temple
    "ChIJaTa9xVil_DoRTHZrk8Cl2tE",


    # ---------------------------------------------
    # RELIGIOUS / CULTURAL
    # ---------------------------------------------

    # Sri Dalada Maligawa
    "ChIJ9ftJsS1m4zoRh-gVwQrXZYE",
    # Gangaramaya Temple
    "ChIJQ9yCmWtZ4joRNu1evW41NTo",
    # Adam's Peak
    "ChIJWUsjiXWX4zoR3DdbHUetI4c",


    # ---------------------------------------------
    # WILDLIFE
    # ---------------------------------------------

    # Yala National Park
    "ChIJWZP7L6bT5ToRFDNaC9cjtjs",
    # Udawalawe National Park
    "ChIJeX6IiP8I5DoR14DZ-5_nEq8",
    # Wilpattu National Park
    "ChIJJ7zkh3es_ToRfBitXXGg2c0",
    # Minneriya National Park
    "ChIJXeALoglg-zoR9QVr8PJG0KQ",


    # ---------------------------------------------
    # NATURE / HIKING
    # ---------------------------------------------

    # Horton Plains
    "ChIJ73hL2y6I4zoRSXJ3U5GovM4",
    # Sinharaja
    "ChIJX9QJ0Wvn4zoRG3BJBgHxDow",
    # Ella
    "ChIJJZrAW5Vl5DoR-4fE3trc-r0",
    # Ravana Falls
    "ChIJk6Socrtl5DoR4NnxYbPPr6c",

    # ---------------------------------------------
    # BEACH / MARINE
    # ---------------------------------------------

    # Mirissa
    "ChIJB6LJSH8V4ToRbtE-5-IX_MU",
    # Unawatuna
    "ChIJ3aAZvO5y4ToRFvXdpG-hzxs",
    # Hikkaduwa
    "ChIJrW7Ly-J34ToR2UUvfXO6rdA",
    # Arugam Bay
    "ChIJv69ve9Ki5ToRNNv1nbXW78Y",


    # ---------------------------------------------
    # TEA / SCENIC
    # ---------------------------------------------

    # Nuwara Eliya
    "ChIJx1QVTkOA4zoRnH2TTEAIFik",
    # Lipton's Seat
    "ChIJr5MIAzRu5DoRa0f3r08Rhjg",


    # ---------------------------------------------
    # URBAN / EDUCATIONAL
    # ---------------------------------------------

    # Colombo National Museum
    "ChIJr7L0oW9Z4joRjaT5aD0oCtk",
    # Royal Botanical Gardens
    "ChIJ_ZUvrpBo4zoRMxJ5v8KOzpI",


    # ---------------------------------------------
    # SCENIC / PHOTOGRAPHY
    # ---------------------------------------------

    # Nine Arches Bridge
    "ChIJZXfiMH1l5DoRYbqmKfh38wg"
]

async def main()-> None:
    async with AsyncSessionLocal() as db:
        pipeline = AttractionIngestionPipeline(db=db)
        result = await pipeline.process_places(place_ids=PILOT_PLACE_IDS, commit_each=True)
        print()
        print("=" * 70)
        print("PILOT INGESTION SUMMARY")
        print("=" * 70)

        print(
            f"Total:      {result.total}"
        )

        print(
            f"Successful: {result.successful}"
        )

        print(
            f"Skipped:    {result.skipped}"
        )

        print(
            f"Failed:     {result.failed}"
        )

        print("=" * 70)

        if result.failed:
            print("FAILED PLACE IDS:")

            for item in result.results:
                error_message = getattr(item, "error", None)
                if error_message:
                    print(f" - {item.place_id} : {error_message}")

                for error in getattr(item, "errors", []) or []:
                    print(f"  - {error}")
if __name__ == "__main__":

    asyncio.run(
        main()
    )
