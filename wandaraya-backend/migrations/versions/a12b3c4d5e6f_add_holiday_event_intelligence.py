"""add Sri Lanka holiday and tourism-event intelligence tables

Revision ID: a12b3c4d5e6f
Revises: f5e2a1d7b903

This migration is additive.  It neither removes existing calendar records nor
calls external sources.  Run a database backup before applying in production.
"""
from alembic import op
import sqlalchemy as sa


revision = "a12b3c4d5e6f"
down_revision = "f5e2a1d7b903"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ingestion_sources",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source_name", sa.String(100), nullable=False, unique=True),
        sa.Column("base_url", sa.Text(), nullable=False),
        sa.Column("source_type", sa.String(40), nullable=False),
        sa.Column("ingestion_frequency", sa.String(40), nullable=False),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("last_success_at", sa.DateTime(timezone=True)),
        sa.Column("last_attempt_at", sa.DateTime(timezone=True)),
        sa.Column("last_error", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "ingestion_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source_id", sa.Integer(), sa.ForeignKey("ingestion_sources.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("dag_id", sa.String(250), nullable=False),
        sa.Column("airflow_run_id", sa.String(250)),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("records_fetched", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("records_inserted", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("records_updated", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("records_unchanged", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("records_rejected", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_summary", sa.Text()),
    )
    op.create_index("ix_ingestion_runs_source_started", "ingestion_runs", ["source_id", "started_at"])
    op.create_table(
        "tourism_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source_id", sa.Integer(), sa.ForeignKey("ingestion_sources.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("source_event_id", sa.String(255), nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("category", sa.String(120)),
        sa.Column("start_datetime", sa.DateTime(timezone=True)),
        sa.Column("end_datetime", sa.DateTime(timezone=True)),
        sa.Column("timezone", sa.String(64), nullable=False, server_default="Asia/Colombo"),
        sa.Column("venue", sa.String(255)), sa.Column("address", sa.Text()), sa.Column("city", sa.String(120)),
        sa.Column("district_id", sa.Integer(), sa.ForeignKey("districts.id", ondelete="RESTRICT")),
        sa.Column("organizer", sa.String(255)), sa.Column("event_url", sa.Text()), sa.Column("registration_url", sa.Text()),
        sa.Column("price_information", sa.Text()), sa.Column("event_notes", sa.Text()), sa.Column("hashtags", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("status", sa.String(40), nullable=False, server_default="unknown"), sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("source_updated_at", sa.DateTime(timezone=True)), sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("source_id", "source_event_id", name="uq_tourism_event_source_record"),
    )
    op.create_index("ix_tourism_events_start", "tourism_events", ["start_datetime"])
    op.create_table(
        "event_attraction_links",
        sa.Column("id", sa.Integer(), primary_key=True), sa.Column("event_id", sa.Integer(), sa.ForeignKey("tourism_events.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("attraction_id", sa.Integer(), sa.ForeignKey("attractions.id", ondelete="RESTRICT"), nullable=False), sa.Column("relationship_type", sa.String(80), nullable=False),
        sa.Column("evidence_source", sa.Text(), nullable=False), sa.Column("verification_status", sa.String(40), nullable=False, server_default="review_required"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("event_id", "attraction_id", "relationship_type", name="uq_event_attraction_relationship"),
    )
    op.create_table(
        "holiday_event_revisions",
        sa.Column("id", sa.Integer(), primary_key=True), sa.Column("record_type", sa.String(30), nullable=False), sa.Column("record_identifier", sa.String(255), nullable=False),
        sa.Column("previous_values", sa.JSON()), sa.Column("updated_values", sa.JSON(), nullable=False), sa.Column("detected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_evidence", sa.Text()), sa.Column("change_reason", sa.String(80), nullable=False),
    )
    # Extend, rather than replace, the legacy holiday_calendar table.
    op.add_column("holiday_calendar", sa.Column("is_bank_holiday", sa.Boolean()))
    op.add_column("holiday_calendar", sa.Column("is_mercantile_holiday", sa.Boolean()))
    op.add_column("holiday_calendar", sa.Column("poya_name", sa.String(100)))
    op.add_column("holiday_calendar", sa.Column("religious_category", sa.String(100)))
    op.add_column("holiday_calendar", sa.Column("confirmation_status", sa.String(30), nullable=False, server_default="unknown"))
    op.add_column("holiday_calendar", sa.Column("source_updated_at", sa.DateTime(timezone=True)))
    op.add_column("holiday_calendar", sa.Column("first_seen_at", sa.DateTime(timezone=True)))
    op.add_column("holiday_calendar", sa.Column("last_seen_at", sa.DateTime(timezone=True)))
    op.create_unique_constraint("uq_holiday_calendar_source_record", "holiday_calendar", ["event_date", "name", "source_url"])


def downgrade() -> None:
    op.drop_constraint("uq_holiday_calendar_source_record", "holiday_calendar", type_="unique")
    for column in ("last_seen_at", "first_seen_at", "source_updated_at", "confirmation_status", "religious_category", "poya_name", "is_mercantile_holiday", "is_bank_holiday"):
        op.drop_column("holiday_calendar", column)
    op.drop_table("holiday_event_revisions")
    op.drop_table("event_attraction_links")
    op.drop_index("ix_tourism_events_start", table_name="tourism_events")
    op.drop_table("tourism_events")
    op.drop_index("ix_ingestion_runs_source_started", table_name="ingestion_runs")
    op.drop_table("ingestion_runs")
    op.drop_table("ingestion_sources")
