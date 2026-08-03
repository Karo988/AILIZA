"""Tests fuer den Reparatur-Mechanismus bei Postgres-Schema-Drift.

Hintergrund (echter Produktionsfehler, 2026-08-03):
`ensure_sqlite_schema()` in apps/backend/database.py patcht fehlende Spalten
NUR fuer SQLite (`if not DATABASE_URL.startswith("sqlite"): return`). Auf der
produktiven PostgreSQL-Datenbank wurde daher nie eine nachtraeglich im
Python-Schema ergaenzte Spalte angelegt -- `metadata_obj.create_all()` legt
nur fehlende TABELLEN an, niemals fehlende SPALTEN. Ergebnis war ein harter
HTTP-500 (`psycopg.errors.UndefinedColumn: column "owner_user_id" of relation
"agent_runs" does not exist`).

Reparatur besteht aus zwei Teilen, die hier beide dauerhaft abgesichert werden:
  1. Migration 0003_add_missing_columns_postgres_drift.py -- additive,
     idempotente `add_column`-Operationen.
  2. Toleranz-Mechanismus in apps/backend/alembic_adopt.py -- erlaubt das
     Stempeln einer Bestands-Datenbank NUR bei exakt den bekannten,
     additiven Luecken (KNOWN_ADDITIVE_GAPS), sonst weiterhin fail-closed.

Diese Tests waren zuvor nur als Wegwerf-Skripte vorhanden. Ohne sie koennte
ein spaeteres Refactoring den Mechanismus still aushebeln -- fuer die
Zertifizierung ist der Nachweis reproduzierbar erforderlich.

Alle Tests laufen ausschliesslich gegen temporaere SQLite-Wegwerfdatenbanken.
Es wird NIE eine echte oder produktive Datenbank verwendet.
"""
import os
import sqlite3
import subprocess
import sys
import tempfile

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASELINE_REVISION = "6165ff33e9ee"

# Die auf der Produktions-Datenbank fehlenden Spalten (siehe Migration 0003).
DRIFT_COLUMNS = [
    ("audit_logs", "tenant_id"),
    ("approval_requests", "tenant_id"),
    ("approval_requests", "owner_user_id"),
    ("agent_runs", "tenant_id"),
    ("agent_runs", "owner_user_id"),
    ("users", "failed_login_attempts"),
    ("users", "locked_until"),
    ("user_projects", "version"),
    ("user_chats", "version"),
    ("user_chats", "keep_uploaded_documents"),
    ("user_chats", "document_retention_days"),
]


def _run(
    code: str, db_path: str | None = None, url: str | None = None
) -> subprocess.CompletedProcess:
    """Fuehrt Python-Code in einem Subprozess gegen eine Wegwerf-DB aus.

    Subprozess statt In-Process, weil apps.backend.database die Engine beim
    Import an AILIZA_DATABASE_URL bindet -- ein spaeterer Wechsel der URL
    wuerde sonst nicht greifen.

    Entweder `db_path` (temporaere SQLite-Datei) oder `url` (vollstaendige
    Datenbank-URL, fuer die PostgreSQL-Tests) angeben.
    """
    assert (db_path is None) != (url is None), "genau eines von db_path/url"
    env = dict(os.environ)
    env["AILIZA_SECRET_KEY"] = "test-secret-key-minimum-32-chars-ok"
    env["AILIZA_DATABASE_URL"] = url if url is not None else f"sqlite:///{db_path}"
    return subprocess.run(
        [sys.executable, "-c", code],
        cwd=REPO_ROOT, env=env, capture_output=True, text=True, timeout=180,
    )


_UPGRADE_SNIPPET = """
import os
from alembic.config import Config
from alembic import command
cfg = Config()
cfg.set_main_option("script_location", "apps/backend/alembic")
cfg.set_main_option("sqlalchemy.url", os.environ["AILIZA_DATABASE_URL"])
command.upgrade(cfg, {target!r})
print("UPGRADE_OK")
"""


def _upgrade(db_path: str, target: str = "head") -> None:
    result = _run(_UPGRADE_SNIPPET.format(target=target), db_path)
    assert "UPGRADE_OK" in result.stdout, result.stdout + result.stderr


def _columns(db_path: str, table: str) -> set[str]:
    con = sqlite3.connect(db_path)
    try:
        return {row[1] for row in con.execute(f"PRAGMA table_info({table})")}
    finally:
        con.close()


def _make_drifted_db(db_path: str, drop: list[tuple[str, str]]) -> None:
    """Baut die Baseline 0001 auf und entfernt danach gezielt Spalten.

    Simuliert damit den realen Zustand der Produktionsdatenbank: ein altes
    Schema, das nie gestempelt wurde und dem Spalten fehlen.
    """
    _upgrade(db_path, BASELINE_REVISION)
    con = sqlite3.connect(db_path)
    try:
        for table, column in drop:
            con.execute(f"ALTER TABLE {table} DROP COLUMN {column}")
        con.execute("DELETE FROM alembic_version")  # ungestempelte Alt-DB
        con.commit()
    finally:
        con.close()


# ---------------------------------------------------------------------------
# 1. Migration 0003: Idempotenz und Reparaturwirkung
# ---------------------------------------------------------------------------

def test_fresh_database_upgrade_head_succeeds():
    """Auf einer frischen DB legt bereits 0001 alle Spalten an -- 0003 muss
    dort ein sauberes No-Op sein und darf keinen Duplicate-Column-Fehler
    ausloesen."""
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "fresh.db")
        _upgrade(db_path)
        cols = _columns(db_path, "user_chats")
        assert "keep_uploaded_documents" in cols
        assert "document_retention_days" in cols


def test_migration_0003_is_idempotent_when_run_twice():
    """Ein zweiter Durchlauf darf nicht fehlschlagen (Existenz-Pruefung)."""
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "twice.db")
        _upgrade(db_path)
        # Modulname beginnt mit einer Ziffer -> nur ueber importlib ladbar.
        result = _run(
            "import importlib.util, os\n"
            "from sqlalchemy import create_engine\n"
            "from alembic.migration import MigrationContext\n"
            "from alembic.operations import Operations\n"
            "spec = importlib.util.spec_from_file_location('m0003',"
            " 'apps/backend/alembic/versions/0003_add_missing_columns_postgres_drift.py')\n"
            "m = importlib.util.module_from_spec(spec)\n"
            "spec.loader.exec_module(m)\n"
            "engine = create_engine(os.environ['AILIZA_DATABASE_URL'])\n"
            "with engine.begin() as conn:\n"
            "    ctx = MigrationContext.configure(conn)\n"
            "    m.op = Operations(ctx)\n"
            "    m.upgrade()\n"
            "print('SECOND_RUN_OK')\n",
            db_path,
        )
        assert "SECOND_RUN_OK" in result.stdout, result.stdout + result.stderr


def test_drifted_database_columns_are_restored():
    """Kernfall: fehlende Spalten muessen durch 0003 zurueckkommen."""
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "drift.db")
        drop = [
            ("agent_runs", "owner_user_id"),
            ("users", "failed_login_attempts"),
            ("user_projects", "version"),
        ]
        _make_drifted_db(db_path, drop)
        for table, column in drop:
            assert column not in _columns(db_path, table), (
                f"Vorbedingung verletzt: {table}.{column} haette fehlen muessen"
            )

        _run(
            "from apps.backend.alembic_adopt import stamp_baseline_with_tolerance\n"
            "stamp_baseline_with_tolerance(allow_gaps=frozenset({"
            "('agent_runs','owner_user_id'),('users','failed_login_attempts'),"
            "('user_projects','version')}))\n",
            db_path,
        )
        _upgrade(db_path)

        for table, column in drop:
            assert column in _columns(db_path, table), (
                f"{table}.{column} wurde durch 0003 nicht wiederhergestellt"
            )


def test_repair_preserves_existing_rows_and_backfills_not_null_columns():
    """Wichtigster Test: eine DB MIT Daten darf durch die Reparatur weder
    Zeilen verlieren, noch an NOT-NULL-Spalten scheitern. Genau hier wuerde
    ein fehlendes server_default die Migration auf Postgres abbrechen."""
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "withdata.db")
        drop = [("agent_runs", "owner_user_id"), ("agent_runs", "tenant_id")]
        _make_drifted_db(db_path, drop)

        con = sqlite3.connect(db_path)
        cols = [row[1] for row in con.execute("PRAGMA table_info(agent_runs)")]
        con.execute(
            f"INSERT INTO agent_runs ({','.join(cols)}) "
            f"VALUES ({','.join(['?'] * len(cols))})",
            ["bestandswert"] * len(cols),
        )
        con.commit()
        con.close()

        _run(
            "from apps.backend.alembic_adopt import stamp_baseline_with_tolerance\n"
            "stamp_baseline_with_tolerance(allow_gaps=frozenset({"
            "('agent_runs','owner_user_id'),('agent_runs','tenant_id')}))\n",
            db_path,
        )
        _upgrade(db_path)

        con = sqlite3.connect(db_path)
        try:
            assert con.execute("SELECT COUNT(*) FROM agent_runs").fetchone()[0] == 1, (
                "Bestandsdaten gingen bei der Reparatur verloren"
            )
            # NOT NULL-Spalte muss fuer die Bestandszeile befuellt sein.
            assert con.execute("SELECT tenant_id FROM agent_runs").fetchone()[0] == "default"
            # Nullable-Spalte bleibt korrekt leer.
            assert con.execute("SELECT owner_user_id FROM agent_runs").fetchone()[0] is None
        finally:
            con.close()


# ---------------------------------------------------------------------------
# 2. Toleranz-Mechanismus: muss eng begrenzt bleiben (fail-closed)
# ---------------------------------------------------------------------------

def test_known_additive_gaps_matches_migration_0003_exactly():
    """Allowlist und Migration duerfen nicht auseinanderlaufen. Eine Spalte
    in der Allowlist, die 0003 nicht repariert, wuerde eine Luecke dauerhaft
    tolerieren, ohne sie je zu schliessen."""
    from apps.backend.alembic_adopt import KNOWN_ADDITIVE_GAPS

    path = os.path.join(
        REPO_ROOT, "apps/backend/alembic/versions",
        "0003_add_missing_columns_postgres_drift.py",
    )
    with open(path, encoding="utf-8") as fh:
        source = fh.read()

    for table, column in KNOWN_ADDITIVE_GAPS:
        assert f'"{column}"' in source, (
            f"{table}.{column} steht in KNOWN_ADDITIVE_GAPS, wird aber von "
            "Migration 0003 nicht behandelt"
        )
    assert set(KNOWN_ADDITIVE_GAPS) == set(DRIFT_COLUMNS), (
        "KNOWN_ADDITIVE_GAPS weicht von der dokumentierten Drift-Liste ab"
    )


def test_strict_stamp_still_rejects_drifted_database():
    """Regressionsschutz: die alte, strenge Funktion darf durch den neuen
    Toleranz-Mechanismus NICHT aufgeweicht worden sein."""
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "strict.db")
        _make_drifted_db(db_path, [("agent_runs", "owner_user_id")])
        result = _run(
            "from apps.backend.alembic_adopt import ("
            "    stamp_baseline_if_matching, SchemaMismatchError)\n"
            "try:\n"
            "    stamp_baseline_if_matching()\n"
            "    print('UNEXPECTED_SUCCESS')\n"
            "except SchemaMismatchError:\n"
            "    print('CORRECTLY_REJECTED')\n",
            db_path,
        )
        assert "CORRECTLY_REJECTED" in result.stdout, result.stdout + result.stderr


def test_tolerance_rejects_column_outside_allowlist():
    """Fehlt zusaetzlich eine NICHT gelistete Spalte, muss trotz korrekter
    allow_gaps weiterhin abgelehnt werden -- sonst wuerden echte Schemafehler
    unter dem Deckmantel der Toleranz durchrutschen."""
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "outside.db")
        _make_drifted_db(
            db_path, [("agent_runs", "owner_user_id"), ("users", "role")]
        )
        result = _run(
            "from apps.backend.alembic_adopt import ("
            "    stamp_baseline_with_tolerance, SchemaMismatchError)\n"
            "try:\n"
            "    stamp_baseline_with_tolerance("
            "        allow_gaps=frozenset({('agent_runs','owner_user_id')}))\n"
            "    print('UNEXPECTED_SUCCESS')\n"
            "except SchemaMismatchError:\n"
            "    print('CORRECTLY_REJECTED')\n",
            db_path,
        )
        assert "CORRECTLY_REJECTED" in result.stdout, result.stdout + result.stderr


def test_tolerance_rejects_gap_not_in_known_additive_gaps():
    """Wer eine Toleranz anfordert, die gar nicht in KNOWN_ADDITIVE_GAPS
    steht, muss fail-closed abgewiesen werden."""
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "unknown.db")
        _make_drifted_db(db_path, [("users", "role")])
        result = _run(
            "from apps.backend.alembic_adopt import ("
            "    stamp_baseline_with_tolerance, UnknownAdditiveGapError)\n"
            "try:\n"
            "    stamp_baseline_with_tolerance("
            "        allow_gaps=frozenset({('users','role')}))\n"
            "    print('UNEXPECTED_SUCCESS')\n"
            "except UnknownAdditiveGapError:\n"
            "    print('CORRECTLY_REJECTED')\n",
            db_path,
        )
        assert "CORRECTLY_REJECTED" in result.stdout, result.stdout + result.stderr


def test_tolerance_with_empty_allow_gaps_rejects():
    """Ohne ausdrueckliche Bestaetigung durch den Aufrufer keine Toleranz."""
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "empty.db")
        _make_drifted_db(db_path, [("agent_runs", "owner_user_id")])
        result = _run(
            "from apps.backend.alembic_adopt import ("
            "    stamp_baseline_with_tolerance, SchemaMismatchError)\n"
            "try:\n"
            "    stamp_baseline_with_tolerance(allow_gaps=frozenset())\n"
            "    print('UNEXPECTED_SUCCESS')\n"
            "except SchemaMismatchError:\n"
            "    print('CORRECTLY_REJECTED')\n",
            db_path,
        )
        assert "CORRECTLY_REJECTED" in result.stdout, result.stdout + result.stderr


# ---------------------------------------------------------------------------
# 3. Gesamtablauf, wie er gegen die Produktionsdatenbank vorgesehen ist
# ---------------------------------------------------------------------------

def test_full_repair_sequence_ends_with_exact_schema_match():
    """Vollstaendiger Ablauf: Drift -> Dry-Run schlaegt an -> Stempeln mit
    Toleranz -> upgrade head -> Dry-Run OHNE Toleranz meldet exakte
    Uebereinstimmung. Das ist die Abnahmebedingung fuer den Produktionslauf."""
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "full.db")
        _make_drifted_db(db_path, DRIFT_COLUMNS)

        gaps = ",".join(f"{t}.{c}" for t, c in DRIFT_COLUMNS)

        before = _run(
            "import sys\n"
            "from apps.backend.alembic_adopt import _main\n"
            "sys.exit(_main(['--dry-run']))\n",
            db_path,
        )
        assert before.returncode == 1, (
            "Dry-Run haette die Abweichung melden muessen:\n" + before.stdout
        )

        _run(
            "import sys\n"
            "from apps.backend.alembic_adopt import _main\n"
            f"sys.exit(_main(['--revision','0001','--allow-additive-gap','{gaps}']))\n",
            db_path,
        )
        _upgrade(db_path)

        after = _run(
            "import sys\n"
            "from apps.backend.alembic_adopt import _main\n"
            "sys.exit(_main(['--dry-run']))\n",
            db_path,
        )
        assert after.returncode == 0, (
            "Nach der Reparatur muss der strenge Dry-Run gruen sein:\n"
            + after.stdout + after.stderr
        )
        assert "entspricht exakt" in after.stdout, after.stdout


# ---------------------------------------------------------------------------
# 4. PostgreSQL-Nachweis (uebersprungen ohne AILIZA_TEST_POSTGRES_URL)
# ---------------------------------------------------------------------------
#
# Die Tests oben laufen ausschliesslich gegen SQLite. Der urspruengliche Fehler
# war jedoch genau eine Abweichung zwischen SQLite und PostgreSQL -- eine reine
# SQLite-Abdeckung kann ihn daher nicht ausschliessen. Zusaetzlich wird
# `_drop_server_defaults()` unter SQLite bewusst uebersprungen, sodass dort
# gerade NICHT belegt ist, dass die DEFAULT-Klauseln wirklich entfernt werden.
#
# Die folgenden Tests schliessen diese Luecke, benoetigen aber eine erreichbare
# PostgreSQL-Instanz. Sie werden uebersprungen, solange
# AILIZA_TEST_POSTGRES_URL nicht gesetzt ist.
#
# Lokal starten (Beispiel):
#   initdb -D <datadir> -U postgres --auth=trust
#   pg_ctl -D <datadir> -o '-p 55432' start
#   export AILIZA_TEST_POSTGRES_URL="postgresql+psycopg://postgres@127.0.0.1:55432/postgres"

POSTGRES_URL = os.environ.get("AILIZA_TEST_POSTGRES_URL")
requires_postgres = pytest.mark.skipif(
    not POSTGRES_URL,
    reason="AILIZA_TEST_POSTGRES_URL nicht gesetzt -- PostgreSQL-Nachweis uebersprungen",
)

_COLUMN_QUERY = """
SELECT table_name, column_name, data_type, is_nullable,
       coalesce(column_default, '<kein>')
FROM information_schema.columns
WHERE table_schema = 'public' AND table_name <> 'alembic_version'
ORDER BY table_name, column_name
"""

# Genau die Spalten, die in Migration 0003 mit server_default ergaenzt und
# anschliessend wieder bereinigt werden.
_BACKFILLED_NOT_NULL_COLUMNS = [
    ("audit_logs", "tenant_id"),
    ("approval_requests", "tenant_id"),
    ("agent_runs", "tenant_id"),
    ("users", "failed_login_attempts"),
    ("user_projects", "version"),
    ("user_chats", "version"),
]


@pytest.fixture
def postgres_databases():
    """Legt zwei frische PostgreSQL-Datenbanken an und raeumt sie wieder ab."""
    import uuid

    import sqlalchemy as sa

    suffix = uuid.uuid4().hex[:10]
    repaired = f"ailiza_test_repaired_{suffix}"
    fresh = f"ailiza_test_fresh_{suffix}"

    admin = sa.create_engine(POSTGRES_URL, isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        for name in (repaired, fresh):
            conn.execute(sa.text(f'CREATE DATABASE "{name}"'))

    def url_for(name: str) -> str:
        base, _, _ = POSTGRES_URL.rpartition("/")
        return f"{base}/{name}"

    try:
        yield url_for(repaired), url_for(fresh)
    finally:
        with admin.connect() as conn:
            for name in (repaired, fresh):
                conn.execute(
                    sa.text(
                        "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                        "WHERE datname = :n AND pid <> pg_backend_pid()"
                    ),
                    {"n": name},
                )
                conn.execute(sa.text(f'DROP DATABASE IF EXISTS "{name}"'))
        admin.dispose()


def _alembic_upgrade(url: str, target: str) -> None:
    """Fuehrt `alembic upgrade` gegen die angegebene URL aus.

    Bewusst als Subprozess: apps/backend/alembic/env.py importiert DATABASE_URL
    aus apps.backend.database und ueberschreibt damit `sqlalchemy.url` der
    Config beim Import. Ein in-process gesetztes set_main_option() haette also
    keine Wirkung -- die Migration liefe gegen die Standard-Entwicklungs-DB.
    Die URL muss deshalb ueber AILIZA_DATABASE_URL gesetzt werden, bevor
    apps.backend.database importiert wird.
    """
    result = _run(_UPGRADE_SNIPPET.format(target=target), db_path=None, url=url)
    assert "UPGRADE_OK" in result.stdout, result.stdout + result.stderr


@requires_postgres
def test_postgres_repaired_schema_is_structurally_identical_to_fresh(postgres_databases):
    """Kernnachweis auf echtem PostgreSQL.

    Eine reparierte Datenbank muss Spalte fuer Spalte identisch zu einer frisch
    migrierten sein -- einschliesslich `column_default`. Genau dieser Vergleich
    ist unter SQLite nicht moeglich und war zuvor unbelegt.
    """
    import sqlalchemy as sa

    repaired_url, fresh_url = postgres_databases

    # Frische Datenbank: kompletter Migrationsweg.
    _alembic_upgrade(fresh_url, "head")

    # Reparierte Datenbank: Baseline, dann Drift erzeugen, dann reparieren.
    _alembic_upgrade(repaired_url, BASELINE_REVISION)
    engine = sa.create_engine(repaired_url)
    with engine.begin() as conn:
        for table, column in DRIFT_COLUMNS:
            conn.execute(sa.text(f"ALTER TABLE {table} DROP COLUMN IF EXISTS {column}"))
        # Bestandszeile, damit der NOT-NULL-Backfill echt geprueft wird.
        conn.execute(
            sa.text(
                "INSERT INTO agent_runs (id, created_at, updated_at, task, "
                "status, run_metadata, result) VALUES ('run-1', now(), now(), "
                "'bestandsauftrag', 'done', '{}', '{}')"
            )
        )
    _alembic_upgrade(repaired_url, "head")

    def columns_of(url: str) -> list[tuple]:
        eng = sa.create_engine(url)
        try:
            with eng.connect() as conn:
                return [tuple(row) for row in conn.execute(sa.text(_COLUMN_QUERY))]
        finally:
            eng.dispose()

    fresh_cols = columns_of(fresh_url)
    repaired_cols = columns_of(repaired_url)

    assert fresh_cols, "Frische Datenbank lieferte keine Spalten"
    assert repaired_cols == fresh_cols, (
        "Reparierte Datenbank weicht strukturell von einer frischen ab.\n"
        f"nur in repariert: {sorted(set(repaired_cols) - set(fresh_cols))}\n"
        f"nur in frisch:    {sorted(set(fresh_cols) - set(repaired_cols))}"
    )
    engine.dispose()


@requires_postgres
def test_postgres_server_defaults_are_removed_after_repair(postgres_databases):
    """`_drop_server_defaults()` wird unter SQLite uebersprungen -- hier wird
    direkt in den PostgreSQL-Metadaten geprueft, dass keine DEFAULT-Klausel
    zurueckbleibt und die Bestandszeile trotzdem korrekt befuellt wurde."""
    import sqlalchemy as sa

    repaired_url, _ = postgres_databases

    _alembic_upgrade(repaired_url, BASELINE_REVISION)
    engine = sa.create_engine(repaired_url)
    with engine.begin() as conn:
        for table, column in DRIFT_COLUMNS:
            conn.execute(sa.text(f"ALTER TABLE {table} DROP COLUMN IF EXISTS {column}"))
        conn.execute(
            sa.text(
                "INSERT INTO agent_runs (id, created_at, updated_at, task, "
                "status, run_metadata, result) VALUES ('run-1', now(), now(), "
                "'bestandsauftrag', 'done', '{}', '{}')"
            )
        )
    _alembic_upgrade(repaired_url, "head")

    with engine.connect() as conn:
        for table, column in _BACKFILLED_NOT_NULL_COLUMNS:
            default = conn.execute(
                sa.text(
                    "SELECT column_default FROM information_schema.columns "
                    "WHERE table_schema='public' AND table_name=:t AND column_name=:c"
                ),
                {"t": table, "c": column},
            ).scalar_one()
            assert default is None, (
                f"{table}.{column} hat nach der Reparatur noch eine "
                f"DEFAULT-Klausel ({default!r}) -- eine frisch angelegte "
                "Datenbank hat dort keine."
            )

        # Bestandsdaten unversehrt, NOT-NULL-Spalte korrekt vorbefuellt.
        row = conn.execute(
            sa.text("SELECT task, tenant_id, owner_user_id FROM agent_runs")
        ).one()
        assert row[0] == "bestandsauftrag", "Bestandsdaten gingen verloren"
        assert row[1] == "default", "NOT-NULL-Spalte wurde nicht vorbefuellt"
        assert row[2] is None, "Nullable-Spalte haette leer bleiben muessen"
    engine.dispose()


def test_no_production_database_is_used_by_these_tests():
    """Schutz-Test: diese Datei darf niemals gegen eine echte DB laufen."""
    path = os.path.abspath(__file__)
    with open(path, encoding="utf-8") as fh:
        source = fh.read()
    # Die Suchmuster werden zusammengesetzt, damit dieser Test nicht an der
    # eigenen Pruefzeile scheitert (die Muster staenden sonst selbst im Quelltext).
    for scheme in ("postgresql" + "://", "postgres" + "://", "mysql" + "://"):
        assert scheme not in source, f"Verdaechtige Datenbank-URL im Test: {scheme}"
    # Jeder Subprozess bekommt eine temporaere SQLite-URL gesetzt.
    assert "AILIZA_DATABASE_URL" in source
    assert 'sqlite:///' in source
