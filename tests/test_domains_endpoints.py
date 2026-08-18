"""Stufe B: HTTP-Endpunkte fuer Bereichsfreischaltung und -mitgliedschaft.

Laeuft gegen die normale Test-Datenbank (sqlite:///:memory:, siehe
conftest.py) -- die Domain-Tabellen sind Teil des regulaeren Schemas
(db_schema.py), aber ohne Migration nicht mit den 13 festen Bereichscodes
befuellt. Deshalb wird hier direkt die Tabelle business_domains ueber
init_db() hinaus mit einem Testbereich versehen, statt Alembic in-process
laufen zu lassen.
"""
from __future__ import annotations

import os

os.environ.setdefault("AILIZA_SECRET_KEY", "test-secret-key-minimum-32-chars-ok")

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from apps.backend.auth.jwt_handler import create_token
from apps.backend.database import engine
from apps.backend.db_schema import business_domains
from apps.backend.main import app

TENANT = "domeptest"


@pytest.fixture()
def client():
    return TestClient(app)


@pytest.fixture(autouse=True)
def _seed_test_domain():
    with engine.begin() as con:
        exists = con.execute(
            business_domains.select().where(business_domains.c.code == "accounting")
        ).first()
        if exists is None:
            con.execute(
                business_domains.insert().values(
                    code="accounting", name="Buchhaltung", sensitivity_level="normal",
                    is_system_domain=1, created_at=datetime.now(timezone.utc),
                    updated_at=datetime.now(timezone.utc),
                )
            )
    yield


def test_bootstrap_requires_admin(client):
    user_token = create_token("u1", TENANT, "user")
    resp = client.post(
        "/domains/bootstrap",
        json={"domain_code": "accounting", "reason": "Testfreigabe", "first_manager_user_id": "mgr1"},
        headers={"Authorization": f"Bearer {user_token}"},
    )
    assert resp.status_code == 403


def test_bootstrap_and_own_memberships_roundtrip(client):
    admin_token = create_token("admin1", TENANT, "admin")
    resp = client.post(
        "/domains/bootstrap",
        json={"domain_code": "accounting", "reason": "Testfreigabe", "first_manager_user_id": "mgr1"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "enabled"

    mgr_token = create_token("mgr1", TENANT, "user")
    resp2 = client.get("/domains/my-memberships", headers={"Authorization": f"Bearer {mgr_token}"})
    assert resp2.status_code == 200
    codes = {m["code"] for m in resp2.json()}
    assert "accounting" in codes


def test_bootstrap_without_reason_returns_400(client):
    admin_token = create_token("admin2", TENANT, "admin")
    resp = client.post(
        "/domains/bootstrap",
        json={"domain_code": "accounting", "reason": "", "first_manager_user_id": "mgr2"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 400


def test_my_memberships_requires_auth(client):
    resp = client.get("/domains/my-memberships")
    assert resp.status_code == 401


def test_revoke_last_manager_returns_409(client):
    tenant = TENANT + "-revoke"
    admin_token = create_token("admin3", tenant, "admin")
    resp0 = client.post(
        "/domains/bootstrap",
        json={"domain_code": "accounting", "reason": "Testfreigabe", "first_manager_user_id": "mgr3"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp0.status_code == 200, resp0.text
    from sqlalchemy import select
    from apps.backend.db_schema import user_domain_memberships
    with engine.begin() as con:
        membership_id = con.execute(
            select(user_domain_memberships.c.id)
            .where(user_domain_memberships.c.tenant_id == tenant)
            .where(user_domain_memberships.c.user_id == "mgr3")
        ).first()[0]

    resp = client.post(
        f"/domains/memberships/{membership_id}/revoke",
        json={"revocation_reason": "Testversuch"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 409


def test_revoke_requires_admin(client):
    user_token = create_token("u2", TENANT, "user")
    resp = client.post(
        "/domains/memberships/1/revoke",
        json={"revocation_reason": "Testversuch"},
        headers={"Authorization": f"Bearer {user_token}"},
    )
    assert resp.status_code == 403
