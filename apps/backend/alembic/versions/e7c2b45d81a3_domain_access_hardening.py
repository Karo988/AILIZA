"""Stufe A: Bereichsrechte -- Wertebereiche und Konsistenz datenbankseitig sichern

Ergaenzt CHECK-Constraints, einen partiellen Unique-Index gegen doppelte
aktive Mitgliedschaften und Pflicht-Begruendungen. Die Tabellen aus
d4a1f7b93c20 werden nicht ersetzt.

SICHERHEIT: SQLite kennt kein nachtraegliches ADD CONSTRAINT; die Tabellen
werden per batch_alter_table rekonstruiert. Die Migration bricht deshalb
kontrolliert ab, wenn in den Bereichstabellen bereits Bestandsdaten liegen
-- eine Rekonstruktion mit echten Rechtezuweisungen darf nicht ungeprueft
laufen.

DOWNGRADE: Ein Downgrade nach echter Rechtevergabe entfernt die
Schutz-Constraints. Er ist nur nach geprueftem Backup und ausdruecklicher
Freigabe zulaessig.

Revision ID: e7c2b45d81a3
Revises: d4a1f7b93c20
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e7c2b45d81a3"
down_revision: Union[str, None] = "d4a1f7b93c20"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

ROLES = ("viewer", "contributor", "reviewer", "domain_manager")
ACTIONS = (
    "domain.view", "content.read", "content.create", "content.update",
    "content.approve", "content.export", "action.execute", "membership.manage",
)

_ROLE_CHECK = "role_in_domain IN ('" + "','".join(ROLES) + "')"
_ACTION_CHECK = "action IN ('" + "','".join(ACTIONS) + "')"
# Aktiv und widerrufen schliessen einander aus -- ein Datensatz darf nicht
# gleichzeitig als gueltig und als widerrufen gelten.
_REVOKE_CHECK = (
    "(is_active = 1 AND revoked_at IS NULL) OR "
    "(is_active = 0 AND revoked_at IS NOT NULL) OR "
    "(is_active = 0 AND revoked_at IS NULL)"
)
_VALIDITY_CHECK = "valid_until IS NULL OR valid_until > valid_from"


class DomainTablesNotEmpty(RuntimeError):
    """Bestandsdaten in den Bereichstabellen -- Rekonstruktion gestoppt."""


def _guard_empty(bind) -> None:
    """Fail-closed: nur auf leeren Bereichstabellen rekonstruieren."""
    counts = {}
    for table in ("user_domain_memberships", "domain_role_permissions",
                  "tenant_business_domains"):
        counts[table] = bind.execute(
            sa.text(f"SELECT COUNT(*) FROM {table}")  # noqa: S608 - feste Namen
        ).scalar_one()
    if any(counts.values()):
        raise DomainTablesNotEmpty(
            "Bereichstabellen enthalten bereits Daten "
            f"({counts}). Die Haertungsmigration rekonstruiert unter SQLite "
            "Tabellen und wird daher nicht automatisch ausgefuehrt. Bitte "
            "Backup pruefen und Migration ausdruecklich freigeben."
        )


def upgrade() -> None:
    bind = op.get_bind()
    _guard_empty(bind)

    if bind.dialect.name == "sqlite":
        with op.batch_alter_table("user_domain_memberships", recreate="always") as b:
            b.create_check_constraint("ck_udm_role", _ROLE_CHECK)
            b.create_check_constraint("ck_udm_revoked", _REVOKE_CHECK)
            b.create_check_constraint("ck_udm_validity", _VALIDITY_CHECK)
        with op.batch_alter_table("domain_role_permissions", recreate="always") as b:
            b.create_check_constraint("ck_drp_role", _ROLE_CHECK)
            b.create_check_constraint("ck_drp_action", _ACTION_CHECK)
        with op.batch_alter_table("tenant_business_domains", recreate="always") as b:
            b.alter_column("reason", existing_type=sa.Text(), nullable=False,
                           server_default="")
    else:
        op.create_check_constraint("ck_udm_role", "user_domain_memberships", _ROLE_CHECK)
        op.create_check_constraint("ck_udm_revoked", "user_domain_memberships", _REVOKE_CHECK)
        op.create_check_constraint("ck_udm_validity", "user_domain_memberships", _VALIDITY_CHECK)
        op.create_check_constraint("ck_drp_role", "domain_role_permissions", _ROLE_CHECK)
        op.create_check_constraint("ck_drp_action", "domain_role_permissions", _ACTION_CHECK)
        op.alter_column("tenant_business_domains", "reason",
                        existing_type=sa.Text(), nullable=False, server_default="")

    # Hoechstens EINE aktive Mitgliedschaft je Tenant/Bereich/Nutzer.
    # Partieller Index: widerrufene Zeilen bleiben als Historie erhalten.
    op.create_index(
        "uq_udm_active_member", "user_domain_memberships",
        ["tenant_id", "domain_id", "user_id"],
        unique=True, sqlite_where=sa.text("is_active = 1"),
        postgresql_where=sa.text("is_active = 1"),
    )


def downgrade() -> None:
    op.drop_index("uq_udm_active_member", table_name="user_domain_memberships")
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        with op.batch_alter_table("user_domain_memberships", recreate="always") as b:
            b.drop_constraint("ck_udm_role", type_="check")
            b.drop_constraint("ck_udm_revoked", type_="check")
            b.drop_constraint("ck_udm_validity", type_="check")
        with op.batch_alter_table("domain_role_permissions", recreate="always") as b:
            b.drop_constraint("ck_drp_role", type_="check")
            b.drop_constraint("ck_drp_action", type_="check")
        with op.batch_alter_table("tenant_business_domains", recreate="always") as b:
            b.alter_column("reason", existing_type=sa.Text(), nullable=True)
    else:
        op.drop_constraint("ck_udm_role", "user_domain_memberships", type_="check")
        op.drop_constraint("ck_udm_revoked", "user_domain_memberships", type_="check")
        op.drop_constraint("ck_udm_validity", "user_domain_memberships", type_="check")
        op.drop_constraint("ck_drp_role", "domain_role_permissions", type_="check")
        op.drop_constraint("ck_drp_action", "domain_role_permissions", type_="check")
        op.alter_column("tenant_business_domains", "reason",
                        existing_type=sa.Text(), nullable=True)
