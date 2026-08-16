"""Knowledge Phase 1 -- Migration c8ff9bb332ba (memory_items.tenant_id NOT NULL).

Ruft wie tests/test_database_migrations.py die echte `alembic`-CLI als
Subprozess auf (kein Mocking). SQLite hier; PostgreSQL-Aequivalente siehe
tests/test_memory_tenant_migration_postgres.py (pg_only, nur mit
AILIZA_TEST_POSTGRES_ADMIN_URL, analog tests/test_memory_audit_cli.py)."""
from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = REPO_ROOT / "apps" / "backend"
PARENT_REVISION = "3c5757ab05f2"
TARGET_REVISION = "c8ff9bb332ba"


def _run_alembic(*args: str, database_url: str) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["AILIZA_SECRET_KEY"] = "test-secret-key-minimum-32-chars-ok"
    env["AILIZA_DATABASE_URL"] = database_url
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=str(BACKEND_DIR), env=env, capture_output=True, text=True, timeout=60,
    )


def _insert_memory_item(db_path: Path, *, tenant_id) -> None:
    con = sqlite3.connect(db_path)
    now = datetime.now(timezone.utc).isoformat()
    con.execute(
        "INSERT INTO memory_items (tenant_id, scope, owner_user_id, title, content, "
        "purpose, status, created_at, updated_at) "
        "VALUES (?, 'user_memory', 'alice', 't', 'c', 'p', 'active', ?, ?)",
        (tenant_id, now, now),
    )
    con.commit()
    con.close()


def test_exactly_one_alembic_head():
    """Auftrag Sicherheitsstopp-Kriterium: mehr als ein Head ist nicht
    zulaessig. Muss nach der neuen Revision weiterhin genau einer sein."""
    result = _run_alembic("heads", database_url="sqlite:///:memory:")
    assert result.returncode == 0, result.stderr
    heads = [line for line in result.stdout.splitlines() if line.strip()]
    assert len(heads) == 1, f"Erwartet genau einen Alembic-Head, gefunden: {heads}"
    assert TARGET_REVISION in heads[0]


def test_fresh_database_upgrade_head_succeeds(tmp_path):
    db_path = tmp_path / "fresh.db"
    result = _run_alembic("upgrade", "head", database_url=f"sqlite:///{db_path}")
    assert result.returncode == 0, result.stderr

    con = sqlite3.connect(db_path)
    assert con.execute("SELECT version_num FROM alembic_version").fetchone()[0] == TARGET_REVISION
    cols = {row[1]: row[3] for row in con.execute("PRAGMA table_info(memory_items)").fetchall()}
    assert cols["tenant_id"] == 1, "tenant_id muss NOT NULL sein (PRAGMA table_info notnull=1)"
    assert con.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    assert con.execute("PRAGMA foreign_key_check").fetchall() == []
    indexes = {row[0] for row in con.execute(
        "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='memory_items'"
    ).fetchall()}
    assert {"ix_memory_items_owner", "ix_memory_items_tenant_status"} <= indexes


def test_existing_database_with_valid_data_migrates_without_loss(tmp_path):
    db_path = tmp_path / "valid.db"
    db_url = f"sqlite:///{db_path}"
    result = _run_alembic("upgrade", PARENT_REVISION, database_url=db_url)
    assert result.returncode == 0, result.stderr
    _insert_memory_item(db_path, tenant_id="tenant-a")

    result = _run_alembic("upgrade", "head", database_url=db_url)
    assert result.returncode == 0, result.stderr

    con = sqlite3.connect(db_path)
    rows = con.execute("SELECT tenant_id, title, content FROM memory_items").fetchall()
    assert rows == [("tenant-a", "t", "c")]
    assert con.execute("SELECT version_num FROM alembic_version").fetchone()[0] == TARGET_REVISION


def test_existing_database_with_null_tenant_legacy_row_blocks_upgrade(tmp_path):
    """Kernnachweis (fail-closed): eine bestehende Zeile ohne Tenant darf
    die Migration nicht durchlaufen -- kein Backfill, keine Loeschung,
    Revision bleibt auf dem alten Stand."""
    db_path = tmp_path / "legacy_null.db"
    db_url = f"sqlite:///{db_path}"
    result = _run_alembic("upgrade", PARENT_REVISION, database_url=db_url)
    assert result.returncode == 0, result.stderr
    _insert_memory_item(db_path, tenant_id=None)

    result = _run_alembic("upgrade", "head", database_url=db_url)
    assert result.returncode != 0, "Migration haette bei NULL-Tenant-Altdaten abbrechen muessen"
    assert "MemoryTenantIdMigrationBlocked" in result.stderr or "abgebrochen" in result.stderr

    con = sqlite3.connect(db_path)
    assert con.execute("SELECT version_num FROM alembic_version").fetchone()[0] == PARENT_REVISION, (
        "Revision darf bei abgebrochener Migration NICHT auf den neuen Stand gestempelt sein"
    )
    assert con.execute("SELECT count(*) FROM memory_items").fetchone()[0] == 1, (
        "Die problematische Zeile darf nicht geloescht worden sein"
    )


def test_downgrade_then_reupgrade_preserves_data(tmp_path):
    db_path = tmp_path / "roundtrip.db"
    db_url = f"sqlite:///{db_path}"
    result = _run_alembic("upgrade", PARENT_REVISION, database_url=db_url)
    assert result.returncode == 0, result.stderr
    _insert_memory_item(db_path, tenant_id="tenant-a")
    result = _run_alembic("upgrade", "head", database_url=db_url)
    assert result.returncode == 0, result.stderr

    result = _run_alembic("downgrade", "-1", database_url=db_url)
    assert result.returncode == 0, result.stderr
    con = sqlite3.connect(db_path)
    cols = {row[1]: row[3] for row in con.execute("PRAGMA table_info(memory_items)").fetchall()}
    assert cols["tenant_id"] == 0, "nach Downgrade muss tenant_id wieder nullable sein"
    assert con.execute("SELECT tenant_id, title FROM memory_items").fetchall() == [("tenant-a", "t")]
    con.close()

    result = _run_alembic("upgrade", "head", database_url=db_url)
    assert result.returncode == 0, result.stderr
    con = sqlite3.connect(db_path)
    cols = {row[1]: row[3] for row in con.execute("PRAGMA table_info(memory_items)").fetchall()}
    assert cols["tenant_id"] == 1
    assert con.execute("SELECT tenant_id, title FROM memory_items").fetchall() == [("tenant-a", "t")]
    assert con.execute("SELECT version_num FROM alembic_version").fetchone()[0] == TARGET_REVISION
