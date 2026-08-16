"""Knowledge Phase 1 -- Migration c8ff9bb332ba, PostgreSQL-Aequivalente.

Laeuft NUR, wenn AILIZA_TEST_POSTGRES_ADMIN_URL gesetzt ist -- eine
Verbindung mit CREATEDB-Recht auf eine LOKALE/ISOLIERTE Testinstanz,
NIEMALS Render/Neon. Ohne diese Variable werden die Tests uebersprungen
(auch in CI ohne PostgreSQL-Service) -- exakt dasselbe Muster wie
tests/test_memory_audit_cli.py (dort ausfuehrlicher begruendet)."""
from __future__ import annotations

import contextlib
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = REPO_ROOT / "apps" / "backend"
PARENT_REVISION = "3c5757ab05f2"
TARGET_REVISION = "c8ff9bb332ba"

_PG_ADMIN_URL = os.environ.get("AILIZA_TEST_POSTGRES_ADMIN_URL")

pg_only = pytest.mark.skipif(
    not _PG_ADMIN_URL,
    reason="AILIZA_TEST_POSTGRES_ADMIN_URL nicht gesetzt -- PostgreSQL-Tests "
    "laufen nur explizit gegen eine lokale/isolierte Testinstanz.",
)


@contextlib.contextmanager
def _fresh_postgres_database(name: str):
    import psycopg

    admin = psycopg.connect(_PG_ADMIN_URL.replace("postgresql+psycopg://", "postgresql://"))
    admin.autocommit = True
    try:
        with admin.cursor() as cur:
            cur.execute(f'DROP DATABASE IF EXISTS "{name}"')
            cur.execute(f'CREATE DATABASE "{name}"')
        parts = urlsplit(_PG_ADMIN_URL)
        db_url = urlunsplit(parts._replace(path=f"/{name}"))
        try:
            yield db_url
        finally:
            with admin.cursor() as cur:
                cur.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
    finally:
        admin.close()


def _run_alembic(*args: str, database_url: str) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["AILIZA_SECRET_KEY"] = "test-secret-key-minimum-32-chars-ok"
    env["AILIZA_DATABASE_URL"] = database_url
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=str(BACKEND_DIR), env=env, capture_output=True, text=True, timeout=60,
    )


def _pg_conn(db_url: str):
    import psycopg
    return psycopg.connect(db_url.replace("postgresql+psycopg://", "postgresql://"))


@pg_only
def test_postgres_fresh_database_upgrade_head_succeeds():
    with _fresh_postgres_database("ailiza_kp1_fresh") as db_url:
        result = _run_alembic("upgrade", "head", database_url=db_url)
        assert result.returncode == 0, result.stderr
        con = _pg_conn(db_url)
        cur = con.cursor()
        cur.execute("SELECT version_num FROM alembic_version")
        assert cur.fetchone()[0] == TARGET_REVISION
        cur.execute(
            "SELECT is_nullable FROM information_schema.columns "
            "WHERE table_name='memory_items' AND column_name='tenant_id'"
        )
        assert cur.fetchone()[0] == "NO"
        con.close()


@pg_only
def test_postgres_existing_valid_data_migrates_without_loss():
    with _fresh_postgres_database("ailiza_kp1_valid") as db_url:
        result = _run_alembic("upgrade", PARENT_REVISION, database_url=db_url)
        assert result.returncode == 0, result.stderr
        con = _pg_conn(db_url)
        now = datetime.now(timezone.utc)
        con.cursor().execute(
            "INSERT INTO memory_items (tenant_id, scope, owner_user_id, title, content, "
            "purpose, status, created_at, updated_at) "
            "VALUES ('tenant-a', 'user_memory', 'alice', 't', 'c', 'p', 'active', %s, %s)",
            (now, now),
        )
        con.commit()
        con.close()

        result = _run_alembic("upgrade", "head", database_url=db_url)
        assert result.returncode == 0, result.stderr
        con = _pg_conn(db_url)
        cur = con.cursor()
        cur.execute("SELECT tenant_id, title, content FROM memory_items")
        assert cur.fetchall() == [("tenant-a", "t", "c")]
        con.close()


@pg_only
def test_postgres_null_tenant_legacy_row_blocks_upgrade():
    with _fresh_postgres_database("ailiza_kp1_nullrow") as db_url:
        result = _run_alembic("upgrade", PARENT_REVISION, database_url=db_url)
        assert result.returncode == 0, result.stderr
        con = _pg_conn(db_url)
        now = datetime.now(timezone.utc)
        con.cursor().execute(
            "INSERT INTO memory_items (tenant_id, scope, owner_user_id, title, content, "
            "purpose, status, created_at, updated_at) "
            "VALUES (NULL, 'user_memory', 'alice', 't', 'c', 'p', 'active', %s, %s)",
            (now, now),
        )
        con.commit()
        con.close()

        result = _run_alembic("upgrade", "head", database_url=db_url)
        assert result.returncode != 0
        assert "MemoryTenantIdMigrationBlocked" in result.stderr or "abgebrochen" in result.stderr

        con = _pg_conn(db_url)
        cur = con.cursor()
        cur.execute("SELECT version_num FROM alembic_version")
        assert cur.fetchone()[0] == PARENT_REVISION
        cur.execute("SELECT count(*) FROM memory_items")
        assert cur.fetchone()[0] == 1
        con.close()


@pg_only
def test_postgres_direct_null_insert_rejected_after_migration():
    """Direkter DB-Beweis (Auftrag Abschnitt 12/20): PostgreSQL selbst weist
    einen NULL-Insert zurueck, nicht nur die Python-Schicht."""
    with _fresh_postgres_database("ailiza_kp1_directnull") as db_url:
        result = _run_alembic("upgrade", "head", database_url=db_url)
        assert result.returncode == 0, result.stderr
        con = _pg_conn(db_url)
        now = datetime.now(timezone.utc)
        with pytest.raises(Exception) as exc_info:
            con.cursor().execute(
                "INSERT INTO memory_items (tenant_id, scope, owner_user_id, title, content, "
                "purpose, status, created_at, updated_at) "
                "VALUES (NULL, 'user_memory', 'bob', 't', 'c', 'p', 'active', %s, %s)",
                (now, now),
            )
        assert "not-null constraint" in str(exc_info.value).lower() or "null value" in str(exc_info.value).lower()
        con.close()


@pg_only
def test_postgres_downgrade_then_reupgrade_preserves_data():
    with _fresh_postgres_database("ailiza_kp1_roundtrip") as db_url:
        result = _run_alembic("upgrade", PARENT_REVISION, database_url=db_url)
        assert result.returncode == 0, result.stderr
        con = _pg_conn(db_url)
        now = datetime.now(timezone.utc)
        con.cursor().execute(
            "INSERT INTO memory_items (tenant_id, scope, owner_user_id, title, content, "
            "purpose, status, created_at, updated_at) "
            "VALUES ('tenant-a', 'user_memory', 'alice', 't', 'c', 'p', 'active', %s, %s)",
            (now, now),
        )
        con.commit()
        con.close()
        result = _run_alembic("upgrade", "head", database_url=db_url)
        assert result.returncode == 0, result.stderr

        result = _run_alembic("downgrade", "-1", database_url=db_url)
        assert result.returncode == 0, result.stderr
        con = _pg_conn(db_url)
        cur = con.cursor()
        cur.execute(
            "SELECT is_nullable FROM information_schema.columns "
            "WHERE table_name='memory_items' AND column_name='tenant_id'"
        )
        assert cur.fetchone()[0] == "YES"
        cur.execute("SELECT tenant_id, title FROM memory_items")
        assert cur.fetchall() == [("tenant-a", "t")]
        con.close()

        result = _run_alembic("upgrade", "head", database_url=db_url)
        assert result.returncode == 0, result.stderr
        con = _pg_conn(db_url)
        cur = con.cursor()
        cur.execute(
            "SELECT is_nullable FROM information_schema.columns "
            "WHERE table_name='memory_items' AND column_name='tenant_id'"
        )
        assert cur.fetchone()[0] == "NO"
        cur.execute("SELECT tenant_id, title FROM memory_items")
        assert cur.fetchall() == [("tenant-a", "t")]
        con.close()
