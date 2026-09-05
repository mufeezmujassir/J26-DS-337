"""
Purpose
-------
Imports Sri Lankan district boundary GeoJSON data into
PostgreSQL/PostGIS using SQLAlchemy + GeoAlchemy2.

Supported sources
-----------------
1. NSDI
2. geoBoundaries

Features
--------
- 25-district validation
- Polygon -> MultiPolygon conversion
- Geometry validation
- Geometry repair using make_valid()
- WGS84 / EPSG:4326 enforcement
- District name normalization
- Province normalization
- Insert/update (idempotent)
- Transaction safety
- Automatic rollback on failure
- Latitude/longitude derived from representative point
- CLI source selection
- Dry-run mode
- Detailed logging

Usage
-----

NSDI:
    python scripts/import_districts.py --source nsdi

geoBoundaries:
    python scripts/import_districts.py --source geoboundaries

Dry run:
    python scripts/import_districts.py --source nsdi --dry-run

"""


from __future__ import annotations
import json
import logging
import os
import sys
from typing import Any, Dict, List, Optional, Tuple
from pathlib import Path
import argparse

import pandas as pd


from dotenv import load_dotenv
from geoalchemy2.shape import from_shape
from shapely.geometry import shape, MultiPolygon, Polygon
from shapely.validation import make_valid
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session



PROJECT_ROOT = Path(__file__).parent.parent

if PROJECT_ROOT not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from app.models.district import District

load_dotenv(dotenv_path=PROJECT_ROOT / ".env")

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL environment variable is not set.")

DATA_DIRECTORY=(
PROJECT_ROOT / "data" / "boundaries"
)

SOURCE_FILES = { 
    "nsdi": DATA_DIRECTORY / "nsdi_districts.geojson",
    "geoboundaries": DATA_DIRECTORY / "geoboundaries_districts.geo"
 }

EXPECTED_DISTRICT_COUNT = 25
WGS84_SRID = 4326


#============= LOGGING ===========

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)

logger = logging.getLogger("wandaraya.district_import")

EXPECTED_DISTRICTS={
    "Colombo",
    "Gampaha",
    "Kalutara",

    "Matara",
    "Galle",
    "Hambantota",

    "Ampara",
    "Batticaloa",
    "Trincomalee",

    "Kandy",
    "Matale",
    "Nuwara Eliya",

    "Jaffna",
    "Kilinochchi",
    "Mannar",
    "Mullaitivu",
    "Vavuniya",

    "Kurunegala",
    "Puttalam",

    "Anuradhapura",
    "Polonnaruwa",

    "Badulla",
    "Moneragala",

    "Ratnapura",
    "Kegalle"

}

DISTRICT_TO_PROVINCE={

    "Colombo": "Western",
    "Gampaha": "Western",
    "Kalutara": "Western",

    "Matara": "Southern",
    "Galle": "Southern",
    "Hambantota": "Southern",

    "Ampara": "Eastern",
    "Batticaloa": "Eastern",
    "Trincomalee": "Eastern",

    "Kandy": "Central",
    "Matale": "Central",
    "Nuwara Eliya": "Central",

    "Jaffna": "Northern",
    "Kilinochchi": "Northern",
    "Mannar": "Northern",
    "Mullaitivu": "Northern",
    "Vavuniya": "Northern",

    "Kurunegala": "North Western",
    "Puttalam": "North Western",

    "Anuradhapura": "North Central",
    "Polonnaruwa": "North Central",

    "Badulla": "Uva",
    "Monaragala": "Uva",

    "Ratnapura": "Sabaragamuwa",
    "Kegalle": "Sabaragamuwa"

}

DISTRICT_NAME_ALIASES = {

    "Colombo District": "Colombo",
    "Gampaha District": "Gampaha",
    "Kalutara District": "Kalutara",

    "Kandy District": "Kandy",
    "Matale District": "Matale",
    "Nuwara Eliya District": "Nuwara Eliya",

    "Galle District": "Galle",
    "Matara District": "Matara",
    "Hambantota District": "Hambantota",

    "Jaffna District": "Jaffna",
    "Kilinochchi District": "Kilinochchi",
    "Mannar District": "Mannar",
    "Mullaitivu District": "Mullaitivu",
    "Vavuniya District": "Vavuniya",

    "Batticaloa District": "Batticaloa",
    "Ampara District": "Ampara",
    "Trincomalee District": "Trincomalee",

    "Kurunegala District": "Kurunegala",
    "Puttalam District": "Puttalam",

    "Anuradhapura District": "Anuradhapura",
    "Polonnaruwa District": "Polonnaruwa",

    "Badulla District": "Badulla",
    "Monaragala District": "Monaragala",

    "Ratnapura District": "Ratnapura",
    "Kegalle District": "Kegalle",
}

def parse_arguments() -> argparse.Namespace:

    parser = argparse.ArgumentParser(
        description=(
            "Import Sri Lankan district "
            "boundaries into WANDARAYA PostGIS."
        )
    )

    parser.add_argument(
        "--source",
        required=True,
        choices=[
            "nsdi",
            "geoboundaries",
        ],
        help="Boundary dataset to import.",
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help=(
            "Validate and process data without "
            "committing database changes."
        ),
    )

    return parser.parse_args()


def load_geojson(file_path: Path) -> Dict[str, Any]:

    logger.info(f"Loading GeoJSON file: {file_path}")
    if not file_path.exists():
        raise FileNotFoundError(f"GeoJSON file not found: {file_path}")

    with file_path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    if data.get("type")!="FeatureCollection":
        raise ValueError("Invalid GeoJSON: Expected FeatureCollection")

    features = data.get("features", [])

    if not isinstance(features, list):
        raise ValueError("Invalid GeoJSON: 'features' must be a list")

    logger.info("Feature load: %d features", len(features))
    return data








#District name normalization

def normalize_district_name(properties:dict[str,Any],
    source:str) -> str:
    if source == "nsdi":
        raw_name= properties.get("district_name")
    elif source == "geoboundaries":
        raw_name = properties.get("shapeName")
    else:
        raise ValueError(f"Invalid source: {source}"                            )

    if not raw_name:
        raise ValueError("District name is missing in properties")

    raw_name=str(raw_name).strip()

    if raw_name in EXPECTED_DISTRICTS:
        return raw_name
    if raw_name in DISTRICT_NAME_ALIASES:
        return DISTRICT_NAME_ALIASES[raw_name]

    #clean remove the District key wrd

    cleaned=raw_name.replace("District","").strip()
    if cleaned in EXPECTED_DISTRICTS:
        return cleaned
    raise ValueError(f"Unrecognized district name: {raw_name}")




# Province details fetchinng

def get_province(district_name:str,
                 properties:dict[str,Any],
                 source:str) -> str:
    if source == "nsdi":
        province=properties.get("province_name")
        if not province:
            raise ValueError(f"Province name missing for district: {district_name}")
        return str(province).strip()

    province=DISTRICT_TO_PROVINCE.get(district_name)
    if not province:
        raise ValueError(f"Province mapping missing for district: {district_name}")

    return province



#Geomatry conversation convert polygon to multipolygon

def convert_to_multipolygon(geomatry_data:dict[str,Any],)->Multipolygon:
    if not geomatry_data:
        raise ValueError("Geometry data is missing")

    geometry=shape(geomatry_data)

    if geometry.is_empty:
        raise ValueError("Geometry is empty")
    logger.debug("Original geometry type: %s", geometry.geom_type)


    if not geometry.is_valid:
        logger.warning("Invalid geometry detected. Attempting to repair using make_valid()")
        geometry=make_valid(geometry)



    if geometry.geom_type=="Polygon":
        geometry=MultiPolygon([geometry])

    elif geometry.geom_type=="MultiPolygon":
        pass
    else:
        raise ValueError(f"Unsupported geometry type: {geometry.geom_type}")


    #final validation
    if geometry.is_empty:
        raise ValueError("Final geometry is empty after conversion")

    if not geometry.is_valid:
        raise ValueError("Final geometry is invalid after conversion")

    return geometry



#FEATURE VALIDATION

def validate_feature(
        features:list[Dict[str,Any]],
        source:str,

)-> list[dict[str,Any]]:
    logger.info("Validating features from source: %s", source)

    if len(features)!=EXPECTED_DISTRICT_COUNT:
        raise ValueError(
            f"Expected {EXPECTED_DISTRICT_COUNT} features, "
            f"but found {len(features)}"
        )
    normalized_names: set[str] = set()

    processed_features=[]

    for index, feature in enumerate(features,start=1):
        properties=feature.get("properties",{})

        district_name=(normalize_district_name(
            properties,
            source,
        ))
        if district_name in normalized_names:
            raise ValueError(f"Duplicate district name found: {district_name}")
        normalized_names.add(district_name)

        province_name=get_province(
            district_name,
            properties,
            source,
        )

        geometry=convert_to_multipolygon(
            feature.get("geometry",{}),
        )

        processed_features.append(
            {
                "name":district_name,
                "province":province_name,
                "geometry":geometry,
            }
        )

        logger.info(
            "Processed feature %d/%d: %s, Province: %s",
            index,
            len(features),
            district_name,
            province_name,
        )


#Verify all the expected districts are present

    missing=(
        EXPECTED_DISTRICTS
        - normalized_names
    )

    unexpected=(
        normalized_names
        - EXPECTED_DISTRICTS
    )

    if missing:
        raise ValueError(
            f"Missing expected districts: {', '.join(missing)}"
        )
    if unexpected:
        raise ValueError(
            f"Unexpected districts found: {', '.join(unexpected)}"
        )

    logger.info("All features validated successfully.")
    return processed_features



# DATABASE IMPORTING

def import_to_database(
        districts:list[dict[str,Any]],
        dry_run:bool=False

)->None:
    logger.info("Importing districts into database. Dry run: %s", dry_run)

    engine=create_engine(DATABASE_URL, pool_pre_ping=True)
    inserted_count=0
    updated_count=0

    try:
        with Session(engine)as session:
            for district in districts:
                name=district["name"]
                province=district["province"]
                geometry=district["geometry"]

                representative_point = (
                    geometry.representative_point()
                )

                longitude = (
                    representative_point.x
                )

                latitude = (
                    representative_point.y
                )

                boundary = from_shape(
                    geometry,
                    srid=WGS84_SRID,
                )
                existing = session.scalar(
                    select(District).where(
                        District.name == name
                    )
                )

                if existing:

                    logger.info(
                        "UPDATE: %s",
                        name,
                    )

                    existing.province = (
                        province
                    )

                    existing.latitude = (
                        latitude
                    )

                    existing.longitude = (
                        longitude
                    )

                    existing.boundary = (
                        boundary
                    )

                    existing.is_active = True

                    updated_count += 1

                else:

                    logger.info(
                        "INSERT: %s",
                        name,
                    )

                    district = District(
                        name=name,
                        province=province,
                        latitude=latitude,
                        longitude=longitude,
                        elevation_m=None,
                        boundary=boundary,
                        is_active=True,
                    )

                    session.add(
                        district
                    )

                    inserted_count += 1
            if dry_run:

                logger.warning(
                    "DRY RUN enabled. "
                    "Rolling back all changes."
                )

                session.rollback()

            else:

                session.commit()

                logger.info(
                    "Database transaction committed."
                )

    except Exception:

        logger.exception(
            "District import failed. "
            "Rolling back transaction."
        )

        raise

    finally:

        engine.dispose()

    logger.info(
        "----------------------------------------"
    )

    logger.info(
        "District import completed."
    )

    logger.info(
        "Inserted : %d",
        inserted_count,
    )

    logger.info(
        "Updated  : %d",
        updated_count,
    )

    logger.info(
        "Processed: %d",
        inserted_count + updated_count,
    )

def main()->None:
    args = parse_arguments()

    source = args.source

    file_path = SOURCE_FILES[
        source
    ]

    logger.info(
        "========================================"
    )

    logger.info(
        "WANDARAYA District Boundary Import"
    )

    logger.info(
        "Source: %s",
        source,
    )

    logger.info(
        "========================================"
    )

    # -----------------------------------------------------
    # Load
    # -----------------------------------------------------

    geojson = load_geojson(
        file_path
    )

    # -----------------------------------------------------
    # Validate + normalize
    # -----------------------------------------------------

    districts = validate_feature(
        geojson["features"],
        source,
    )

    # -----------------------------------------------------
    # Import
    # -----------------------------------------------------

    import_to_database(
        districts,
        dry_run=args.dry_run,
    )

if __name__ == "__main__":

    main()