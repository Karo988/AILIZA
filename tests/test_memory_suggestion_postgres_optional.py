"""Optionaler Postgres-Nebenlaeufigkeitstest fuer M2/M2b.

In dieser Umgebung ist keine Postgres-Instanz verfuegbar (siehe
docs/HANDOFF_DATENBANK_GEDAECHTNIS.md: Neon/Postgres nur Uebergangsloesung
fuer Render-Staging, autarker Betrieb primaer SQLite). Dieser Test bleibt
daher hier NICHT ausgefuehrt -- er wird uebersprungen, solange die
Umgebungsvariable AILIZA_TEST_POSTGRES_URL nicht gesetzt ist.

Zweck: dieselben Nebenlaeufigkeits-Garantien wie
tests/test_memory_suggestion_concurrency.py (Datei-SQLite, getrennte
Connections) zusaetzlich gegen echtes Postgres nachweisen -- dort greift
KEIN Python-Prozess-Lock mehr (ausser man startet die Tests aus demselben
Prozess wie hier), die Atomaritaet muss dann ausschliesslich aus der
WHERE-Klausel + Rowcount-Pruefung + partiellem Unique-Index (inkl.
postgresql_where, siehe memory_suggestion_delegations) kommen.

CI-Anbindung (optional, nicht Teil des Pflicht-Testlaufs): ein separater
GitHub-Actions-Job kann einen `postgres:`-Service-Container starten und
AILIZA_TEST_POSTGRES_URL setzen, siehe Kommentar in .github/workflows/ci.yml."""
from __future__ import annotations

import os
import threading

import pytest
from sqlalchemy import create_engine, select

POSTGRES_URL = os.environ.get("AILIZA_TEST_POSTGRES_URL")

pytestmark = pytest.mark.skipif(
    not POSTGRES_URL,
    reason="AILIZA_TEST_POSTGRES_URL nicht gesetzt -- keine Postgres-Instanz in dieser Umgebung verfuegbar.",
)

os.environ.setdefault("AILIZA_SECRET_KEY", "test-secret-key-minimum-32-chars-ok")
os.environ.setdefault("AILIZA_DATABASE_URL", "sqlite:///:memory:")


@pytest.fixture
def postgres_db():
    import apps.backend.database as dbmod

    pg_engine = create_engine(POSTGRES_URL)
    old_engine = dbmod.engine
    dbmod.engine = pg_engine
    try:
        dbmod.metadata_obj.drop_all(pg_engine)
        dbmod.init_db()
        yield dbmod
    finally:
        dbmod.metadata_obj.drop_all(pg_engine)
        dbmod.engine = old_engine


def test_concurrent_double_confirm_no_duplicate_item_on_postgres(postgres_db):
    dbmod = postgres_db
    dbmod.create_user(user_id="alice", tenant_id="default", role="user", hashed_password="hash")
    dbmod.create_user(user_id="admin1", tenant_id="default", role="admin", hashed_password="hash")
    s = dbmod.create_memory_suggestion(
        user_id="alice", tenant_id="default", suggested_scope="company_memory",
        suggested_title="DATEV", suggested_content="Firma nutzt DATEV.",
        suggested_purpose="Kontext", source_type="user_confirmation",
    )

    outcomes = []

    def _confirm():
        try:
            dbmod.confirm_memory_suggestion(s["id"], confirmed_by="admin1", tenant_id="default")
            outcomes.append("ok")
        except dbmod.MemoryValidationError:
            outcomes.append("denied")

    threads = [threading.Thread(target=_confirm) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)

    assert outcomes.count("ok") == 1
    assert outcomes.count("denied") == 1
    with dbmod.engine.begin() as conn:
        items = conn.execute(select(dbmod.memory_items)).mappings().all()
    assert len(items) == 1


def test_delegation_unique_index_enforced_on_postgres(postgres_db):
    """Verifiziert speziell die in der Planung gefundene Postgres-Falle:
    ohne postgresql_where wuerde der Unique-Index nach Revoke/Completion
    dauerhaft blockieren. memory_suggestion_delegations hat BEIDE
    _where-Klauseln -- eine zweite Delegation nach Abschluss der ersten
    muss moeglich sein."""
    dbmod = postgres_db
    dbmod.create_user(user_id="alice", tenant_id="default", role="user", hashed_password="hash")
    dbmod.create_user(user_id="admin1", tenant_id="default", role="admin", hashed_password="hash")
    dbmod.create_user(user_id="bob", tenant_id="default", role="user", hashed_password="hash")
    dbmod.create_user(user_id="carol", tenant_id="default", role="user", hashed_password="hash")
    s = dbmod.create_memory_suggestion(
        user_id="alice", tenant_id="default", suggested_scope="company_memory",
        suggested_title="DATEV", suggested_content="Firma nutzt DATEV.",
        suggested_purpose="Kontext", source_type="user_confirmation",
    )
    d1 = dbmod.create_memory_suggestion_delegation(
        s["id"], tenant_id="default", delegated_by_user_id="admin1", delegated_to_user_id="bob",
    )
    dbmod.revoke_memory_suggestion_delegation(d1["id"], tenant_id="default", revoking_user_id="admin1")
    # Nach Revoke MUSS eine neue Delegation fuer denselben Vorschlag moeglich
    # sein -- waere der Index unter Postgres nicht partiell, wuerde dieser
    # zweite Insert mit IntegrityError scheitern.
    d2 = dbmod.create_memory_suggestion_delegation(
        s["id"], tenant_id="default", delegated_by_user_id="admin1", delegated_to_user_id="carol",
    )
    assert d2["status"] == "active"
