"""Tests für den Kunde-Baustein (Phase 1, kleinster Schritt von
Kunde -> Artikel -> Rechnung): Anlegen, Liste, Mandanten-Trennung,
Feldverschlüsselung. Kein Artikel-/Rechnungscode Gegenstand dieser Tests.
"""
from __future__ import annotations

import os

os.environ.setdefault("AILIZA_SECRET_KEY", "test-secret-key-minimum-32-chars-ok")
os.environ.setdefault("AILIZA_DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("AILIZA_EXTERNAL_LLM_ENABLED", "false")

import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
ALEMBIC_INI = REPO_ROOT / "apps" / "backend" / "alembic.ini"


@pytest.fixture(autouse=True)
def fresh_db():
    from apps.backend.database import init_db, metadata_obj, engine
    metadata_obj.drop_all(engine)
    init_db()
    yield


def test_create_and_list_customer():
    from apps.backend.database import create_customer, list_customers

    create_customer("kunde-1", "tenant-a", name="Musterladen GmbH", email="info@musterladen.de")
    rows = list_customers("tenant-a")

    assert len(rows) == 1
    assert rows[0]["id"] == "kunde-1"
    assert rows[0]["name"] == "Musterladen GmbH"
    assert rows[0]["email"] == "info@musterladen.de"


def test_customer_fields_are_encrypted_at_rest():
    """Feldverschluesselung wie bei user_projects/user_chats: der Klartext
    darf nicht direkt in der Datenbankzeile stehen."""
    from apps.backend.database import create_customer, engine, customers
    from sqlalchemy import select

    create_customer("kunde-1", "tenant-a", name="Sehr Geheime Kundin AG", email="geheim@example.de")

    with engine.begin() as conn:
        row = conn.execute(
            select(customers).where(customers.c.id == "kunde-1").where(customers.c.tenant_id == "tenant-a")
        ).mappings().first()

    assert row is not None
    assert row["name"] != "Sehr Geheime Kundin AG"
    assert row["name"].startswith("enc:v1:")
    assert row["email"] != "geheim@example.de"
    assert row["email"].startswith("enc:v1:")


def test_tenant_isolation_customer_not_visible_across_tenants():
    """Kernkriterium aus dem Auftrag: keine Kunden ueber Mandantengrenzen
    hinweg sichtbar."""
    from apps.backend.database import create_customer, list_customers

    create_customer("kunde-1", "tenant-a", name="Kunde von A")
    create_customer("kunde-1", "tenant-b", name="Kunde von B")  # gleiche id, anderer Mandant

    rows_a = list_customers("tenant-a")
    rows_b = list_customers("tenant-b")

    assert len(rows_a) == 1
    assert rows_a[0]["name"] == "Kunde von A"
    assert len(rows_b) == 1
    assert rows_b[0]["name"] == "Kunde von B"


def test_same_id_different_tenant_does_not_collide():
    """Zusammengesetzter Primary Key (id, tenant_id): dieselbe id in zwei
    Mandanten darf keinen IntegrityError ausloesen und keine Zeile
    ueberschreiben (Karo-Fund-Muster wie bei user_projects)."""
    from apps.backend.database import create_customer, list_customers

    create_customer("gleiche-id", "tenant-a", name="A")
    create_customer("gleiche-id", "tenant-b", name="B")  # darf NICHT scheitern

    assert list_customers("tenant-a")[0]["name"] == "A"
    assert list_customers("tenant-b")[0]["name"] == "B"


def test_duplicate_id_within_same_tenant_rejected():
    """Kein stilles Ueberschreiben eines bestehenden Kunden -- create_customer
    ist bewusst kein Upsert."""
    import sqlalchemy.exc
    from apps.backend.database import create_customer

    create_customer("kunde-1", "tenant-a", name="Original")
    with pytest.raises(sqlalchemy.exc.IntegrityError):
        create_customer("kunde-1", "tenant-a", name="Ueberschrieben")


def test_owner_filter_narrows_list():
    from apps.backend.database import create_customer, list_customers

    create_customer("kunde-1", "tenant-a", name="Kunde von Alice", owner_user_id="alice")
    create_customer("kunde-2", "tenant-a", name="Kunde von Bob", owner_user_id="bob")

    rows = list_customers("tenant-a", owner_user_id="alice")
    assert len(rows) == 1
    assert rows[0]["id"] == "kunde-1"


def test_customer_migration_on_fresh_and_existing_database(tmp_path):
    """Migration 0005 muss sowohl auf einer frischen als auch auf einer
    bereits vorhandenen (Stand vor customers) Datenbank sauber laufen,
    ohne bestehende Daten zu veraendern."""
    db_path = tmp_path / "existing.sqlite"
    db_url = f"sqlite:///{db_path}"
    env = os.environ.copy()
    env["AILIZA_DATABASE_URL"] = db_url

    # 1. Bestehende Datenbank auf Stand VOR customers (0004) simulieren.
    subprocess.run(
        [sys.executable, "-m", "alembic", "-c", str(ALEMBIC_INI), "upgrade", "d8f4c6a91b27"],
        cwd=REPO_ROOT / "apps" / "backend", env=env, check=True, capture_output=True, text=True, timeout=60,
    )

    from sqlalchemy import create_engine
    engine = create_engine(db_url)
    with engine.begin() as conn:
        conn.exec_driver_sql(
            "INSERT INTO audit_logs (timestamp, action, metadata, tenant_id, previous_hash, entry_hash) "
            "VALUES ('2026-01-01T00:00:00+00:00', 'test.action', '{}', 'default', '00', '11')"
        )
    engine.dispose()

    # 2. Migration auf head (inkl. customers) ausfuehren.
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "-c", str(ALEMBIC_INI), "upgrade", "head"],
        cwd=REPO_ROOT / "apps" / "backend", env=env, check=True, capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0, result.stderr

    # 3. customers-Tabelle existiert, bestehende audit_logs-Zeile unveraendert.
    engine = create_engine(db_url)
    with engine.begin() as conn:
        tables = {row[0] for row in conn.exec_driver_sql(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).all()}
        assert "customers" in tables
        assert conn.exec_driver_sql("SELECT COUNT(*) FROM audit_logs").scalar() == 1
        assert conn.exec_driver_sql("SELECT action FROM audit_logs").scalar() == "test.action"
    engine.dispose()


def test_customer_migration_downgrade_removes_table_cleanly(tmp_path):
    db_path = tmp_path / "downgrade.sqlite"
    db_url = f"sqlite:///{db_path}"
    env = os.environ.copy()
    env["AILIZA_DATABASE_URL"] = db_url

    subprocess.run(
        [sys.executable, "-m", "alembic", "-c", str(ALEMBIC_INI), "upgrade", "head"],
        cwd=REPO_ROOT / "apps" / "backend", env=env, check=True, capture_output=True, text=True, timeout=60,
    )
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "-c", str(ALEMBIC_INI), "downgrade", "d8f4c6a91b27"],
        cwd=REPO_ROOT / "apps" / "backend", env=env, check=True, capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0, result.stderr

    from sqlalchemy import create_engine
    engine = create_engine(db_url)
    with engine.begin() as conn:
        tables = {row[0] for row in conn.exec_driver_sql(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).all()}
        assert "customers" not in tables
    engine.dispose()
