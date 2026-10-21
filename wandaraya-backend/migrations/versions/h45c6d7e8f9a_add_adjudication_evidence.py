"""add adjudication evidence provenance

Revision ID: h45c6d7e8f9a
Revises: g34b5c6d7e8f
"""
from alembic import op
import sqlalchemy as sa

revision="h45c6d7e8f9a"
down_revision="g34b5c6d7e8f"
branch_labels=None
depends_on=None

def upgrade():
    op.add_column("climate_adjudicated_labels",sa.Column("evidence_json",sa.JSON(),nullable=False,server_default=sa.text("'{}'::json")))
    op.alter_column("climate_adjudicated_labels","evidence_json",server_default=None)

def downgrade():
    op.drop_column("climate_adjudicated_labels","evidence_json")
