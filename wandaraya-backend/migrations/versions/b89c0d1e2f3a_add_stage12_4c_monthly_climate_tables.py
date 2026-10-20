"""add stage12_4c monthly climate tables

Revision ID: b89c0d1e2f3a
Revises: f78a9b0c1d2e
Create Date: 2026-10-20 11:20:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = "b89c0d1e2f3a"
down_revision = "f78a9b0c1d2e"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. climate_district_monthly_aggregates
    op.create_table(
        "climate_district_monthly_aggregates",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("district_id", sa.Integer(), sa.ForeignKey("districts.id"), nullable=False),
        sa.Column("dataset_version_id", sa.Integer(), sa.ForeignKey("climate_dataset_versions.id"), nullable=False),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("month", sa.Integer(), nullable=False),
        sa.Column("temp_mean_c", sa.Float(), nullable=True),
        sa.Column("temp_max_mean_c", sa.Float(), nullable=True),
        sa.Column("temp_min_mean_c", sa.Float(), nullable=True),
        sa.Column("temp_min_observed_c", sa.Float(), nullable=True),
        sa.Column("temp_max_observed_c", sa.Float(), nullable=True),
        sa.Column("diurnal_range_mean_c", sa.Float(), nullable=True),
        sa.Column("precipitation_total_mm", sa.Float(), nullable=True),
        sa.Column("precipitation_daily_mean_mm", sa.Float(), nullable=True),
        sa.Column("precipitation_max_daily_mm", sa.Float(), nullable=True),
        sa.Column("rainy_days_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("rainy_days_frequency", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("heavy_rain_days_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("very_heavy_rain_days_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("relative_humidity_mean_pct", sa.Float(), nullable=True),
        sa.Column("relative_humidity_min_pct", sa.Float(), nullable=True),
        sa.Column("relative_humidity_max_pct", sa.Float(), nullable=True),
        sa.Column("wind_speed_mean_ms", sa.Float(), nullable=True),
        sa.Column("wind_speed_max_ms", sa.Float(), nullable=True),
        sa.Column("solar_radiation_mean_mj", sa.Float(), nullable=True),
        sa.Column("solar_radiation_total_mj", sa.Float(), nullable=True),
        sa.Column("calendar_days", sa.Integer(), nullable=False),
        sa.Column("observed_days", sa.Integer(), nullable=False),
        sa.Column("completeness_pct", sa.Float(), nullable=False),
        sa.Column("quality_status", sa.String(40), nullable=False, server_default="VALIDATED"),
        sa.Column("processing_version", sa.String(40), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("district_id", "dataset_version_id", "year", "month", name="uq_district_monthly_aggregate"),
    )
    op.create_index("ix_climate_district_monthly_aggregates_district_id", "climate_district_monthly_aggregates", ["district_id"])
    op.create_index("ix_climate_district_monthly_aggregates_dataset_version_id", "climate_district_monthly_aggregates", ["dataset_version_id"])
    op.create_index("ix_climate_district_monthly_aggregates_year", "climate_district_monthly_aggregates", ["year"])
    op.create_index("ix_climate_district_monthly_aggregates_month", "climate_district_monthly_aggregates", ["month"])

    # 2. climate_district_monthly_climatology
    op.create_table(
        "climate_district_monthly_climatology",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("district_id", sa.Integer(), sa.ForeignKey("districts.id"), nullable=False),
        sa.Column("dataset_version_id", sa.Integer(), sa.ForeignKey("climate_dataset_versions.id"), nullable=False),
        sa.Column("month", sa.Integer(), nullable=False),
        sa.Column("reference_period", sa.String(40), nullable=False),
        sa.Column("processing_version", sa.String(40), nullable=False),
        sa.Column("rainfall_mean_mm", sa.Float(), nullable=True),
        sa.Column("rainfall_median_mm", sa.Float(), nullable=True),
        sa.Column("rainfall_std_mm", sa.Float(), nullable=True),
        sa.Column("rainfall_iqr_mm", sa.Float(), nullable=True),
        sa.Column("rainfall_p10_mm", sa.Float(), nullable=True),
        sa.Column("rainfall_p90_mm", sa.Float(), nullable=True),
        sa.Column("rainfall_min_mm", sa.Float(), nullable=True),
        sa.Column("rainfall_max_mm", sa.Float(), nullable=True),
        sa.Column("rainfall_cv", sa.Float(), nullable=True),
        sa.Column("rainy_day_frequency_mean", sa.Float(), nullable=True),
        sa.Column("heavy_rain_days_mean", sa.Float(), nullable=True),
        sa.Column("very_heavy_rain_days_mean", sa.Float(), nullable=True),
        sa.Column("temp_mean_c", sa.Float(), nullable=True),
        sa.Column("temp_max_mean_c", sa.Float(), nullable=True),
        sa.Column("temp_min_mean_c", sa.Float(), nullable=True),
        sa.Column("diurnal_range_mean_c", sa.Float(), nullable=True),
        sa.Column("relative_humidity_mean_pct", sa.Float(), nullable=True),
        sa.Column("wind_speed_mean_ms", sa.Float(), nullable=True),
        sa.Column("solar_radiation_mean_mj", sa.Float(), nullable=True),
        sa.Column("solar_radiation_total_mean_mj", sa.Float(), nullable=True),
        sa.Column("valid_years_count", sa.Integer(), nullable=False),
        sa.Column("total_observed_days", sa.Integer(), nullable=False),
        sa.Column("geographic_uncertainty", sa.String(40), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("district_id", "dataset_version_id", "month", "reference_period", "processing_version", name="uq_district_monthly_climatology"),
    )
    op.create_index("ix_climate_district_monthly_climatology_district_id", "climate_district_monthly_climatology", ["district_id"])
    op.create_index("ix_climate_district_monthly_climatology_dataset_version_id", "climate_district_monthly_climatology", ["dataset_version_id"])
    op.create_index("ix_climate_district_monthly_climatology_month", "climate_district_monthly_climatology", ["month"])

    # 3. climate_seasonality_features
    op.create_table(
        "climate_seasonality_features",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("district_id", sa.Integer(), sa.ForeignKey("districts.id"), nullable=False),
        sa.Column("dataset_version_id", sa.Integer(), sa.ForeignKey("climate_dataset_versions.id"), nullable=False),
        sa.Column("month", sa.Integer(), nullable=False),
        sa.Column("feature_version", sa.String(40), nullable=False),
        sa.Column("relative_rainfall_favorability", sa.Float(), nullable=False),
        sa.Column("temperature_comfort_index", sa.Float(), nullable=False),
        sa.Column("humidity_comfort_index", sa.Float(), nullable=False),
        sa.Column("rainfall_reliability_index", sa.Float(), nullable=False),
        sa.Column("seasonality_uncertainty_score", sa.Float(), nullable=False),
        sa.Column("baseline_a_rainfall_rank", sa.Integer(), nullable=False),
        sa.Column("baseline_b_multivar_score", sa.Float(), nullable=False),
        sa.Column("baseline_b_multivar_rank", sa.Integer(), nullable=False),
        sa.Column("baseline_c_variability_rank", sa.Integer(), nullable=False),
        sa.Column("feature_vector_json", sa.JSON(), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("district_id", "dataset_version_id", "month", "feature_version", name="uq_climate_seasonality_features"),
    )
    op.create_index("ix_climate_seasonality_features_district_id", "climate_seasonality_features", ["district_id"])
    op.create_index("ix_climate_seasonality_features_dataset_version_id", "climate_seasonality_features", ["dataset_version_id"])
    op.create_index("ix_climate_seasonality_features_month", "climate_seasonality_features", ["month"])

    # 4. climate_processing_runs
    op.create_table(
        "climate_processing_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("stage", sa.String(40), nullable=False),
        sa.Column("run_type", sa.String(80), nullable=False),
        sa.Column("dataset_version_id", sa.Integer(), sa.ForeignKey("climate_dataset_versions.id"), nullable=True),
        sa.Column("processing_version", sa.String(40), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("records_processed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("records_persisted", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("parameters_json", sa.JSON(), nullable=False),
        sa.Column("summary_json", sa.JSON(), nullable=False),
        sa.Column("error_summary", sa.Text(), nullable=True),
    )
    op.create_index("ix_climate_processing_runs_dataset_version_id", "climate_processing_runs", ["dataset_version_id"])


def downgrade() -> None:
    op.drop_table("climate_processing_runs")
    op.drop_table("climate_seasonality_features")
    op.drop_table("climate_district_monthly_climatology")
    op.drop_table("climate_district_monthly_aggregates")
