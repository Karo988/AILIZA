"""
AILIZA Redaction
================
Entfernt Secrets vollstaendig und ersetzt PII durch fluechtige Platzhalter.

WICHTIG:
- Secrets werden NIE wiederhergestellt (komplett entfernt).
- Das Mapping (Platzhalter -> Typ) wird NICHT persistiert, nur fluechtig im RAM.
- Im replacements-Mapping steht NIEMALS der Originalwert, nur der Typ.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .data_governance import (
    ClassificationResult,
    _CARD_PATTERN,
    _EMAIL_PATTERN,
    _IBAN_PATTERN,
    _IP_PATTERN,
    _PHONE_PATTERN,
    _SECRET_PATTERNS,
)


@dataclass
class RedactionResult:
    redacted_text: str
    replacements: dict[str, str] = field(default_factory=dict)  # placeholder -> type
    secrets_blocked: int = 0
    pii_replaced: int = 0
    redaction_applied: bool = False


def _replace_sequential(
    text: str,
    pattern: re.Pattern,
    label: str,
    replacements: dict[str, str],
) -> tuple[str, int]:
    counter = {"n": 0}
    seen: dict[str, str] = {}

    def _sub(match: re.Match) -> str:
        original = match.group()
        if original in seen:
            return seen[original]
        counter["n"] += 1
        placeholder = f"[{label}_{counter['n']}]"
        seen[original] = placeholder
        replacements[placeholder] = label.lower()  # nur Typ, kein Originalwert
        return placeholder

    new_text = pattern.sub(_sub, text)
    return new_text, counter["n"]


def redact(text: str, classification: ClassificationResult | None = None) -> RedactionResult:
    if text is None:
        text = ""
    replacements: dict[str, str] = {}
    secrets_blocked = 0
    pii_replaced = 0

    # 1. Secrets vollstaendig entfernen
    for _name, pattern in _SECRET_PATTERNS:
        text, count = pattern.subn("[SECRET_REMOVED]", text)
        secrets_blocked += count

    # 2. PII durch Platzhalter ersetzen
    text, n = _replace_sequential(text, _EMAIL_PATTERN, "EMAIL", replacements)
    pii_replaced += n
    text, n = _replace_sequential(text, _IBAN_PATTERN, "IBAN", replacements)
    pii_replaced += n
    text, n = _replace_sequential(text, _PHONE_PATTERN, "PHONE", replacements)
    pii_replaced += n
    text, n = _replace_sequential(text, _CARD_PATTERN, "CARD", replacements)
    pii_replaced += n
    text, n = _replace_sequential(text, _IP_PATTERN, "IP", replacements)
    pii_replaced += n

    applied = secrets_blocked > 0 or pii_replaced > 0
    return RedactionResult(
        redacted_text=text,
        replacements=replacements,
        secrets_blocked=secrets_blocked,
        pii_replaced=pii_replaced,
        redaction_applied=applied,
    )
