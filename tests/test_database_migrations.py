"""Formales Migrationssystem (Alembic) -- Arbeitspaket 3.

Scope: apps/backend/alembic.ini, apps/backend/alembic/env.py,
apps/backend/alembic/versions/0001_baseline_existing_schema.py.

Wichtig: Ein normaler Modulimport bleibt nebenwirkungsfrei. Beim
FastAPI-Lifespan wird fuer persistente Datenbanken jedoch verbindlich
`alembic upgrade head` ausgefuehrt. `init_db()` und
`ensure_sqlite_schema()` bleiben nur als Legacy-/In-Memory-Testhelfer.

Diese Tests rufen bewusst die echte `alembic`-CLI als Subprozess auf
(kein Mocking) -- das ist der tatsaechliche, dokumentierte Aufrufweg
("cd apps/backend && alembic upgrade head")."""
from __future__ import annotations

import os
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = REPO_ROOT / "apps" / "backend"


def _run_alembic(*args: str, database_url: str) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["AILIZA_SECRET_KEY"] = "test-secret-key-minimum-32-chars-ok"
    env["AILIZA_DATABASE_URL"] = database_url
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=str(BACKEND_DIR),
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )


def _table_names(db_path: Path) -> set[str]:
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        cur = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        return {row[0] for row in cur.fetchall()}
    finally:
        conn.close()


# ── 1. Leere, neue Datenbank -> aktueller Stand ──────────────────────────────

def test_empty_database_migrates_to_current_schema(tmp_path):
    db_path = tmp_path / "empty.db"
    result = _run_alembic("upgrade", "head", database_url=f"sqlite:///{db_path}")
    assert result.returncode == 0, result.stderr

    tables = _table_names(db_path)
    assert "alembic_version" in tables
    # Bekannte Kern-Tabellen (nicht alle einzeln, aber ein Querschnitt ueber
    # AILIZA-Kern/Benutzer/Memory/Audit/Fachanwendung):
    for expected in ("users", "audit_logs", "memory_items", "memory_visibility",
                      "knowledge_sources", "totp_secrets", "user_settings"):
        assert expected in tables, f"Tabelle {expected} fehlt nach Baseline-Migration"
    # Migration 0005b (Paket A, model_candidates + routing_decisions) und
    # Migration 0005 (Phase 1, customers) sind beide ueber die Merge-Revision
    # angewandt -- ausdruecklich anhand der Namen geprueft statt einer
    # geratenen Gesamtzahl.
    for expected in ("model_candidates", "routing_decisions", "customers"):
        assert expected in tables, f"Tabelle {expected} fehlt nach Merge-Revision"
    for expected in ("business_domains", "tenant_business_domains",
                     "user_domain_memberships", "domain_role_permissions"):
        assert expected in tables, f"Tabelle {expected} fehlt nach Bereichs-Migration"
    for expected in ("component_evidence", "evaluation_runs", "component_approvals",
                     "tenant_governance_settings", "budget_policies",
                     "budget_reservations", "cost_events", "component_activations"):
        assert expected in tables, f"Tabelle {expected} fehlt nach Board-Migration"
    # Tatsaechlich ermittelte Tabellenzahl, gegen eine frische Migration
    # verifiziert: 27 Basis-Tabellen + model_candidates + routing_decisions
    # + customers + alembic_version = 31, dazu die vier Tabellen der
    # Bereichsfreischaltung (d4a1f7b93c20) = 35, plus acht Tabellen des
    # Komponenten-Boards (c31a9f4d82e7) = 43.
    assert len(tables) == 43, f"Unerwartete Tabellenzahl nach Board-Migration: {len(tables)}"


# ── 1b. Import vs. Datenbankstart sind sauber getrennt ───────────────────────
# (Karo-Entscheidung 2026-08-02: apps/backend/db_schema.py enthaelt die
# nebenwirkungsfreie Schema-Beschreibung, apps/backend/database.py ruft
# init_db() nicht mehr automatisch beim Modulimport auf.)

def test_importing_database_module_creates_no_tables(tmp_path):
    """Reiner Import von apps.backend.database darf keine einzige Tabelle
    anlegen -- Voraussetzung dafuer, dass eine feste Alembic-Baseline
    (0001) auf einer neuen Datenbank ueberhaupt laufen kann."""
    db_path = tmp_path / "import_only.db"
    result = subprocess.run(
        [sys.executable, "-c", (
            "import apps.backend.database as dbmod; "
            "conn = dbmod.engine.connect(); "
            "tables = dbmod.engine.dialect.get_table_names(conn); "
            "assert tables == [], f'Import hat Tabellen angelegt: {tables}'; "
            "print('OK')"
        )],
        cwd=str(REPO_ROOT),
        env={**os.environ, "AILIZA_SECRET_KEY": "test-secret-key-minimum-32-chars-ok",
             "AILIZA_DATABASE_URL": f"sqlite:///{db_path}"},
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "OK" in result.stdout


def test_application_start_migrates_persistent_database_to_head(tmp_path):
    """Der reale Startpfad muss eine persistente DB per Alembic anlegen."""
    db_path = tmp_path / "app_start.db"
    result = subprocess.run(
        [sys.executable, "-c", (
            "import apps.backend.database as dbmod; "
            "dbmod.prepare_database_for_startup(); "
            "conn = dbmod.engine.connect(); "
            "tables = set(dbmod.engine.dialect.get_table_names(conn)); "
            "assert 'users' in tables and 'audit_logs' in tables and 'alembic_version' in tables, tables; "
            "versions = conn.exec_driver_sql('SELECT version_num FROM alembic_version').fetchall(); "
            "assert len(versions) == 1 and versions[0][0], versions; "
            "conn.close(); "
            "print('OK')"
        )],
        cwd=str(REPO_ROOT),
        env={**os.environ, "AILIZA_SECRET_KEY": "test-secret-key-minimum-32-chars-ok",
             "AILIZA_DATABASE_URL": f"sqlite:///{db_path}"},
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "OK" in result.stdout


def test_application_start_rejects_unversioned_conflicting_schema(tmp_path):
    """Ein unbekannter Altbestand darf nicht still mit create_all/ALTER
    weitergefuehrt werden. Die bewusste Uebernahme erfolgt ausschliesslich
    ueber `python -m apps.backend.alembic_adopt`."""
    db_path = tmp_path / "unversioned.db"
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE users (id TEXT PRIMARY KEY)")
    conn.commit()
    conn.close()

    result = subprocess.run(
        [sys.executable, "-c", (
            "import apps.backend.database as dbmod; "
            "dbmod.prepare_database_for_startup()"
        )],
        cwd=str(REPO_ROOT),
        env={**os.environ, "AILIZA_SECRET_KEY": "test-secret-key-minimum-32-chars-ok",
             "AILIZA_DATABASE_URL": f"sqlite:///{db_path}"},
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode != 0
    assert "already exists" in (result.stdout + result.stderr).lower()


def test_alembic_env_import_does_not_trigger_init_db(tmp_path):
    """alembic/env.py importiert nur die nebenwirkungsfreie metadata_obj aus
    db_schema.py (nicht init_db() aus database.py). Ein `alembic upgrade
    6165ff33e9ee` gegen eine neue Datenbank darf deshalb NICHT mit "table
    already exists" scheitern (Regressionstest fuer den urspruenglichen
    Fund: init_db() lief bisher automatisch beim Import von database.py)."""
    db_path = tmp_path / "env_import.db"
    result = _run_alembic("upgrade", "6165ff33e9ee", database_url=f"sqlite:///{db_path}")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "already exists" not in (result.stdout + result.stderr)


def test_existing_imports_of_tables_still_work():
    """Bestehende Importe wie `from apps.backend.database import users,
    memory_items, ...` muessen unveraendert funktionieren -- database.py
    exportiert die Tabellenobjekte aus db_schema.py unveraendert weiter."""
    import apps.backend.database as dbmod
    import apps.backend.db_schema as schema_mod

    for name in (
        "audit_logs", "approval_requests", "agent_runs", "user_specialist_roles",
        "case_assignments", "security_logs", "performance_logs", "cost_logs",
        "reflection_facts", "feedback", "routing_proposals", "kill_switch_state",
        "users", "user_settings", "memory_sources", "memory_items",
        "memory_visibility", "memory_suggestions", "messenger_bindings",
        "totp_secrets", "totp_backup_codes", "skills", "knowledge_sources",
        "knowledge_chunks", "knowledge_source_permissions", "user_projects",
        "user_chats", "metadata_obj", "DEFAULT_TENANT_ID",
    ):
        assert hasattr(dbmod, name), f"database.py exportiert {name} nicht mehr"
        assert getattr(dbmod, name) is getattr(schema_mod, name), (
            f"{name}: database.py und db_schema.py verweisen auf verschiedene Objekte"
        )


def test_db_schema_module_has_no_side_effects_on_import():
    """apps/backend/db_schema.py darf keine Engine erzeugen, keine
    Verbindung aufbauen und keine Datei anlegen -- reine Beschreibung."""
    result = subprocess.run(
        [sys.executable, "-c", (
            "import apps.backend.db_schema as schema_mod; "
            "assert not hasattr(schema_mod, 'engine'), 'db_schema.py darf keine engine definieren'; "
            "assert not hasattr(schema_mod, 'init_db'), 'db_schema.py darf init_db nicht definieren'; "
            "print('OK')"
        )],
        cwd=str(REPO_ROOT),
        env={**os.environ, "AILIZA_SECRET_KEY": "test-secret-key-minimum-32-chars-ok"},
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "OK" in result.stdout


# ── 2. Bestehende Datenbank ohne Datenverlust (Uebernahme per Stempeln) ──────

def _run_adopt(*args: str, database_url: str) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["AILIZA_SECRET_KEY"] = "test-secret-key-minimum-32-chars-ok"
    env["AILIZA_DATABASE_URL"] = database_url
    return subprocess.run(
        [sys.executable, "-m", "apps.backend.alembic_adopt", *args],
        cwd=str(REPO_ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )


def test_existing_database_migrates_without_data_loss(tmp_path):
    # "Bestehende" DB simulieren: NICHT ueber init_db() (das baut das
    # HEUTIGE Schema -- inkl. customers, PR-85-Indizes, user_chats-Spalten
    # aus Migration 0006 -- und ist damit KEINE echte 0001-Datenbank mehr,
    # siehe Nachpruefungs-Handoff "vollstaendige 0001-Baseline-Pruefung").
    # Stattdessen die echte Baseline-Migration 0001 direkt ausfuehren --
    # das legt exakt das historische Schema an, unabhaengig davon, wie weit
    # sich database.py/db_schema.py seither weiterentwickelt haben.
    #
    # WICHTIG: Das Aufbauen der "bestehenden" DB laeuft bewusst in einem
    # eigenen Subprozess (nicht per importlib.reload(apps.backend.database)
    # im Testprozess selbst) -- ein In-Prozess-Reload wuerde die vom
    # gesamten pytest-Lauf geteilte engine/DATABASE_URL des Moduls dauerhaft
    # auf diese temporaere Datei umbiegen und ALLE anderen, danach
    # laufenden Tests der Suite zum Fehlschlagen bringen (siehe HANDOFF-
    # Selbstkorrektur bei der Einfuehrung dieses Tests).
    #
    # Die feste Baseline-Migration 0001 legt Tabellen mit expliziten
    # op.create_table()-Aufrufen an -- `alembic upgrade head` wuerde gegen
    # eine bereits bestehende Datenbank mit "table already exists"
    # fehlschlagen (beabsichtigt, siehe alembic_adopt.py-Docstring). Der
    # korrekte Weg fuer eine bestehende Datenbank ist das Stempeln nach
    # erfolgreicher Schema-Pruefung.
    db_path = tmp_path / "existing.db"
    result_upgrade = _run_alembic("upgrade", "6165ff33e9ee", database_url=f"sqlite:///{db_path}")
    assert result_upgrade.returncode == 0, result_upgrade.stderr

    conn = sqlite3.connect(db_path)
    conn.execute("DROP TABLE alembic_version")  # echter Alt-Bestand: nie von Alembic getrackt
    conn.execute(
        "INSERT INTO users (user_id, tenant_id, role, hashed_password, created_at, active, failed_login_attempts) "
        "VALUES ('alice', 'default', 'user', 'hash', '2025-01-01T00:00:00+00:00', 1, 0)"
    )
    conn.commit()
    conn.close()

    result = _run_adopt("--revision", "0001", database_url=f"sqlite:///{db_path}")
    assert result.returncode == 0, result.stdout + result.stderr

    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        count = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        stamped = conn.execute("SELECT version_num FROM alembic_version").fetchone()[0]
    finally:
        conn.close()
    assert count == 1, "vorhandene Nutzerzeile darf nicht verloren gehen"
    assert stamped == "6165ff33e9ee"


def test_existing_database_with_missing_table_is_rejected(tmp_path):
    """Fail-closed: fehlt eine erwartete Tabelle, wird NICHT gestempelt."""
    db_path = tmp_path / "incomplete.db"
    setup = subprocess.run(
        [sys.executable, "-c", (
            "import sqlite3; "
            "conn = sqlite3.connect(" + repr(str(db_path)) + "); "
            "conn.execute('CREATE TABLE users (user_id TEXT PRIMARY KEY)'); "
            "conn.commit(); conn.close()"
        )],
        capture_output=True, text=True, timeout=30,
    )
    assert setup.returncode == 0, setup.stderr

    result = _run_adopt("--revision", "0001", database_url=f"sqlite:///{db_path}")
    assert result.returncode != 0
    assert "fehlende" in (result.stdout + result.stderr).lower()

    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        tables = {row[0] for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
    finally:
        conn.close()
    assert "alembic_version" not in tables, "bei Ablehnung darf nicht gestempelt werden"


def test_existing_database_with_missing_column_is_rejected(tmp_path):
    """Fail-closed: fehlt eine erwartete Spalte in einer sonst bekannten
    Tabelle, wird ebenfalls NICHT gestempelt (keine stille Reparatur)."""
    db_path = tmp_path / "wrong_column.db"
    setup = subprocess.run(
        [sys.executable, "-c", (
            "import apps.backend.database as dbmod; dbmod.init_db(); "
            "dbmod.engine.dispose(); "
            "import sqlite3; conn = sqlite3.connect(" + repr(str(db_path)) + "); "
            "conn.execute('ALTER TABLE users RENAME COLUMN active TO active_renamed'); "
            "conn.commit(); conn.close()"
        )],
        cwd=str(REPO_ROOT),
        env={**os.environ, "AILIZA_SECRET_KEY": "test-secret-key-minimum-32-chars-ok",
             "AILIZA_DATABASE_URL": f"sqlite:///{db_path}"},
        capture_output=True, text=True, timeout=30,
    )
    assert setup.returncode == 0, setup.stderr

    result = _run_adopt("--revision", "0001", database_url=f"sqlite:///{db_path}")
    assert result.returncode != 0
    assert "users" in (result.stdout + result.stderr).lower()


def test_stamping_matching_database_is_idempotent(tmp_path):
    # Echte 0001-Datenbank -- nicht init_db() (heutiges Schema, siehe
    # Kommentar bei test_existing_database_migrates_without_data_loss).
    db_path = tmp_path / "idempotent_existing.db"
    setup = _run_alembic("upgrade", "6165ff33e9ee", database_url=f"sqlite:///{db_path}")
    assert setup.returncode == 0, setup.stderr
    conn = sqlite3.connect(db_path)
    conn.execute("DROP TABLE alembic_version")
    conn.commit()
    conn.close()

    r1 = _run_adopt("--revision", "0001", database_url=f"sqlite:///{db_path}")
    assert r1.returncode == 0, r1.stdout + r1.stderr
    r2 = _run_adopt("--revision", "0001", database_url=f"sqlite:///{db_path}")
    assert r2.returncode == 0, r2.stdout + r2.stderr


# ── 3. Erneuter Lauf ist sicher (idempotent) ─────────────────────────────────

def test_repeated_upgrade_is_safe_and_idempotent(tmp_path):
    db_path = tmp_path / "repeat.db"
    r1 = _run_alembic("upgrade", "head", database_url=f"sqlite:///{db_path}")
    assert r1.returncode == 0, r1.stderr
    tables_after_first = _table_names(db_path)

    r2 = _run_alembic("upgrade", "head", database_url=f"sqlite:///{db_path}")
    assert r2.returncode == 0, r2.stderr
    tables_after_second = _table_names(db_path)

    assert tables_after_first == tables_after_second


# ── 4. Fehler werden zurueckgemeldet, nicht verschluckt ──────────────────────

def test_downgrade_of_baseline_is_rejected_not_silently_destructive(tmp_path):
    db_path = tmp_path / "downgrade.db"
    r1 = _run_alembic("upgrade", "head", database_url=f"sqlite:///{db_path}")
    assert r1.returncode == 0, r1.stderr

    r2 = _run_alembic("downgrade", "base", database_url=f"sqlite:///{db_path}")
    assert r2.returncode != 0, "Downgrade der Baseline darf nicht klaglos durchlaufen"
    # Tabellen muessen unveraendert erhalten bleiben (kein Teil-Loeschen):
    assert len(_table_names(db_path)) == 28


# ── 5. ensure_sqlite_schema bleibt unveraendert bestehen ─────────────────────

def test_ensure_sqlite_schema_still_exists_and_is_not_removed():
    import apps.backend.database as dbmod
    assert hasattr(dbmod, "ensure_sqlite_schema")
    assert callable(dbmod.ensure_sqlite_schema)


# ── 6. Kein automatischer Migrationslauf beim Import ─────────────────────────

def test_importing_database_module_does_not_touch_alembic():
    """Reiner Import von apps.backend.database darf alembic nicht einmal
    importieren -- die Trennung zwischen Anwendungscode und Migrations-CLI
    muss strikt sein."""
    result = subprocess.run(
        [sys.executable, "-c", (
            "import os; "
            "os.environ.setdefault('AILIZA_SECRET_KEY', 'test-secret-key-minimum-32-chars-ok'); "
            "os.environ.setdefault('AILIZA_DATABASE_URL', 'sqlite:///:memory:'); "
            "import sys; "
            "import apps.backend.database; "
            "assert 'alembic' not in sys.modules, 'alembic wurde durch reinen Import geladen'; "
            "print('OK')"
        )],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "OK" in result.stdout


# ── 7. PostgreSQL (optional, wie bei den bestehenden Postgres-Tests) ────────

POSTGRES_URL = os.environ.get("AILIZA_TEST_POSTGRES_URL")


def _reset_postgres_public_schema() -> None:
    """Alle Tabellen im 'public'-Schema der Test-Postgres-DB entfernen, damit
    jeder Postgres-Test von einem definierten (leeren) Zustand startet --
    die Test-DB wird ueber mehrere Tests/Laeufe hinweg wiederverwendet."""
    import psycopg

    pg_dsn = POSTGRES_URL.replace("postgresql+psycopg://", "postgresql://")
    with psycopg.connect(pg_dsn) as conn:
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
            for (name,) in cur.fetchall():
                cur.execute(f'DROP TABLE IF EXISTS "{name}" CASCADE')


@pytest.mark.skipif(not POSTGRES_URL, reason="AILIZA_TEST_POSTGRES_URL nicht gesetzt.")
def test_postgres_baseline_migration_creates_expected_tables():
    import psycopg

    _reset_postgres_public_schema()
    result = _run_alembic("upgrade", "head", database_url=POSTGRES_URL)
    assert result.returncode == 0, result.stderr

    pg_dsn = POSTGRES_URL.replace("postgresql+psycopg://", "postgresql://")
    with psycopg.connect(pg_dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'"
            )
            tables = {row[0] for row in cur.fetchall()}
    assert "alembic_version" in tables
    assert "users" in tables
    assert "audit_logs" in tables


@pytest.mark.skipif(not POSTGRES_URL, reason="AILIZA_TEST_POSTGRES_URL nicht gesetzt.")
def test_postgres_partial_indexes_have_postgresql_where_after_0002():
    import psycopg

    _reset_postgres_public_schema()
    result = _run_alembic("upgrade", "head", database_url=POSTGRES_URL)
    assert result.returncode == 0, result.stderr

    pg_dsn = POSTGRES_URL.replace("postgresql+psycopg://", "postgresql://")
    with psycopg.connect(pg_dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT indexdef FROM pg_indexes WHERE indexname = 'ux_active_specialist_role'"
            )
            row = cur.fetchone()
    assert row is not None
    assert "WHERE" in row[0], "Index muss nach Migration 0002 partiell (mit WHERE) sein"


@pytest.mark.skipif(not POSTGRES_URL, reason="AILIZA_TEST_POSTGRES_URL nicht gesetzt.")
def test_postgres_existing_database_adoption_via_stamp(tmp_path):
    import psycopg

    _reset_postgres_public_schema()

    setup = subprocess.run(
        [sys.executable, "-c", "import apps.backend.database as dbmod; dbmod.init_db(); dbmod.engine.dispose()"],
        cwd=str(REPO_ROOT),
        env={**os.environ, "AILIZA_SECRET_KEY": "test-secret-key-minimum-32-chars-ok",
             "AILIZA_DATABASE_URL": POSTGRES_URL},
        capture_output=True, text=True, timeout=60,
    )
    assert setup.returncode == 0, setup.stderr

    adopt = subprocess.run(
        [sys.executable, "-m", "apps.backend.alembic_adopt", "--revision", "0001"],
        cwd=str(REPO_ROOT),
        env={**os.environ, "AILIZA_SECRET_KEY": "test-secret-key-minimum-32-chars-ok",
             "AILIZA_DATABASE_URL": POSTGRES_URL},
        capture_output=True, text=True, timeout=60,
    )
    assert adopt.returncode == 0, adopt.stdout + adopt.stderr

    pg_dsn = POSTGRES_URL.replace("postgresql+psycopg://", "postgresql://")
    with psycopg.connect(pg_dsn) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT version_num FROM alembic_version")
            (stamped,) = cur.fetchone()
    assert stamped == "6165ff33e9ee"


# ── 8. Meta: keine Test-DB beruehrt eine echte/produktive Datenbank ─────────

def test_no_migration_test_uses_production_database_url():
    """Alle Tests dieser Datei setzen AILIZA_DATABASE_URL explizit auf eine
    tmp_path-Datei, :memory: oder eine gesondert deklarierte Test-Postgres-URL
    -- niemals implizit auf die produktive/Dev-Datenbank. Diese Meta-Pruefung
    stellt sicher, dass keine Testfunktion versehentlich ohne
    AILIZA_DATABASE_URL-Override arbeitet, was auf eine echte Datei ausweichen
    wuerde (siehe _resolve_database_url() Dev-Fallback in database.py)."""
    import inspect as _inspect

    module = sys.modules[__name__]
    for name, func in vars(module).items():
        if not name.startswith("test_"):
            continue
        source = _inspect.getsource(func)
        if "_run_alembic(" in source or "_run_adopt(" in source or "AILIZA_DATABASE_URL" in source:
            continue
        # Tests, die weder die Alembic-CLI noch das Adopt-Skript noch direkt
        # AILIZA_DATABASE_URL verwenden, duerfen keine Datenbankdatei anfassen.
        assert "engine" not in source or "dbmod.engine" not in source, (
            f"{name} scheint eine Datenbank-Engine zu beruehren, ohne "
            "AILIZA_DATABASE_URL explizit zu setzen"
        )


# ── 9. Baseline-Migration 0001 ist strukturell festgeschrieben ──────────────

def test_baseline_migration_0001_table_set_is_pinned():
    """Migration 0001 muss genau die 27 aktuell in database.py definierten
    Tabellennamen enthalten -- weder mehr noch weniger. Diese Pruefung soll
    kuenftige Aenderungen an database.py NICHT automatisch in die historische
    Baseline durchsickern lassen: sie vergleicht bewusst gegen eine im Test
    fest hinterlegte Namensliste (Stand der Entscheidung 2026-08-02), nicht
    gegen metadata_obj.tables.keys() zur Laufzeit."""
    import ast

    versions_dir = REPO_ROOT / "apps" / "backend" / "alembic" / "versions"
    source = (versions_dir / "0001_baseline_existing_schema.py").read_text(encoding="utf-8")
    tree = ast.parse(source)

    created_tables = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr == "create_table" and node.args:
                first_arg = node.args[0]
                if isinstance(first_arg, ast.Constant) and isinstance(first_arg.value, str):
                    created_tables.add(first_arg.value)

    expected = {
        "audit_logs", "approval_requests", "agent_runs", "user_specialist_roles",
        "case_assignments", "security_logs", "performance_logs", "cost_logs",
        "reflection_facts", "feedback", "routing_proposals", "kill_switch_state",
        "users", "user_settings", "memory_sources", "memory_items",
        "memory_visibility", "memory_suggestions", "messenger_bindings",
        "totp_secrets", "totp_backup_codes", "skills", "knowledge_sources",
        "knowledge_chunks", "knowledge_source_permissions", "user_projects",
        "user_chats",
    }
    assert created_tables == expected
    assert len(expected) == 27

    revision_line = [l for l in source.splitlines() if l.startswith("revision: str")][0]
    assert "6165ff33e9ee" in revision_line, (
        "Revisions-ID von Migration 0001 darf sich nicht aendern -- "
        "bereits referenziert (u.a. alembic_adopt.py, bestehende Tests)."
    )
