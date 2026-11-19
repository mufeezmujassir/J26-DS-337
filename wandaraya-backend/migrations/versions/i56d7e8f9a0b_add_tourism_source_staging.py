"""add source-attributed tourism staging table

Revision ID: i56d7e8f9a0b
Revises: h45c6d7e8f9a
"""
from alembic import op
import sqlalchemy as sa

revision = "i56d7e8f9a0b"
down_revision = "h45c6d7e8f9a"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    if sa.inspect(bind).has_table("tourism_source_staging"):
        return
    op.create_table(
        "tourism_source_staging",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source_provider", sa.String(80), nullable=False),
        sa.Column("external_source_id", sa.String(255), nullable=False),
        sa.Column("canonical_source_url", sa.Text(), nullable=False),
        sa.Column("source_record_sha256", sa.String(64), nullable=False),
        sa.Column("raw_record", sa.JSON(), nullable=False),
        sa.Column("mapped_theme", sa.String(80)),
        sa.Column("mapping_method", sa.String(80)),
        sa.Column("validation_status", sa.String(50), nullable=False, server_default="pending"),
        sa.Column("matched_attraction_id", sa.Integer(), sa.ForeignKey("attractions.id", ondelete="SET NULL")),
        sa.Column("google_place_id", sa.String(255)),
        sa.Column("google_evidence", sa.JSON()),
        sa.Column("import_batch_id", sa.String(120)),
        sa.Column("error_message", sa.Text()),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("source_provider", "external_source_id", name="uq_tourism_source_staging_identity"),
    )
    op.create_index("ix_tourism_source_staging_source_provider", "tourism_source_staging", ["source_provider"])
    op.create_index("ix_tourism_source_staging_matched_attraction_id", "tourism_source_staging", ["matched_attraction_id"])
    op.create_index("ix_tourism_source_staging_import_batch_id", "tourism_source_staging", ["import_batch_id"])


def downgrade():
    bind = op.get_bind()
    if not sa.inspect(bind).has_table("tourism_source_staging"):
        return
    op.drop_index("ix_tourism_source_staging_import_batch_id", table_name="tourism_source_staging")
    op.drop_index("ix_tourism_source_staging_matched_attraction_id", table_name="tourism_source_staging")
    op.drop_index("ix_tourism_source_staging_source_provider", table_name="tourism_source_staging")
    op.drop_table("tourism_source_staging")
