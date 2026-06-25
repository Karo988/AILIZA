"""
PII Redactor — DSGVO Art. 5 Abs. 1 lit. c (Datenminimierung)

Entfernt erkannte personenbezogene Daten aus dem Text
bevor er an externe APIs oder LLMs weitergegeben wird.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .classifier import _PII_PATTERNS


@dataclass(frozen=True)
class RedactionResult:
    original_length: int
    redacted_text: str
    redacted_count: int
    redacted_categories: list[str] = field(default_factory=list)

    @property
    def was_redacted(self) -> bool:
        return self.redacted_count > 0


def redact(text: str) -> RedactionResult:
    """
    Ersetzt PII-Inhalte durch Platzhalter.

    Beispiel: "Max Müller, max@example.com" → "Max Müller, [E-Mail-Adresse]"
    """
    result = text
    count = 0
    categories: list[str] = []

    for label, pattern in _PII_PATTERNS:
        matches = pattern.findall(result)
        if matches:
            result = pattern.sub(f"[{label}]", result)
            count += len(matches)
            categories.append(label)

    return RedactionResult(
        original_length=len(text),
        redacted_text=result,
        redacted_count=count,
        redacted_categories=categories,
    )
