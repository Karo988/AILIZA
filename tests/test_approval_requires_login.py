"""
Regressionsschutz: /approvals/{id}/approve und /reject hatten KEINE
Login-Pflicht -- jede Person, die eine Approval-ID kennt, konnte eine
Freigabe erteilen oder ablehnen. Diese Tests stellen sicher, dass beide
Endpunkte eine gueltige Session verlangen (B1, Freigabe Betreiberin:
"Freigabe nur mit Login").
"""
from __future__ import annotations

import os

os.environ.setdefault("AILIZA_SECRET_KEY", "test-secret-key-minimum-32-chars-ok")
os.environ.setdefault("AILIZA_DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("AILIZA_EXTERNAL_LLM_ENABLED", "false")

import pytest


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
    return TestClient(app, raise_server_exceptions=True, cookies={})


def _user_token():
    from apps.backend.auth.jwt_handler import create_token
    return create_token("betroffene1", "default", "user")


def _manager_token():
    from apps.backend.auth.jwt_handler import create_token
    return create_token("managerin1", "default", "manager")


def _make_pending_approval() -> int:
    from apps.backend.database import create_approval_request
    entry = create_approval_request(
        tool="llm_call",
        input_params={"task_length": 42},
        risk_level="high",
        risk_reason="Test",
        run_id="run-test-1",
    )
    return entry["id"]


def test_approve_without_login_rejected(client):
    approval_id = _make_pending_approval()
    resp = client.post(f"/approvals/{approval_id}/approve")
    assert resp.status_code == 401


def test_reject_without_login_rejected(client):
    approval_id = _make_pending_approval()
    resp = client.post(f"/approvals/{approval_id}/reject")
    assert resp.status_code == 401


def test_approve_with_login_succeeds(client):
    # PR 2 (Nachbesserung): eine einfache Login-Session -- auch mit
    # Role.MANAGER -- reicht seit der Korrektur bewusst NICHT mehr aus, um
    # eine fremde Freigabe zu entscheiden. Es gibt kein pauschales
    # role >= MANAGER mehr; nur eine aktive case_assignment oder eine
    # gepruefte eigene compliance_consent begruenden eine Zustaendigkeit.
    # Fuer den Erfolgsfall wird hier daher eine explizite Zuweisung angelegt.
    from apps.backend.database import create_case_assignment, create_user, get_user

    approval_id = _make_pending_approval()
    # required_approver_roles fuer risk_level="high" ist per Voreinstellung
    # ["admin", "owner"] -- die zugewiesene Testperson braucht daher
    # tatsaechlich die Rolle "admin" (nicht nur irgendeine Zuweisung), seit
    # required_approver_roles verbindlich ausgewertet wird.
    if get_user("adminin1", tenant_id="default") is None:
        create_user("adminin1", "default", "admin", hashed_password="x")
    create_case_assignment(
        case_type="APPROVAL", case_id=str(approval_id), tenant_id="default",
        assigned_to_user_id="adminin1", assigned_by_user_id="adminin1",
        assignment_reason="Test-Zustaendigkeit",
    )
    from apps.backend.auth.jwt_handler import create_token
    resp = client.post(
        f"/approvals/{approval_id}/approve",
        headers={"Authorization": f"Bearer {create_token('adminin1', 'default', 'admin')}"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "approved"
