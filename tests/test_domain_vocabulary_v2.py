"""Domain-Vokabular V2: die 22 KMU-Fachbereiche und ihre Einstufung.

Geprueft wird gegen eine echt migrierte Datenbank, nicht gegen die
Konstanten des Migrationsmoduls -- sonst wuerde der Test nur bestaetigen,
dass eine Liste sich selbst gleicht.

Die Sensitivitaet ist kein Schmuckfeld: sie ist die Grundlage, auf die
sich spaetere Governance-Regeln beziehen. Eine stille Absenkung (etwa hr
von confidential auf normal) muss auffallen, deshalb wird jede Stufe
einzeln festgeschrieben.
"""
from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

REVISION = "a4e8b2c15d97"
PARENT = "f9a3c61e07b2"
BACKEND = Path(__file__).resolve().parents[1] / "apps" / "backend"

# Vollstaendiges Zielbild nach V2: 22 Bereiche.
EXPECTED_SENSITIVITY = {
    # hochkritisch
    "management": "confidential",
    "finance": "confidential",
    "accounting": "confidential",
    "controlling": "confidential",
    "invoicing": "confidential",
    "factoring": "confidential",
    "hr": "confidential",
    "legal": "confidential",
    "it_support": "confidential",
    "research_development": "confidential",
    # mittel
    "company_knowledge": "high",
    "sales": "high",
    "marketing": "high",
    "customer_support": "high",
    "procurement": "high",
    "logistics": "high",
    "operations": "high",
    "quality_management": "high",
    # niedriger, aber geschuetzt
    "projects": "normal",
    "tasks": "normal",
    "administration": "normal",
    "facility_management": "normal",
}

NEW_IN_V2 = {
    "management", "operations", "logistics", "it_support", "research_development",
    "customer_support", "quality_management", "administration", "facility_management",
}

RECLASSIFIED_IN_V2 = {"sales", "marketing", "procurement"}


def _alembic(*args: str, database_url: str) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["AILIZA_DATABASE_URL"] = database_url
    env.setdefault("AILIZA_SECRET_KEY", "test-secret-key-minimum-32-chars-ok")
    return subprocess.run([sys.executable, "-m", "alembic", *args],
                          cwd=BACKEND, env=env, capture_output=True, text=True)


@pytest.fixture()
def db_path(tmp_path: Path) -> Path:
    path = tmp_path / "vocab.sqlite"
    result = _alembic("upgrade", "head", database_url=f"sqlite:///{path}")
    assert result.returncode == 0, result.stderr
    return path


def _rows(path: Path) -> dict[str, str]:
    con = sqlite3.connect(path)
    try:
        return {
            code: sens
            for code, sens in con.execute(
                "SELECT code, sensitivity_level FROM business_domains"
            )
        }
    finally:
        con.close()


def test_exactly_one_head_and_revision_in_chain() -> None:
    result = _alembic("heads", database_url="sqlite:///:memory:")
    heads = [line for line in result.stdout.splitlines() if line.strip()]
    assert len(heads) == 1, f"Erwartet genau einen Head, gefunden: {heads}"
    history = _alembic("history", database_url="sqlite:///:memory:")
    assert REVISION in history.stdout


def test_all_22_domains_exist(db_path: Path) -> None:
    codes = set(_rows(db_path))
    assert set(EXPECTED_SENSITIVITY) <= codes, (
        f"Fehlende Bereiche: {sorted(set(EXPECTED_SENSITIVITY) - codes)}"
    )


@pytest.mark.parametrize("code,sensitivity", sorted(EXPECTED_SENSITIVITY.items()))
def test_sensitivity_is_pinned(db_path: Path, code: str, sensitivity: str) -> None:
    """Jede Einstufung einzeln festgeschrieben -- eine stille Absenkung
    einzelner Bereiche wuerde sonst in einer Sammelpruefung untergehen."""
    actual = _rows(db_path).get(code)
    assert actual == sensitivity, (
        f"{code}: erwartet {sensitivity}, tatsaechlich {actual}"
    )


def test_no_domain_is_lower_than_normal(db_path: Path) -> None:
    """Es darf keinen Bereich ohne Schutzstufe geben -- fail-closed."""
    allowed = {"normal", "high", "confidential"}
    for code, sens in _rows(db_path).items():
        assert sens in allowed, f"{code} hat unzulaessige Stufe {sens!r}"


def test_reclassified_domains_are_no_longer_normal(db_path: Path) -> None:
    """sales/marketing/procurement verarbeiten personenbezogene Daten --
    'normal' waere dafuer zu schwach."""
    rows = _rows(db_path)
    for code in RECLASSIFIED_IN_V2:
        assert rows[code] == "high", f"{code} steht auf {rows[code]}, erwartet high"


def test_v2_does_not_grant_any_access(db_path: Path) -> None:
    """Vokabular-Erweiterung ist keine Freischaltung: fail-closed bleibt."""
    con = sqlite3.connect(db_path)
    try:
        for table in ("tenant_business_domains", "user_domain_memberships",
                      "domain_role_permissions"):
            count = con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]  # noqa: S608
            assert count == 0, f"{table} enthaelt {count} Zeilen -- kein Zugriff erwartet"
    finally:
        con.close()


def test_existing_domains_survive_upgrade(db_path: Path) -> None:
    """V2 darf keinen Bestandsbereich entfernen oder umbenennen."""
    codes = set(_rows(db_path))
    for code in ("factoring", "projects", "tasks", "company_knowledge"):
        assert code in codes, f"Bestandsbereich {code} fehlt nach V2"


def test_downgrade_removes_only_new_domains(tmp_path: Path) -> None:
    path = tmp_path / "down.sqlite"
    url = f"sqlite:///{path}"
    assert _alembic("upgrade", "head", database_url=url).returncode == 0
    assert _alembic("downgrade", PARENT, database_url=url).returncode == 0

    rows = _rows(path)
    assert not (NEW_IN_V2 & set(rows)), "Neue Bereiche muessen entfernt sein"
    # Bestand bleibt, Einstufung zurueckgesetzt.
    assert "accounting" in rows
    for code in RECLASSIFIED_IN_V2:
        assert rows[code] == "normal", f"{code} nicht zurueckgestuft"


def test_downgrade_refuses_when_domain_is_in_use(tmp_path: Path) -> None:
    """Fail-closed: ein Bereich mit echter Freischaltung darf nicht
    stillschweigend samt Zugriffsdaten verschwinden."""
    path = tmp_path / "inuse.sqlite"
    url = f"sqlite:///{path}"
    assert _alembic("upgrade", "head", database_url=url).returncode == 0

    con = sqlite3.connect(path)
    try:
        did = con.execute(
            "SELECT id FROM business_domains WHERE code='it_support'"
        ).fetchone()[0]
        con.execute(
            "INSERT INTO tenant_business_domains "
            "(tenant_id, domain_id, is_enabled, reason, version) "
            "VALUES ('t1', ?, 1, 'Testfreischaltung', 1)", (did,)
        )
        con.commit()
    finally:
        con.close()

    result = _alembic("downgrade", PARENT, database_url=url)
    assert result.returncode != 0, "Downgrade haette abgelehnt werden muessen"
    assert ("DomainVocabularyError" in result.stderr
            or "Freischaltungen" in result.stderr)

    # Der Bereich muss noch da sein -- nichts wurde verworfen.
    assert "it_support" in _rows(path)


def test_upgrade_is_idempotent(tmp_path: Path) -> None:
    path = tmp_path / "idem.sqlite"
    url = f"sqlite:///{path}"
    assert _alembic("upgrade", "head", database_url=url).returncode == 0
    before = _rows(path)
    assert _alembic("downgrade", PARENT, database_url=url).returncode == 0
    assert _alembic("upgrade", "head", database_url=url).returncode == 0
    assert _rows(path) == before, "Erneutes Upgrade muss denselben Stand ergeben"
