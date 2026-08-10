"""fix: user_chats-Dokumenten-Aufbewahrungsspalten per Migration nachziehen

Revision ID: f3c9a1e7d2b4
Revises: e1a7c3f92b56
Create Date: 2026-08-10

Hintergrund (Nachpruefung Phase-1-Handoff, Teil 2 der Matrix): die Spalten
`user_chats.keep_uploaded_documents` und `user_chats.document_retention_days`
existieren seit ihrer Einfuehrung (Karo-Entscheidung 2026-08-03) NUR in
apps/backend/db_schema.py und werden ausschliesslich durch
ensure_sqlite_schema() (apps/backend/database.py) zur Laufzeit nachgezogen --
und die beginnt mit `if not DATABASE_URL.startswith("sqlite"): return`.
Fuer PostgreSQL gibt es KEINEN Nachziehweg; fuer SQLite laeuft der Patch nur
ueber init_db(), nicht ueber `alembic upgrade head`. Eine per Alembic (nicht
per init_db()) verwaltete Datenbank -- z.B. eine adoptierte 0001-Alt-
Datenbank, die danach nur noch per `alembic upgrade head` aktualisiert wird --
bekommt diese zwei Spalten nie. Reine additive Migration, keine Datenaenderung
an bestehenden Zeilen (beide Spalten nullable, Default bleibt NULL =
Systemstandard, siehe database.get_chat_document_retention()).
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "f3c9a1e7d2b4"
down_revision: Union[str, None] = "e1a7c3f92b56"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("user_chats", sa.Column("keep_uploaded_documents", sa.Integer(), nullable=True))
    op.add_column("user_chats", sa.Column("document_retention_days", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("user_chats", "document_retention_days")
    op.drop_column("user_chats", "keep_uploaded_documents")
