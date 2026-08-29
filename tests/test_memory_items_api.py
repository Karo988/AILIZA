"""Persönliche-Gedächtnis-Übersicht: HTTP-Schicht (GET/PATCH/DELETE
/api/memory-items). Prüft Auth-Pflicht, Ownership (404 statt 403 bei
Fremdzugriff -- verrät nicht die Existenz fremder Einträge) und dass die
Antwort keine fremden Felder preisgibt. Die Scope-/Owner-/Tenant-Regeln
selbst sind in tests/test_memory_items_overview.py auf DB-Ebene geprüft.
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


@pytest.fixture()
def client():
    from fastapi.testclient import TestClient
    from apps.backend.main import app
    return TestClient(app, raise_server_exceptions=True)


def _auth(user_id: str, tenant_id: str = "default"):
    from apps.backend.auth import create_token
    token = create_token(user_id=user_id, tenant_id=tenant_id, role="user")
    return {"Authorization": f"Bearer {token}"}


def _make_user(user_id: str, tenant_id: str = "default"):
    from apps.backend.database import create_user, upsert_user_settings
    create_user(user_id=user_id, tenant_id=tenant_id, role="user", hashed_password="hash")
    upsert_user_settings(user_id, tenant_id, speichermodus="immer_fragen")


def _confirmed_item(user_id: str, tenant_id: str = "default"):
    from apps.backend.database import create_memory_suggestion, confirm_memory_suggestion
    s = create_memory_suggestion(
        user_id=user_id, tenant_id=tenant_id, suggested_scope="user_memory",
        suggested_title="Kurze Antworten", suggested_content="Nutzer bevorzugt kurze Antworten.",
        suggested_purpose="Antwortstil", source_type="user_confirmation",
    )
    r = confirm_memory_suggestion(s["id"], confirmed_by=user_id, tenant_id=tenant_id)
    return r["memory_item_id"]


def test_memory_items_require_auth(client):
    assert client.get("/api/memory-items").status_code == 401
    assert client.patch("/api/memory-items/1", json={"title": "x"}).status_code == 401
    assert client.delete("/api/memory-items/1").status_code == 401


def test_list_returns_only_own(client):
    _make_user("alice")
    _make_user("bob")
    _confirmed_item("alice")
    _confirmed_item("bob")
    r = client.get("/api/memory-items", headers=_auth("alice"))
    assert r.status_code == 200
    body = r.json()
    assert body["count"] == 1
    assert body["items"][0]["owner_user_id"] == "alice"


def test_update_own_item(client):
    _make_user("alice")
    item_id = _confirmed_item("alice")
    r = client.patch(f"/api/memory-items/{item_id}", json={"title": "Neuer Titel"}, headers=_auth("alice"))
    assert r.status_code == 200
    assert r.json()["item"]["title"] == "Neuer Titel"


def test_update_foreign_item_returns_404(client):
    _make_user("alice")
    _make_user("bob")
    item_id = _confirmed_item("alice")
    r = client.patch(f"/api/memory-items/{item_id}", json={"title": "Übernommen"}, headers=_auth("bob"))
    assert r.status_code == 404


def test_update_secret_content_returns_422(client):
    _make_user("alice")
    item_id = _confirmed_item("alice")
    r = client.patch(
        f"/api/memory-items/{item_id}",
        json={"content": "Mein API-Key ist sk-abcdefghijklmnopqrstuvwxyz123456"},
        headers=_auth("alice"),
    )
    assert r.status_code == 422


def test_delete_own_item(client):
    _make_user("alice")
    item_id = _confirmed_item("alice")
    r = client.delete(f"/api/memory-items/{item_id}", headers=_auth("alice"))
    assert r.status_code == 200
    assert r.json()["status"] == "deleted"
    # nach dem Loeschen nicht mehr in der Liste:
    r2 = client.get("/api/memory-items", headers=_auth("alice"))
    assert r2.json()["count"] == 0


def test_delete_foreign_item_returns_404(client):
    _make_user("alice")
    _make_user("bob")
    item_id = _confirmed_item("alice")
    r = client.delete(f"/api/memory-items/{item_id}", headers=_auth("bob"))
    assert r.status_code == 404
    # unveraendert -- steht weiter bei alice:
    r2 = client.get("/api/memory-items", headers=_auth("alice"))
    assert r2.json()["count"] == 1


def test_delete_nonexistent_item_returns_404(client):
    _make_user("alice")
    r = client.delete("/api/memory-items/999999", headers=_auth("alice"))
    assert r.status_code == 404


def test_update_writes_audit_entry_without_content(client):
    from apps.backend.database import list_audit_entries

    _make_user("alice")
    item_id = _confirmed_item("alice")
    client.patch(f"/api/memory-items/{item_id}", json={"title": "Neuer Titel"}, headers=_auth("alice"))
    entries = [e for e in list_audit_entries(limit=50, tenant_id="default") if e["action"] == "memory_item.updated"]
    assert len(entries) == 1
    assert entries[0]["metadata"]["item_id"] == item_id
    assert "Neuer Titel" not in str(entries[0]["metadata"])


def test_delete_writes_audit_entry(client):
    from apps.backend.database import list_audit_entries

    _make_user("alice")
    item_id = _confirmed_item("alice")
    client.delete(f"/api/memory-items/{item_id}", headers=_auth("alice"))
    entries = [e for e in list_audit_entries(limit=50, tenant_id="default") if e["action"] == "memory_item.deleted"]
    assert len(entries) == 1
    assert entries[0]["metadata"]["item_id"] == item_id
