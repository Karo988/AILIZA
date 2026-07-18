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

T7-Import-Scan-Ausnahme (dokumentiert, PR-3b-Review): main.py enthaelt
einen einzigen weiteren direkten provider.generate()-Aufruf (Debug-
Provider-Test, /api/debug/provider-test). Das ist bewusst KEIN
Gate-Bypass in Produktion: die Route wird nur registriert, wenn
AILIZA_ENV != "production" -- in Produktion existiert der Endpoint
nicht (kein Fallback, kein Laufzeit-Check, sondern fehlende Route).
Beweis: tests/test_debug_provider_endpoint.py::
test_provider_debug_endpoint_not_registered_in_production.
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
    from ..governance.mirror_lint import einzelsignal_genuegt, run_mirror_lint
except ImportError:  # pragma: no cover
    from providers.gate_types import EgressOutcome, GateDiagnostic, Zweck
    from errors import AILIZAError
    from governance.mirror_lint import einzelsignal_genuegt, run_mirror_lint


# 1 Generate-Versuch + 1 Repair/Retry -- PR-2 kann dies um Modell-Eskalation
# erweitern, der Budget-Wert selbst bleibt hier fix fuer PR-1.
MAX_LLM_CALLS_PRO_ANFRAGE = 2

# PR-4: dritter Slot, ausschliesslich fuer den optionalen Stufe-3-Pruefer
# reserviert -- KEIN beliebiger dritter Generate-/Repair-Versuch.
MAX_TOTAL_CALLS_WITH_PRUEFER = 3

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


def _has_critical_signal_disagreement(findings) -> bool:
    """RED/BLACK-Uneinigkeit: eine zertifizierungskritische Kategorie (siehe
    mirror_lint.einzelsignal_genuegt) taucht in genau einem der beiden Texte
    auf, nicht in beiden UND nicht in keinem. Komfort-/Wording-Kategorien
    loesen NIE einen Pruefer-Call aus."""
    return any(
        einzelsignal_genuegt(f.category) and f.in_ingress != f.in_egress
        for f in findings
    )


_PRUEFER_CONFIRM_MARKERS = ("BESTAETIGT", "CONFIRMED")


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
        on_phase: Any = None,
    ) -> str:
        """on_phase (optional): Callable[[str], None], bekommt ausschliesslich
        Phasen-Codes ("GENERATE"/"REPAIR"/"PRUEFER"/"DELIVER"/"BLOCK") -- nie
        Prompt-/Antwort-Inhalte. Ohne on_phase aendert sich das Verhalten
        nicht (reines Beobachtungs-Hook, kein Pflichtparameter)."""
        zweck = zweck or Zweck.NUTZER_AUSGABE  # fail-closed default

        def _emit(phase: str) -> None:
            if on_phase is not None:
                on_phase(phase)

        attempts = 0
        repair_used = False
        saw_refusal = False
        current_messages = messages
        path_b_schema = require_schema and resolve_provider_path(provider) == "B"

        while attempts < MAX_LLM_CALLS_PRO_ANFRAGE:
            attempts += 1
            _emit("GENERATE" if attempts == 1 else "REPAIR")
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
            pruefer_flag = None
            if zweck == Zweck.NUTZER_AUSGABE and ingress_source is not None:
                findings = run_mirror_lint(ingress_source, result.text)
                blocking = [f for f in findings if f.is_blocking]

                # PR-4: Stufe-3-Pruefer -- NUR bei RED/BLACK-Signal-Uneinigkeit,
                # NUR fuer NUTZER_AUSGABE (also nie rekursiv aus einem
                # Pruefer-Call selbst heraus, der laueft mit Zweck.PRUEFER und
                # ueberspringt diesen ganzen Block), NUR wenn noch ein Slot
                # im 3er-Budget frei ist. Flag-only: das Ergebnis fliesst NIE
                # in "blocking" ein, die Policy-Entscheidung bleibt
                # deterministisch.
                if _has_critical_signal_disagreement(findings) and attempts < MAX_TOTAL_CALLS_WITH_PRUEFER:
                    _emit("PRUEFER")
                    attempts += 1
                    pruefer_flag = self._run_pruefer_call(provider, current_messages, context)

                if blocking:
                    _emit("BLOCK")
                    self.last_diagnostic = GateDiagnostic(
                        outcome=EgressOutcome.BLOCK_WITH_ALTERNATIVE.value,
                        zweck=zweck.value,
                        attempts=attempts,
                        candidate_status="VALID",
                        grund="MIRROR_LINT_BLOCK",
                        repair_used=repair_used,
                        pruefer_flag=pruefer_flag,
                    )
                    raise AILIZAError.from_code("policy_blocked")

            _emit("DELIVER")
            self.last_diagnostic = GateDiagnostic(
                outcome=EgressOutcome.DELIVER.value,
                zweck=zweck.value,
                attempts=attempts,
                candidate_status="VALID",
                repair_used=repair_used,
                pruefer_flag=pruefer_flag,
            )
            return result.text

        _emit("BLOCK")
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

    def _run_pruefer_call(self, provider: Any, messages: list[dict[str, Any]], context: Any) -> str:
        """Stufe-3-Pruefer: EIN best-effort Zusatz-Call, liefert nur einen
        Code zurueck (nie den vollen Text als Diagnose). Wird ausschliesslich
        bei kritischer Signal-Uneinigkeit aufgerufen (siehe Aufrufstelle) und
        ist selbst nie rekursiv -- er nutzt provider.generate_with_meta()
        direkt, NICHT self.generate(..., zweck=Zweck.PRUEFER), also kann er
        keinen weiteren Pruefer-Call ausloesen."""
        try:
            result = provider.generate_with_meta(messages, context)
        except AILIZAError:
            return "PRUEFER_ERROR"
        text = (result.text or "").strip().upper()
        if any(marker in text for marker in _PRUEFER_CONFIRM_MARKERS):
            return "CONFIRMED"
        return "UNCLEAR"
