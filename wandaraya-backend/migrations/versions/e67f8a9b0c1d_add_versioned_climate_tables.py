"""add versioned climate pilot tables

Revision ID: e67f8a9b0c1d
Revises: d56e7f8a9b0c
"""
from alembic import op
import sqlalchemy as sa
from geoalchemy2 import Geometry

revision = "e67f8a9b0c1d"
down_revision = "d56e7f8a9b0c"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table("climate_dataset_versions", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("source_name", sa.String(120), nullable=False), sa.Column("provider_name", sa.String(120), nullable=False), sa.Column("product_name", sa.String(120), nullable=False), sa.Column("product_version", sa.String(160), nullable=False), sa.Column("source_url", sa.Text(), nullable=False), sa.Column("license_reference", sa.Text()), sa.Column("license_review_status", sa.String(40), nullable=False), sa.Column("attribution_text", sa.Text()), sa.Column("reference_start", sa.Date()), sa.Column("reference_end", sa.Date()), sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=False), sa.Column("request_manifest_hash", sa.String(64)), sa.Column("dataset_checksum", sa.String(64)), sa.Column("source_units_json", sa.JSON(), nullable=False), sa.Column("normalized_units_json", sa.JSON(), nullable=False), sa.UniqueConstraint("provider_name", "product_name", "product_version", name="uq_climate_dataset_source_version"))
    op.create_table("climate_grid_cells", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("dataset_version_id", sa.Integer(), sa.ForeignKey("climate_dataset_versions.id"), nullable=False), sa.Column("source_grid_identifier", sa.String(160), nullable=False), sa.Column("latitude", sa.Float(), nullable=False), sa.Column("longitude", sa.Float(), nullable=False), sa.Column("geometry", Geometry("POINT", srid=4326), nullable=False), sa.Column("spatial_resolution", sa.String(80), nullable=False), sa.Column("elevation_m", sa.Float()), sa.Column("metadata_json", sa.JSON(), nullable=False), sa.UniqueConstraint("dataset_version_id", "source_grid_identifier", name="uq_climate_grid_cell_version_source"))
    op.create_index("ix_climate_grid_cells_dataset_version_id", "climate_grid_cells", ["dataset_version_id"])
    op.create_table("climate_daily_observations", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("dataset_version_id", sa.Integer(), sa.ForeignKey("climate_dataset_versions.id"), nullable=False), sa.Column("grid_cell_id", sa.Integer(), sa.ForeignKey("climate_grid_cells.id"), nullable=False), sa.Column("observation_date", sa.Date(), nullable=False), sa.Column("precipitation_mm", sa.Float()), sa.Column("temperature_mean_c", sa.Float()), sa.Column("temperature_min_c", sa.Float()), sa.Column("temperature_max_c", sa.Float()), sa.Column("relative_humidity_pct", sa.Float()), sa.Column("wind_speed", sa.Float()), sa.Column("wind_speed_unit", sa.String(16)), sa.Column("solar_radiation", sa.Float()), sa.Column("solar_radiation_unit", sa.String(32)), sa.Column("quality_status", sa.String(40), nullable=False), sa.Column("source_record_hash", sa.String(64), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.UniqueConstraint("dataset_version_id", "grid_cell_id", "observation_date", name="uq_climate_daily_observation"))
    op.create_index("ix_climate_daily_observations_dataset_version_id", "climate_daily_observations", ["dataset_version_id"]); op.create_index("ix_climate_daily_observations_grid_cell_id", "climate_daily_observations", ["grid_cell_id"]); op.create_index("ix_climate_daily_observations_observation_date", "climate_daily_observations", ["observation_date"])
    op.create_table("climate_attraction_mappings", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("attraction_id", sa.Integer(), sa.ForeignKey("attractions.id"), nullable=False), sa.Column("dataset_version_id", sa.Integer(), sa.ForeignKey("climate_dataset_versions.id"), nullable=False), sa.Column("grid_cell_id", sa.Integer(), sa.ForeignKey("climate_grid_cells.id"), nullable=False), sa.Column("mapping_method", sa.String(80), nullable=False), sa.Column("distance_km", sa.Float()), sa.Column("geographic_confidence", sa.String(40), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.UniqueConstraint("attraction_id", "dataset_version_id", name="uq_climate_attraction_mapping"))
    op.create_index("ix_climate_attraction_mappings_attraction_id", "climate_attraction_mappings", ["attraction_id"]); op.create_index("ix_climate_attraction_mappings_dataset_version_id", "climate_attraction_mappings", ["dataset_version_id"])
    op.create_table("climate_ingestion_runs", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("dataset_version_id", sa.Integer(), sa.ForeignKey("climate_dataset_versions.id")), sa.Column("started_at", sa.DateTime(timezone=True), nullable=False), sa.Column("completed_at", sa.DateTime(timezone=True)), sa.Column("status", sa.String(40), nullable=False), sa.Column("request_count", sa.Integer(), nullable=False, server_default="0"), sa.Column("records_received", sa.Integer(), nullable=False, server_default="0"), sa.Column("records_accepted", sa.Integer(), nullable=False, server_default="0"), sa.Column("records_rejected", sa.Integer(), nullable=False, server_default="0"), sa.Column("error_summary", sa.Text()), sa.Column("manifest_path", sa.Text()))
    op.create_index("ix_climate_ingestion_runs_dataset_version_id", "climate_ingestion_runs", ["dataset_version_id"])


def downgrade() -> None:
    op.drop_table("climate_ingestion_runs"); op.drop_table("climate_attraction_mappings"); op.drop_table("climate_daily_observations"); op.drop_table("climate_grid_cells"); op.drop_table("climate_dataset_versions")
