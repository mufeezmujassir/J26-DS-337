"""add climate district mappings table

Revision ID: f78a9b0c1d2e
Revises: e67f8a9b0c1d
Create Date: 2026-10-20 10:15:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = "f78a9b0c1d2e"
down_revision = "e67f8a9b0c1d"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "climate_district_mappings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("district_id", sa.Integer(), sa.ForeignKey("districts.id"), nullable=False),
        sa.Column("dataset_version_id", sa.Integer(), sa.ForeignKey("climate_dataset_versions.id"), nullable=False),
        sa.Column("grid_cell_id", sa.Integer(), sa.ForeignKey("climate_grid_cells.id"), nullable=False),
        sa.Column("mapping_method", sa.String(80), nullable=False),
        sa.Column("distance_km", sa.Float()),
        sa.Column("geographic_confidence", sa.String(40), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("district_id", "dataset_version_id", name="uq_climate_district_mapping"),
    )
    op.create_index("ix_climate_district_mappings_district_id", "climate_district_mappings", ["district_id"])
    op.create_index("ix_climate_district_mappings_dataset_version_id", "climate_district_mappings", ["dataset_version_id"])
    op.create_index("ix_climate_district_mappings_grid_cell_id", "climate_district_mappings", ["grid_cell_id"])


def downgrade() -> None:
    op.drop_index("ix_climate_district_mappings_grid_cell_id", "climate_district_mappings")
    op.drop_index("ix_climate_district_mappings_dataset_version_id", "climate_district_mappings")
    op.drop_index("ix_climate_district_mappings_district_id", "climate_district_mappings")
    op.drop_table("climate_district_mappings")
