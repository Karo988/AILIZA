"""fix: postgresql_where fuer die zwei partiellen Unique-Indizes ergaenzen

Revision ID: b4d3a1d0de71
Revises: 6165ff33e9ee
Create Date: 2026-08-02

Hintergrund: `ux_active_specialist_role` (user_specialist_roles) und
`ux_active_case_assignment` (case_assignments) sind in database.py als
partielle Unique-Indizes mit `sqlite_where=...` definiert, aber OHNE
passendes `postgresql_where=...`. Unter SQLite funktionieren sie bereits
korrekt als partielle Indizes (nur "aktive" Zeilen sind eindeutig). Unter
PostgreSQL wurden sie bisher (auch durch die Baseline-Migration 0001, die
das Ist-Verhalten bewusst 1:1 abbildet) als VOLLE, nicht-partielle Unique-
Indizes angelegt -- strenger als fachlich gemeint, da dort auch inaktive/
widerrufene Zeilen in die Eindeutigkeitspruefung eingehen.

Diese Migration korrigiert das NUR fuer PostgreSQL:
  - Auf SQLite ist dies ein reines No-Op (die Indizes sind dort bereits
    korrekt partiell aus Migration 0001; ein Drop/Recreate mit identischer
    sqlite_where-Klausel aendert das Verhalten nicht, wird hier aber
    dialektabhaengig uebersprungen, um bestehende SQLite-Datenbanken nicht
    unnoetig anzufassen).
  - Auf PostgreSQL wird der jeweilige Index gedroppt und mit passendem
    postgresql_where neu angelegt (Zeilen bleiben unveraendert -- reine
    Index-Operation, kein Datenverlust).

Fachliche Regel bleibt in beiden Faellen identisch: "genau eine aktive
Zuweisung je (user_id, tenant_id, specialist_role)" bzw. "genau eine nicht
widerrufene Zuordnung je (tenant_id, case_type, case_id, assigned_to_user_id)".
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "b4d3a1d0de71"
down_revision: Union[str, None] = "6165ff33e9ee"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return  # SQLite: Indizes sind bereits korrekt partiell (Migration 0001).

    op.drop_index("ux_active_specialist_role", table_name="user_specialist_roles")
    op.create_index(
        "ux_active_specialist_role", "user_specialist_roles",
        ["user_id", "tenant_id", "specialist_role"], unique=True,
        postgresql_where=sa.text("is_active = 1 AND revoked_at IS NULL"),
    )

    op.drop_index("ux_active_case_assignment", table_name="case_assignments")
    op.create_index(
        "ux_active_case_assignment", "case_assignments",
        ["tenant_id", "case_type", "case_id", "assigned_to_user_id"], unique=True,
        postgresql_where=sa.text("revoked_at IS NULL"),
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    op.drop_index("ux_active_case_assignment", table_name="case_assignments")
    op.create_index(
        "ux_active_case_assignment", "case_assignments",
        ["tenant_id", "case_type", "case_id", "assigned_to_user_id"], unique=True,
    )

    op.drop_index("ux_active_specialist_role", table_name="user_specialist_roles")
    op.create_index(
        "ux_active_specialist_role", "user_specialist_roles",
        ["user_id", "tenant_id", "specialist_role"], unique=True,
    )
