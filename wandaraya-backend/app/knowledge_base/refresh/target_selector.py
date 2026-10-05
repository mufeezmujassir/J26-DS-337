from __future__ import annotations
import logging

from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.attraction import Attraction
logger = logging.getLogger(__name__)

@dataclass(frozen=True)
class AttractionRefreshTarget:
    attraction_id: int
    name: str
    google_place_id: str
    last_sync_at: datetime | None


class AttractionRefreshTargetSelector:

    async def select_targets(
            self,
            db: AsyncSession,
            *,
            limit:int | None = None,

    )->list[AttractionRefreshTarget]:
        """
        Selects attractions that need to be refreshed based on the last_sync_at timestamp.
        If last_sync_at is None or older than 30 days, the attraction is considered for refresh.

        Args:
            db (AsyncSession): The database session to use for the query.
            limit (int | None): Optional limit on the number of results to return.

        Returns:    """
        statement = (
            select(
                Attraction.id,
                Attraction.name,
                Attraction.google_place_id,
                Attraction.last_sync_at,
            )
            .where(
                Attraction.is_active.is_(True),
                Attraction.google_place_id.is_not(None),
            )
            .order_by(
                Attraction.last_sync_at.asc().nullsfirst(),
                Attraction.id.asc(),
            )
        )
        if limit is not None:

            if limit <= 0:
                raise ValueError(
                    "limit must be greater than zero."
                )

            statement = statement.limit(limit)

        result = await db.execute(statement)

        rows = result.all()

        targets = [
            AttractionRefreshTarget(
                attraction_id=row.id,
                name=row.name,
                google_place_id=row.google_place_id,
                last_sync_at=row.last_sync_at,
            )
            for row in rows
            if row.google_place_id
        ]

        logger.info(
            "Selected %s attraction refresh targets.",
            len(targets),
        )

        return targets