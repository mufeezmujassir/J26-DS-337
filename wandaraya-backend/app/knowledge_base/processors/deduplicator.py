from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Dict, List, Optional
from sqlalchemy import select,func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session
from geoalchemy2 import Geography
from app.models.attraction import Attraction


@dataclass
class DeduplicationResult:
    is_duplicated:bool
    existing_attraction:Optional[Attraction]=None
    match_types:Optional[str]=None
    distance_meter:Optional[float]=None

class AttractionDeduplicator:
    DEFAULT_DISTANCE_METER=150.0

    @classmethod
    def find_duplicates(
        cls,
        db:Session,
        attraction:Dict[str,Any],

    )->DeduplicationResult:
        google_place_id=attraction.get("google_place_id")

        if google_place_id:
            result=cls._find_by_google_place_id(
                db=db,
                google_place_id=google_place_id

            )
            if result is not None:
                return DeduplicationResult(
                    is_duplicated=True,
                    existing_attraction=result,
                    match_types="google_place_id",
                    distance_meter=0.0


                )

            slug= attraction.get("slug")
            district_id=attraction.get("district_id")
            if slug and district_id:
                result=cls._find_by_slug_and_district(
                db=db,
                slug=slug,
                district_id=district_id,
            )
            if result is not None:
                return DeduplicationResult(
                    is_duplicated=True,
                    existing_attraction=result,
                    match_types="slug_and_district",
                    distance_meter=0.0
                )

            name=attraction.get("name")
            longtitude=attraction.get("longitude")
            latitude=attraction.get("latitude")

            if (name and latitude is not None and longtitude is not None):
                result=cls._find_by_name_and_distance(
                    db=db,
                    name=name,
                    latitude=latitude,
                    longitude=longtitude,
                )
                if result is not None:
                    exsisting,distance=result
                    return DeduplicationResult(
                        is_duplicated=True,
                        existing_attraction=exsisting,
                        match_types="name_and_distance",
                        distance_meter=distance
                    )
        return DeduplicationResult(is_duplicated=False)

    @staticmethod
    def _find_by_google_place_id(db: Session,
        google_place_id: str)->Optional[Attraction]:
        statement=(
            select(Attraction).where(Attraction.google_place_id==google_place_id)
        ).limit(1)

        return (
            db.execute(statement).scalars().first()
        )

    @staticmethod
    def _find_by_slug_and_district(db: Session,
        slug: str,
        district_id:int)->Optional[Attraction]:
        statement=(
            select(Attraction).where(Attraction.slug==slug).where(Attraction.district_id==district_id)
        ).limit(1)

        return (
            db.execute(statement).scalars().first()
        )

    @staticmethod
    def _find_by_name_and_distance(
        db: Session,
        name: str,
        latitude:float,
        longitude:float):
        point1=func.ST_SetSRID(
            func.ST_MakePoint(
                longitude,
                latitude,
            ),
            4326,
        )
        point2=func.ST_SetSRID(
            func.ST_MakePoint(
                longitude,
                latitude,
            ),
            4326
        )

        distance = func.ST_Distance(
            point1.cast(Geography),
            point2.cast(Geography),
        )
        statement=(
            select(Attraction,distance.label("distance_meter")).where(
                func.lower(Attraction.name)==func.lower(name),
                Attraction.latitude.is_not(None),
                Attraction.longitude.is_not(None),
                distance<=AttractionDeduplicator.DEFAULT_DISTANCE_METER,
            ).order_by(distance).limit(1)
        )

        row=db.execute(statement).first()
        if row is None:
            return None
        attraction=row[0]
        distance_meter=float(row[1])
        return (
            attraction,
            distance_meter
        )
