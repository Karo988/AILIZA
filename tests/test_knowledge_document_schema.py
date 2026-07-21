"""Block C Phase C1: Dokument-/Quellen-Schema fuer die Wissensdatenbank.

Scope (siehe AILIZA_BLOCK_C_PHASE_C1_DOCUMENT_SCHEMA.md):
Nur das Datenbankfundament fuer Wissensquellen. Noch KEINE Dokumentextraktion,
KEINE Suche, KEIN RAG, KEINE Embeddings, KEIN pgvector, KEINE UI.

Tabellen:
- knowledge_sources: eine freigegebene/hochgeladene Wissensquelle
- knowledge_chunks: Textabschnitte einer Quelle (noch ohne Embeddings)
- knowledge_source_permissions: wer darf eine Quelle sehen/nutzen
"""
from __future__ import annotations

import os

os.environ.setdefault("AILIZA_SECRET_KEY", "test-secret-key-minimum-32-chars-ok")
os.environ.setdefault("AILIZA_DATABASE_URL", "sqlite:///:memory:")

import pytest
from sqlalchemy.exc import IntegrityError

from apps.backend.database import (
    metadata_obj, engine, init_db, create_user,
    knowledge_sources, knowledge_chunks, knowledge_source_permissions,
    create_knowledge_source, get_knowledge_source,
    create_knowledge_chunk, list_active_chunks_for_source,
    set_knowledge_source_permission, get_knowledge_source_permission,
    mark_knowledge_source_deleted, mark_knowledge_source_blocked,
    KnowledgeValidationError,
)


@pytest.fixture(autouse=True)
def fresh_db():
    metadata_obj.drop_all(engine)
    init_db()
    yield


def _make_user(user_id: str = "alice", tenant_id: str = "default") -> None:
    create_user(user_id=user_id, tenant_id=tenant_id, role="user", hashed_password="hash")


def _make_source(**overrides) -> dict:
    defaults = dict(
        tenant_id="default", uploaded_by="alice", source_type="txt",
        title="Testquelle",
    )
    defaults.update(overrides)
    return create_knowledge_source(**defaults)


# ── Testgruppe 1: Tabellen existieren ───────────────────────────────────────

def test_tables_are_created():
    for table in (knowledge_sources, knowledge_chunks, knowledge_source_permissions):
        assert table.name in metadata_obj.tables


def test_required_fields_present():
    source_cols = {c.name for c in knowledge_sources.columns}
    for field in (
        "id", "tenant_id", "uploaded_by", "source_type", "title",
        "original_filename", "storage_path", "content_hash", "mime_type",
        "status", "visibility_scope", "approved_by", "approved_at",
        "expires_at", "created_at", "updated_at",
    ):
        assert field in source_cols, f"knowledge_sources fehlt Feld {field}"

    chunk_cols = {c.name for c in knowledge_chunks.columns}
    for field in (
        "id", "source_id", "tenant_id", "chunk_index", "chunk_text",
        "chunk_hash", "page_number", "section_title", "token_estimate",
        "status", "created_at", "updated_at",
    ):
        assert field in chunk_cols, f"knowledge_chunks fehlt Feld {field}"

    perm_cols = {c.name for c in knowledge_source_permissions.columns}
    for field in (
        "id", "source_id", "tenant_id", "visibility_scope", "allowed_roles",
        "allowed_user_ids", "project_id", "created_by", "created_at", "updated_at",
    ):
        assert field in perm_cols, f"knowledge_source_permissions fehlt Feld {field}"


# ── Testgruppe 2: Source braucht Tenant/Owner ───────────────────────────────

def test_create_knowledge_source_requires_tenant():
    _make_user()
    with pytest.raises(KnowledgeValidationError):
        create_knowledge_source(
            tenant_id=None, uploaded_by="alice", source_type="txt", title="X",
        )


def test_create_knowledge_source_requires_uploaded_by():
    _make_user()
    with pytest.raises(KnowledgeValidationError):
        create_knowledge_source(
            tenant_id="default", uploaded_by=None, source_type="txt", title="X",
        )


def test_create_knowledge_source_success():
    _make_user()
    source = _make_source()
    assert source["id"] is not None
    assert source["tenant_id"] == "default"
    assert source["uploaded_by"] == "alice"
    assert source["status"] == "uploaded"


def test_get_knowledge_source_roundtrip():
    _make_user()
    source = _make_source()
    fetched = get_knowledge_source(source["id"])
    assert fetched is not None
    assert fetched["title"] == "Testquelle"


# ── Testgruppe 3: Statuswerte werden validiert ──────────────────────────────

def test_invalid_source_type_rejected():
    _make_user()
    with pytest.raises(KnowledgeValidationError):
        create_knowledge_source(
            tenant_id="default", uploaded_by="alice",
            source_type="exe", title="X",
        )


def test_invalid_status_rejected():
    _make_user()
    with pytest.raises(KnowledgeValidationError):
        create_knowledge_source(
            tenant_id="default", uploaded_by="alice",
            source_type="txt", title="X", status="not_a_real_status",
        )


def test_valid_source_types_accepted():
    _make_user()
    for source_type in ("pdf", "docx", "txt", "md", "csv", "manual", "url_reference"):
        source = _make_source(source_type=source_type)
        assert source["source_type"] == source_type


def test_invalid_chunk_status_rejected():
    _make_user()
    source = _make_source()
    with pytest.raises(KnowledgeValidationError):
        create_knowledge_chunk(
            source_id=source["id"], tenant_id="default", chunk_index=0,
            chunk_text="Testinhalt", status="not_a_real_status",
        )


def test_invalid_visibility_scope_rejected():
    _make_user()
    source = _make_source()
    with pytest.raises(KnowledgeValidationError):
        set_knowledge_source_permission(
            source_id=source["id"], tenant_id="default",
            visibility_scope="public_internet", created_by="alice",
        )


# ── Testgruppe 4: Chunk braucht Source ──────────────────────────────────────

def test_chunk_requires_existing_source():
    _make_user()
    with pytest.raises(KnowledgeValidationError):
        create_knowledge_chunk(
            source_id=999999, tenant_id="default", chunk_index=0,
            chunk_text="verwaister Chunk",
        )


def test_create_knowledge_chunk_success():
    _make_user()
    source = _make_source()
    chunk = create_knowledge_chunk(
        source_id=source["id"], tenant_id="default", chunk_index=0,
        chunk_text="Ein Textabschnitt.",
    )
    assert chunk["id"] is not None
    assert chunk["source_id"] == source["id"]
    assert chunk["status"] == "active"


# ── Testgruppe 5: Permissions brauchen Source ───────────────────────────────

def test_permission_requires_existing_source():
    _make_user()
    with pytest.raises(KnowledgeValidationError):
        set_knowledge_source_permission(
            source_id=999999, tenant_id="default",
            visibility_scope="private", created_by="alice",
        )


def test_set_and_get_knowledge_source_permission():
    _make_user()
    source = _make_source()
    perm = set_knowledge_source_permission(
        source_id=source["id"], tenant_id="default",
        visibility_scope="team", created_by="alice",
    )
    assert perm["visibility_scope"] == "team"
    fetched = get_knowledge_source_permission(source["id"])
    assert fetched["visibility_scope"] == "team"


# ── Testgruppe 6: Standard-Sichtbarkeit ist nicht automatisch oeffentlich ───

def test_default_visibility_scope_is_private():
    _make_user()
    source = _make_source()
    assert source["visibility_scope"] == "private"


# ── Testgruppe 7: Geloeschte/blockierte Sources liefern keine aktiven Chunks ─

def test_deleted_source_yields_no_active_chunks():
    _make_user()
    source = _make_source()
    create_knowledge_chunk(
        source_id=source["id"], tenant_id="default", chunk_index=0,
        chunk_text="Inhalt vor Loeschung.",
    )
    mark_knowledge_source_deleted(source["id"])
    assert list_active_chunks_for_source(source["id"]) == []


def test_blocked_source_yields_no_active_chunks():
    _make_user()
    source = _make_source()
    create_knowledge_chunk(
        source_id=source["id"], tenant_id="default", chunk_index=0,
        chunk_text="Inhalt vor Blockierung.",
    )
    mark_knowledge_source_blocked(source["id"])
    assert list_active_chunks_for_source(source["id"]) == []


def test_active_source_yields_active_chunks():
    _make_user()
    source = _make_source()
    create_knowledge_chunk(
        source_id=source["id"], tenant_id="default", chunk_index=0,
        chunk_text="Aktiver Inhalt.",
    )
    chunks = list_active_chunks_for_source(source["id"])
    assert len(chunks) == 1
    assert chunks[0]["chunk_text"] == "Aktiver Inhalt."


# ── Testgruppe 8: Kein Suchen/Ingestion-Code in C1 ──────────────────────────

def test_no_search_function_exists():
    """C1 baut nur das Schema -- keine Suchfunktion darf existieren."""
    import apps.backend.database as db_module
    forbidden_names = ("search_knowledge", "search_chunks", "rag_query", "embed_chunk")
    for name in forbidden_names:
        assert not hasattr(db_module, name), f"C1 darf keine Suchfunktion {name} enthalten"
