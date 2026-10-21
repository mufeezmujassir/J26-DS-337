"""add Stage 12.4D.2 evidence and evaluation eligibility

Revision ID: e12f3a4b5c6d
Revises: d01e2f3a4b5c
Create Date: 2026-10-20 22:15:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = "e12f3a4b5c6d"
down_revision = "d01e2f3a4b5c"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("climate_attraction_activity_mappings", sa.Column("evidence_tier", sa.String(20), nullable=True))
    op.add_column("climate_attraction_activity_mappings", sa.Column("evidence_policy_version", sa.String(40), nullable=True))
    op.add_column("climate_attraction_activity_mappings", sa.Column("evaluation_eligibility_status", sa.String(60), nullable=True))
    op.add_column("climate_attraction_activity_mappings", sa.Column("is_eligible_for_offline_evaluation", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("climate_attraction_activity_mappings", sa.Column("independent_review_status", sa.String(40), nullable=False, server_default="NOT_REVIEWED"))
    op.create_index("ix_climate_mapping_evidence_tier", "climate_attraction_activity_mappings", ["evidence_tier"])
    op.create_index("ix_climate_mapping_eval_status", "climate_attraction_activity_mappings", ["evaluation_eligibility_status"])
    op.create_index("ix_climate_mapping_eval_eligible", "climate_attraction_activity_mappings", ["is_eligible_for_offline_evaluation"])
    op.create_table(
        "climate_mapping_evidence_audit",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("mapping_id", sa.Integer(), sa.ForeignKey("climate_attraction_activity_mappings.id"), nullable=False),
        sa.Column("original_mapping_status", sa.String(40), nullable=False),
        sa.Column("revised_mapping_status", sa.String(40), nullable=False),
        sa.Column("original_evaluation_eligibility", sa.String(60), nullable=True),
        sa.Column("revised_evaluation_eligibility", sa.String(60), nullable=False),
        sa.Column("provisional_audit_class", sa.String(80), nullable=True),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("evidence_json", sa.JSON(), nullable=False),
        sa.Column("policy_version", sa.String(40), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("mapping_id", "policy_version", name="uq_climate_mapping_evidence_audit"),
    )
    op.create_index("ix_climate_mapping_evidence_audit_mapping", "climate_mapping_evidence_audit", ["mapping_id"])


def downgrade() -> None:
    op.drop_table("climate_mapping_evidence_audit")
    op.drop_index("ix_climate_mapping_eval_eligible", table_name="climate_attraction_activity_mappings")
    op.drop_index("ix_climate_mapping_eval_status", table_name="climate_attraction_activity_mappings")
    op.drop_index("ix_climate_mapping_evidence_tier", table_name="climate_attraction_activity_mappings")
    op.drop_column("climate_attraction_activity_mappings", "independent_review_status")
    op.drop_column("climate_attraction_activity_mappings", "is_eligible_for_offline_evaluation")
    op.drop_column("climate_attraction_activity_mappings", "evaluation_eligibility_status")
    op.drop_column("climate_attraction_activity_mappings", "evidence_policy_version")
    op.drop_column("climate_attraction_activity_mappings", "evidence_tier")
