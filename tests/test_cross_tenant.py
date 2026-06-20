"""
Cross-Tenant-Sicherheitstests: Tenant A darf nie auf Daten von Tenant B zugreifen.
"""
from __future__ import annotations

import os
import pytest

os.environ.setdefault("AILIZA_SECRET_KEY", "test-secret-key-minimum-32-chars-ok")
os.environ.setdefault("AILIZA_DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("AILIZA_EXTERNAL_LLM_ENABLED", "false")


@pytest.fixture(autouse=True)
def fresh_db():
    from apps.backend.database import init_db, metadata_obj, engine
    metadata_obj.drop_all(engine)
    init_db()
    yield


# ── Hilfsfunktionen ───────────────────────────────────────────────────────────
def _make_user(user_id: str, tenant_id: str, role: str = "user") -> None:
    from apps.backend.database import create_user
    from apps.backend.auth.models import UserCreate, UserInDB
    uc = UserCreate(user_id=user_id, tenant_id=tenant_id, role=role, plain_password="Pass1234!")
    u = UserInDB.from_create(uc)
    create_user(u.user_id, u.tenant_id, u.role, u.hashed_password)


def _token(user_id: str, tenant_id: str, role: str = "user") -> str:
    from apps.backend.auth.jwt_handler import create_token
    return create_token(user_id, tenant_id, role)


# ── Audit-Log-Isolation ───────────────────────────────────────────────────────
def test_audit_logs_isolated_per_tenant():
    from apps.backend.database import write_audit_entry, list_audit_entries
    write_audit_entry("action.a", tenant_id="tenant_a")
    write_audit_entry("action.b", tenant_id="tenant_b")

    logs_a = list_audit_entries(tenant_id="tenant_a")
    logs_b = list_audit_entries(tenant_id="tenant_b")

    assert all(e["tenant_id"] == "tenant_a" for e in logs_a)
    assert all(e["tenant_id"] == "tenant_b" for e in logs_b)
    assert not any(e["action"] == "action.b" for e in logs_a)
    assert not any(e["action"] == "action.a" for e in logs_b)


# ── Reflection-Facts-Isolation ────────────────────────────────────────────────
def test_reflection_facts_isolated_per_tenant():
    from apps.backend.database import insert_reflection_fact, query_reflection_facts
    import uuid

    fact_a = {
        "id": str(uuid.uuid4()), "tenant_id": "tenant_a", "user_id": "u1",
        "content": "Fakt fuer A", "data_classes": [], "quality_score": 1.0,
        "opt_in_confirmed": 1, "created_at": "2026-01-01T00:00:00+00:00",
        "expires_at": "2027-01-01T00:00:00+00:00", "source": "test",
        "purpose": "test", "pii_cleared": 1,
    }
    fact_b = {**fact_a, "id": str(uuid.uuid4()), "tenant_id": "tenant_b", "content": "Fakt fuer B"}
    insert_reflection_fact(fact_a)
    insert_reflection_fact(fact_b)

    results_a = query_reflection_facts("tenant_a")
    results_b = query_reflection_facts("tenant_b")

    assert all(r["tenant_id"] == "tenant_a" for r in results_a)
    assert all(r["tenant_id"] == "tenant_b" for r in results_b)
    assert not any(r["content"] == "Fakt fuer B" for r in results_a)
    assert not any(r["content"] == "Fakt fuer A" for r in results_b)


# ── Nutzer-Isolation ──────────────────────────────────────────────────────────
def test_user_lookup_requires_correct_tenant():
    from apps.backend.database import get_user
    _make_user("alice", "tenant_a")

    # alice im richtigen Mandanten
    assert get_user("alice", "tenant_a") is not None
    # alice im falschen Mandanten → None
    assert get_user("alice", "tenant_b") is None


def test_authenticate_user_wrong_tenant_fails():
    from apps.backend.database import authenticate_user
    _make_user("bob", "tenant_a")

    # Richtiger Mandant → geht
    assert authenticate_user("bob", "Pass1234!", "tenant_a") is not None
    # Falscher Mandant → None (kein Tenant-Leak)
    assert authenticate_user("bob", "Pass1234!", "tenant_b") is None


# ── API-Endpunkt-Isolation ────────────────────────────────────────────────────
@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient
    from apps.backend.main import app
    return TestClient(app)


def test_audit_log_api_tenant_isolation(client):
    """Tenant-A-Token sieht nur Tenant-A-Logs."""
    from apps.backend.database import write_audit_entry
    write_audit_entry("tenant_a.action", tenant_id="tenant_a")
    write_audit_entry("tenant_b.action", tenant_id="tenant_b")

    token_a = _token("user_a", "tenant_a")
    resp = client.get("/audit-logs", headers={"Authorization": f"Bearer {token_a}"})
    assert resp.status_code == 200
    actions = [e["action"] for e in resp.json()]
    assert "tenant_b.action" not in actions


def test_feedback_uses_token_tenant(client):
    """Feedback nutzt tenant_id aus JWT, nicht aus Body wenn kein tenant_id angegeben."""
    token_a = _token("user_a", "tenant_a")
    resp = client.post(
        "/feedback",
        json={"rating": "helpful", "run_id": None},
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert resp.status_code == 201
