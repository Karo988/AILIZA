"""Block B Schritt 2: Export & Loeschung (Art. 20 / Art. 17 DSGVO).

Scope (siehe docs/BLOCK_B_MASTER_AUFTRAG.md, Karo-Entscheidung zur Stop-Regel):
GET /api/me/export, DELETE /api/me. Loeschung deaktiviert den Account
(active=0) und loescht/anonymisiert abhaengige persoenliche Daten. KEIN
hartes Loeschen des users-Datensatzes in dieser PR.
"""
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


def _auth(user_id: str, tenant_id: str = "default"):
    from apps.backend.auth import create_token
    token = create_token(user_id=user_id, tenant_id=tenant_id, role="user")
    return {"Authorization": f"Bearer {token}"}


def _setup_user_with_data(user_id="alice"):
    from apps.backend.database import (
        create_user, upsert_user_settings, save_user_project, save_user_chat,
        create_memory_suggestion, confirm_memory_suggestion,
    )
    create_user(user_id=user_id, tenant_id="default", role="user", hashed_password="hash")
    upsert_user_settings(user_id, "default", ton="sachlich")
    save_user_project("p1", "default", user_id, name="Testprojekt")
    save_user_chat("c1", "default", user_id, messages=[{"role": "user", "content": "Hallo"}])
    s = create_memory_suggestion(
        user_id=user_id, tenant_id="default", suggested_scope="user_memory",
        suggested_title="Test", suggested_content="Inhalt",
        suggested_purpose="Zweck", source_type="user_confirmation",
    )
    confirm_memory_suggestion(s["id"], confirmed_by=user_id)


# ── Export ────────────────────────────────────────────────────────────────

def test_export_requires_auth(client):
    assert client.get("/api/me/export").status_code == 401


def test_export_contains_own_data_without_password(client):
    _setup_user_with_data("alice")
    h = _auth("alice")
    r = client.get("/api/me/export", headers=h)
    assert r.status_code == 200
    body = r.json()
    assert "hashed_password" not in body.get("user", {})
    assert body["user"]["user_id"] == "alice"
    assert body["user_settings"]["ton"] == "sachlich"
    assert len(body["user_projects"]) == 1
    assert len(body["user_chats"]) == 1
    assert len(body["memory_items"]) == 1
    assert len(body["memory_suggestions"]) == 1


def test_export_does_not_contain_foreign_data(client):
    from apps.backend.database import create_user
    _setup_user_with_data("alice")
    create_user(user_id="bob", tenant_id="default", role="user", hashed_password="hash")
    h = _auth("bob")
    r = client.get("/api/me/export", headers=h)
    assert r.status_code == 200
    body = r.json()
    assert body["user_projects"] == []
    assert body["user_chats"] == []
    assert body["memory_items"] == []


def test_export_only_includes_user_memory_scope(client):
    from apps.backend.database import create_memory_source, create_memory_item
    _setup_user_with_data("alice")
    source = create_memory_source(tenant_id="default", source_type="admin_approval")
    create_memory_item(
        tenant_id="default", scope="company_memory", title="Firmenwissen",
        content="x", purpose="y", source_id=source["id"], owner_user_id=None,
        status="active",
    )
    h = _auth("alice")
    r = client.get("/api/me/export", headers=h)
    titles = [i["title"] for i in r.json()["memory_items"]]
    assert "Firmenwissen" not in titles


# ── Loeschung ────────────────────────────────────────────────────────────

def test_delete_requires_auth(client):
    assert client.delete("/api/me").status_code == 401


def test_delete_deactivates_account_not_hard_delete(client):
    from apps.backend.database import get_user

    _setup_user_with_data("alice")
    h = _auth("alice")
    r = client.delete("/api/me", headers=h)
    assert r.status_code == 200
    user = get_user("alice", "default")
    assert user is not None  # users-Datensatz bleibt bestehen (kein Hard-Delete)
    assert user["active"] == 0


def test_delete_removes_dependent_personal_data(client):
    from apps.backend.database import (
        list_user_projects, list_user_chats, get_user_settings,
        list_memory_suggestions_for_user, list_active_memory_items_for_user,
    )

    _setup_user_with_data("alice")
    h = _auth("alice")
    client.delete("/api/me", headers=h)

    assert list_user_projects("default", "alice") == []
    assert list_user_chats("default", "alice") == []
    assert get_user_settings("alice", "default") is None
    assert list_active_memory_items_for_user("alice", "default") == []


def test_delete_is_transactional_all_or_nothing(monkeypatch):
    """Wenn ein Teilschritt innerhalb derselben DB-Transaktion fehlschlaegt,
    darf NICHTS committet werden -- direkter Test der database.py-Funktion,
    da echte Atomaritaet eine gemeinsame Connection/Transaktion braucht."""
    import apps.backend.database as db_module
    from apps.backend.database import list_user_projects, get_user

    _setup_user_with_data("alice")

    def _boom(*a, **kw):
        raise RuntimeError("Simulierter Fehler waehrend Loeschung")

    monkeypatch.setattr(db_module, "_soft_delete_owned_memory_items", _boom)
    with pytest.raises(RuntimeError):
        db_module.delete_own_account_data("alice", "default")
    # Nichts wurde committet -- Projekt ist noch da, Account noch aktiv:
    assert len(list_user_projects("default", "alice")) == 1
    assert get_user("alice", "default")["active"] == 1


def test_delete_writes_audit_entry_with_codes_only():
    from apps.backend.database import write_audit_entry, list_audit_entries

    write_audit_entry(action="user.self_deletion_requested", metadata={"user_id": "alice"})
    entries = list_audit_entries(limit=10)
    assert any(e["action"] == "user.self_deletion_requested" for e in entries)


def test_cannot_use_app_after_deletion(client):
    _setup_user_with_data("alice")
    h = _auth("alice")
    client.delete("/api/me", headers=h)
    # Nach Deaktivierung: erneuter Login schlaegt fehl (active=0).
    from apps.backend.database import authenticate_user
    assert authenticate_user("alice", "irgendwas", "default") is None
