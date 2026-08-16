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

# Bewusst NICHT setdefault: ein bereits gesetzter, aber zu kurzer Wert (z.B.
# ein leerer AILIZA_LOG_HMAC_KEY in der Shell oder CI-Umgebung) wuerde von
# setdefault nicht ersetzt. _get_log_hmac_key() verlangt >= 32 Zeichen und
# gibt sonst None zurueck -- dann fehlt der user_id_hash und vier Tests
# dieser Datei schlagen mit einer irrefuehrenden Meldung fehl, die nach
# einem Fehler in der Auth-Logik aussieht statt nach einer Umgebungsfrage.
if len(os.environ.get("AILIZA_LOG_HMAC_KEY", "")) < 32:
    os.environ["AILIZA_LOG_HMAC_KEY"] = "test-log-hmac-key-minimum-32-chars-ok"

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


# ── HMAC-Pseudonymisierung (Haertung: ersetzt einfachen SHA-256-Hash) ──────

def test_hmac_fingerprint_differs_from_plaintext_and_reason_code(client):
    from apps.backend.database import query_audit_events
    _seed_user("Tester001")
    client.post("/auth/login", json={"user_id": "Tester001", "password": "WrongPassword1!"})
    entries = query_audit_events(tenant_id="default", action="auth.login.failed")
    fingerprint = entries[0]["metadata"]["user_id_hash"]
    assert fingerprint != "Tester001"
    assert "Tester001" not in fingerprint
    assert fingerprint.startswith("uh_v")


def test_hmac_fingerprint_stable_for_same_username_and_key(client):
    from apps.backend.database import query_audit_events
    _seed_user("Tester001")
    client.post("/auth/login", json={"user_id": "Tester001", "password": "Wrong1!"})
    client.post("/auth/login", json={"user_id": "Tester001", "password": "Wrong2!"})
    entries = query_audit_events(tenant_id="default", action="auth.login.failed")
    fingerprints = {e["metadata"]["user_id_hash"] for e in entries}
    assert len(fingerprints) == 1


def test_hmac_fingerprint_differs_for_different_usernames(client):
    from apps.backend.database import query_audit_events
    _seed_user("Tester001")
    _seed_user("Tester002")
    client.post("/auth/login", json={"user_id": "Tester001", "password": "Wrong1!"})
    client.post("/auth/login", json={"user_id": "Tester002", "password": "Wrong1!"})
    entries = query_audit_events(tenant_id="default", action="auth.login.failed")
    fingerprints = {e["metadata"]["user_id_hash"] for e in entries}
    assert len(fingerprints) == 2


def test_hmac_fingerprint_differs_for_different_keys(monkeypatch):
    from apps.backend.main import _mask_user_id_for_log
    monkeypatch.setenv("AILIZA_LOG_HMAC_KEY", "a" * 32)
    fp_a = _mask_user_id_for_log("SomeUser")
    monkeypatch.setenv("AILIZA_LOG_HMAC_KEY", "b" * 32)
    fp_b = _mask_user_id_for_log("SomeUser")
    assert fp_a != fp_b


def test_missing_hmac_key_omits_fingerprint_but_does_not_break_login(monkeypatch, client):
    """Fehlt AILIZA_LOG_HMAC_KEY, darf die Anmeldung trotzdem funktionieren --
    es wird lediglich kein Fingerprint erzeugt (kein Fallback auf Klartext
    oder SHA-256)."""
    from apps.backend.database import query_audit_events
    monkeypatch.delenv("AILIZA_LOG_HMAC_KEY", raising=False)
    _seed_user("Tester001")
    resp = client.post("/auth/login", json={"user_id": "Tester001", "password": "WrongPassword1!"})
    assert resp.status_code == 401
    entries = query_audit_events(tenant_id="default", action="auth.login.failed")
    meta = entries[-1]["metadata"]
    assert "user_id_hash" not in meta
    assert "Tester001" not in str(meta)


def test_missing_hmac_key_does_not_fall_back_to_secret_key(monkeypatch):
    """AILIZA_SECRET_KEY (JWT-Signatur) darf NIEMALS als Ersatz fuer
    AILIZA_LOG_HMAC_KEY verwendet werden."""
    from apps.backend.main import _mask_user_id_for_log
    monkeypatch.delenv("AILIZA_LOG_HMAC_KEY", raising=False)
    assert _mask_user_id_for_log("SomeUser") is None


# ── Request-ID: zentrale Middleware ─────────────────────────────────────────

def test_request_id_header_present_on_every_response(client):
    resp = client.get("/health")
    assert "x-request-id" in resp.headers
    assert len(resp.headers["x-request-id"]) > 0


def test_request_id_differs_per_request(client):
    r1 = client.get("/health")
    r2 = client.get("/health")
    assert r1.headers["x-request-id"] != r2.headers["x-request-id"]


def test_client_supplied_request_id_is_ignored(client):
    """Ein vom Client mitgeschickter X-Request-ID-Header darf NICHT
    uebernommen werden (sonst koennte ein Client Log-Korrelationen faelschen)."""
    resp = client.get("/health", headers={"X-Request-ID": "attacker-supplied-id"})
    assert resp.headers["x-request-id"] != "attacker-supplied-id"


def test_login_audit_entry_contains_request_id_matching_response_header(client):
    from apps.backend.database import query_audit_events
    _seed_user("Tester001")
    resp = client.post("/auth/login", json={"user_id": "Tester001", "password": "WrongPassword1!"})
    entries = query_audit_events(tenant_id="default", action="auth.login.failed")
    assert entries[-1]["metadata"]["request_id"] == resp.headers["x-request-id"]


# ── Rate-Limit-Logging im richtigen Handler (nicht in authenticate_user_with_reason) ─

def test_rate_limit_logs_at_correct_handler_without_leaking_credentials(client):
    from apps.backend.database import query_audit_events
    for _ in range(11):
        client.post("/auth/login", json={"user_id": "RateLimitVictim", "password": "SomePassword1!"})
    entries = query_audit_events(tenant_id="default", action="auth.login.rate_limited")
    assert len(entries) >= 1
    meta = entries[-1]["metadata"]
    assert meta["reason_code"] == "auth_rate_limited"
    blob = str(meta)
    assert "RateLimitVictim" not in blob
    assert "SomePassword1!" not in blob


# ── Ergebnisklassen (Item 4) ────────────────────────────────────────────────

def test_success_login_has_success_result_class(client):
    from apps.backend.database import query_audit_events
    _seed_user("Tester001")
    client.post("/auth/login", json={"user_id": "Tester001", "password": "CorrectHorse123!"})
    entries = query_audit_events(tenant_id="default", action="auth.login.success")
    assert entries[-1]["metadata"]["result_class"] == "AUTH_SUCCESS"


def test_failed_login_has_failed_result_class(client):
    from apps.backend.database import query_audit_events
    _seed_user("Tester001")
    client.post("/auth/login", json={"user_id": "Tester001", "password": "WrongPassword1!"})
    entries = query_audit_events(tenant_id="default", action="auth.login.failed")
    assert entries[-1]["metadata"]["result_class"] == "AUTH_FAILED"


def test_totp_step_up_has_step_up_result_class_and_does_not_increment_lockout(client):
    from apps.backend.auth.totp import generate_secret
    from apps.backend.database import (
        query_audit_events, get_user, upsert_totp_secret, confirm_totp_secret,
    )
    _seed_user("AdminUser1", tenant_id="default")
    from sqlalchemy import update
    from apps.backend.database import users, engine
    with engine.begin() as conn:
        conn.execute(update(users).where(users.c.user_id == "AdminUser1").values(role="admin"))
    secret = generate_secret()
    upsert_totp_secret("AdminUser1", "default", secret)
    confirm_totp_secret("AdminUser1")

    before = get_user("AdminUser1", "default")
    resp = client.post("/auth/login", json={"user_id": "AdminUser1", "password": "CorrectHorse123!"})
    assert resp.status_code == 200
    assert resp.json()["totp_required"] is True
    after = get_user("AdminUser1", "default")
    assert after.get("failed_login_attempts", 0) == before.get("failed_login_attempts", 0)

    entries = query_audit_events(tenant_id="default", action="auth.login.totp_required")
    assert entries[-1]["metadata"]["result_class"] == "AUTH_STEP_UP_REQUIRED"
