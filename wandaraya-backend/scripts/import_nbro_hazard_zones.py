"""
NBRO Landslide Data & Hazard Zonation Map (LHMP) Database Import Script
========================================================================
Imports the official NBRO 1:50,000 Landslide Hazard Zonation Map (LHMP) dataset
into PostgreSQL/PostGIS and ensures spatial Point geometries and GiST indexes
exist across all NBRO tables (nbro_hazard_zones, nbro_incidents, nbro_inspections, nbro_polygons).

CRS Transformation:
- Source: EPSG:5234 (Kandawala / Sri Lanka Grid 1999, Easting/Northing in meters)
- Target: EPSG:4326 (WGS-84, Latitude/Longitude degrees)

Run command:
  python scripts/import_nbro_hazard_zones.py
"""

from __future__ import annotations

import logging
import os
import sys
import time
from pathlib import Path
from typing import Dict, Any

import pandas as pd
import pyproj
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

# Set up logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("nbro_import")

BASE_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = BASE_DIR / "data" / "NBRO_DATA"
ENV_PATH = BASE_DIR / ".env"

if ENV_PATH.exists():
    load_dotenv(ENV_PATH)

def get_engine():
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        raise RuntimeError("DATABASE_URL is not set in environment or .env")
    sync_url = db_url.replace("+asyncpg", "").replace("+psycopg", "")
    return create_engine(sync_url)

def upgrade_existing_nbro_spatial_columns(engine) -> Dict[str, Any]:
    """Adds PostGIS geometry columns and GiST spatial indexes to nbro_incidents and nbro_inspections."""
    logger.info("Checking and upgrading geometry columns on existing NBRO tables...")
    results = {}
    with engine.begin() as conn:
        # 1. nbro_incidents
        conn.execute(text("ALTER TABLE public.nbro_incidents ADD COLUMN IF NOT EXISTS geom geometry(Point, 4326);"))
        conn.execute(text("""
            UPDATE public.nbro_incidents
            SET geom = ST_SetSRID(ST_MakePoint(longitude, latitude), 4326)
            WHERE geom IS NULL AND latitude IS NOT NULL AND longitude IS NOT NULL;
        """))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_nbro_incidents_geom ON public.nbro_incidents USING gist (geom);"))
        inc_geom_cnt = conn.execute(text("SELECT count(*) FROM public.nbro_incidents WHERE geom IS NOT NULL;")).scalar()
        results["nbro_incidents_with_geom"] = inc_geom_cnt
        logger.info(f"  [OK] nbro_incidents: {inc_geom_cnt} records with PostGIS Point geometries (SRID 4326).")

        # 2. nbro_inspections
        conn.execute(text("ALTER TABLE public.nbro_inspections ADD COLUMN IF NOT EXISTS geom geometry(Point, 4326);"))
        conn.execute(text("""
            UPDATE public.nbro_inspections
            SET geom = ST_SetSRID(ST_MakePoint(longitude, latitude), 4326)
            WHERE geom IS NULL AND latitude IS NOT NULL AND longitude IS NOT NULL;
        """))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_nbro_inspections_geom ON public.nbro_inspections USING gist (geom);"))
        insp_geom_cnt = conn.execute(text("SELECT count(*) FROM public.nbro_inspections WHERE geom IS NOT NULL;")).scalar()
        results["nbro_inspections_with_geom"] = insp_geom_cnt
        logger.info(f"  [OK] nbro_inspections: {insp_geom_cnt} records with PostGIS Point geometries (SRID 4326).")

    return results

def import_nbro_hazard_zones(engine, batch_size: int = 10000) -> Dict[str, Any]:
    """Imports LHMP_LHZM_50000_ALL_LHMP_50000.csv into public.nbro_hazard_zones table."""
    csv_path = DATA_DIR / "LHMP_LHZM_50000_ALL_LHMP_50000.csv"
    if not csv_path.exists():
        logger.error(f"Source file not found: {csv_path}")
        return {"status": "FILE_NOT_FOUND", "path": str(csv_path)}

    logger.info(f"Found LHMP dataset: {csv_path} ({csv_path.stat().st_size:,} bytes)")

    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS public.nbro_hazard_zones (
                id SERIAL PRIMARY KEY,
                hazard_range DOUBLE PRECISION NOT NULL,
                hazard_class VARCHAR(50) NOT NULL,
                susceptibility_score DOUBLE PRECISION NOT NULL,
                centroid_x DOUBLE PRECISION NOT NULL,
                centroid_y DOUBLE PRECISION NOT NULL,
                latitude DOUBLE PRECISION NOT NULL,
                longitude DOUBLE PRECISION NOT NULL,
                source_crs VARCHAR(20) DEFAULT 'EPSG:5234',
                geom geometry(Point, 4326) NOT NULL,
                created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT (NOW() AT TIME ZONE 'utc')
            );
        """))
        
        current_cnt = conn.execute(text("SELECT count(*) FROM public.nbro_hazard_zones;")).scalar()
        if current_cnt >= 194000:
            logger.info(f"nbro_hazard_zones already contains {current_cnt} records. Skipping re-import.")
            return {"status": "ALREADY_IMPORTED", "record_count": current_cnt}

    # Setup Coordinate Transformer: EPSG:5234 (Kandawala SL Grid 1999) -> EPSG:4326 (WGS84)
    transformer = pyproj.Transformer.from_crs("EPSG:5234", "EPSG:4326", always_xy=True)

    def map_hazard_class(r: float) -> str:
        if r == 1.0: return "LOW_HAZARD"
        if r == 2.0: return "MODEST_HAZARD"
        if r == 3.0: return "HIGH_HAZARD"
        if r == 4.0: return "VERY_HIGH_HAZARD"
        return "WATER_BODY_UNCLASSIFIED"

    def map_susceptibility(r: float) -> float:
        if r == 1.0: return 15.0
        if r == 2.0: return 40.0
        if r == 3.0: return 75.0
        if r == 4.0: return 95.0
        return 0.0

    t0 = time.time()
    logger.info("Reading CSV and transforming coordinates...")
    df = pd.read_csv(csv_path)
    total_source_rows = len(df)
    logger.info(f"Loaded {total_source_rows:,} source records. Transforming coordinates to EPSG:4326...")

    x_vals = df["Centroid_X_m"].values
    y_vals = df["Centroid_Y_m"].values
    lons, lats = transformer.transform(x_vals, y_vals)
    df["longitude"] = lons
    df["latitude"] = lats
    df["hazard_class"] = df["Range"].map(map_hazard_class)
    df["susceptibility_score"] = df["Range"].map(map_susceptibility)

    # Insert into database in batches using SQL
    logger.info(f"Writing {total_source_rows:,} records to public.nbro_hazard_zones in batches of {batch_size:,}...")
    
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE TABLE public.nbro_hazard_zones RESTART IDENTITY;"))
        
        total_inserted = 0
        for start_idx in range(0, total_source_rows, batch_size):
            batch = df.iloc[start_idx:start_idx + batch_size]
            rows_data = []
            for _, r in batch.iterrows():
                rows_data.append({
                    "hr": float(r["Range"]),
                    "hc": str(r["hazard_class"]),
                    "ss": float(r["susceptibility_score"]),
                    "cx": float(r["Centroid_X_m"]),
                    "cy": float(r["Centroid_Y_m"]),
                    "lat": float(r["latitude"]),
                    "lon": float(r["longitude"]),
                })
            
            conn.execute(
                text("""
                    INSERT INTO public.nbro_hazard_zones 
                    (hazard_range, hazard_class, susceptibility_score, centroid_x, centroid_y, latitude, longitude, geom)
                    VALUES (:hr, :hc, :ss, :cx, :cy, :lat, :lon, ST_SetSRID(ST_MakePoint(:lon, :lat), 4326));
                """),
                rows_data
            )
            total_inserted += len(rows_data)
            logger.info(f"  Inserted {total_inserted:,} / {total_source_rows:,} records...")

        # Create GiST and BTree indexes
        logger.info("Creating spatial GiST index on nbro_hazard_zones(geom)...")
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_nbro_hazard_zones_geom ON public.nbro_hazard_zones USING gist (geom);"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_nbro_hazard_zones_range ON public.nbro_hazard_zones (hazard_range);"))

    elapsed = time.time() - t0
    logger.info(f"Successfully imported {total_inserted:,} LHMP records in {elapsed:.1f}s.")
    return {
        "status": "SUCCESS",
        "total_source_rows": total_source_rows,
        "total_imported": total_inserted,
        "elapsed_seconds": round(elapsed, 2)
    }

def verify_import(engine) -> Dict[str, Any]:
    """Verifies table counts, SRIDs, geometry validity, and spatial extent."""
    logger.info("Executing PostGIS verification queries...")
    results = {}
    with engine.connect() as conn:
        # Table count
        count = conn.execute(text("SELECT count(*) FROM public.nbro_hazard_zones;")).scalar()
        results["hazard_zones_count"] = count

        # Range distribution
        dist = conn.execute(text("""
            SELECT hazard_range, hazard_class, count(*) 
            FROM public.nbro_hazard_zones 
            GROUP BY hazard_range, hazard_class 
            ORDER BY hazard_range;
        """)).fetchall()
        results["range_distribution"] = [dict(r._mapping) for r in dist]

        # Geometry and SRID validity
        geom_info = conn.execute(text("""
            SELECT ST_SRID(geom) as srid, GeometryType(geom) as geom_type, count(*) as count
            FROM public.nbro_hazard_zones
            GROUP BY ST_SRID(geom), GeometryType(geom);
        """)).fetchall()
        results["geometry_info"] = [dict(r._mapping) for r in geom_info]

        # Check for invalid geometries
        invalid_cnt = conn.execute(text("""
            SELECT count(*) FROM public.nbro_hazard_zones WHERE geom IS NULL OR NOT ST_IsValid(geom);
        """)).scalar()
        results["invalid_geometry_count"] = invalid_cnt

        # Spatial extent
        extent = conn.execute(text("""
            SELECT 
                min(latitude) as min_lat, max(latitude) as max_lat,
                min(longitude) as min_lon, max(longitude) as max_lon
            FROM public.nbro_hazard_zones;
        """)).fetchone()
        results["spatial_extent"] = dict(extent._mapping)

        # Spatial index check
        indices = conn.execute(text("""
            SELECT indexname, indexdef FROM pg_indexes WHERE tablename = 'nbro_hazard_zones';
        """)).fetchall()
        results["indexes"] = [dict(r._mapping) for r in indices]

    logger.info(f"Verification Results:\n{results}")
    return results

if __name__ == "__main__":
    engine = get_engine()
    upgrade_existing_nbro_spatial_columns(engine)
    import_nbro_hazard_zones(engine, batch_size=10000)
    verify_import(engine)
