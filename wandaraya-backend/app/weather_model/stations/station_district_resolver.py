from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.knowledge_base.processors.district_resolver import (
    DistrictResolution,
    DistrictResolver,
)
from app.models.district import District


@dataclass(frozen=True)
class StationDistrictResolution:
    district: DistrictResolution | None
    status: str


class WeatherStationDistrictResolver:
    """Thin weather-station adapter around the shared PostGIS resolver."""

    def __init__(self, district_resolver: DistrictResolver | None = None) -> None:
        self.district_resolver = district_resolver or DistrictResolver()

    # The imported NSDI boundaries leave a few verified station points just
    # outside a polygon edge.  This 0.01-degree (~1.1 km) fallback is limited
    # to known-coordinate stations and is explicitly reported as near-boundary.
    NEAR_BOUNDARY_TOLERANCE_DEGREES = 0.01

    async def resolve_station(
        self,
        db: AsyncSession,
        station: Any,
    ) -> DistrictResolution | None:
        return (await self.resolve_station_with_status(db, station)).district

    async def resolve_station_with_status(
        self,
        db: AsyncSession,
        station: Any,
    ) -> StationDistrictResolution:
        latitude = getattr(station, "latitude", None)
        longitude = getattr(station, "longitude", None)
        if latitude is None or longitude is None:
            return StationDistrictResolution(None, "PENDING_METADATA")

        district = await self.district_resolver.resolve(
            db=db,
            latitude=float(latitude),
            longitude=float(longitude),
        )
        if district.found:
            return StationDistrictResolution(district, "RESOLVED")

        point = func.ST_SetSRID(
            func.ST_MakePoint(float(longitude), float(latitude)),
            4326,
        )
        statement = (
            select(District)
            .where(
                func.ST_DWithin(
                    District.boundary,
                    point,
                    self.NEAR_BOUNDARY_TOLERANCE_DEGREES,
                )
            )
            .order_by(func.ST_Distance(District.boundary, point))
            .limit(1)
        )
        nearest = (await db.execute(statement)).scalars().first()
        if nearest is None:
            return StationDistrictResolution(
                DistrictResolution(found=False),
                "SPATIAL_FAILURE",
            )
        return StationDistrictResolution(
            DistrictResolution(
                found=True,
                district_id=nearest.id,
                district_name=nearest.name,
                province=nearest.province,
            ),
            "RESOLVED_NEAR_BOUNDARY",
        )
