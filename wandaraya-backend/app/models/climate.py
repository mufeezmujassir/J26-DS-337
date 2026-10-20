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


class ClimateDistrictMapping(Base):
    __tablename__ = "climate_district_mappings"
    __table_args__ = (UniqueConstraint("district_id", "dataset_version_id", name="uq_climate_district_mapping"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    district_id: Mapped[int] = mapped_column(ForeignKey("districts.id"), nullable=False, index=True)
    dataset_version_id: Mapped[int] = mapped_column(ForeignKey("climate_dataset_versions.id"), nullable=False, index=True)
    grid_cell_id: Mapped[int] = mapped_column(ForeignKey("climate_grid_cells.id"), nullable=False, index=True)
    mapping_method: Mapped[str] = mapped_column(String(80), nullable=False)
    distance_km: Mapped[float | None] = mapped_column(Float)
    geographic_confidence: Mapped[str] = mapped_column(String(40), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class ClimateDistrictMonthlyAggregate(Base):
    __tablename__ = "climate_district_monthly_aggregates"
    __table_args__ = (
        UniqueConstraint("district_id", "dataset_version_id", "year", "month", name="uq_district_monthly_aggregate"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    district_id: Mapped[int] = mapped_column(ForeignKey("districts.id"), nullable=False, index=True)
    dataset_version_id: Mapped[int] = mapped_column(ForeignKey("climate_dataset_versions.id"), nullable=False, index=True)
    year: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    month: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    temp_mean_c: Mapped[float | None] = mapped_column(Float)
    temp_max_mean_c: Mapped[float | None] = mapped_column(Float)
    temp_min_mean_c: Mapped[float | None] = mapped_column(Float)
    temp_min_observed_c: Mapped[float | None] = mapped_column(Float)
    temp_max_observed_c: Mapped[float | None] = mapped_column(Float)
    diurnal_range_mean_c: Mapped[float | None] = mapped_column(Float)
    precipitation_total_mm: Mapped[float | None] = mapped_column(Float)
    precipitation_daily_mean_mm: Mapped[float | None] = mapped_column(Float)
    precipitation_max_daily_mm: Mapped[float | None] = mapped_column(Float)
    rainy_days_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rainy_days_frequency: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    heavy_rain_days_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    very_heavy_rain_days_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    relative_humidity_mean_pct: Mapped[float | None] = mapped_column(Float)
    relative_humidity_min_pct: Mapped[float | None] = mapped_column(Float)
    relative_humidity_max_pct: Mapped[float | None] = mapped_column(Float)
    wind_speed_mean_ms: Mapped[float | None] = mapped_column(Float)
    wind_speed_max_ms: Mapped[float | None] = mapped_column(Float)
    solar_radiation_mean_mj: Mapped[float | None] = mapped_column(Float)
    solar_radiation_total_mj: Mapped[float | None] = mapped_column(Float)
    calendar_days: Mapped[int] = mapped_column(Integer, nullable=False)
    observed_days: Mapped[int] = mapped_column(Integer, nullable=False)
    completeness_pct: Mapped[float] = mapped_column(Float, nullable=False)
    quality_status: Mapped[str] = mapped_column(String(40), nullable=False, default="VALIDATED")
    processing_version: Mapped[str] = mapped_column(String(40), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class ClimateDistrictMonthlyClimatology(Base):
    __tablename__ = "climate_district_monthly_climatology"
    __table_args__ = (
        UniqueConstraint("district_id", "dataset_version_id", "month", "reference_period", "processing_version", name="uq_district_monthly_climatology"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    district_id: Mapped[int] = mapped_column(ForeignKey("districts.id"), nullable=False, index=True)
    dataset_version_id: Mapped[int] = mapped_column(ForeignKey("climate_dataset_versions.id"), nullable=False, index=True)
    month: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    reference_period: Mapped[str] = mapped_column(String(40), nullable=False)
    processing_version: Mapped[str] = mapped_column(String(40), nullable=False)
    rainfall_mean_mm: Mapped[float | None] = mapped_column(Float)
    rainfall_median_mm: Mapped[float | None] = mapped_column(Float)
    rainfall_std_mm: Mapped[float | None] = mapped_column(Float)
    rainfall_iqr_mm: Mapped[float | None] = mapped_column(Float)
    rainfall_p10_mm: Mapped[float | None] = mapped_column(Float)
    rainfall_p90_mm: Mapped[float | None] = mapped_column(Float)
    rainfall_min_mm: Mapped[float | None] = mapped_column(Float)
    rainfall_max_mm: Mapped[float | None] = mapped_column(Float)
    rainfall_cv: Mapped[float | None] = mapped_column(Float)
    rainy_day_frequency_mean: Mapped[float | None] = mapped_column(Float)
    heavy_rain_days_mean: Mapped[float | None] = mapped_column(Float)
    very_heavy_rain_days_mean: Mapped[float | None] = mapped_column(Float)
    temp_mean_c: Mapped[float | None] = mapped_column(Float)
    temp_max_mean_c: Mapped[float | None] = mapped_column(Float)
    temp_min_mean_c: Mapped[float | None] = mapped_column(Float)
    diurnal_range_mean_c: Mapped[float | None] = mapped_column(Float)
    relative_humidity_mean_pct: Mapped[float | None] = mapped_column(Float)
    wind_speed_mean_ms: Mapped[float | None] = mapped_column(Float)
    solar_radiation_mean_mj: Mapped[float | None] = mapped_column(Float)
    solar_radiation_total_mean_mj: Mapped[float | None] = mapped_column(Float)
    valid_years_count: Mapped[int] = mapped_column(Integer, nullable=False)
    total_observed_days: Mapped[int] = mapped_column(Integer, nullable=False)
    geographic_uncertainty: Mapped[str] = mapped_column(String(40), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class ClimateSeasonalityFeature(Base):
    __tablename__ = "climate_seasonality_features"
    __table_args__ = (
        UniqueConstraint("district_id", "dataset_version_id", "month", "feature_version", name="uq_climate_seasonality_features"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    district_id: Mapped[int] = mapped_column(ForeignKey("districts.id"), nullable=False, index=True)
    dataset_version_id: Mapped[int] = mapped_column(ForeignKey("climate_dataset_versions.id"), nullable=False, index=True)
    month: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    feature_version: Mapped[str] = mapped_column(String(40), nullable=False)
    relative_rainfall_favorability: Mapped[float] = mapped_column(Float, nullable=False)
    temperature_comfort_index: Mapped[float] = mapped_column(Float, nullable=False)
    humidity_comfort_index: Mapped[float] = mapped_column(Float, nullable=False)
    rainfall_reliability_index: Mapped[float] = mapped_column(Float, nullable=False)
    seasonality_uncertainty_score: Mapped[float] = mapped_column(Float, nullable=False)
    baseline_a_rainfall_rank: Mapped[int] = mapped_column(Integer, nullable=False)
    baseline_b_multivar_score: Mapped[float] = mapped_column(Float, nullable=False)
    baseline_b_multivar_rank: Mapped[int] = mapped_column(Integer, nullable=False)
    baseline_c_variability_rank: Mapped[int] = mapped_column(Integer, nullable=False)
    feature_vector_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    metadata_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class ClimateProcessingRun(Base):
    __tablename__ = "climate_processing_runs"
    id: Mapped[int] = mapped_column(primary_key=True)
    stage: Mapped[str] = mapped_column(String(40), nullable=False)
    run_type: Mapped[str] = mapped_column(String(80), nullable=False)
    dataset_version_id: Mapped[int | None] = mapped_column(ForeignKey("climate_dataset_versions.id"), nullable=True, index=True)
    processing_version: Mapped[str] = mapped_column(String(40), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(40), nullable=False)
    records_processed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    records_persisted: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    parameters_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    summary_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    error_summary: Mapped[str | None] = mapped_column(Text)


class ClimateActivityType(Base):
    __tablename__ = "climate_activity_types"
    __table_args__ = (
        UniqueConstraint("activity_family", "activity_type", "activity_variant", name="uq_climate_activity_type"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    activity_family: Mapped[str] = mapped_column(String(80), nullable=False)
    activity_type: Mapped[str] = mapped_column(String(80), nullable=False)
    activity_variant: Mapped[str] = mapped_column(String(80), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    primary_climate_factor: Mapped[str] = mapped_column(String(80), nullable=False)
    requires_external_evidence: Mapped[bool] = mapped_column(nullable=False, default=False)
    external_evidence_requirements: Mapped[dict] = mapped_column(JSON, nullable=False, default=list)
    is_active: Mapped[bool] = mapped_column(nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class ClimateActivityProfile(Base):
    __tablename__ = "climate_activity_profiles"
    __table_args__ = (
        UniqueConstraint("activity_type_id", "profile_version", name="uq_climate_activity_profile"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    activity_type_id: Mapped[int] = mapped_column(ForeignKey("climate_activity_types.id"), nullable=False, index=True)
    profile_version: Mapped[str] = mapped_column(String(40), nullable=False)
    feature_weights_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    thresholds_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    hard_constraints_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    required_external_evidence_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=list)
    uncertainty_policy_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_status: Mapped[str] = mapped_column(String(40), nullable=False)
    is_experimental: Mapped[bool] = mapped_column(nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class ClimateAttractionActivityMapping(Base):
    __tablename__ = "climate_attraction_activity_mappings"
    __table_args__ = (
        UniqueConstraint("attraction_id", "activity_type_id", "classification_version", name="uq_climate_attraction_activity_mapping"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    attraction_id: Mapped[int] = mapped_column(ForeignKey("attractions.id"), nullable=False, index=True)
    activity_type_id: Mapped[int] = mapped_column(ForeignKey("climate_activity_types.id"), nullable=False, index=True)
    mapping_source: Mapped[str] = mapped_column(String(80), nullable=False)
    mapping_method: Mapped[str] = mapped_column(String(80), nullable=False)
    evidence_reference: Mapped[str | None] = mapped_column(String(160))
    confidence_level: Mapped[str] = mapped_column(String(40), nullable=False)
    verification_status: Mapped[str] = mapped_column(String(40), nullable=False)
    reviewer_status: Mapped[str] = mapped_column(String(40), nullable=False, default="AUTOMATED_RULE_AUDITED")
    classification_version: Mapped[str] = mapped_column(String(40), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class ClimateAttractionMonthlyClimatology(Base):
    __tablename__ = "climate_attraction_monthly_climatology"
    __table_args__ = (
        UniqueConstraint("attraction_id", "dataset_version_id", "month", "reference_period", "processing_version", name="uq_climate_attraction_monthly_climatology"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    attraction_id: Mapped[int] = mapped_column(ForeignKey("attractions.id"), nullable=False, index=True)
    dataset_version_id: Mapped[int] = mapped_column(ForeignKey("climate_dataset_versions.id"), nullable=False, index=True)
    month: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    reference_period: Mapped[str] = mapped_column(String(40), nullable=False)
    processing_version: Mapped[str] = mapped_column(String(40), nullable=False)
    rainfall_mean_mm: Mapped[float | None] = mapped_column(Float)
    rainfall_median_mm: Mapped[float | None] = mapped_column(Float)
    rainfall_std_mm: Mapped[float | None] = mapped_column(Float)
    rainfall_iqr_mm: Mapped[float | None] = mapped_column(Float)
    rainfall_p10_mm: Mapped[float | None] = mapped_column(Float)
    rainfall_p90_mm: Mapped[float | None] = mapped_column(Float)
    rainfall_min_mm: Mapped[float | None] = mapped_column(Float)
    rainfall_max_mm: Mapped[float | None] = mapped_column(Float)
    rainfall_cv: Mapped[float | None] = mapped_column(Float)
    temp_mean_c: Mapped[float | None] = mapped_column(Float)
    temp_max_mean_c: Mapped[float | None] = mapped_column(Float)
    temp_min_mean_c: Mapped[float | None] = mapped_column(Float)
    diurnal_range_mean_c: Mapped[float | None] = mapped_column(Float)
    relative_humidity_mean_pct: Mapped[float | None] = mapped_column(Float)
    wind_speed_mean_ms: Mapped[float | None] = mapped_column(Float)
    solar_radiation_mean_mj: Mapped[float | None] = mapped_column(Float)
    valid_years_count: Mapped[int] = mapped_column(Integer, nullable=False)
    total_observed_days: Mapped[int] = mapped_column(Integer, nullable=False)
    geographic_source_type: Mapped[str] = mapped_column(String(60), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class ClimateAttractionActivitySeasonality(Base):
    __tablename__ = "climate_attraction_activity_seasonality"
    __table_args__ = (
        UniqueConstraint("attraction_id", "activity_type_id", "month", "processing_version", "activity_profile_version", name="uq_attr_act_seasonality"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    attraction_id: Mapped[int] = mapped_column(ForeignKey("attractions.id"), nullable=False, index=True)
    activity_type_id: Mapped[int] = mapped_column(ForeignKey("climate_activity_types.id"), nullable=False, index=True)
    district_id: Mapped[int] = mapped_column(ForeignKey("districts.id"), nullable=False, index=True)
    month: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    dataset_version_id: Mapped[int] = mapped_column(ForeignKey("climate_dataset_versions.id"), nullable=False, index=True)
    climate_source_type: Mapped[str] = mapped_column(String(60), nullable=False)
    activity_profile_version: Mapped[str] = mapped_column(String(40), nullable=False)
    processing_version: Mapped[str] = mapped_column(String(40), nullable=False)
    climate_favorability_score: Mapped[float] = mapped_column(Float, nullable=False)
    climate_favorability_rank: Mapped[int] = mapped_column(Integer, nullable=False)
    evidence_status: Mapped[str] = mapped_column(String(40), nullable=False)
    confidence_level: Mapped[str] = mapped_column(String(40), nullable=False)
    uncertainty_score: Mapped[float] = mapped_column(Float, nullable=False)
    feature_contributions_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    explanation_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    limitations_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    calculated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class ClimateActivityProcessingRun(Base):
    __tablename__ = "climate_activity_processing_runs"
    id: Mapped[int] = mapped_column(primary_key=True)
    stage: Mapped[str] = mapped_column(String(40), nullable=False)
    run_type: Mapped[str] = mapped_column(String(80), nullable=False)
    processing_version: Mapped[str] = mapped_column(String(40), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(40), nullable=False)
    records_processed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    records_persisted: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    parameters_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    summary_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    error_summary: Mapped[str | None] = mapped_column(Text)



