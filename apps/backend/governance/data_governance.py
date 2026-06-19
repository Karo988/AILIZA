"""
AILIZA Data Governance — Klassifikation
=======================================
Pattern-basierte Datenklassifikation. KEIN LLM beteiligt.

Fail-closed: Bei jeder Exception wird CREDENTIALS + needs_review=True
zurueckgegeben, damit im Zweifel nicht extern gesendet wird.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum


class DataClass(str, Enum):
    PUBLIC = "public"
    INTERNAL = "internal"
    CONFIDENTIAL = "confidential"
    PERSONAL_DATA = "personal_data"
    SPECIAL_CATEGORY = "special_category"
    CREDENTIALS = "credentials"
    FINANCIAL = "financial"
    HR = "hr"
    LEGAL = "legal"
    INTELLECTUAL_PROPERTY = "intellectual_property"
    SECURITY_SENSITIVE = "security_sensitive"


class DataTarget(str, Enum):
    RAM = "ram"
    SESSION = "session"
    AUDIT = "audit"
    FILE_STORAGE = "file_storage"
    MEMORY = "memory"
    VECTOR_DB = "vector_db"
    EXTERNAL_LLM = "external_llm"
    CRM = "crm"
    EMAIL = "email"
    ADMIN_UI = "admin_ui"


# Reihenfolge von niedrig nach hoch. Strengste (hoechste) Klasse gewinnt.
RISK_ORDER: list[DataClass] = [
    DataClass.PUBLIC,
    DataClass.INTERNAL,
    DataClass.CONFIDENTIAL,
    DataClass.INTELLECTUAL_PROPERTY,
    DataClass.PERSONAL_DATA,
    DataClass.FINANCIAL,
    DataClass.HR,
    DataClass.LEGAL,
    DataClass.SECURITY_SENSITIVE,
    DataClass.SPECIAL_CATEGORY,
    DataClass.CREDENTIALS,
]


@dataclass
class ClassificationResult:
    data_classes: list[DataClass] = field(default_factory=list)
    highest_risk_class: DataClass = DataClass.PUBLIC
    confidence: float = 1.0
    matched_rules: list[str] = field(default_factory=list)
    needs_review: bool = False


# ── Pattern ───────────────────────────────────────────────────────────────
_SECRET_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("api_key_openai", re.compile(r"\bsk-[A-Za-z0-9]{16,}\b")),
    ("api_key_groq", re.compile(r"\bgsk_[A-Za-z0-9]{16,}\b")),
    ("bearer_token", re.compile(r"\bBearer\s+[A-Za-z0-9._\-]{12,}")),
    ("google_api_key", re.compile(r"\bAIza[0-9A-Za-z._\-]{20,}\b")),
    ("github_token", re.compile(r"\bghp_[A-Za-z0-9]{16,}\b")),
    ("secret_assignment", re.compile(r"\b(password|passwd|token|api[_-]?key|secret)\s*[=:]\s*\S+", re.I)),
]

_EMAIL_PATTERN = re.compile(
    r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b"
)
# Deutsche Telefonformate (grob): +49..., 0049..., 0XXX...
_PHONE_PATTERN = re.compile(
    r"(?:(?:\+49|0049)[\s\-/]?|\b0)(?:\d[\s\-/]?){6,14}\d"
)
_IBAN_PATTERN = re.compile(r"\bDE\d{20}\b")
# Kreditkarte (grob): 13-16 Ziffern, evtl. mit Trennern
_CARD_PATTERN = re.compile(r"\b(?:\d[ \-]?){13,16}\b")
_IP_PATTERN = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")


def classify(text: str) -> ClassificationResult:
    """Klassifiziert einen Text pattern-basiert. Fail-closed bei Fehler."""
    try:
        if text is None:
            text = ""
        matched: list[str] = []
        classes: set[DataClass] = set()

        for name, pattern in _SECRET_PATTERNS:
            if pattern.search(text):
                matched.append(name)
                classes.add(DataClass.CREDENTIALS)

        if _EMAIL_PATTERN.search(text):
            matched.append("email")
            classes.add(DataClass.PERSONAL_DATA)
        if _PHONE_PATTERN.search(text):
            matched.append("phone")
            classes.add(DataClass.PERSONAL_DATA)
        if _IP_PATTERN.search(text):
            matched.append("ip_address")
            classes.add(DataClass.PERSONAL_DATA)
        if _IBAN_PATTERN.search(text):
            matched.append("iban")
            classes.add(DataClass.FINANCIAL)
        if _CARD_PATTERN.search(text) and not _IBAN_PATTERN.search(text):
            # nur als Karte werten wenn nicht bereits IBAN (Ueberlappung vermeiden)
            digits = re.sub(r"\D", "", _CARD_PATTERN.search(text).group())
            if 13 <= len(digits) <= 16:
                matched.append("credit_card")
                classes.add(DataClass.FINANCIAL)

        if not classes:
            classes.add(DataClass.PUBLIC)

        ordered = sorted(classes, key=lambda c: RISK_ORDER.index(c))
        highest = ordered[-1]
        needs_review = highest in {DataClass.CREDENTIALS, DataClass.SPECIAL_CATEGORY}

        return ClassificationResult(
            data_classes=ordered,
            highest_risk_class=highest,
            confidence=0.9 if matched else 0.6,
            matched_rules=matched,
            needs_review=needs_review,
        )
    except Exception:
        # Fail-closed
        return ClassificationResult(
            data_classes=[DataClass.CREDENTIALS],
            highest_risk_class=DataClass.CREDENTIALS,
            confidence=0.0,
            matched_rules=["classification_error"],
            needs_review=True,
        )
