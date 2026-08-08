"""fix: fehlende Spalten auf Bestands-Postgres-DBs nachziehen (Drift-Fix)

Revision ID: c7e2f9a1b3d4
Revises: b4d3a1d0de71
Create Date: 2026-08-03

Hintergrund: Der alte Column-Patch-Mechanismus `ensure_sqlite_schema()` in
apps/backend/database.py hat fehlende Spalten frueher NUR auf SQLite
nachtraeglich ergaenzt (ALTER TABLE ... ADD COLUMN beim Start), niemals auf
PostgreSQL. Dadurch fehlen auf einer alten produktiven Postgres-DB diverse
Spalten, die in der Baseline-Migration 0001 (create_table) bzw. im aktuellen
db_schema.py (Quelle der Wahrheit) laengst Teil des Schemas sind.

Diese Migration ist rein additiv und pro Spalte idempotent: vor jedem
op.add_column() wird per sqlalchemy.inspect() geprueft, ob die Spalte
bereits existiert. Dadurch ist sie sicher sowohl fuer
  - alte Bestands-DBs (Spalte fehlt -> wird ergaenzt) als auch
  - frische DBs, die bereits ueber 0001+0002 korrekt angelegt wurden
    (Spalte existiert bereits -> add_column wird uebersprungen).

Abweichungen von der urspruenglichen 12er-Liste (gegen db_schema.py
verifiziert):
  - `user_chats.keep_uploaded_documents` und `user_chats.document_retention_days`
    sind in der Baseline 0001 bereits per create_table() enthalten (siehe
    db_schema.py Zeilen 524/525). Sie werden hier trotzdem idempotent
    mitgefuehrt (Verteidigung in der Tiefe fuer evtl. noch aeltere,
    VOR der Baseline entstandene Bestands-DBs), sind aber im Normalfall ein
    reines No-Op.
  - `agent_runs.run_id` existiert NICHT als Spaltenname in agent_runs
    (die Tabelle hat `id` als Primary Key, siehe db_schema.py Zeile 76) --
    wurde aus der Liste ENTFERNT. `run_id` als Spalte gibt es nur in
    `approval_requests` und `feedback` (beide bereits Teil der Baseline
    0001 und daher hier nicht nochmal noetig).

Damit enthaelt diese Migration final 11 add_column-Operationen (statt der
urspruenglich genannten 12): 9 echte Drift-Fixes + 2 defensive No-Ops fuer
user_chats.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "c7e2f9a1b3d4"
down_revision: Union[str, None] = "b4d3a1d0de71"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _existing_columns(table_name: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    return {col["name"] for col in inspector.get_columns(table_name)}


def _add_column_if_missing(table_name: str, column: sa.Column) -> None:
    if column.name not in _existing_columns(table_name):
        op.add_column(table_name, column)


# Spalten, die oben mit server_default ergaenzt werden. Das server_default ist
# NUR noetig, damit `ADD COLUMN ... NOT NULL` auf einer Tabelle mit bereits
# vorhandenen Zeilen ueberhaupt durchlaeuft (Postgres verlangt einen Wert fuer
# die Bestandszeilen). Danach wird es wieder entfernt -- sonst haette eine
# reparierte Datenbank dauerhaft eine DEFAULT-Klausel, die eine frisch aus
# Baseline 0001 erzeugte Datenbank NICHT hat (db_schema.py und 0001 verwenden
# bewusst kein server_default). Diese stille Abweichung wuerde von
# alembic_adopt.py nicht erkannt, da dort nur Spaltennamen und Nullability
# verglichen werden -- fuer die Zertifizierung ist "repariert == frisch"
# jedoch die verbindliche Anforderung.
_SERVER_DEFAULT_COLUMNS: tuple[tuple[str, str], ...] = (
    ("audit_logs", "tenant_id"),
    ("approval_requests", "tenant_id"),
    ("agent_runs", "tenant_id"),
    ("users", "failed_login_attempts"),
    ("user_projects", "version"),
    ("user_chats", "version"),
)


def _drop_server_defaults() -> None:
    """Entfernt die nur fuer den Backfill benoetigten DEFAULT-Klauseln wieder.

    Wird auf SQLite bewusst uebersprungen: SQLite kann eine DEFAULT-Klausel
    nicht per ALTER COLUMN entfernen, Alembic muesste dafuer die gesamte
    Tabelle neu aufbauen (batch_alter_table) -- ein unnoetiges Datenrisiko.
    Produktiv laeuft AILIZA auf PostgreSQL; dort ist der Schritt relevant und
    wird ausgefuehrt. Auf SQLite bleibt lediglich eine harmlose DEFAULT-Klausel
    zurueck, die das Verhalten der Anwendung nicht veraendert.
    """
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        return
    for table_name, column_name in _SERVER_DEFAULT_COLUMNS:
        if column_name in _existing_columns(table_name):
            op.alter_column(table_name, column_name, server_default=None)


def upgrade() -> None:
    # audit_logs.tenant_id
    _add_column_if_missing(
        "audit_logs",
        sa.Column("tenant_id", sa.String(64), nullable=False, server_default="default"),
    )

    # approval_requests.tenant_id / owner_user_id
    _add_column_if_missing(
        "approval_requests",
        sa.Column("tenant_id", sa.String(64), nullable=False, server_default="default"),
    )
    _add_column_if_missing(
        "approval_requests",
        sa.Column("owner_user_id", sa.String(64), nullable=True),
    )

    # agent_runs.tenant_id / owner_user_id
    _add_column_if_missing(
        "agent_runs",
        sa.Column("tenant_id", sa.String(64), nullable=False, server_default="default"),
    )
    _add_column_if_missing(
        "agent_runs",
        sa.Column("owner_user_id", sa.String(64), nullable=True),
    )

    # users.failed_login_attempts / locked_until
    _add_column_if_missing(
        "users",
        sa.Column("failed_login_attempts", sa.Integer(), nullable=False, server_default="0"),
    )
    _add_column_if_missing(
        "users",
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
    )

    # user_projects.version
    _add_column_if_missing(
        "user_projects",
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
    )

    # user_chats.version
    _add_column_if_missing(
        "user_chats",
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
    )

    # user_chats.keep_uploaded_documents / document_retention_days
    # (bereits Teil der Baseline 0001 -- hier nur defensiv/idempotent, siehe
    # Docstring oben. Im Normalfall ein No-Op.)
    _add_column_if_missing(
        "user_chats",
        sa.Column("keep_uploaded_documents", sa.Integer(), nullable=True),
    )
    _add_column_if_missing(
        "user_chats",
        sa.Column("document_retention_days", sa.Integer(), nullable=True),
    )

    # Die nur fuer den Backfill benoetigten DEFAULT-Klauseln wieder entfernen,
    # damit eine reparierte Datenbank strukturell identisch zu einer frisch
    # aus 0001 erzeugten Datenbank ist (siehe _drop_server_defaults()).
    _drop_server_defaults()

    # HINWEIS: "agent_runs.run_id" wurde bewusst NICHT aufgenommen -- diese
    # Spalte existiert unter diesem Namen nicht in agent_runs (siehe
    # Docstring oben). agent_runs.id ist bereits Primary Key seit 0001.


def downgrade() -> None:
    # Bewusst restriktiv: KEIN automatisches drop_column.
    #
    # Diese Migration behebt reinen Postgres-Drift (Spalten, die auf einer
    # Bestands-DB fehlten, aber im aktuellen Schema und auf frischen DBs
    # laengst regulaerer, dauerhafter Bestandteil sind -- siehe 0001 und
    # db_schema.py). Ein automatisches Zurueck-Droppen wuerde auf einer
    # DB, die diese Spalten bereits uebergangsweise befuellt hat (z.B.
    # tenant_id, owner_user_id, failed_login_attempts), zu echtem
    # Datenverlust fuehren -- und selbst dort, wo aktuell nur Defaults
    # stehen, widerspraeche ein Drop dem Ziel dieser Migration (Angleichung
    # an das Ist-Schema). Ein Downgrade dieser Revision ist daher ein
    # bewusstes No-Op; ein echter Rollback muesste manuell und mit voller
    # Kenntnis der jeweiligen Datenlage erfolgen.
    pass
