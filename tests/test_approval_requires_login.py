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
    approval_id = _make_pending_approval()
    resp = client.post(
        f"/approvals/{approval_id}/approve",
        headers={"Authorization": f"Bearer {_user_token()}"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "approved"
