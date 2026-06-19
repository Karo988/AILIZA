"""
AILIZA Dokumenten-Workflow MVP
=============================
Kein Upload ohne Governance. Whitelist + Groessenpruefung + Klassifikation.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

try:
    from ..governance.data_governance import ClassificationResult, DataClass, classify
    from ..governance.data_matrix import PolicyDecision, check_data_target
    from ..governance.data_governance import DataTarget
except ImportError:  # pragma: no cover
    from governance.data_governance import ClassificationResult, DataClass, classify, DataTarget
    from governance.data_matrix import PolicyDecision, check_data_target


ALLOWED_EXTENSIONS = {".pdf", ".docx", ".xlsx", ".txt", ".csv"}
MAX_FILE_SIZE_MB = 10
_RETENTION_DAYS = int(os.getenv("AILIZA_DOCUMENT_RETENTION_DAYS", "30"))


@dataclass
class DocumentScanResult:
    allowed: bool
    file_type: str
    size_bytes: int
    classification: ClassificationResult
    decision: str  # allow / redact / approval_required / block
    reason: str
    expires_at: str


def _extract_text(ext: str, content: bytes) -> str:
    if ext in {".txt", ".csv"}:
        try:
            return content.decode("utf-8", errors="ignore")
        except Exception:
            return ""
    # PDF/DOCX/XLSX: Platzhalter im MVP (kein Heavy-Parsing erzwungen)
    return ""


def scan_document(filename: str, content: bytes) -> DocumentScanResult:
    ext = os.path.splitext(filename or "")[1].lower()
    size = len(content or b"")
    expires_at = (datetime.now(timezone.utc) + timedelta(days=_RETENTION_DAYS)).isoformat()

    # 1. Whitelist
    if ext not in ALLOWED_EXTENSIONS:
        return DocumentScanResult(
            allowed=False, file_type=ext or "unknown", size_bytes=size,
            classification=classify(""), decision="block",
            reason=f"Dateityp {ext or 'unbekannt'} ist nicht erlaubt.", expires_at=expires_at)

    # 2. Groesse
    if size > MAX_FILE_SIZE_MB * 1024 * 1024:
        return DocumentScanResult(
            allowed=False, file_type=ext, size_bytes=size,
            classification=classify(""), decision="block",
            reason=f"Datei groesser als {MAX_FILE_SIZE_MB} MB.", expires_at=expires_at)

    # 3. Text extrahieren
    text = _extract_text(ext, content)

    # 4. Klassifizieren
    classification = classify(text)

    # 5. Entscheidung (Ziel: externes LLM, ohne aktives ProviderProfile by default)
    decision = check_data_target(
        data_classes=classification.data_classes,
        target=DataTarget.EXTERNAL_LLM,
        redaction_applied=False,
        approval_given=False,
        provider_profile_active=False,
    )
    decision_map = {
        PolicyDecision.ALLOW: ("allow", "Dokument freigegeben."),
        PolicyDecision.ALLOW_WITH_NOTICE: ("allow", "Dokument freigegeben (mit Hinweis)."),
        PolicyDecision.REDACT_REQUIRED: ("redact", "Dokument muss anonymisiert werden."),
        PolicyDecision.APPROVAL_REQUIRED: ("approval_required", "Freigabe erforderlich."),
        PolicyDecision.BLOCK: ("block", "Dokument enthaelt nicht erlaubte Datenklassen."),
    }
    decision_str, reason = decision_map.get(decision, ("block", "Unklar — blockiert."))

    return DocumentScanResult(
        allowed=decision_str in {"allow", "redact", "approval_required"},
        file_type=ext, size_bytes=size, classification=classification,
        decision=decision_str, reason=reason, expires_at=expires_at)
