"""Bereichsfreischaltung und Rechteverwaltung V1

Legt die vier Tabellen des Bereichsmodells an und spielt das feste
Bereichsvokabular idempotent ein. Rein additiv: bestehende Tabellen,
Daten und Zugriffspfade bleiben unveraendert. Es werden KEINE
Mitgliedschaften oder Rechte vergeben -- ohne ausdrueckliche Zuweisung
gilt weiterhin fail-closed "kein Zugriff".

Revision ID: d4a1f7b93c20
Revises: c8ff9bb332ba
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "d4a1f7b93c20"
down_revision: Union[str, None] = "c8ff9bb332ba"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Festes Startvokabular. Codes sind nach Inbetriebnahme unveraenderlich.
_SEED_DOMAINS = [
    ("accounting", "Buchhaltung", "finance", "confidential"),
    ("invoicing", "Faktura", "finance", "confidential"),
    ("factoring", "Factoring", "finance", "confidential"),
    ("finance", "Finanzen", "finance", "confidential"),
    ("controlling", "Controlling", "finance", "confidential"),
    ("marketing", "Marketing", "market", "normal"),
    ("sales", "Vertrieb", "market", "normal"),
    ("procurement", "Einkauf", "supply", "normal"),
    ("hr", "Personal", "people", "confidential"),
    ("legal", "Recht", "governance", "confidential"),
    ("projects", "Projekte", "delivery", "normal"),
    ("tasks", "Aufgaben", "delivery", "normal"),
    ("company_knowledge", "Unternehmenswissen", "knowledge", "high"),
]


def upgrade() -> None:
    op.create_table(
        "business_domains",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("category", sa.String(length=64), nullable=True),
        sa.Column("sensitivity_level", sa.String(length=32), nullable=False,
                  server_default="normal"),
        sa.Column("is_system_domain", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code"),
    )

    op.create_table(
        "tenant_business_domains",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("domain_id", sa.Integer(), nullable=False),
        sa.Column("is_enabled", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("enabled_by", sa.String(length=64), nullable=True),
        sa.Column("enabled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("disabled_by", sa.String(length=64), nullable=True),
        sa.Column("disabled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.ForeignKeyConstraint(["domain_id"], ["business_domains.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "domain_id", name="uq_tenant_domain"),
    )
    op.create_index("ix_tenant_business_domains_tenant", "tenant_business_domains",
                    ["tenant_id", "is_enabled"])

    op.create_table(
        "user_domain_memberships",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("domain_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("role_in_domain", sa.String(length=32), nullable=False),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("valid_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("review_required_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("assigned_by", sa.String(length=64), nullable=False),
        sa.Column("assignment_reason", sa.Text(), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_by", sa.String(length=64), nullable=True),
        sa.Column("revocation_reason", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.ForeignKeyConstraint(["domain_id"], ["business_domains.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_user_domain_memberships_lookup", "user_domain_memberships",
                    ["tenant_id", "user_id", "is_active"])
    op.create_index("ix_user_domain_memberships_domain", "user_domain_memberships",
                    ["tenant_id", "domain_id", "is_active"])

    op.create_table(
        "domain_role_permissions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("domain_id", sa.Integer(), nullable=False),
        sa.Column("role_in_domain", sa.String(length=32), nullable=False),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("allowed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("granted_by", sa.String(length=64), nullable=True),
        sa.Column("granted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.ForeignKeyConstraint(["domain_id"], ["business_domains.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "domain_id", "role_in_domain", "action",
                            name="uq_domain_role_action"),
    )
    op.create_index("ix_domain_role_permissions_lookup", "domain_role_permissions",
                    ["tenant_id", "domain_id", "role_in_domain"])

    # Startvokabular idempotent einspielen (nur fehlende Codes anlegen).
    bind = op.get_bind()
    now = datetime.now(timezone.utc)
    existing = {
        row[0] for row in bind.execute(sa.text("SELECT code FROM business_domains"))
    }
    for code, name, category, sensitivity in _SEED_DOMAINS:
        if code in existing:
            continue
        bind.execute(
            sa.text(
                "INSERT INTO business_domains "
                "(code, name, description, category, sensitivity_level, "
                " is_system_domain, created_at, updated_at) "
                "VALUES (:code, :name, NULL, :category, :sensitivity, 1, :now, :now)"
            ),
            {"code": code, "name": name, "category": category,
             "sensitivity": sensitivity, "now": now},
        )


def downgrade() -> None:
    # Reihenfolge beachtet die Fremdschluessel auf business_domains.
    op.drop_index("ix_domain_role_permissions_lookup", table_name="domain_role_permissions")
    op.drop_table("domain_role_permissions")
    op.drop_index("ix_user_domain_memberships_domain", table_name="user_domain_memberships")
    op.drop_index("ix_user_domain_memberships_lookup", table_name="user_domain_memberships")
    op.drop_table("user_domain_memberships")
    op.drop_index("ix_tenant_business_domains_tenant", table_name="tenant_business_domains")
    op.drop_table("tenant_business_domains")
    op.drop_table("business_domains")
