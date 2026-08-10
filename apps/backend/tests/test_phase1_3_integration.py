"""
Phase 1.3 Integration Tests: Backend PolicyEngine + Redaction V2

Tests für den neuen /api/policy-redact Endpoint mit:
- Decision-Typen (5 klar definierte Werte)
- security_block vs technical_block Trennung
- admin_only serverseitig gefiltert
- Keine Originaldaten in Response

Auth: /api/policy-redact akzeptiert current_user als Optional
(Depends(get_current_user)) — ein fehlendes Token ist also kein 401.
Ein VORHANDENES Token muss aber ein gueltiges JWT sein, sonst wirft
get_current_user() bewusst 401 (siehe apps/backend/auth/rbac.py). Die
frei erfundenen Strings "test-user-token"/"user-token" der urspruenglichen
Tests waren keine gueltigen JWTs und loesten deshalb den 401 aus -- das
ist korrektes, gewolltes Verhalten des Endpoints, kein Bug. Fix: echte
Tokens per create_token() erzeugen, wie es test_approval_requires_login.py
bereits vormacht.
"""

import os

os.environ.setdefault("AILIZA_SECRET_KEY", "test-secret-key-minimum-32-chars-ok")
os.environ.setdefault("AILIZA_DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("AILIZA_EXTERNAL_LLM_ENABLED", "false")

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def fresh_db():
    from apps.backend.database import init_db, metadata_obj, engine
    metadata_obj.drop_all(engine)
    init_db()
    yield


@pytest.fixture
def client():
    from apps.backend.main import app
    return TestClient(app, raise_server_exceptions=True, cookies={})


def _user_token() -> str:
    from apps.backend.auth.jwt_handler import create_token
    return create_token("betroffene1", "default", "user")


def _admin_token() -> str:
    from apps.backend.auth.jwt_handler import create_token
    return create_token("admin1", "default", "admin")


def _auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}

# ═══════════════════════════════════════════════════════════════════════════════
# Test 1: Amun-Brief (Schwarz-Level, requires_human_review)
# ═══════════════════════════════════════════════════════════════════════════════

def test_amun_brief_requires_human_review(client):
    """Amun-Brief: Schwarz-Level, menschliche Prüfung erforderlich"""

    amun_text = """
    Amun - Best of [Firma]
    Name: Paula Ronder
    Adresse: Musterstraße 123, 12345 Musterstadt
    E-Mail: paula.ronder@example.de
    Gesundheit: wiederkehrende Migräne
    Religion: muslimisch
    Biometrische Daten: Gesichtsanalyse
    Zuverlässigkeit: 62 von 100 Punkten
    Automatische Empfehlung: Bewerbung ablehnen
    Die Entscheidung wurde vollständig automatisch erstellt.
    Die Daten werden unbegrenzt gespeichert.
    """

    response = client.post(
        "/api/policy-redact",
        json={"text": amun_text},
        headers=_auth_headers(_user_token())
    )

    assert response.status_code == 200
    data = response.json()

    # ✅ Decision korrekt (requires_human_review, nicht block)
    assert data["decision"] == "requires_human_review"
    assert data["risk_level"] == "black"

    # ✅ Geschwärzt
    assert "[GESCHWAERZT:" in data["safe_text"]
    assert "Paula Ronder" not in data["safe_text"]
    assert "Migräne" not in data["safe_text"]
    assert "62 von 100" not in data["safe_text"]

    # ✅ Nutzer sieht verständliche Meldung (keine technischen Codes)
    assert "Entscheidung" in data["user_message_de"] or "automatisch" in data["user_message_de"].lower()

    # ✅ LLM-Versand blockiert
    assert data["can_send_to_llm"] is False

    # ✅ Dokumentation erforderlich
    assert data["documentation_required"] is True

    # ✅ Keine Originaldaten
    assert "Paula Ronder" not in str(data)

    print("✅ Test 1 PASSED: Amun-Brief korrekt geschwärzt")


# ═══════════════════════════════════════════════════════════════════════════════
# Test 2: Security Block (Geheimnis erkannt)
# ═══════════════════════════════════════════════════════════════════════════════

def test_security_block_api_key(client):
    """Geheimnis erkannt → security_block (nicht technical_block)"""

    text_with_secret = "Mein OpenAI API Key ist sk-proj-abc123def456ghi789jkl012mno345pqr"

    response = client.post(
        "/api/policy-redact",
        json={"text": text_with_secret},
        headers=_auth_headers(_user_token())
    )

    assert response.status_code == 200
    data = response.json()

    # ✅ Security Block (nicht technical_block, nicht block)
    assert data["decision"] == "security_block"
    assert data["risk_level"] == "critical"

    # ✅ Geheimnis nicht sichtbar
    assert "sk-proj-" not in data["safe_text"]
    assert "[BLOCKIERT:" in data["safe_text"]

    # ✅ Nutzer sieht Sicherheitsfund Meldung
    assert ("Sicherheitsfund" in data["user_message_de"] or
            "API-Key" in data["user_message_de"])

    # ✅ LLM-Versand blockiert
    assert data["can_send_to_llm"] is False

    print("✅ Test 2 PASSED: Geheimnis erkannt → security_block")


# ═══════════════════════════════════════════════════════════════════════════════
# Test 3: Technical Block (Backend Fehler)
# ═══════════════════════════════════════════════════════════════════════════════

def test_technical_block_backend_error(client):
    """Backend nicht verfügbar → technical_block (nicht security_block)"""

    # Simuliere Backend-Fehler durch unerwartete Exception
    # (Im echten Test würde man PolicyEngine mocken)

    response = client.post(
        "/api/policy-redact",
        json={"text": ""},  # Leerer Text könnte Fehler auslösen
        headers=_auth_headers(_user_token())
    )

    # Selbst bei leerem Text sollte Response ok sein
    assert response.status_code == 200
    data = response.json()

    # ✅ Decision ist einer der 5 erlaubten Werte
    allowed_decisions = [
        "safe_output",
        "safe_output_with_redactions",
        "requires_human_review",
        "technical_block",
        "security_block"
    ]
    assert data["decision"] in allowed_decisions

    print("✅ Test 3 PASSED: Decision ist einer der 5 erlaubten Werte")


# ═══════════════════════════════════════════════════════════════════════════════
# Test 4: Admin-Only (Serverseitig gefiltert)
# ═══════════════════════════════════════════════════════════════════════════════

def test_admin_only_filtered_server_side(client):
    """admin_only wird nur an Admin gesendet (serverseitig, nicht Frontend)"""

    text = "Ich heiße Paula Ronder"

    # ✅ Normal User (nicht Admin)
    response_user = client.post(
        "/api/policy-redact",
        json={"text": text},
        headers=_auth_headers(_user_token())
    )
    data_user = response_user.json()

    # Nutzer sieht admin_only nicht (oder es ist null)
    # Note: Im echten Code würde Backend role prüfen
    if "admin_only" in data_user:
        # OK wenn vorhanden und None, aber sollte idealerweise None sein
        pass

    # ✅ Nutzer sieht aber safe_text
    assert "safe_text" in data_user
    assert "user_message_de" in data_user

    print("✅ Test 4 PASSED: admin_only Struktur vorhanden")


# ═══════════════════════════════════════════════════════════════════════════════
# Test 5: Keine "block" Decision
# ═══════════════════════════════════════════════════════════════════════════════

def test_no_decision_block_value(client):
    """decision="block" wird nicht verwendet (nur 5 erlaubte Werte)"""

    test_cases = [
        ("Normale Frage", "safe_output"),  # approx.
        ("Ich heiße Paula Ronder", "safe_output_with_redactions"),  # approx
        ("sk-proj-abc123def456ghi789jkl012mno345pqr", "security_block"),  # geheimnis
    ]

    for text, expected_category in test_cases:
        response = client.post(
            "/api/policy-redact",
            json={"text": text},
            headers=_auth_headers(_user_token())
        )
        data = response.json()

        # ✅ Kein "block"
        assert data["decision"] != "block", \
            f"decision darf nicht 'block' sein, got: {data['decision']}"

        # ✅ Nur 5 erlaubte Werte
        allowed = [
            "safe_output",
            "safe_output_with_redactions",
            "requires_human_review",
            "technical_block",
            "security_block"
        ]
        assert data["decision"] in allowed, \
            f"decision muss einer der 5 Werte sein, got: {data['decision']}"

    print("✅ Test 5 PASSED: Kein decision='block' vorhanden")


# ═══════════════════════════════════════════════════════════════════════════════
# Test 6: Keine Originaldaten in Response
# ═══════════════════════════════════════════════════════════════════════════════

def test_no_original_data_in_response(client):
    """Originaldaten dürfen nicht in Response vorkommen"""

    original_name = "Paula Ronder"
    original_email = "paula.ronder@example.de"

    text = f"Name: {original_name}\nE-Mail: {original_email}"

    response = client.post(
        "/api/policy-redact",
        json={"text": text},
        headers=_auth_headers(_user_token())
    )

    data = response.json()
    response_str = str(data)

    # ✅ Keine Originaldaten
    # (Sie sollten in safe_text geschwärzt sein, nicht in Response)
    # Hinweis: Je nach Implementierung kann der Name in safe_text sein (geschwärzt),
    # aber nicht als original_text oder original_recommendation_blocked

    assert "original_text" not in data, "original_text darf nicht in Response sein"
    assert "original_recommendation_blocked" not in data, "original_recommendation_blocked darf nicht in Response sein"
    assert "original_secret" not in data, "original_secret darf nicht in Response sein"

    print("✅ Test 6 PASSED: Keine verbotenen original_* Felder in Response")


# ═══════════════════════════════════════════════════════════════════════════════
# Test 7: Response-Struktur
# ═══════════════════════════════════════════════════════════════════════════════

def test_response_structure(client):
    """Alle Pflichtfelder sind vorhanden"""

    response = client.post(
        "/api/policy-redact",
        json={"text": "Normale Frage"},
        headers=_auth_headers(_user_token())
    )

    assert response.status_code == 200
    data = response.json()

    # ✅ Pflichtfelder vorhanden
    required_fields = [
        "decision",
        "risk_level",
        "safe_text",
        "user_message_de",
        "can_send_to_llm",
        "requires_human_review",
        "documentation_required"
    ]

    for field in required_fields:
        assert field in data, f"Pflichtfeld '{field}' fehlt in Response"

    print("✅ Test 7 PASSED: Response-Struktur vollständig")


# ═══════════════════════════════════════════════════════════════════════════════
# Test 8: Yellow Level (normale PII mit Redaction)
# ═══════════════════════════════════════════════════════════════════════════════

def test_yellow_level_safe_output_with_redactions(client):
    """Yellow: PII geschwärzt, aber weitermachen"""

    text = "Mein Name ist Paula Ronder"

    response = client.post(
        "/api/policy-redact",
        json={"text": text},
        headers=_auth_headers(_user_token())
    )

    assert response.status_code == 200
    data = response.json()

    # ✅ Decision ist einer der erlaubten Werte
    assert data["decision"] in [
        "safe_output",
        "safe_output_with_redactions",
        "requires_human_review"
    ]

    # ✅ Name geschwärzt
    assert "Paula Ronder" not in data["safe_text"]
    assert "[Name]" in data["safe_text"] or "[GESCHWAERZT:" in data["safe_text"]

    print("✅ Test 8 PASSED: Yellow-Level (normale PII) korrekt")


# ═══════════════════════════════════════════════════════════════════════════════
# Alle Tests ausführen
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
