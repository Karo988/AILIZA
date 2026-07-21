"""
AILIZA Wissensdatenbank -- Block C Phase C2: Sicherer Ingestion-Kern
=====================================================================
Nur TXT + Markdown (Karo-Entscheidung, siehe AILIZA_BLOCK_C_STOP_DECISIONS.md).
PDF/DOCX/CSV folgen als eigener, spaeterer Auftrag nach erneuter Freigabe.

Fail-closed: Originaldateien liegen unter /data/uploads (Docker-Volume),
die Datenbank speichert NUR Metadaten (Pfad, Hash, Status, Besitzer,
Sichtbarkeit, Berechtigungen). Sensible/unklare Inhalte werden NICHT aktiv
freigegeben (Status "blocked" oder "pending_review"), keine Chunks fuer
aktive Nutzung. Keine externen LLM-/Embedding-Aufrufe -- Klassifikation
laeuft ausschliesslich ueber die bestehende, pattern-basierte
Governance-Pipeline (apps/backend/governance/).
"""
from __future__ import annotations

import hashlib
import os
import uuid
import warnings
from pathlib import Path
from typing import Any

try:
    from ..governance.data_governance import classify, DataTarget
    from ..governance.data_matrix import check_data_target, PolicyDecision
    from ..database import (
        create_knowledge_source, create_knowledge_chunk,
        set_knowledge_source_permission, write_audit_entry,
    )
except ImportError:  # pragma: no cover
    from governance.data_governance import classify, DataTarget  # type: ignore
    from governance.data_matrix import check_data_target, PolicyDecision  # type: ignore
    from database import (  # type: ignore
        create_knowledge_source, create_knowledge_chunk,
        set_knowledge_source_permission, write_audit_entry,
    )


class KnowledgeIngestionError(ValueError):
    """Nutzerseitig verstaendlicher Ingestion-Fehler (Dateityp/Groesse/Inhalt)."""


ALLOWED_KNOWLEDGE_EXTENSIONS = {".txt", ".md"}
MAX_KNOWLEDGE_FILE_BYTES = 2_000_000
_CHUNK_MAX_CHARS = 1000

_MIME_TYPES = {".txt": "text/plain", ".md": "text/markdown"}
_SOURCE_TYPES = {".txt": "txt", ".md": "md"}

_UNSUPPORTED_TYPE_MESSAGE = (
    "Dieser Dateityp wird aktuell nicht unterstuetzt. Bitte lade eine "
    "TXT- oder Markdown-Datei (.txt/.md) hoch. Weitere Dateitypen folgen "
    "in einem spaeteren Schritt."
)
_BLOCKED_MESSAGE = (
    "Dieses Dokument konnte nicht gespeichert werden, da es vermutlich "
    "Zugangsdaten oder andere nicht erlaubte Inhalte enthaelt. Bitte "
    "entferne solche Inhalte und lade das Dokument erneut hoch, oder "
    "wende dich an eine Administratorin bzw. einen Administrator."
)
_PENDING_REVIEW_MESSAGE = (
    "Dein Dokument wurde gespeichert, muss aber vor der Nutzung noch "
    "geprueft werden, da es moeglicherweise sensible Inhalte enthaelt. "
    "Du wirst informiert, sobald es freigegeben ist."
)
_APPROVED_MESSAGE = "Dein Dokument wurde erfolgreich hinzugefuegt und ist jetzt durchsuchbar."

# Block D0: rein manuelle Demo-Kategorien fuer die Nachschlagewerk-Ansicht.
# KEINE automatische Kategorisierung per LLM -- der Nutzer waehlt selbst,
# oder es bleibt None (keine Kategorie).
ALLOWED_DEMO_CATEGORIES = {
    "Allgemein", "Richtlinie", "Projekt", "Kunde", "Vorlage",
    "Anleitung", "Vertrag/Compliance",
}


def _resolve_upload_dir() -> Path:
    """Aufloesung analog zu database._resolve_database_url: /data/uploads ist
    das Ziel im Docker-Volume, Dev-Fallback nur wenn das nicht anlegbar ist."""
    raw = os.getenv("AILIZA_KNOWLEDGE_UPLOAD_DIR", "/data/uploads")
    target = Path(raw)
    try:
        target.mkdir(parents=True, exist_ok=True)
        return target
    except OSError:
        repo_root = Path(__file__).resolve().parent.parent.parent.parent
        fallback = repo_root / "data" / "uploads"
        fallback.mkdir(parents=True, exist_ok=True)
        warnings.warn(
            f"AILIZA_KNOWLEDGE_UPLOAD_DIR ({raw}) nicht anlegbar. "
            f"Dev-Fallback: {fallback}. In Produktion persistentes Volume mounten.",
            stacklevel=2,
        )
        return fallback


def _sanitize_filename(filename: str | None) -> str:
    """Nimmt nur den Basisnamen -- keine Pfadanteile (weder / noch \\),
    keine Steuerzeichen. Wird NUR als Metadatum gespeichert, NIE fuer den
    tatsaechlichen Speicherpfad verwendet (siehe _build_storage_path)."""
    if not filename:
        raise KnowledgeIngestionError("Kein Dateiname angegeben.")
    normalized = filename.replace("\\", "/").replace("\x00", "")
    base = normalized.rsplit("/", 1)[-1].strip()
    if not base or base in {".", ".."}:
        raise KnowledgeIngestionError("Ungueltiger Dateiname.")
    return base


def _validate_extension(sanitized_filename: str) -> str:
    ext = os.path.splitext(sanitized_filename)[1].lower()
    if ext not in ALLOWED_KNOWLEDGE_EXTENSIONS:
        raise KnowledgeIngestionError(_UNSUPPORTED_TYPE_MESSAGE)
    return ext


def _split_into_chunks(text: str, max_chars: int = _CHUNK_MAX_CHARS) -> list[str]:
    """Deterministische, einfache Fixgroessen-Chunkbildung -- keine
    Bibliothek, keine Embeddings, reproduzierbar bei gleichem Input."""
    stripped = text.strip()
    if not stripped:
        return []
    return [stripped[i:i + max_chars] for i in range(0, len(stripped), max_chars)]


def ingest_txt_or_markdown_source(*, tenant_id: str, uploaded_by: str,
                                   filename: str, content: bytes,
                                   title: str | None = None,
                                   category: str | None = None) -> dict[str, Any]:
    """Sicherer Ingestion-Kern fuer Block C2 (nur TXT + Markdown).

    Fail-closed ueber die gesamte Kette: unbekannter Dateityp, leere Datei,
    zu grosse Datei oder ungueltiges UTF-8 werden mit einer verstaendlichen
    KnowledgeIngestionError abgelehnt, BEVOR irgendetwas gespeichert wird.
    Sensible/unklare Inhalte werden gespeichert, aber nicht aktiv freigegeben
    (status=blocked/pending_review, keine Chunks).

    category (Block D0): rein manuell, optional, feste Whitelist
    (ALLOWED_DEMO_CATEGORIES) -- keine automatische Kategorisierung.
    """
    if not tenant_id:
        raise KnowledgeIngestionError("Tenant fehlt.")
    if not uploaded_by:
        raise KnowledgeIngestionError("Hochladende Person fehlt.")
    if category is not None and category not in ALLOWED_DEMO_CATEGORIES:
        raise KnowledgeIngestionError(
            f"Ungueltige Kategorie. Bitte eine der folgenden waehlen: "
            f"{', '.join(sorted(ALLOWED_DEMO_CATEGORIES))}."
        )

    sanitized_filename = _sanitize_filename(filename)
    ext = _validate_extension(sanitized_filename)

    size = len(content or b"")
    if size == 0:
        raise KnowledgeIngestionError("Die Datei ist leer.")
    if size > MAX_KNOWLEDGE_FILE_BYTES:
        raise KnowledgeIngestionError(
            f"Die Datei ist zu gross (max. {MAX_KNOWLEDGE_FILE_BYTES // 1_000_000} MB). "
            "Bitte eine kleinere Datei hochladen oder den Inhalt aufteilen."
        )

    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError:
        raise KnowledgeIngestionError(
            "Die Datei konnte nicht als Text gelesen werden (kein gueltiges UTF-8). "
            "Bitte als reine Textdatei mit UTF-8-Kodierung hochladen."
        )

    content_hash = hashlib.sha256(content).hexdigest()

    # Bestehende, pattern-basierte Governance-Klassifikation -- kein LLM,
    # keine neue eigene Klassifikationslogik (siehe apps/backend/governance/).
    classification = classify(text)
    decision = check_data_target(
        data_classes=classification.data_classes,
        target=DataTarget.FILE_STORAGE,
        redaction_applied=False,
        approval_given=False,
        provider_profile_active=False,
    )

    # check_data_target(target=FILE_STORAGE) ist fuer allgemeine Dateiablage
    # gedacht und daher fuer SPECIAL_CATEGORY/CREDENTIALS allein nicht streng
    # genug fuer eine aktiv durchsuchbare Wissensquelle. Zusaetzlich das
    # bereits vorhandene classification.needs_review-Flag beachten (kein
    # neues Klassifikationssystem -- nur ein bestehendes Signal ernstnehmen).
    if decision == PolicyDecision.BLOCK:
        source_status = "blocked"
        user_message = _BLOCKED_MESSAGE
    elif decision in (PolicyDecision.APPROVAL_REQUIRED, PolicyDecision.REDACT_REQUIRED) or classification.needs_review:
        source_status = "pending_review"
        user_message = _PENDING_REVIEW_MESSAGE
    else:
        source_status = "approved"
        user_message = _APPROVED_MESSAGE

    # Speicherpfad wird AUSSCHLIESSLICH aus Tenant + zufaelliger ID + validierter
    # Extension gebaut -- der (sanitisierte) Nutzer-Dateiname fliesst nie in den
    # tatsaechlichen Pfad ein, dadurch ist Pfad-Traversal strukturell ausgeschlossen.
    upload_dir = _resolve_upload_dir() / tenant_id
    upload_dir.mkdir(parents=True, exist_ok=True)
    storage_path = upload_dir / f"{uuid.uuid4().hex}{ext}"
    storage_path.write_bytes(content)

    source = create_knowledge_source(
        tenant_id=tenant_id, uploaded_by=uploaded_by,
        source_type=_SOURCE_TYPES[ext],
        title=title or sanitized_filename,
        original_filename=sanitized_filename,
        storage_path=str(storage_path),
        content_hash=content_hash,
        mime_type=_MIME_TYPES[ext],
        status=source_status,
        category=category,
    )

    set_knowledge_source_permission(
        source_id=source["id"], tenant_id=tenant_id,
        visibility_scope="private", created_by=uploaded_by,
    )

    chunks_created = 0
    if source_status == "approved":
        for index, chunk_text in enumerate(_split_into_chunks(text)):
            create_knowledge_chunk(
                source_id=source["id"], tenant_id=tenant_id, chunk_index=index,
                chunk_text=chunk_text,
                chunk_hash=hashlib.sha256(chunk_text.encode("utf-8")).hexdigest(),
                token_estimate=max(1, len(chunk_text) // 4),
            )
            chunks_created += 1

    # Audit-Light: keine Rohinhalte, keine Klassifikations-Treffertexte.
    write_audit_entry(
        action="knowledge_source_ingested",
        metadata={
            "source_id": source["id"],
            "status": source_status,
            "size_bytes": size,
            "extension": ext,
            "chunks_created": chunks_created,
        },
        tenant_id=tenant_id,
    )

    return {
        "source": source,
        "status": source_status,
        "chunks_created": chunks_created,
        "message": user_message,
    }
