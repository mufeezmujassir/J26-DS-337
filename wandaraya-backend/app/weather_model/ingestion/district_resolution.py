from __future__ import annotations

import pandas as pd
from sqlalchemy.ext.asyncio import AsyncSession

from app.knowledge_base.processors.district_resolver import DistrictResolver


async def resolve_weather_districts(
    db: AsyncSession,
    dataframe: pd.DataFrame,
) -> pd.DataFrame:
    """Attach PostGIS district metadata without guessing missing coordinates."""
    required = {"station_id", "latitude", "longitude"}
    missing = required - set(dataframe.columns)
    if missing:
        raise ValueError(f"Weather data is missing required columns: {sorted(missing)}")

    result = dataframe.copy()
    result["district_id"] = pd.NA
    result["district_name"] = pd.NA
    result["resolution_status"] = "UNRESOLVED_NO_COORDINATES"

    stations = result[["station_id", "latitude", "longitude"]].drop_duplicates()
    resolutions: dict[str, tuple[int | None, str | None, str]] = {}
    for station in stations.itertuples(index=False):
        if pd.isna(station.latitude) or pd.isna(station.longitude):
            continue

        district = await DistrictResolver.resolve(
            db=db,
            latitude=float(station.latitude),
            longitude=float(station.longitude),
        )
        if district.found:
            resolutions[str(station.station_id)] = (
                district.district_id,
                district.district_name,
                "RESOLVED",
            )
        else:
            resolutions[str(station.station_id)] = (
                None,
                None,
                "UNRESOLVED_OUTSIDE_BOUNDARY",
            )

    for station_id, (district_id, district_name, status) in resolutions.items():
        mask = result["station_id"].astype(str) == station_id
        result.loc[mask, "district_id"] = district_id
        result.loc[mask, "district_name"] = district_name
        result.loc[mask, "resolution_status"] = status

    return result
