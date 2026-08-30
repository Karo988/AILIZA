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
