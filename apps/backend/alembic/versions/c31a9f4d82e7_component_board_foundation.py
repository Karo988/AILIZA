"""Component-board integrity, evidence, approval and budget foundation.

Revision ID: c31a9f4d82e7
Revises: b6d2f4a09e13
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c31a9f4d82e7"
down_revision: Union[str, None] = "b6d2f4a09e13"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("model_candidates") as batch:
        batch.add_column(sa.Column("candidate_object_hash", sa.String(64), nullable=True))
        batch.add_column(sa.Column("provider_profile_version", sa.String(64), nullable=True))
        batch.add_column(sa.Column("provider_profile_hash", sa.String(64), nullable=True))

    op.create_table(
        "component_evidence",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("candidate_id", sa.Integer, sa.ForeignKey("model_candidates.id"), nullable=False),
        sa.Column("source_url", sa.Text, nullable=False),
        sa.Column("source_type", sa.String(32), nullable=False),
        sa.Column("source_checksum", sa.String(64), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("valid_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("review_status", sa.String(32), nullable=False),
    )
    op.create_index("ix_component_evidence_candidate", "component_evidence", ["candidate_id", "observed_at"])

    op.create_table(
        "evaluation_runs",
        sa.Column("evaluation_run_id", sa.String(36), primary_key=True),
        sa.Column("candidate_id", sa.Integer, sa.ForeignKey("model_candidates.id"), nullable=False),
        sa.Column("candidate_object_hash", sa.String(64), nullable=False),
        sa.Column("provider_profile_hash", sa.String(64), nullable=False),
        sa.Column("benchmark_version", sa.String(64), nullable=False),
        sa.Column("data_kind", sa.String(32), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("metrics", sa.JSON, nullable=False),
        sa.Column("artifact_checksum", sa.String(64), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.String(64), nullable=False),
    )
    op.create_index("ix_evaluation_runs_candidate", "evaluation_runs", ["candidate_id", "started_at"])

    op.create_table(
        "component_approvals",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("candidate_id", sa.Integer, sa.ForeignKey("model_candidates.id"), nullable=False),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("approval_mode", sa.String(32), nullable=False),
        sa.Column("approval_kind", sa.String(32), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("candidate_object_hash", sa.String(64), nullable=False),
        sa.Column("provider_profile_version", sa.String(64), nullable=False),
        sa.Column("provider_profile_hash", sa.String(64), nullable=False),
        sa.Column("approval_basis_hash", sa.String(64), nullable=False),
        sa.Column("task_package", sa.String(128), nullable=False),
        sa.Column("purpose", sa.String(255), nullable=False),
        sa.Column("allowed_data_classes", sa.JSON, nullable=False),
        sa.Column("max_records", sa.Integer, nullable=True),
        sa.Column("cost_limit", sa.Float, nullable=False),
        sa.Column("approver_user_id", sa.String(64), nullable=False),
        sa.Column("reason", sa.Text, nullable=False),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("invalidated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("invalidated_reason", sa.String(255), nullable=True),
    )
    op.create_index("ix_component_approvals_candidate_status", "component_approvals", ["candidate_id", "tenant_id", "status"])

    op.create_table(
        "tenant_governance_settings",
        sa.Column("tenant_id", sa.String(64), primary_key=True),
        sa.Column("organization_mode", sa.String(32), nullable=False),
        sa.Column("configured_by", sa.String(64), nullable=False),
        sa.Column("configured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "budget_policies",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("task_package", sa.String(128), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("hard_limit", sa.Float, nullable=False),
        sa.Column("warning_threshold", sa.Float, nullable=False),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("period_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tenant_id", "task_package", "period_start", name="uq_budget_policy_period"),
    )
    op.create_table(
        "budget_reservations",
        sa.Column("reservation_id", sa.String(36), primary_key=True),
        sa.Column("policy_id", sa.Integer, sa.ForeignKey("budget_policies.id"), nullable=False),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("task_package", sa.String(128), nullable=False),
        sa.Column("amount_reserved", sa.Float, nullable=False),
        sa.Column("amount_actual", sa.Float, nullable=True),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("settled_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_budget_reservations_policy_status", "budget_reservations", ["policy_id", "status"])
    op.create_table(
        "cost_events",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("reservation_id", sa.String(36), sa.ForeignKey("budget_reservations.reservation_id"), nullable=False),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("task_package", sa.String(128), nullable=False),
        sa.Column("provider", sa.String(64), nullable=True),
        sa.Column("model", sa.String(128), nullable=True),
        sa.Column("event_type", sa.String(32), nullable=False),
        sa.Column("amount", sa.Float, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_cost_events_tenant_created", "cost_events", ["tenant_id", "created_at"])

    op.create_table(
        "component_activations",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("approval_id", sa.Integer, sa.ForeignKey("component_approvals.id"), nullable=False),
        sa.Column("candidate_id", sa.Integer, sa.ForeignKey("model_candidates.id"), nullable=False),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("task_package", sa.String(128), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("fallback_candidate_id", sa.Integer, sa.ForeignKey("model_candidates.id"), nullable=True),
        sa.Column("activated_by", sa.String(64), nullable=False),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("disabled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("disable_reason", sa.String(255), nullable=True),
    )
    op.create_index(
        "uq_active_component_task_package", "component_activations",
        ["tenant_id", "task_package"], unique=True,
        sqlite_where=sa.text("status = 'active'"),
        postgresql_where=sa.text("status = 'active'"),
    )


def downgrade() -> None:
    op.drop_table("component_activations")
    op.drop_index("ix_cost_events_tenant_created", table_name="cost_events")
    op.drop_table("cost_events")
    op.drop_index("ix_budget_reservations_policy_status", table_name="budget_reservations")
    op.drop_table("budget_reservations")
    op.drop_table("budget_policies")
    op.drop_table("tenant_governance_settings")
    op.drop_index("ix_component_approvals_candidate_status", table_name="component_approvals")
    op.drop_table("component_approvals")
    op.drop_index("ix_evaluation_runs_candidate", table_name="evaluation_runs")
    op.drop_table("evaluation_runs")
    op.drop_index("ix_component_evidence_candidate", table_name="component_evidence")
    op.drop_table("component_evidence")
    with op.batch_alter_table("model_candidates") as batch:
        batch.drop_column("provider_profile_hash")
        batch.drop_column("provider_profile_version")
        batch.drop_column("candidate_object_hash")
