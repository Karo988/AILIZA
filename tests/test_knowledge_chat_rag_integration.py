"""Block C Phase C4: Chat-Integration der internen Wissensquellen.

Testet die Verdrahtung in apps/backend/main.py: _maybe_build_knowledge_context(),
_attach_knowledge_result() und die Kontext-Injektion in _run_agent_core()
ueber effective_task. Kein echter externer LLM-Call -- _ask_llm_directly
wird gefaked (gleiches Muster wie tests/test_memory_chat_integration.py).
"""
from __future__ import annotations

import os

os.environ.setdefault("AILIZA_SECRET_KEY", "test-secret-key-minimum-32-chars-ok")
os.environ.setdefault("AILIZA_DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("AILIZA_EXTERNAL_LLM_ENABLED", "false")

import pytest

from apps.backend.main import _maybe_build_knowledge_context, _attach_knowledge_result
from apps.backend.knowledge.search import NOT_FOUND_MESSAGE


@pytest.fixture(autouse=True)
def fresh_db():
    from apps.backend.database import init_db, metadata_obj, engine
    metadata_obj.drop_all(engine)
    init_db()
    yield


class _FakeToken:
    def __init__(self, user_id="alice", tenant_id="default"):
        self.user_id = user_id
        self.tenant_id = tenant_id


def _seed_findable_source(chunk_text="Die Urlaubsregelung erlaubt 30 Tage pro Jahr."):
    from apps.backend.database import (
        create_user, create_knowledge_source, create_knowledge_chunk,
        set_knowledge_source_permission,
    )
    create_user(user_id="alice", tenant_id="default", role="user", hashed_password="hash")
    source = create_knowledge_source(
        tenant_id="default", uploaded_by="alice", source_type="txt",
        title="Personalhandbuch", status="approved",
    )
    create_knowledge_chunk(
        source_id=source["id"], tenant_id="default", chunk_index=0, chunk_text=chunk_text,
    )
    set_knowledge_source_permission(
        source_id=source["id"], tenant_id="default", visibility_scope="organization",
        created_by="alice",
    )
    return source


# -- Testgruppe 1: _maybe_build_knowledge_context ----------------------------

def test_maybe_build_knowledge_context_no_token_returns_neutral():
    knowledge = _maybe_build_knowledge_context(task="Urlaubsregelung?", token=None, tenant_id="default")
    assert knowledge["context_block"] is None
    assert knowledge["answer_mode"] == "general_ai"


def test_maybe_build_knowledge_context_finds_hit_with_token():
    _seed_findable_source()
    token = _FakeToken("alice")
    knowledge = _maybe_build_knowledge_context(task="Wie ist die Urlaubsregelung?", token=token, tenant_id="default")
    assert knowledge["context_block"] is not None
    assert knowledge["answer_mode"] == "internal_knowledge"


def test_maybe_build_knowledge_context_never_raises(monkeypatch):
    import apps.backend.main as main_module

    def _boom(**kwargs):
        raise RuntimeError("Simulierter Fehler")

    monkeypatch.setattr(main_module, "build_knowledge_context", _boom)
    token = _FakeToken("alice")
    knowledge = _maybe_build_knowledge_context(task="Test", token=token, tenant_id="default")
    assert knowledge["context_block"] is None  # Fallback greift, kein Raise


# -- Testgruppe 2: _attach_knowledge_result ----------------------------------

def test_attach_knowledge_result_adds_sources_and_sanitizes_citations():
    _seed_findable_source()
    token = _FakeToken("alice")
    knowledge = _maybe_build_knowledge_context(task="Wie ist die Urlaubsregelung", token=token, tenant_id="default")
    tag = next(iter(knowledge["tag_map"]))
    result = {
        "status": "completed",
        "message": f"Laut {tag} sind es 30 Tage. Siehe auch [Quelle 99].",
        "ai_response": f"Laut {tag} sind es 30 Tage. Siehe auch [Quelle 99].",
    }
    _attach_knowledge_result(result=result, knowledge=knowledge, tenant_id="default")

    assert result["answer_mode"] == "internal_knowledge"
    assert "sources" in result
    assert len(result["sources"]) == 1
    assert tag in result["message"]
    assert "[Quelle 99]" not in result["message"]
    assert "[Quelle 99]" not in result["ai_response"]


def test_attach_knowledge_result_no_sources_when_nothing_used():
    token = _FakeToken("alice")
    knowledge = _maybe_build_knowledge_context(task="Voellig unbekannt", token=token, tenant_id="default")
    result = {"status": "completed", "message": "Normale Antwort.", "ai_response": "Normale Antwort."}
    _attach_knowledge_result(result=result, knowledge=knowledge, tenant_id="default")

    assert "sources" not in result
    assert result["message"] == "Normale Antwort."
    assert result["answer_mode"] == "general_ai"


def test_attach_knowledge_result_explicit_question_appends_hint():
    token = _FakeToken("alice")
    knowledge = _maybe_build_knowledge_context(
        task="Hast du dazu ein internes Dokument oder eine Quelle?",
        token=token, tenant_id="default",
    )
    result = {"status": "completed", "message": "Ich kann dazu allgemein antworten.", "ai_response": "Ich kann dazu allgemein antworten."}
    _attach_knowledge_result(result=result, knowledge=knowledge, tenant_id="default")

    assert NOT_FOUND_MESSAGE in result["message"]
    assert result["answer_mode"] == "no_internal_source"


def test_attach_knowledge_result_never_raises(monkeypatch):
    import apps.backend.main as main_module

    def _boom(*a, **kw):
        raise RuntimeError("Simulierter Fehler in build_sources_list")

    monkeypatch.setattr(main_module, "build_sources_list", _boom)
    knowledge = {
        "answer_mode": "internal_knowledge", "confidence": "high",
        "status_message": None, "tag_map": {"[Quelle 1]": {}},
        "found_count": 1, "filtered_count": 0,
    }
    result = {"status": "completed", "message": "Antwort bleibt unveraendert.", "ai_response": "Antwort bleibt unveraendert."}
    _attach_knowledge_result(result=result, knowledge=knowledge, tenant_id="default")
    assert result["message"] == "Antwort bleibt unveraendert."


# -- Testgruppe 3: Ende-zu-Ende ueber /agent/run -----------------------------

@pytest.fixture()
def client():
    from fastapi.testclient import TestClient
    from apps.backend.main import app
    return TestClient(app, raise_server_exceptions=True)


def _auth(user_id: str):
    from apps.backend.auth import create_token
    token = create_token(user_id=user_id, tenant_id="default", role="user")
    return {"Authorization": f"Bearer {token}"}


def test_agent_run_includes_knowledge_context_in_llm_task(client, monkeypatch):
    import apps.backend.main as main_module

    _seed_findable_source()
    h = _auth("alice")
    captured: dict[str, str] = {}

    def fake_ask_llm_directly(task, history=None):
        captured["task"] = task
        return f"Laut [Quelle 1] sind es 30 Tage.", None, {}

    monkeypatch.setattr(main_module, "_ask_llm_directly", fake_ask_llm_directly)

    response = client.post(
        "/agent/run",
        json={"task": "Bitte schreibe: Wie ist die Urlaubsregelung?"},
        headers=h,
    )
    assert response.status_code == 200
    body = response.json()
    assert "Urlaubsregelung" in captured["task"]
    assert "[Interne freigegebene Wissensquellen]" in captured["task"]
    assert body["ai_response"]
    assert body.get("sources")
    assert body["sources"][0]["title"] == "Personalhandbuch"


def test_agent_run_normal_chat_without_hits_has_no_hint(client, monkeypatch):
    import apps.backend.main as main_module
    from apps.backend.database import create_user

    create_user(user_id="alice", tenant_id="default", role="user", hashed_password="hash")
    h = _auth("alice")

    def fake_ask_llm_directly(task, history=None):
        return "Das Wetter ist heute sonnig.", None, {}

    monkeypatch.setattr(main_module, "_ask_llm_directly", fake_ask_llm_directly)

    response = client.post(
        "/agent/run", json={"task": "Bitte schreibe: Wie ist das Wetter?"}, headers=h,
    )
    assert response.status_code == 200
    body = response.json()
    assert NOT_FOUND_MESSAGE not in body["ai_response"]
    assert "sources" not in body
    assert body["answer_mode"] == "general_ai"


def test_agent_run_search_failure_does_not_break_chat(client, monkeypatch):
    import apps.backend.main as main_module
    from apps.backend.database import create_user

    create_user(user_id="alice", tenant_id="default", role="user", hashed_password="hash")
    h = _auth("alice")

    def _boom(**kwargs):
        raise RuntimeError("Suche kaputt")

    monkeypatch.setattr(main_module, "build_knowledge_context", _boom)

    def fake_ask_llm_directly(task, history=None):
        return "Normale Antwort trotz kaputter Suche.", None, {}

    monkeypatch.setattr(main_module, "_ask_llm_directly", fake_ask_llm_directly)

    response = client.post(
        "/agent/run", json={"task": "Bitte schreibe: Test"}, headers=h,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["ai_response"] == "Normale Antwort trotz kaputter Suche."


def test_agent_run_without_token_skips_knowledge_context(client, monkeypatch):
    import apps.backend.main as main_module

    def fake_ask_llm_directly(task, history=None):
        return "Anonyme Antwort.", None, {}

    monkeypatch.setattr(main_module, "_ask_llm_directly", fake_ask_llm_directly)

    response = client.post("/agent/run", json={"task": "Bitte schreibe: Test ohne Login."})
    assert response.status_code == 200
    body = response.json()
    assert "sources" not in body
