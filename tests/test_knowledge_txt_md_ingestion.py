"""Block C Phase C2: Sichere TXT/Markdown-Ingestion fuer Wissensquellen.

Scope (siehe Karo-Auftrag Block C2):
Nur der sichere Ingestion-Kern fuer TXT + Markdown. Originaldateien liegen
unter /data/uploads (Docker-Volume, hier per Env-Var auf ein Testverzeichnis
umgeleitet), die Datenbank speichert nur Metadaten. Fail-closed bei
sensiblen/unklaren Inhalten (Status pending_review/blocked). Keine
Suche, kein RAG, kein pgvector, keine UI, kein PDF/DOCX, keine externen
LLM-/Embedding-Aufrufe.
"""
from __future__ import annotations

import hashlib
import os

os.environ.setdefault("AILIZA_SECRET_KEY", "test-secret-key-minimum-32-chars-ok")
os.environ.setdefault("AILIZA_DATABASE_URL", "sqlite:///:memory:")

import pytest

from apps.backend.database import (
    metadata_obj, engine, init_db, create_user,
    get_knowledge_source, get_knowledge_source_permission,
    list_active_chunks_for_source, mark_knowledge_source_deleted,
)
from apps.backend.knowledge.ingestion import (
    ingest_txt_or_markdown_source, KnowledgeIngestionError,
    ALLOWED_KNOWLEDGE_EXTENSIONS, MAX_KNOWLEDGE_FILE_BYTES,
)


@pytest.fixture(autouse=True)
def fresh_db():
    metadata_obj.drop_all(engine)
    init_db()
    yield


@pytest.fixture(autouse=True)
def upload_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("AILIZA_KNOWLEDGE_UPLOAD_DIR", str(tmp_path / "uploads"))
    yield tmp_path / "uploads"


def _make_user(user_id: str = "alice", tenant_id: str = "default") -> None:
    create_user(user_id=user_id, tenant_id=tenant_id, role="user", hashed_password="hash")


# -- Testgruppe 1: Nur .txt und .md werden akzeptiert --------------------

def test_txt_file_accepted():
    _make_user()
    result = ingest_txt_or_markdown_source(
        tenant_id="default", uploaded_by="alice", filename="notiz.txt",
        content=b"Ein normaler Text ohne sensible Inhalte.",
    )
    assert result["status"] == "approved"
    assert result["source"]["source_type"] == "txt"


def test_markdown_file_accepted():
    _make_user()
    result = ingest_txt_or_markdown_source(
        tenant_id="default", uploaded_by="alice", filename="notiz.md",
        content=b"# Ueberschrift\n\nEin normaler Markdown-Text.",
    )
    assert result["status"] == "approved"
    assert result["source"]["source_type"] == "md"


def test_pdf_file_rejected():
    _make_user()
    with pytest.raises(KnowledgeIngestionError):
        ingest_txt_or_markdown_source(
            tenant_id="default", uploaded_by="alice", filename="dokument.pdf",
            content=b"%PDF-1.4 ...",
        )


def test_docx_file_rejected():
    _make_user()
    with pytest.raises(KnowledgeIngestionError):
        ingest_txt_or_markdown_source(
            tenant_id="default", uploaded_by="alice", filename="dokument.docx",
            content=b"PK\x03\x04 ...",
        )


def test_allowed_extensions_constant_is_exactly_txt_and_md():
    assert ALLOWED_KNOWLEDGE_EXTENSIONS == {".txt", ".md"}


# -- Testgruppe 2: Dateien werden unter /data/uploads gespeichert --------------------

def test_file_is_written_to_upload_dir(upload_dir):
    _make_user()
    result = ingest_txt_or_markdown_source(
        tenant_id="default", uploaded_by="alice", filename="a.txt",
        content=b"Inhalt fuer Speichertest.",
    )
    storage_path = result["source"]["storage_path"]
    assert storage_path is not None
    assert str(upload_dir) in storage_path
    assert os.path.isfile(storage_path)
    with open(storage_path, "rb") as f:
        assert f.read() == b"Inhalt fuer Speichertest."


# -- Testgruppe 3: Pfad-Traversal wird verhindert --------------------

def test_path_traversal_filename_is_neutralized(upload_dir):
    _make_user()
    result = ingest_txt_or_markdown_source(
        tenant_id="default", uploaded_by="alice",
        filename="../../etc/passwd.txt",
        content=b"harmloser Inhalt",
    )
    storage_path = result["source"]["storage_path"]
    # Storage-Pfad bleibt IMMER innerhalb des Upload-Verzeichnisses.
    assert os.path.commonpath([str(upload_dir), storage_path]) == str(upload_dir)
    assert ".." not in os.path.relpath(storage_path, str(upload_dir))
    # Der urspruengliche (sanitisierte) Dateiname wird nur als Metadatum gespeichert.
    assert result["source"]["original_filename"] == "passwd.txt"


def test_path_traversal_backslash_variant_is_neutralized(upload_dir):
    _make_user()
    result = ingest_txt_or_markdown_source(
        tenant_id="default", uploaded_by="alice",
        filename="..\\..\\windows\\win.txt",
        content=b"harmloser Inhalt",
    )
    storage_path = result["source"]["storage_path"]
    assert os.path.commonpath([str(upload_dir), storage_path]) == str(upload_dir)


# -- Testgruppe 4: content_hash wird gespeichert --------------------

def test_content_hash_is_stored_correctly():
    _make_user()
    content = b"Hash-Test-Inhalt"
    result = ingest_txt_or_markdown_source(
        tenant_id="default", uploaded_by="alice", filename="hash.txt", content=content,
    )
    expected = hashlib.sha256(content).hexdigest()
    assert result["source"]["content_hash"] == expected


# -- Testgruppe 5: knowledge_sources wird korrekt angelegt --------------------

def test_knowledge_source_created_with_correct_fields():
    _make_user()
    result = ingest_txt_or_markdown_source(
        tenant_id="default", uploaded_by="alice", filename="quelle.txt",
        content=b"Ein Beispieltext.", title="Meine Quelle",
    )
    source = get_knowledge_source(result["source"]["id"])
    assert source["tenant_id"] == "default"
    assert source["uploaded_by"] == "alice"
    assert source["title"] == "Meine Quelle"
    assert source["mime_type"] == "text/plain"


# -- Testgruppe 6: knowledge_chunks werden deterministisch erzeugt --------------------

def test_chunks_created_deterministically():
    _make_user()
    content = ("Satz eins. " * 50).encode("utf-8")
    result_a = ingest_txt_or_markdown_source(
        tenant_id="default", uploaded_by="alice", filename="a.txt", content=content,
    )
    result_b = ingest_txt_or_markdown_source(
        tenant_id="default", uploaded_by="alice", filename="b.txt", content=content,
    )
    chunks_a = list_active_chunks_for_source(result_a["source"]["id"])
    chunks_b = list_active_chunks_for_source(result_b["source"]["id"])
    assert len(chunks_a) == len(chunks_b)
    assert [c["chunk_text"] for c in chunks_a] == [c["chunk_text"] for c in chunks_b]
    assert [c["chunk_index"] for c in chunks_a] == list(range(len(chunks_a)))


def test_empty_file_rejected():
    _make_user()
    with pytest.raises(KnowledgeIngestionError):
        ingest_txt_or_markdown_source(
            tenant_id="default", uploaded_by="alice", filename="leer.txt", content=b"",
        )


def test_oversized_file_rejected():
    _make_user()
    too_big = b"x" * (MAX_KNOWLEDGE_FILE_BYTES + 1)
    with pytest.raises(KnowledgeIngestionError):
        ingest_txt_or_markdown_source(
            tenant_id="default", uploaded_by="alice", filename="riesig.txt", content=too_big,
        )


# -- Testgruppe 7: blockierte Quellen erzeugen keine aktiven Chunks --------------------

def test_secret_content_blocks_source_and_creates_no_chunks():
    _make_user()
    result = ingest_txt_or_markdown_source(
        tenant_id="default", uploaded_by="alice", filename="secret.txt",
        content=b"Mein API-Key: sk-abcdefghijklmnopqrstuvwxyz123456",
    )
    assert result["status"] == "blocked"
    assert list_active_chunks_for_source(result["source"]["id"]) == []


def test_password_in_german_blocks_source():
    _make_user()
    result = ingest_txt_or_markdown_source(
        tenant_id="default", uploaded_by="alice", filename="zugang.txt",
        content=b"Passwort: Sommer2026!",
    )
    assert result["status"] == "blocked"
    assert list_active_chunks_for_source(result["source"]["id"]) == []


# -- Testgruppe 8: sensible Inhalte werden blocked oder pending_review --------------------

def test_sensitive_but_not_secret_content_is_pending_review_or_blocked():
    _make_user()
    # Personenbezogene/besondere Kategorie (Gesundheitsdaten) -- kein Secret,
    # aber sensibel genug fuer menschliche Pruefung vor aktiver Nutzung.
    result = ingest_txt_or_markdown_source(
        tenant_id="default", uploaded_by="alice", filename="gesundheit.txt",
        content=b"Diagnose: Depression. Patientin leidet seit 2024 an dieser Erkrankung.",
    )
    assert result["status"] in {"pending_review", "blocked"}
    assert list_active_chunks_for_source(result["source"]["id"]) == []


def test_user_message_never_contains_technical_regex_details():
    _make_user()
    result = ingest_txt_or_markdown_source(
        tenant_id="default", uploaded_by="alice", filename="secret.txt",
        content=b"token=abcdef1234567890geheim",
    )
    message = result["message"].lower()
    for forbidden in ("regex", "pattern", "traceback", "exception", "classdataclass"):
        assert forbidden not in message


# -- Testgruppe 9: keine externen LLM-/Embedding-Aufrufe --------------------

def test_ingestion_module_has_no_external_llm_or_embedding_calls():
    import inspect
    import apps.backend.knowledge.ingestion as ingestion_module
    source = inspect.getsource(ingestion_module)
    forbidden_tokens = (
        "ProviderOrchestrator", "openai", "anthropic.Anthropic", "requests.post",
        "httpx.post", "embed(", "embedding", "groq_client",
    )
    for token in forbidden_tokens:
        assert token not in source, f"Ingestion-Modul darf {token!r} nicht referenzieren"


# -- Testgruppe 10: Berechtigungen werden angelegt --------------------

def test_permission_row_created_with_private_default():
    _make_user()
    result = ingest_txt_or_markdown_source(
        tenant_id="default", uploaded_by="alice", filename="perm.txt",
        content=b"Ein Text fuer den Berechtigungstest.",
    )
    perm = get_knowledge_source_permission(result["source"]["id"])
    assert perm is not None
    assert perm["visibility_scope"] == "private"
    assert perm["created_by"] == "alice"


# -- Testgruppe 11: geloeschte/blockierte Quellen sind nicht aktiv nutzbar --------------------

def test_deleted_source_after_ingestion_has_no_active_chunks():
    _make_user()
    result = ingest_txt_or_markdown_source(
        tenant_id="default", uploaded_by="alice", filename="del.txt",
        content=b"Text der spaeter geloescht wird.",
    )
    assert list_active_chunks_for_source(result["source"]["id"]) != []
    mark_knowledge_source_deleted(result["source"]["id"])
    assert list_active_chunks_for_source(result["source"]["id"]) == []


# -- Testgruppe 12: Pflichtfelder --------------------

def test_missing_tenant_id_rejected():
    _make_user()
    with pytest.raises(KnowledgeIngestionError):
        ingest_txt_or_markdown_source(
            tenant_id="", uploaded_by="alice", filename="x.txt", content=b"Text",
        )


def test_missing_uploaded_by_rejected():
    _make_user()
    with pytest.raises(KnowledgeIngestionError):
        ingest_txt_or_markdown_source(
            tenant_id="default", uploaded_by="", filename="x.txt", content=b"Text",
        )


def test_invalid_utf8_content_rejected():
    _make_user()
    with pytest.raises(KnowledgeIngestionError):
        ingest_txt_or_markdown_source(
            tenant_id="default", uploaded_by="alice", filename="bin.txt",
            content=b"\xff\xfe\x00\x01invalid",
        )


# -- Testgruppe 13 (Block D0): optionale, manuelle Demo-Kategorie -----------

def test_valid_category_accepted():
    _make_user()
    result = ingest_txt_or_markdown_source(
        tenant_id="default", uploaded_by="alice", filename="richtlinie.txt",
        content=b"Ein Richtlinientext.", category="Richtlinie",
    )
    assert result["source"]["category"] == "Richtlinie"


def test_no_category_is_none():
    _make_user()
    result = ingest_txt_or_markdown_source(
        tenant_id="default", uploaded_by="alice", filename="x.txt", content=b"Text ohne Kategorie.",
    )
    assert result["source"]["category"] is None


def test_invalid_category_rejected():
    _make_user()
    with pytest.raises(KnowledgeIngestionError):
        ingest_txt_or_markdown_source(
            tenant_id="default", uploaded_by="alice", filename="x.txt", content=b"Text",
            category="ErfundeneKategorie",
        )
