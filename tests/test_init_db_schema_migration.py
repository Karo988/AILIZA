"""Regressionstest fuer den init_db()-Doppel-Definitions-Bug.

Vorher: database.py definierte init_db() zweimal; die zweite (spaetere)
Definition ueberschrieb die erste und rief ensure_sqlite_schema() NIE auf.
Auf einer bestehenden SQLite-Datei ohne neuere Spalten (z. B. "version" aus
der serverseitigen Speicherung) fuehrte das beim Zugriff zu "no such column".
Dieser Test legt bewusst eine SQLite-Datei im ALTEN Schema (ohne version-Spalte)
an und prueft, dass ein frischer Prozess-Start (Modul-Import) die fehlende
Spalte automatisch nachzieht.
"""
import os
import sqlite3
import subprocess
import sys
import tempfile


def test_missing_version_column_is_migrated_on_fresh_import():
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "old_schema.db")
        con = sqlite3.connect(db_path)
        con.execute("""CREATE TABLE user_projects (
            id TEXT, tenant_id TEXT, user_id TEXT, name TEXT, description TEXT,
            priority TEXT, chat_id TEXT, files TEXT,
            created_at TEXT, updated_at TEXT, retention_until TEXT,
            PRIMARY KEY (id, tenant_id, user_id)
        )""")
        con.execute("""CREATE TABLE user_chats (
            id TEXT, tenant_id TEXT, user_id TEXT, project_id TEXT, title TEXT,
            messages TEXT, message_count INTEGER,
            created_at TEXT, updated_at TEXT, retention_until TEXT,
            PRIMARY KEY (id, tenant_id, user_id)
        )""")
        con.execute(
            "INSERT INTO user_projects VALUES "
            "('legacy1','default','karo','Alt-Projekt','alte Beschreibung',"
            "NULL,NULL,NULL,'2026-01-01','2026-01-01',NULL)"
        )
        con.commit()
        con.close()

        env = dict(os.environ)
        env["AILIZA_SECRET_KEY"] = "test-secret-key-minimum-32-chars-ok"
        env["AILIZA_DATABASE_URL"] = f"sqlite:///{db_path}"
        code = (
            "from apps.backend.database import list_user_projects\n"
            "rows = list_user_projects('default', 'karo')\n"
            "assert len(rows) == 1, rows\n"
            "assert rows[0]['version'] == 1, rows\n"
            "assert rows[0]['name'] == 'Alt-Projekt', rows\n"
            "print('OK')\n"
        )
        result = subprocess.run(
            [sys.executable, "-c", code],
            cwd=os.getcwd(), env=env, capture_output=True, text=True, timeout=30,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        assert "OK" in result.stdout

        con = sqlite3.connect(db_path)
        cols = {row[1] for row in con.execute("PRAGMA table_info(user_projects)")}
        con.close()
        assert "version" in cols


def test_init_db_defined_exactly_once():
    """Struktureller Schutz: init_db darf nur EINMAL definiert sein, sonst
    ueberschreibt eine zweite Definition wieder ensure_sqlite_schema()."""
    import inspect
    import apps.backend.database as db
    src = inspect.getsource(db)
    assert src.count("\ndef init_db(") == 1, "init_db ist mehr als einmal definiert"
