"""
Tests fuer JWT-Auth und RBAC (Step 1).
"""
from __future__ import annotations

import os
import pytest

os.environ.setdefault("AILIZA_SECRET_KEY", "test-secret-key-minimum-32-chars-ok")
os.environ.setdefault("AILIZA_DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("AILIZA_EXTERNAL_LLM_ENABLED", "false")


# ── JWT-Handler ───────────────────────────────────────────────────────────────
def test_create_and_decode_token():
    from apps.backend.auth.jwt_handler import create_token, decode_token
    token = create_token("alice", "acme", "admin")
    data = decode_token(token)
    assert data.user_id == "alice"
    assert data.tenant_id == "acme"
    assert data.role == "admin"
    assert data.exp is not None


def test_decode_invalid_token_raises():
    from apps.backend.auth.jwt_handler import decode_token
    with pytest.raises(ValueError):
        decode_token("not.a.jwt")


def test_short_secret_raises():
    import importlib
    orig = os.environ.get("AILIZA_SECRET_KEY")
    os.environ["AILIZA_SECRET_KEY"] = "short"
    try:
        import apps.backend.auth.jwt_handler as jh
        importlib.reload(jh)
        with pytest.raises(ValueError):
            jh.create_token("u", "t", "user")
    finally:
        if orig is not None:
            os.environ["AILIZA_SECRET_KEY"] = orig
        importlib.reload(jh)


# ── RBAC / Role ───────────────────────────────────────────────────────────────
def test_role_ordering():
    from apps.backend.auth.rbac import Role
    assert Role.USER < Role.MANAGER < Role.ADMIN < Role.DSB


def test_role_from_str():
    from apps.backend.auth.rbac import Role
    assert Role.from_str("admin") == Role.ADMIN
    assert Role.from_str("MANAGER") == Role.MANAGER
    assert Role.from_str("unknown") == Role.USER


# ── UserInDB / password hashing ───────────────────────────────────────────────
def test_password_hash_and_verify():
    from apps.backend.auth.models import UserCreate, UserInDB
    uc = UserCreate(user_id="bob", tenant_id="t", role="user", plain_password="secret123")
    u = UserInDB.from_create(uc)
    assert u.hashed_password != "secret123"
    assert u.verify_password("secret123")
    assert not u.verify_password("wrong")


# ── Database helpers ──────────────────────────────────────────────────────────
def test_create_and_authenticate_user():
    from apps.backend.database import init_db, create_user, authenticate_user
    from apps.backend.auth.models import UserCreate, UserInDB
    init_db()
    uc = UserCreate(user_id="testuser", tenant_id="t1", role="manager", plain_password="Pa$$w0rd!")
    u = UserInDB.from_create(uc)
    create_user(u.user_id, u.tenant_id, u.role, u.hashed_password)

    result = authenticate_user("testuser", "Pa$$w0rd!", "t1")
    assert result is not None
    assert result["role"] == "manager"
    assert "hashed_password" not in result


def test_authenticate_wrong_password_returns_none():
    from apps.backend.database import init_db, create_user, authenticate_user
    from apps.backend.auth.models import UserCreate, UserInDB
    init_db()
    uc = UserCreate(user_id="testuser2", tenant_id="t1", role="user", plain_password="correct")
    u = UserInDB.from_create(uc)
    create_user(u.user_id, u.tenant_id, u.role, u.hashed_password)

    assert authenticate_user("testuser2", "wrong", "t1") is None


# ── API endpoints ─────────────────────────────────────────────────────────────
@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient
    from apps.backend.main import app
    from apps.backend.database import init_db
    init_db()
    return TestClient(app)


def test_login_no_user(client):
    resp = client.post("/auth/login", json={"user_id": "nobody", "password": "x"})
    assert resp.status_code == 401


def test_register_requires_admin(client):
    resp = client.post("/auth/register",
                       json={"user_id": "newuser", "password": "Pa$$w0rd!"},
                       headers={})
    assert resp.status_code == 401


def test_register_and_login_flow(client):
    from apps.backend.auth.jwt_handler import create_token
    admin_token = create_token("admin1", "default", "admin")
    headers = {"Authorization": f"Bearer {admin_token}"}

    resp = client.post("/auth/register",
                       json={"user_id": "testflow", "password": "FlowPass1!", "role": "user"},
                       headers=headers)
    assert resp.status_code == 201
    assert resp.json()["user_id"] == "testflow"

    resp2 = client.post("/auth/login", json={"user_id": "testflow", "password": "FlowPass1!"})
    assert resp2.status_code == 200
    data = resp2.json()
    assert "access_token" in data
    assert data["role"] == "user"


def test_admin_cleanup_requires_admin(client):
    resp = client.post("/admin/cleanup")
    assert resp.status_code == 401


def test_admin_cleanup_with_admin_token(client):
    from apps.backend.auth.jwt_handler import create_token
    token = create_token("a", "default", "admin")
    resp = client.post("/admin/cleanup", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
