"""Migrationstests fuer Bereichsfreischaltung und Rechteverwaltung V1.

Geprueft wird ausschliesslich die Migration d4a1f7b93c20: dass die vier
Tabellen entstehen, das feste Bereichsvokabular vollstaendig und idempotent
eingespielt wird und Downgrade/Re-Upgrade verlustfrei sind.

Bewusst NICHT geprueft: Rechtevergabe oder Zugriffsentscheidungen -- die
zentrale Entscheidungsfunktion ist noch nicht Teil dieses Pakets. Ohne sie
gilt weiterhin fail-closed "kein Zugriff", weil keine Mitgliedschaft und
keine Rechtezeile angelegt wird.
"""
from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

REVISION = "d4a1f7b93c20"
PARENT = "c8ff9bb332ba"
BACKEND = Path(__file__).resolve().parents[1] / "apps" / "backend"

EXPECTED_TABLES = {
    "business_domains",
    "tenant_business_domains",
    "user_domain_memberships",
    "domain_role_permissions",
}

EXPECTED_CODES = {
    "accounting", "invoicing", "factoring", "finance", "controlling",
    "marketing", "sales", "procurement", "hr", "legal",
    "projects", "tasks", "company_knowledge",
}


def _alembic(*args: str, database_url: str) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["AILIZA_DATABASE_URL"] = database_url
    env.setdefault("AILIZA_SECRET_KEY", "test-secret-key-minimum-32-chars-ok")
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=BACKEND, env=env, capture_output=True, text=True,
    )


@pytest.fixture()
def db_url(tmp_path: Path) -> str:
    return f"sqlite:///{tmp_path / 'dac.sqlite'}"


def _sqlite_path(db_url: str) -> str:
    return db_url.replace("sqlite:///", "")


def test_exactly_one_head_and_revision_in_chain() -> None:
    """Genau ein Head -- welche Revision der Head IST, wandert mit jeder
    neuen Migration weiter. Geprueft wird daher die Kette, nicht die
    Head-Position dieser Revision."""
    result = _alembic("heads", database_url="sqlite:///:memory:")
    assert result.returncode == 0, result.stderr
    heads = [line for line in result.stdout.splitlines() if line.strip()]
    assert len(heads) == 1, f"Erwartet genau einen Head, gefunden: {heads}"

    history = _alembic("history", database_url="sqlite:///:memory:")
    assert REVISION in history.stdout


def test_upgrade_creates_tables_and_seeds_domains(db_url: str) -> None:
    result = _alembic("upgrade", "head", database_url=db_url)
    assert result.returncode == 0, result.stderr

    con = sqlite3.connect(_sqlite_path(db_url))
    try:
        tables = {
            row[0]
            for row in con.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        assert EXPECTED_TABLES <= tables

        # Teilmengenpruefung, keine Gleichheit: spaetere Migrationen duerfen
        # das Vokabular erweitern (siehe a4e8b2c15d97). Geprueft wird, dass
        # DIESE Revision ihre 13 Codes vollstaendig einspielt -- nicht, dass
        # sie die einzigen im System bleiben.
        codes = {row[0] for row in con.execute("SELECT code FROM business_domains")}
        assert EXPECTED_CODES <= codes, f"Fehlend: {sorted(EXPECTED_CODES - codes)}"

        # Fail-closed: die Migration vergibt keinerlei Zugriff.
        assert con.execute("SELECT COUNT(*) FROM user_domain_memberships").fetchone()[0] == 0
        assert con.execute("SELECT COUNT(*) FROM domain_role_permissions").fetchone()[0] == 0
        assert con.execute("SELECT COUNT(*) FROM tenant_business_domains").fetchone()[0] == 0
    finally:
        con.close()


def test_domain_code_is_unique(db_url: str) -> None:
    assert _alembic("upgrade", "head", database_url=db_url).returncode == 0
    con = sqlite3.connect(_sqlite_path(db_url))
    try:
        with pytest.raises(sqlite3.IntegrityError):
            con.execute(
                "INSERT INTO business_domains "
                "(code, name, sensitivity_level, is_system_domain, created_at, updated_at) "
                "VALUES ('accounting', 'Doppelt', 'normal', 1, '2026-01-01', '2026-01-01')"
            )
    finally:
        con.close()


def test_tenant_domain_pair_is_unique(db_url: str) -> None:
    assert _alembic("upgrade", "head", database_url=db_url).returncode == 0
    con = sqlite3.connect(_sqlite_path(db_url))
    try:
        did = con.execute(
            "SELECT id FROM business_domains WHERE code='accounting'"
        ).fetchone()[0]
        con.execute(
            "INSERT INTO tenant_business_domains "
            "(tenant_id, domain_id, is_enabled, reason, version) "
            "VALUES ('t1', ?, 1, 'Testfreigabe', 1)", (did,)
        )
        with pytest.raises(sqlite3.IntegrityError):
            con.execute(
                "INSERT INTO tenant_business_domains "
                "(tenant_id, domain_id, is_enabled, reason, version) "
                "VALUES ('t1', ?, 1, 'Testfreigabe', 1)", (did,)
            )
    finally:
        con.close()


def test_downgrade_then_reupgrade_is_idempotent(db_url: str) -> None:
    assert _alembic("upgrade", "head", database_url=db_url).returncode == 0
    assert _alembic("downgrade", PARENT, database_url=db_url).returncode == 0

    con = sqlite3.connect(_sqlite_path(db_url))
    try:
        tables = {
            row[0]
            for row in con.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        assert not (EXPECTED_TABLES & tables), "Downgrade muss alle vier Tabellen entfernen"
    finally:
        con.close()

    assert _alembic("upgrade", "head", database_url=db_url).returncode == 0
    con = sqlite3.connect(_sqlite_path(db_url))
    try:
        rows = [row[0] for row in con.execute("SELECT code FROM business_domains")]
        codes = set(rows)
        # Kernaussage dieses Tests: keine Verdopplung durch Re-Upgrade.
        # Als Menge vs. Liste geprueft, damit ein doppelt eingespielter Code
        # auffaellt -- eine reine Mengenpruefung wuerde ihn verschlucken.
        assert len(rows) == len(codes), (
            f"Startwerte verdoppelt: {sorted(c for c in codes if rows.count(c) > 1)}"
        )
        assert EXPECTED_CODES <= codes, f"Fehlend: {sorted(EXPECTED_CODES - codes)}"
    finally:
        con.close()
