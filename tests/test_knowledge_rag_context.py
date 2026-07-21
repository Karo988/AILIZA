"""Block C Phase C4: Interne Wissensquellen im Chat mit Quellenanzeige.

Scope (siehe Karo-Entscheidungen, docs/AGENT_HANDOFF_BLOCK_C1_ABGESCHLOSSEN.md
Abschnitt 4):
Best-effort Kontextaufbau aus freigegebenen knowledge_chunks fuer den Chat.
Kein RAG-Redesign, keine Websuche, keine UI, kein pgvector, keine Embeddings,
kein Wissensgraph. Nur search_knowledge_chunks() + bestehende Governance
(classify/check_data_target). Backend bleibt Quelle der Wahrheit fuer die
Quellenliste -- niemals aus Modelltext abgeleitet.
"""
from __future__ import annotations

import os

os.environ.setdefault("AILIZA_SECRET_KEY", "test-secret-key-minimum-32-chars-ok")
os.environ.setdefault("AILIZA_DATABASE_URL", "sqlite:///:memory:")

import pytest

from apps.backend.database import (
    metadata_obj, engine, init_db, create_user,
    create_knowledge_source, create_knowledge_chunk,
    set_knowledge_source_permission,
)
from apps.backend.knowledge.rag_context import (
    build_knowledge_context, sanitize_answer_citations, build_sources_list,
    answer_mode_user_text, MAX_CONTEXT_SNIPPETS, MAX_CONTEXT_CHARS_TOTAL,
)
from apps.backend.knowledge.search import NOT_FOUND_MESSAGE


@pytest.fixture(autouse=True)
def fresh_db():
    metadata_obj.drop_all(engine)
    init_db()
    yield


def _make_user(user_id: str = "alice", tenant_id: str = "default") -> None:
    create_user(user_id=user_id, tenant_id=tenant_id, role="user", hashed_password="hash")


def _make_source(tenant_id="default", uploaded_by="alice", status="approved", **overrides):
    defaults = dict(
        tenant_id=tenant_id, uploaded_by=uploaded_by, source_type="txt",
        title="Testquelle", status=status,
    )
    defaults.update(overrides)
    return create_knowledge_source(**defaults)


def _make_chunk(source_id, tenant_id="default", chunk_index=0, chunk_text="Standardinhalt", **kw):
    return create_knowledge_chunk(
        source_id=source_id, tenant_id=tenant_id, chunk_index=chunk_index,
        chunk_text=chunk_text, **kw,
    )


def _make_permission(source_id, tenant_id="default", visibility_scope="organization",
                     created_by="alice", **kw):
    return set_knowledge_source_permission(
        source_id=source_id, tenant_id=tenant_id, visibility_scope=visibility_scope,
        created_by=created_by, **kw,
    )


def _seed_findable_source(chunk_text="Die Urlaubsregelung erlaubt 30 Tage pro Jahr."):
    _make_user("alice")
    source = _make_source(uploaded_by="alice")
    _make_chunk(source["id"], chunk_text=chunk_text)
    _make_permission(source["id"])
    return source


# -- Testgruppe 1: Treffer werden gesucht und in Kontext uebersetzt ---------

def test_finds_hit_and_builds_context_block():
    _seed_findable_source()
    context = build_knowledge_context(
        tenant_id="default", requester_user_id="alice", query="Urlaubsregelung",
    )
    assert context["answer_mode"] == "internal_knowledge"
    assert context["confidence"] == "high"
    assert context["context_block"] is not None
    assert "[Interne freigegebene Wissensquellen]" in context["context_block"]
    assert "[Quelle 1]" in context["context_block"]
    assert "Urlaubsregelung" in context["context_block"]
    assert len(context["used_snippets"]) == 1
    assert context["status_message"] is None


def test_tag_map_contains_required_metadata():
    source = _seed_findable_source()
    context = build_knowledge_context(
        tenant_id="default", requester_user_id="alice", query="Urlaubsregelung",
    )
    tag, meta = next(iter(context["tag_map"].items()))
    assert tag == "[Quelle 1]"
    assert meta["source_id"] == source["id"]
    assert "chunk_id" in meta
    assert "title" in meta
    assert "source_type" in meta
    assert "visibility_scope" in meta


# -- Testgruppe 2: Treffer werden begrenzt -----------------------------------

def test_max_three_snippets_in_context():
    _make_user("alice")
    source = _make_source(uploaded_by="alice")
    for i in range(6):
        _make_chunk(source["id"], chunk_index=i, chunk_text=f"Suchwort Eintrag Nummer {i}.")
    _make_permission(source["id"])

    context = build_knowledge_context(
        tenant_id="default", requester_user_id="alice", query="Suchwort",
    )
    assert len(context["used_snippets"]) <= MAX_CONTEXT_SNIPPETS
    assert MAX_CONTEXT_SNIPPETS == 3


def test_total_context_chars_limited_to_800():
    _make_user("alice")
    source = _make_source(uploaded_by="alice")
    long_text = "Suchwort " + ("Lorem ipsum dolor sit amet consectetur. " * 10)
    for i in range(3):
        _make_chunk(source["id"], chunk_index=i, chunk_text=long_text)
    _make_permission(source["id"])

    context = build_knowledge_context(
        tenant_id="default", requester_user_id="alice", query="Suchwort",
    )
    total_snippet_chars = sum(len(hit["snippet"]) for hit in context["used_snippets"])
    assert total_snippet_chars <= MAX_CONTEXT_CHARS_TOTAL
    assert MAX_CONTEXT_CHARS_TOTAL == 800


# -- Testgruppe 3: Nur Snippets gehen ins LLM, nie rohe Felder ---------------

def test_context_block_never_contains_storage_path_or_raw_marker():
    _make_user("alice")
    source = _make_source(
        uploaded_by="alice",
        storage_path="/data/uploads/default/geheimer-dateiname-marker.txt",
    )
    _make_chunk(source["id"], chunk_text="Suchwort Inhalt fuer den Kontexttest.")
    _make_permission(source["id"])

    context = build_knowledge_context(
        tenant_id="default", requester_user_id="alice", query="Suchwort",
    )
    assert "geheimer-dateiname-marker" not in context["context_block"]
    assert "storage_path" not in context["context_block"]


def test_used_snippets_only_expose_documented_fields():
    _seed_findable_source()
    context = build_knowledge_context(
        tenant_id="default", requester_user_id="alice", query="Urlaubsregelung",
    )
    hit = context["used_snippets"][0]
    for field in ("source_id", "chunk_id", "title", "snippet", "source_type", "visibility_scope"):
        assert field in hit
    assert "storage_path" not in hit
    assert "chunk_text" not in hit


# -- Testgruppe 4: Governance-Reklassifikation -------------------------------

def test_secret_snippet_is_filtered_out_of_context():
    _make_user("alice")
    source = _make_source(uploaded_by="alice")
    # Chunk direkt (nicht ueber Ingestion) mit Secret-Inhalt anlegen, um die
    # Reklassifikation in rag_context selbst zu testen (nicht die von C2).
    _make_chunk(source["id"], chunk_text="Suchwort Mein API-Key: sk-abcdefghijklmnopqrstuvwxyz123456")
    _make_permission(source["id"])

    context = build_knowledge_context(
        tenant_id="default", requester_user_id="alice", query="Suchwort",
    )
    assert context["used_snippets"] == []
    assert context["context_block"] is None
    assert context["answer_mode"] == "blocked_sensitive"
    assert context["filtered_count"] == 1


def test_mixed_allowed_and_blocked_snippets_only_allowed_used():
    _make_user("alice")
    source = _make_source(uploaded_by="alice")
    _make_chunk(source["id"], chunk_index=0, chunk_text="Suchwort harmloser Inhalt ohne Geheimnisse.")
    _make_chunk(source["id"], chunk_index=1, chunk_text="Suchwort Passwort: Sommer2026!")
    _make_permission(source["id"])

    context = build_knowledge_context(
        tenant_id="default", requester_user_id="alice", query="Suchwort",
    )
    assert len(context["used_snippets"]) == 1
    assert "Passwort" not in context["context_block"]
    assert context["filtered_count"] == 1
    assert context["found_count"] == 2


# -- Testgruppe 5: Keine Treffer ----------------------------------------------

def test_no_hits_normal_chat_no_hint():
    _make_user("alice")
    context = build_knowledge_context(
        tenant_id="default", requester_user_id="alice", query="VoelligUnbekanntesWort",
    )
    assert context["context_block"] is None
    assert context["status_message"] is None
    assert context["answer_mode"] == "general_ai"


# -- Testgruppe 6: Explizite Dokumentfrage ohne Treffer ----------------------

def test_explicit_document_question_without_hits_shows_hint():
    _make_user("alice")
    context = build_knowledge_context(
        tenant_id="default", requester_user_id="alice",
        query="Hast du dazu eine interne Quelle oder ein Dokument in der Wissensdatenbank?",
    )
    assert context["status_message"] == NOT_FOUND_MESSAGE
    assert context["answer_mode"] == "no_internal_source"
    assert context["confidence"] == "low"


def test_normal_question_without_hits_has_no_hint():
    _make_user("alice")
    context = build_knowledge_context(
        tenant_id="default", requester_user_id="alice",
        query="Wie ist das Wetter heute?",
    )
    assert context["status_message"] is None


# -- Testgruppe 7: Quellenliste (Backend = Quelle der Wahrheit) --------------

def test_build_sources_list_only_used_snippets():
    _seed_findable_source()
    context = build_knowledge_context(
        tenant_id="default", requester_user_id="alice", query="Urlaubsregelung",
    )
    sources = build_sources_list(context["tag_map"])
    assert len(sources) == 1
    assert sources[0]["tag"] == "[Quelle 1]"
    assert "source_id" in sources[0]
    assert "chunk_id" in sources[0]
    assert "title" in sources[0]


def test_build_sources_list_none_when_nothing_used():
    assert build_sources_list({}) is None


def test_model_cannot_invent_extra_sources():
    """Die Quellenliste wird ausschliesslich aus dem Backend-tag_map gebaut --
    ein vom Modell erfundener Text wird dafuer nie gelesen/geparsed."""
    source = _seed_findable_source()
    context = build_knowledge_context(
        tenant_id="default", requester_user_id="alice", query="Urlaubsregelung",
    )
    fake_model_output = "Siehe auch [Quelle 99] und [Quelle 2] fuer mehr Details."
    sources = build_sources_list(context["tag_map"])
    # Unabhaengig vom (fiktiven) Modelltext bleibt die Liste unveraendert.
    assert len(sources) == 1
    assert sources[0]["source_id"] == source["id"]


def test_sanitize_answer_citations_removes_unknown_tags():
    tag_map = {"[Quelle 1]": {"source_id": 1, "chunk_id": 1, "title": "X"}}
    text = "Laut [Quelle 1] und auch [Quelle 5] gilt das."
    cleaned = sanitize_answer_citations(text, tag_map)
    assert "[Quelle 1]" in cleaned
    assert "[Quelle 5]" not in cleaned


def test_sanitize_answer_citations_keeps_known_tags_only():
    tag_map = {"[Quelle 1]": {}, "[Quelle 2]": {}}
    text = "[Quelle 1] [Quelle 2] [Quelle 3]"
    cleaned = sanitize_answer_citations(text, tag_map)
    assert "[Quelle 1]" in cleaned
    assert "[Quelle 2]" in cleaned
    assert "[Quelle 3]" not in cleaned


def test_sanitize_answer_citations_empty_tag_map_removes_all():
    text = "Quelle: [Quelle 1]"
    cleaned = sanitize_answer_citations(text, {})
    assert "[Quelle 1]" not in cleaned


# -- Testgruppe 8: Fehlerfall (Suche/Governance schlaegt fehl) ---------------

def test_search_exception_returns_neutral_context(monkeypatch):
    import apps.backend.knowledge.rag_context as rag_context_module

    def _boom(**kwargs):
        raise RuntimeError("DB down")

    monkeypatch.setattr(rag_context_module, "search_knowledge_chunks", _boom)
    context = build_knowledge_context(
        tenant_id="default", requester_user_id="alice", query="irgendwas",
    )
    assert context["context_block"] is None
    assert context["answer_mode"] == "general_ai"


def test_reclassification_exception_treated_as_filtered(monkeypatch):
    import apps.backend.knowledge.rag_context as rag_context_module

    _seed_findable_source()

    def _boom(text):
        raise RuntimeError("classify kaputt")

    monkeypatch.setattr(rag_context_module, "classify", _boom)
    context = build_knowledge_context(
        tenant_id="default", requester_user_id="alice", query="Urlaubsregelung",
    )
    assert context["used_snippets"] == []
    assert context["context_block"] is None


def test_missing_required_arguments_returns_neutral_context():
    context = build_knowledge_context(tenant_id="", requester_user_id="alice", query="Test")
    assert context["context_block"] is None
    assert context["answer_mode"] == "general_ai"

    context2 = build_knowledge_context(tenant_id="default", requester_user_id="", query="Test")
    assert context2["context_block"] is None

    context3 = build_knowledge_context(tenant_id="default", requester_user_id="alice", query="   ")
    assert context3["context_block"] is None


# -- Testgruppe 9: Keine Websuche / keine externen Dienste -------------------

def test_rag_context_module_has_no_web_search_or_external_calls():
    import inspect
    import apps.backend.knowledge.rag_context as rag_context_module
    source = inspect.getsource(rag_context_module)
    forbidden_tokens = (
        "requests.get", "requests.post", "httpx.get", "httpx.post",
        "tavily", "Tavily", "web_search", "WebSearch", "pgvector",
        "ProviderOrchestrator", "openai", "groq_client",
    )
    for token in forbidden_tokens:
        assert token not in source, f"rag_context darf {token!r} nicht referenzieren"


# -- Testgruppe 10: Backend ist Quelle der Wahrheit --------------------------

def test_answer_mode_user_text_mapping_covers_expected_modes():
    assert answer_mode_user_text("general_ai") is None
    assert "internes Wissen" in answer_mode_user_text("internal_knowledge")
    assert answer_mode_user_text("no_internal_source") is not None
    assert answer_mode_user_text("blocked_sensitive") is not None


def test_sources_never_exceed_used_snippets_count():
    _make_user("alice")
    source = _make_source(uploaded_by="alice")
    for i in range(6):
        _make_chunk(source["id"], chunk_index=i, chunk_text=f"Suchwort Eintrag {i}.")
    _make_permission(source["id"])

    context = build_knowledge_context(
        tenant_id="default", requester_user_id="alice", query="Suchwort",
    )
    sources = build_sources_list(context["tag_map"])
    assert len(sources) == len(context["used_snippets"])
    assert len(sources) <= MAX_CONTEXT_SNIPPETS


# -- Testgruppe 11: Berechtigungen bleiben auch hier durchgesetzt -----------

def test_private_source_of_other_user_not_included():
    _make_user("alice")
    _make_user("bob")
    source = _make_source(uploaded_by="alice", visibility_scope="private")
    _make_chunk(source["id"], chunk_text="Suchwort vertraulicher Inhalt von Alice.")
    _make_permission(source["id"], visibility_scope="private", created_by="alice")

    context = build_knowledge_context(
        tenant_id="default", requester_user_id="bob", query="Suchwort",
    )
    assert context["context_block"] is None
    assert context["used_snippets"] == []
