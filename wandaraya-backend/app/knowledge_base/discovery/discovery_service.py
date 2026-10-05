from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Iterable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.knowledge_base.connectors.google_places import GooglePlacesConnector
from app.knowledge_base.discovery.attraction_discovery import DiscoveredPlace
from app.knowledge_base.discovery.discovery_types import ALL_DISCOVERY_TYPES
from app.knowledge_base.discovery.sri_lanka_grid import load_sri_lanka_discovery_grid
from app.knowledge_base.pipelines.attraction_ingestion_pipeline import (
    AttractionIngestionPipeline,
    BatchPipelineResult,
)
from app.models.attraction import Attraction


logger = logging.getLogger(__name__)


@dataclass
class DiscoveryRunResult:
    discovered_places: list[DiscoveredPlace] = field(default_factory=list)
    existing_place_ids: list[str] = field(default_factory=list)
    new_place_ids: list[str] = field(default_factory=list)
    ingestion: BatchPipelineResult | None = None
    errors: list[str] = field(default_factory=list)

    @property
    def discovered_count(self) -> int:
        return len(self.discovered_places)


class NationwideAttractionDiscoveryService:
    """Discover unknown places, then hand only new IDs to the existing pipeline."""

    def __init__(self, google_places: GooglePlacesConnector | None = None) -> None:
        self.google_places = google_places or GooglePlacesConnector()

    async def discover(
        self,
        *,
        db: AsyncSession,
        max_cells: int | None = None,
        max_types: int | None = None,
    ) -> tuple[list[DiscoveredPlace], list[str]]:
        if max_cells is not None and max_cells <= 0:
            raise ValueError("max_cells must be greater than zero.")
        if max_types is not None and max_types <= 0:
            raise ValueError("max_types must be greater than zero.")

        grid = await load_sri_lanka_discovery_grid(db)
        types = ALL_DISCOVERY_TYPES
        if max_cells is not None:
            grid = grid[:max_cells]
        if max_types is not None:
            types = types[:max_types]

        discovered: dict[str, DiscoveredPlace] = {}
        errors: list[str] = []
        for cell in grid:
            logger.info("Searching discovery cell: %s", cell.name)
            for place_type in types:
                try:
                    results = await self.google_places.search_nearby(
                        latitude=cell.latitude,
                        longitude=cell.longitude,
                        radius_meters=cell.radius_meters,
                        included_types=[place_type],
                        max_results=20,
                    )
                except Exception as exc:
                    message = f"{cell.name}/{place_type}: {exc}"
                    errors.append(message)
                    logger.exception("Discovery request failed | %s", message)
                    continue

                for raw_place in results:
                    place_id = raw_place.get("id")
                    if not place_id:
                        logger.warning("Skipping Google result without a place ID.")
                        continue

                    place = discovered.get(place_id)
                    if place is None:
                        location = raw_place.get("location") or {}
                        display_name = raw_place.get("displayName")
                        place = DiscoveredPlace(
                            place_id=place_id,
                            name=(display_name.get("text") if isinstance(display_name, dict) else display_name),
                            latitude=location.get("latitude"),
                            longitude=location.get("longitude"),
                            primary_type=raw_place.get("primaryType"),
                        )
                        discovered[place_id] = place

                    place.discovered_by_types.add(place_type)
                    place.discovered_in_cells.add(cell.name)

        self._last_errors = errors
        return list(discovered.values()), errors

    async def run(
        self,
        *,
        db: AsyncSession,
        max_cells: int | None = None,
        max_types: int | None = None,
        ingest: bool = True,
    ) -> DiscoveryRunResult:
        discovered_places, errors = await self.discover(
            db=db,
            max_cells=max_cells,
            max_types=max_types,
        )
        discovered_ids = [place.place_id for place in discovered_places]
        existing_ids = await self._existing_place_ids(db, discovered_ids)
        new_ids = [place_id for place_id in discovered_ids if place_id not in existing_ids]

        result = DiscoveryRunResult(
            discovered_places=discovered_places,
            existing_place_ids=sorted(existing_ids),
            new_place_ids=new_ids,
            errors=errors,
        )
        logger.info(
            "Discovery complete | discovered=%s known=%s new=%s",
            result.discovered_count,
            len(existing_ids),
            len(new_ids),
        )

        if ingest and new_ids:
            result.ingestion = await AttractionIngestionPipeline(db=db).process_places(
                place_ids=new_ids,
                commit_each=True,
            )
        return result

    @staticmethod
    async def _existing_place_ids(
        db: AsyncSession,
        place_ids: Iterable[str],
    ) -> set[str]:
        unique_ids = list(dict.fromkeys(place_ids))
        if not unique_ids:
            return set()
        query_result = await db.execute(
            select(Attraction.google_place_id).where(
                Attraction.google_place_id.in_(unique_ids)
            )
        )
        return {place_id for place_id in query_result.scalars() if place_id}
