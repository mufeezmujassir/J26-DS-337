"""add weather forecast persistence tables

Revision ID: e4a7d9c2f681
Revises: 8295ce04d40b
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "e4a7d9c2f681"
down_revision = "8295ce04d40b"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "weather_model_runs",
        sa.Column("run_id", sa.String(length=160), nullable=False),
        sa.Column("district_id", sa.Integer(), nullable=False),
        sa.Column("target", sa.String(length=50), nullable=False),
        sa.Column("model_name", sa.String(length=60), nullable=False),
        sa.Column("training_start", sa.Date(), nullable=False),
        sa.Column("training_cutoff", sa.Date(), nullable=False),
        sa.Column("latest_calendar_month", sa.Date(), nullable=False),
        sa.Column("latest_observed_month", sa.Date(), nullable=False),
        sa.Column("latest_month_missing", sa.Boolean(), nullable=False),
        sa.Column("training_observations", sa.Integer(), nullable=False),
        sa.Column("forecast_horizon_months", sa.Integer(), nullable=False),
        sa.Column("validation_gate_passed", sa.Boolean(), nullable=False),
        sa.Column("production_approved", sa.Boolean(), nullable=False),
        sa.Column("parameters", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("created_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("training_observations >= 0", name="ck_weather_run_observations"),
        sa.CheckConstraint("forecast_horizon_months > 0", name="ck_weather_run_horizon"),
        sa.ForeignKeyConstraint(["district_id"], ["districts.id"]),
        sa.PrimaryKeyConstraint("run_id"),
    )
    op.create_index("ix_weather_model_runs_district_id", "weather_model_runs", ["district_id"])
    op.create_index("ix_weather_model_runs_target", "weather_model_runs", ["target"])

    op.create_table(
        "weather_forecasts",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("run_id", sa.String(length=160), nullable=False),
        sa.Column("forecast_month", sa.Date(), nullable=False),
        sa.Column("predicted_value", sa.Float(), nullable=False),
        sa.Column("lower_bound", sa.Float(), nullable=True),
        sa.Column("upper_bound", sa.Float(), nullable=True),
        sa.Column("raw_prediction", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "lower_bound IS NULL OR lower_bound <= predicted_value",
            name="ck_weather_forecast_lower_bound",
        ),
        sa.CheckConstraint(
            "upper_bound IS NULL OR upper_bound >= predicted_value",
            name="ck_weather_forecast_upper_bound",
        ),
        sa.ForeignKeyConstraint(["run_id"], ["weather_model_runs.run_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id", "forecast_month", name="uq_weather_forecast_run_month"),
    )
    op.create_index("ix_weather_forecasts_forecast_month", "weather_forecasts", ["forecast_month"])
    op.create_index("ix_weather_forecasts_run_id", "weather_forecasts", ["run_id"])


def downgrade() -> None:
    op.drop_index("ix_weather_forecasts_run_id", table_name="weather_forecasts")
    op.drop_index("ix_weather_forecasts_forecast_month", table_name="weather_forecasts")
    op.drop_table("weather_forecasts")
    op.drop_index("ix_weather_model_runs_target", table_name="weather_model_runs")
    op.drop_index("ix_weather_model_runs_district_id", table_name="weather_model_runs")
    op.drop_table("weather_model_runs")
