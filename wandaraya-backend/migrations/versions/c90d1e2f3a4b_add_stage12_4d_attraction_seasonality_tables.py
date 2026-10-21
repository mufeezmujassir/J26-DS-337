"""add stage12_4d attraction seasonality tables

Revision ID: c90d1e2f3a4b
Revises: b89c0d1e2f3a
Create Date: 2026-10-20 14:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = "c90d1e2f3a4b"
down_revision = "b89c0d1e2f3a"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. climate_activity_types
    op.create_table(
        "climate_activity_types",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("activity_family", sa.String(80), nullable=False),
        sa.Column("activity_type", sa.String(80), nullable=False),
        sa.Column("activity_variant", sa.String(80), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("primary_climate_factor", sa.String(80), nullable=False),
        sa.Column("requires_external_evidence", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("external_evidence_requirements", sa.JSON(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("activity_family", "activity_type", "activity_variant", name="uq_climate_activity_type"),
    )
    op.create_index("ix_climate_activity_types_family", "climate_activity_types", ["activity_family"])
    op.create_index("ix_climate_activity_types_type", "climate_activity_types", ["activity_type"])

    # 2. climate_activity_profiles
    op.create_table(
        "climate_activity_profiles",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("activity_type_id", sa.Integer(), sa.ForeignKey("climate_activity_types.id"), nullable=False),
        sa.Column("profile_version", sa.String(40), nullable=False),
        sa.Column("feature_weights_json", sa.JSON(), nullable=False),
        sa.Column("thresholds_json", sa.JSON(), nullable=False),
        sa.Column("hard_constraints_json", sa.JSON(), nullable=False),
        sa.Column("required_external_evidence_json", sa.JSON(), nullable=False),
        sa.Column("uncertainty_policy_json", sa.JSON(), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("evidence_status", sa.String(40), nullable=False),
        sa.Column("is_experimental", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("activity_type_id", "profile_version", name="uq_climate_activity_profile"),
    )
    op.create_index("ix_climate_activity_profiles_type_id", "climate_activity_profiles", ["activity_type_id"])

    # 3. climate_attraction_activity_mappings
    op.create_table(
        "climate_attraction_activity_mappings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("attraction_id", sa.Integer(), sa.ForeignKey("attractions.id"), nullable=False),
        sa.Column("activity_type_id", sa.Integer(), sa.ForeignKey("climate_activity_types.id"), nullable=False),
        sa.Column("mapping_source", sa.String(80), nullable=False),
        sa.Column("mapping_method", sa.String(80), nullable=False),
        sa.Column("evidence_reference", sa.String(160), nullable=True),
        sa.Column("confidence_level", sa.String(40), nullable=False),
        sa.Column("verification_status", sa.String(40), nullable=False),
        sa.Column("reviewer_status", sa.String(40), nullable=False, server_default="AUTOMATED_RULE_AUDITED"),
        sa.Column("classification_version", sa.String(40), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("attraction_id", "activity_type_id", "classification_version", name="uq_climate_attraction_activity_mapping"),
    )
    op.create_index("ix_climate_attr_act_map_attraction_id", "climate_attraction_activity_mappings", ["attraction_id"])
    op.create_index("ix_climate_attr_act_map_activity_id", "climate_attraction_activity_mappings", ["activity_type_id"])

    # 4. climate_attraction_monthly_climatology
    op.create_table(
        "climate_attraction_monthly_climatology",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("attraction_id", sa.Integer(), sa.ForeignKey("attractions.id"), nullable=False),
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
        sa.Column("temp_mean_c", sa.Float(), nullable=True),
        sa.Column("temp_max_mean_c", sa.Float(), nullable=True),
        sa.Column("temp_min_mean_c", sa.Float(), nullable=True),
        sa.Column("diurnal_range_mean_c", sa.Float(), nullable=True),
        sa.Column("relative_humidity_mean_pct", sa.Float(), nullable=True),
        sa.Column("wind_speed_mean_ms", sa.Float(), nullable=True),
        sa.Column("solar_radiation_mean_mj", sa.Float(), nullable=True),
        sa.Column("valid_years_count", sa.Integer(), nullable=False),
        sa.Column("total_observed_days", sa.Integer(), nullable=False),
        sa.Column("geographic_source_type", sa.String(60), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("attraction_id", "dataset_version_id", "month", "reference_period", "processing_version", name="uq_climate_attraction_monthly_climatology"),
    )
    op.create_index("ix_climate_attr_clim_attraction_id", "climate_attraction_monthly_climatology", ["attraction_id"])
    op.create_index("ix_climate_attr_clim_month", "climate_attraction_monthly_climatology", ["month"])

    # 5. climate_attraction_activity_seasonality
    op.create_table(
        "climate_attraction_activity_seasonality",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("attraction_id", sa.Integer(), sa.ForeignKey("attractions.id"), nullable=False),
        sa.Column("activity_type_id", sa.Integer(), sa.ForeignKey("climate_activity_types.id"), nullable=False),
        sa.Column("district_id", sa.Integer(), sa.ForeignKey("districts.id"), nullable=False),
        sa.Column("month", sa.Integer(), nullable=False),
        sa.Column("dataset_version_id", sa.Integer(), sa.ForeignKey("climate_dataset_versions.id"), nullable=False),
        sa.Column("climate_source_type", sa.String(60), nullable=False),
        sa.Column("activity_profile_version", sa.String(40), nullable=False),
        sa.Column("processing_version", sa.String(40), nullable=False),
        sa.Column("climate_favorability_score", sa.Float(), nullable=False),
        sa.Column("climate_favorability_rank", sa.Integer(), nullable=False),
        sa.Column("evidence_status", sa.String(40), nullable=False),
        sa.Column("confidence_level", sa.String(40), nullable=False),
        sa.Column("uncertainty_score", sa.Float(), nullable=False),
        sa.Column("feature_contributions_json", sa.JSON(), nullable=False),
        sa.Column("explanation_json", sa.JSON(), nullable=False),
        sa.Column("limitations_json", sa.JSON(), nullable=False),
        sa.Column("calculated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("attraction_id", "activity_type_id", "month", "processing_version", "activity_profile_version", name="uq_attr_act_seasonality"),
    )
    op.create_index("ix_climate_attr_act_season_attraction_id", "climate_attraction_activity_seasonality", ["attraction_id"])
    op.create_index("ix_climate_attr_act_season_activity_id", "climate_attraction_activity_seasonality", ["activity_type_id"])
    op.create_index("ix_climate_attr_act_season_district_id", "climate_attraction_activity_seasonality", ["district_id"])
    op.create_index("ix_climate_attr_act_season_month", "climate_attraction_activity_seasonality", ["month"])

    # 6. climate_activity_processing_runs
    op.create_table(
        "climate_activity_processing_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("stage", sa.String(40), nullable=False),
        sa.Column("run_type", sa.String(80), nullable=False),
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


def downgrade() -> None:
    op.drop_table("climate_activity_processing_runs")
    op.drop_table("climate_attraction_activity_seasonality")
    op.drop_table("climate_attraction_monthly_climatology")
    op.drop_table("climate_attraction_activity_mappings")
    op.drop_table("climate_activity_profiles")
    op.drop_table("climate_activity_types")
