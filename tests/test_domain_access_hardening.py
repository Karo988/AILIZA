"""Stufe A: datenbankseitige Schutzregeln der Bereichsrechte.

Die Constraints sind die letzte Verteidigungslinie: sie greifen auch dann,
wenn ein Anwendungspfad sie umgeht. Deshalb wird hier direkt per SQL gegen
sie geschrieben, nicht ueber Anwendungsfunktionen.

Negative Faelle laufen ueber Testdaten, nicht durch Manipulation
produktiver Dateien.
"""
from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

REVISION = "e7c2b45d81a3"
PARENT = "d4a1f7b93c20"
BACKEND = Path(__file__).resolve().parents[1] / "apps" / "backend"


def _alembic(*args: str, database_url: str) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["AILIZA_DATABASE_URL"] = database_url
    env.setdefault("AILIZA_SECRET_KEY", "test-secret-key-minimum-32-chars-ok")
    return subprocess.run([sys.executable, "-m", "alembic", *args],
                          cwd=BACKEND, env=env, capture_output=True, text=True)


@pytest.fixture()
def db(tmp_path: Path):
    path = tmp_path / "hard.sqlite"
    result = _alembic("upgrade", "head", database_url=f"sqlite:///{path}")
    assert result.returncode == 0, result.stderr
    con = sqlite3.connect(path)
    con.execute("PRAGMA foreign_keys=ON")
    try:
        yield con
    finally:
        con.close()


def _domain_id(con: sqlite3.Connection, code: str = "accounting") -> int:
    return con.execute("SELECT id FROM business_domains WHERE code=?", (code,)).fetchone()[0]


def _member_sql(extra_cols: str = "", extra_vals: str = "") -> str:
    return (
        "INSERT INTO user_domain_memberships "
        f"(tenant_id, domain_id, user_id, role_in_domain, valid_from, "
        f"assigned_by, assignment_reason, is_active, version{extra_cols}) "
        f"VALUES (?, ?, ?, ?, '2026-01-01', 'admin', 'Grund', 1, 1{extra_vals})"
    )


def test_exactly_one_head() -> None:
    result = _alembic("heads", database_url="sqlite:///:memory:")
    heads = [line for line in result.stdout.splitlines() if line.strip()]
    assert len(heads) == 1 and REVISION in heads[0]


def test_invalid_role_is_rejected(db: sqlite3.Connection) -> None:
    with pytest.raises(sqlite3.IntegrityError):
        db.execute(_member_sql(), ("t1", _domain_id(db), "u1", "superuser"))


@pytest.mark.parametrize("role", ["viewer", "contributor", "reviewer", "domain_manager"])
def test_valid_roles_are_accepted(db: sqlite3.Connection, role: str) -> None:
    db.execute(_member_sql(), ("t1", _domain_id(db), f"u_{role}", role))


def test_invalid_action_is_rejected(db: sqlite3.Connection) -> None:
    with pytest.raises(sqlite3.IntegrityError):
        db.execute(
            "INSERT INTO domain_role_permissions "
            "(tenant_id, domain_id, role_in_domain, action, allowed, version) "
            "VALUES ('t1', ?, 'viewer', 'content.destroy', 1, 1)", (_domain_id(db),)
        )


@pytest.mark.parametrize("action", [
    "domain.view", "content.read", "content.create", "content.update",
    "content.approve", "content.export", "action.execute", "membership.manage",
])
def test_valid_actions_are_accepted(db: sqlite3.Connection, action: str) -> None:
    db.execute(
        "INSERT INTO domain_role_permissions "
        "(tenant_id, domain_id, role_in_domain, action, allowed, version) "
        "VALUES ('t1', ?, 'viewer', ?, 1, 1)", (_domain_id(db), action)
    )


def test_active_and_revoked_is_contradictory(db: sqlite3.Connection) -> None:
    """is_active=1 zusammen mit revoked_at waere ein widerrufener Zugriff,
    der weiter gilt -- genau der Zustand, der einen Widerruf wirkungslos
    machen wuerde."""
    with pytest.raises(sqlite3.IntegrityError):
        db.execute(
            _member_sql(", revoked_at", ", '2026-02-01'"),
            ("t1", _domain_id(db), "u2", "viewer"),
        )


def test_revoked_membership_is_allowed_when_inactive(db: sqlite3.Connection) -> None:
    db.execute(
        "INSERT INTO user_domain_memberships "
        "(tenant_id, domain_id, user_id, role_in_domain, valid_from, assigned_by, "
        " assignment_reason, is_active, revoked_at, revoked_by, revocation_reason, version) "
        "VALUES ('t1', ?, 'u3', 'viewer', '2026-01-01', 'admin', 'Grund', 0, "
        "'2026-02-01', 'admin', 'Austritt', 1)", (_domain_id(db),)
    )


def test_validity_period_must_be_ordered(db: sqlite3.Connection) -> None:
    with pytest.raises(sqlite3.IntegrityError):
        db.execute(
            _member_sql(", valid_until", ", '2025-01-01'"),
            ("t1", _domain_id(db), "u4", "viewer"),
        )


def test_only_one_active_membership_per_user_and_domain(db: sqlite3.Connection) -> None:
    did = _domain_id(db)
    db.execute(_member_sql(), ("t1", did, "u5", "viewer"))
    with pytest.raises(sqlite3.IntegrityError):
        db.execute(_member_sql(), ("t1", did, "u5", "contributor"))


def test_revoked_history_does_not_block_new_membership(db: sqlite3.Connection) -> None:
    """Widerrufene Zeilen bleiben als Nachweis erhalten und duerfen eine
    spaetere Neuzuweisung nicht verhindern."""
    did = _domain_id(db)
    db.execute(
        "INSERT INTO user_domain_memberships "
        "(tenant_id, domain_id, user_id, role_in_domain, valid_from, assigned_by, "
        " assignment_reason, is_active, revoked_at, version) "
        "VALUES ('t1', ?, 'u6', 'viewer', '2026-01-01', 'admin', 'Grund', 0, "
        "'2026-02-01', 1)", (did,)
    )
    db.execute(_member_sql(), ("t1", did, "u6", "reviewer"))


def test_same_user_in_two_tenants_stays_separate(db: sqlite3.Connection) -> None:
    did = _domain_id(db)
    db.execute(_member_sql(), ("t1", did, "gleiche_kennung", "viewer"))
    db.execute(_member_sql(), ("t2", did, "gleiche_kennung", "domain_manager"))


def test_downgrade_then_reupgrade(tmp_path: Path) -> None:
    url = f"sqlite:///{tmp_path / 'rt.sqlite'}"
    assert _alembic("upgrade", "head", database_url=url).returncode == 0
    assert _alembic("downgrade", PARENT, database_url=url).returncode == 0
    assert _alembic("upgrade", "head", database_url=url).returncode == 0


def test_migration_stops_when_domain_tables_hold_data(tmp_path: Path) -> None:
    """Fail-closed: unter SQLite werden Tabellen rekonstruiert. Mit echten
    Rechtezuweisungen darf das nicht unbemerkt laufen."""
    path = tmp_path / "guard.sqlite"
    url = f"sqlite:///{path}"
    assert _alembic("upgrade", PARENT, database_url=url).returncode == 0

    con = sqlite3.connect(path)
    try:
        did = con.execute("SELECT id FROM business_domains WHERE code='hr'").fetchone()[0]
        con.execute(
            "INSERT INTO tenant_business_domains (tenant_id, domain_id, is_enabled, version) "
            "VALUES ('t1', ?, 1, 1)", (did,)
        )
        con.commit()
    finally:
        con.close()

    result = _alembic("upgrade", "head", database_url=url)
    assert result.returncode != 0
    assert "DomainTablesNotEmpty" in result.stderr or "bereits Daten" in result.stderr
