"""Add resumable historical climate import checkpoints.

Revision ID: f78a9b0c1d2e
Revises: e67f8a9b0c1d
"""
from alembic import op
import sqlalchemy as sa

revision = "f78a9b0c1d2e"
down_revision = "e67f8a9b0c1d"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "climate_historical_import_checkpoints",
        sa.Column("dataset_version_id", sa.Integer(), sa.ForeignKey("climate_dataset_versions.id"), primary_key=True),
        sa.Column("grid_cell_id", sa.Integer(), sa.ForeignKey("climate_grid_cells.id"), primary_key=True),
        sa.Column("sample_id", sa.String(160), nullable=False),
        sa.Column("source_sha256", sa.String(64), nullable=False),
        sa.Column("record_count", sa.Integer(), nullable=False),
        sa.Column("committed_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("dataset_version_id", "sample_id", name="uq_climate_checkpoint_sample"),
        sa.CheckConstraint("record_count > 0", name="ck_climate_checkpoint_record_count"),
    )


def downgrade():
    op.drop_table("climate_historical_import_checkpoints")
