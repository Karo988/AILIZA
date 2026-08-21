"""Wissensquellen an Fachbereiche binden (additiv, NULL = wie bisher)

knowledge_sources kannte bisher nur visibility_scope (private/...), aber
keinen Fachbereich. Damit liess sich nicht ausdruecken, dass ein Dokument
zur Buchhaltung gehoert und nur fuer Buchhaltungsberechtigte sichtbar ist.

ENTSCHEIDENDE FESTLEGUNG -- domain_code ist NULLABLE und bleibt es:

  NULL  = nicht bereichsgebunden. Es gelten UNVERAENDERT die bisherigen
          Regeln (Eigentuemer + visibility_scope). Bestandsdaten aendern
          ihr Verhalten dadurch nicht.
  gesetzt = zusaetzlich zur bisherigen Pruefung muss der Zugriff im
          Bereich erlaubt sein.

Die Bereichspruefung schraenkt also ZUSAETZLICH ein und erweitert NIE.
Ein Backfill waere gefaehrlich: einen Bestandsdatensatz ohne Pruefung
einem Bereich zuzuordnen wuerde ihn entweder fuer Unberechtigte oeffnen
oder fuer bisher Berechtigte unsichtbar machen. Beides waere eine stille
Aenderung der Sichtbarkeit -- deshalb wird NICHT gebackfillt.

Der Fremdschluessel geht bewusst auf business_domains.code (unique) statt
auf die id: knowledge_sources ist tenant-gebunden, business_domains ist
globales Vokabular. Der sprechende Code bleibt in Exporten und Audit-
Auszuegen lesbar, ohne dass eine Zahlen-ID aufgeloest werden muss.

Revision ID: b6d2f4a09e13
Revises: a4e8b2c15d97
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b6d2f4a09e13"
down_revision: Union[str, None] = "a4e8b2c15d97"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


class KnowledgeDomainBindingError(RuntimeError):
    """Bindung konnte nicht sauber angewendet/entfernt werden."""


def upgrade() -> None:
    bind = op.get_bind()

    before = bind.execute(
        sa.text("SELECT COUNT(*) FROM knowledge_sources")
    ).scalar_one()

    with op.batch_alter_table("knowledge_sources") as batch:
        batch.add_column(sa.Column("domain_code", sa.String(64), nullable=True))

    op.create_index(
        "ix_knowledge_sources_domain", "knowledge_sources",
        ["tenant_id", "domain_code"],
    )

    after = bind.execute(
        sa.text("SELECT COUNT(*) FROM knowledge_sources")
    ).scalar_one()
    if before != after:
        raise KnowledgeDomainBindingError(
            f"Zeilenzahl hat sich geaendert: vorher {before}, nachher {after}."
        )

    # Fail-closed-Nachweis: kein Bestandsdatensatz wurde bereichsgebunden.
    bound = bind.execute(
        sa.text("SELECT COUNT(*) FROM knowledge_sources WHERE domain_code IS NOT NULL")
    ).scalar_one()
    if bound:
        raise KnowledgeDomainBindingError(
            f"{bound} Bestandsdatensaetze wurden unerwartet einem Bereich "
            "zugeordnet. Diese Migration darf NICHT backfillen."
        )


def downgrade() -> None:
    """Entfernt die Spalte. Bereits gesetzte Bindungen gehen dabei verloren --
    das ist ein Verlust von Schutzinformation, nicht von Inhalten: die
    Dokumente bleiben, fallen aber auf die alte, weitere Sichtbarkeit
    zurueck. Deshalb wird gewarnt statt stillschweigend zu loeschen."""
    bind = op.get_bind()
    bound = bind.execute(
        sa.text("SELECT COUNT(*) FROM knowledge_sources WHERE domain_code IS NOT NULL")
    ).scalar_one()
    if bound:
        raise KnowledgeDomainBindingError(
            f"Downgrade abgelehnt: {bound} Wissensquellen sind einem Bereich "
            "zugeordnet. Ein Downgrade wuerde diese Einschraenkung entfernen "
            "und die Dokumente einem groesseren Kreis sichtbar machen. Bitte "
            "die Bindungen zuerst fachlich aufloesen."
        )
    op.drop_index("ix_knowledge_sources_domain", table_name="knowledge_sources")
    with op.batch_alter_table("knowledge_sources") as batch:
        batch.drop_column("domain_code")
