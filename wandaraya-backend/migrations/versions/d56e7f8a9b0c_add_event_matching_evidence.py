"""Add evidence-aware fields for candidate event-attraction links.

Revision ID: d56e7f8a9b0c
Revises: c45d6e7f8a9b
"""
from alembic import op
import sqlalchemy as sa


revision = "d56e7f8a9b0c"
down_revision = "c45d6e7f8a9b"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("event_attraction_links", sa.Column("evidence_type", sa.String(length=80), nullable=True))
    op.add_column("event_attraction_links", sa.Column("semantic_similarity", sa.Float(), nullable=True))
    op.add_column("event_attraction_links", sa.Column("geographic_distance_km", sa.Float(), nullable=True))
    op.add_column("event_attraction_links", sa.Column("matching_confidence", sa.Float(), nullable=True))
    op.add_column("event_attraction_links", sa.Column("explanation", sa.Text(), nullable=True))
    op.add_column("event_attraction_links", sa.Column("verification_timestamp", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_event_attraction_links_status", "event_attraction_links", ["verification_status"])


def downgrade() -> None:
    op.drop_index("ix_event_attraction_links_status", table_name="event_attraction_links")
    for column in ("verification_timestamp", "explanation", "matching_confidence", "geographic_distance_km", "semantic_similarity", "evidence_type"):
        op.drop_column("event_attraction_links", column)
