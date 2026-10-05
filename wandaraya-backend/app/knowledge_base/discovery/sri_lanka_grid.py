"""Generate discovery search centres from the imported district boundaries."""

from __future__ import annotations

import math
from dataclasses import dataclass

from geoalchemy2.shape import to_shape
from shapely.geometry import Point
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.district import District


DEFAULT_RADIUS_METERS = 30_000.0
DEFAULT_SPACING_MULTIPLIER = 1.5
METERS_PER_DEGREE_LATITUDE = 111_320.0


@dataclass(frozen=True)
class DiscoveryGridPoint:
    name: str
    latitude: float
    longitude: float
    radius_meters: float


async def load_sri_lanka_discovery_grid(
    db: AsyncSession,
    *,
    radius_meters: float = DEFAULT_RADIUS_METERS,
    spacing_multiplier: float = DEFAULT_SPACING_MULTIPLIER,
) -> list[DiscoveryGridPoint]:

    
    """Build an interior-point grid from active PostGIS district polygons."""
    if not 0 < radius_meters <= 50_000:
        raise ValueError("radius_meters must be greater than 0 and no more than 50 km.")
    if spacing_multiplier <= 0:
        raise ValueError("spacing_multiplier must be greater than zero.")

    result = await db.execute(
        select(District.name, District.boundary)
        .where(District.is_active.is_(True))
        .order_by(District.name)
    )
    districts = result.all()
    if not districts:
        raise RuntimeError("No active district boundaries are available for discovery.")

    latitude_step = radius_meters * spacing_multiplier / METERS_PER_DEGREE_LATITUDE
    points: dict[tuple[float, float], DiscoveryGridPoint] = {}

    for district_name, boundary in districts:
        geometry = to_shape(boundary)
        min_longitude, min_latitude, max_longitude, max_latitude = geometry.bounds
        latitude = min_latitude
        district_point_count = 0

        while latitude <= max_latitude + 1e-9:
            longitude_step = (
                radius_meters
                * spacing_multiplier
                / (METERS_PER_DEGREE_LATITUDE * max(math.cos(math.radians(latitude)), 0.1))
            )
            longitude = min_longitude
            while longitude <= max_longitude + 1e-9:
                if geometry.covers(Point(longitude, latitude)):
                    key = (round(latitude, 6), round(longitude, 6))
                    points.setdefault(
                        key,
                        DiscoveryGridPoint(
                            name=(
                                f"{district_name.casefold().replace(' ', '_')}"
                                f"_{len(points) + 1:03d}"
                            ),
                            latitude=latitude,
                            longitude=longitude,
                            radius_meters=radius_meters,
                        ),
                    )
                    district_point_count += 1
                longitude += longitude_step
            latitude += latitude_step

        # Small or narrow districts can fall between regular grid intersections.
        # A representative point guarantees that every imported district is searched.
        if district_point_count == 0:
            representative = geometry.representative_point()
            key = (round(representative.y, 6), round(representative.x, 6))
            points.setdefault(
                key,
                DiscoveryGridPoint(
                    name=f"{district_name.casefold().replace(' ', '_')}_representative",
                    latitude=representative.y,
                    longitude=representative.x,
                    radius_meters=radius_meters,
                ),
            )

    return sorted(points.values(), key=lambda point: (point.latitude, point.longitude))
