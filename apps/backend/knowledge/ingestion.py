"""
AILIZA Wissensdatenbank -- Sicherer Ingestion-Kern
=====================================================================
Unterstuetzt TXT/MD (reiner Text) sowie PDF/DOCX/XLSX/CSV (strukturierte
Extraktion ueber documents/extraction.py, konsolidiert mit dem Governance-
Scan-Pfad documents/document_handler.py -- vorher gab es zwei getrennte,
unabhaengige Datei-Lese-Implementierungen, das ist jetzt aufgeraeumt).
Bilder (.png/.jpg/.jpeg) NUR, wenn OCR lokal verfuegbar ist (siehe
extraction.ocr_available(); auf dem aktuellen Server-Hosting nicht
verfuegbar, Karo-Entscheidung 2026-08-03).

Fail-closed: Originaldateien liegen unter /data/uploads (Docker-Volume),
die Datenbank speichert NUR Metadaten (Pfad, Hash, Status, Besitzer,
Sichtbarkeit, Berechtigungen). Sensible/unklare Inhalte werden NICHT aktiv
freigegeben (Status "blocked" oder "pending_review"), keine Chunks fuer
aktive Nutzung. Keine externen LLM-/Embedding-Aufrufe -- Klassifikation
laeuft ausschliesslich ueber die bestehende, pattern-basierte
Governance-Pipeline (apps/backend/governance/).

Duplikat-Verhalten (Karo-Entscheidung 2026-08-03): identischer content_hash
im selben Tenant -> bestehende Quelle wird zurueckgegeben, kein Fehler,
kein zweiter Eintrag (siehe database.get_knowledge_source_by_hash).
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
        get_knowledge_source_by_hash,
        set_knowledge_source_permission, write_audit_entry,
    )
    from ..documents.extraction import extract_structured, supported_structured_extensions
    from ..documents.document_handler import _scan_for_injection
except ImportError:  # pragma: no cover
    from governance.data_governance import classify, DataTarget  # type: ignore
    from governance.data_matrix import check_data_target, PolicyDecision  # type: ignore
    from database import (  # type: ignore
        create_knowledge_source, create_knowledge_chunk,
        get_knowledge_source_by_hash,
        set_knowledge_source_permission, write_audit_entry,
    )
    from documents.extraction import extract_structured, supported_structured_extensions  # type: ignore
    from documents.document_handler import _scan_for_injection  # type: ignore


class KnowledgeIngestionError(ValueError):
    """Nutzerseitig verstaendlicher Ingestion-Fehler (Dateityp/Groesse/Inhalt)."""


_TEXT_EXTENSIONS = {".txt", ".md"}


def _structured_extensions() -> set[str]:
    return supported_structured_extensions()


def allowed_knowledge_extensions() -> set[str]:
    """Dynamisch (Bild-Formate nur bei verfuegbarem lokalem OCR) -- fuer
    Aufrufer, die die aktuell gueltige Menge brauchen (z.B. Endpunkt-
    Validierung, Frontend-Hinweistexte)."""
    return _TEXT_EXTENSIONS | _structured_extensions()


# Rueckwaertskompatibler Name (bestehende Importe/Tests) -- statisch auf die
# reinen Textformate begrenzt, weil ALLOWED_KNOWLEDGE_EXTENSIONS bisher als
# einfaches, unveraenderliches set genutzt wurde. Neue Aufrufer sollten
# allowed_knowledge_extensions() verwenden (siehe oben).
ALLOWED_KNOWLEDGE_EXTENSIONS = _TEXT_EXTENSIONS

MAX_KNOWLEDGE_FILE_BYTES = 2_000_000
MAX_KNOWLEDGE_DOCUMENT_FILE_BYTES = 10_000_000  # PDF/DOCX/XLSX koennen groesser sein
_CHUNK_MAX_CHARS = 1000

_MIME_TYPES = {
    ".txt": "text/plain", ".md": "text/markdown",
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".csv": "text/csv",
    ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
}
_SOURCE_TYPES = {
    ".txt": "txt", ".md": "md", ".pdf": "pdf", ".docx": "docx", ".xlsx": "xlsx",
    ".csv": "csv", ".png": "image", ".jpg": "image", ".jpeg": "image",
}
_DUPLICATE_MESSAGE = "Dieses Dokument wurde bereits hochgeladen."
_LIBRARY_MISSING_MESSAGE = (
    "Dieser Dateityp kann auf diesem Server aktuell nicht verarbeitet werden. "
    "Bitte an eine Administratorin bzw. einen Administrator wenden."
)

_UNSUPPORTED_TYPE_MESSAGE = (
    "Dieser Dateityp wird aktuell nicht unterstuetzt. Erlaubt sind "
    "TXT, Markdown, PDF, Word (.docx), Excel (.xlsx) und CSV -- Bilder "
    "nur auf lokal installierten AILIZA-Instanzen mit aktivierter "
    "Texterkennung."
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
    if ext not in allowed_knowledge_extensions():
        raise KnowledgeIngestionError(_UNSUPPORTED_TYPE_MESSAGE)
    return ext


def _split_into_chunks(text: str, max_chars: int = _CHUNK_MAX_CHARS) -> list[tuple[int | None, str | None, str]]:
    """Deterministische, einfache Fixgroessen-Chunkbildung fuer reinen Text
    (TXT/MD) -- keine Bibliothek, keine Embeddings, reproduzierbar bei
    gleichem Input. Rueckgabeformat wie _split_structured_sections()
    (page_number, section_title, chunk_text), page/section immer None."""
    stripped = text.strip()
    if not stripped:
        return []
    return [(None, None, stripped[i:i + max_chars]) for i in range(0, len(stripped), max_chars)]


def _split_structured_sections(
    sections: list[Any], max_chars: int = _CHUNK_MAX_CHARS,
) -> list[tuple[int | None, str | None, str]]:
    """Chunkt bereits extrahierte, strukturierte Abschnitte (siehe
    documents/extraction.py: ExtractedSection) weiter in Fixgroessen-Stuecke.
    Ein Chunk ueberschreitet nie eine Seiten-/Abschnittsgrenze -- page_number/
    section_title der Ursprungssektion werden an jeden daraus entstehenden
    Chunk durchgereicht."""
    chunks: list[tuple[int | None, str | None, str]] = []
    for section in sections:
        text = section.content_markdown.strip()
        if not text:
            continue
        for i in range(0, len(text), max_chars):
            chunks.append((section.page_number, section.section_title, text[i:i + max_chars]))
    return chunks


def ingest_document_source(*, tenant_id: str, uploaded_by: str,
                            filename: str, content: bytes,
                            title: str | None = None,
                            expires_at: Any | None = None) -> dict[str, Any]:
    """Sicherer Ingestion-Kern -- TXT/MD (reiner Text) sowie PDF/DOCX/XLSX/
    CSV (strukturierte Extraktion) und Bilder (nur bei lokal verfuegbarem
    OCR).

    Fail-closed ueber die gesamte Kette: unbekannter Dateityp, leere Datei,
    zu grosse Datei, fehlende Verarbeitungs-Bibliothek oder ungueltiges
    UTF-8 (bei Text) werden mit einer verstaendlichen KnowledgeIngestionError
    abgelehnt, BEVOR irgendetwas gespeichert wird. Sensible/unklare Inhalte
    werden gespeichert, aber nicht aktiv freigegeben (status=blocked/
    pending_review, keine Chunks). Identischer content_hash im selben Tenant
    liefert die bestehende Quelle zurueck statt eines neuen Eintrags.

    expires_at: optionales Ablaufdatum (datetime), aus der Chat-
    Aufbewahrungs-Einstellung berechnet (siehe database.
    get_chat_document_retention()) -- wird unveraendert an
    create_knowledge_source() durchgereicht, keine eigene Logik hier.
    """
    if not tenant_id:
        raise KnowledgeIngestionError("Tenant fehlt.")
    if not uploaded_by:
        raise KnowledgeIngestionError("Hochladende Person fehlt.")

    sanitized_filename = _sanitize_filename(filename)
    ext = _validate_extension(sanitized_filename)
    is_text = ext in _TEXT_EXTENSIONS

    size = len(content or b"")
    if size == 0:
        raise KnowledgeIngestionError("Die Datei ist leer.")
    size_limit = MAX_KNOWLEDGE_FILE_BYTES if is_text else MAX_KNOWLEDGE_DOCUMENT_FILE_BYTES
    if size > size_limit:
        raise KnowledgeIngestionError(
            f"Die Datei ist zu gross (max. {size_limit // 1_000_000} MB). "
            "Bitte eine kleinere Datei hochladen oder den Inhalt aufteilen."
        )

    content_hash = hashlib.sha256(content).hexdigest()

    existing = get_knowledge_source_by_hash(tenant_id=tenant_id, content_hash=content_hash)
    if existing is not None:
        return {
            "source": existing, "status": existing["status"],
            "chunks_created": 0, "duplicate": True,
            "message": _DUPLICATE_MESSAGE,
        }

    structured_sections: list[Any] = []
    if is_text:
        try:
            text = content.decode("utf-8")
        except UnicodeDecodeError:
            raise KnowledgeIngestionError(
                "Die Datei konnte nicht als Text gelesen werden (kein gueltiges UTF-8). "
                "Bitte als reine Textdatei mit UTF-8-Kodierung hochladen."
            )
    else:
        extraction = extract_structured(ext, content)
        if extraction.library_missing:
            raise KnowledgeIngestionError(_LIBRARY_MISSING_MESSAGE)
        structured_sections = extraction.sections
        text = extraction.full_text

    # Gate 6 -- Prompt-Injection-Erkennung, VOR der Governance-Klassifikation
    # (bisher fehlte dieser Schritt im Ingestion-Pfad komplett -- nur der
    # separate Scan-Endpunkt hatte ihn; jetzt konsolidiert, ein Signal).
    injection = _scan_for_injection(text)

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
    # bereits vorhandene classification.needs_review-Flag und den Gate-6-
    # Injection-Fund beachten (kein neues Klassifikationssystem -- nur
    # bestehende Signale ernstnehmen).
    if decision == PolicyDecision.BLOCK or injection.injection_detected:
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
        expires_at=expires_at,
    )

    set_knowledge_source_permission(
        source_id=source["id"], tenant_id=tenant_id,
        visibility_scope="private", created_by=uploaded_by,
    )

    chunks_created = 0
    if source_status == "approved":
        chunk_units = (
            _split_structured_sections(structured_sections) if structured_sections
            else _split_into_chunks(text)
        )
        for index, (page_number, section_title, chunk_text) in enumerate(chunk_units):
            create_knowledge_chunk(
                source_id=source["id"], tenant_id=tenant_id, chunk_index=index,
                chunk_text=chunk_text,
                chunk_hash=hashlib.sha256(chunk_text.encode("utf-8")).hexdigest(),
                page_number=page_number, section_title=section_title,
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
            "injection_detected": injection.injection_detected,
        },
        tenant_id=tenant_id,
    )

    return {
        "source": source,
        "status": source_status,
        "chunks_created": chunks_created,
        "message": user_message,
        "duplicate": False,
    }


def ingest_txt_or_markdown_source(*, tenant_id: str, uploaded_by: str,
                                   filename: str, content: bytes,
                                   title: str | None = None) -> dict[str, Any]:
    """Rueckwaertskompatibler Name (frueherer Funktionsname vor der
    Erweiterung um PDF/DOCX/XLSX/CSV/Bilder) -- duenner Wrapper um
    ingest_document_source()."""
    return ingest_document_source(
        tenant_id=tenant_id, uploaded_by=uploaded_by,
        filename=filename, content=content, title=title,
    )
