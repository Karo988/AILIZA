"""Tests für Migration 0006 (Teil 2 des Nachprüfungs-Handoffs):
user_chats.keep_uploaded_documents / document_retention_days müssen über
`alembic upgrade head` nachgezogen werden -- vorher gab es dafür KEINE
Migration, nur den SQLite-spezifischen Laufzeit-Patch ensure_sqlite_schema(),
der für PostgreSQL nie greift.

Läuft ausschließlich gegen temporäre SQLite-Dateien, nie gegen eine echte
AILIZA-Datenbank.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = REPO_ROOT / "apps" / "backend"


def _run_alembic(*args: str, db_url: str) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env["AILIZA_DATABASE_URL"] = db_url
    return subprocess.run(
        [sys.executable, "-m", "alembic", "-c", "alembic.ini", *args],
        cwd=BACKEND_DIR, env=env, capture_output=True, text=True, timeout=60,
    )


def _table_columns(db_path: Path, table: str) -> set[str]:
    import sqlite3
    con = sqlite3.connect(db_path)
    try:
        return {r[1] for r in con.execute(f"PRAGMA table_info({table})")}
    finally:
        con.close()


def test_columns_missing_before_0006(tmp_path):
    db_path = tmp_path / "before.sqlite"
    db_url = f"sqlite:///{db_path}"
    result = _run_alembic("upgrade", "e1a7c3f92b56", db_url=db_url)
    assert result.returncode == 0, result.stderr

    cols = _table_columns(db_path, "user_chats")
    assert "keep_uploaded_documents" not in cols
    assert "document_retention_days" not in cols


def test_columns_added_by_0006_without_data_loss(tmp_path):
    db_path = tmp_path / "with_data.sqlite"
    db_url = f"sqlite:///{db_path}"
    result = _run_alembic("upgrade", "e1a7c3f92b56", db_url=db_url)
    assert result.returncode == 0, result.stderr

    import sqlite3
    con = sqlite3.connect(db_path)
    con.execute(
        "INSERT INTO user_chats (id, tenant_id, user_id, messages, message_count, created_at, updated_at, version) "
        "VALUES ('chat-1', 'default', 'user-1', '[]', 0, '2025-01-01T00:00:00+00:00', '2025-01-01T00:00:00+00:00', 1)"
    )
    con.commit()
    con.close()

    result = _run_alembic("upgrade", "head", db_url=db_url)
    assert result.returncode == 0, result.stderr

    cols = _table_columns(db_path, "user_chats")
    assert "keep_uploaded_documents" in cols
    assert "document_retention_days" in cols

    con = sqlite3.connect(db_path)
    assert con.execute("SELECT COUNT(*) FROM user_chats").fetchone()[0] == 1
    assert con.execute("SELECT id FROM user_chats").fetchone()[0] == "chat-1"
    con.close()


def test_downgrade_removes_columns_without_data_loss(tmp_path):
    db_path = tmp_path / "downgrade.sqlite"
    db_url = f"sqlite:///{db_path}"
    result = _run_alembic("upgrade", "head", db_url=db_url)
    assert result.returncode == 0, result.stderr

    import sqlite3
    con = sqlite3.connect(db_path)
    con.execute(
        "INSERT INTO user_chats (id, tenant_id, user_id, messages, message_count, created_at, updated_at, version) "
        "VALUES ('chat-1', 'default', 'user-1', '[]', 0, '2025-01-01T00:00:00+00:00', '2025-01-01T00:00:00+00:00', 1)"
    )
    con.commit()
    con.close()

    result = _run_alembic("downgrade", "e1a7c3f92b56", db_url=db_url)
    assert result.returncode == 0, result.stderr

    cols = _table_columns(db_path, "user_chats")
    assert "keep_uploaded_documents" not in cols
    assert "document_retention_days" not in cols

    con = sqlite3.connect(db_path)
    assert con.execute("SELECT COUNT(*) FROM user_chats").fetchone()[0] == 1
    con.close()
