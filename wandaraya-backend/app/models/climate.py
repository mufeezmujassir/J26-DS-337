"""Dedicated, versioned historical-climate entities (Stage 12.4B).

They are intentionally separate from operational weather forecasts/readings.
The accompanying Alembic migration is not applied by this stage.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from sqlalchemy import Date, DateTime, Float, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from geoalchemy2 import Geometry
from app.database import Base


class ClimateDatasetVersion(Base):
    __tablename__ = "climate_dataset_versions"
    __table_args__ = (UniqueConstraint("provider_name", "product_name", "product_version", name="uq_climate_dataset_source_version"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    source_name: Mapped[str] = mapped_column(String(120), nullable=False)
    provider_name: Mapped[str] = mapped_column(String(120), nullable=False)
    product_name: Mapped[str] = mapped_column(String(120), nullable=False)
    product_version: Mapped[str] = mapped_column(String(160), nullable=False)
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    license_reference: Mapped[str | None] = mapped_column(Text)
    license_review_status: Mapped[str] = mapped_column(String(40), nullable=False)
    attribution_text: Mapped[str | None] = mapped_column(Text)
    reference_start: Mapped[date | None] = mapped_column(Date)
    reference_end: Mapped[date | None] = mapped_column(Date)
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    request_manifest_hash: Mapped[str | None] = mapped_column(String(64))
    dataset_checksum: Mapped[str | None] = mapped_column(String(64))
    source_units_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    normalized_units_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)


class ClimateGridCell(Base):
    __tablename__ = "climate_grid_cells"
    __table_args__ = (UniqueConstraint("dataset_version_id", "source_grid_identifier", name="uq_climate_grid_cell_version_source"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    dataset_version_id: Mapped[int] = mapped_column(ForeignKey("climate_dataset_versions.id"), nullable=False, index=True)
    source_grid_identifier: Mapped[str] = mapped_column(String(160), nullable=False)
    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)
    geometry: Mapped[object] = mapped_column(Geometry("POINT", srid=4326), nullable=False)
    spatial_resolution: Mapped[str] = mapped_column(String(80), nullable=False)
    elevation_m: Mapped[float | None] = mapped_column(Float)
    metadata_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)


class ClimateDailyObservation(Base):
    __tablename__ = "climate_daily_observations"
    __table_args__ = (UniqueConstraint("dataset_version_id", "grid_cell_id", "observation_date", name="uq_climate_daily_observation"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    dataset_version_id: Mapped[int] = mapped_column(ForeignKey("climate_dataset_versions.id"), nullable=False, index=True)
    grid_cell_id: Mapped[int] = mapped_column(ForeignKey("climate_grid_cells.id"), nullable=False, index=True)
    observation_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    precipitation_mm: Mapped[float | None] = mapped_column(Float)
    temperature_mean_c: Mapped[float | None] = mapped_column(Float)
    temperature_min_c: Mapped[float | None] = mapped_column(Float)
    temperature_max_c: Mapped[float | None] = mapped_column(Float)
    relative_humidity_pct: Mapped[float | None] = mapped_column(Float)
    wind_speed: Mapped[float | None] = mapped_column(Float)
    wind_speed_unit: Mapped[str | None] = mapped_column(String(16))
    solar_radiation: Mapped[float | None] = mapped_column(Float)
    solar_radiation_unit: Mapped[str | None] = mapped_column(String(32))
    quality_status: Mapped[str] = mapped_column(String(40), nullable=False)
    source_record_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class ClimateAttractionMapping(Base):
    __tablename__ = "climate_attraction_mappings"
    __table_args__ = (UniqueConstraint("attraction_id", "dataset_version_id", name="uq_climate_attraction_mapping"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    attraction_id: Mapped[int] = mapped_column(ForeignKey("attractions.id"), nullable=False, index=True)
    dataset_version_id: Mapped[int] = mapped_column(ForeignKey("climate_dataset_versions.id"), nullable=False, index=True)
    grid_cell_id: Mapped[int] = mapped_column(ForeignKey("climate_grid_cells.id"), nullable=False)
    mapping_method: Mapped[str] = mapped_column(String(80), nullable=False)
    distance_km: Mapped[float | None] = mapped_column(Float)
    geographic_confidence: Mapped[str] = mapped_column(String(40), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class ClimateIngestionRun(Base):
    __tablename__ = "climate_ingestion_runs"
    id: Mapped[int] = mapped_column(primary_key=True)
    dataset_version_id: Mapped[int | None] = mapped_column(ForeignKey("climate_dataset_versions.id"), index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(40), nullable=False)
    request_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    records_received: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    records_accepted: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    records_rejected: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_summary: Mapped[str | None] = mapped_column(Text)
    manifest_path: Mapped[str | None] = mapped_column(Text)
