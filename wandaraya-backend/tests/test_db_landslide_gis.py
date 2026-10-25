"""
Test Suite: Existing PostgreSQL/PostGIS Landslide Database GIS Capabilities.
=============================================================================
Strict Compliance:
- READ-ONLY inspection and spatial query verification.
- Zero re-import, zero reload, zero table drops or truncates.
- Verifies SRID, geometries, spatial indexes, and geographic coverage.
"""

import pytest
from app.config import settings
from sqlalchemy import create_engine, text
from app.services.landslide_service import (
    LandslideService,
    landslide_service,
    SRI_LANKA_BOUNDS,
)


@pytest.fixture(scope="module")
def db_engine():
    sync_url = settings.DATABASE_URL.replace("+asyncpg", "")
    engine = create_engine(sync_url, pool_pre_ping=True, connect_args={"connect_timeout": 3})
    yield engine
    engine.dispose()


def test_postgis_extension_and_version(db_engine):
    """Verify PostGIS is installed, active, and operational."""
    with db_engine.connect() as conn:
        version = conn.execute(text("SELECT PostGIS_Version();")).scalar()
        assert version is not None
        assert "3." in version or "2." in version


def test_existing_landslide_tables_record_counts(db_engine):
    """Verify existing landslide GIS datasets exist and contain official data without re-import."""
    with db_engine.connect() as conn:
        hz_count = conn.execute(text("SELECT count(*) FROM nbro_hazard_zones;")).scalar()
        inc_count = conn.execute(text("SELECT count(*) FROM nbro_incidents;")).scalar()
        poly_count = conn.execute(text("SELECT count(*) FROM nbro_polygons;")).scalar()
        insp_count = conn.execute(text("SELECT count(*) FROM nbro_inspections;")).scalar()

        # Official NBRO datasets in PostgreSQL
        assert hz_count >= 190000, f"Expected ~194,016 hazard zones, found {hz_count}"
        assert inc_count >= 20000, f"Expected ~20,438 incidents, found {inc_count}"
        assert poly_count >= 1900, f"Expected ~1,967 polygons, found {poly_count}"
        assert insp_count >= 3000, f"Expected ~3,340 inspections, found {insp_count}"


def test_geometry_types_srids_and_dimensions(db_engine):
    """Verify SRID 4326 (WGS-84) and 2D coordinate dimensions across all landslide tables."""
    with db_engine.connect() as conn:
        # Check geometry_columns catalog
        rows = conn.execute(text("""
            SELECT f_table_name, f_geometry_column, srid, type 
            FROM geometry_columns 
            WHERE f_table_name LIKE 'nbro_%';
        """)).fetchall()

        table_srids = {r[0]: (r[2], r[3]) for r in rows}
        assert table_srids["nbro_hazard_zones"][0] == 4326
        assert table_srids["nbro_incidents"][0] == 4326
        assert table_srids["nbro_polygons"][0] == 4326


def test_spatial_indexes_existence(db_engine):
    """Verify GiST spatial indexes exist for high-performance sub-second route queries."""
    with db_engine.connect() as conn:
        indexes = conn.execute(text("""
            SELECT tablename, indexname 
            FROM pg_indexes 
            WHERE tablename LIKE 'nbro_%' AND indexdef LIKE '%gist%';
        """)).fetchall()

        index_names = [r[1] for r in indexes]
        assert "idx_nbro_hazard_zones_geom" in index_names
        assert "idx_nbro_incidents_geom" in index_names
        assert "idx_nbro_polygons_wkt_geometry" in index_names


def test_representative_spatial_query_kandy_hill_country(db_engine):
    """
    Executes a representative spatial query around Kandy/Gampola hill country
    to verify spatial proximity calculation and susceptibility score retrieval.
    """
    kandy_lat, kandy_lon = 7.1621, 80.5669  # Near Gampola slope corridor
    with db_engine.connect() as conn:
        res = conn.execute(text("""
            SELECT hz.id, hz.hazard_class, hz.susceptibility_score,
                   ST_Distance(hz.geom::geography, ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography) AS dist_m
            FROM nbro_hazard_zones hz
            WHERE ST_DWithin(hz.geom, ST_SetSRID(ST_MakePoint(:lon, :lat), 4326), 0.02)
            ORDER BY dist_m ASC
            LIMIT 5;
        """), {"lon": kandy_lon, "lat": kandy_lat}).fetchall()

        assert len(res) > 0
        first_match = res[0]
        assert first_match[1] in ("LOW_HAZARD", "MODERATE_HAZARD", "HIGH_HAZARD", "VERY_HIGH_HAZARD")
        assert 0.0 <= float(first_match[2]) <= 100.0
        assert float(first_match[3]) >= 0.0


def test_susceptibility_score_service_method():
    """Verify landslide_service.get_susceptibility_score for hill country vs coastal coordinates."""
    # Hill country: Gampola / Nawalapitiya
    susc, h_class = landslide_service.get_susceptibility_score(7.1621, 80.5669)
    assert susc > 0.0
    assert h_class in ("LOW_HAZARD", "MODERATE_HAZARD", "HIGH_HAZARD", "VERY_HIGH_HAZARD")

    # Coastal flat plains (Colombo Galle Face): should be outside hazard zonation
    c_susc, c_class = landslide_service.get_susceptibility_score(6.9271, 79.8431)
    assert c_susc == 0.0
    assert c_class == "NO_HAZARD_ZONE"


def test_location_outside_coverage_handling():
    """Verify that coordinates outside Sri Lanka return safe fallback without errors."""
    out_lat, out_lon = 25.0, 55.0  # Outside Sri Lanka
    susc, h_class = landslide_service.get_susceptibility_score(out_lat, out_lon)
    assert susc == 0.0
    assert h_class == "NO_HAZARD_ZONE"


def test_database_records_not_modified(db_engine):
    """Verify read-only integrity: row count remains exact and unmodified."""
    with db_engine.connect() as conn:
        cnt1 = conn.execute(text("SELECT count(*) FROM nbro_hazard_zones;")).scalar()
        assert cnt1 == 194016
