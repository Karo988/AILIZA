"""perf: Indizes fuer haeufige Abfragen auf audit_logs, approval_requests, agent_runs

Revision ID: d8f4c6a91b27
Revises: b4d3a1d0de71
Create Date: 2026-08-10

Hintergrund: query_audit_events()/list_audit_entries() (audit_logs),
list_approval_requests() (approval_requests) und list_agent_runs()
(agent_runs) filtern nach tenant_id/status/action und sortieren nach
timestamp/created_at/updated_at DESC -- ohne Index bisher ein
Volltabellen-Scan je Aufruf, der mit wachsendem (append-only) Audit-Log
kontinuierlich teurer wird. Reine Index-Ergaenzung, keine Datenaenderung,
kein Datenverlust, kein Downtime-Risiko (CREATE INDEX auf einer
bestehenden Tabelle liest nur, schreibt keine Zeilen um).
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d8f4c6a91b27"
down_revision: Union[str, None] = "b4d3a1d0de71"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index("ix_audit_logs_tenant_timestamp", "audit_logs", ["tenant_id", "timestamp"])
    op.create_index("ix_audit_logs_action", "audit_logs", ["action"])
    op.create_index("ix_approval_requests_status", "approval_requests", ["status"])
    op.create_index("ix_approval_requests_tenant_created", "approval_requests", ["tenant_id", "created_at"])
    op.create_index("ix_agent_runs_status", "agent_runs", ["status"])
    op.create_index("ix_agent_runs_tenant_updated", "agent_runs", ["tenant_id", "updated_at"])


def downgrade() -> None:
    op.drop_index("ix_agent_runs_tenant_updated", table_name="agent_runs")
    op.drop_index("ix_agent_runs_status", table_name="agent_runs")
    op.drop_index("ix_approval_requests_tenant_created", table_name="approval_requests")
    op.drop_index("ix_approval_requests_status", table_name="approval_requests")
    op.drop_index("ix_audit_logs_action", table_name="audit_logs")
    op.drop_index("ix_audit_logs_tenant_timestamp", table_name="audit_logs")
