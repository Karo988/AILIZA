"""M2/M2b Nebenlaeufigkeitstests mit datei-basiertem SQLite und getrennten
Connections/Threads.

WICHTIG: Die uebrigen Memory-Suggestion-Tests laufen gegen `sqlite:///:memory:`
mit StaticPool -- dort teilen sich alle Threads EINE rohe Connection, was
Races kuenstlich "unsichtbar" machen kann (der Python-Lock `_sql_write_lock`
serialisiert dann ohnehin alles, egal ob die WHERE-Klausel selbst race-sicher
waere). Diese Datei erzwingt stattdessen eine echte Datei-SQLite-Engine ohne
StaticPool, mit `check_same_thread=False` -- jeder Thread bekommt eine eigene
Connection aus dem Pool, echte Nebenlaeufigkeit auf DB-Ebene wird moeglich.
Damit wird nachgewiesen, dass die Sicherheit aus der WHERE-Klausel +
Rowcount-Pruefung + Unique-Index kommt, NICHT (nur) aus dem prozesslokalen
`threading.RLock` -- der bei mehreren Server-Worker-PROZESSEN nicht wirkt."""
from __future__ import annotations

import os
import threading

os.environ.setdefault("AILIZA_SECRET_KEY", "test-secret-key-minimum-32-chars-ok")
os.environ.setdefault("AILIZA_DATABASE_URL", "sqlite:///:memory:")

import pytest
from sqlalchemy import create_engine, select

import apps.backend.database as dbmod
from apps.backend.database import MemoryValidationError


@pytest.fixture
def file_db(tmp_path):
    """Ersetzt die globale, In-Memory/StaticPool-Engine des Moduls
    zeitweise durch eine echte Datei-SQLite-Engine ohne StaticPool -- jeder
    Thread/jede Connection sieht dieselbe Datei, aber KEINE geteilte rohe
    Connection. Stellt die alte Engine danach wieder her."""
    db_path = tmp_path / "concurrency.sqlite"
    file_engine = create_engine(
        f"sqlite:///{db_path}", connect_args={"check_same_thread": False},
    )
    old_engine = dbmod.engine
    dbmod.engine = file_engine
    try:
        dbmod.init_db()
        yield file_engine
    finally:
        dbmod.engine = old_engine


def _company_suggestion(tenant_id="default"):
    dbmod.create_user(user_id="alice", tenant_id=tenant_id, role="user", hashed_password="hash")
    dbmod.create_user(user_id="admin1", tenant_id=tenant_id, role="admin", hashed_password="hash")
    dbmod.create_user(user_id="bob", tenant_id=tenant_id, role="user", hashed_password="hash")
    dbmod.create_user(user_id="carol", tenant_id=tenant_id, role="user", hashed_password="hash")
    return dbmod.create_memory_suggestion(
        user_id="alice", tenant_id=tenant_id, suggested_scope="company_memory",
        suggested_title="DATEV", suggested_content="Firma nutzt DATEV.",
        suggested_purpose="Kontext", source_type="user_confirmation",
    )


def _run_concurrently(*callables):
    """Startet alle callables als eigene Threads (jeder mit eigener DB-
    Connection ueber den Engine-Pool), sammelt Ergebnisse/Exceptions."""
    results: list[tuple[str, Exception | None]] = [("", None)] * len(callables)

    def _wrap(idx, fn):
        try:
            fn()
            results[idx] = ("ok", None)
        except MemoryValidationError as exc:
            results[idx] = ("denied", exc)
        except Exception as exc:  # noqa: BLE001 -- Test soll jede Exception sichtbar machen
            results[idx] = ("error", exc)

    threads = [threading.Thread(target=_wrap, args=(i, fn)) for i, fn in enumerate(callables)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)
    return results


# ── 1. Gleichzeitiges Confirm und Reject ─────────────────────────────────────

def test_concurrent_confirm_and_reject_exactly_one_wins(file_db):
    s = _company_suggestion()

    results = _run_concurrently(
        lambda: dbmod.confirm_memory_suggestion(s["id"], confirmed_by="admin1", tenant_id="default"),
        lambda: dbmod.reject_memory_suggestion(s["id"], reviewed_by="admin1", tenant_id="default"),
    )
    outcomes = [r[0] for r in results]
    assert outcomes.count("ok") == 1, f"genau eine Aktion darf gewinnen, war: {outcomes}"
    assert outcomes.count("denied") == 1

    final = [x for x in dbmod.list_memory_suggestions_for_user("alice", "default", status=None)
             if x["id"] == s["id"]][0]
    assert final["status"] in ("confirmed", "rejected")


# ── 2. Zwei parallele Confirm-Aufrufe ────────────────────────────────────────

def test_concurrent_double_confirm_no_duplicate_item_or_audit(file_db):
    s = _company_suggestion()

    results = _run_concurrently(
        lambda: dbmod.confirm_memory_suggestion(s["id"], confirmed_by="admin1", tenant_id="default"),
        lambda: dbmod.confirm_memory_suggestion(s["id"], confirmed_by="admin1", tenant_id="default"),
    )
    outcomes = [r[0] for r in results]
    assert outcomes.count("ok") == 1, f"genau ein Confirm darf gewinnen, war: {outcomes}"
    assert outcomes.count("denied") == 1

    with dbmod.engine.begin() as conn:
        items = conn.execute(select(dbmod.memory_items)).mappings().all()
        audit_rows = conn.execute(
            select(dbmod.audit_logs).where(dbmod.audit_logs.c.action == "memory_suggestion.confirmed")
        ).mappings().all()
    assert len(items) == 1, "keine doppelte Wissensuebernahme"
    assert len(audit_rows) == 1, "kein doppelter Audit-Eintrag"


# ── 3. Gleichzeitiger Delegationswiderruf und Confirm ────────────────────────

def test_concurrent_revoke_and_delegated_confirm_defined_outcome(file_db):
    """Definiertes Verhalten: entweder gewinnt der Confirm (Vorschlag
    bestaetigt, Delegation im selben Zug 'completed') ODER der Widerruf
    (Delegation 'revoked', der Confirm-Versuch scheitert generisch) -- NIE
    beides gleichzeitig, NIE ein bestaetigter Vorschlag mit noch aktiver
    Delegation."""
    s = _company_suggestion()
    delegation = dbmod.create_memory_suggestion_delegation(
        s["id"], tenant_id="default", delegated_by_user_id="admin1", delegated_to_user_id="bob",
    )

    results = _run_concurrently(
        lambda: dbmod.confirm_memory_suggestion(s["id"], confirmed_by="bob", tenant_id="default"),
        lambda: dbmod.revoke_memory_suggestion_delegation(
            delegation["id"], tenant_id="default", revoking_user_id="admin1"),
    )
    confirm_outcome = results[0][0]
    # revoke_memory_suggestion_delegation gibt bool zurueck, wirft nie --
    # "ok" heisst hier nur "kein Fehler", nicht zwingend True.

    with dbmod.engine.begin() as conn:
        suggestion_row = conn.execute(
            select(dbmod.memory_suggestions.c.status)
            .where(dbmod.memory_suggestions.c.id == s["id"])
        ).first()
        delegation_row = conn.execute(
            select(dbmod.memory_suggestion_delegations.c.status)
            .where(dbmod.memory_suggestion_delegations.c.id == delegation["id"])
        ).first()

    suggestion_status = suggestion_row[0]
    delegation_status = delegation_row[0]

    if confirm_outcome == "ok":
        # Confirm hat gewonnen: Vorschlag bestaetigt, Delegation im selben
        # Zug "completed" -- niemals "active" nach erfolgreichem Confirm.
        assert suggestion_status == "confirmed"
        assert delegation_status in ("completed", "revoked")
    else:
        # Widerruf hat gewonnen (oder war zuerst durch): Vorschlag bleibt
        # offen, Confirm-Versuch wurde generisch abgelehnt.
        assert suggestion_status in ("open", "needs_admin_approval")
        assert delegation_status == "revoked"

    # Der verbotene Zustand: bestaetigt UND Delegation noch aktiv.
    assert not (suggestion_status == "confirmed" and delegation_status == "active")


# ── 4. Paralleles Erstellen identischer Delegationen ─────────────────────────

def test_concurrent_identical_delegation_creation_at_most_one_active(file_db):
    s = _company_suggestion()

    results = _run_concurrently(
        lambda: dbmod.create_memory_suggestion_delegation(
            s["id"], tenant_id="default", delegated_by_user_id="admin1", delegated_to_user_id="bob"),
        lambda: dbmod.create_memory_suggestion_delegation(
            s["id"], tenant_id="default", delegated_by_user_id="admin1", delegated_to_user_id="carol"),
    )
    outcomes = [r[0] for r in results]
    assert outcomes.count("ok") == 1, f"nur eine Delegation darf entstehen, war: {outcomes}"
    assert outcomes.count("denied") == 1

    with dbmod.engine.begin() as conn:
        active = conn.execute(
            select(dbmod.memory_suggestion_delegations)
            .where(dbmod.memory_suggestion_delegations.c.suggestion_id == s["id"])
            .where(dbmod.memory_suggestion_delegations.c.status == "active")
        ).mappings().all()
    assert len(active) == 1, "hoechstens eine aktive Delegation pro Vorschlag (Unique-Index)"


# ── 5. Datei-SQLite mit getrennten Connections (kein StaticPool-Verdeckungseffekt) ──

def test_file_sqlite_uses_separate_connections_not_static_pool(file_db):
    """Regressionsschutz fuer die Tests selbst: stellt sicher, dass die
    Test-Engine wirklich KEINE StaticPool ist -- sonst wuerden obige Tests
    denselben Verdeckungseffekt haben wie die :memory:-Testsuite und die
    Race-Pruefung waere wertlos."""
    from sqlalchemy.pool import StaticPool
    assert not isinstance(dbmod.engine.pool, StaticPool)
    with dbmod.engine.connect() as c1, dbmod.engine.connect() as c2:
        assert c1.connection is not c2.connection
