from __future__ import annotations
import re
import unicodedata
from typing import Any, Dict, List, Optional


class AttractionNormalizer:

    @classmethod
    def normalize_google_place(
        cls,
        place:Dict[str,Any],
    )->Dict[str,Any]:
        display_name = place.get("displayName") or {}
        location=place.get("location") or {}

        name=cls._clean_string(
            display_name.get("text") or ""
        )
        latitude = cls._to_float(
            location.get("latitude")
        )

        longitude = cls._to_float(
            location.get("longitude")
        )

        address_components = (
            place.get("addressComponents") or []
        )

        city = cls._get_address_component(
            address_components,
            "locality",
        )
        administrative_area_level_2 = (
            cls._get_address_component(
                address_components,
                "administrative_area_level_2",
            )
        )

        province = cls._get_address_component(
            address_components,
            "administrative_area_level_1",
        )

        country = cls._get_address_component(
            address_components,
            "country",
        )

        postal_code = cls._get_address_component(
            address_components,
            "postal_code",
        )

        opening_hours = cls._normalize_opening_hours(
            place.get("regularOpeningHours")
        )

        photos = cls._normalize_google_photos(
            place.get("photos") or [],
            limit=2,
        )

        business_status = cls._clean_string(
            place.get("businessStatus")
        )

        is_active=(
            business_status != "CLOSED_TEMPORARILY"
        )

        return {
            # -------------------------------------------------
            # Core Attraction fields
            # -------------------------------------------------

            "name": name,

            "slug": (
                cls._slugify(name)
                if name
                else None
            ),

            "google_place_id": cls._clean_string(
                place.get("id")
            ),

            "description": None,

            "address": cls._clean_string(
                place.get("formattedAddress")
            ),

            # district_id is deliberately NOT determined here.
            "district_id": None,

            "city": city,

            "latitude": latitude,

            "longitude": longitude,

            "location": (
                {
                    "latitude": latitude,
                    "longitude": longitude,
                }
                if latitude is not None
                and longitude is not None
                else None
            ),

            "rating": cls._to_float(
                place.get("rating")
            ),

            "review_count": cls._to_int(
                place.get("userRatingCount")
            ),

            "price_level": cls._normalize_price_level(
                place.get("priceLevel")
            ),

            "phone_number": (
                cls._clean_string(
                    place.get(
                        "internationalPhoneNumber"
                    )
                )
                or cls._clean_string(
                    place.get(
                        "nationalPhoneNumber"
                    )
                )
            ),

            "website_url": cls._clean_string(
                place.get("websiteUri")
            ),

            "opening_hours": opening_hours,

            # These will be generated/enriched later.
            "vibe_tags": None,
            "experience_tags": None,
            "best_visit_months": None,
            "poya_sensitivity": None,

            "is_active": is_active,

            # -------------------------------------------------
            # Source metadata
            # Not necessarily direct Attraction DB columns.
            # -------------------------------------------------

            "source_metadata": {
                "source": "google_places",

                "primary_type": cls._clean_string(
                    place.get("primaryType")
                ),

                "types": place.get("types") or [],

                "business_status": business_status,

                "google_maps_uri": cls._clean_string(
                    place.get("googleMapsUri")
                ),

                "language_code": cls._clean_string(
                    display_name.get("languageCode")
                ),

                "address_components": {
                    "city": city,
                    "administrative_area_level_2":
                        administrative_area_level_2,
                    "province": province,
                    "country": country,
                    "postal_code": postal_code,
                },
            },

            # -------------------------------------------------
            # Image metadata
            # Separate from Attraction DB row.
            # -------------------------------------------------

            "images": photos,
        }

    @classmethod
    def _normalize_google_photos(
        cls,
        photos: List[Dict[str, Any]],
        limit: int = 2,
    )->List[Dict[str,Any]]:
        normalized_photos: List[
            Dict[str, Any]
        ] = []

        for index, photo in enumerate(
            photos[:limit]
        ):
            photo_name = cls._clean_string(
                photo.get("name")
            )

            if not photo_name:
                continue

            normalized_photos.append(
                {
                    "source_type": "google_places",

                    "external_image_id": photo_name,

                    # Do not set this to the attribution
                    # photoUri. That is the contributor avatar.
                    "original_url": None,

                    # Google image is not being placed
                    # in MinIO at this stage.
                    "bucket_name": None,
                    "storage_key": None,

                    "mime_type": None,
                    "file_name": None,
                    "file_size_bytes": None,

                    "width": cls._to_int(
                        photo.get("widthPx")
                    ),

                    "height": cls._to_int(
                        photo.get("heightPx")
                    ),

                    "attribution": (
                        photo.get(
                            "authorAttributions"
                        )
                        or []
                    ),

                    "content_hash": None,

                    "is_primary": index == 0,
                    "is_active": True,
                }
            )

        return normalized_photos
    @staticmethod
    def _get_address_component(
        components:List[Dict[str,Any]],
        component_type:str,
    )->Optional[str]:
        for component in components:
            type=component.get("types") or []
            if component_type in type:
                value=component.get("longText")
                if isinstance(value,str):
                    value=value.strip()

                    if value:
                        return value

        return None

    @staticmethod
    def _normalize_opening_hours(
        opening_hours: Optional[Dict[str, Any]],
    )->Optional[Dict[str,Any]]:
        if not opening_hours:
            return None

        return {
            "open_now": opening_hours.get(
                "openNow"
            ),

            "periods": opening_hours.get(
                "periods",
                [],
            ),

            "weekday_descriptions":
                opening_hours.get(
                    "weekdayDescriptions",
                    [],
                ),
        }
    @staticmethod
    def _normalize_price_level(
        price_level: Any,
    ) -> Optional[int]:
        """
        Convert Google Places price-level enum into the
        integer structure expected by the current Attraction
        model.

        0 = Free
        1 = Inexpensive
        2 = Moderate
        3 = Expensive
        4 = Very Expensive
        """

        if price_level is None:
            return None

        if isinstance(price_level, int):
            return price_level

        mapping = {
            "PRICE_LEVEL_FREE": 0,
            "PRICE_LEVEL_INEXPENSIVE": 1,
            "PRICE_LEVEL_MODERATE": 2,
            "PRICE_LEVEL_EXPENSIVE": 3,
            "PRICE_LEVEL_VERY_EXPENSIVE": 4,
        }

        return mapping.get(str(price_level))
    @staticmethod
    def _slugify(
        value: str,
    ) -> str:
        """
        Convert attraction name into URL-friendly slug.

        Example:
        Galle Dutch Fort -> galle-dutch-fort
        """

        value = unicodedata.normalize(
            "NFKD",
            value,
        )

        value = value.encode(
            "ascii",
            "ignore",
        ).decode("ascii")

        value = value.lower().strip()

        value = re.sub(
            r"[^a-z0-9]+",
            "-",
            value,
        )

        return value.strip("-")
    @staticmethod
    def _clean_string(
        value: Any,
    ) -> Optional[str]:

        if value is None:
            return None

        value = str(value).strip()

        return value if value else None

    @staticmethod
    def _to_float(
        value: Any,
    ) -> Optional[float]:

        if value is None:
            return None

        try:
            return float(value)

        except (TypeError, ValueError):
            return None

    @staticmethod
    def _to_int(
        value: Any,
    ) -> Optional[int]:

        if value is None:
            return None

        try:
            return int(value)

        except (TypeError, ValueError):
            return None
