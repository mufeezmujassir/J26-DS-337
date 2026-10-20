"""Read-only Historical Climate Service for WANDARAYA.

Provides queryable access to persisted NASA POWER historical climate datasets
(2010-2025) across Sri Lankan districts and attraction samples.
"""
from __future__ import annotations

from datetime import date
from typing import Any, Dict, List, Optional

from sqlalchemy import text
from app.database import AsyncSessionLocal

DEFAULT_DISTRICT_DATASET_VERSION = "nasa_power_daily_v2.10.0_historical_2010_2025_batch02"
HISTORICAL_BATCH01_DATASET_VERSION = "nasa_power_daily_v2.10.0_historical_2010_2025_batch01"
PILOT_DATASET_VERSION = "nasa_power_daily_v2.10.0_2024_pilot"


class HistoricalClimateService:
    """Service providing read-only queries for historical climate data."""

    @staticmethod
    async def get_district_daily(
        district_id: int,
        start_date: date,
        end_date: date,
        dataset_version: str = DEFAULT_DISTRICT_DATASET_VERSION,
    ) -> List[Dict[str, Any]]:
        """Retrieve daily observations for a given district and date range."""
        async with AsyncSessionLocal() as session:
            stmt = text("""
                SELECT
                    o.observation_date,
                    o.temperature_mean_c,
                    o.temperature_min_c,
                    o.temperature_max_c,
                    o.precipitation_mm,
                    o.relative_humidity_pct,
                    o.wind_speed,
                    o.solar_radiation,
                    o.quality_status,
                    d.name AS district_name,
                    d.province,
                    g.latitude,
                    g.longitude
                FROM climate_daily_observations o
                JOIN climate_district_mappings m
                    ON o.grid_cell_id = m.grid_cell_id AND o.dataset_version_id = m.dataset_version_id
                JOIN climate_dataset_versions v
                    ON m.dataset_version_id = v.id
                JOIN districts d
                    ON m.district_id = d.id
                JOIN climate_grid_cells g
                    ON m.grid_cell_id = g.id
                WHERE m.district_id = :district_id
                  AND v.product_version = :version
                  AND o.observation_date BETWEEN :start_date AND :end_date
                ORDER BY o.observation_date ASC
            """)
            result = await session.execute(
                stmt,
                {
                    "district_id": district_id,
                    "version": dataset_version,
                    "start_date": start_date,
                    "end_date": end_date,
                },
            )
            rows = result.mappings().all()
            return [dict(r) for r in rows]

    @staticmethod
    async def get_sample_daily(
        grid_cell_id: int,
        start_date: date,
        end_date: date,
    ) -> List[Dict[str, Any]]:
        """Retrieve daily observations for an individual grid cell / sample."""
        async with AsyncSessionLocal() as session:
            stmt = text("""
                SELECT
                    o.observation_date,
                    o.temperature_mean_c,
                    o.temperature_min_c,
                    o.temperature_max_c,
                    o.precipitation_mm,
                    o.relative_humidity_pct,
                    o.wind_speed,
                    o.solar_radiation,
                    o.quality_status,
                    g.source_grid_identifier,
                    g.latitude,
                    g.longitude
                FROM climate_daily_observations o
                JOIN climate_grid_cells g ON o.grid_cell_id = g.id
                WHERE o.grid_cell_id = :grid_cell_id
                  AND o.observation_date BETWEEN :start_date AND :end_date
                ORDER BY o.observation_date ASC
            """)
            result = await session.execute(
                stmt,
                {
                    "grid_cell_id": grid_cell_id,
                    "start_date": start_date,
                    "end_date": end_date,
                },
            )
            rows = result.mappings().all()
            return [dict(r) for r in rows]

    @staticmethod
    async def get_district_observations_by_month(
        district_id: int,
        month: int,
        dataset_version: str = DEFAULT_DISTRICT_DATASET_VERSION,
    ) -> List[Dict[str, Any]]:
        """Retrieve all historical observations across years for a specific calendar month."""
        if not 1 <= month <= 12:
            raise ValueError("Month must be between 1 and 12")

        async with AsyncSessionLocal() as session:
            stmt = text("""
                SELECT
                    o.observation_date,
                    o.temperature_mean_c,
                    o.temperature_min_c,
                    o.temperature_max_c,
                    o.precipitation_mm,
                    o.relative_humidity_pct,
                    o.wind_speed,
                    o.solar_radiation
                FROM climate_daily_observations o
                JOIN climate_district_mappings m
                    ON o.grid_cell_id = m.grid_cell_id AND o.dataset_version_id = m.dataset_version_id
                JOIN climate_dataset_versions v
                    ON m.dataset_version_id = v.id
                WHERE m.district_id = :district_id
                  AND v.product_version = :version
                  AND EXTRACT(MONTH FROM o.observation_date) = :month
                ORDER BY o.observation_date ASC
            """)
            result = await session.execute(
                stmt,
                {
                    "district_id": district_id,
                    "version": dataset_version,
                    "month": month,
                },
            )
            rows = result.mappings().all()
            return [dict(r) for r in rows]

    @staticmethod
    async def get_district_yearly_summary(
        district_id: int,
        start_year: int = 2010,
        end_year: int = 2025,
        dataset_version: str = DEFAULT_DISTRICT_DATASET_VERSION,
    ) -> List[Dict[str, Any]]:
        """Calculate yearly aggregates for a district."""
        async with AsyncSessionLocal() as session:
            stmt = text("""
                SELECT
                    EXTRACT(YEAR FROM o.observation_date)::int AS year,
                    COUNT(o.id) AS days_count,
                    ROUND(AVG(o.temperature_mean_c)::numeric, 2) AS avg_temperature_c,
                    ROUND(MIN(o.temperature_min_c)::numeric, 2) AS min_temperature_c,
                    ROUND(MAX(o.temperature_max_c)::numeric, 2) AS max_temperature_c,
                    ROUND(SUM(o.precipitation_mm)::numeric, 2) AS total_precipitation_mm,
                    ROUND(AVG(o.relative_humidity_pct)::numeric, 2) AS avg_relative_humidity_pct,
                    ROUND(AVG(o.wind_speed)::numeric, 2) AS avg_wind_speed_ms,
                    ROUND(AVG(o.solar_radiation)::numeric, 2) AS avg_solar_radiation
                FROM climate_daily_observations o
                JOIN climate_district_mappings m
                    ON o.grid_cell_id = m.grid_cell_id AND o.dataset_version_id = m.dataset_version_id
                JOIN climate_dataset_versions v
                    ON m.dataset_version_id = v.id
                WHERE m.district_id = :district_id
                  AND v.product_version = :version
                  AND EXTRACT(YEAR FROM o.observation_date) BETWEEN :start_year AND :end_year
                GROUP BY EXTRACT(YEAR FROM o.observation_date)
                ORDER BY year ASC
            """)
            result = await session.execute(
                stmt,
                {
                    "district_id": district_id,
                    "version": dataset_version,
                    "start_year": start_year,
                    "end_year": end_year,
                },
            )
            rows = result.mappings().all()
            return [dict(r) for r in rows]

    @staticmethod
    async def get_quality_statistics(
        dataset_version: str = DEFAULT_DISTRICT_DATASET_VERSION,
    ) -> Dict[str, Any]:
        """Retrieve observation quality metrics for a dataset version."""
        async with AsyncSessionLocal() as session:
            stmt = text("""
                SELECT
                    COUNT(*) AS total_records,
                    COUNT(CASE WHEN o.quality_status = 'VALIDATED' THEN 1 END) AS validated_count,
                    COUNT(CASE WHEN o.precipitation_mm IS NULL THEN 1 END) AS null_precip,
                    COUNT(CASE WHEN o.temperature_mean_c IS NULL THEN 1 END) AS null_tmean,
                    COUNT(CASE WHEN o.relative_humidity_pct IS NULL THEN 1 END) AS null_rh,
                    COUNT(CASE WHEN o.solar_radiation IS NULL THEN 1 END) AS null_solar,
                    COUNT(CASE WHEN o.wind_speed IS NULL THEN 1 END) AS null_wind
                FROM climate_daily_observations o
                JOIN climate_dataset_versions v ON o.dataset_version_id = v.id
                WHERE v.product_version = :version
            """)
            result = await session.execute(stmt, {"version": dataset_version})
            row = result.mappings().one()
            return dict(row)

    @staticmethod
    async def get_dataset_provenance(
        dataset_version: str = DEFAULT_DISTRICT_DATASET_VERSION,
    ) -> Dict[str, Any]:
        """Retrieve dataset version metadata, provider attribution, and units."""
        async with AsyncSessionLocal() as session:
            stmt = text("""
                SELECT
                    v.id,
                    v.source_name,
                    v.provider_name,
                    v.product_name,
                    v.product_version,
                    v.source_url,
                    v.attribution_text,
                    v.reference_start,
                    v.reference_end,
                    v.retrieved_at,
                    v.request_manifest_hash,
                    v.dataset_checksum,
                    v.source_units_json,
                    v.normalized_units_json,
                    COUNT(DISTINCT g.id) AS grid_cell_count,
                    COUNT(o.id) AS observation_count
                FROM climate_dataset_versions v
                LEFT JOIN climate_grid_cells g ON g.dataset_version_id = v.id
                LEFT JOIN climate_daily_observations o ON o.grid_cell_id = g.id AND o.dataset_version_id = v.id
                WHERE v.product_version = :version
                GROUP BY v.id
            """)
            result = await session.execute(stmt, {"version": dataset_version})
            row = result.mappings().first()
            if not row:
                raise ValueError(f"Dataset version not found: {dataset_version}")
            return dict(row)

    @staticmethod
    async def get_source_geographic_uncertainty(
        district_id: int,
        dataset_version: str = DEFAULT_DISTRICT_DATASET_VERSION,
    ) -> Dict[str, Any]:
        """Retrieve geographic uncertainty and representative coordinate metadata."""
        async with AsyncSessionLocal() as session:
            stmt = text("""
                SELECT
                    m.district_id,
                    d.name AS district_name,
                    d.province,
                    m.mapping_method,
                    m.distance_km,
                    m.geographic_confidence,
                    g.source_grid_identifier,
                    g.latitude,
                    g.longitude,
                    g.spatial_resolution,
                    g.metadata_json
                FROM climate_district_mappings m
                JOIN districts d ON m.district_id = d.id
                JOIN climate_grid_cells g ON m.grid_cell_id = g.id
                JOIN climate_dataset_versions v ON m.dataset_version_id = v.id
                WHERE m.district_id = :district_id
                  AND v.product_version = :version
            """)
            result = await session.execute(
                stmt,
                {"district_id": district_id, "version": dataset_version},
            )
            row = result.mappings().first()
            if not row:
                raise ValueError(f"No mapping found for district {district_id} in {dataset_version}")
            return dict(row)

    @staticmethod
    async def get_available_date_coverage(
        dataset_version: str = DEFAULT_DISTRICT_DATASET_VERSION,
    ) -> Dict[str, Any]:
        """Retrieve the date range and total days available in the dataset."""
        async with AsyncSessionLocal() as session:
            stmt = text("""
                SELECT
                    MIN(o.observation_date) AS earliest_date,
                    MAX(o.observation_date) AS latest_date,
                    COUNT(DISTINCT o.observation_date) AS distinct_dates_count
                FROM climate_daily_observations o
                JOIN climate_dataset_versions v ON o.dataset_version_id = v.id
                WHERE v.product_version = :version
            """)
            result = await session.execute(stmt, {"version": dataset_version})
            row = result.mappings().one()
            return {
                "earliest_date": str(row["earliest_date"]),
                "latest_date": str(row["latest_date"]),
                "distinct_dates_count": row["distinct_dates_count"],
            }

    @staticmethod
    async def list_dataset_versions() -> List[Dict[str, Any]]:
        """List all registered climate dataset versions with summaries."""
        async with AsyncSessionLocal() as session:
            stmt = text("""
                SELECT
                    v.id,
                    v.product_version,
                    v.provider_name,
                    v.reference_start,
                    v.reference_end,
                    COUNT(DISTINCT g.id) AS grid_cells,
                    COUNT(o.id) AS observations
                FROM climate_dataset_versions v
                LEFT JOIN climate_grid_cells g ON g.dataset_version_id = v.id
                LEFT JOIN climate_daily_observations o ON o.grid_cell_id = g.id AND o.dataset_version_id = v.id
                GROUP BY v.id
                ORDER BY v.id ASC
            """)
            result = await session.execute(stmt)
            rows = result.mappings().all()
            return [dict(r) for r in rows]
