"""Block D0: Datenbank-Erweiterungen fuer die Demo-/Nachschlagewerk-Ansicht.

Rein additiv: nullable `category`-Spalte auf knowledge_sources sowie
list_knowledge_sources_for_tenant() mit Chunk-Anzahl. Keine neue
Architektur, keine automatische Kategorisierung.
"""
from __future__ import annotations

import os

os.environ.setdefault("AILIZA_SECRET_KEY", "test-secret-key-minimum-32-chars-ok")
os.environ.setdefault("AILIZA_DATABASE_URL", "sqlite:///:memory:")

import pytest

from apps.backend.database import (
    metadata_obj, engine, init_db, create_user,
    create_knowledge_source, create_knowledge_chunk,
    list_knowledge_sources_for_tenant,
)


@pytest.fixture(autouse=True)
def fresh_db():
    metadata_obj.drop_all(engine)
    init_db()
    yield


def _make_user(user_id: str = "alice", tenant_id: str = "default") -> None:
    create_user(user_id=user_id, tenant_id=tenant_id, role="user", hashed_password="hash")


def test_category_column_exists_and_is_optional():
    _make_user()
    source = create_knowledge_source(
        tenant_id="default", uploaded_by="alice", source_type="txt", title="Ohne Kategorie",
    )
    assert source["category"] is None


def test_category_can_be_set():
    _make_user()
    source = create_knowledge_source(
        tenant_id="default", uploaded_by="alice", source_type="txt", title="Mit Kategorie",
        category="Richtlinie",
    )
    assert source["category"] == "Richtlinie"


def test_list_knowledge_sources_for_tenant_includes_all_statuses():
    _make_user()
    create_knowledge_source(tenant_id="default", uploaded_by="alice", source_type="txt",
                            title="A", status="approved")
    create_knowledge_source(tenant_id="default", uploaded_by="alice", source_type="txt",
                            title="B", status="blocked")
    create_knowledge_source(tenant_id="default", uploaded_by="alice", source_type="txt",
                            title="C", status="pending_review")

    sources = list_knowledge_sources_for_tenant("default")
    assert len(sources) == 3
    statuses = {s["status"] for s in sources}
    assert statuses == {"approved", "blocked", "pending_review"}


def test_list_knowledge_sources_for_tenant_respects_tenant_isolation():
    create_user(user_id="alice", tenant_id="tenant-a", role="user", hashed_password="hash")
    create_knowledge_source(tenant_id="tenant-a", uploaded_by="alice", source_type="txt", title="A")

    assert list_knowledge_sources_for_tenant("tenant-b") == []
    assert len(list_knowledge_sources_for_tenant("tenant-a")) == 1


def test_list_knowledge_sources_includes_chunk_count():
    _make_user()
    source = create_knowledge_source(
        tenant_id="default", uploaded_by="alice", source_type="txt", title="Mit Chunks",
        status="approved",
    )
    create_knowledge_chunk(source_id=source["id"], tenant_id="default", chunk_index=0, chunk_text="Eins")
    create_knowledge_chunk(source_id=source["id"], tenant_id="default", chunk_index=1, chunk_text="Zwei")

    sources = list_knowledge_sources_for_tenant("default")
    assert sources[0]["chunk_count"] == 2


def test_list_knowledge_sources_zero_chunk_count_when_none():
    _make_user()
    create_knowledge_source(tenant_id="default", uploaded_by="alice", source_type="txt", title="Ohne Chunks")
    sources = list_knowledge_sources_for_tenant("default")
    assert sources[0]["chunk_count"] == 0
