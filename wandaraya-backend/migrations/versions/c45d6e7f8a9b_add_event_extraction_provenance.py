"""Add event extraction provenance fields.

Revision ID: c45d6e7f8a9b
Revises: b34c5d6e7f8a
"""
from alembic import op
import sqlalchemy as sa

revision = "c45d6e7f8a9b"
down_revision = "b34c5d6e7f8a"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("tourism_events", sa.Column("extraction_method", sa.String(length=30), nullable=False, server_default="deterministic"))
    op.add_column("tourism_events", sa.Column("extraction_confidence", sa.Float(), nullable=True))
    op.add_column("tourism_events", sa.Column("extraction_evidence", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")))


def downgrade() -> None:
    op.drop_column("tourism_events", "extraction_evidence")
    op.drop_column("tourism_events", "extraction_confidence")
    op.drop_column("tourism_events", "extraction_method")
