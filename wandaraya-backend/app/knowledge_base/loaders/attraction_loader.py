"""
Responsible of this module is insert and update the visting place from the postgre database
keep database transection handling safe 
"""

from __future__ import annotations
from datetime import datetime,timezone
from typing import Any, Dict, List, Optional
from sqlalchemy import func, select
from sqlalchemy.orm import Session


from app.models import Attraction
from app.models import AttractionImage


class AttractionLoader:

    @classmethod
    def upsert(
        cls,
        db: Session,
        attraction_data: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> Attraction:
        if attraction_data is None:
            attraction_data = kwargs.get("attraction")

        if attraction_data is None:
            raise ValueError("attraction_data or attraction must be provided")

        google_place_id = attraction_data.get("google_place_id")
        existing = None

        if google_place_id:
            statement = (
                select(Attraction)
                .where(Attraction.google_place_id == google_place_id)
                .limit(1)
            )
            existing = db.execute(statement).scalars().first()

        if existing:
            attraction_obj = cls._update_attraction(
                existing=existing,
                data=attraction_data,
            )
        else:
            attraction_obj = cls._create_attraction(data=attraction_data)
            db.add(attraction_obj)
            db.flush()

        cls._sync_image(
            db=db,
            attraction=attraction_obj,
            images=attraction_data.get("images", []),
        )

        attraction_obj.last_sync_at = datetime.now(timezone.utc)
        return attraction_obj


    @staticmethod
    def _create_attraction(
        data:Dict[str,Any],
    )->Attraction:
        return Attraction(
            name=data.get("name"),
            slug=data.get("slug"),
            description=data.get("description"),
            address=data.get("address"),
            district_id=data.get("district_id"),
            city=data.get("city"),
            latitude=data.get("latitude"),
            longitude=data.get("longitude"),
            location=data.get("location"),
            google_place_id=data.get(
                "google_place_id"
            ),
            rating=data.get("rating"),
            review_count=data.get(
                "review_count"
            ),
            price_level=data.get(
                "price_level"
            ),
            phone_number=data.get(
                "phone_number"
            ),
            website_url=data.get(
                "website_url"
            ),
            opening_hours=data.get(
                "opening_hours"
            ),
            vibe_tags=data.get(
                "vibe_tags"
            ),
            experience_tags=data.get(
                "experience_tags"
            ),
            best_visit_months=data.get(
                "best_visit_months"
            ),
            poya_sensitivity=data.get(
                "poya_sensitivity"
            ),
            is_active=data.get(
                "is_active",
                True,
            ),
        )

    @staticmethod
    def _update_attraction(
        existing:Attraction,
        data:Dict[str,Any],
    )->Attraction:
        fields = [
            "name",
            "address",
            "district_id",
            "city",
            "latitude",
            "longitude",
            "location",
            "rating",
            "review_count",
            "price_level",
            "phone_number",
            "website_url",
            "opening_hours",
            "is_active",
        ]
        for field in fields:
            if field  in data:
                setattr(existing, field, data[field])
        existing.last_sync_at=(
            datetime.now(timezone.utc)
        )

        return existing

    @classmethod

    def _sync_image(
        cls,
        db:Session,
        attraction:Attraction,
        images:List[Dict[str,Any]],
    )->None:
        for image in images[:2]:
            external_image_id = image.get(
                "external_image_id"
            )

            if not external_image_id:
                continue
            statement=(
                select(AttractionImage).where(
                    AttractionImage.attraction_id==attraction.id, AttractionImage.external_image_id==external_image_id,
                    AttractionImage.source_type==image.get("source_type")
                ).limit(1)
            )
            existing_image=(
                db.execute(statement).scalars().first(
                
                )
            )
            if existing_image:
                existing_image.width = image.get(
                    "width"
                )

                existing_image.height = image.get(
                    "height"
                )

                existing_image.attribution = (
                    image.get("attribution")
                )

                existing_image.is_primary = (
                    image.get(
                        "is_primary",
                        False,
                    )
                )

                existing_image.is_active = True

                existing_image.last_sync_at = (
                    datetime.now(timezone.utc)
                )

                continue

            new_image = AttractionImage(
                attraction_id=attraction.id,

                source_type=image.get(
                    "source_type"
                ),

                external_image_id=(
                    external_image_id
                ),

                original_url=image.get(
                    "original_url"
                ),

                bucket_name=image.get(
                    "bucket_name"
                ),

                storage_key=image.get(
                    "storage_key"
                ),

                mime_type=image.get(
                    "mime_type"
                ),

                file_name=image.get(
                    "file_name"
                ),

                file_size_bytes=image.get(
                    "file_size_bytes"
                ),

                width=image.get(
                    "width"
                ),

                height=image.get(
                    "height"
                ),

                attribution=image.get(
                    "attribution"
                ),

                content_hash=image.get(
                    "content_hash"
                ),

                is_primary=image.get(
                    "is_primary",
                    False,
                ),

                is_active=image.get(
                    "is_active",
                    True,
                ),

                retrieved_at=(
                    datetime.now(timezone.utc)
                ),

                last_sync_at=(
                    datetime.now(timezone.utc)
                ),
            )

            db.add(new_image)