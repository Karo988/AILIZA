"""Domain-Vokabular V2: KMU-Fachbereiche vervollstaendigen und Sensitivitaet angleichen

Das Startvokabular aus d4a1f7b93c20 deckte 13 Bereiche ab. Gegenueber dem
fachlichen Zielbild (15 KMU-Abteilungen, Karo-Entscheidung 2026-08-19)
fehlten neun Bereiche vollstaendig, und drei vorhandene waren zu niedrig
eingestuft.

NEU (9):
  management, operations, logistics, it_support, research_development,
  customer_support, quality_management, administration, facility_management

UMGESTUFT (3): sales, marketing, procurement -- jeweils normal -> high.
Alle drei verarbeiten regelmaessig personenbezogene Daten (Kundendaten,
Verteilerlisten, Lieferantenkontakte); "normal" war dafuer zu schwach.

BEWUSST NICHT geaendert: kein Code wird geloescht oder umbenannt. Bereiche
sind nach Inbetriebnahme unveraenderlich (siehe db_schema.py) -- sie werden
deaktiviert, nie entfernt. factoring, projects, tasks und company_knowledge
bleiben unveraendert bestehen.

ABGRENZUNG: Diese Migration erweitert ausschliesslich das Bereichs-
VOKABULAR. Sie schaltet keinen Bereich fuer einen Mandanten frei, vergibt
keine Mitgliedschaft und aendert keine Rechteprofile -- es bleibt
fail-closed bei "kein Zugriff", bis bootstrap_domain() ausdruecklich
aufgerufen wird.

KEINE Governance-Regel: Die Entscheidung "AILIZA gibt nur DSGVO-konforme
Daten heraus" wird NICHT hier umgesetzt. sensitivity_level ist eine
Einstufung, kein Durchsetzungsmechanismus -- die Durchsetzung liegt
unveraendert in der Governance-Pipeline (classify -> evaluate_policy ->
redact). Diese Migration liefert nur die Grundlage, auf die sich eine
spaetere Regel beziehen kann.

Revision ID: a4e8b2c15d97
Revises: f9a3c61e07b2
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a4e8b2c15d97"
down_revision: Union[str, None] = "f9a3c61e07b2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# (code, Anzeigename, Kategorie, Sensitivitaet)
_NEW_DOMAINS = [
    ("management", "Geschaeftsfuehrung", "governance", "confidential"),
    ("it_support", "IT-Support", "technology", "confidential"),
    ("research_development", "Forschung und Entwicklung", "innovation", "confidential"),
    ("operations", "Produktion und Betrieb", "delivery", "high"),
    ("logistics", "Logistik", "supply", "high"),
    ("customer_support", "Kundenservice", "market", "high"),
    ("quality_management", "Qualitaetsmanagement", "delivery", "high"),
    ("administration", "Verwaltung", "governance", "normal"),
    ("facility_management", "Facility Management", "delivery", "normal"),
]

# code -> (alte Stufe, neue Stufe). Die alte Stufe wird mitgeprueft, damit
# eine bereits von Hand angepasste Einstufung nicht ueberschrieben wird.
_RECLASSIFY = {
    "sales": ("normal", "high"),
    "marketing": ("normal", "high"),
    "procurement": ("normal", "high"),
}


class DomainVocabularyError(RuntimeError):
    """Vokabular-Migration konnte nicht sauber angewendet werden."""


def upgrade() -> None:
    bind = op.get_bind()
    now = datetime.now(timezone.utc)

    existing = {
        row[0]: row[1]
        for row in bind.execute(
            sa.text("SELECT code, sensitivity_level FROM business_domains")
        )
    }

    # 1. Fehlende Bereiche anlegen -- idempotent, vorhandene bleiben unberuehrt.
    for code, name, category, sensitivity in _NEW_DOMAINS:
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

    # 2. Drei Bereiche hoeher einstufen. Nur wenn sie noch auf dem
    # urspruenglichen Wert stehen -- eine abweichende Einstufung waere eine
    # bewusste Entscheidung und wird nicht ueberschrieben.
    for code, (old, new) in _RECLASSIFY.items():
        if existing.get(code) != old:
            continue
        bind.execute(
            sa.text(
                "UPDATE business_domains SET sensitivity_level = :new, "
                "updated_at = :now WHERE code = :code AND sensitivity_level = :old"
            ),
            {"code": code, "old": old, "new": new, "now": now},
        )

    # 3. Fail-closed pruefen: alle erwarteten Codes vorhanden?
    after = {
        row[0] for row in bind.execute(sa.text("SELECT code FROM business_domains"))
    }
    missing = {code for code, _, _, _ in _NEW_DOMAINS} - after
    if missing:
        raise DomainVocabularyError(
            f"Bereiche fehlen nach der Migration: {sorted(missing)}"
        )


def downgrade() -> None:
    """Entfernt NUR die neun in dieser Revision angelegten Bereiche und
    setzt die drei Einstufungen zurueck.

    Ein Bereich mit bereits vergebenen Mitgliedschaften oder Mandanten-
    Freischaltungen wird NICHT entfernt -- der Downgrade bricht dann
    kontrolliert ab, statt Zugriffsdaten stillschweigend zu verlieren."""
    bind = op.get_bind()
    now = datetime.now(timezone.utc)
    new_codes = [code for code, _, _, _ in _NEW_DOMAINS]

    in_use = bind.execute(
        sa.text(
            "SELECT bd.code FROM business_domains bd WHERE bd.code IN :codes AND ("
            " EXISTS (SELECT 1 FROM tenant_business_domains t WHERE t.domain_id = bd.id)"
            " OR EXISTS (SELECT 1 FROM user_domain_memberships m WHERE m.domain_id = bd.id)"
            " OR EXISTS (SELECT 1 FROM domain_role_permissions p WHERE p.domain_id = bd.id)"
            ")"
        ).bindparams(sa.bindparam("codes", expanding=True)),
        {"codes": new_codes},
    ).all()
    if in_use:
        raise DomainVocabularyError(
            "Downgrade abgelehnt: fuer diese Bereiche bestehen bereits "
            f"Freischaltungen oder Mitgliedschaften: {[r[0] for r in in_use]}. "
            "Bitte fachlich klaeren, statt Zugriffsdaten zu verwerfen."
        )

    bind.execute(
        sa.text("DELETE FROM business_domains WHERE code IN :codes").bindparams(
            sa.bindparam("codes", expanding=True)
        ),
        {"codes": new_codes},
    )
    for code, (old, new) in _RECLASSIFY.items():
        bind.execute(
            sa.text(
                "UPDATE business_domains SET sensitivity_level = :old, "
                "updated_at = :now WHERE code = :code AND sensitivity_level = :new"
            ),
            {"code": code, "old": old, "new": new, "now": now},
        )
