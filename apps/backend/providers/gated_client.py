"""
AILIZA Dual-Gate PR-1 -- GatedLLMClient
========================================
Sofort-Pflaster gegen rohe LLM-Ablehnungen/Textwaende und kaputte
Providerformate. Sitzt am echten Provider-Chokepoint (orchestrator.py,
provider.generate_with_meta()) -- jeder Provider, auch kuenftige, laeuft
hier durch.

PR-1-Scope (siehe Freigabe): nur Refusal-/Invalid-Netz, Budget-Cap,
rueckwaertskompatible Text-Rueckgabe, Gate-Diagnosekapsel (nur Codes).
Spiegel-Linting, Ingress-Tags, Stufe-3-Pruefer, Freigabe-Cockpit und
Pfad-B-JSON-Haertung fuer Groq/OpenAI-kompatible Provider sind NICHT
Teil von PR-1.
"""
from __future__ import annotations

import json
import re
from typing import Any

try:
    from .gate_types import EgressOutcome, GateDiagnostic, Zweck
    from ..errors import AILIZAError
except ImportError:  # pragma: no cover
    from providers.gate_types import EgressOutcome, GateDiagnostic, Zweck
    from errors import AILIZAError


# 1 Generate-Versuch + 1 Repair/Retry -- PR-2 kann dies um Modell-Eskalation
# erweitern, der Budget-Wert selbst bleibt hier fix fuer PR-1.
MAX_LLM_CALLS_PRO_ANFRAGE = 2

_REFUSAL_STOP_REASONS = {"refusal"}


def recover_json(raw: str) -> dict | None:
    """Deterministische JSON-Bergung (stdlib only): Markdown-Fences strippen,
    sonst per Brace-Balance das erste vollstaendige JSON-Objekt extrahieren."""
    if not raw:
        return None
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL)
    candidate = fenced.group(1) if fenced else None
    if candidate is None:
        start = raw.find("{")
        if start == -1:
            return None
        depth = 0
        for i in range(start, len(raw)):
            if raw[i] == "{":
                depth += 1
            elif raw[i] == "}":
                depth -= 1
                if depth == 0:
                    candidate = raw[start : i + 1]
                    break
        if candidate is None:
            return None
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        return None


class GatedLLMClient:
    """Einziger Ort, an dem provider.generate_with_meta() aufgerufen wird
    (siehe T7-Import-Scan-Allowlist). Zweck.INTERN/PRUEFER ueberspringen nur
    spaetere Egress-Enforcement (PR-3), niemals den Client selbst -- das
    Refusal-/Invalid-Netz gilt fuer ALLE Zwecke."""

    def __init__(self) -> None:
        self.last_diagnostic: GateDiagnostic | None = None

    def generate(
        self,
        provider: Any,
        messages: list[dict[str, Any]],
        context: Any = None,
        zweck: Zweck | None = None,
    ) -> str:
        zweck = zweck or Zweck.NUTZER_AUSGABE  # fail-closed default

        attempts = 0
        repair_used = False
        saw_refusal = False

        while attempts < MAX_LLM_CALLS_PRO_ANFRAGE:
            attempts += 1
            try:
                result = provider.generate_with_meta(messages, context)
            except AILIZAError:
                self.last_diagnostic = GateDiagnostic(
                    outcome=EgressOutcome.BLOCK_WITH_ALTERNATIVE.value,
                    zweck=zweck.value,
                    attempts=attempts,
                    candidate_status="PROVIDER_ERROR",
                    grund="PROVIDER_ERROR",
                )
                raise

            is_refusal = result.stop_reason in _REFUSAL_STOP_REASONS
            is_empty = not result.text or not result.text.strip()

            if is_refusal:
                saw_refusal = True

            if is_refusal or is_empty:
                if attempts >= MAX_LLM_CALLS_PRO_ANFRAGE:
                    break
                repair_used = True
                continue

            self.last_diagnostic = GateDiagnostic(
                outcome=EgressOutcome.DELIVER.value,
                zweck=zweck.value,
                attempts=attempts,
                candidate_status="VALID",
                repair_used=repair_used,
            )
            return result.text

        grund = "REFUSAL_STOP" if saw_refusal else "INVALID_CANDIDATE"
        self.last_diagnostic = GateDiagnostic(
            outcome=EgressOutcome.BLOCK_WITH_ALTERNATIVE.value,
            zweck=zweck.value,
            attempts=attempts,
            candidate_status="INVALID_CANDIDATE",
            grund=grund,
            repair_used=repair_used,
            raw_refusal_suppressed=saw_refusal,
        )
        raise AILIZAError.from_code("all_providers_failed")
