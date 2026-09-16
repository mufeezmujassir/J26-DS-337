from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.district import District


@dataclass
class DistrictResolution:
    found:bool
    district_id: Optional[int] = None
    district_name: Optional[str] = None
    province: Optional[str] = None

class DistrictResolver:

    @staticmethod
    async def resolve(db:AsyncSession,
                latitude:float,
                longitude:float)->DistrictResolution:
        if latitude is None or longitude is None:
            return DistrictResolution(found=False)

        point = func.ST_SetSRID(
            func.ST_MakePoint(
                longitude,
                latitude,
            ),
            4326,
        )
        statement=(
            select (District).where(
                func.ST_Covers(
                    District.boundary,
                    point,
                )
            )
            .limit(1)
        )

        result = await db.execute(statement)
        district = result.scalars().first()

        if district is None:
            return DistrictResolution(found=False)

        return DistrictResolution(
            found=True,
            district_id=district.id,
            district_name=district.name,
            province=district.province,
        )

    @classmethod
    async def resolve_attraction(
        cls,
        db:AsyncSession,
        attraction: Dict[str, Any],

    )->DistrictResolution:
        latitude = attraction.get(
            "latitude"
        )

        longitude = attraction.get(
            "longitude"
        )

        return await cls.resolve(
            db=db,
            latitude=latitude,
            longitude=longitude,
        )
    @classmethod
    async def apply_to_attraction(
        cls,
        db: AsyncSession,
        attraction: Dict[str, Any],
    ) -> DistrictResolution:
        
        result = await cls.resolve_attraction(
            db=db,
            attraction=attraction,
        )

        if result.found:
            attraction["district_id"] = (
                result.district_id
            )

        return result