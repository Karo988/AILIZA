from fastapi.testclient import TestClient

from apps.backend.main import app


def test_cookie_approval_decision_rejects_foreign_origin(monkeypatch):
    monkeypatch.setenv("AILIZA_CORS_ORIGINS", "https://ailiza.example.com")
    client = TestClient(app)
    client.cookies.set("ailiza_session", "invalid-but-cookie-auth-shaped")

    response = client.post(
        "/approvals/1/approve",
        headers={"Origin": "https://evil.example"},
        json={"note": ""},
    )

    assert response.status_code == 403
    assert response.json()["code"] == "csrf_blocked"


def test_cookie_approval_decision_accepts_configured_origin_for_auth_check(monkeypatch):
    monkeypatch.setenv("AILIZA_CORS_ORIGINS", "https://ailiza.example.com")
    client = TestClient(app)
    client.cookies.set("ailiza_session", "invalid-but-cookie-auth-shaped")

    response = client.post(
        "/approvals/1/approve",
        headers={"Origin": "https://ailiza.example.com"},
        json={"note": ""},
    )

    assert response.status_code == 401
    assert response.json().get("code") != "csrf_blocked"


def test_cookie_approval_decision_rejects_allowed_origin_prefix_attack(monkeypatch):
    monkeypatch.setenv("AILIZA_CORS_ORIGINS", "https://ailiza.example.com")
    client = TestClient(app)
    client.cookies.set("ailiza_session", "invalid-but-cookie-auth-shaped")

    response = client.post(
        "/approvals/1/approve",
        headers={"Origin": "https://ailiza.example.com.attacker.invalid"},
        json={"note": ""},
    )

    assert response.status_code == 403
    assert response.json()["code"] == "csrf_blocked"


def test_cookie_approval_decision_rejects_missing_source_for_explicit_origins(monkeypatch):
    monkeypatch.setenv("AILIZA_CORS_ORIGINS", "https://ailiza.example.com")
    client = TestClient(app)
    client.cookies.set("ailiza_session", "invalid-but-cookie-auth-shaped")

    response = client.post("/approvals/1/approve", json={"note": ""})

    assert response.status_code == 403
    assert response.json()["code"] == "csrf_blocked"


def test_cookie_approval_decision_accepts_referer_path_from_configured_origin(monkeypatch):
    monkeypatch.setenv("AILIZA_CORS_ORIGINS", "https://ailiza.example.com")
    client = TestClient(app)
    client.cookies.set("ailiza_session", "invalid-but-cookie-auth-shaped")

    response = client.post(
        "/approvals/1/approve",
        headers={"Referer": "https://ailiza.example.com/freigaben?seite=1"},
        json={"note": ""},
    )

    assert response.status_code == 401
    assert response.json().get("code") != "csrf_blocked"


def test_cookie_approval_decision_rejects_wildcard_in_production(monkeypatch):
    monkeypatch.setenv("AILIZA_ENV", "production")
    monkeypatch.setenv("AILIZA_CORS_ORIGINS", "*")
    client = TestClient(app)
    client.cookies.set("ailiza_session", "invalid-but-cookie-auth-shaped")

    response = client.post(
        "/approvals/1/approve",
        headers={"Origin": "https://ailiza.example.com"},
        json={"note": ""},
    )

    assert response.status_code == 403
    assert response.json()["code"] == "csrf_blocked"
