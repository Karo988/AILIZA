"""
AILIZA Redaction
================
Entfernt Secrets vollstaendig und ersetzt PII durch fluechtige Platzhalter.
Nach der LLM-Antwort kann die lokale Reinsertion die Originaldaten wieder einsetzen.

WICHTIG:
- Secrets werden NIE wiederhergestellt (komplett entfernt).
- `replacements` (Platzhalter → Typ) ist log-sicher — kein Originalwert.
- `reinsertion_map` (Platzhalter → Originalwert) bleibt ausschliesslich im RAM.
  NIEMALS in Audit-Logs, Datenbank oder externe Systeme schreiben.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .data_governance import (
    ClassificationResult,
    DataClass,
    _CARD_PATTERN,
    _EMAIL_PATTERN,
    _IBAN_PATTERN,
    _IP_PATTERN,
    _PERSON_NAME_PATTERN,
    _PHONE_PATTERN,
    _REFERENCE_NUMBER_PATTERN,
    _SECRET_PATTERNS,
)

_BLOCK_CLASSES = {DataClass.SPECIAL_CATEGORY}


@dataclass
class RedactionResult:
    redacted_text: str
    replacements: dict[str, str] = field(default_factory=dict)   # placeholder → type (log-sicher)
    reinsertion_map: dict[str, str] = field(default_factory=dict) # placeholder → original (NUR RAM)
    secrets_blocked: int = 0
    pii_replaced: int = 0
    redaction_applied: bool = False


def _replace_sequential(
    text: str,
    pattern: re.Pattern,
    label: str,
    replacements: dict[str, str],
    reinsertion_map: dict[str, str],
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
        replacements[placeholder] = label.lower()       # log-sicher: nur Typ
        reinsertion_map[placeholder] = original         # RAM-only: Originalwert
        return placeholder

    new_text = pattern.sub(_sub, text)
    return new_text, counter["n"]


def _replace_name_group(
    text: str,
    pattern: re.Pattern,
    label: str,
    replacements: dict[str, str],
    reinsertion_map: dict[str, str],
) -> tuple[str, int]:
    """Ersetzt Gruppe 1 (Name) im Pattern; Keyword-Präfix bleibt erhalten."""
    counter = {"n": 0}
    seen: dict[str, str] = {}

    def _sub(match: re.Match) -> str:
        name = match.group(1)
        prefix = match.group(0)[: match.start(1) - match.start(0)]
        if name in seen:
            return prefix + seen[name]
        counter["n"] += 1
        placeholder = f"[{label}_{counter['n']}]"
        seen[name] = placeholder
        replacements[placeholder] = label.lower()
        reinsertion_map[placeholder] = name
        return prefix + placeholder

    new_text = pattern.sub(_sub, text)
    return new_text, counter["n"]


def reinsert(text: str, reinsertion_map: dict[str, str]) -> tuple[str, bool]:
    """
    Setzt Originalwerte aus reinsertion_map in den LLM-Antworttext ein.
    Gibt (reinserted_text, fully_reinserted) zurueck.
    fully_reinserted=False wenn Platzhalter in der Antwort vorkommen, die nicht
    im Map sind (z.B. weil das Modell den Platzhalter veraendert hat).
    """
    if not reinsertion_map or not text:
        return text, True

    result = text
    for placeholder, original in reinsertion_map.items():
        result = result.replace(placeholder, original)

    # Prüfen ob noch Platzhalter-Reste übrig sind
    remaining = re.findall(r"\[[A-Z]+_\d+\]", result)
    fully_reinserted = len(remaining) == 0
    return result, fully_reinserted


def redact(text: str, classification: ClassificationResult | None = None) -> RedactionResult:
    if text is None:
        text = ""
    replacements: dict[str, str] = {}
    reinsertion_map: dict[str, str] = {}
    secrets_blocked = 0
    pii_replaced = 0

    # 0. Besondere Kategorien (DSGVO Art. 9): gesamten Text blockieren
    if classification is not None:
        blocking = _BLOCK_CLASSES.intersection(classification.data_classes)
        if blocking:
            blocked_classes = "+".join(sorted(c.value for c in blocking))
            return RedactionResult(
                redacted_text=f"[BLOCKED:{blocked_classes}]",
                replacements={},
                reinsertion_map={},
                secrets_blocked=1,
                pii_replaced=0,
                redaction_applied=True,
            )

    # 1. Secrets vollstaendig entfernen (keine Reinsertion — bewusste Datenlöschung)
    for _name, pattern in _SECRET_PATTERNS:
        text, count = pattern.subn("[SECRET_REMOVED]", text)
        secrets_blocked += count

    # 2. PII durch Platzhalter ersetzen (mit lokaler Reinsertion-Map)
    # Personennamen zuerst (vor Email, damit "Max.Mueller@..." korrekt bleibt)
    text, n = _replace_name_group(text, _PERSON_NAME_PATTERN, "PERSON", replacements, reinsertion_map)
    pii_replaced += n
    text, n = _replace_sequential(text, _EMAIL_PATTERN, "EMAIL", replacements, reinsertion_map)
    pii_replaced += n
    text, n = _replace_sequential(text, _IBAN_PATTERN, "IBAN", replacements, reinsertion_map)
    pii_replaced += n
    text, n = _replace_sequential(text, _PHONE_PATTERN, "PHONE", replacements, reinsertion_map)
    pii_replaced += n
    text, n = _replace_sequential(text, _CARD_PATTERN, "CARD", replacements, reinsertion_map)
    pii_replaced += n
    text, n = _replace_sequential(text, _IP_PATTERN, "IP", replacements, reinsertion_map)
    pii_replaced += n
    text, n = _replace_sequential(text, _REFERENCE_NUMBER_PATTERN, "REFERENCE", replacements, reinsertion_map)
    pii_replaced += n

    applied = secrets_blocked > 0 or pii_replaced > 0
    return RedactionResult(
        redacted_text=text,
        replacements=replacements,
        reinsertion_map=reinsertion_map,
        secrets_blocked=secrets_blocked,
        pii_replaced=pii_replaced,
        redaction_applied=applied,
    )
