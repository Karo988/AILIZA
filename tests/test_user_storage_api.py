"""TS2 – Serverseitige Speicherung: API-Endpunkte (Projekte & Chats).

Prueft: Auth-Gate (401), Mandanten-/Nutzer-Isolation (Fremdzugriff -> 404),
Optimistic Locking (409 bei Versionskonflikt), server-berechneter
message_count. Kein Test sendet echte PII an externe Dienste.
"""
import os

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("AILIZA_SECRET_KEY", "test-secret-key-minimum-32-chars-ok")
os.environ.setdefault("AILIZA_DATABASE_URL", "sqlite:///:memory:")


@pytest.fixture()
def client():
    from apps.backend.main import app
    from apps.backend.database import init_db, metadata_obj, engine
    metadata_obj.drop_all(engine)
    init_db()
    return TestClient(app, raise_server_exceptions=True)


def _auth(user_id: str, tenant_id: str = "default"):
    from apps.backend.auth import create_token
    token = create_token(user_id=user_id, tenant_id=tenant_id, role="user")
    return {"Authorization": f"Bearer {token}"}


# ── Auth-Gate ────────────────────────────────────────────────────────────────

def test_projects_require_auth(client):
    assert client.get("/api/user-projects").status_code == 401
    assert client.post("/api/user-projects", json={"name": "X"}).status_code == 401


def test_chats_require_auth(client):
    assert client.get("/api/user-chats").status_code == 401
    assert client.put("/api/user-chats/c1", json={"messages": []}).status_code == 401


# ── Projekte: CRUD ───────────────────────────────────────────────────────────

def test_create_and_list_project(client):
    h = _auth("alice")
    r = client.post("/api/user-projects", json={"name": "Angebot Q3"}, headers=h)
    assert r.status_code == 201
    pid = r.json()["id"]
    assert r.json()["version"] == 1

    r2 = client.get("/api/user-projects", headers=h)
    assert r2.status_code == 200
    assert r2.json()["count"] == 1
    assert r2.json()["projects"][0]["id"] == pid


def test_update_project_increments_version(client):
    h = _auth("alice")
    pid = client.post("/api/user-projects", json={"name": "A"}, headers=h).json()["id"]
    r = client.patch(f"/api/user-projects/{pid}", json={"name": "B"}, headers=h)
    assert r.status_code == 200
    assert r.json()["version"] == 2


def test_patch_missing_project_404(client):
    h = _auth("alice")
    r = client.patch("/api/user-projects/nope", json={"name": "X"}, headers=h)
    assert r.status_code == 404


def test_version_conflict_returns_409(client):
    h = _auth("alice")
    pid = client.post("/api/user-projects", json={"name": "A"}, headers=h).json()["id"]
    # aktueller Stand = 1; wir behaupten faelschlich, wir haetten Version 5
    r = client.patch(f"/api/user-projects/{pid}",
                     json={"name": "B", "expected_version": 5}, headers=h)
    assert r.status_code == 409
    assert r.json()["detail"]["current_version"] == 1


def test_delete_project(client):
    h = _auth("alice")
    pid = client.post("/api/user-projects", json={"name": "A"}, headers=h).json()["id"]
    assert client.delete(f"/api/user-projects/{pid}", headers=h).status_code == 200
    assert client.delete(f"/api/user-projects/{pid}", headers=h).status_code == 404


# ── Isolation: fremder Nutzer / fremder Mandant ──────────────────────────────

def test_foreign_user_cannot_see_projects(client):
    a, b = _auth("alice"), _auth("bob")
    client.post("/api/user-projects", json={"name": "Alice-Only"}, headers=a)
    assert client.get("/api/user-projects", headers=b).json()["count"] == 0


def test_foreign_user_patch_is_404_not_403(client):
    a, b = _auth("alice"), _auth("bob")
    pid = client.post("/api/user-projects", json={"name": "A"}, headers=a).json()["id"]
    # Bob darf nicht mal die Existenz erfahren -> 404, nicht 403
    assert client.patch(f"/api/user-projects/{pid}", json={"name": "X"},
                        headers=b).status_code == 404
    assert client.delete(f"/api/user-projects/{pid}", headers=b).status_code == 404


def test_foreign_tenant_isolation(client):
    a = _auth("alice", tenant_id="t1")
    b = _auth("alice", tenant_id="t2")  # gleicher user_id, anderer Mandant
    client.post("/api/user-projects", json={"name": "T1"}, headers=a)
    assert client.get("/api/user-projects", headers=b).json()["count"] == 0


# ── Chats ────────────────────────────────────────────────────────────────────

def test_put_chat_computes_message_count(client):
    h = _auth("alice")
    r = client.put("/api/user-chats/chat1",
                   json={"messages": [{"role": "user", "content": "hi"},
                                      {"role": "assistant", "content": "hallo"}]},
                   headers=h)
    assert r.status_code == 200
    assert r.json()["message_count"] == 2
    assert r.json()["created"] is True
    assert r.json()["version"] == 1


def test_get_chat_by_id_and_foreign_404(client):
    a, b = _auth("alice"), _auth("bob")
    client.put("/api/user-chats/c9", json={"messages": []}, headers=a)
    assert client.get("/api/user-chats/c9", headers=a).status_code == 200
    assert client.get("/api/user-chats/c9", headers=b).status_code == 404


def test_list_chats_filtered_by_project(client):
    h = _auth("alice")
    client.put("/api/user-chats/c1", json={"messages": [], "project_id": "p1"}, headers=h)
    client.put("/api/user-chats/c2", json={"messages": [], "project_id": "p2"}, headers=h)
    r = client.get("/api/user-chats", params={"project_id": "p1"}, headers=h)
    assert r.json()["count"] == 1
    assert r.json()["chats"][0]["id"] == "c1"


def test_chat_version_conflict_409(client):
    h = _auth("alice")
    client.put("/api/user-chats/c1", json={"messages": []}, headers=h)
    r = client.put("/api/user-chats/c1",
                   json={"messages": [], "expected_version": 99}, headers=h)
    assert r.status_code == 409


def test_delete_chat(client):
    h = _auth("alice")
    client.put("/api/user-chats/c1", json={"messages": []}, headers=h)
    assert client.delete("/api/user-chats/c1", headers=h).status_code == 200
    assert client.delete("/api/user-chats/c1", headers=h).status_code == 404
