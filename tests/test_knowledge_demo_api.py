"""Block D0: API-Endpunkte fuer die Demo-/Nachschlagewerk-Ansicht.

/api/knowledge/upload, /api/knowledge/sources, /api/knowledge/sources/{id}.
Nutzt ausschliesslich bestehende ingestion/search-Funktionen (Block C2/C3),
keine parallele Logik. Nie storage_path/chunk_text im Response.
"""
from __future__ import annotations

import os

os.environ.setdefault("AILIZA_SECRET_KEY", "test-secret-key-minimum-32-chars-ok")
os.environ.setdefault("AILIZA_DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("AILIZA_EXTERNAL_LLM_ENABLED", "false")

import pytest


@pytest.fixture(autouse=True)
def fresh_db(tmp_path, monkeypatch):
    from apps.backend.database import init_db, metadata_obj, engine
    monkeypatch.setenv("AILIZA_KNOWLEDGE_UPLOAD_DIR", str(tmp_path / "uploads"))
    metadata_obj.drop_all(engine)
    init_db()
    yield


@pytest.fixture()
def client():
    from fastapi.testclient import TestClient
    from apps.backend.main import app
    return TestClient(app, raise_server_exceptions=True)


def _auth(user_id: str = "alice", tenant_id: str = "default"):
    from apps.backend.auth import create_token
    from apps.backend.database import create_user
    try:
        create_user(user_id=user_id, tenant_id=tenant_id, role="user", hashed_password="hash")
    except Exception:
        pass
    token = create_token(user_id=user_id, tenant_id=tenant_id, role="user")
    return {"Authorization": f"Bearer {token}"}


# -- Testgruppe 1: Upload-Regeln ---------------------------------------------

def test_upload_txt_accepted(client):
    h = _auth()
    r = client.post(
        "/api/knowledge/upload", headers=h,
        files={"file": ("notiz.txt", b"Ein normaler Text.", "text/plain")},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "approved"
    assert body["source"]["usable_in_chat"] is True
    assert body["source"]["usability_label"] == "Nutzbar im Chat"


def test_upload_markdown_accepted(client):
    h = _auth()
    r = client.post(
        "/api/knowledge/upload", headers=h,
        files={"file": ("notiz.md", b"# Titel\n\nInhalt.", "text/markdown")},
    )
    assert r.status_code == 200
    assert r.json()["source"]["source_type"] == "md"


def test_upload_pdf_rejected(client):
    h = _auth()
    r = client.post(
        "/api/knowledge/upload", headers=h,
        files={"file": ("dokument.pdf", b"%PDF-1.4", "application/pdf")},
    )
    assert r.status_code == 422
    assert "detail" in r.json()


def test_upload_requires_login(client):
    r = client.post(
        "/api/knowledge/upload",
        files={"file": ("notiz.txt", b"Text.", "text/plain")},
    )
    assert r.status_code in (401, 403)


def test_upload_with_valid_category(client):
    h = _auth()
    r = client.post(
        "/api/knowledge/upload", headers=h,
        data={"category": "Richtlinie"},
        files={"file": ("notiz.txt", b"Ein Richtlinientext.", "text/plain")},
    )
    assert r.status_code == 200
    assert r.json()["source"]["category"] == "Richtlinie"


def test_upload_with_invalid_category_rejected(client):
    h = _auth()
    r = client.post(
        "/api/knowledge/upload", headers=h,
        data={"category": "NichtErlaubt"},
        files={"file": ("notiz.txt", b"Text.", "text/plain")},
    )
    assert r.status_code == 422


# -- Testgruppe 2: Upload-/Statusanzeige --------------------------------------

def test_upload_response_never_contains_storage_path_or_chunk_text(client):
    h = _auth()
    r = client.post(
        "/api/knowledge/upload", headers=h,
        files={"file": ("notiz.txt", b"Ein normaler Text.", "text/plain")},
    )
    body_text = r.text
    assert "storage_path" not in body_text
    assert "chunk_text" not in body_text


def test_pending_review_source_visible_with_correct_label(client):
    h = _auth()
    r = client.post(
        "/api/knowledge/upload", headers=h,
        files={"file": ("gesundheit.txt", b"Diagnose: Depression seit 2024.", "text/plain")},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["status"] in ("pending_review", "blocked")
    assert body["source"]["usable_in_chat"] is False


def test_blocked_source_visible_with_correct_label(client):
    h = _auth()
    r = client.post(
        "/api/knowledge/upload", headers=h,
        files={"file": ("secret.txt", b"Mein API-Key: sk-abcdefghijklmnopqrstuvwxyz123456", "text/plain")},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "blocked"
    assert body["source"]["usability_label"] == "Blockiert"
    assert body["source"]["usable_in_chat"] is False


# -- Testgruppe 3: Listenansicht ----------------------------------------------

def test_list_sources_returns_all_statuses_with_labels(client):
    h = _auth()
    client.post("/api/knowledge/upload", headers=h,
                files={"file": ("a.txt", b"Normaler Inhalt A.", "text/plain")})
    client.post("/api/knowledge/upload", headers=h,
                files={"file": ("b.txt", b"Mein API-Key: sk-abcdefghijklmnopqrstuvwxyz123456", "text/plain")})

    r = client.get("/api/knowledge/sources", headers=h)
    assert r.status_code == 200
    body = r.json()
    assert body["count"] == 2
    labels = {s["usability_label"] for s in body["sources"]}
    assert "Nutzbar im Chat" in labels
    assert "Blockiert" in labels
    assert "categories" in body


def test_list_sources_never_contains_storage_path_or_chunk_text(client):
    h = _auth()
    client.post("/api/knowledge/upload", headers=h,
                files={"file": ("a.txt", b"Normaler Inhalt.", "text/plain")})
    r = client.get("/api/knowledge/sources", headers=h)
    assert "storage_path" not in r.text
    assert "chunk_text" not in r.text


def test_list_sources_sorted_approved_first(client):
    h = _auth()
    client.post("/api/knowledge/upload", headers=h,
                files={"file": ("blocked.txt", b"Passwort: Sommer2026!", "text/plain")})
    client.post("/api/knowledge/upload", headers=h,
                files={"file": ("ok.txt", b"Normaler Inhalt B.", "text/plain")})

    r = client.get("/api/knowledge/sources", headers=h)
    sources = r.json()["sources"]
    assert sources[0]["status"] == "approved"


def test_list_sources_requires_login(client):
    r = client.get("/api/knowledge/sources")
    assert r.status_code in (401, 403)


def test_list_sources_tenant_isolation(client):
    h_a = _auth("alice", "tenant-a")
    h_b = _auth("bob", "tenant-b")
    client.post("/api/knowledge/upload", headers=h_a,
                files={"file": ("a.txt", b"Inhalt fuer Tenant A.", "text/plain")})

    r_b = client.get("/api/knowledge/sources", headers=h_b)
    assert r_b.json()["count"] == 0
    r_a = client.get("/api/knowledge/sources", headers=h_a)
    assert r_a.json()["count"] == 1


# -- Testgruppe 4: Detailansicht ----------------------------------------------

def test_source_detail_returns_public_view(client):
    h = _auth()
    upload = client.post("/api/knowledge/upload", headers=h,
                         files={"file": ("a.txt", b"Normaler Inhalt.", "text/plain")}).json()
    source_id = upload["source"]["source_id"]

    r = client.get(f"/api/knowledge/sources/{source_id}", headers=h)
    assert r.status_code == 200
    body = r.json()
    assert body["source_id"] == source_id
    assert "storage_path" not in r.text
    assert "chunk_text" not in r.text


def test_source_detail_not_found_for_other_tenant(client):
    h_a = _auth("alice", "tenant-a")
    h_b = _auth("bob", "tenant-b")
    upload = client.post("/api/knowledge/upload", headers=h_a,
                         files={"file": ("a.txt", b"Inhalt.", "text/plain")}).json()
    source_id = upload["source"]["source_id"]

    r = client.get(f"/api/knowledge/sources/{source_id}", headers=h_b)
    assert r.status_code == 404


def test_source_detail_unknown_id_404(client):
    h = _auth()
    r = client.get("/api/knowledge/sources/999999", headers=h)
    assert r.status_code == 404


# -- Testgruppe 5: Chat mit Quelle (bestehende C4-Anbindung, hier nur end-to-end) --

def test_chat_shows_sources_for_uploaded_approved_document(client, monkeypatch):
    import apps.backend.main as main_module

    h = _auth()
    client.post("/api/knowledge/upload", headers=h,
                files={"file": ("regel.txt", b"Die Urlaubsregelung erlaubt 30 Tage pro Jahr.", "text/plain")})

    def fake_ask_llm_directly(task, history=None):
        return "Laut [Quelle 1] sind es 30 Tage.", None, {}

    monkeypatch.setattr(main_module, "_ask_llm_directly", fake_ask_llm_directly)

    r = client.post(
        "/agent/run", json={"task": "Bitte schreibe: Wie ist die Urlaubsregelung?"}, headers=h,
    )
    assert r.status_code == 200
    body = r.json()
    assert body.get("sources")
    assert body["sources"][0]["title"] == "regel.txt"
    assert "source_id" in body["sources"][0]
    assert "chunk_id" in body["sources"][0]


def test_chat_without_hit_answers_normally(client, monkeypatch):
    import apps.backend.main as main_module
    h = _auth()

    def fake_ask_llm_directly(task, history=None):
        return "Das Wetter ist heute sonnig.", None, {}

    monkeypatch.setattr(main_module, "_ask_llm_directly", fake_ask_llm_directly)

    r = client.post("/agent/run", json={"task": "Bitte schreibe: Wie ist das Wetter?"}, headers=h)
    assert r.status_code == 200
    body = r.json()
    assert "Ich habe in freigegebenen Quellen nichts Passendes gefunden." not in body["ai_response"]
    assert "sources" not in body


def test_chat_explicit_document_question_without_hit_shows_hint(client, monkeypatch):
    import apps.backend.main as main_module
    h = _auth()

    def fake_ask_llm_directly(task, history=None):
        return "Dazu kann ich allgemein antworten.", None, {}

    monkeypatch.setattr(main_module, "_ask_llm_directly", fake_ask_llm_directly)

    r = client.post(
        "/agent/run",
        json={"task": "Bitte schreibe: Was steht dazu in unseren Dokumenten oder Quellen?"},
        headers=h,
    )
    assert r.status_code == 200
    body = r.json()
    assert "Ich habe in freigegebenen Quellen nichts Passendes gefunden." in body["ai_response"]


# -- Testgruppe 6: bestehende Tests bleiben gruen (Rauchtest) ----------------

def test_existing_agent_run_flow_still_works(client, monkeypatch):
    import apps.backend.main as main_module
    h = _auth()

    def fake_ask_llm_directly(task, history=None):
        return "Normale Antwort.", None, {}

    monkeypatch.setattr(main_module, "_ask_llm_directly", fake_ask_llm_directly)
    r = client.post("/agent/run", json={"task": "Bitte schreibe: Test."}, headers=h)
    assert r.status_code == 200
