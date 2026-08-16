"""feat: Model-Intelligence-Persistenz (Paket A, reine Empfehlungsschicht)

Revision ID: b7e4d92c1a63
Revises: d8f4c6a91b27
Create Date: 2026-08-10

Legt model_candidates und routing_decisions neu an -- reine
Additiv-Migration, keine bestehende Tabelle wird veraendert. Beide
Tabellen sind plattformweite Konfiguration (kein tenant_id-Split bei
model_candidates -- welche Modelle ueberhaupt existieren duerfen, ist
keine Mandantenentscheidung; routing_decisions protokolliert je Mandant,
welche Empfehlung fuer welche Anfrage gegeben wurde).

Kein automatisches Freigaberecht: status startet immer bei "candidate",
wird nur durch einen expliziten, separaten Freigabeschritt (nicht Teil
dieser Migration) auf "approved" gesetzt.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "b7e4d92c1a63"
down_revision: Union[str, None] = "d8f4c6a91b27"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "model_candidates",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("provider", sa.String(64), nullable=False),
        sa.Column("model_id", sa.String(128), nullable=False),
        sa.Column("modalities", sa.JSON, nullable=False),
        sa.Column("capabilities", sa.JSON, nullable=False),
        sa.Column("context_window", sa.Integer, nullable=False),
        sa.Column("regions", sa.JSON, nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("quality_score", sa.Float, nullable=True),
        sa.Column("latency_score", sa.Float, nullable=True),
        sa.Column("cost_score", sa.Float, nullable=True),
        sa.Column("privacy_score", sa.Float, nullable=True),
        sa.Column("benchmark_version", sa.String(64), nullable=False),
        sa.Column("evidence_urls", sa.JSON, nullable=False),
        sa.Column("approved_by", sa.String(64), nullable=True),
        sa.Column("created_by", sa.String(64), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_model_candidates_provider_model", "model_candidates",
        ["provider", "model_id"], unique=True,
    )
    op.create_index("ix_model_candidates_status", "model_candidates", ["status"])

    op.create_table(
        "routing_decisions",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("modality", sa.String(32), nullable=False),
        sa.Column("task", sa.String(64), nullable=False),
        sa.Column("data_risk", sa.String(16), nullable=False),
        sa.Column("selected", sa.String(192), nullable=True),
        sa.Column("fallback", sa.String(192), nullable=True),
        sa.Column("score", sa.Float, nullable=True),
        sa.Column("reason", sa.Text, nullable=False),
        sa.Column("considered", sa.JSON, nullable=False),
        sa.Column("benchmark_version", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_routing_decisions_tenant_created", "routing_decisions",
        ["tenant_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_routing_decisions_tenant_created", table_name="routing_decisions")
    op.drop_table("routing_decisions")
    op.drop_index("ix_model_candidates_status", table_name="model_candidates")
    op.drop_index("ix_model_candidates_provider_model", table_name="model_candidates")
    op.drop_table("model_candidates")
