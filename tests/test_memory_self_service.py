"""AP-MEMGOV-UI-001: Self-Service Memory-Facts lesen und einzeln loeschen."""
from __future__ import annotations

import os

os.environ.setdefault("AILIZA_SECRET_KEY", "test-secret-key-minimum-32-chars-ok")
os.environ.setdefault("AILIZA_DATABASE_URL", "sqlite:///:memory:")

import pytest


@pytest.fixture(autouse=True)
def fresh_db():
    from apps.backend.database import init_db, metadata_obj, engine
    metadata_obj.drop_all(engine)
    init_db()
    yield


@pytest.fixture()
def client():
    from fastapi.testclient import TestClient
    from apps.backend.main import app
    return TestClient(app, raise_server_exceptions=True)


@pytest.fixture()
def no_raise_client():
    from fastapi.testclient import TestClient
    from apps.backend.main import app
    return TestClient(app, raise_server_exceptions=False)


def _auth(user_id: str, tenant_id: str = "default") -> dict[str, str]:
    from apps.backend.auth import create_token
    token = create_token(user_id=user_id, tenant_id=tenant_id, role="user")
    return {"Authorization": f"Bearer {token}"}


def _create_user(user_id: str, tenant_id: str = "default") -> None:
    from apps.backend.database import create_user
    create_user(user_id=user_id, tenant_id=tenant_id, role="user", hashed_password="hash")


def _create_memory_fact(
    *,
    user_id: str,
    tenant_id: str = "default",
    title: str = "Kommunikationsstil",
    content: str = "Bitte antworte kompakt.",
    purpose: str = "Personalisierung",
) -> dict:
    from apps.backend.database import create_memory_item, create_memory_source
    source = create_memory_source(
        tenant_id=tenant_id,
        source_type="user_confirmation",
        confirmed_by=user_id,
    )
    return create_memory_item(
        tenant_id=tenant_id,
        scope="user_memory",
        title=title,
        content=content,
        category="preference",
        purpose=purpose,
        source_id=source["id"],
        owner_user_id=user_id,
        status="active",
        created_by=user_id,
    )


def test_memory_facts_require_auth(client):
    assert client.get("/memory/facts").status_code == 401
    assert client.delete("/memory/facts/1").status_code == 401


def test_list_returns_only_own_user_memory_without_internal_fields(client):
    _create_user("alice")
    item = _create_memory_fact(user_id="alice")

    response = client.get("/memory/facts", headers=_auth("alice"))

    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 1
    assert body["items"][0]["id"] == item["id"]
    assert body["items"][0]["title"] == "Kommunikationsstil"
    assert body["items"][0]["content"] == "Bitte antworte kompakt."
    assert "tenant_id" not in body["items"][0]
    assert "owner_user_id" not in body["items"][0]
    assert "created_by" not in body["items"][0]
    assert "approved_by" not in body["items"][0]
    assert "source_id" not in body["items"][0]


def test_list_excludes_foreign_user_in_same_tenant(client):
    _create_user("alice")
    _create_user("bob")
    _create_memory_fact(user_id="alice", title="Alice")
    bob_item = _create_memory_fact(user_id="bob", title="Bob")

    response = client.get("/memory/facts", headers=_auth("bob"))

    assert response.status_code == 200
    assert [item["id"] for item in response.json()["items"]] == [bob_item["id"]]


def test_list_excludes_foreign_tenant(client):
    _create_user("alice", "tenant-a")
    _create_user("bob", "tenant-b")
    _create_memory_fact(user_id="alice", tenant_id="tenant-a", title="Tenant A")
    bob_item = _create_memory_fact(user_id="bob", tenant_id="tenant-b", title="Tenant B")

    response = client.get("/memory/facts", headers=_auth("bob", "tenant-b"))

    assert response.status_code == 200
    assert [item["id"] for item in response.json()["items"]] == [bob_item["id"]]


def test_delete_own_memory_fact_soft_deletes_and_hides_it(client):
    from apps.backend.database import get_memory_item

    _create_user("alice")
    item = _create_memory_fact(user_id="alice")

    response = client.delete(f"/memory/facts/{item['id']}", headers=_auth("alice"))

    assert response.status_code == 200
    assert response.json() == {"status": "deleted", "id": item["id"]}
    assert get_memory_item(item["id"])["status"] == "deleted"
    assert client.get("/memory/facts", headers=_auth("alice")).json()["items"] == []


def test_delete_foreign_user_memory_fact_returns_generic_404(client):
    from apps.backend.database import get_memory_item

    _create_user("alice")
    _create_user("bob")
    item = _create_memory_fact(user_id="alice")

    response = client.delete(f"/memory/facts/{item['id']}", headers=_auth("bob"))

    assert response.status_code == 404
    assert response.json()["detail"] == "Memory-Fact nicht gefunden."
    assert get_memory_item(item["id"])["status"] == "active"


def test_delete_unknown_memory_fact_returns_generic_404(client):
    _create_user("alice")

    response = client.delete("/memory/facts/999999", headers=_auth("alice"))

    assert response.status_code == 404
    assert response.json()["detail"] == "Memory-Fact nicht gefunden."


def test_delete_removes_memory_visibility_for_deleted_fact(client):
    from sqlalchemy import select
    from apps.backend.database import engine, memory_visibility

    _create_user("alice")
    item = _create_memory_fact(user_id="alice")

    response = client.delete(f"/memory/facts/{item['id']}", headers=_auth("alice"))

    assert response.status_code == 200
    with engine.begin() as conn:
        remaining = conn.execute(
            select(memory_visibility).where(memory_visibility.c.memory_item_id == item["id"])
        ).mappings().all()
    assert remaining == []


def test_delete_writes_memory_deleted_audit_event(client):
    from apps.backend.database import list_audit_entries

    _create_user("alice")
    item = _create_memory_fact(user_id="alice")

    response = client.delete(f"/memory/facts/{item['id']}", headers=_auth("alice"))

    assert response.status_code == 200
    events = list_audit_entries(limit=10, tenant_id="default")
    event = next(entry for entry in events if entry["action"] == "memory.deleted")
    assert event["metadata"] == {
        "memory_item_id": item["id"],
        "scope": "user_memory",
        "actor_user_id": "alice",
        "result": "deleted",
    }
    assert event["previous_hash"]
    assert event["entry_hash"]
    assert event["entry_hash"] != "pending"


def test_delete_audit_contains_no_memory_raw_content(client):
    from apps.backend.database import list_audit_entries

    _create_user("alice")
    item = _create_memory_fact(
        user_id="alice",
        title="Privater Titel",
        content="Privater Memory-Rohinhalt",
        purpose="Privater Zweck",
    )

    response = client.delete(f"/memory/facts/{item['id']}", headers=_auth("alice"))

    assert response.status_code == 200
    event = next(entry for entry in list_audit_entries(limit=10) if entry["action"] == "memory.deleted")
    serialized = str(event["metadata"])
    assert "Privater Titel" not in serialized
    assert "Privater Memory-Rohinhalt" not in serialized
    assert "Privater Zweck" not in serialized
    assert "title" not in event["metadata"]
    assert "content" not in event["metadata"]
    assert "purpose" not in event["metadata"]


def test_audit_failure_does_not_report_success_or_commit_delete(no_raise_client, monkeypatch):
    import apps.backend.routers.approvals as approvals_router
    from apps.backend.database import get_memory_item

    _create_user("alice")
    item = _create_memory_fact(user_id="alice")

    def _boom(*args, **kwargs):
        raise RuntimeError("audit failed")

    monkeypatch.setattr(approvals_router, "_write_memory_deleted_audit_in_transaction", _boom)
    response = no_raise_client.delete(f"/memory/facts/{item['id']}", headers=_auth("alice"))

    assert response.status_code == 500
    assert get_memory_item(item["id"])["status"] == "active"
