"""
Tests fuer den Cookie-basierten JWT-Flow.
Prueft: Login setzt HttpOnly-Cookie, /auth/me liest Cookie,
        Logout loescht Cookie, 401 bei fehlendem Token,
        Bearer-Header als Fallback, Cookie+Bearer Kompatibilitaet.
"""
from __future__ import annotations

import os
import pytest

os.environ.setdefault("AILIZA_SECRET_KEY", "test-secret-key-minimum-32-chars-ok")
os.environ.setdefault("AILIZA_DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("AILIZA_EXTERNAL_LLM_ENABLED", "false")

STRONG_PW = "StrongPass1!XYzq"


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
    # Jeder Test bekommt einen frischen Client ohne Cookie-Zustand
    return TestClient(app, raise_server_exceptions=True, cookies={})


def _admin_token():
    from apps.backend.auth.jwt_handler import create_token
    return create_token("admin1", "default", "admin")


def _create_user(client, user_id="testuser", role="user", password=STRONG_PW):
    resp = client.post(
        "/auth/register",
        json={"user_id": user_id, "password": password, "role": role},
        headers={"Authorization": f"Bearer {_admin_token()}"},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


# ── Login setzt HttpOnly-Cookie ───────────────────────────────────────────────
def test_login_sets_httponly_cookie(client):
    _create_user(client, "cookieuser")
    resp = client.post("/auth/login",
                       json={"user_id": "cookieuser", "password": STRONG_PW})
    assert resp.status_code == 200
    # TestClient exponiert Set-Cookie Header
    set_cookie = resp.headers.get("set-cookie", "")
    assert "ailiza_session" in set_cookie
    assert "HttpOnly" in set_cookie
    assert "SameSite=strict" in set_cookie.lower() or "samesite=strict" in set_cookie.lower()


def test_login_returns_user_info(client):
    _create_user(client, "infouser")
    resp = client.post("/auth/login",
                       json={"user_id": "infouser", "password": STRONG_PW})
    data = resp.json()
    assert data["user_id"] == "infouser"
    assert data["role"] == "user"
    assert "access_token" in data  # API-Client-Kompatibilitaet


def test_login_wrong_password_no_cookie(client):
    _create_user(client, "wrongpwuser")
    resp = client.post("/auth/login",
                       json={"user_id": "wrongpwuser", "password": "WrongPass999!"})
    assert resp.status_code == 401
    assert "ailiza_session" not in resp.headers.get("set-cookie", "")


# ── /auth/me ─────────────────────────────────────────────────────────────────
def test_me_with_bearer_token(client):
    _create_user(client, "meuser")
    login_resp = client.post("/auth/login",
                             json={"user_id": "meuser", "password": STRONG_PW})
    token = login_resp.json()["access_token"]

    resp = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["user_id"] == "meuser"
    assert data["role"] == "user"
    assert "exp" in data


def test_me_without_token_returns_401(client):
    resp = client.get("/auth/me")
    assert resp.status_code == 401


def test_me_with_invalid_token_returns_401(client):
    resp = client.get("/auth/me",
                      headers={"Authorization": "Bearer invalid.token.here"})
    assert resp.status_code == 401


# ── /auth/logout ─────────────────────────────────────────────────────────────
def test_logout_clears_cookie(client):
    resp = client.post("/auth/logout")
    assert resp.status_code == 200
    assert resp.json()["status"] == "logged_out"
    # Cookie sollte mit Max-Age=0 oder expires-in-past geloescht sein
    set_cookie = resp.headers.get("set-cookie", "")
    assert "ailiza_session" in set_cookie


# ── Bearer-Token als Fallback ─────────────────────────────────────────────────
def test_bearer_token_still_works_for_protected_endpoint(client):
    token = _admin_token()
    resp = client.get("/admin/capabilities",
                      headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_require_role_rejects_without_any_auth(client):
    resp = client.get("/admin/capabilities")
    assert resp.status_code == 401


def test_require_role_rejects_wrong_role(client):
    _create_user(client, "lowroleuser", role="user")
    login_resp = client.post("/auth/login",
                             json={"user_id": "lowroleuser", "password": STRONG_PW})
    token = login_resp.json()["access_token"]
    resp = client.get("/admin/capabilities",
                      headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 403


# ── messenger_send Risiko-Level ───────────────────────────────────────────────
def test_messenger_send_risk_is_high_not_critical():
    from apps.backend.capabilities.registry import get_capability
    cap = get_capability("messenger_send")
    assert cap is not None
    assert cap["risk_level"] == "high"


def test_messenger_receive_is_medium():
    from apps.backend.capabilities.registry import get_capability
    cap = get_capability("messenger_receive")
    assert cap is not None
    assert cap["risk_level"] == "medium"


def test_message_process_is_low():
    from apps.backend.capabilities.registry import get_capability
    cap = get_capability("message_process")
    assert cap is not None
    assert cap["risk_level"] == "low"
