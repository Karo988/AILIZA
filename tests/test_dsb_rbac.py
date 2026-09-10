"""Regressionstests fuer DSB-001 und die nichtlineare Rollenmatrix."""
from __future__ import annotations

import os

import pytest

os.environ.setdefault("AILIZA_SECRET_KEY", "test-secret-key-minimum-32-chars-ok")
os.environ.setdefault("AILIZA_DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("AILIZA_EXTERNAL_LLM_ENABLED", "false")

STRONG_PASSWORD = "BasisV1!Audit2026"


@pytest.fixture(autouse=True)
def fresh_db():
    from apps.backend.database import engine, init_db, metadata_obj

    metadata_obj.drop_all(engine)
    init_db()
    yield


@pytest.fixture
def client():
    from fastapi.testclient import TestClient

    from apps.backend.main import app

    return TestClient(app, raise_server_exceptions=True, cookies={})


def _headers(role: str, *, user_id: str | None = None) -> dict[str, str]:
    from apps.backend.auth.jwt_handler import create_token

    token = create_token(user_id or f"basis-{role}", "default", role)
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.parametrize("new_role", ["admin", "dsb"])
def test_dsb_cannot_register_privileged_accounts_without_side_effect(client, new_role):
    from apps.backend.database import get_user, list_audit_entries

    user_id = f"dsb-must-not-create-{new_role}"
    audit_before = list_audit_entries(limit=100, tenant_id="default")
    response = client.post(
        "/auth/register",
        json={
            "user_id": user_id,
            "password": STRONG_PASSWORD,
            "role": new_role,
            "tenant_id": "default",
        },
        headers=_headers("dsb"),
    )

    assert response.status_code == 403
    assert get_user(user_id, tenant_id="default") is None
    assert list_audit_entries(limit=100, tenant_id="default") == audit_before


def test_dsb_is_denied_user_manager_and_admin_dependencies():
    from fastapi import HTTPException

    from apps.backend.auth.jwt_handler import create_token
    from apps.backend.auth.rbac import Role, require_role

    class Credentials:
        credentials = create_token("basis-dsb", "default", "dsb")

    for required_role in (Role.USER, Role.MANAGER, Role.ADMIN):
        with pytest.raises(HTTPException) as exc_info:
            require_role(required_role)(credentials=Credentials(), ailiza_session=None)
        assert exc_info.value.status_code == 403


def test_dsb_can_read_the_explicit_audit_control_endpoint(client):
    response = client.get("/admin/audit/events", headers=_headers("dsb"))

    assert response.status_code == 200
    assert "events" in response.json()


def test_admin_can_provision_and_login_audit_viewer(client):
    response = client.post(
        "/auth/register",
        json={
            "user_id": "basis-audit-viewer",
            "password": STRONG_PASSWORD,
            "role": "audit_viewer",
            "tenant_id": "default",
        },
        headers=_headers("admin"),
    )
    assert response.status_code == 201
    assert response.json()["role"] == "audit_viewer"

    login = client.post(
        "/auth/login",
        json={
            "user_id": "basis-audit-viewer",
            "password": STRONG_PASSWORD,
            "tenant_id": "default",
        },
    )
    assert login.status_code == 200
    assert login.json()["role"] == "audit_viewer"


def test_audit_viewer_can_read_audit_but_cannot_register_users(client):
    audit_response = client.get(
        "/admin/audit/events",
        headers=_headers("audit_viewer"),
    )
    assert audit_response.status_code == 200

    register_response = client.post(
        "/auth/register",
        json={
            "user_id": "audit-viewer-must-not-create",
            "password": STRONG_PASSWORD,
            "role": "user",
            "tenant_id": "default",
        },
        headers=_headers("audit_viewer"),
    )
    assert register_response.status_code == 403


def test_admin_and_manager_keep_their_existing_role_grants():
    from apps.backend.auth.rbac import Role, role_allows

    assert role_allows(Role.MANAGER, Role.USER)
    assert role_allows(Role.MANAGER, Role.MANAGER)
    assert role_allows(Role.ADMIN, Role.USER)
    assert role_allows(Role.ADMIN, Role.AUDIT_VIEWER)
    assert role_allows(Role.ADMIN, Role.MANAGER)
    assert role_allows(Role.ADMIN, Role.ADMIN)


def test_unknown_token_role_is_denied_even_for_user_dependency():
    from fastapi import HTTPException

    from apps.backend.auth.jwt_handler import create_token
    from apps.backend.auth.rbac import Role, require_role

    class Credentials:
        credentials = create_token("basis-unknown", "default", "unknown-role")

    with pytest.raises(HTTPException) as exc_info:
        require_role(Role.USER)(credentials=Credentials(), ailiza_session=None)
    assert exc_info.value.status_code == 403
