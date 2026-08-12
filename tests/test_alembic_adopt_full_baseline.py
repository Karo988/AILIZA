"""Tests für apps/backend/alembic_adopt.py — vollständige 0001-Baseline-Prüfung
(Teil 1 des Nachprüfungs-Handoffs: Tabellen UND Spalten UND Indizes gegen
die echte historische Migration 0001, nicht gegen das lebende metadata_obj).

Regressionsschutz für den konkreten Vorfall: eine neue Tabelle/Spalte/Index
im heutigen Code (z.B. customers, PR-85-Indizes) darf die Adoption einer
echten, nie migrierten Alt-Datenbank NICHT verweigern.

Läuft ausschließlich gegen temporäre SQLite-Dateien, nie gegen eine echte
AILIZA-Datenbank. Subprozess-isoliert (kein importlib.reload im Prozess --
siehe Lehre aus tests/test_database_performance_safety.py).
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = REPO_ROOT / "apps" / "backend"
ALEMBIC_INI = BACKEND_DIR / "alembic.ini"
BASELINE_REVISION = "6165ff33e9ee"


def _run_alembic(*args: str, db_url: str) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env["AILIZA_DATABASE_URL"] = db_url
    return subprocess.run(
        [sys.executable, "-m", "alembic", "-c", "alembic.ini", *args],
        cwd=BACKEND_DIR, env=env, capture_output=True, text=True, timeout=60,
    )


def _run_adopt(*args: str, db_url: str) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env["AILIZA_DATABASE_URL"] = db_url
    env.setdefault("AILIZA_SECRET_KEY", "test-secret-key-minimum-32-chars-ok")
    return subprocess.run(
        [sys.executable, "-m", "apps.backend.alembic_adopt", *args],
        cwd=REPO_ROOT, env=env, capture_output=True, text=True, timeout=60,
    )


def _build_true_0001_database(db_path: Path) -> None:
    """Baut eine echte, historisch korrekte 0001-Datenbank -- über die echte
    Migrationsdatei, NICHT über das heutige ORM-Modell (metadata_obj). Danach
    wird alembic_version entfernt, um einen echten, nie migrierten Alt-
    Bestand zu simulieren (das ist der reale Adoptions-Anwendungsfall)."""
    db_url = f"sqlite:///{db_path}"
    result = _run_alembic("upgrade", BASELINE_REVISION, db_url=db_url)
    assert result.returncode == 0, result.stderr

    import sqlite3
    con = sqlite3.connect(db_path)
    con.execute("DROP TABLE alembic_version")
    con.commit()
    con.close()


def test_genuine_0001_database_is_adopted_despite_newer_schema_in_code(tmp_path):
    """Kernregression: eine echte 0001-Alt-Datenbank muss adoptierbar
    bleiben, auch wenn der heutige Code (customers-Tabelle, PR-85-Indizes,
    user_chats-Spalten) laengst weiter ist."""
    db_path = tmp_path / "true_0001.sqlite"
    _build_true_0001_database(db_path)
    db_url = f"sqlite:///{db_path}"

    result = _run_adopt("--dry-run", "--revision", "0001", db_url=db_url)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "entspricht exakt der erwarteten Baseline" in result.stdout


def test_genuine_0001_database_full_adopt_and_upgrade_preserves_data(tmp_path):
    """End-to-End: adoptieren -> alembic upgrade head -> Kopfrevision,
    customers vorhanden, Altdaten unveraendert."""
    db_path = tmp_path / "full_flow.sqlite"
    _build_true_0001_database(db_path)
    db_url = f"sqlite:///{db_path}"

    import sqlite3
    con = sqlite3.connect(db_path)
    con.execute(
        "INSERT INTO audit_logs (timestamp, action, metadata, tenant_id, previous_hash, entry_hash) "
        "VALUES ('2025-03-01T00:00:00+00:00', 'echtbestand.test', '{}', 'default', '00', '11')"
    )
    con.commit()
    con.close()

    result = _run_adopt("--revision", "0001", db_url=db_url)
    assert result.returncode == 0, result.stdout + result.stderr

    con = sqlite3.connect(db_path)
    assert con.execute("SELECT version_num FROM alembic_version").fetchone()[0] == BASELINE_REVISION
    con.close()

    result = _run_alembic("upgrade", "head", db_url=db_url)
    assert result.returncode == 0, result.stderr

    con = sqlite3.connect(db_path)
    tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert "customers" in tables
    assert con.execute("SELECT COUNT(*) FROM audit_logs").fetchone()[0] == 1
    assert con.execute("SELECT action FROM audit_logs").fetchone()[0] == "echtbestand.test"
    con.close()


def test_database_missing_expected_table_is_rejected(tmp_path):
    """Fail-closed-Gegenprobe: eine tatsächlich abweichende Alt-Datenbank
    (fehlende Tabelle) muss weiterhin verweigert werden."""
    db_path = tmp_path / "broken.sqlite"
    _build_true_0001_database(db_path)

    import sqlite3
    con = sqlite3.connect(db_path)
    con.execute("DROP TABLE users")
    con.commit()
    con.close()

    result = _run_adopt("--dry-run", "--revision", "0001", db_url=f"sqlite:///{db_path}")
    assert result.returncode == 1
    assert "users" in result.stdout


def test_database_already_past_0001_is_rejected(tmp_path):
    """Eine Datenbank, die bereits neuere Elemente enthält (hier: die
    heutige, vollständige Schema-Erstellung über init_db()), ist NICHT
    wirklich auf 0001-Stand und muss als Abweichung erkannt werden --
    auch mit dem gefixten Vergleich (Regressionsschutz gegen einen zu
    laxen Fix, der einfach alles durchwinkt)."""
    db_path = tmp_path / "ahead.sqlite"
    env = os.environ.copy()
    env["AILIZA_DATABASE_URL"] = f"sqlite:///{db_path}"
    env["AILIZA_SECRET_KEY"] = "test-secret-key-minimum-32-chars-ok"
    code = "import sys; sys.path.insert(0, '.'); from apps.backend.database import init_db; init_db()"
    r = subprocess.run([sys.executable, "-c", code], cwd=REPO_ROOT, env=env,
                        capture_output=True, text=True, timeout=30)
    assert r.returncode == 0, r.stderr

    result = _run_adopt("--dry-run", "--revision", "0001", db_url=f"sqlite:///{db_path}")
    assert result.returncode == 1
    assert "customers" in result.stdout
