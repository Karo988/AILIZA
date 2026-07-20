"""Tests fuer Dual-Gate PR-2: Stufe-1-PII-Integritaet + Pfad-B-Haertung.

Scope (Karo-Freigabe "ok, fuer alle auch neue LLM"):
- Provider-Pfad-Klassifikation (A = natives Schema, B = alles andere --
  auch unbekannte/kuenftige Provider faellt automatisch auf B, nie auf A)
- Few-Shot-Schema-Hinweis nur fuer Pfad-B-Provider
- Stufe-1-PII-Integritaet: Platzhalter-Anzahl darf im Kandidaten nicht sinken
- Degradations-Leiter: Formatprobleme fuehren NIE zum Blockieren, sondern zur
  Auslieferung als Klartext-Vertrag (degraded=True in der Diagnosekapsel)
- Kein neuer Dependency

Keine echten API-Calls -- alle Provider sind Fakes.
"""
from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("AILIZA_SECRET_KEY", "test-secret-key-minimum-32-chars-ok")

import pytest

from apps.backend.providers.gate_types import EgressOutcome, ProviderResult, Zweck
from apps.backend.providers.gated_client import (
    GatedLLMClient,
    check_placeholder_integrity,
    inject_schema_few_shot,
    recover_json,
    resolve_provider_path,
)
from apps.backend.providers.anthropic_provider import AnthropicProvider
from apps.backend.providers.groq_provider import GroqProvider
from apps.backend.errors import AILIZAError


class _FakeProvider:
    provider_id = "future_llm_xyz"  # bewusst unbekannt -- steht fuer ein kuenftiges Modell

    def __init__(self, results):
        self._results = list(results)
        self.calls = 0
        self.seen_messages = []

    def generate_with_meta(self, messages, context=None):
        self.calls += 1
        self.seen_messages.append(messages)
        result = self._results.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


# ---------------------------------------------------------------------------
# T1: Groq deklariert JSON-Modus-Faehigkeit (Pfad B, response_format optional)
# ---------------------------------------------------------------------------

def test_json_mode_enabled_for_groq_when_supported():
    provider = GroqProvider()
    assert provider.supports_json_mode is True
    assert resolve_provider_path(provider) == "B"


# ---------------------------------------------------------------------------
# T2: Ohne JSON-Modus faellt die Bergung auf recover_json() zurueck
# ---------------------------------------------------------------------------

def test_json_mode_absent_falls_back_to_recover_json():
    raw = "Text drumherum ```json\n{\"draft\": \"x\", \"risk_flags\": []}\n``` Ende"
    parsed = recover_json(raw)
    assert parsed == {"draft": "x", "risk_flags": []}


# ---------------------------------------------------------------------------
# T3: Few-Shot-Beispiel nur fuer Pfad-B-Provider injiziert -- auch fuer
# unbekannte/kuenftige Provider (fail-safe Generalisierung)
# ---------------------------------------------------------------------------

def test_few_shot_example_injected_only_for_path_b_providers():
    messages = [{"role": "system", "content": "Basisregeln."}, {"role": "user", "content": "hi"}]
    future_provider = _FakeProvider([])
    out = inject_schema_few_shot(messages, future_provider)
    assert "draft" in out[0]["content"]
    assert "risk_flags" in out[0]["content"]

    anthropic_provider = AnthropicProvider()
    out_a = inject_schema_few_shot(messages, anthropic_provider)
    assert out_a == messages  # Pfad A: unveraendert, natives Schema uebernimmt das


# ---------------------------------------------------------------------------
# T4: Stufe-1-PII-Integritaet -- Platzhalter-Anzahl darf nicht sinken
# ---------------------------------------------------------------------------

def test_pii_integrity_stufe1_placeholder_count_preserved_in_candidate():
    source = "Sehr geehrte/r [Name], Ihre Anfrage zu [IBAN] wurde erfasst."
    good_candidate = "Sehr geehrte/r [Name], vielen Dank fuer [IBAN]."
    bad_candidate = "Vielen Dank fuer Ihre Anfrage."  # Platzhalter verschluckt

    assert check_placeholder_integrity(source, good_candidate) is True
    assert check_placeholder_integrity(source, bad_candidate) is False


# ---------------------------------------------------------------------------
# T5: Degradations-Leiter -- Formatproblem blockiert NIE, sondern liefert
# den Klartext-Vertrag aus (degraded=True), auch bei unbekannten Providern
# ---------------------------------------------------------------------------

def test_degradation_ladder_falls_back_to_plain_text_contract_not_block():
    provider = _FakeProvider([
        ProviderResult(text="Kein JSON, nur Prosa-Entwurf.", stop_reason="end_turn"),
        ProviderResult(text="Immer noch kein JSON, nur Prosa.", stop_reason="end_turn"),
    ])
    client = GatedLLMClient()
    text = client.generate(
        provider, [{"role": "user", "content": "x"}], require_schema=True,
    )
    assert text == "Immer noch kein JSON, nur Prosa."
    assert client.last_diagnostic.outcome == EgressOutcome.DELIVER.value
    assert client.last_diagnostic.degraded is True
    assert client.last_diagnostic.grund == "SCHEMA_DEGRADED"
    # Few-Shot-Hinweis wurde beim Repair-Versuch tatsaechlich mitgeschickt:
    assert any("draft" in str(m) for m in provider.seen_messages[1])


# ---------------------------------------------------------------------------
# T6: Anthropic (Pfad A) bekommt keine Prompt-Schema-Injektion
# ---------------------------------------------------------------------------

def test_anthropic_uses_path_a_no_prompt_schema_injection():
    provider = AnthropicProvider()
    assert resolve_provider_path(provider) == "A"
    messages = [{"role": "user", "content": "x"}]
    assert inject_schema_few_shot(messages, provider) == messages


# ---------------------------------------------------------------------------
# T7: Kein neuer Dependency fuer PR-2
# ---------------------------------------------------------------------------

_BASELINE_REQUIREMENTS = {
    "fastapi==0.111.0", "uvicorn==0.29.0", "sqlalchemy==2.0.30", "pydantic==2.7.1",
    "requests==2.31.0", "beautifulsoup4==4.12.3", "python-dotenv==1.0.1",
    "slowapi==0.1.9", "apscheduler==3.10.4", "tavily-python==0.3.3",
    "anthropic>=0.40.0", "pyyaml>=6.0", "bcrypt==4.1.3",
    "python-multipart==0.0.9", "cryptography>=42.0.0",
    # Neon/Postgres-Persistenz (bereits in main via requirements-core.txt)
    "psycopg[binary]>=3.1",
}


def test_no_new_dependency_added():
    req_path = Path(__file__).resolve().parents[1] / "apps" / "backend" / "requirements-core.txt"
    lines = {
        line.strip() for line in req_path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    }
    assert lines == _BASELINE_REQUIREMENTS
