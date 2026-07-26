"""
PR A: Login-UX-Entkopplung und interne Ursachen-Codes fuer fehlgeschlagene
Anmeldungen.

Prueft:
  - authenticate_user_with_reason() liefert den korrekten technischen
    Ursachen-Code fuer jede Fehlerklasse, OHNE die oeffentliche Antwort zu
    beeinflussen.
  - POST /auth/login liefert fuer ALLE Fehlerfaelle exakt denselben
    Statuscode + Text (kein User-Enumeration-Leck).
  - Die interne Audit-Metadaten enthalten reason_code + request_id +
    gehashten Nutzernamen -- NIEMALS Klartext-Nutzername, Passwort,
    Passwort-Hash oder Token.
  - Registrierung: Erfolg, Duplikat, ungueltiges Passwort.
"""
from __future__ import annotations

import os

os.environ.setdefault("AILIZA_SECRET_KEY", "test-secret-key-minimum-32-chars-ok")
os.environ.setdefault("AILIZA_DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("AILIZA_EXTERNAL_LLM_ENABLED", "false")

import pytest
from datetime import datetime, timedelta, timezone


@pytest.fixture(autouse=True)
def fresh_db():
    from apps.backend.database import init_db, metadata_obj, engine
    metadata_obj.drop_all(engine)
    init_db()
    yield


@pytest.fixture
def client():
    from fastapi.testclient import TestClient
    from apps.backend.main import app
    return TestClient(app, cookies={})


def _seed_user(user_id="Tester001", tenant_id="default", password="CorrectHorse123!", **overrides):
    import bcrypt
    from apps.backend.database import create_user, users, engine
    from sqlalchemy import update
    pw_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    create_user(user_id, tenant_id, "user", pw_hash)
    if overrides:
        with engine.begin() as conn:
            conn.execute(update(users).where(users.c.user_id == user_id).values(**overrides))
    return user_id


# ── authenticate_user_with_reason(): korrekte interne Ursachen-Codes ────────

def test_reason_success():
    from apps.backend.database import authenticate_user_with_reason, AUTH_REASON_SUCCESS
    _seed_user()
    user, reason = authenticate_user_with_reason("Tester001", "CorrectHorse123!", "default")
    assert user is not None
    assert reason == AUTH_REASON_SUCCESS


def test_reason_password_mismatch():
    from apps.backend.database import authenticate_user_with_reason, AUTH_REASON_PASSWORD_MISMATCH
    _seed_user()
    user, reason = authenticate_user_with_reason("Tester001", "WrongPassword1!", "default")
    assert user is None
    assert reason == AUTH_REASON_PASSWORD_MISMATCH


def test_reason_user_not_found():
    from apps.backend.database import authenticate_user_with_reason, AUTH_REASON_USER_NOT_FOUND
    user, reason = authenticate_user_with_reason("GhostUser", "whatever123!A", "default")
    assert user is None
    assert reason == AUTH_REASON_USER_NOT_FOUND


def test_reason_user_inactive():
    from apps.backend.database import authenticate_user_with_reason, AUTH_REASON_USER_INACTIVE
    _seed_user("Deaktiviert1", active=0)
    user, reason = authenticate_user_with_reason("Deaktiviert1", "CorrectHorse123!", "default")
    assert user is None
    assert reason == AUTH_REASON_USER_INACTIVE


def test_reason_user_locked():
    from apps.backend.database import authenticate_user_with_reason, AUTH_REASON_USER_LOCKED
    _seed_user("Gesperrt1", locked_until=datetime.now(timezone.utc) + timedelta(minutes=30))
    user, reason = authenticate_user_with_reason("Gesperrt1", "CorrectHorse123!", "default")
    assert user is None
    assert reason == AUTH_REASON_USER_LOCKED


def test_reason_password_hash_invalid():
    from apps.backend.database import authenticate_user_with_reason, AUTH_REASON_PASSWORD_HASH_INVALID
    _seed_user("Kaputt1", hashed_password="not-a-valid-bcrypt-hash")
    user, reason = authenticate_user_with_reason("Kaputt1", "irgendein-passwort", "default")
    assert user is None
    assert reason == AUTH_REASON_PASSWORD_HASH_INVALID


def test_reason_tenant_mismatch():
    from apps.backend.database import authenticate_user_with_reason, AUTH_REASON_TENANT_MISMATCH
    _seed_user("Tester001", tenant_id="tenant-a")
    user, reason = authenticate_user_with_reason("Tester001", "CorrectHorse123!", "tenant-b")
    assert user is None
    assert reason == AUTH_REASON_TENANT_MISMATCH


def test_existing_authenticate_user_signature_unchanged():
    """authenticate_user() bleibt ein reiner (user|None)-Wrapper -- bestehende
    Aufrufer (Tests, Seed-Logik) duerfen nicht brechen."""
    from apps.backend.database import authenticate_user
    _seed_user()
    assert authenticate_user("Tester001", "CorrectHorse123!", "default") is not None
    assert authenticate_user("Tester001", "wrong", "default") is None


# ── POST /auth/login: identische oeffentliche Antwort in allen Fehlerfaellen ─

def test_public_response_identical_for_all_failure_reasons(client):
    _seed_user("Tester001")
    _seed_user("Deaktiviert1", active=0)
    _seed_user("Gesperrt1", locked_until=datetime.now(timezone.utc) + timedelta(minutes=30))

    responses = [
        client.post("/auth/login", json={"user_id": "GhostUser", "password": "whatever123!A"}),
        client.post("/auth/login", json={"user_id": "Tester001", "password": "WrongPassword1!"}),
        client.post("/auth/login", json={"user_id": "Deaktiviert1", "password": "CorrectHorse123!"}),
        client.post("/auth/login", json={"user_id": "Gesperrt1", "password": "CorrectHorse123!"}),
    ]
    statuses = {r.status_code for r in responses}
    bodies = {r.json()["detail"] for r in responses}
    assert statuses == {401}
    assert bodies == {"Ungültige Zugangsdaten."}


def test_correct_login_succeeds(client):
    _seed_user("Tester001")
    resp = client.post("/auth/login", json={"user_id": "Tester001", "password": "CorrectHorse123!"})
    assert resp.status_code == 200
    assert resp.json()["user_id"] == "Tester001"


# ── Case-Sensitivity / Whitespace (bestehendes Verhalten, bewusst NICHT
#    veraendert -- siehe Auftrag Abschnitt 3: keine stillen Migrationen) ────

def test_username_case_sensitive(client):
    _seed_user("Tester001")
    resp = client.post("/auth/login", json={"user_id": "tester001", "password": "CorrectHorse123!"})
    assert resp.status_code == 401


def test_username_with_internal_space_not_matched(client):
    _seed_user("Tester001")
    resp = client.post("/auth/login", json={"user_id": "Tester 001", "password": "CorrectHorse123!"})
    assert resp.status_code == 401


# ── Interne Audit-Metadaten: reason_code + request_id + gehashter Name,
#    NIEMALS Klartext-Nutzername/Passwort/Hash/Token ────────────────────────

def test_failed_login_audit_contains_reason_code_and_masked_username(client):
    from apps.backend.database import query_audit_events, AUTH_REASON_PASSWORD_MISMATCH
    _seed_user("Tester001")
    client.post("/auth/login", json={"user_id": "Tester001", "password": "WrongPassword1!"})

    entries = query_audit_events(tenant_id="default", action="auth.login.failed")
    assert len(entries) == 1
    meta = entries[0]["metadata"]
    assert meta["reason_code"] == AUTH_REASON_PASSWORD_MISMATCH
    assert "request_id" in meta and len(meta["request_id"]) > 0
    assert "user_id_hash" in meta
    assert meta["user_id_hash"] != "Tester001"
    assert not meta["user_id_hash"].startswith("Tester")
    assert "user_id" not in meta  # kein Klartext-Nutzername mehr im Fehlschlag-Log


def test_no_sensitive_data_in_any_audit_metadata(client):
    """Durchsucht ALLE Audit-Eintraege dieses Testlaufs nach Passwort/Hash/Token-
    Fragmenten -- Regressionsschutz gegen zukuenftiges versehentliches Logging."""
    from apps.backend.database import query_audit_events
    _seed_user("Tester001")
    client.post("/auth/login", json={"user_id": "Tester001", "password": "WrongPassword1!"})
    client.post("/auth/login", json={"user_id": "Tester001", "password": "CorrectHorse123!"})
    client.post("/auth/self-register", json={"user_id": "NeuerNutzer1", "password": "ValidPass123!"})

    forbidden_substrings = ["WrongPassword1!", "CorrectHorse123!", "ValidPass123!", "$2b$"]
    entries = query_audit_events(tenant_id="default", limit=100)
    for entry in entries:
        blob = str(entry["metadata"])
        for forbidden in forbidden_substrings:
            assert forbidden not in blob, f"Sensibler Wert {forbidden!r} im Audit-Log gefunden: {blob}"


# ── Registrierung ────────────────────────────────────────────────────────

def test_registration_success_and_auto_login(client):
    resp = client.post("/auth/self-register", json={"user_id": "NeuerNutzer1", "password": "ValidPass123!"})
    assert resp.status_code == 201
    assert resp.json()["access_token"]


def test_registration_existing_user_returns_409(client):
    _seed_user("Tester001")
    resp = client.post("/auth/self-register", json={"user_id": "Tester001", "password": "AndereValide123!"})
    assert resp.status_code == 409


def test_registration_weak_password_returns_422(client):
    resp = client.post("/auth/self-register", json={"user_id": "NeuerNutzer2", "password": "short"})
    assert resp.status_code == 422


def test_registration_existing_user_with_weak_password_returns_422_not_409(client):
    """Kern-Reproduktion des gemeldeten Verhaltens: Pydantic validiert das
    Passwort VOR der Uniqueness-Pruefung -- 422, nicht 409."""
    _seed_user("Tester001")
    resp = client.post("/auth/self-register", json={"user_id": "Tester001", "password": "short"})
    assert resp.status_code == 422


# ── Timing-Schutz: Dummy-bcrypt-Vergleich bei unbekannten Nutzernamen ──────

def test_unknown_user_triggers_dummy_bcrypt_comparison(monkeypatch):
    """Beweist, dass der bcrypt-Vergleich auch bei unbekanntem Nutzernamen
    tatsaechlich ausgefuehrt wird (Timing-Schutz), statt fruehzeitig ohne
    bcrypt-Aufruf zurueckzukehren."""
    import apps.backend.database as db_module

    calls = []
    real_checkpw = __import__("bcrypt").checkpw

    def spy_checkpw(password, hashed):
        calls.append(hashed)
        return real_checkpw(password, hashed)

    monkeypatch.setattr("bcrypt.checkpw", spy_checkpw)

    user, reason = db_module.authenticate_user_with_reason("GhostUser999", "whatever123!A", "default")
    assert user is None
    assert reason == db_module.AUTH_REASON_USER_NOT_FOUND
    assert len(calls) == 1
    assert calls[0] == db_module._DUMMY_BCRYPT_HASH.encode()
