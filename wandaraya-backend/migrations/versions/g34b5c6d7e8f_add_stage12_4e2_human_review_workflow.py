"""add Stage 12.4E.2 human review workflow

Revision ID: g34b5c6d7e8f
Revises: f23a4b5c6d7e
"""
from alembic import op
import sqlalchemy as sa

revision = "g34b5c6d7e8f"
down_revision = "f23a4b5c6d7e"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "climate_review_assignments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("review_dataset_version", sa.String(80), nullable=False),
        sa.Column("task_type", sa.String(30), nullable=False),
        sa.Column("review_item_id", sa.String(80), nullable=False),
        sa.Column("reviewer_id", sa.String(120), nullable=False),
        sa.Column("status", sa.String(30), nullable=False, server_default="ASSIGNED"),
        sa.Column("assigned_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finalized_at", sa.DateTime(timezone=True)),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.CheckConstraint("task_type IN ('mapping','seasonality')", name="ck_climate_review_assignment_task"),
        sa.CheckConstraint("status IN ('ASSIGNED','IN_PROGRESS','FINALIZED')", name="ck_climate_review_assignment_status"),
        sa.UniqueConstraint("review_dataset_version", "task_type", "review_item_id", "reviewer_id", name="uq_climate_review_assignment"),
    )
    op.create_table(
        "climate_reviewer_submission_corrections",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("submission_id", sa.Integer(), sa.ForeignKey("climate_reviewer_label_submissions.id"), nullable=False),
        sa.Column("prior_label", sa.String(50), nullable=False),
        sa.Column("revised_label", sa.String(50), nullable=False),
        sa.Column("authorized_by", sa.String(120), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("corrected_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "climate_ground_truth_dataset_versions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("dataset_version", sa.String(80), nullable=False, unique=True),
        sa.Column("review_sampling_version", sa.String(80), nullable=False),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("manifest_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "climate_evaluation_artifact_references",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("run_id", sa.Integer(), sa.ForeignKey("climate_evaluation_runs.id"), nullable=False),
        sa.Column("artifact_type", sa.String(60), nullable=False),
        sa.Column("path", sa.Text(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("run_id", "path", name="uq_climate_eval_artifact_ref"),
    )


def downgrade():
    for table in (
        "climate_evaluation_artifact_references",
        "climate_ground_truth_dataset_versions",
        "climate_reviewer_submission_corrections",
        "climate_review_assignments",
    ):
        op.drop_table(table)
