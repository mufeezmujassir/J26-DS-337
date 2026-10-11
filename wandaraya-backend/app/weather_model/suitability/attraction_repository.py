"""Read-only Tourism Knowledge Base queries for weather suitability."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.activities import Activity
from app.models.attraction import Attraction
from app.models.attraction_activities import AttractionActivity
from app.models.district import District
from app.weather_model.suitability.activity_mapper import (
    map_activity_to_weather_profile,
)


class AttractionWeatherRepository:
    """Loads active district attractions and their available activity mappings."""

    @staticmethod
    async def get_candidates(
        db: AsyncSession,
        district_id: int,
        limit: int = 50,
    ) -> list[dict]:
        # Limit attractions before joining activities; otherwise a single
        # attraction with many activities could consume the whole limit.
        selected_attraction_ids = (
            select(Attraction.id)
            .where(
                Attraction.district_id == district_id,
                Attraction.is_active.is_(True),
            )
            .order_by(Attraction.id)
            .limit(limit)
            .subquery()
        )

        statement = (
            select(
                Attraction.id.label("attraction_id"),
                Attraction.name.label("attraction_name"),
                Attraction.district_id,
                Attraction.latitude.label("attraction_latitude"),
                Attraction.longitude.label("attraction_longitude"),
                District.latitude.label("district_latitude"),
                District.longitude.label("district_longitude"),
                Activity.name.label("activity_name"),
            )
            .join(
                selected_attraction_ids,
                selected_attraction_ids.c.id == Attraction.id,
            )
            .outerjoin(District, District.id == Attraction.district_id)
            .join(
                AttractionActivity,
                AttractionActivity.attraction_id == Attraction.id,
            )
            .join(Activity, Activity.id == AttractionActivity.activity_id)
            .where(
                AttractionActivity.is_available.is_(True),
                Activity.is_active.is_(True),
            )
            .order_by(
                Attraction.id,
                AttractionActivity.suitability_score.desc(),
                Activity.id,
            )
        )
        rows = (await db.execute(statement)).mappings().all()
        grouped: dict[int, dict] = {}

        for row in rows:
            attraction_id = row["attraction_id"]
            candidate = grouped.get(attraction_id)
            if candidate is None:
                latitude, longitude, coordinate_source = (
                    AttractionWeatherRepository._resolve_coordinates(row)
                )
                candidate = {
                    "attraction_id": attraction_id,
                    "name": row["attraction_name"],
                    "district_id": row["district_id"],
                    "latitude": latitude,
                    "longitude": longitude,
                    "coordinate_source": coordinate_source,
                    "activity_types": [],
                }
                grouped[attraction_id] = candidate

            profile = map_activity_to_weather_profile(row["activity_name"])
            # Keep unknown vocabulary visible to Stage 9.3, which reports it
            # as unsupported rather than silently treating the attraction as
            # if it had no activities.
            activity_type = profile or row["activity_name"]
            if activity_type not in candidate["activity_types"]:
                candidate["activity_types"].append(activity_type)

        return list(grouped.values())

    @staticmethod
    def _resolve_coordinates(row) -> tuple[float | None, float | None, str]:
        attraction_coordinates = (
            row["attraction_latitude"],
            row["attraction_longitude"],
        )
        if all(value is not None for value in attraction_coordinates):
            return (*attraction_coordinates, "attraction")

        district_coordinates = (
            row["district_latitude"],
            row["district_longitude"],
        )
        if all(value is not None for value in district_coordinates):
            return (*district_coordinates, "district_fallback")

        return None, None, "unavailable"
