"""
Tests fuer Account-Lockout nach wiederholten Fehlversuchen.
"""
from __future__ import annotations

import os
import pytest

os.environ.setdefault("AILIZA_SECRET_KEY", "test-secret-key-minimum-32-chars-ok")
os.environ.setdefault("AILIZA_DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("AILIZA_EXTERNAL_LLM_ENABLED", "false")
os.environ.setdefault("AILIZA_MAX_LOGIN_ATTEMPTS", "3")
os.environ.setdefault("AILIZA_LOCKOUT_MINUTES", "15")


@pytest.fixture(autouse=True)
def fresh_db():
    from apps.backend.database import init_db, metadata_obj, engine
    metadata_obj.drop_all(engine)
    init_db()
    yield


def _make_user(user_id: str = "testuser", tenant_id: str = "default") -> None:
    from apps.backend.database import create_user
    from apps.backend.auth.models import UserCreate, UserInDB
    uc = UserCreate(user_id=user_id, tenant_id=tenant_id, role="user", plain_password="Correct1!")
    u = UserInDB.from_create(uc)
    create_user(u.user_id, u.tenant_id, u.role, u.hashed_password)


def test_correct_login_works():
    from apps.backend.database import authenticate_user
    _make_user()
    assert authenticate_user("testuser", "Correct1!") is not None


def test_wrong_password_returns_none():
    from apps.backend.database import authenticate_user
    _make_user()
    assert authenticate_user("testuser", "Wrong!") is None


def test_account_locked_after_max_attempts():
    from apps.backend.database import authenticate_user
    _make_user()
    # 3 Fehlversuche (entspricht AILIZA_MAX_LOGIN_ATTEMPTS)
    for _ in range(3):
        authenticate_user("testuser", "wrong")
    # Jetzt auch mit richtigem Passwort gesperrt
    assert authenticate_user("testuser", "Correct1!") is None


def test_counter_resets_after_success():
    from apps.backend.database import authenticate_user
    _make_user()
    authenticate_user("testuser", "wrong")
    authenticate_user("testuser", "wrong")
    # Erfolgreicher Login → Reset
    result = authenticate_user("testuser", "Correct1!")
    assert result is not None
    # Danach funktioniert Login weiter
    assert authenticate_user("testuser", "Correct1!") is not None


def test_nonexistent_user_returns_none():
    from apps.backend.database import authenticate_user
    assert authenticate_user("ghost", "anypassword") is None


def test_lockout_via_api():
    """Login-Endpunkt gibt 401 zurueck, auch wenn Account gesperrt."""
    from apps.backend.database import init_db
    from fastapi.testclient import TestClient
    from apps.backend.main import app
    init_db()
    _make_user("lockeduser", "default")
    client = TestClient(app)

    # 3 Fehlversuche
    for _ in range(3):
        client.post("/auth/login", json={"user_id": "lockeduser", "password": "wrong"})

    # Richtiges Passwort — Account gesperrt → trotzdem 401
    resp = client.post("/auth/login", json={"user_id": "lockeduser", "password": "Correct1!"})
    assert resp.status_code == 401


def test_password_policy_enforced_on_register():
    """Schwaches Passwort beim Register wird abgelehnt."""
    from apps.backend.auth.jwt_handler import create_token
    from fastapi.testclient import TestClient
    from apps.backend.main import app
    client = TestClient(app)
    admin_token = create_token("admin", "default", "admin")

    resp = client.post(
        "/auth/register",
        json={"user_id": "weakuser", "password": "short"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 422  # Pydantic-Validation schlägt an


def test_strong_password_accepted_on_register():
    """Starkes Passwort beim Register wird akzeptiert."""
    from apps.backend.auth.jwt_handler import create_token
    from apps.backend.database import init_db
    from fastapi.testclient import TestClient
    from apps.backend.main import app
    init_db()
    client = TestClient(app)
    admin_token = create_token("admin", "default", "admin")

    resp = client.post(
        "/auth/register",
        json={"user_id": "stronguser", "password": "StrongPass1!"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 201
