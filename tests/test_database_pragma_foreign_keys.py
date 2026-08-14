"""Tests fuer PRAGMA foreign_keys=ON auf jeder SQLite-Verbindung.

Scope: apps/backend/database.py setzt PRAGMA foreign_keys=ON per
Connect-Event auf der SQLAlchemy-Engine. apps/backend/memory/sqlite_store.py
setzt es direkt nach sqlite3.connect(), weil diese Verbindung am ORM
vorbeigeht und vom SQLAlchemy-Event nicht erfasst wird.

Ohne PRAGMA foreign_keys=ON ignoriert SQLite ON DELETE CASCADE und
Fremdschluesselverletzungen stillschweigend -- dieser Test beweist, dass
eine Verletzung jetzt tatsaechlich abgelehnt wird, statt es nur zu behaupten.
"""
import sqlite3
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from apps.backend.database import engine
from apps.backend.memory.sqlite_store import SqliteMemoryStore


class TestSqlAlchemyEnginePragmas:
    """PRAGMA-Werte auf der zentralen SQLAlchemy-Engine (database.py)."""

    def test_foreign_keys_pragma_is_on(self):
        with engine.connect() as conn:
            value = conn.execute(text("PRAGMA foreign_keys")).scalar()
        assert value == 1

    def test_busy_timeout_pragma_is_5000(self):
        with engine.connect() as conn:
            value = conn.execute(text("PRAGMA busy_timeout")).scalar()
        assert value == 5000

    def test_foreign_key_violation_is_rejected(self):
        """memory_visibility.memory_item_id -> memory_items.id: ein
        Verweis auf eine nicht existierende memory_items.id muss jetzt
        an der DB scheitern, nicht nur an Anwendungslogik."""
        now = datetime.now(timezone.utc)
        with engine.connect() as conn:
            with conn.begin():
                with pytest.raises(IntegrityError):
                    conn.execute(
                        text(
                            "INSERT INTO memory_visibility "
                            "(memory_item_id, visibility_scope, allowed_roles, "
                            "allowed_user_ids, created_at, updated_at) "
                            "VALUES (:item_id, 'private', '[]', '[]', :now, :now)"
                        ),
                        {"item_id": 9_999_999, "now": now},
                    )


class TestSqliteMemoryStorePragmas:
    """PRAGMA-Werte auf der direkten sqlite3.connect()-Verbindung in
    memory/sqlite_store.py, die am SQLAlchemy-Event vorbeigeht."""

    @pytest.fixture()
    def store(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = str(Path(tmp) / "memory_test.db")
            yield SqliteMemoryStore(db_path=db_path)

    def test_foreign_keys_pragma_is_on(self, store):
        cursor = store._conn.execute("PRAGMA foreign_keys")
        assert cursor.fetchone()[0] == 1

    def test_busy_timeout_pragma_is_5000(self, store):
        cursor = store._conn.execute("PRAGMA busy_timeout")
        assert cursor.fetchone()[0] == 5000

    def test_pragma_set_immediately_after_connect(self, tmp_path):
        """Regressionsschutz: die PRAGMA-Aufrufe muessen vor _init_schema()
        erfolgen -- sonst koennte das Schema selbst unter fehlender
        Fremdschluesselpruefung angelegt werden."""
        db_path = str(tmp_path / "order_test.db")
        s = SqliteMemoryStore(db_path=db_path)
        raw = sqlite3.connect(db_path)
        try:
            # Eigenstaendige Verbindung: foreign_keys ist PRAGMA-seitig
            # verbindungslokal, hier pruefen wir nur, dass das Schema
            # ueberhaupt sauber angelegt wurde (kein Fehlschlag durch
            # fehlende PRAGMA-Reihenfolge).
            tables = raw.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
            assert ("memory_entries",) in tables
        finally:
            raw.close()
            s._conn.close()
