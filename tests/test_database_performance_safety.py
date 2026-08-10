"""Tests für die Performance-/Sicherheits-Ergänzungen aus Paket
fix/database-performance-safety: neue Indizes (db_schema.py + Alembic-
Migration 0004), WAL-Modus, busy_timeout.

Läuft ausschließlich gegen temporäre SQLite-Dateien, nie gegen eine echte
AILIZA-Datenbank.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from sqlalchemy import create_engine

REPO_ROOT = Path(__file__).resolve().parent.parent
ALEMBIC_INI = REPO_ROOT / "apps" / "backend" / "alembic.ini"


def _pragma_indexes(engine, table: str) -> set[str]:
    with engine.begin() as conn:
        rows = conn.exec_driver_sql(f"PRAGMA index_list({table})").all()
    return {row[1] for row in rows}


# WICHTIG: apps.backend.database ist ein fuer die GESAMTE Pytest-Session
# geteiltes Singleton-Modul (eine Engine, ein StaticPool). Ein
# importlib.reload() dieses Moduls im selben Prozess ersetzt diese geteilte
# Engine dauerhaft fuer alle NACH diesem Test laufenden Dateien -- das hat
# in einer frueheren Fassung dieser Datei zu 150+ Fehlschlaegen in voellig
# unabhaengigen Testdateien gefuehrt (sqlalchemy.exc.IntegrityError: UNIQUE
# constraint failed: users.user_id, reproduzierbar in Kombination mit z.B.
# test_user_settings.py). Jeder Test, der eine eigene AILIZA_DATABASE_URL
# braucht, laeuft deshalb als eigener Subprozess -- eigener Prozessraum,
# eigenes frisches Modul, keine Beruehrung der Test-Session.
_ENGINE_CHECK_SNIPPET = """
import sys
sys.path.insert(0, {repo_root!r})
import apps.backend.database as db
db.init_db()
with db.engine.begin() as conn:
    print("JOURNAL_MODE=" + str(conn.exec_driver_sql("PRAGMA journal_mode").scalar()))
    print("BUSY_TIMEOUT=" + str(conn.exec_driver_sql("PRAGMA busy_timeout").scalar()))
    for table in ("audit_logs", "approval_requests", "agent_runs"):
        rows = conn.exec_driver_sql(f"PRAGMA index_list({{table}})").all()
        names = ",".join(sorted(row[1] for row in rows))
        print(f"INDEXES_{{table}}=" + names)
"""


def _run_engine_check(db_url: str) -> dict[str, str]:
    env = os.environ.copy()
    env["AILIZA_DATABASE_URL"] = db_url
    code = _ENGINE_CHECK_SNIPPET.format(repo_root=str(REPO_ROOT))
    r = subprocess.run(
        [sys.executable, "-c", code],
        cwd=REPO_ROOT, env=env, capture_output=True, text=True, timeout=60,
    )
    assert r.returncode == 0, r.stderr
    result: dict[str, str] = {}
    for line in r.stdout.splitlines():
        if "=" in line:
            key, _, value = line.partition("=")
            result[key] = value
    return result


def test_fresh_database_has_new_indexes(tmp_path):
    """create_all() auf einer frischen Datenbank muss die neuen Indizes
    aus db_schema.py sofort enthalten (kein Migrationslauf nötig)."""
    db_path = tmp_path / "fresh.sqlite"
    out = _run_engine_check(f"sqlite:///{db_path}")

    assert "ix_audit_logs_tenant_timestamp" in out["INDEXES_audit_logs"]
    assert "ix_audit_logs_action" in out["INDEXES_audit_logs"]
    assert "ix_approval_requests_status" in out["INDEXES_approval_requests"]
    assert "ix_approval_requests_tenant_created" in out["INDEXES_approval_requests"]
    assert "ix_agent_runs_status" in out["INDEXES_agent_runs"]
    assert "ix_agent_runs_tenant_updated" in out["INDEXES_agent_runs"]


def test_wal_mode_enabled_for_file_database(tmp_path):
    """Datei-basierte SQLite-DB muss im WAL-Journal-Modus laufen."""
    db_path = tmp_path / "wal_check.sqlite"
    out = _run_engine_check(f"sqlite:///{db_path}")
    assert out["JOURNAL_MODE"].lower() == "wal"


def test_busy_timeout_set(tmp_path):
    db_path = tmp_path / "timeout_check.sqlite"
    out = _run_engine_check(f"sqlite:///{db_path}")
    assert out["BUSY_TIMEOUT"] == "5000"


def test_memory_database_does_not_break_on_wal_pragma():
    """WAL wird für :memory:-Datenbanken bewusst übersprungen (SQLite
    ignoriert es dort ohnehin) -- init_db() darf trotzdem nicht scheitern."""
    out = _run_engine_check("sqlite:///:memory:")
    assert out["BUSY_TIMEOUT"] == "5000"


def test_existing_database_migration_adds_indexes_without_data_loss(tmp_path):
    """Eine bestehende (bereits mit Daten gefüllte) Datenbank auf Stand 0002
    muss durch `alembic upgrade head` die neuen Indizes bekommen, OHNE
    vorhandene Zeilen zu verändern oder zu verlieren."""
    db_path = tmp_path / "existing.sqlite"
    db_url = f"sqlite:///{db_path}"

    # 1. Bestehende Datenbank auf Stand 0002 simulieren: Tabellen anlegen,
    #    eine Zeile je betroffener Tabelle einfügen, dann NUR bis 0002
    #    stempeln (ohne die neuen Indizes).
    env = os.environ.copy()
    env["AILIZA_DATABASE_URL"] = db_url
    subprocess.run(
        [sys.executable, "-m", "alembic", "-c", str(ALEMBIC_INI), "upgrade", "b4d3a1d0de71"],
        cwd=REPO_ROOT / "apps" / "backend", env=env, check=True, capture_output=True, text=True, timeout=60,
    )

    engine = create_engine(db_url)
    with engine.begin() as conn:
        conn.exec_driver_sql(
            "INSERT INTO audit_logs (timestamp, action, metadata, tenant_id, previous_hash, entry_hash) "
            "VALUES ('2026-01-01T00:00:00+00:00', 'test.action', '{}', 'default', '00', '11')"
        )
        conn.exec_driver_sql(
            "INSERT INTO approval_requests (created_at, tool, input_params, risk_level, risk_reason, status, tenant_id) "
            "VALUES ('2026-01-01T00:00:00+00:00', 'llm_call', '{}', 'high', 'test', 'pending', 'default')"
        )
        conn.exec_driver_sql(
            "INSERT INTO agent_runs (id, created_at, updated_at, task, status, run_metadata, tenant_id) "
            "VALUES ('run-1', '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00', 'test', 'done', '{}', 'default')"
        )
    engine.dispose()

    # 2. Migration ausführen
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "-c", str(ALEMBIC_INI), "upgrade", "head"],
        cwd=REPO_ROOT / "apps" / "backend", env=env, check=True, capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0, result.stderr

    # 3. Indizes vorhanden UND Daten unverändert
    engine = create_engine(db_url)
    assert "ix_audit_logs_tenant_timestamp" in _pragma_indexes(engine, "audit_logs")
    assert "ix_approval_requests_status" in _pragma_indexes(engine, "approval_requests")
    assert "ix_agent_runs_status" in _pragma_indexes(engine, "agent_runs")

    with engine.begin() as conn:
        assert conn.exec_driver_sql("SELECT COUNT(*) FROM audit_logs").scalar() == 1
        assert conn.exec_driver_sql("SELECT action FROM audit_logs").scalar() == "test.action"
        assert conn.exec_driver_sql("SELECT COUNT(*) FROM approval_requests").scalar() == 1
        assert conn.exec_driver_sql("SELECT COUNT(*) FROM agent_runs").scalar() == 1
        assert conn.exec_driver_sql("SELECT status FROM agent_runs WHERE id='run-1'").scalar() == "done"
    engine.dispose()


def test_migration_downgrade_removes_indexes_without_data_loss(tmp_path):
    db_path = tmp_path / "downgrade.sqlite"
    db_url = f"sqlite:///{db_path}"
    env = os.environ.copy()
    env["AILIZA_DATABASE_URL"] = db_url

    subprocess.run(
        [sys.executable, "-m", "alembic", "-c", str(ALEMBIC_INI), "upgrade", "head"],
        cwd=REPO_ROOT / "apps" / "backend", env=env, check=True, capture_output=True, text=True, timeout=60,
    )
    engine = create_engine(db_url)
    with engine.begin() as conn:
        conn.exec_driver_sql(
            "INSERT INTO audit_logs (timestamp, action, metadata, tenant_id, previous_hash, entry_hash) "
            "VALUES ('2026-01-01T00:00:00+00:00', 'test.action', '{}', 'default', '00', '11')"
        )
    engine.dispose()

    result = subprocess.run(
        [sys.executable, "-m", "alembic", "-c", str(ALEMBIC_INI), "downgrade", "b4d3a1d0de71"],
        cwd=REPO_ROOT / "apps" / "backend", env=env, check=True, capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0, result.stderr

    engine = create_engine(db_url)
    assert "ix_audit_logs_tenant_timestamp" not in _pragma_indexes(engine, "audit_logs")
    with engine.begin() as conn:
        assert conn.exec_driver_sql("SELECT COUNT(*) FROM audit_logs").scalar() == 1
    engine.dispose()


def test_backup_api_compatible_with_wal_and_new_indexes(tmp_path):
    """Regressionsschutz für die Datensicherung (Paket 0 / PR #82, dort als
    scripts/ailiza_backup.py umgesetzt -- hier bewusst OHNE Abhängigkeit von
    diesem separaten Branch getestet): die SQLite-Backup-API (die dortige
    Sicherung nutzt sqlite3.Connection.backup()) muss weiterhin konsistent
    sichern, wenn die Quelldatenbank WAL-aktiv ist und die neuen Indizes aus
    diesem Paket enthält -- inklusive committeter Daten, die noch nicht in
    die Haupt-Datei zurückgeschrieben (WAL-Checkpoint) wurden."""
    import sqlite3

    db_path = tmp_path / "backup_source.sqlite"
    env = os.environ.copy()
    env["AILIZA_DATABASE_URL"] = f"sqlite:///{db_path}"
    code = (
        "import sys; sys.path.insert(0, " + repr(str(REPO_ROOT)) + ")\n"
        "import apps.backend.database as db\n"
        "db.init_db()\n"
        "db.write_audit_entry(action='test.backup_compat', metadata={})\n"
        "with db.engine.begin() as conn:\n"
        "    print(conn.exec_driver_sql('PRAGMA journal_mode').scalar())\n"
    )
    r = subprocess.run(
        [sys.executable, "-c", code],
        cwd=REPO_ROOT, env=env, capture_output=True, text=True, timeout=60,
    )
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip().lower() == "wal"

    # Konsistente Sicherung wie in scripts/ailiza_backup.py: Backup-API statt
    # Dateikopie, sonst fehlen ggf. noch nicht gecheckpointete WAL-Daten.
    backup_path = tmp_path / "backup_target.sqlite"
    src = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        dst = sqlite3.connect(str(backup_path))
        try:
            src.backup(dst)
        finally:
            dst.close()
    finally:
        src.close()

    verify_con = sqlite3.connect(f"file:{backup_path}?mode=ro", uri=True)
    try:
        assert verify_con.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        rows = verify_con.execute(
            "SELECT action FROM audit_logs WHERE action = 'test.backup_compat'"
        ).fetchall()
        assert len(rows) == 1, "Audit-Eintrag muss in der Sicherung vorhanden sein"
        indexes = {row[1] for row in verify_con.execute("PRAGMA index_list(audit_logs)").fetchall()}
        assert "ix_audit_logs_tenant_timestamp" in indexes, "Neue Indizes muessen in der Sicherung erhalten bleiben"
    finally:
        verify_con.close()
