"""Block C Phase C3: Lokale Suche ueber freigegebene Wissens-Chunks.

Scope (siehe Karo-Auftrag Block C3):
Nur lokale Keyword-Suche ueber knowledge_chunks. Kein RAG, keine
Antwortgenerierung, keine UI, kein pgvector, keine Embeddings, kein
Wissensgraph, keine externen Dienste. Nur approved/aktive Quellen,
tenant_id/Sichtbarkeit/Berechtigungen werden respektiert.
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
    mark_knowledge_source_deleted, mark_knowledge_source_blocked,
)
from apps.backend.knowledge.search import (
    search_knowledge_chunks, KnowledgeSearchError, NOT_FOUND_MESSAGE,
)


@pytest.fixture(autouse=True)
def fresh_db():
    metadata_obj.drop_all(engine)
    init_db()
    yield


def _make_user(user_id: str, tenant_id: str = "default") -> None:
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


def _make_permission(source_id, tenant_id="default", visibility_scope="private",
                     created_by="alice", **kw):
    return set_knowledge_source_permission(
        source_id=source_id, tenant_id=tenant_id, visibility_scope=visibility_scope,
        created_by=created_by, **kw,
    )


# -- Testgruppe 1: Eigene/freigegebene Chunks werden gefunden ---------------

def test_finds_own_private_chunk():
    _make_user("alice")
    source = _make_source(uploaded_by="alice")
    _make_chunk(source["id"], chunk_text="Die Katze sitzt auf der Matte.")
    _make_permission(source["id"], created_by="alice")

    result = search_knowledge_chunks(
        tenant_id="default", requester_user_id="alice", query="Katze",
    )
    assert len(result["results"]) == 1
    assert result["results"][0]["source_id"] == source["id"]
    assert result["message"] is None


def test_does_not_find_other_users_private_chunk():
    _make_user("alice")
    _make_user("bob")
    source = _make_source(uploaded_by="alice")
    _make_chunk(source["id"], chunk_text="Vertrauliche Notiz von Alice.")
    _make_permission(source["id"], created_by="alice", visibility_scope="private")

    result = search_knowledge_chunks(
        tenant_id="default", requester_user_id="bob", query="Vertrauliche",
    )
    assert result["results"] == []
    assert result["message"] == NOT_FOUND_MESSAGE


# -- Testgruppe 2: blocked/deleted/pending_review/expired werden nie gefunden --

def test_blocked_source_not_found():
    _make_user("alice")
    source = _make_source(uploaded_by="alice", status="blocked")
    _make_chunk(source["id"], chunk_text="Blockierter Inhalt mit Suchbegriff.")
    _make_permission(source["id"], created_by="alice", visibility_scope="organization")

    result = search_knowledge_chunks(
        tenant_id="default", requester_user_id="alice", query="Suchbegriff",
    )
    assert result["results"] == []


def test_pending_review_source_not_found():
    _make_user("alice")
    source = _make_source(uploaded_by="alice", status="pending_review")
    _make_chunk(source["id"], chunk_text="Zu pruefender Inhalt mit Suchbegriff.")
    _make_permission(source["id"], created_by="alice", visibility_scope="organization")

    result = search_knowledge_chunks(
        tenant_id="default", requester_user_id="alice", query="Suchbegriff",
    )
    assert result["results"] == []


def test_deleted_source_not_found_after_deletion():
    _make_user("alice")
    source = _make_source(uploaded_by="alice", status="approved")
    _make_chunk(source["id"], chunk_text="Inhalt der spaeter geloescht wird.")
    _make_permission(source["id"], created_by="alice", visibility_scope="organization")

    before = search_knowledge_chunks(
        tenant_id="default", requester_user_id="alice", query="geloescht",
    )
    assert len(before["results"]) == 1

    mark_knowledge_source_deleted(source["id"])
    after = search_knowledge_chunks(
        tenant_id="default", requester_user_id="alice", query="geloescht",
    )
    assert after["results"] == []


def test_expired_source_not_found():
    _make_user("alice")
    source = _make_source(uploaded_by="alice", status="expired")
    _make_chunk(source["id"], chunk_text="Abgelaufener Inhalt mit Suchbegriff.")
    _make_permission(source["id"], created_by="alice", visibility_scope="organization")

    result = search_knowledge_chunks(
        tenant_id="default", requester_user_id="alice", query="Suchbegriff",
    )
    assert result["results"] == []


def test_mark_blocked_removes_previously_found_source():
    _make_user("alice")
    source = _make_source(uploaded_by="alice", status="approved")
    _make_chunk(source["id"], chunk_text="Inhalt der spaeter blockiert wird.")
    _make_permission(source["id"], created_by="alice", visibility_scope="organization")

    before = search_knowledge_chunks(
        tenant_id="default", requester_user_id="alice", query="blockiert",
    )
    assert len(before["results"]) == 1

    mark_knowledge_source_blocked(source["id"])
    after = search_knowledge_chunks(
        tenant_id="default", requester_user_id="alice", query="blockiert",
    )
    assert after["results"] == []


# -- Testgruppe 3: Ergebnisformat ---------------------------------------------

def test_result_contains_all_required_fields():
    _make_user("alice")
    source = _make_source(uploaded_by="alice")
    chunk = _make_chunk(source["id"], chunk_text="Ein Beispieltext mit Suchbegriff darin.")
    _make_permission(source["id"], created_by="alice")

    result = search_knowledge_chunks(
        tenant_id="default", requester_user_id="alice", query="Suchbegriff",
    )
    hit = result["results"][0]
    for field in (
        "source_id", "chunk_id", "title", "snippet", "score",
        "source_type", "visibility_scope", "status",
    ):
        assert field in hit, f"Ergebnis fehlt Feld {field}"
    assert hit["source_id"] == source["id"]
    assert hit["chunk_id"] == chunk["id"]
    assert hit["status"] == "approved"


# -- Testgruppe 4: tenant_id wird respektiert --------------------------------

def test_tenant_isolation():
    create_user(user_id="alice", tenant_id="tenant-a", role="user", hashed_password="hash")
    source = _make_source(tenant_id="tenant-a", uploaded_by="alice")
    _make_chunk(source["id"], tenant_id="tenant-a", chunk_text="Mandantenspezifischer Inhalt.")
    _make_permission(source["id"], tenant_id="tenant-a", created_by="alice", visibility_scope="organization")

    result = search_knowledge_chunks(
        tenant_id="tenant-b", requester_user_id="alice", query="Mandantenspezifischer",
    )
    assert result["results"] == []


# -- Testgruppe 5: Sichtbarkeits-Scopes ---------------------------------------

def test_organization_scope_visible_to_other_user_same_tenant():
    _make_user("alice")
    _make_user("bob")
    source = _make_source(uploaded_by="alice")
    _make_chunk(source["id"], chunk_text="Firmenweites Wissen fuer alle.")
    _make_permission(source["id"], created_by="alice", visibility_scope="organization")

    result = search_knowledge_chunks(
        tenant_id="default", requester_user_id="bob", query="Firmenweites",
    )
    assert len(result["results"]) == 1


def test_project_scope_requires_matching_project_id():
    _make_user("alice")
    _make_user("bob")
    source = _make_source(uploaded_by="alice")
    _make_chunk(source["id"], chunk_text="Projektspezifische Information.")
    _make_permission(source["id"], created_by="alice", visibility_scope="project", project_id="proj-1")

    no_project = search_knowledge_chunks(
        tenant_id="default", requester_user_id="bob", query="Projektspezifische",
    )
    assert no_project["results"] == []

    wrong_project = search_knowledge_chunks(
        tenant_id="default", requester_user_id="bob", query="Projektspezifische",
        project_id="proj-2",
    )
    assert wrong_project["results"] == []

    right_project = search_knowledge_chunks(
        tenant_id="default", requester_user_id="bob", query="Projektspezifische",
        project_id="proj-1",
    )
    assert len(right_project["results"]) == 1


def test_external_limited_scope_requires_allowed_user_or_role():
    _make_user("alice")
    _make_user("bob")
    _make_user("carol")
    source = _make_source(uploaded_by="alice")
    _make_chunk(source["id"], chunk_text="Eingeschraenkt geteiltes Wissen.")
    _make_permission(
        source["id"], created_by="alice", visibility_scope="external_limited",
        allowed_user_ids=["carol"], allowed_roles=["auditor"],
    )

    not_allowed = search_knowledge_chunks(
        tenant_id="default", requester_user_id="bob", query="Eingeschraenkt",
    )
    assert not_allowed["results"] == []

    allowed_by_user = search_knowledge_chunks(
        tenant_id="default", requester_user_id="carol", query="Eingeschraenkt",
    )
    assert len(allowed_by_user["results"]) == 1

    allowed_by_role = search_knowledge_chunks(
        tenant_id="default", requester_user_id="bob", query="Eingeschraenkt",
        requester_roles=["auditor"],
    )
    assert len(allowed_by_role["results"]) == 1


def test_no_permission_row_is_fail_closed_only_uploader_sees():
    _make_user("alice")
    _make_user("bob")
    source = _make_source(uploaded_by="alice")
    _make_chunk(source["id"], chunk_text="Inhalt ohne explizite Berechtigung.")
    # Bewusst KEINE set_knowledge_source_permission()-Aufruf.

    owner_result = search_knowledge_chunks(
        tenant_id="default", requester_user_id="alice", query="Berechtigung",
    )
    assert len(owner_result["results"]) == 1

    other_result = search_knowledge_chunks(
        tenant_id="default", requester_user_id="bob", query="Berechtigung",
    )
    assert other_result["results"] == []


# -- Testgruppe 6: Kein Treffer -> freundliche Meldung -----------------------

def test_no_match_returns_friendly_message():
    _make_user("alice")
    source = _make_source(uploaded_by="alice")
    _make_chunk(source["id"], chunk_text="Voellig anderer Inhalt.")
    _make_permission(source["id"], created_by="alice", visibility_scope="organization")

    result = search_knowledge_chunks(
        tenant_id="default", requester_user_id="alice", query="NichtVorhandenesWort",
    )
    assert result["results"] == []
    assert result["message"] == NOT_FOUND_MESSAGE


# -- Testgruppe 7: Relevanz-Sortierung ---------------------------------------

def test_results_sorted_by_relevance_score_descending():
    _make_user("alice")
    source = _make_source(uploaded_by="alice")
    _make_chunk(source["id"], chunk_index=0, chunk_text="Katze Katze Katze Katze.")
    _make_chunk(source["id"], chunk_index=1, chunk_text="Katze einmal erwaehnt.")
    _make_permission(source["id"], created_by="alice", visibility_scope="organization")

    result = search_knowledge_chunks(
        tenant_id="default", requester_user_id="alice", query="Katze",
    )
    scores = [hit["score"] for hit in result["results"]]
    assert scores == sorted(scores, reverse=True)
    assert result["results"][0]["chunk_id"] != result["results"][1]["chunk_id"]


# -- Testgruppe 8: kein RAG, keine externen Dienste --------------------------

def test_search_module_has_no_external_llm_or_embedding_calls():
    import inspect
    import apps.backend.knowledge.search as search_module
    source = inspect.getsource(search_module)
    forbidden_tokens = (
        "ProviderOrchestrator", "openai", "anthropic.Anthropic", "requests.post",
        "httpx.post", "embed(", "embedding", "groq_client", "pgvector",
    )
    for token in forbidden_tokens:
        assert token not in source, f"Such-Modul darf {token!r} nicht referenzieren"


# -- Testgruppe 9: Validierung ------------------------------------------------

def test_empty_query_raises_error():
    _make_user("alice")
    with pytest.raises(KnowledgeSearchError):
        search_knowledge_chunks(tenant_id="default", requester_user_id="alice", query="   ")


def test_missing_tenant_id_raises_error():
    with pytest.raises(KnowledgeSearchError):
        search_knowledge_chunks(tenant_id="", requester_user_id="alice", query="Text")


def test_missing_requester_raises_error():
    with pytest.raises(KnowledgeSearchError):
        search_knowledge_chunks(tenant_id="default", requester_user_id="", query="Text")


# -- Testgruppe 10: Limit wird respektiert -----------------------------------

def test_result_limit_is_respected():
    _make_user("alice")
    source = _make_source(uploaded_by="alice")
    for i in range(5):
        _make_chunk(source["id"], chunk_index=i, chunk_text=f"Wiederholung Nummer {i} von Suchwort.")
    _make_permission(source["id"], created_by="alice", visibility_scope="organization")

    result = search_knowledge_chunks(
        tenant_id="default", requester_user_id="alice", query="Suchwort", limit=2,
    )
    assert len(result["results"]) == 2
