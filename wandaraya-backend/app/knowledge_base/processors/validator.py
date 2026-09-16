from __future__ import annotations

from dataclasses import dataclass,field
from typing import Any, Dict, List, Optional

@dataclass
class  ValidationResult:
    is_valid:bool
    errors:List[str]=field(
        default_factory=list
    )
    warnings:List[str]=field(
        default_factory=list
    )

class AttractionValidation:
    SRI_LANKA_BOUNDS = {
        "min_latitude": 5.8,
        "max_latitude": 10.0,
        "min_longitude": 79.5,
        "max_longitude": 82.0,
    }

    # Generic Google types that do not provide meaningful
    # tourism classification.
    GENERIC_TYPES = {
        "point_of_interest",
        "establishment",
    }

    # Types that should not normally enter the attraction KB
    # by themselves.
    EXCLUDED_PRIMARY_TYPES = {
        "atm",
        "bank",
        "gas_station",
        "pharmacy",
        "hospital",
        "doctor",
        "dentist",
        "car_repair",
        "car_dealer",
        "parking",
        "supermarket",
    }

    @classmethod
    def validate(
        cls,attraction:Dict[str,Any],
        
    )->ValidationResult:
        errors:List[str]=[]
        warnings:List[str]=[]

        name=attraction.get("name")
        if not name:
            errors.append("Attraction name is missing")


        google_place_id = attraction.get("google_place_id" )
        if not google_place_id:
            errors.append(
                "Google Place ID is missing."
            )
        google_place_id = attraction.get(
            "google_place_id"
        )

        if not google_place_id:
            errors.append(
                "Google Place ID is missing."
            )
        metadata = (
            attraction.get("source_metadata")
            or {}
        )

        address_components = (
            metadata.get("address_components")
            or {}
        )

        country = address_components.get(
            "country"
        )

        if country:
            normalized_country = (
                country.strip().lower()
            )

            if normalized_country not in {
                "sri lanka",
                "lk",
            }:
                errors.append(
                    f"Place is outside Sri Lanka: {country}"
                )
        else:
            warnings.append(
                "Country was not available from source data."
            )

        business_status = metadata.get(
            "business_status"
        )

        if (
            business_status
            == "CLOSED_PERMANENTLY"
        ):
            errors.append(
                "Place is permanently closed."
            )
        google_types = set(
            metadata.get("types") or []
        )

        primary_type = metadata.get(
            "primary_type"
        )

        if not google_types:
            warnings.append(
                "Google place types are missing."
            )

        if (
            primary_type
            in cls.EXCLUDED_PRIMARY_TYPES
        ):
            errors.append(
                "Place has an excluded primary type: "
                f"{primary_type}"
            )

        meaningful_types = (
            google_types
            - cls.GENERIC_TYPES
        )

        if not meaningful_types:
            warnings.append(
                "Place contains only generic Google types."
            )
        if not attraction.get("address"):
            warnings.append(
                "Formatted address is missing."
            )
        return ValidationResult(
            is_valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
        )
    @classmethod
    def _validate_coordinates(
        cls,
        latitude: float,
        longitude: float,
        errors: List[str],
    )->None:
        if not -90 <= latitude <= 90:
            errors.append(
                f"Invalid latitude: {latitude}"
            )
            return

        if not -180 <= longitude <= 180:
            errors.append(
                f"Invalid longitude: {longitude}"
            )
            return

        bounds = cls.SRI_LANKA_BOUNDS

        if not (
            bounds["min_latitude"]
            <= latitude
            <= bounds["max_latitude"]
        ):
            errors.append(
                "Latitude is outside the expected "
                "Sri Lankan geographic range."
            )

        if not (
            bounds["min_longitude"]
            <= longitude
            <= bounds["max_longitude"]
        ):
            errors.append(
                "Longitude is outside the expected "
                "Sri Lankan geographic range."
            )