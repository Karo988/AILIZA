"""
Input Classifier — EU AI Act Art. 9 / DSGVO Art. 25

Klassifiziert den rohen User-Input VOR jedem Tool- oder LLM-Aufruf.
Ergebnis bestimmt: weiter | redact + weiter | approval_required | blocked
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class InputRiskLevel(str, Enum):
    LOW = "low"           # Weiter ohne Einschränkung
    MEDIUM = "medium"     # Weiter, aber mit Redaction
    HIGH = "high"         # Approval required
    BLOCKED = "blocked"   # Sofort stoppen


@dataclass(frozen=True)
class ClassificationResult:
    risk_level: InputRiskLevel
    pii_detected: bool
    requires_approval: bool
    blocked: bool
    reason: str
    # Nachricht in einfacher Sprache für den Nutzer
    user_message: str
    detected_categories: list[str] = field(default_factory=list)


# ── PII-Muster ────────────────────────────────────────────────────────────────

_PII_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("E-Mail-Adresse", re.compile(r"\b[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}\b")),
    ("Telefonnummer", re.compile(r"(?<!\w)(\+49|0049|0)[1-9]\d{1,14}(?!\d)")),
    ("IBAN", re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{4}\d{7}([A-Z0-9]?){0,16}\b")),
    ("Sozialversicherungsnummer", re.compile(r"\b\d{2}\s?\d{6}\s?[A-Z]\s?\d{3}\b")),
    ("Personalausweis/Reisepass", re.compile(r"\b[A-Z]{1,3}\d{6,9}\b")),
    ("IP-Adresse", re.compile(r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b")),
    ("Geburtsdatum", re.compile(r"\b\d{1,2}[.\-/]\d{1,2}[.\-/]\d{2,4}\b")),
]

# ── Risikothemen ──────────────────────────────────────────────────────────────

_HIGH_RISK_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("HR/Personalentscheidung", re.compile(
        r"\b(k[üu]ndigung|entlassung|bewerbung|einstellung|gehaltsverhandlung|abmahnung|arbeitszeugnis)\b", re.I
    )),
    ("Rechtliche Wirkung", re.compile(
        r"\b(vertrag|klage|rechtsstreit|anwalt|gericht|vollmacht|testament|erbschaft|schadensersatz)\b", re.I
    )),
    ("Finanzielle Wirkung", re.compile(
        r"\b(kredit|darlehen|bürgschaft|hypothek|insolvenz|pfändung|steuererkl[äa]rung)\b", re.I
    )),
    ("Gesundheit/Versicherung", re.compile(
        r"\b(diagnose|medikament|krankenhaus|krankenkasse|berufsunf[äa]higkeit|pflegegrad)\b", re.I
    )),
    ("Profiling/Bewertung", re.compile(
        r"\b(scoring|bonitätspr[üu]fung|schufa|risikobewertung|persönlichkeitsprofil)\b", re.I
    )),
]

_BLOCKED_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("Verbotene KI-Praktiken", re.compile(
        r"\b(manipulation|unterschwellig|unterbewusstsein|ausnutzen von schwächen|social.?engineering)\b", re.I
    )),
    ("Massen-Überwachung", re.compile(
        r"\b(massenüberwachung|biometrische.?erfassung|gesichtserkennung.{0,20}öffentlich)\b", re.I
    )),
]


def classify(task: str) -> ClassificationResult:
    """
    Klassifiziert den rohen User-Input.

    Reihenfolge: blocked → high → medium (PII) → low
    """
    detected: list[str] = []

    # 1. Sofort blockieren
    for label, pattern in _BLOCKED_PATTERNS:
        if pattern.search(task):
            detected.append(label)
            return ClassificationResult(
                risk_level=InputRiskLevel.BLOCKED,
                pii_detected=False,
                requires_approval=False,
                blocked=True,
                reason=f"Verbotene Praktik erkannt: {label}",
                user_message=(
                    "Diese Anfrage kann ich nicht bearbeiten. Sie enthält Inhalte, "
                    "die nach EU AI Act Art. 5 nicht zulässig sind."
                ),
                detected_categories=detected,
            )

    # 2. Approval required (Hochrisiko-Themen)
    high_risk_found: list[str] = []
    for label, pattern in _HIGH_RISK_PATTERNS:
        if pattern.search(task):
            high_risk_found.append(label)
            detected.append(label)

    # 3. PII-Erkennung
    pii_found: list[str] = []
    for label, pattern in _PII_PATTERNS:
        if pattern.search(task):
            pii_found.append(label)
            detected.append(label)

    if high_risk_found:
        topic = high_risk_found[0]
        return ClassificationResult(
            risk_level=InputRiskLevel.HIGH,
            pii_detected=bool(pii_found),
            requires_approval=True,
            blocked=False,
            reason=f"Freigabepflichtige Anfrage: {topic}",
            user_message=(
                f"Diese Anfrage betrifft ein sensibles Thema ({topic}). "
                "Sie wird als Entwurf vorbereitet und zur menschlichen Prüfung vorgelegt. "
                "Das Ergebnis gilt erst nach Freigabe als verbindlich."
            ),
            detected_categories=detected,
        )

    if pii_found:
        return ClassificationResult(
            risk_level=InputRiskLevel.MEDIUM,
            pii_detected=True,
            requires_approval=False,
            blocked=False,
            reason=f"Personenbezogene Daten erkannt: {', '.join(pii_found)}",
            user_message=(
                "Ich habe erkannt, dass Ihre Anfrage personenbezogene Daten enthält. "
                "Diese werden vor der Verarbeitung anonymisiert."
            ),
            detected_categories=detected,
        )

    return ClassificationResult(
        risk_level=InputRiskLevel.LOW,
        pii_detected=False,
        requires_approval=False,
        blocked=False,
        reason="Keine Risikofaktoren erkannt",
        user_message="",
        detected_categories=[],
    )
