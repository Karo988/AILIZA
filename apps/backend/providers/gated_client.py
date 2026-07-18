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

# ── PR-2: Provider-Pfad-Klassifikation ───────────────────────────────────────
# Pfad A = natives Schema + strukturiertes Refusal-Signal (aktuell nur
# Anthropic ueber generate_with_meta()). ALLES andere -- auch unbekannte
# oder kuenftige Provider -- faellt automatisch auf Pfad B (prompt-
# eingebettetes Schema + lokale Validierung). Das ist die fail-safe
# Generalisierung: ein neuer Provider ist nie versehentlich "zu sicher"
# eingestuft, nur hoechstens zu vorsichtig.
_PATH_A_PROVIDER_IDS = {"anthropic"}

_SCHEMA_FEW_SHOT_HINT = (
    "\n\nWICHTIG: Antworte ausschliesslich mit einem JSON-Objekt, kein Text "
    "davor oder danach:\n"
    '{"draft": "<Text>", "risk_flags": [], "compliance_note": ""}\n'
    "Beispiel:\n"
    '{"draft": "Beispieltext", "risk_flags": [], "compliance_note": ""}'
)

_PLACEHOLDER_PATTERN = re.compile(r"\[[^\[\]]+\]")

try:
    from .gate_types import EgressOutcome, GateDiagnostic, Zweck
    from ..errors import AILIZAError
    from ..governance.mirror_lint import run_mirror_lint
except ImportError:  # pragma: no cover
    from providers.gate_types import EgressOutcome, GateDiagnostic, Zweck
    from errors import AILIZAError
    from governance.mirror_lint import run_mirror_lint


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


def resolve_provider_path(provider: Any) -> str:
    """'A' fuer natives Schema (aktuell nur Anthropic), sonst immer 'B' --
    auch fuer unbekannte/kuenftige Provider (fail-safe Default)."""
    pid = getattr(provider, "provider_id", "")
    return "A" if pid in _PATH_A_PROVIDER_IDS else "B"


def inject_schema_few_shot(messages: list[dict[str, Any]], provider: Any) -> list[dict[str, Any]]:
    """Haengt fuer Pfad-B-Provider ein Few-Shot-Schema-Beispiel an die
    System-Nachricht an (Pfad-B-Haertung Stufe 3). Pfad-A-Provider (natives
    Schema) bleiben unveraendert."""
    if resolve_provider_path(provider) != "B":
        return messages
    out = [dict(m) for m in messages]
    for m in out:
        if m.get("role") == "system":
            m["content"] = m.get("content", "") + _SCHEMA_FEW_SHOT_HINT
            return out
    out.insert(0, {"role": "system", "content": _SCHEMA_FEW_SHOT_HINT.strip()})
    return out


def check_placeholder_integrity(source_text: str, candidate_text: str) -> bool:
    """Stufe-1-PII-Integritaet: die Anzahl der [Platzhalter] im Kandidaten darf
    gegenueber dem Ursprungstext nicht sinken -- der Generator darf keine
    bereits geschwaerzten Platzhalter stillschweigend verschlucken."""
    source_count = len(_PLACEHOLDER_PATTERN.findall(source_text or ""))
    candidate_count = len(_PLACEHOLDER_PATTERN.findall(candidate_text or ""))
    return candidate_count >= source_count


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
        require_schema: bool = False,
        ingress_source: str | None = None,
    ) -> str:
        zweck = zweck or Zweck.NUTZER_AUSGABE  # fail-closed default

        attempts = 0
        repair_used = False
        saw_refusal = False
        current_messages = messages
        path_b_schema = require_schema and resolve_provider_path(provider) == "B"

        while attempts < MAX_LLM_CALLS_PRO_ANFRAGE:
            attempts += 1
            try:
                result = provider.generate_with_meta(current_messages, context)
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

            if path_b_schema and recover_json(result.text) is None:
                if attempts >= MAX_LLM_CALLS_PRO_ANFRAGE:
                    # Degradations-Leiter: ein Formatproblem blockiert NIE,
                    # sondern liefert den Klartext-Vertrag aus. Kein Nutzer
                    # wird fuer Formatprobleme eines Modells bestraft.
                    self.last_diagnostic = GateDiagnostic(
                        outcome=EgressOutcome.DELIVER.value,
                        zweck=zweck.value,
                        attempts=attempts,
                        candidate_status="VALID",
                        grund="SCHEMA_DEGRADED",
                        repair_used=repair_used,
                        degraded=True,
                    )
                    return result.text
                repair_used = True
                current_messages = inject_schema_few_shot(messages, provider)
                continue

            # Egress-Enforcement (PR-3b): nur fuer NUTZER_AUSGABE und nur,
            # wenn eine Ingress-Quelle zum Vergleich vorliegt. INTERN/PRUEFER
            # ueberspringen dies bewusst (kein Client-Bypass -- Refusal-/
            # Invalid-Netz oben bleibt fuer sie unveraendert aktiv).
            if zweck == Zweck.NUTZER_AUSGABE and ingress_source is not None:
                findings = run_mirror_lint(ingress_source, result.text)
                blocking = [f for f in findings if f.is_blocking]
                if blocking:
                    self.last_diagnostic = GateDiagnostic(
                        outcome=EgressOutcome.BLOCK_WITH_ALTERNATIVE.value,
                        zweck=zweck.value,
                        attempts=attempts,
                        candidate_status="VALID",
                        grund="MIRROR_LINT_BLOCK",
                        repair_used=repair_used,
                    )
                    raise AILIZAError.from_code("policy_blocked")

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
