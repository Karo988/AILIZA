"""
Tests fuer die Capability Registry.
Prueft: Fail-closed, Datenklassen-Checks, Policy-Integration, Admin-Endpoint.
"""
from __future__ import annotations

import os
import pytest

os.environ.setdefault("AILIZA_SECRET_KEY", "test-secret-key-minimum-32-chars-ok")
os.environ.setdefault("AILIZA_DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("AILIZA_EXTERNAL_LLM_ENABLED", "false")


# ── Capability-Check-Logik ────────────────────────────────────────────────────
def test_unknown_capability_blocked():
    from apps.backend.capabilities.registry import check_capability
    from apps.backend.governance.data_governance import DataClass
    result = check_capability("nonexistent_skill", [DataClass.PUBLIC])
    assert not result.allowed
    assert "nicht registriert" in result.reason


def test_disabled_capability_blocked():
    from apps.backend.capabilities.registry import check_capability
    from apps.backend.governance.data_governance import DataClass
    # messenger_send ist enabled=False
    result = check_capability("messenger_send", [DataClass.PUBLIC])
    assert not result.allowed
    assert result.capability_enabled is False


def test_public_data_web_search_allowed():
    from apps.backend.capabilities.registry import check_capability
    from apps.backend.governance.data_governance import DataClass
    result = check_capability("web_search", [DataClass.PUBLIC])
    assert result.allowed


def test_credentials_blocked_for_llm_call():
    from apps.backend.capabilities.registry import check_capability
    from apps.backend.governance.data_governance import DataClass
    result = check_capability("llm_call", [DataClass.CREDENTIALS])
    assert not result.allowed
    assert "nicht erlaubt" in result.reason


def test_special_category_blocked_for_web_search():
    from apps.backend.capabilities.registry import check_capability
    from apps.backend.governance.data_governance import DataClass
    result = check_capability("web_search", [DataClass.SPECIAL_CATEGORY])
    assert not result.allowed


def test_memory_store_requires_approval():
    from apps.backend.capabilities.registry import check_capability
    from apps.backend.governance.data_governance import DataClass
    # Ohne approval_given → APPROVAL_REQUIRED
    result = check_capability("memory_store", [DataClass.PUBLIC], approval_given=False)
    assert not result.allowed
    assert result.requires_approval is True


def test_memory_store_allowed_with_approval():
    from apps.backend.capabilities.registry import check_capability
    from apps.backend.governance.data_governance import DataClass
    result = check_capability("memory_store", [DataClass.PUBLIC], approval_given=True)
    assert result.allowed


def test_skill_propose_requires_approval():
    from apps.backend.capabilities.registry import check_capability
    from apps.backend.governance.data_governance import DataClass
    result = check_capability("skill_propose", [DataClass.PUBLIC], approval_given=False)
    assert not result.allowed


def test_audit_write_always_allowed():
    from apps.backend.capabilities.registry import check_capability
    from apps.backend.governance.data_governance import DataClass
    result = check_capability("audit_write", [DataClass.PUBLIC])
    assert result.allowed
    assert result.risk_level == "low"


def test_get_all_capabilities_returns_list():
    from apps.backend.capabilities.registry import get_all_capabilities
    caps = get_all_capabilities()
    assert len(caps) >= 8
    ids = [c["capability_id"] for c in caps]
    assert "llm_call" in ids
    assert "memory_store" in ids
    assert "skill_propose" in ids
    assert "messenger_send" in ids


def test_get_capability_by_id():
    from apps.backend.capabilities.registry import get_capability
    cap = get_capability("web_search")
    assert cap is not None
    assert cap["external_call"] is True
    assert get_capability("does_not_exist") is None


# ── Admin-Endpoint ────────────────────────────────────────────────────────────
@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient
    from apps.backend.main import app
    from apps.backend.database import init_db
    init_db()
    return TestClient(app)


def _admin_headers() -> dict[str, str]:
    from apps.backend.auth.jwt_handler import create_token
    return {"Authorization": f"Bearer {create_token('admin', 'default', 'admin')}"}


def _manager_headers() -> dict[str, str]:
    from apps.backend.auth.jwt_handler import create_token
    return {"Authorization": f"Bearer {create_token('mgr', 'default', 'manager')}"}


def test_list_capabilities_requires_admin(client):
    resp = client.get("/admin/capabilities")
    assert resp.status_code == 401


def test_list_capabilities_as_admin(client):
    resp = client.get("/admin/capabilities", headers=_admin_headers())
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert any(c["capability_id"] == "llm_call" for c in data)


def test_capability_check_endpoint_public_allowed(client):
    resp = client.post(
        "/admin/capabilities/check",
        json={"capability_id": "web_search", "data_classes": ["public"]},
        headers=_manager_headers(),
    )
    assert resp.status_code == 200
    assert resp.json()["allowed"] is True


def test_capability_check_endpoint_credentials_blocked(client):
    resp = client.post(
        "/admin/capabilities/check",
        json={"capability_id": "llm_call", "data_classes": ["credentials"]},
        headers=_manager_headers(),
    )
    assert resp.status_code == 200
    assert resp.json()["allowed"] is False


def test_capability_check_endpoint_unknown(client):
    resp = client.post(
        "/admin/capabilities/check",
        json={"capability_id": "unknown_skill", "data_classes": ["public"]},
        headers=_manager_headers(),
    )
    assert resp.status_code == 200
    assert resp.json()["allowed"] is False
