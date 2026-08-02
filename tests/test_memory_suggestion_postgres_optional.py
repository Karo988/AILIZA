"""Optionaler Postgres-Nebenlaeufigkeitstest fuer M2/M2b.

In dieser Umgebung ist standardmaessig keine Postgres-Instanz verfuegbar
(siehe docs/HANDOFF_DATENBANK_GEDAECHTNIS.md: Neon/Postgres nur
Uebergangsloesung fuer Render-Staging, autarker Betrieb primaer SQLite).
Dieser Test bleibt daher uebersprungen, solange die Umgebungsvariable
AILIZA_TEST_POSTGRES_URL nicht gesetzt ist.

Zweck: dieselben Nebenlaeufigkeits-Garantien wie
tests/test_memory_suggestion_concurrency.py (Datei-SQLite, getrennte
Connections) zusaetzlich gegen echtes Postgres nachweisen -- dort greift
KEIN Python-Prozess-Lock mehr (ausser man startet die Tests aus demselben
Prozess wie hier), die Atomaritaet muss dann ausschliesslich aus der
WHERE-Klausel + Rowcount-Pruefung + partiellem Unique-Index (inkl.
postgresql_where, siehe memory_suggestion_delegations) kommen.

Synchronisation: statt Sleep-basierter Scheintests wird ein
threading.Barrier verwendet, damit alle beteiligten Threads ihre jeweilige
DB-Operation moeglichst gleichzeitig starten (echte Race-Bedingung statt
zeitlich entzerrter Abfolge).

CI-Anbindung: siehe .github/workflows/ci.yml, Job "postgres-concurrency"
(ephemerer postgres:16-Service-Container, setzt AILIZA_TEST_POSTGRES_URL)."""
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


def _company_suggestion(dbmod, tenant_id="default"):
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
    """Startet alle callables als eigene Threads (jeder mit eigener
    Postgres-Connection ueber den Engine-Pool), synchronisiert deren Start
    ueber eine Barrier (kein Sleep-Timing) und sammelt Ergebnisse."""
    barrier = threading.Barrier(len(callables))
    results: list[tuple[str, Exception | None]] = [("", None)] * len(callables)

    def _wrap(idx, fn):
        barrier.wait(timeout=10)
        try:
            fn()
            results[idx] = ("ok", None)
        except Exception as exc:  # noqa: BLE001 -- Test soll jede Exception sichtbar machen
            from apps.backend.database import MemoryValidationError
            results[idx] = ("denied" if isinstance(exc, MemoryValidationError) else "error", exc)

    threads = [threading.Thread(target=_wrap, args=(i, fn)) for i, fn in enumerate(callables)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)
    return results


# ── 1. Gleichzeitiges Confirm und Reject ─────────────────────────────────────

def test_concurrent_confirm_and_reject_exactly_one_wins_on_postgres(postgres_db):
    dbmod = postgres_db
    s = _company_suggestion(dbmod)

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


# ── 2. Zwei parallele Confirm-Aufrufe (doppeltes Confirm) ────────────────────

def test_concurrent_double_confirm_no_duplicate_item_or_audit_on_postgres(postgres_db):
    dbmod = postgres_db
    s = _company_suggestion(dbmod)

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
    assert len(items) == 1, "genau eine Wissensuebernahme, keine doppelte"
    assert len(audit_rows) == 1, "genau ein Audit-Eintrag, kein doppelter"


# ── 3. Gleichzeitiger Delegationswiderruf und Confirm ────────────────────────

def test_concurrent_revoke_and_delegated_confirm_defined_outcome_on_postgres(postgres_db):
    """Definiertes Verhalten: entweder gewinnt der Confirm (Vorschlag
    bestaetigt, Delegation im selben Zug 'completed') ODER der Widerruf
    (Delegation 'revoked', der Confirm-Versuch scheitert generisch) -- NIE
    beides gleichzeitig, NIE ein bestaetigter Vorschlag mit noch aktiver
    Delegation. Genau EIN Terminalzustand fuer die Suggestion."""
    dbmod = postgres_db
    s = _company_suggestion(dbmod)
    delegation = dbmod.create_memory_suggestion_delegation(
        s["id"], tenant_id="default", delegated_by_user_id="admin1", delegated_to_user_id="bob",
    )

    results = _run_concurrently(
        lambda: dbmod.confirm_memory_suggestion(s["id"], confirmed_by="bob", tenant_id="default"),
        lambda: dbmod.revoke_memory_suggestion_delegation(
            delegation["id"], tenant_id="default", revoking_user_id="admin1"),
    )
    confirm_outcome = results[0][0]

    with dbmod.engine.begin() as conn:
        suggestion_row = conn.execute(
            select(dbmod.memory_suggestions.c.status)
            .where(dbmod.memory_suggestions.c.id == s["id"])
        ).first()
        delegation_row = conn.execute(
            select(dbmod.memory_suggestion_delegations.c.status)
            .where(dbmod.memory_suggestion_delegations.c.id == delegation["id"])
        ).first()
        items = conn.execute(select(dbmod.memory_items)).mappings().all()

    suggestion_status = suggestion_row[0]
    delegation_status = delegation_row[0]

    if confirm_outcome == "ok":
        assert suggestion_status == "confirmed"
        assert delegation_status in ("completed", "revoked")
        assert len(items) == 1, "genau eine Wissensuebernahme bei gewonnenem Confirm"
    else:
        assert suggestion_status in ("open", "needs_admin_approval")
        assert delegation_status == "revoked"
        assert len(items) == 0, "keine Wissensuebernahme, wenn der Widerruf gewinnt"

    # Verbotener Zustand: bestaetigt UND Delegation noch aktiv.
    assert not (suggestion_status == "confirmed" and delegation_status == "active")
    # Genau ein Terminalzustand der Suggestion -- niemals "open" UND "confirmed"/"rejected" gleichzeitig moeglich,
    # hier zusaetzlich explizit gegen den erlaubten Zustandsraum geprueft:
    assert suggestion_status in ("confirmed", "open", "needs_admin_approval")


# ── 4. Paralleles und doppeltes Erstellen von Delegationen ───────────────────

def test_concurrent_identical_delegation_creation_at_most_one_active_on_postgres(postgres_db):
    """Verifiziert speziell die in der Planung gefundene Postgres-Falle:
    ohne postgresql_where wuerde der partielle Unique-Index nicht wirken.
    Zwei PARALLELE Delegationsversuche fuer denselben Vorschlag duerfen nur
    genau eine aktive Delegation erzeugen (doppelte Delegation verhindert)."""
    dbmod = postgres_db
    s = _company_suggestion(dbmod)

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
    assert len(active) == 1, "hoechstens eine aktive Delegation pro Vorschlag (partieller Unique-Index)"


def test_delegation_unique_index_enforced_after_revoke_on_postgres(postgres_db):
    """memory_suggestion_delegations hat BEIDE _where-Klauseln (sqlite_where
    UND postgresql_where) -- eine zweite, sequentielle Delegation nach
    Abschluss der ersten muss unter Postgres moeglich sein (nicht Teil des
    Race-Tests oben, sondern des partiellen-Index-Nachweises als solchem)."""
    dbmod = postgres_db
    s = _company_suggestion(dbmod)
    d1 = dbmod.create_memory_suggestion_delegation(
        s["id"], tenant_id="default", delegated_by_user_id="admin1", delegated_to_user_id="bob",
    )
    dbmod.revoke_memory_suggestion_delegation(d1["id"], tenant_id="default", revoking_user_id="admin1")
    d2 = dbmod.create_memory_suggestion_delegation(
        s["id"], tenant_id="default", delegated_by_user_id="admin1", delegated_to_user_id="carol",
    )
    assert d2["status"] == "active"


# ── 5. Vollstaendiger Rollback bei Audit-Folgefehler ─────────────────────────

def test_audit_write_failure_rolls_back_confirm_completely_on_postgres(postgres_db, monkeypatch):
    """Schlaegt der Audit-Schreibvorgang (derselben Transaktion) fehl, darf
    weder der Vorschlagsstatus noch das memory_item/memory_source bestehen
    bleiben -- vollstaendiger Transaktionsrollback, nicht nur teilweise."""
    dbmod = postgres_db
    s = _company_suggestion(dbmod)

    def _boom(*args, **kwargs):
        raise RuntimeError("simulierter Audit-Schreibfehler")

    monkeypatch.setattr(dbmod, "_insert_audit_entry_on_connection", _boom)

    with pytest.raises(RuntimeError):
        dbmod.confirm_memory_suggestion(s["id"], confirmed_by="admin1", tenant_id="default")

    with dbmod.engine.begin() as conn:
        suggestion_row = conn.execute(
            select(dbmod.memory_suggestions.c.status).where(dbmod.memory_suggestions.c.id == s["id"])
        ).first()
        items = conn.execute(select(dbmod.memory_items)).mappings().all()
        sources = conn.execute(select(dbmod.memory_sources)).mappings().all()
        audit_rows = conn.execute(select(dbmod.audit_logs)).mappings().all()

    assert suggestion_row[0] == "needs_admin_approval"  # unveraendert, kein "confirmed"
    assert len(items) == 0, "kein verwaistes memory_item nach Rollback"
    assert len(sources) == 0, "keine verwaiste memory_source nach Rollback"
    assert len(audit_rows) == 0, "kein Audit-Eintrag nach fehlgeschlagenem Schreibvorgang"


# ── 6. Regressionsschutz: echte getrennte Connections, kein Verdeckungseffekt ──

def test_postgres_engine_uses_separate_connections(postgres_db):
    """Stellt sicher, dass die Postgres-Test-Engine wirklich unabhaengige
    Connections liefert (kein StaticPool-Verdeckungseffekt wie bei
    sqlite:///:memory:) -- sonst waere die Race-Pruefung oben wertlos."""
    from sqlalchemy.pool import StaticPool
    dbmod = postgres_db
    assert not isinstance(dbmod.engine.pool, StaticPool)
    with dbmod.engine.connect() as c1, dbmod.engine.connect() as c2:
        assert c1.connection is not c2.connection
