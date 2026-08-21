"""Stufe-A-Korrektur: vollstaendige Wertebereiche und Begruendungspflicht.

Zusaetzlich wird nachgewiesen, dass eine ueber SQLAlchemy-Metadaten
erzeugte Datenbank (create_all) dieselben Schutzregeln besitzt wie eine
migrierte -- sonst waeren neu angelegte Instanzen schwaecher geschuetzt.

PostgreSQL laeuft ueber denselben Testkoerper, sofern
AILIZA_TEST_POSTGRES_ADMIN_URL gesetzt ist (in CI verpflichtend).
"""
from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

REVISION = "f9a3c61e07b2"
PARENT = "e7c2b45d81a3"
BACKEND = Path(__file__).resolve().parents[1] / "apps" / "backend"

pg_only = pytest.mark.skipif(
    not os.getenv("AILIZA_TEST_POSTGRES_ADMIN_URL"),
    reason="AILIZA_TEST_POSTGRES_ADMIN_URL nicht gesetzt",
)


def _alembic(*args: str, database_url: str) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["AILIZA_DATABASE_URL"] = database_url
    env.setdefault("AILIZA_SECRET_KEY", "test-secret-key-minimum-32-chars-ok")
    return subprocess.run([sys.executable, "-m", "alembic", *args],
                          cwd=BACKEND, env=env, capture_output=True, text=True)


@pytest.fixture()
def db(tmp_path: Path):
    path = tmp_path / "c.sqlite"
    result = _alembic("upgrade", "head", database_url=f"sqlite:///{path}")
    assert result.returncode == 0, result.stderr
    con = sqlite3.connect(path)
    try:
        yield con
    finally:
        con.close()


def _did(con: sqlite3.Connection, code: str = "hr") -> int:
    return con.execute("SELECT id FROM business_domains WHERE code=?", (code,)).fetchone()[0]


def test_exactly_one_head() -> None:
    """Genau ein Head -- welche Revision der Head IST, wandert mit jeder
    neuen Migration weiter. Geprueft wird daher die Kette, nicht die
    Head-Position dieser Revision."""
    result = _alembic("heads", database_url="sqlite:///:memory:")
    heads = [line for line in result.stdout.splitlines() if line.strip()]
    assert len(heads) == 1, f"Erwartet genau einen Head, gefunden: {heads}"

    history = _alembic("history", database_url="sqlite:///:memory:")
    assert REVISION in history.stdout


@pytest.mark.parametrize("level", ["geheim", "", "NORMAL"])
def test_invalid_sensitivity_rejected(db: sqlite3.Connection, level: str) -> None:
    with pytest.raises(sqlite3.IntegrityError):
        db.execute(
            "INSERT INTO business_domains (code, name, sensitivity_level, "
            "is_system_domain, created_at, updated_at) "
            "VALUES ('neu', 'Neu', ?, 1, '2026-01-01', '2026-01-01')", (level,)
        )


@pytest.mark.parametrize("level", ["normal", "high", "confidential"])
def test_valid_sensitivity_accepted(db: sqlite3.Connection, level: str) -> None:
    db.execute(
        "INSERT INTO business_domains (code, name, sensitivity_level, "
        "is_system_domain, created_at, updated_at) "
        "VALUES (?, 'Neu', ?, 1, '2026-01-01', '2026-01-01')", (f"neu_{level}", level)
    )


@pytest.mark.parametrize("flag", [2, 7, -1])
def test_boolean_flags_reject_other_values(db: sqlite3.Connection, flag: int) -> None:
    with pytest.raises(sqlite3.IntegrityError):
        db.execute(
            "INSERT INTO tenant_business_domains "
            "(tenant_id, domain_id, is_enabled, reason, version) "
            "VALUES ('t1', ?, ?, 'Grund', 1)", (_did(db), flag)
        )


@pytest.mark.parametrize("reason", ["", "   ", "\t"])
def test_blank_activation_reason_rejected(db: sqlite3.Connection, reason: str) -> None:
    """NOT NULL allein genuegt nicht: eine leere Angabe waere keine
    Begruendung und wuerde die Nachvollziehbarkeit aushebeln."""
    with pytest.raises(sqlite3.IntegrityError):
        db.execute(
            "INSERT INTO tenant_business_domains "
            "(tenant_id, domain_id, is_enabled, reason, version) "
            "VALUES ('t1', ?, 1, ?, 1)", (_did(db), reason)
        )


def test_activation_reason_is_required(db: sqlite3.Connection) -> None:
    with pytest.raises(sqlite3.IntegrityError):
        db.execute(
            "INSERT INTO tenant_business_domains "
            "(tenant_id, domain_id, is_enabled, version) VALUES ('t1', ?, 1, 1)",
            (_did(db),)
        )


def test_valid_activation_accepted(db: sqlite3.Connection) -> None:
    db.execute(
        "INSERT INTO tenant_business_domains "
        "(tenant_id, domain_id, is_enabled, reason, version) "
        "VALUES ('t1', ?, 1, 'Freigabe durch Geschaeftsfuehrung', 1)", (_did(db),)
    )


def test_permission_row_requires_reason(db: sqlite3.Connection) -> None:
    with pytest.raises(sqlite3.IntegrityError):
        db.execute(
            "INSERT INTO domain_role_permissions "
            "(tenant_id, domain_id, role_in_domain, action, allowed, reason, version) "
            "VALUES ('t1', ?, 'viewer', 'content.read', 1, '  ', 1)", (_did(db),)
        )


def test_permission_allowed_flag_is_boolean(db: sqlite3.Connection) -> None:
    with pytest.raises(sqlite3.IntegrityError):
        db.execute(
            "INSERT INTO domain_role_permissions "
            "(tenant_id, domain_id, role_in_domain, action, allowed, reason, version) "
            "VALUES ('t1', ?, 'viewer', 'content.read', 5, 'Grund', 1)", (_did(db),)
        )


def test_revocation_requires_reason(db: sqlite3.Connection) -> None:
    """Ein Widerruf ohne Begruendung waere im Audit nicht nachvollziehbar."""
    with pytest.raises(sqlite3.IntegrityError):
        db.execute(
            "INSERT INTO user_domain_memberships "
            "(tenant_id, domain_id, user_id, role_in_domain, valid_from, assigned_by, "
            " assignment_reason, is_active, revoked_at, version) "
            "VALUES ('t1', ?, 'u1', 'viewer', '2026-01-01', 'admin', 'Grund', 0, "
            "'2026-02-01', 1)", (_did(db),)
        )


def test_revocation_with_reason_accepted(db: sqlite3.Connection) -> None:
    db.execute(
        "INSERT INTO user_domain_memberships "
        "(tenant_id, domain_id, user_id, role_in_domain, valid_from, assigned_by, "
        " assignment_reason, is_active, revoked_at, revoked_by, revocation_reason, version) "
        "VALUES ('t1', ?, 'u2', 'viewer', '2026-01-01', 'admin', 'Grund', 0, "
        "'2026-02-01', 'admin', 'Austritt', 1)", (_did(db),)
    )


def test_assignment_reason_must_not_be_blank(db: sqlite3.Connection) -> None:
    with pytest.raises(sqlite3.IntegrityError):
        db.execute(
            "INSERT INTO user_domain_memberships "
            "(tenant_id, domain_id, user_id, role_in_domain, valid_from, assigned_by, "
            " assignment_reason, is_active, version) "
            "VALUES ('t1', ?, 'u3', 'viewer', '2026-01-01', 'admin', '   ', 1, 1)",
            (_did(db),)
        )


def test_metadata_and_migration_define_same_constraints(tmp_path: Path) -> None:
    """Eine ueber create_all() erzeugte Datenbank darf nicht schwaecher sein
    als eine migrierte -- sonst haetten frische Instanzen weniger Schutz."""
    sys.path.insert(0, str(BACKEND))
    try:
        import sqlalchemy as sa

        from db_schema import metadata_obj  # type: ignore[import-not-found]
    finally:
        sys.path.pop(0)

    meta_path = tmp_path / "meta.sqlite"
    engine = sa.create_engine(f"sqlite:///{meta_path}")
    metadata_obj.create_all(engine)
    engine.dispose()

    mig_path = tmp_path / "mig.sqlite"
    assert _alembic("upgrade", "head", database_url=f"sqlite:///{mig_path}").returncode == 0

    def constraint_names(path: Path) -> set[str]:
        con = sqlite3.connect(path)
        try:
            names: set[str] = set()
            for table in ("business_domains", "tenant_business_domains",
                          "user_domain_memberships", "domain_role_permissions"):
                sql = con.execute(
                    "SELECT sql FROM sqlite_master WHERE type='table' AND name=?",
                    (table,)
                ).fetchone()[0]
                names |= {
                    part.split()[0]
                    for part in sql.split("CONSTRAINT ")[1:]
                }
            return names
        finally:
            con.close()

    from_metadata = constraint_names(meta_path)
    from_migration = constraint_names(mig_path)
    missing = from_migration - from_metadata
    assert not missing, (
        f"db_schema.py fehlen Constraints, die die Migration setzt: {missing}"
    )


def test_guard_blocks_invalid_existing_data(tmp_path: Path) -> None:
    """Gueltige Bestandsdaten passieren, ungueltige stoppen fail-closed --
    ohne zu raten, zu korrigieren oder zu loeschen."""
    path = tmp_path / "guard.sqlite"
    url = f"sqlite:///{path}"
    assert _alembic("upgrade", PARENT, database_url=url).returncode == 0

    con = sqlite3.connect(path)
    try:
        did = con.execute("SELECT id FROM business_domains WHERE code='hr'").fetchone()[0]
        # Vor der Korrektur war eine leere Begruendung noch moeglich.
        con.execute(
            "INSERT INTO tenant_business_domains "
            "(tenant_id, domain_id, is_enabled, reason, version) "
            "VALUES ('t1', ?, 1, '', 1)", (did,)
        )
        con.commit()
    finally:
        con.close()

    result = _alembic("upgrade", "head", database_url=url)
    assert result.returncode != 0
    assert "DomainDataViolatesNewRules" in result.stderr or "verletzen" in result.stderr

    # Nichts wurde veraendert oder geloescht.
    con = sqlite3.connect(path)
    try:
        assert con.execute(
            "SELECT COUNT(*) FROM tenant_business_domains"
        ).fetchone()[0] == 1
    finally:
        con.close()


def test_valid_existing_data_passes_migration(tmp_path: Path) -> None:
    path = tmp_path / "ok.sqlite"
    url = f"sqlite:///{path}"
    assert _alembic("upgrade", PARENT, database_url=url).returncode == 0

    con = sqlite3.connect(path)
    try:
        did = con.execute("SELECT id FROM business_domains WHERE code='hr'").fetchone()[0]
        con.execute(
            "INSERT INTO tenant_business_domains "
            "(tenant_id, domain_id, is_enabled, reason, version) "
            "VALUES ('t1', ?, 1, 'Gueltiger Grund', 1)", (did,)
        )
        con.commit()
    finally:
        con.close()

    result = _alembic("upgrade", "head", database_url=url)
    assert result.returncode == 0, result.stderr

    con = sqlite3.connect(path)
    try:
        assert con.execute(
            "SELECT COUNT(*) FROM tenant_business_domains"
        ).fetchone()[0] == 1, "Bestandsdaten muessen die Rekonstruktion ueberleben"
    finally:
        con.close()


def test_downgrade_then_reupgrade(tmp_path: Path) -> None:
    url = f"sqlite:///{tmp_path / 'rt.sqlite'}"
    assert _alembic("upgrade", "head", database_url=url).returncode == 0
    assert _alembic("downgrade", PARENT, database_url=url).returncode == 0
    assert _alembic("upgrade", "head", database_url=url).returncode == 0


@pg_only
def test_postgres_enforces_same_constraints() -> None:
    """Nachweis in der Testdatei statt nur manuell: PostgreSQL weist
    dieselben ungueltigen Werte ab wie SQLite."""
    import sqlalchemy as sa

    admin_url = os.environ["AILIZA_TEST_POSTGRES_ADMIN_URL"]
    db_name = "ailiza_domain_constraints_test"
    admin = sa.create_engine(admin_url, isolation_level="AUTOCOMMIT")
    with admin.connect() as con:
        con.execute(sa.text(f"DROP DATABASE IF EXISTS {db_name}"))
        con.execute(sa.text(f"CREATE DATABASE {db_name}"))
    admin.dispose()

    target = admin_url.rsplit("/", 1)[0] + "/" + db_name
    assert _alembic("upgrade", "head", database_url=target).returncode == 0

    engine = sa.create_engine(target)
    try:
        with engine.connect() as con:
            did = con.execute(
                sa.text("SELECT id FROM business_domains WHERE code='hr'")
            ).scalar_one()
            for stmt, params in [
                ("INSERT INTO tenant_business_domains "
                 "(tenant_id, domain_id, is_enabled, reason, version) "
                 "VALUES ('t1', :d, 1, '   ', 1)", {"d": did}),
                ("INSERT INTO tenant_business_domains "
                 "(tenant_id, domain_id, is_enabled, reason, version) "
                 "VALUES ('t2', :d, 7, 'Grund', 1)", {"d": did}),
                ("INSERT INTO domain_role_permissions "
                 "(tenant_id, domain_id, role_in_domain, action, allowed, reason, version) "
                 "VALUES ('t1', :d, 'viewer', 'content.read', 5, 'Grund', 1)", {"d": did}),
            ]:
                with pytest.raises(sa.exc.IntegrityError):
                    con.execute(sa.text(stmt), params)
                con.rollback()
    finally:
        engine.dispose()
