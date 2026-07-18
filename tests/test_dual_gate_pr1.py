"""Tests fuer Dual-Gate PR-1: Refusal-/Invalid-Netz am Provider-Chokepoint.

Deckt exakt den PR-1-Scope ab (siehe Karo-Freigabe):
- EgressOutcome / Zweck Enums
- GatedLLMClient als einziger Ort, an dem provider.generate_with_meta() aufgerufen wird
- Refusal-/Invalid-Erkennung ueber ProviderResult.stop_reason (providerneutral, keine
  Text-Heuristik auf die eigentliche Antwort)
- Budget-Cap (max. 1 Repair-Versuch)
- Rueckwaertskompatible reine Text-Rueckgabe fuer bestehende Aufrufer
- Zweck.INTERN / Zweck.PRUEFER ueberspringen nur Egress-Enforcement, nicht den Client
- Gate-Diagnosekapsel: nur Codes, keine Inhalte
- Import-Scan (T7): kein Modul ausserhalb der Allowlist ruft Provider-SDKs/-Generate direkt auf

Keine echten API-Calls -- alle Provider sind Fakes.
"""
from __future__ import annotations

import ast
import os
from pathlib import Path

os.environ.setdefault("AILIZA_SECRET_KEY", "test-secret-key-minimum-32-chars-ok")

import pytest

from apps.backend.providers.gate_types import (
    EgressOutcome,
    GateDiagnostic,
    LLMResult,
    ProviderResult,
    Zweck,
)
from apps.backend.providers.gated_client import GatedLLMClient
from apps.backend.errors import AILIZAError


class _FakeProvider:
    """Fake-Provider, der ProviderResult liefert -- keine echten API-Calls."""

    provider_id = "fake"

    def __init__(self, results):
        # Liste von ProviderResult, ein Eintrag pro Aufruf (für Retry-Tests).
        self._results = list(results)
        self.calls = 0

    def generate_with_meta(self, messages, context=None):
        self.calls += 1
        if not self._results:
            raise AssertionError("FakeProvider: keine weiteren Ergebnisse konfiguriert")
        result = self._results.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


# ---------------------------------------------------------------------------
# T1: EgressOutcome hat exakt 3 Werte
# ---------------------------------------------------------------------------

def test_egress_outcome_has_exactly_three_values():
    values = {o.value for o in EgressOutcome}
    assert values == {"DELIVER", "DELIVER_AFTER_CONFIRM", "BLOCK_WITH_ALTERNATIVE"}


# ---------------------------------------------------------------------------
# T2: GatedLLMClient-Ergebnis mappt immer auf einen der 3 EgressOutcome-Werte
# ---------------------------------------------------------------------------

def test_gated_client_result_always_maps_to_outcome():
    provider = _FakeProvider([ProviderResult(text="Antwort ok", stop_reason="end_turn")])
    client = GatedLLMClient()
    text = client.generate(provider, [{"role": "user", "content": "hallo"}])
    assert text == "Antwort ok"
    assert client.last_diagnostic.outcome in {o.value for o in EgressOutcome}


# ---------------------------------------------------------------------------
# T3: Fehlender Zweck -> fail-closed default NUTZER_AUSGABE
# ---------------------------------------------------------------------------

def test_missing_zweck_defaults_to_nutzer_ausgabe():
    provider = _FakeProvider([ProviderResult(text="ok", stop_reason="end_turn")])
    client = GatedLLMClient()
    client.generate(provider, [{"role": "user", "content": "x"}])
    assert client.last_diagnostic.zweck == Zweck.NUTZER_AUSGABE.value


# ---------------------------------------------------------------------------
# T4: gueltiger Kandidat wird ausgeliefert (DELIVER)
# ---------------------------------------------------------------------------

def test_t4a_valid_candidate_delivers():
    provider = _FakeProvider([ProviderResult(text="Hier ist Ihr Entwurf.", stop_reason="end_turn")])
    client = GatedLLMClient()
    text = client.generate(provider, [{"role": "user", "content": "x"}], zweck=Zweck.NUTZER_AUSGABE)
    assert text == "Hier ist Ihr Entwurf."
    assert client.last_diagnostic.outcome == EgressOutcome.DELIVER.value
    assert client.last_diagnostic.candidate_status == "VALID"
    assert provider.calls == 1


# ---------------------------------------------------------------------------
# T5: JSON-Bergung -- Fenced-JSON wird ohne weiteren Call extrahiert
# ---------------------------------------------------------------------------

def test_json_recovery_extracts_fenced_json_without_extra_call():
    from apps.backend.providers.gated_client import recover_json

    raw = "Hier ist das Ergebnis:\n```json\n{\"draft\": \"Text\", \"risk_flags\": []}\n```\n"
    recovered = recover_json(raw)
    assert recovered == {"draft": "Text", "risk_flags": []}


# ---------------------------------------------------------------------------
# T6: Invalider Kandidat -> genau ein Repair-Versuch, dann Auslieferung
# ---------------------------------------------------------------------------

def test_invalid_json_triggers_one_repair_then_delivers():
    provider = _FakeProvider([
        ProviderResult(text="", stop_reason="end_turn"),  # leer -> INVALID_CANDIDATE
        ProviderResult(text="Zweiter Versuch: Antwort.", stop_reason="end_turn"),
    ])
    client = GatedLLMClient()
    text = client.generate(provider, [{"role": "user", "content": "x"}])
    assert text == "Zweiter Versuch: Antwort."
    assert provider.calls == 2
    assert client.last_diagnostic.attempts == 2
    assert client.last_diagnostic.repair_used is True


# ---------------------------------------------------------------------------
# T7 (fachlich T4c): Ablehnung -- Budget erschoepft -> Block, NIE Roh-Refusal-Text
# ---------------------------------------------------------------------------

def test_t4c_refusal_exhausted_blocks_never_raw_text():
    provider = _FakeProvider([
        ProviderResult(text="Ich kann das nicht bearbeiten.", stop_reason="refusal"),
        ProviderResult(text="Ich lehne dies weiterhin ab.", stop_reason="refusal"),
    ])
    client = GatedLLMClient()
    with pytest.raises(AILIZAError) as exc_info:
        client.generate(provider, [{"role": "user", "content": "x"}])
    # Die rohe Provider-Ablehnung darf niemals im Fehler landen.
    assert "Ich kann das nicht" not in str(exc_info.value)
    assert "Ich lehne dies" not in str(exc_info.value)
    assert client.last_diagnostic.outcome == EgressOutcome.BLOCK_WITH_ALTERNATIVE.value
    assert client.last_diagnostic.raw_refusal_suppressed is True


# ---------------------------------------------------------------------------
# T8: Budget ist gedeckelt (max. MAX_LLM_CALLS_PRO_ANFRAGE Aufrufe)
# ---------------------------------------------------------------------------

def test_refusal_retry_budget_is_capped():
    from apps.backend.providers.gated_client import MAX_LLM_CALLS_PRO_ANFRAGE

    assert MAX_LLM_CALLS_PRO_ANFRAGE == 2  # 1 Generate + 1 Repair/Retry fuer PR-1

    provider = _FakeProvider([
        ProviderResult(text="", stop_reason="refusal"),
        ProviderResult(text="", stop_reason="refusal"),
        ProviderResult(text="wuerde nie ankommen", stop_reason="end_turn"),
    ])
    client = GatedLLMClient()
    with pytest.raises(AILIZAError):
        client.generate(provider, [{"role": "user", "content": "x"}])
    assert provider.calls == MAX_LLM_CALLS_PRO_ANFRAGE


# ---------------------------------------------------------------------------
# T9: Zweck.INTERN ueberspringt Egress-Enforcement, nutzt aber GatedLLMClient
# ---------------------------------------------------------------------------

def test_internal_zweck_skips_egress_enforcement_but_uses_gated_client():
    provider = _FakeProvider([ProviderResult(text="interner Test-Output", stop_reason="end_turn")])
    client = GatedLLMClient()
    text = client.generate(provider, [{"role": "user", "content": "x"}], zweck=Zweck.INTERN)
    assert text == "interner Test-Output"
    assert client.last_diagnostic.zweck == Zweck.INTERN.value
    # Refusal-/Invalid-Schutz bleibt trotzdem aktiv (Client-Bypass verboten):
    provider2 = _FakeProvider([
        ProviderResult(text="", stop_reason="refusal"),
        ProviderResult(text="", stop_reason="refusal"),
    ])
    with pytest.raises(AILIZAError):
        client.generate(provider2, [{"role": "user", "content": "x"}], zweck=Zweck.INTERN)


# ---------------------------------------------------------------------------
# T10: Zweck.PRUEFER ueberspringt Egress-Enforcement (kein echter Pruefer in PR-1)
# ---------------------------------------------------------------------------

def test_pruefer_zweck_skips_egress_enforcement():
    provider = _FakeProvider([ProviderResult(text="Pruef-Ergebnis", stop_reason="end_turn")])
    client = GatedLLMClient()
    text = client.generate(provider, [{"role": "user", "content": "x"}], zweck=Zweck.PRUEFER)
    assert text == "Pruef-Ergebnis"
    assert client.last_diagnostic.zweck == Zweck.PRUEFER.value


# ---------------------------------------------------------------------------
# T11: Rueckwaertskompatibilitaet -- bestehende Aufrufer bekommen reinen Text
# ---------------------------------------------------------------------------

def test_gated_client_returns_plain_text_for_existing_callers():
    provider = _FakeProvider([ProviderResult(text="einfacher Text", stop_reason="end_turn")])
    client = GatedLLMClient()
    result = client.generate(provider, [{"role": "user", "content": "x"}])
    assert isinstance(result, str)
    assert result == "einfacher Text"


# ---------------------------------------------------------------------------
# T12/T13: Import-Scan -- kein Modul ausserhalb der Allowlist importiert
# Provider-SDKs oder ruft provider.generate()/generate_with_meta() direkt auf.
# ---------------------------------------------------------------------------

_PROVIDERS_DIR = Path(__file__).resolve().parents[1] / "apps" / "backend" / "providers"
_ALLOWLIST = {
    "orchestrator.py",
    "gated_client.py",
    "anthropic_provider.py",
    "groq_provider.py",
    "openai_provider.py",
    "openrouter_provider.py",
    "base.py",
    "provider_profiles.py",
    "__init__.py",
    "gate_types.py",
}
_PROVIDER_SDK_MODULES = {"anthropic", "groq", "openai"}


def test_no_module_outside_adapters_imports_provider_sdk_or_endpoint():
    backend_dir = _PROVIDERS_DIR.parent
    offenders = []
    for path in backend_dir.rglob("*.py"):
        if _PROVIDERS_DIR in path.parents and path.name in _ALLOWLIST:
            continue
        if "tests" in path.parts:
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.split(".")[0] in _PROVIDER_SDK_MODULES:
                        offenders.append(f"{path}: import {alias.name}")
            elif isinstance(node, ast.ImportFrom):
                if node.module and node.module.split(".")[0] in _PROVIDER_SDK_MODULES:
                    offenders.append(f"{path}: from {node.module} import ...")
    assert offenders == []


def test_no_module_calls_provider_generate_directly_outside_allowlist():
    backend_dir = _PROVIDERS_DIR.parent
    offenders = []
    for path in backend_dir.rglob("*.py"):
        if _PROVIDERS_DIR in path.parents and path.name in _ALLOWLIST:
            continue
        if "tests" in path.parts:
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                if node.func.attr in {"generate_with_meta"}:
                    offenders.append(f"{path}: .{node.func.attr}(...) direkt aufgerufen")
    assert offenders == []


# ---------------------------------------------------------------------------
# T14: Gate-Diagnosekapsel enthaelt nur Codes, keine Inhalte/PII
# ---------------------------------------------------------------------------

def test_gate_diagnostic_contains_only_codes_no_prompt_or_content():
    provider = _FakeProvider([ProviderResult(text="Vertraulicher Inhalt XYZ", stop_reason="end_turn")])
    client = GatedLLMClient()
    client.generate(provider, [{"role": "user", "content": "geheime Eingabe ABC"}])
    diag = client.last_diagnostic
    assert isinstance(diag, GateDiagnostic)
    for field_name in ("outcome", "zweck", "candidate_status", "grund"):
        value = getattr(diag, field_name, None)
        if value is not None:
            assert "Vertraulicher Inhalt" not in str(value)
            assert "geheime Eingabe" not in str(value)
    assert isinstance(diag.attempts, int)
    assert isinstance(diag.repair_used, bool)
    assert isinstance(diag.degraded, bool)
    assert isinstance(diag.raw_refusal_suppressed, bool)
