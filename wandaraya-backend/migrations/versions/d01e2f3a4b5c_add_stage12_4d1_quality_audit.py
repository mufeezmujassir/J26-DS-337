"""add stage12_4d1 quality audit tables and columns

Revision ID: d01e2f3a4b5c
Revises: c90d1e2f3a4b
Create Date: 2026-10-20 20:50:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = "d01e2f3a4b5c"
down_revision = "c90d1e2f3a4b"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Add quality audit columns to climate_attraction_activity_mappings
    op.add_column(
        "climate_attraction_activity_mappings",
        sa.Column("mapping_validation_status", sa.String(40), nullable=False, server_default="VERIFIED"),
    )
    op.add_column(
        "climate_attraction_activity_mappings",
        sa.Column("mapping_validation_reason", sa.Text(), nullable=True),
    )
    op.add_column(
        "climate_attraction_activity_mappings",
        sa.Column("mapping_rule_version", sa.String(40), nullable=False, server_default="v1.1"),
    )
    op.add_column(
        "climate_attraction_activity_mappings",
        sa.Column("is_eligible_for_seasonality", sa.Boolean(), nullable=False, server_default="true"),
    )
    op.create_index(
        "ix_climate_attraction_activity_mappings_val_status",
        "climate_attraction_activity_mappings",
        ["mapping_validation_status"],
    )
    op.create_index(
        "ix_climate_attraction_activity_mappings_eligible",
        "climate_attraction_activity_mappings",
        ["is_eligible_for_seasonality"],
    )

    # 2. Add quality audit columns to climate_attraction_activity_seasonality
    op.add_column(
        "climate_attraction_activity_seasonality",
        sa.Column("explanation_validation_status", sa.String(40), nullable=False, server_default="VALIDATED"),
    )
    op.add_column(
        "climate_attraction_activity_seasonality",
        sa.Column("geographic_validation_status", sa.String(40), nullable=False, server_default="VERIFIED"),
    )
    op.add_column(
        "climate_attraction_activity_seasonality",
        sa.Column("quality_audit_version", sa.String(40), nullable=False, server_default="v1.1"),
    )
    op.add_column(
        "climate_attraction_activity_seasonality",
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
    )
    op.create_index(
        "ix_attr_act_seasonality_active",
        "climate_attraction_activity_seasonality",
        ["is_active"],
    )

    # 3. Create climate_seasonality_quality_audit table
    op.create_table(
        "climate_seasonality_quality_audit",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("entity_type", sa.String(60), nullable=False),
        sa.Column("entity_id", sa.Integer(), nullable=False),
        sa.Column("issue_type", sa.String(60), nullable=False),
        sa.Column("severity", sa.String(20), nullable=False),
        sa.Column("original_value_json", sa.JSON(), nullable=False),
        sa.Column("corrected_value_json", sa.JSON(), nullable=False),
        sa.Column("evidence_json", sa.JSON(), nullable=False),
        sa.Column("correction_status", sa.String(40), nullable=False),
        sa.Column("audit_version", sa.String(40), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("corrected_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_climate_seasonality_quality_audit_entity", "climate_seasonality_quality_audit", ["entity_type", "entity_id"])
    op.create_index("ix_climate_seasonality_quality_audit_issue", "climate_seasonality_quality_audit", ["issue_type"])
    op.create_index("ix_climate_seasonality_quality_audit_status", "climate_seasonality_quality_audit", ["correction_status"])


def downgrade() -> None:
    op.drop_table("climate_seasonality_quality_audit")
    op.drop_index("ix_attr_act_seasonality_active", table_name="climate_attraction_activity_seasonality")
    op.drop_column("climate_attraction_activity_seasonality", "is_active")
    op.drop_column("climate_attraction_activity_seasonality", "quality_audit_version")
    op.drop_column("climate_attraction_activity_seasonality", "geographic_validation_status")
    op.drop_column("climate_attraction_activity_seasonality", "explanation_validation_status")
    op.drop_index("ix_climate_attraction_activity_mappings_eligible", table_name="climate_attraction_activity_mappings")
    op.drop_index("ix_climate_attraction_activity_mappings_val_status", table_name="climate_attraction_activity_mappings")
    op.drop_column("climate_attraction_activity_mappings", "is_eligible_for_seasonality")
    op.drop_column("climate_attraction_activity_mappings", "mapping_rule_version")
    op.drop_column("climate_attraction_activity_mappings", "mapping_validation_reason")
    op.drop_column("climate_attraction_activity_mappings", "mapping_validation_status")
