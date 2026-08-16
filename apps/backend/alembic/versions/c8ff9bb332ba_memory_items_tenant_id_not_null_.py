"""memory_items tenant_id NOT NULL (Knowledge Phase 1)

Revision ID: c8ff9bb332ba
Revises: 3c5757ab05f2
Create Date: 2026-08-16 10:39:30.042314

Knowledge Phase 1 -- Memory Tenant Integrity. Vorher war memory_items.tenant_id
fuer user_memory optional (Uebergangsregel aus M1); diese Migration macht
tenant_id fuer JEDEN Scope zur Datenbank-Pflicht.

FAIL-CLOSED: kein automatischer Default-Tenant, kein Erraten anhand
owner_user_id, keine Loeschung ungeklaerter Altdaten. Existieren vor dem
ALTER noch Zeilen mit tenant_id IS NULL oder nur Whitespace, bricht die
Migration kontrolliert ab (MemoryTenantIdMigrationBlocked) -- die
Fehlermeldung enthaelt ausschliesslich die Anzahl betroffener Zeilen, keine
Memory-Inhalte. Eine fachliche Legacy-Reconciliation ist ein separates,
spaeteres Arbeitspaket (siehe database.py count_unassigned_memory_items()
fuer die read-only Vorab-Diagnose).
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c8ff9bb332ba'
down_revision: Union[str, None] = '3c5757ab05f2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


class MemoryTenantIdMigrationBlocked(Exception):
    """Wird geworfen, wenn memory_items Zeilen mit tenant_id IS NULL oder
    leer/Whitespace enthaelt und die Migration deshalb NICHT sicher
    durchgefuehrt werden kann."""


def upgrade() -> None:
    bind = op.get_bind()

    # Vorab-Pruefung VOR jeder Schemaaenderung -- datensparsame
    # Fehlermeldung (nur Anzahl, keine IDs, keine Inhalte).
    null_count = bind.execute(
        sa.text(
            "SELECT COUNT(*) FROM memory_items "
            "WHERE tenant_id IS NULL OR TRIM(tenant_id) = ''"
        )
    ).scalar_one()

    if null_count > 0:
        raise MemoryTenantIdMigrationBlocked(
            f"Migration abgebrochen: memory_items enthaelt {null_count} "
            "Eintrag/Eintraege ohne eindeutige Tenant-Zuordnung. Keine "
            "automatische Zuordnung vorgenommen -- siehe "
            "database.count_unassigned_memory_items() fuer eine read-only "
            "Vorab-Diagnose. Legacy-Reconciliation ist ein separates "
            "Arbeitspaket."
        )

    dialect = bind.dialect.name
    if dialect == "sqlite":
        # SQLite kennt kein natives ALTER COLUMN -- batch-Modus baut die
        # Tabelle kontrolliert neu auf (Spalten/PK/FK/Indizes bleiben
        # erhalten, da aus der reflektierten Metadata uebernommen).
        with op.batch_alter_table("memory_items", recreate="always") as batch_op:
            batch_op.alter_column(
                "tenant_id",
                existing_type=sa.String(length=64),
                nullable=False,
            )
    else:
        op.alter_column(
            "memory_items",
            "tenant_id",
            existing_type=sa.String(length=64),
            nullable=False,
        )


def downgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name

    if dialect == "sqlite":
        with op.batch_alter_table("memory_items", recreate="always") as batch_op:
            batch_op.alter_column(
                "tenant_id",
                existing_type=sa.String(length=64),
                nullable=True,
            )
    else:
        op.alter_column(
            "memory_items",
            "tenant_id",
            existing_type=sa.String(length=64),
            nullable=True,
        )
