from __future__ import annotations
import logging

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from datetime import datetime, timedelta,timezone
from dataclasses import dataclass, field

from app.knowledge_base.pipelines.attraction_ingestion_pipeline import(
    AttractionIngestionPipeline,
    PipelineStatus
)

from app.knowledge_base.refresh.target_selector import AttractionRefreshTargetSelector, AttractionRefreshTarget

logger = logging.getLogger(__name__)


@dataclass
class KBRefreshResult:
    started_at: datetime
    finished_at: datetime | None = None

    requested: int = 0
    successful: int = 0
    skipped: int = 0
    failed: int = 0

    refreshed_attraction_ids: list[int] = field(
        default_factory=list
    )

    errors: list[str] = field(
        default_factory=list
    )


class TourismKBRefreshService:
    """
    Coordinates a refresh of existing WANDARAYA attractions.

    Responsibilities:

        PostgreSQL
            ↓
        select refresh targets
            ↓
        AttractionIngestionPipeline
            ↓
        PostgreSQL update
            ↓
        semantic document
            ↓
        BGE
            ↓
        Qdrant

    This service intentionally reuses the existing ingestion
    pipeline instead of duplicating ingestion logic.
    """

    def __init__(
        self,
        db: AsyncSession,
    ) -> None:

        self.db = db

        self.target_selector = (
            AttractionRefreshTargetSelector()
        )

        self.pipeline = AttractionIngestionPipeline(
            db=db
        )

    async def refresh(
        self,
        *,
        limit: int | None = None,
    ) -> KBRefreshResult:

        refresh_result = KBRefreshResult(
            started_at=datetime.now(
                timezone.utc
            )
        )

        

        targets = await self.target_selector.select_targets(
            db=self.db,
            limit=limit,
        )

        refresh_result.requested = len(
            targets
        )

        if not targets:

            logger.info(
                "No attractions require refresh."
            )

            refresh_result.finished_at = datetime.now(
                timezone.utc
            )

            return refresh_result

        place_ids = [
            target.google_place_id
            for target in targets
        ]

        logger.info(
            "Starting Tourism KB refresh | targets=%s",
            len(place_ids),
        )

        batch_result = await self.pipeline.process_places(
            place_ids=place_ids,
            commit_each=True,
        )


        for item in batch_result.results:

            if item.status == PipelineStatus.SUCCESS:

                refresh_result.successful += 1

                if item.attraction_id is not None:

                    refresh_result.refreshed_attraction_ids.append(
                        item.attraction_id
                    )

            elif item.status == PipelineStatus.SKIPPED:

                refresh_result.skipped += 1

            elif item.status == PipelineStatus.FAILED:

                refresh_result.failed += 1

                if item.errors:

                    refresh_result.errors.extend(
                        [
                            (
                                f"{item.place_id}: "
                                f"{error}"
                            )
                            for error in item.errors
                        ]
                    )

        refresh_result.finished_at = datetime.now(
            timezone.utc
        )

        logger.info(
            (
                "Tourism KB refresh completed | "
                "requested=%s success=%s "
                "skipped=%s failed=%s"
            ),
            refresh_result.requested,
            refresh_result.successful,
            refresh_result.skipped,
            refresh_result.failed,
        )

        return refresh_result