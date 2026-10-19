"""Extend tourism-event source fields for bounded LankaEvents ingestion.

Revision ID: b34c5d6e7f8a
Revises: a12b3c4d5e6f
"""
from alembic import op
import sqlalchemy as sa

revision = "b34c5d6e7f8a"
down_revision = "a12b3c4d5e6f"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("tourism_events", sa.Column("original_category", sa.String(length=120), nullable=True))
    op.add_column("tourism_events", sa.Column("province", sa.String(length=120), nullable=True))
    op.add_column("tourism_events", sa.Column("location_confidence", sa.String(length=30), nullable=False, server_default="unresolved"))
    op.add_column("tourism_events", sa.Column("ticket_url", sa.Text(), nullable=True))
    op.add_column("tourism_events", sa.Column("currency", sa.String(length=8), nullable=True))
    op.add_column("tourism_events", sa.Column("is_free", sa.Boolean(), nullable=True))


def downgrade() -> None:
    for column in ("is_free", "currency", "ticket_url", "location_confidence", "province", "original_category"):
        op.drop_column("tourism_events", column)
