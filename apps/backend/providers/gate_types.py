"""
AILIZA Dual-Gate PR-1 -- Typen
==============================
EgressOutcome/Zweck/ProviderResult/LLMResult/GateDiagnostic fuer das
Refusal-/Invalid-Netz am Provider-Chokepoint (siehe orchestrator.py).

Kein Feld dieser Typen darf Prompt-Inhalte, Antwort-Inhalte oder PII
enthalten -- nur Status-Codes (Dual-Gate-Diagnosekapsel, Datensparsamkeit).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Literal


class Zweck(Enum):
    """Zweck eines LLM-Calls. Fehlender Zweck defaultet fail-closed auf NUTZER_AUSGABE."""

    NUTZER_AUSGABE = "NUTZER_AUSGABE"
    INTERN = "INTERN"
    PRUEFER = "PRUEFER"


class EgressOutcome(Enum):
    """Genau 3 Endzustaende -- ein 4. (rohe Ablehnung erreicht den Nutzer) ist ein Bug."""

    DELIVER = "DELIVER"
    DELIVER_AFTER_CONFIRM = "DELIVER_AFTER_CONFIRM"
    BLOCK_WITH_ALTERNATIVE = "BLOCK_WITH_ALTERNATIVE"


CandidateStatus = Literal["VALID", "INVALID_CANDIDATE", "PROVIDER_ERROR"]


@dataclass
class ProviderResult:
    """Rueckgabe eines Provider-Adapters mit Metadaten (statt reinem Text)."""

    text: str
    stop_reason: str | None = None


@dataclass
class GateDiagnostic:
    """Gate-Diagnosekapsel: nur Codes, keine Inhalte. Nicht persistiert, nicht im UI (PR-1)."""

    outcome: str
    zweck: str
    attempts: int
    candidate_status: CandidateStatus
    grund: str | None = None
    repair_used: bool = False
    degraded: bool = False
    raw_refusal_suppressed: bool = False


@dataclass
class LLMResult:
    status: CandidateStatus
    payload: str | None
    grund: str | None = None
    diagnostic: GateDiagnostic | None = None
