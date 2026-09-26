from __future__ import annotations

import asyncio

from app.database import AsyncSessionLocal

from app.knowledge_base.pipelines.attraction_ingestion_pipeline import (
    AttractionIngestionPipeline,
    PipelineStatus,
)


PLACE_IDS = [

    # Galle Dutch Fort
    "ChIJXQLueKNz4ToR_sMWrhaKb7k",

    # Add after finding exact Google Place IDs:
    #
"ChIJ0Xkxp9-g_DoR3w7_DBXBBB4",
"ChIJWZP7L6bT5ToRFDNaC9cjtjs",

"ChIJ_9U2xtQ_4ToRspMatLlWFLg",
"ChIJ9ftJsS1m4zoRh-gVwQrXZYE"


]




def print_attraction_result(
    number: int,
    result,
) -> None:

    print()
    print("=" * 70)

    print(
        f"ATTRACTION {number}"
    )

    print("=" * 70)

    print(
        f"Status: "
        f"{result.status.value.upper()}"
    )

    print(
        f"Place ID: "
        f"{result.place_id}"
    )

    print(
        f"Attraction ID: "
        f"{result.attraction_id}"
    )

    print(
        f"Name: "
        f"{result.attraction_name}"
    )

    print(
        f"District: "
        f"{result.district_name}"
    )

    print(
        f"Wikipedia: "
        f"{result.wikipedia_enriched}"
    )

    print(
        f"Wikivoyage: "
        f"{result.wikivoyage_enriched}"
    )

    print(
        f"Categories mapped: "
        f"{result.categories_mapped}"
    )

    print(
        f"Activities mapped: "
        f"{result.activities_mapped}"
    )

    print(
        f"Semantic document: "
        f"{result.semantic_document_created}"
    )

    print(
        f"BGE embedding: "
        f"{result.embedding_created}"
    )

    print(
        f"Qdrant indexed: "
        f"{result.indexed_in_qdrant}"
    )

    # --------------------------------------------------------
    # WARNINGS
    # --------------------------------------------------------

    if result.warnings:

        print()
        print("WARNINGS")

        print("-" * 70)

        for warning in result.warnings:

            print(
                f"- {warning}"
            )

    # --------------------------------------------------------
    # ERRORS
    # --------------------------------------------------------

    if result.errors:

        print()
        print("ERRORS")

        print("-" * 70)

        for error in result.errors:

            print(
                f"- {error}"
            )


# ============================================================
# MAIN
# ============================================================


async def main() -> None:

    print()
    print("=" * 70)

    print(
        "WANDARAYA MULTI-ATTRACTION "
        "INGESTION PIPELINE"
    )

    print("=" * 70)

    print(
        f"Requested attractions: "
        f"{len(PLACE_IDS)}"
    )

    async with AsyncSessionLocal() as db:
        try:

            pipeline = (
                AttractionIngestionPipeline(
                    db=db
                )
            )

            batch_result = (
                await pipeline.process_places(
                    place_ids=PLACE_IDS,
                    commit_each=True,
                )
            )

            # ====================================================
            # INDIVIDUAL RESULTS
            # ====================================================

            for number, result in enumerate(
                batch_result.results,
                start=1,
            ):

                print_attraction_result(
                    number,
                    result,
                )

            # ====================================================
            # SUMMARY
            # ====================================================

            print()
            print()
            print("=" * 70)

            print(
                "INGESTION SUMMARY"
            )

            print("=" * 70)

            print(
                f"Total:      "
                f"{batch_result.total}"
            )

            print(
                f"Successful: "
                f"{batch_result.successful}"
            )

            print(
                f"Skipped:    "
                f"{batch_result.skipped}"
            )

            print(
                f"Failed:     "
                f"{batch_result.failed}"
            )

            print("=" * 70)

            # ====================================================
            # FINAL STATUS
            # ====================================================

            if batch_result.failed == 0:

                print()
                print(
                    "MULTI-ATTRACTION INGESTION "
                    "TEST COMPLETED."
                )

            else:

                print()
                print(
                    "INGESTION COMPLETED WITH "
                    "FAILURES."
                )

                print(
                    "Review the failed attraction "
                    "messages above."
                )

        except Exception as exc:

            await db.rollback()

            print()
            print("=" * 70)

            print(
                "PIPELINE TEST FAILED"
            )

            print("=" * 70)

            print(
                str(exc)
            )

            raise


# ============================================================
# ENTRY POINT
# ============================================================


if __name__ == "__main__":

    asyncio.run(
        main()
    )