"""add modified wheather

Revision ID: 8295ce04d40b
Revises: d9e7f6a5b4c3
Create Date: 2026-10-08 04:42:13.780528

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8295ce04d40b'
down_revision: Union[str, None] = 'd9e7f6a5b4c3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add the missing lookup index without replacing referenced unique keys.

    ``weather_readings.station_id`` references the existing named unique
    constraint on ``weather_stations.station_id``.  Dropping that constraint
    would invalidate the foreign key, so this revision must leave both station
    unique constraints in place.
    """
    op.create_index(op.f('ix_weather_readings_station_id'), 'weather_readings', ['station_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_weather_readings_station_id'), table_name='weather_readings')
