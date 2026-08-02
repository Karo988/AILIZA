"""Hotfix: kanonische Timestamp-Serialisierung für die Audit-Hash-Chain.

Bug (live reproduziert vor diesem Fix): audit_logs.timestamp wird beim
Schreiben ausnahmslos über datetime.now(timezone.utc) gesetzt. SQLite liefert
eine DateTime(timezone=True)-Spalte beim Zurücklesen jedoch als NAIVES
datetime -- isoformat() auf dem zurückgelesenen Objekt erzeugt dadurch einen
anderen String als beim ursprünglichen Schreiben. verify_audit_chain()
(apps/backend/audit/vault.py, aufgerufen von der produktiven Route
GET /admin/audit/verify) meldete dadurch bei JEDEM Aufruf fälschlich
"Manipulation erkannt", obwohl nichts verändert wurde -- ein Falsch-Alarm auf
der einzigen tatsächlich im Backend verdrahteten Audit-Verifikationsroute.

Hinweis zur zweiten, im Auftrag erwähnten "produktiven" Route
GET /audit/vault/verify (apps/backend/routers/vault.py): dieser Router wird
NIRGENDS über app.include_router() in main.py eingebunden (verifiziert per
Grep) und verwendet zudem eine komplett andere, unabhängige Speicherklasse
(AuditVault mit eigener SQLite-Datei/eigenem _compute_hash, siehe
apps/backend/audit/vault.py Klassen-Definition weiter oben in derselben
Datei) -- nicht dieselbe audit_logs-Tabelle/denselben _compute_audit_hash.
Er ist also kein Aufrufer des hier reparierten Pfads und aktuell kein
produktiv erreichbarer Endpunkt. Nur GET /admin/audit/verify (main.py) ist
real verdrahtet und betroffen -- wird unten als Endpunkttest abgedeckt."""
from __future__ import annotations

import os

os.environ.setdefault("AILIZA_SECRET_KEY", "test-secret-key-minimum-32-chars-ok")
os.environ.setdefault("AILIZA_DATABASE_URL", "sqlite:///:memory:")

from datetime import datetime, timezone

import pytest
from sqlalchemy import select, update as sa_update

import apps.backend.database as dbmod
from apps.backend.audit.vault import verify_audit_chain


@pytest.fixture(autouse=True)
def fresh_db():
    dbmod.metadata_obj.drop_all(dbmod.engine)
    dbmod.init_db()
    yield


# ── 1. Round-Trip: geschriebene, unveränderte Einträge bleiben verifizierbar ──

def test_single_entry_round_trip_verifies_ok():
    dbmod.write_audit_entry(action="test.one", metadata={}, tenant_id="default")
    result = verify_audit_chain(tenant_id="default")
    assert result["ok"] is True
    assert result["first_invalid_id"] is None
    assert result["checked"] == 1


def test_multiple_chained_entries_all_verify_ok():
    """Regressionstest für den live reproduzierten Bug: vor dem Fix meldete
    dieser exakte Ablauf 'Manipulation erkannt ab Eintrag ID 1', obwohl
    nichts verändert wurde."""
    for i in range(5):
        dbmod.write_audit_entry(action=f"test.action.{i}", metadata={"i": i}, tenant_id="default")
    result = verify_audit_chain(tenant_id="default")
    assert result["ok"] is True
    assert result["checked"] == 5
    assert result["first_invalid_id"] is None


def test_memory_suggestion_audit_entries_verify_ok():
    """Reale Aktion aus M2/M2b statt eines synthetischen write_audit_entry-
    Aufrufs -- stellt sicher, dass der Fix auch für die Confirm/Reject/
    Delegieren/Widerrufen-Audit-Einträge greift."""
    dbmod.create_user(user_id="alice", tenant_id="default", role="user", hashed_password="hash")
    s = dbmod.create_memory_suggestion(
        user_id="alice", tenant_id="default", suggested_scope="user_memory",
        suggested_title="x", suggested_content="y",
        suggested_purpose="z", source_type="user_confirmation",
    )
    dbmod.confirm_memory_suggestion(s["id"], confirmed_by="alice")
    result = verify_audit_chain(tenant_id="default")
    assert result["ok"] is True
    assert result["first_invalid_id"] is None


# ── 2. Manipulationserkennung bleibt (bzw. wird nach dem Fix erst) korrekt ───

def test_tampered_action_is_detected():
    dbmod.write_audit_entry(action="test.one", metadata={}, tenant_id="default")
    dbmod.write_audit_entry(action="test.two", metadata={}, tenant_id="default")
    with dbmod.engine.begin() as conn:
        first_id = conn.execute(select(dbmod.audit_logs.c.id).order_by(dbmod.audit_logs.c.id.asc())).first()[0]
        conn.execute(
            sa_update(dbmod.audit_logs).where(dbmod.audit_logs.c.id == first_id)
            .values(action="test.manipuliert")
        )
    result = verify_audit_chain(tenant_id="default")
    assert result["ok"] is False
    assert result["first_invalid_id"] == first_id


def test_tampered_previous_hash_is_detected():
    dbmod.write_audit_entry(action="test.one", metadata={}, tenant_id="default")
    dbmod.write_audit_entry(action="test.two", metadata={}, tenant_id="default")
    with dbmod.engine.begin() as conn:
        second_id = conn.execute(select(dbmod.audit_logs.c.id).order_by(dbmod.audit_logs.c.id.desc())).first()[0]
        conn.execute(
            sa_update(dbmod.audit_logs).where(dbmod.audit_logs.c.id == second_id)
            .values(previous_hash="0" * 64)
        )
    result = verify_audit_chain(tenant_id="default")
    assert result["ok"] is False
    assert result["first_invalid_id"] == second_id


def test_unmodified_entries_never_report_false_positive():
    """Direktes Gegenstück zum ursprünglichen Bug: mehrere unveränderte
    Einträge dürfen NIEMALS als manipuliert gemeldet werden."""
    for i in range(10):
        dbmod.write_audit_entry(action=f"test.{i}", metadata={}, tenant_id="default")
    result = verify_audit_chain(tenant_id="default")
    assert result["ok"] is True


# ── 2b. Golden Vector: historisches Payload-/Hashformat bleibt bit-exakt ─────
# fixiert. Schreib- und Lesepfad koennten nach dem Fix zwar UNTEREINANDER
# uebereinstimmen, aber gemeinsam unbemerkt vom bisherigen Format abweichen
# (z.B. anderes Trennzeichen, andere Feldreihenfolge, andere ISO-Praezision).
# Dieser Test bindet _compute_audit_hash an einen fest verdrahteten,
# unabhaengig -- nicht ueber den Code selbst, sondern manuell -- berechneten
# SHA-256-Wert nach dem UNVERAENDERTEN Payloadformat
# f"{entry_id}|{iso_mit_+00:00}|{action}|{tenant_id}|{previous_hash}".
# Weicht der Code jemals von diesem Format ab (Trennzeichen, Feldreihenfolge,
# Praezision), schlaegt dieser Test fehl, auch wenn Schreib-/Lesepfad intern
# noch konsistent zueinander waeren.

_GOLDEN_ENTRY_ID = 42
_GOLDEN_ACTION = "test.golden"
_GOLDEN_TENANT_ID = "default"
_GOLDEN_PREVIOUS_HASH = "0" * 64
_GOLDEN_TIMESTAMP_UTC = datetime(2026, 1, 15, 9, 30, 45, 123456, tzinfo=timezone.utc)
_GOLDEN_ISO_STRING = "2026-01-15T09:30:45.123456+00:00"
# Unabhaengig, manuell vorberechnet aus:
#   raw = "42|2026-01-15T09:30:45.123456+00:00|test.golden|default|" + "0"*64
#   hashlib.sha256(raw.encode("utf-8")).hexdigest()
_GOLDEN_EXPECTED_HASH = "5aef3aa160f384d7b5866b16714efefe7ae945ec7192c41d3d2e4d95d1678c81"


def test_golden_vector_iso_string_matches_historical_format():
    """Der ISO-String selbst (mit +00:00-Suffix, volle Mikrosekunden) muss
    unveraendert zum historischen Format sein."""
    assert dbmod._canonicalize_audit_timestamp(_GOLDEN_TIMESTAMP_UTC) == _GOLDEN_ISO_STRING


def test_golden_vector_hash_matches_historical_format_for_aware_utc():
    computed = dbmod._compute_audit_hash(
        _GOLDEN_ENTRY_ID, _GOLDEN_TIMESTAMP_UTC, _GOLDEN_ACTION,
        _GOLDEN_TENANT_ID, _GOLDEN_PREVIOUS_HASH,
    )
    assert computed == _GOLDEN_EXPECTED_HASH


def test_golden_vector_hash_matches_historical_format_for_naive_sqlite_roundtrip():
    """Simuliert exakt das, was SQLite nach einem echten Round-Trip liefert:
    denselben Zeitpunkt, aber ohne tzinfo. Muss trotzdem denselben
    historischen Golden-Hash ergeben wie der aware Originalwert -- das ist
    der eigentliche Kern des Fixes."""
    naive_after_sqlite_roundtrip = _GOLDEN_TIMESTAMP_UTC.replace(tzinfo=None)
    computed = dbmod._compute_audit_hash(
        _GOLDEN_ENTRY_ID, naive_after_sqlite_roundtrip, _GOLDEN_ACTION,
        _GOLDEN_TENANT_ID, _GOLDEN_PREVIOUS_HASH,
    )
    assert computed == _GOLDEN_EXPECTED_HASH


def test_golden_vector_aware_and_naive_produce_identical_hash():
    aware_hash = dbmod._compute_audit_hash(
        _GOLDEN_ENTRY_ID, _GOLDEN_TIMESTAMP_UTC, _GOLDEN_ACTION,
        _GOLDEN_TENANT_ID, _GOLDEN_PREVIOUS_HASH,
    )
    naive_hash = dbmod._compute_audit_hash(
        _GOLDEN_ENTRY_ID, _GOLDEN_TIMESTAMP_UTC.replace(tzinfo=None), _GOLDEN_ACTION,
        _GOLDEN_TENANT_ID, _GOLDEN_PREVIOUS_HASH,
    )
    assert aware_hash == naive_hash == _GOLDEN_EXPECTED_HASH


# ── 3. Alt-Einträge (vor diesem Fix geschrieben) bleiben verifizierbar ───────

def test_entries_written_with_unchanged_write_path_remain_verifiable():
    """Der Fix verändert ausschließlich die Leseseite (Verifikation).
    Der Schreibpfad (write_audit_entry / _insert_audit_entry_on_connection)
    war nie fehlerhaft -- er erzeugte immer korrekt zeitzonenbehaftete
    isoformat-Strings. Ein "alter" Eintrag unterscheidet sich technisch in
    nichts von einem neuen; dieser Test hält das explizit fest, statt es nur
    implizit vorauszusetzen."""
    entry = dbmod.write_audit_entry(action="legacy.simulated", metadata={}, tenant_id="default")
    with dbmod.engine.begin() as conn:
        row = conn.execute(
            select(dbmod.audit_logs).where(dbmod.audit_logs.c.id == entry["id"])
        ).mappings().first()
    # Der gespeicherte Hash wurde mit dem aware datetime-Objekt zum
    # Schreibzeitpunkt berechnet -- exakt das, was _canonicalize_audit_timestamp
    # bei der Verifikation aus dem (jetzt naiven) zurückgelesenen Wert
    # rekonstruieren muss.
    recomputed = dbmod._compute_audit_hash(
        row["id"], row["timestamp"], row["action"], row["tenant_id"], row["previous_hash"],
    )
    assert recomputed == row["entry_hash"]


# ── 4. Kanonische Normalisierung: naive und aware Zeitstempel, Fail-Closed ───

def test_naive_timestamp_is_interpreted_as_utc():
    naive = datetime(2026, 8, 2, 10, 0, 0, 123456)
    aware = naive.replace(tzinfo=timezone.utc)
    assert dbmod._canonicalize_audit_timestamp(naive) == dbmod._canonicalize_audit_timestamp(aware)
    assert dbmod._canonicalize_audit_timestamp(naive).endswith("+00:00")


def test_aware_non_utc_timestamp_is_normalized_to_utc():
    from datetime import timedelta
    tz_plus2 = timezone(timedelta(hours=2))
    local = datetime(2026, 8, 2, 12, 0, 0, tzinfo=tz_plus2)
    utc_equivalent = datetime(2026, 8, 2, 10, 0, 0, tzinfo=timezone.utc)
    assert dbmod._canonicalize_audit_timestamp(local) == dbmod._canonicalize_audit_timestamp(utc_equivalent)


def test_invalid_timestamp_type_fails_closed_not_silent_str():
    with pytest.raises(TypeError):
        dbmod._canonicalize_audit_timestamp("2026-08-02T10:00:00+00:00")  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        dbmod._compute_audit_hash(1, "not-a-datetime", "action", "default", "0" * 64)  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        dbmod._canonicalize_audit_timestamp(None)  # type: ignore[arg-type]


# ── 5. Produktive Route GET /admin/audit/verify (main.py, echt verdrahtet) ──

@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient
    from apps.backend.main import app
    return TestClient(app)


def test_admin_audit_verify_endpoint_reports_ok_for_unmodified_chain(client):
    from apps.backend.auth.jwt_handler import create_token
    dbmod.metadata_obj.drop_all(dbmod.engine)
    dbmod.init_db()
    dbmod.write_audit_entry(action="test.endpoint.one", metadata={}, tenant_id="default")
    dbmod.write_audit_entry(action="test.endpoint.two", metadata={}, tenant_id="default")

    token = create_token("admin1", "default", "admin")
    resp = client.get("/admin/audit/verify", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True, f"Falsch-Alarm reproduziert: {body}"
    assert body["first_invalid_id"] is None


def test_admin_audit_verify_endpoint_detects_real_tampering(client):
    from apps.backend.auth.jwt_handler import create_token
    dbmod.metadata_obj.drop_all(dbmod.engine)
    dbmod.init_db()
    dbmod.write_audit_entry(action="test.endpoint.one", metadata={}, tenant_id="default")
    with dbmod.engine.begin() as conn:
        first_id = conn.execute(select(dbmod.audit_logs.c.id)).first()[0]
        conn.execute(
            sa_update(dbmod.audit_logs).where(dbmod.audit_logs.c.id == first_id)
            .values(action="tatsaechlich.manipuliert")
        )

    token = create_token("admin1", "default", "admin")
    resp = client.get("/admin/audit/verify", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is False
    assert body["first_invalid_id"] == first_id
