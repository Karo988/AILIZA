"""Stufe A (Korrektur): Wertebereiche vervollstaendigen und Begruendungspflicht durchsetzen

Behebt vier Luecken aus e7c2b45d81a3:

1. sensitivity_level, is_enabled, is_active, allowed und is_system_domain
   akzeptierten beliebige Werte.
2. reason war mit server_default="" faktisch optional -- eine leere
   Zeichenkette erfuellt keine Begruendungspflicht.
3. domain_role_permissions.reason war nullable.
4. Ein Widerruf war ohne Begruendung moeglich.

Die Regeln sind identisch zu den CheckConstraints in db_schema.py, damit
eine ueber create_all() erzeugte Datenbank nicht schwaecher ist als eine
migrierte.

BESTANDSDATEN: Die Vorgaengermigration brach bei jeder vorhandenen Zeile ab.
Das ist betrieblich zu streng. Hier wird stattdessen GEPRUEFT: gueltige
Bestandsdaten passieren, ungueltige fuehren fail-closed zum Abbruch mit
Angabe der betroffenen Anzahl -- es wird nichts geraten, korrigiert oder
geloescht. Vor und nach einer SQLite-Rekonstruktion werden die Zeilenzahlen
verglichen.

Revision ID: f9a3c61e07b2
Revises: e7c2b45d81a3
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "f9a3c61e07b2"
down_revision: Union[str, None] = "e7c2b45d81a3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLES = ("business_domains", "tenant_business_domains",
           "user_domain_memberships", "domain_role_permissions")

# Bedingungen, die Bestandsdaten VERLETZEN wuerden (SQL-Praedikate).
_INVALID_ROWS = {
    "business_domains": (
        "sensitivity_level NOT IN ('normal','high','confidential') "
        "OR is_system_domain NOT IN (0,1)"
    ),
    "tenant_business_domains": (
        "is_enabled NOT IN (0,1) OR reason IS NULL OR LENGTH(TRIM(reason)) < 3"
    ),
    "user_domain_memberships": (
        "is_active NOT IN (0,1) "
        "OR assignment_reason IS NULL OR LENGTH(TRIM(assignment_reason)) < 3 "
        "OR (revoked_at IS NOT NULL "
        "    AND (revocation_reason IS NULL OR LENGTH(TRIM(revocation_reason)) < 3))"
    ),
    "domain_role_permissions": (
        "allowed NOT IN (0,1) OR reason IS NULL OR LENGTH(TRIM(reason)) < 3"
    ),
}


class DomainDataViolatesNewRules(RuntimeError):
    """Bestandsdaten erfuellen die neuen Regeln nicht -- fail-closed."""


def _counts(bind) -> dict[str, int]:
    return {
        t: bind.execute(sa.text(f"SELECT COUNT(*) FROM {t}")).scalar_one()  # noqa: S608
        for t in _TABLES
    }


def _guard_valid(bind) -> None:
    offenders = {}
    for table, predicate in _INVALID_ROWS.items():
        n = bind.execute(
            sa.text(f"SELECT COUNT(*) FROM {table} WHERE {predicate}")  # noqa: S608
        ).scalar_one()
        if n:
            offenders[table] = n
    if offenders:
        raise DomainDataViolatesNewRules(
            "Bestandsdaten verletzen die neuen Regeln "
            f"(betroffene Zeilen je Tabelle: {offenders}). Es wird nichts "
            "automatisch korrigiert oder geloescht. Bitte die Daten fachlich "
            "bereinigen und die Migration danach erneut ausfuehren."
        )


def upgrade() -> None:
    bind = op.get_bind()
    _guard_valid(bind)
    before = _counts(bind)

    if bind.dialect.name == "sqlite":
        with op.batch_alter_table("business_domains", recreate="always") as b:
            b.create_check_constraint(
                "ck_bd_sensitivity",
                "sensitivity_level IN ('normal','high','confidential')")
            b.create_check_constraint("ck_bd_system_flag", "is_system_domain IN (0,1)")
        with op.batch_alter_table("tenant_business_domains", recreate="always") as b:
            b.alter_column("reason", existing_type=sa.Text(), nullable=False,
                           server_default=None)
            b.create_check_constraint("ck_tbd_enabled", "is_enabled IN (0,1)")
            b.create_check_constraint("ck_tbd_reason_not_blank", "LENGTH(TRIM(reason)) >= 3")
        with op.batch_alter_table("user_domain_memberships", recreate="always") as b:
            b.create_check_constraint("ck_udm_active_flag", "is_active IN (0,1)")
            b.create_check_constraint("ck_udm_reason_not_blank",
                                      "LENGTH(TRIM(assignment_reason)) >= 3")
            b.create_check_constraint(
                "ck_udm_revocation_reason",
                "revoked_at IS NULL OR LENGTH(TRIM(COALESCE(revocation_reason,''))) >= 3")
        with op.batch_alter_table("domain_role_permissions", recreate="always") as b:
            b.alter_column("reason", existing_type=sa.Text(), nullable=False)
            b.create_check_constraint("ck_drp_allowed", "allowed IN (0,1)")
            b.create_check_constraint("ck_drp_reason_not_blank", "LENGTH(TRIM(reason)) >= 3")
    else:
        op.create_check_constraint(
            "ck_bd_sensitivity", "business_domains",
            "sensitivity_level IN ('normal','high','confidential')")
        op.create_check_constraint("ck_bd_system_flag", "business_domains",
                                   "is_system_domain IN (0,1)")
        op.alter_column("tenant_business_domains", "reason",
                        existing_type=sa.Text(), nullable=False, server_default=None)
        op.create_check_constraint("ck_tbd_enabled", "tenant_business_domains",
                                   "is_enabled IN (0,1)")
        op.create_check_constraint("ck_tbd_reason_not_blank", "tenant_business_domains",
                                   "LENGTH(TRIM(reason)) >= 3")
        op.create_check_constraint("ck_udm_active_flag", "user_domain_memberships",
                                   "is_active IN (0,1)")
        op.create_check_constraint("ck_udm_reason_not_blank", "user_domain_memberships",
                                   "LENGTH(TRIM(assignment_reason)) >= 3")
        op.create_check_constraint(
            "ck_udm_revocation_reason", "user_domain_memberships",
            "revoked_at IS NULL OR LENGTH(TRIM(COALESCE(revocation_reason,''))) >= 3")
        op.alter_column("domain_role_permissions", "reason",
                        existing_type=sa.Text(), nullable=False)
        op.create_check_constraint("ck_drp_allowed", "domain_role_permissions",
                                   "allowed IN (0,1)")
        op.create_check_constraint("ck_drp_reason_not_blank", "domain_role_permissions",
                                   "LENGTH(TRIM(reason)) >= 3")

    after = _counts(bind)
    if before != after:
        raise DomainDataViolatesNewRules(
            f"Zeilenzahlen haben sich waehrend der Migration veraendert: "
            f"vorher {before}, nachher {after}."
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        with op.batch_alter_table("domain_role_permissions", recreate="always") as b:
            b.drop_constraint("ck_drp_reason_not_blank", type_="check")
            b.drop_constraint("ck_drp_allowed", type_="check")
            b.alter_column("reason", existing_type=sa.Text(), nullable=True)
        with op.batch_alter_table("user_domain_memberships", recreate="always") as b:
            b.drop_constraint("ck_udm_revocation_reason", type_="check")
            b.drop_constraint("ck_udm_reason_not_blank", type_="check")
            b.drop_constraint("ck_udm_active_flag", type_="check")
        with op.batch_alter_table("tenant_business_domains", recreate="always") as b:
            b.drop_constraint("ck_tbd_reason_not_blank", type_="check")
            b.drop_constraint("ck_tbd_enabled", type_="check")
            b.alter_column("reason", existing_type=sa.Text(), nullable=False,
                           server_default="")
        with op.batch_alter_table("business_domains", recreate="always") as b:
            b.drop_constraint("ck_bd_system_flag", type_="check")
            b.drop_constraint("ck_bd_sensitivity", type_="check")
    else:
        op.drop_constraint("ck_drp_reason_not_blank", "domain_role_permissions", type_="check")
        op.drop_constraint("ck_drp_allowed", "domain_role_permissions", type_="check")
        op.alter_column("domain_role_permissions", "reason",
                        existing_type=sa.Text(), nullable=True)
        op.drop_constraint("ck_udm_revocation_reason", "user_domain_memberships", type_="check")
        op.drop_constraint("ck_udm_reason_not_blank", "user_domain_memberships", type_="check")
        op.drop_constraint("ck_udm_active_flag", "user_domain_memberships", type_="check")
        op.drop_constraint("ck_tbd_reason_not_blank", "tenant_business_domains", type_="check")
        op.drop_constraint("ck_tbd_enabled", "tenant_business_domains", type_="check")
        op.alter_column("tenant_business_domains", "reason",
                        existing_type=sa.Text(), nullable=False, server_default="")
        op.drop_constraint("ck_bd_system_flag", "business_domains", type_="check")
        op.drop_constraint("ck_bd_sensitivity", "business_domains", type_="check")
