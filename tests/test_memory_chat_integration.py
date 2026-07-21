"""Block B Schritt 1: Chat-Anbindung der Speicher-Entscheidungslogik.

Scope (siehe docs/BLOCK_B_MASTER_AUFTRAG.md):
decide_memory_storage() wird im echten /agent/run-Flow aufgerufen. Nur
memory_suggestion, nie direkter memory_item. Sensible Inhalte nie
Suggestion. speichermodus respektiert. Best effort: Fehler in der
Memory-Logik duerfen die normale Agentenantwort nie blockieren.
Kein LLM-Call zur info_kind-Klassifikation -- classify() aus
data_governance.py + feste Regeln fuer Einstellungen.
"""
from __future__ import annotations

import os

os.environ.setdefault("AILIZA_SECRET_KEY", "test-secret-key-minimum-32-chars-ok")
os.environ.setdefault("AILIZA_DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("AILIZA_EXTERNAL_LLM_ENABLED", "false")

import pytest

from apps.backend.main import classify_info_kind_for_memory, _maybe_suggest_memory


@pytest.fixture(autouse=True)
def fresh_db():
    from apps.backend.database import init_db, metadata_obj, engine
    metadata_obj.drop_all(engine)
    init_db()
    yield


# ── info_kind-Klassifikation (regelbasiert, kein LLM) ────────────────────────

def test_credentials_classified_as_sensitive():
    assert classify_info_kind_for_memory("Mein API Key ist sk-abcdefghijklmnop123456") == "sensitive"


def test_setting_phrase_classified_as_setting():
    assert classify_info_kind_for_memory("Bitte antworte mir immer kurz.") == "setting"
    assert classify_info_kind_for_memory("Antworte bitte künftig förmlich.") == "setting"


def test_plain_statement_classified_as_user_knowledge():
    assert classify_info_kind_for_memory("Unser Projekt X hat als Ziel Y.") == "user_knowledge"


def test_health_data_classified_as_sensitive():
    assert classify_info_kind_for_memory("Meine Diagnose lautet Depression.") == "sensitive"


# ── _maybe_suggest_memory: Integration mit decide_memory_storage ────────────

class _FakeToken:
    def __init__(self, user_id="alice", tenant_id="default"):
        self.user_id = user_id
        self.tenant_id = tenant_id


def _make_user_with_settings(user_id="alice", speichermodus="immer_fragen"):
    from apps.backend.database import create_user, upsert_user_settings
    create_user(user_id=user_id, tenant_id="default", role="user", hashed_password="hash")
    upsert_user_settings(user_id, "default", speichermodus=speichermodus)


def test_completed_result_with_reusable_knowledge_creates_suggestion():
    from apps.backend.database import list_memory_suggestions_for_user

    _make_user_with_settings("alice")
    token = _FakeToken("alice")
    result = {"status": "completed", "ai_response": "Notiert."}
    _maybe_suggest_memory(task="Unser Projekt X hat als Ziel Y.", result=result, token=token, tenant_id="default")
    suggestions = list_memory_suggestions_for_user("alice", "default")
    assert len(suggestions) == 1
    assert suggestions[0]["suggested_scope"] == "user_memory"


def test_sensitive_content_never_creates_suggestion():
    from apps.backend.database import list_memory_suggestions_for_user

    _make_user_with_settings("alice")
    token = _FakeToken("alice")
    result = {"status": "completed", "ai_response": "..."}
    _maybe_suggest_memory(task="Mein API Key ist sk-abcdefghijklmnop123456", result=result, token=token, tenant_id="default")
    assert list_memory_suggestions_for_user("alice", "default") == []


def test_setting_phrase_never_creates_memory_suggestion():
    from apps.backend.database import list_memory_suggestions_for_user

    _make_user_with_settings("alice")
    token = _FakeToken("alice")
    result = {"status": "completed", "ai_response": "..."}
    _maybe_suggest_memory(task="Bitte antworte mir immer kurz.", result=result, token=token, tenant_id="default")
    assert list_memory_suggestions_for_user("alice", "default") == []


def test_nie_automatisch_creates_no_suggestion():
    from apps.backend.database import list_memory_suggestions_for_user

    _make_user_with_settings("alice", speichermodus="nie_automatisch")
    token = _FakeToken("alice")
    result = {"status": "completed", "ai_response": "..."}
    _maybe_suggest_memory(task="Unser Projekt X hat als Ziel Y.", result=result, token=token, tenant_id="default")
    assert list_memory_suggestions_for_user("alice", "default") == []


def test_no_token_creates_no_suggestion():
    from apps.backend.database import list_memory_suggestions_for_user

    result = {"status": "completed", "ai_response": "..."}
    _maybe_suggest_memory(task="Unser Projekt X hat als Ziel Y.", result=result, token=None, tenant_id="default")
    # Kein User-Kontext -> keine Zuordnung moeglich, keine Suggestion.


def test_non_completed_status_creates_no_suggestion():
    from apps.backend.database import list_memory_suggestions_for_user

    _make_user_with_settings("alice")
    token = _FakeToken("alice")
    for status in ("blocked", "login_required", "consent_required", "failed"):
        result = {"status": status, "ai_response": "..."}
        _maybe_suggest_memory(task="Unser Projekt X hat als Ziel Y.", result=result, token=token, tenant_id="default")
    assert list_memory_suggestions_for_user("alice", "default") == []


def test_memory_logic_error_never_raises(monkeypatch):
    """Best effort: ein Fehler in der Memory-Logik darf niemals nach oben
    durchschlagen -- die eigentliche Agentenantwort bleibt unberuehrt."""
    import apps.backend.main as main_module

    _make_user_with_settings("alice")
    token = _FakeToken("alice")

    def _boom(*a, **kw):
        raise RuntimeError("Simulierter Fehler in der Memory-Logik")

    monkeypatch.setattr(main_module, "decide_memory_storage", _boom)
    result = {"status": "completed", "ai_response": "Antwort bleibt unveraendert."}
    # Darf NICHT raisen:
    _maybe_suggest_memory(task="Unser Projekt X hat als Ziel Y.", result=result, token=token, tenant_id="default")
    assert result["ai_response"] == "Antwort bleibt unveraendert."


# ── End-to-End: /agent/run erzeugt Suggestion, blockiert Antwort nie ────────

@pytest.fixture()
def client():
    from fastapi.testclient import TestClient
    from apps.backend.main import app
    return TestClient(app, raise_server_exceptions=True)


def _auth(user_id: str):
    from apps.backend.auth import create_token
    token = create_token(user_id=user_id, tenant_id="default", role="user")
    return {"Authorization": f"Bearer {token}"}


def test_agent_run_creates_suggestion_without_blocking_answer(client, monkeypatch):
    import apps.backend.main as main_module
    from apps.backend.database import list_memory_suggestions_for_user

    _make_user_with_settings("alice")
    h = _auth("alice")

    def fake_ask_llm_directly(task, history=None):
        return "Verstanden, notiert.", None, {}

    monkeypatch.setattr(main_module, "_ask_llm_directly", fake_ask_llm_directly)

    response = client.post("/agent/run", json={"task": "Bitte schreibe: Unser Projekt X hat als Ziel Y."}, headers=h)
    assert response.status_code == 200
    body = response.json()
    assert body["status"] in ("completed", "draft")
    assert body["ai_response"]  # Antwort kommt normal durch, unabhaengig vom Memory-Vorschlag


# ── API: Vorschlaege bestaetigen/ablehnen ───────────────────────────────────

def test_memory_suggestions_require_auth(client):
    assert client.get("/api/memory-suggestions").status_code == 401
    assert client.post("/api/memory-suggestions/1/confirm").status_code == 401
    assert client.post("/api/memory-suggestions/1/reject").status_code == 401


def test_list_confirm_reject_own_suggestion(client):
    from apps.backend.database import create_memory_suggestion, get_memory_item

    _make_user_with_settings("alice")
    h = _auth("alice")
    s = create_memory_suggestion(
        user_id="alice", tenant_id="default", suggested_scope="user_memory",
        suggested_title="Test", suggested_content="Inhalt",
        suggested_purpose="Zweck", source_type="user_confirmation",
    )
    r = client.get("/api/memory-suggestions", headers=h)
    assert r.status_code == 200
    assert r.json()["count"] == 1

    r2 = client.post(f"/api/memory-suggestions/{s['id']}/confirm", headers=h)
    assert r2.status_code == 200
    item = get_memory_item(r2.json()["memory_item_id"])
    assert item["status"] == "active"


def test_foreign_user_cannot_confirm_or_reject(client):
    from apps.backend.database import create_memory_suggestion

    _make_user_with_settings("alice")
    _make_user_with_settings("bob")
    h_bob = _auth("bob")
    s = create_memory_suggestion(
        user_id="alice", tenant_id="default", suggested_scope="user_memory",
        suggested_title="Test", suggested_content="Inhalt",
        suggested_purpose="Zweck", source_type="user_confirmation",
    )
    assert client.post(f"/api/memory-suggestions/{s['id']}/confirm", headers=h_bob).status_code == 404
    assert client.post(f"/api/memory-suggestions/{s['id']}/reject", headers=h_bob).status_code == 404


def test_reject_own_suggestion(client):
    from apps.backend.database import create_memory_suggestion

    _make_user_with_settings("alice")
    h = _auth("alice")
    s = create_memory_suggestion(
        user_id="alice", tenant_id="default", suggested_scope="user_memory",
        suggested_title="Test", suggested_content="Inhalt",
        suggested_purpose="Zweck", source_type="user_confirmation",
    )
    r = client.post(f"/api/memory-suggestions/{s['id']}/reject", headers=h)
    assert r.status_code == 200
    assert r.json()["status"] == "rejected"
