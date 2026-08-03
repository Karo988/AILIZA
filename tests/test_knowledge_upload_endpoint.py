"""
Tests fuer den HTTP-Endpunkt POST /knowledge/upload.

Vertrag (siehe Aufgabenstellung / main.py):
- Kein Login: nur scannen, NICHTS wird gespeichert (stored=false).
- Login + keep_documents True (Standard): ingest_document_source() wird
  aufgerufen, stored=true.
- Login + Chat mit keep_documents=False: nur scannen, stored=false.
- Zu grosse Datei / nicht unterstuetzter Dateityp: 422 mit deutscher Meldung,
  nichts gespeichert.
- Duplikat: zweiter Upload derselben Datei -> duplicate=true, keine neuen
  Chunks.
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


@pytest.fixture(autouse=True)
def upload_dir(tmp_path, monkeypatch):
    # Verhindert, dass die Ingestion echte Dateien ausserhalb des Testverzeichnisses ablegt.
    monkeypatch.setenv("AILIZA_KNOWLEDGE_UPLOAD_DIR", str(tmp_path / "uploads"))
    yield tmp_path / "uploads"


@pytest.fixture
def client():
    from fastapi.testclient import TestClient
    from apps.backend.main import app

    return TestClient(app, cookies={})


def _make_user_and_token(user_id: str = "alice", tenant_id: str = "default",
                          role: str = "user") -> str:
    from apps.backend.database import create_user
    from apps.backend.auth.jwt_handler import create_token

    create_user(user_id=user_id, tenant_id=tenant_id, role=role, hashed_password="hash")
    return create_token(user_id, tenant_id, role)


def _auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ── 1. Ohne Login: nur scannen, nichts speichern ─────────────────────────────

def test_upload_without_login_only_scans_nothing_stored(client):
    response = client.post(
        "/knowledge/upload",
        files={"file": ("notiz.txt", b"Ein einfacher Testinhalt ohne Auffaelligkeiten.", "text/plain")},
    )

    assert response.status_code == 200
    body = response.json()

    assert body["stored"] is False
    assert any(w in body["message"].lower() for w in ("login", "anmeld", "einloggen"))
    assert "status" in body
    assert "allowed" in body
    assert "file_type" in body


# ── 2. Mit Login, TXT-Datei -> gespeichert ───────────────────────────────────

def test_upload_with_login_txt_is_stored(client):
    token = _make_user_and_token()

    response = client.post(
        "/knowledge/upload",
        headers=_auth_headers(token),
        files={"file": ("wissen.txt", b"Dies ist ein Wissensdokument mit relevantem Inhalt fuer den Test.", "text/plain")},
    )

    assert response.status_code == 200
    body = response.json()

    assert body["stored"] is True
    assert body["status"] == "approved"
    assert body["chunks_created"] > 0
    assert body["duplicate"] is False
    assert "source_id" in body


# ── 3. Mit Login, zu grosse Datei -> 422 ─────────────────────────────────────

def test_upload_with_login_too_large_file_returns_422(client, monkeypatch):
    import apps.backend.knowledge.ingestion as ingestion_mod

    # Reduziert die Groessengrenze, damit der Test nicht wirklich MB-grosse Dateien senden muss.
    monkeypatch.setattr(ingestion_mod, "MAX_KNOWLEDGE_FILE_BYTES", 10)

    token = _make_user_and_token()

    response = client.post(
        "/knowledge/upload",
        headers=_auth_headers(token),
        files={"file": ("gross.txt", b"Dieser Inhalt ist definitiv laenger als zehn Bytes.", "text/plain")},
    )

    assert response.status_code == 422
    body = response.json()
    detail = str(body.get("detail", body))
    assert "gross" in detail.lower() or "groesse" in detail.lower() or "mb" in detail.lower()
    # Kein Stack-Trace im Response.
    assert "Traceback" not in detail


# ── 4. Mit Login, nicht unterstuetzter Dateityp -> 422 ───────────────────────

def test_upload_with_login_unsupported_extension_returns_422(client):
    token = _make_user_and_token()

    response = client.post(
        "/knowledge/upload",
        headers=_auth_headers(token),
        files={"file": ("programm.exe", b"not-an-executable", "application/octet-stream")},
    )

    assert response.status_code == 422
    body = response.json()
    detail = str(body.get("detail", body))
    assert "Traceback" not in detail


# ── 5. Duplikat-Upload ────────────────────────────────────────────────────────

def test_duplicate_upload_second_time_marks_duplicate(client):
    token = _make_user_and_token()
    content = b"Immer derselbe Inhalt fuer den Duplikat-Test der Wissensdatenbank."

    first = client.post(
        "/knowledge/upload",
        headers=_auth_headers(token),
        files={"file": ("original.txt", content, "text/plain")},
    )
    assert first.status_code == 200
    first_body = first.json()
    assert first_body["stored"] is True
    assert first_body["duplicate"] is False
    assert first_body["chunks_created"] > 0

    second = client.post(
        "/knowledge/upload",
        headers=_auth_headers(token),
        files={"file": ("kopie.txt", content, "text/plain")},
    )
    assert second.status_code == 200
    second_body = second.json()
    assert second_body["stored"] is True
    assert second_body["duplicate"] is True
    assert second_body["chunks_created"] == 0
    assert second_body["source_id"] == first_body["source_id"]


# ── 6. Mit Login, chat_id mit keep_documents=False -> nicht gespeichert ──────

def test_upload_with_login_and_keep_documents_false_not_stored(client):
    from apps.backend.database import save_user_chat, set_chat_document_retention

    token = _make_user_and_token()
    chat_id = "chat-no-keep"
    save_user_chat(chat_id, "default", "alice", messages=[])
    set_chat_document_retention(
        chat_id=chat_id, tenant_id="default", user_id="alice",
        keep_documents=False, retention_days=14,
    )

    response = client.post(
        "/knowledge/upload",
        headers=_auth_headers(token),
        data={"chat_id": chat_id},
        files={"file": ("nicht_behalten.txt", b"Dieser Inhalt soll laut Chat-Einstellung nicht behalten werden.", "text/plain")},
    )

    assert response.status_code == 200
    body = response.json()

    assert body["stored"] is False
    assert "status" in body
    assert "allowed" in body
    assert "file_type" in body


# ── 7. Meta: keine echte/produktive DB wird beruehrt ─────────────────────────

def test_uses_in_memory_sqlite_not_production_db():
    assert os.environ.get("AILIZA_DATABASE_URL") == "sqlite:///:memory:"

    from apps.backend.database import engine

    assert str(engine.url).startswith("sqlite://")
    assert "memory" in str(engine.url) or str(engine.url).endswith(":memory:")
