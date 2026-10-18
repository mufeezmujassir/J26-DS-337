"""add weather foundation tables

Revision ID: d9e7f6a5b4c3
Revises: b10f0b26943a
"""

from alembic import op
import sqlalchemy as sa


revision = "d9e7f6a5b4c3"
down_revision = "b10f0b26943a"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "weather_stations",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("station_id", sa.String(length=50), nullable=False),
        sa.Column("station_name", sa.String(length=150), nullable=False),
        sa.Column("latitude", sa.Float(), nullable=True),
        sa.Column("longitude", sa.Float(), nullable=True),
        sa.Column("district_id", sa.Integer(), nullable=True),
        sa.Column("has_rainfall", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("has_temperature", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["district_id"], ["districts.id"]),
        sa.UniqueConstraint("station_id", name="uq_weather_stations_station_id"),
        sa.UniqueConstraint("station_name", name="uq_weather_stations_station_name"),
    )
    op.create_index("ix_weather_stations_district_id", "weather_stations", ["district_id"])
    op.create_table(
        "weather_readings",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("station_id", sa.String(length=50), nullable=False),
        sa.Column("station_name", sa.String(length=150), nullable=False),
        sa.Column("district_id", sa.Integer(), nullable=True),
        sa.Column("latitude", sa.Float(), nullable=True),
        sa.Column("longitude", sa.Float(), nullable=True),
        sa.Column("observation_date", sa.Date(), nullable=False),
        sa.Column("rainfall_mm", sa.Float(), nullable=True),
        sa.Column("temperature_min_c", sa.Float(), nullable=True),
        sa.Column("temperature_max_c", sa.Float(), nullable=True),
        sa.Column("humidity_percent", sa.Float(), nullable=True),
        sa.Column("source", sa.String(length=100), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["station_id"], ["weather_stations.station_id"]),
        sa.ForeignKeyConstraint(["district_id"], ["districts.id"]),
        sa.UniqueConstraint("station_id", "observation_date", name="uq_weather_reading_station_date"),
    )
    op.create_index("ix_weather_readings_district_id", "weather_readings", ["district_id"])
    op.create_index("ix_weather_readings_observation_date", "weather_readings", ["observation_date"])
    op.create_table(
        "district_weather_monthly",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("district_id", sa.Integer(), nullable=False),
        sa.Column("observation_date", sa.Date(), nullable=False),
        sa.Column("rainfall_mm", sa.Float(), nullable=True),
        sa.Column("temperature_min_c", sa.Float(), nullable=True),
        sa.Column("temperature_max_c", sa.Float(), nullable=True),
        sa.Column("temperature_avg_c", sa.Float(), nullable=True),
        sa.Column("rainfall_station_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("temperature_station_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["district_id"], ["districts.id"]),
        sa.UniqueConstraint("district_id", "observation_date", name="uq_district_weather_monthly"),
    )
    op.create_index("ix_district_weather_monthly_district_id", "district_weather_monthly", ["district_id"])


def downgrade() -> None:
    op.drop_index("ix_district_weather_monthly_district_id", table_name="district_weather_monthly")
    op.drop_table("district_weather_monthly")
    op.drop_index("ix_weather_readings_observation_date", table_name="weather_readings")
    op.drop_index("ix_weather_readings_district_id", table_name="weather_readings")
    op.drop_table("weather_readings")
    op.drop_index("ix_weather_stations_district_id", table_name="weather_stations")
    op.drop_table("weather_stations")
