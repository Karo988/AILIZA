"""feat: Kundenstammdaten-Tabelle (Phase 1, kleinster Baustein Kunde->Artikel->Rechnung)

Revision ID: e1a7c3f92b56
Revises: d8f4c6a91b27
Create Date: 2026-08-10

Legt die Tabelle `customers` neu an -- reine Additiv-Migration, keine
bestehende Tabelle wird veraendert. Zusammengesetzter Primary Key
(id, tenant_id) wie bei user_projects/user_chats: vollstaendige
Mandanten-Isolation, kein Hijack ueber eine kollidierende id ueber
Mandantengrenzen hinweg.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "e1a7c3f92b56"
down_revision: Union[str, None] = "d8f4c6a91b27"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "customers",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("tenant_id", sa.String(64), primary_key=True, nullable=False),
        sa.Column("owner_user_id", sa.String(64), nullable=True),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("email", sa.Text, nullable=True),
        sa.Column("phone", sa.Text, nullable=True),
        sa.Column("address", sa.Text, nullable=True),
        sa.Column("note", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_customers_tenant_owner", "customers", ["tenant_id", "owner_user_id"])


def downgrade() -> None:
    op.drop_index("ix_customers_tenant_owner", table_name="customers")
    op.drop_table("customers")
