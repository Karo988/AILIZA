"""M2/M2b: Audit-Rollback und Hash-Chain-Verifikation fuer Confirm/Reject/
Delegieren/Widerrufen.

Wichtiger Befund (dokumentiert, nicht "repariert" -- vorbestehende
Projekt-Konvention): `audit_logs` hat KEINE eigene Akteur-Spalte (nur id,
timestamp, action, metadata JSON, tenant_id, previous_hash, entry_hash).
Kein einziger bestehender write_audit_entry()/_insert_audit_entry_on_
connection()-Aufruf im gesamten Projekt schreibt eine Nutzer-ID ins
metadata-Feld (verifiziert per Grep) -- das ist konsistent mit dieser neuen
Memory-Suggestion-Implementierung. Der Akteur bleibt NICHT direkt im
Audit-Log nachvollziehbar, sondern nur indirekt ueber die Fachtabellen
selbst (memory_suggestions.reviewed_by,
memory_suggestion_delegations.delegated_by_user_id/revoked_by_user_id),
korreliert ueber Tenant + Zeitpunkt + Aktion mit dem Audit-Eintrag."""
from __future__ import annotations

import hashlib
import os

os.environ.setdefault("AILIZA_SECRET_KEY", "test-secret-key-minimum-32-chars-ok")
os.environ.setdefault("AILIZA_DATABASE_URL", "sqlite:///:memory:")

import pytest
from sqlalchemy import select, update

import apps.backend.database as dbmod
from apps.backend.database import MemoryValidationError


@pytest.fixture(autouse=True)
def fresh_db():
    dbmod.metadata_obj.drop_all(dbmod.engine)
    dbmod.init_db()
    yield


def _make_users():
    dbmod.create_user(user_id="alice", tenant_id="default", role="user", hashed_password="hash")
    dbmod.create_user(user_id="admin1", tenant_id="default", role="admin", hashed_password="hash")
    dbmod.create_user(user_id="bob", tenant_id="default", role="user", hashed_password="hash")


def _new_company_suggestion():
    return dbmod.create_memory_suggestion(
        user_id="alice", tenant_id="default", suggested_scope="company_memory",
        suggested_title="DATEV", suggested_content="Firma nutzt DATEV.",
        suggested_purpose="Kontext", source_type="user_confirmation",
    )


def _setup():
    _make_users()
    return _new_company_suggestion()


def _audit_action_count(action: str) -> int:
    with dbmod.engine.begin() as conn:
        rows = conn.execute(
            select(dbmod.audit_logs).where(dbmod.audit_logs.c.action == action)
        ).mappings().all()
    return len(rows)


# ── 1. Audit-Schema-Nachweis ─────────────────────────────────────────────────

def test_audit_schema_has_no_actor_column_but_domain_tables_do():
    """Dokumentiert den Ist-Zustand: audit_logs selbst hat kein Akteur-Feld,
    reviewed_by/delegated_by_user_id/revoked_by_user_id in den Fachtabellen
    schon -- Nachvollziehbarkeit ist indirekt, nicht direkt im Audit-Log."""
    audit_cols = {c.name for c in dbmod.audit_logs.columns}
    assert audit_cols == {"id", "timestamp", "action", "metadata", "tenant_id",
                           "previous_hash", "entry_hash"}
    assert "reviewed_by" in {c.name for c in dbmod.memory_suggestions.columns}
    assert "delegated_by_user_id" in {c.name for c in dbmod.memory_suggestion_delegations.columns}
    assert "revoked_by_user_id" in {c.name for c in dbmod.memory_suggestion_delegations.columns}


def test_confirm_reject_delegate_revoke_each_produce_one_audit_entry():
    s1 = _setup()
    s2 = dbmod.create_memory_suggestion(
        user_id="alice", tenant_id="default", suggested_scope="user_memory",
        suggested_title="Privat", suggested_content="x",
        suggested_purpose="z", source_type="user_confirmation",
    )
    dbmod.confirm_memory_suggestion(s1["id"], confirmed_by="admin1", tenant_id="default")
    dbmod.reject_memory_suggestion(s2["id"], reviewed_by="alice", tenant_id="default")
    s3 = _new_company_suggestion()
    delegation = dbmod.create_memory_suggestion_delegation(
        s3["id"], tenant_id="default", delegated_by_user_id="admin1", delegated_to_user_id="bob",
    )
    dbmod.revoke_memory_suggestion_delegation(delegation["id"], tenant_id="default", revoking_user_id="admin1")

    assert _audit_action_count("memory_suggestion.confirmed") == 1
    assert _audit_action_count("memory_suggestion.rejected") == 1
    assert _audit_action_count("memory_suggestion.delegated") == 1
    assert _audit_action_count("memory_suggestion.delegation_revoked") == 1


# ── 2. Rollback-Test: Audit-Fehler darf keinen Teilzustand hinterlassen ──────

def test_audit_write_failure_rolls_back_confirm_completely(monkeypatch):
    s = _setup()

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

    assert suggestion_row[0] == "needs_admin_approval"  # unveraendert, kein "confirmed"
    assert len(items) == 0  # kein verwaistes Item
    assert len(sources) == 0  # keine verwaiste Source


def test_audit_write_failure_rolls_back_delegation_completion(monkeypatch):
    s = _setup()
    delegation = dbmod.create_memory_suggestion_delegation(
        s["id"], tenant_id="default", delegated_by_user_id="admin1", delegated_to_user_id="bob",
    )

    original = dbmod._insert_audit_entry_on_connection
    call_count = {"n": 0}

    def _fail_on_confirm(conn, action, metadata, tenant_id):
        if action == "memory_suggestion.confirmed":
            raise RuntimeError("simulierter Audit-Schreibfehler beim Confirm")
        return original(conn, action, metadata, tenant_id)

    monkeypatch.setattr(dbmod, "_insert_audit_entry_on_connection", _fail_on_confirm)

    with pytest.raises(RuntimeError):
        dbmod.confirm_memory_suggestion(s["id"], confirmed_by="bob", tenant_id="default")

    with dbmod.engine.begin() as conn:
        suggestion_row = conn.execute(
            select(dbmod.memory_suggestions.c.status).where(dbmod.memory_suggestions.c.id == s["id"])
        ).first()
        delegation_row = conn.execute(
            select(dbmod.memory_suggestion_delegations.c.status)
            .where(dbmod.memory_suggestion_delegations.c.id == delegation["id"])
        ).first()
    assert suggestion_row[0] == "needs_admin_approval"
    assert delegation_row[0] == "active"  # NICHT "completed" -- vollstaendiger Rollback


def test_audit_write_failure_rolls_back_delegation_creation(monkeypatch):
    s = _setup()

    def _boom(*args, **kwargs):
        raise RuntimeError("simulierter Audit-Schreibfehler bei Delegation")

    monkeypatch.setattr(dbmod, "_insert_audit_entry_on_connection", _boom)

    with pytest.raises(RuntimeError):
        dbmod.create_memory_suggestion_delegation(
            s["id"], tenant_id="default", delegated_by_user_id="admin1", delegated_to_user_id="bob",
        )

    with dbmod.engine.begin() as conn:
        rows = conn.execute(select(dbmod.memory_suggestion_delegations)).mappings().all()
    assert len(rows) == 0  # keine verwaiste Delegation ohne Audit-Eintrag


# ── 3. Hash-Chain-Verifikation ───────────────────────────────────────────────
#
# WICHTIGER, VORBESTEHENDER BEFUND (nicht durch M2/M2b eingefuehrt, betrifft
# die gesamte Audit-Hash-Chain-Implementierung seit ihrer urspruenglichen
# Einfuehrung): `_compute_audit_hash()` wird beim Schreiben mit einem
# ZEITZONEN-BEHAFTETEN `datetime.now(timezone.utc).isoformat()`-String
# berechnet. SQLite (`DateTime(timezone=True)` unter pysqlite) verliert beim
# Zuruecklesen jedoch die Zeitzoneninfo -- `row["timestamp"].isoformat()`
# liefert nach einem DB-Round-Trip einen ANDEREN String (ohne "+00:00"-
# Suffix) als beim urspruenglichen Schreiben verwendet wurde. Der
# gespeicherte entry_hash ist deshalb aus den zurueckgelesenen Feldern NICHT
# reproduzierbar -- unabhaengig von Manipulation. Das ist eine echte Luecke
# in der Nachtraeglichen-Verifizierbarkeit der Kette, existiert aber bereits
# im gesamten Projekt (jeder write_audit_entry()-Aufruf ist betroffen, nicht
# nur Memory-Suggestions) und wird hier bewusst NUR dokumentiert und
# nachgewiesen, NICHT repariert -- das waere eine Aenderung ausserhalb des
# M2/M2b-Scopes und muesste separat freigegeben werden.
#
# Was DIESER Test deshalb tatsaechlich zeigt: die KETTENVERKETTUNG
# (previous_hash[n] == entry_hash[n-1]) ist nach Confirm/Reject/Delegieren/
# Widerrufen durchgehend intakt -- das ist unabhaengig vom Timestamp-Problem
# pruefbar und beweist, dass kein Audit-Eintrag uebersprungen oder aus der
# Kette herausgefallen ist.

def _verify_chain_linkage() -> None:
    """Prueft NUR die Verkettung (previous_hash[n] == entry_hash[n-1]) in
    Einfuegereihenfolge -- unabhaengig vom Timestamp-Rundungsproblem oben."""
    with dbmod.engine.begin() as conn:
        rows = conn.execute(
            select(dbmod.audit_logs).order_by(dbmod.audit_logs.c.id.asc())
        ).mappings().all()
    prev = "0" * 64
    for row in rows:
        assert row["previous_hash"] == prev, f"Kette gebrochen bei id={row['id']}"
        assert row["entry_hash"], f"entry_hash fehlt bei id={row['id']}"
        prev = row["entry_hash"]


def test_hash_chain_consistent_after_confirm_reject_delegate_revoke():
    s1 = _setup()
    s2 = dbmod.create_memory_suggestion(
        user_id="alice", tenant_id="default", suggested_scope="user_memory",
        suggested_title="Privat", suggested_content="x",
        suggested_purpose="z", source_type="user_confirmation",
    )
    dbmod.confirm_memory_suggestion(s1["id"], confirmed_by="admin1", tenant_id="default")
    dbmod.reject_memory_suggestion(s2["id"], reviewed_by="alice", tenant_id="default")
    s3 = _new_company_suggestion()
    delegation = dbmod.create_memory_suggestion_delegation(
        s3["id"], tenant_id="default", delegated_by_user_id="admin1", delegated_to_user_id="bob",
    )
    dbmod.revoke_memory_suggestion_delegation(delegation["id"], tenant_id="default", revoking_user_id="admin1")

    _verify_chain_linkage()


def test_tampering_with_audit_entry_changes_its_recomputed_hash():
    """Manipulationstest (fairer Vorher/Nachher-Vergleich, siehe Kommentar
    oben zum Timestamp-Rundungsproblem): der aus den Feldern neu berechnete
    Hash AENDERT SICH, wenn das action-Feld nachtraeglich manipuliert wird --
    die Hash-Funktion ist also grundsaetzlich manipulationsempfindlich (SHA-256
    ueber id/timestamp/action/tenant_id/previous_hash). Beide Berechnungen
    (vorher/nachher) nutzen konsistent denselben (DB-round-getrippten,
    zeitzonenfreien) Timestamp-String, damit der Vergleich NICHT durch das
    Timestamp-Problem verfaelscht wird.

    WICHTIGE EINSCHRAENKUNG (ehrlich dokumentiert): ein Vergleich des
    NEU BERECHNETEN Hashes gegen den GESPEICHERTEN entry_hash wuerde wegen
    des oben beschriebenen Timestamp-Rundungsproblems AUCH bei einem
    unveraenderten, nicht manipulierten Eintrag fehlschlagen -- ein solcher
    Vergleich waere also aktuell fuer eine echte, automatisierte
    Manipulationserkennung NICHT zuverlaessig nutzbar. Das ist ein
    vorbestehendes Reparaturbeduerfnis ausserhalb des M2/M2b-Scopes, hier nur
    aufgedeckt und dokumentiert, nicht behoben."""
    s = _setup()
    dbmod.confirm_memory_suggestion(s["id"], confirmed_by="admin1", tenant_id="default")

    with dbmod.engine.begin() as conn:
        original = conn.execute(
            select(dbmod.audit_logs).where(dbmod.audit_logs.c.action == "memory_suggestion.confirmed")
        ).mappings().first()
    hash_before = dbmod._compute_audit_hash(
        original["id"], original["timestamp"].isoformat(), original["action"],
        original["tenant_id"], original["previous_hash"],
    )

    with dbmod.engine.begin() as conn:
        # Manipulation: action-Feld nachtraeglich veraendert, entry_hash bleibt (absichtlich) unveraendert.
        conn.execute(
            update(dbmod.audit_logs).where(dbmod.audit_logs.c.id == original["id"])
            .values(action="memory_suggestion.rejected")
        )
        tampered = conn.execute(
            select(dbmod.audit_logs).where(dbmod.audit_logs.c.id == original["id"])
        ).mappings().first()
    hash_after = dbmod._compute_audit_hash(
        tampered["id"], tampered["timestamp"].isoformat(), tampered["action"],
        tampered["tenant_id"], tampered["previous_hash"],
    )

    assert hash_before != hash_after, "Manipulation des action-Feldes muss den berechneten Hash aendern"
    # Der gespeicherte entry_hash blieb unveraendert (nicht mit-manipuliert) --
    # er stimmt jetzt weder mit hash_before noch mit hash_after exakt ueberein
    # (Timestamp-Rundungsproblem, siehe Docstring); die MANIPULATION selbst
    # ist trotzdem durch den veraenderten Hashwert nachweisbar.
