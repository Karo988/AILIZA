"""Tests fuer Dual-Gate PR-3b: Verdrahtung von Spiegel-Linting (PR-3) in den
echten GatedLLMClient/Orchestrator-Flow.

Scope: ingress_source bis zum Gate durchreichen, run_mirror_lint() im
Nutzer-Ausgabe-Pfad tatsaechlich aufrufen, INTERN/PRUEFER bleiben nicht
blockierend. Keine Stufe-3-Pruefer, kein UI, kein Replay-Korpus, keine
neuen Provider-Adapter.
"""
from __future__ import annotations

import os

os.environ.setdefault("AILIZA_SECRET_KEY", "test-secret-key-minimum-32-chars-ok")

import pytest

from apps.backend.providers.gate_types import EgressOutcome, ProviderResult, Zweck
from apps.backend.providers.gated_client import GatedLLMClient
from apps.backend.errors import AILIZAError


class _FakeProvider:
    provider_id = "fake"

    def __init__(self, results):
        self._results = list(results)
        self.calls = 0

    def generate_with_meta(self, messages, context=None):
        self.calls += 1
        result = self._results.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


# ---------------------------------------------------------------------------
# T1: ingress_source wird bis zum Gate durchgereicht und beeinflusst das Ergebnis
# ---------------------------------------------------------------------------

def test_ingress_source_reaches_the_gate():
    provider = _FakeProvider([ProviderResult(text="Ihre IBAN DE89370400440532013000 ist erfasst.", stop_reason="end_turn")])
    client = GatedLLMClient()
    with pytest.raises(AILIZAError):
        client.generate(
            provider, [{"role": "user", "content": "x"}],
            zweck=Zweck.NUTZER_AUSGABE,
            ingress_source="Meine IBAN ist DE89370400440532013000.",
        )
    assert client.last_diagnostic.grund == "MIRROR_LINT_BLOCK"


# ---------------------------------------------------------------------------
# T2: Mirror-Lint laeuft nur bei NUTZER_AUSGABE blockierend
# ---------------------------------------------------------------------------

def test_mirror_lint_only_blocking_for_nutzer_ausgabe():
    provider = _FakeProvider([ProviderResult(text="Ohne Ingress-Vergleich: DE89370400440532013000", stop_reason="end_turn")])
    client = GatedLLMClient()
    # kein ingress_source -> Mirror-Lint laeuft nicht, DELIVER
    text = client.generate(
        provider, [{"role": "user", "content": "x"}], zweck=Zweck.NUTZER_AUSGABE,
    )
    assert text == "Ohne Ingress-Vergleich: DE89370400440532013000"
    assert client.last_diagnostic.outcome == EgressOutcome.DELIVER.value


# ---------------------------------------------------------------------------
# T3: INTERN/PRUEFER erzeugen keine Egress-Enforcement-Blocks, auch mit
# ingress_source
# ---------------------------------------------------------------------------

def test_intern_and_pruefer_never_egress_blocked_even_with_ingress_source():
    for zweck in (Zweck.INTERN, Zweck.PRUEFER):
        provider = _FakeProvider([ProviderResult(text="Kandidat mit IBAN DE89370400440532013000", stop_reason="end_turn")])
        client = GatedLLMClient()
        text = client.generate(
            provider, [{"role": "user", "content": "x"}], zweck=zweck,
            ingress_source="Meine IBAN ist DE89370400440532013000.",
        )
        assert text == "Kandidat mit IBAN DE89370400440532013000"
        assert client.last_diagnostic.outcome == EgressOutcome.DELIVER.value


# ---------------------------------------------------------------------------
# T4: Shadow-Regel blockt im echten Flow nicht
# ---------------------------------------------------------------------------

def test_shadow_rule_does_not_block_in_real_flow():
    ingress = "Mein Name ist Peter Mustermann."
    provider = _FakeProvider([ProviderResult(text="Sehr geehrter Herr Mustermann, danke.", stop_reason="end_turn")])
    client = GatedLLMClient()
    text = client.generate(
        provider, [{"role": "user", "content": "x"}], zweck=Zweck.NUTZER_AUSGABE,
        ingress_source=ingress,
    )
    assert "Mustermann" in text
    assert client.last_diagnostic.outcome == EgressOutcome.DELIVER.value


# ---------------------------------------------------------------------------
# T5: Enforce-kritische Regel kann im echten Flow BLOCK_WITH_ALTERNATIVE
# erzeugen
# ---------------------------------------------------------------------------

def test_enforce_critical_rule_blocks_in_real_flow():
    provider = _FakeProvider([ProviderResult(text="Ihre Kartennummer 4111 1111 1111 1111 wurde erfasst.", stop_reason="end_turn")])
    client = GatedLLMClient()
    with pytest.raises(AILIZAError):
        client.generate(
            provider, [{"role": "user", "content": "x"}], zweck=Zweck.NUTZER_AUSGABE,
            ingress_source="Ganz ohne Kartendaten im Ursprungstext.",
        )
    assert client.last_diagnostic.outcome == EgressOutcome.BLOCK_WITH_ALTERNATIVE.value


# ---------------------------------------------------------------------------
# T6: Generator-risk_flags bleiben nicht entscheidend (Gate kennt sie in
# PR-3b noch gar nicht als Eingabeparameter -- Egress-Entscheidung haengt
# ausschliesslich am deterministischen Ingress/Egress-Vergleich)
# ---------------------------------------------------------------------------

def test_generator_risk_flags_not_decisive_in_real_flow():
    import inspect

    from apps.backend.providers.gated_client import GatedLLMClient as _Client

    sig = inspect.signature(_Client.generate)
    assert "risk_flags" not in sig.parameters


# ---------------------------------------------------------------------------
# T7: Rueckwaertskompatible Textausgabe bleibt erhalten
# ---------------------------------------------------------------------------

def test_summarize_with_llm_includes_search_text_in_ingress_source(monkeypatch):
    """Review-Fund: ingress_source darf nicht nur die Nutzerfrage sein,
    sondern muss auch search_text abdecken, sonst sieht Spiegel-Linting die
    PII nicht, die nur im Suchergebnis (nicht in der Frage) steht."""
    from apps.backend import main as main_module

    captured = {}

    def fake_generate(messages, context=None, zweck=None, ingress_source=None):
        captured["ingress_source"] = ingress_source
        return "Kurze Antwort."

    monkeypatch.setattr(main_module._orchestrator, "generate", fake_generate)
    main_module._summarize_with_llm(
        "Was ist meine IBAN?", "Suchergebnis enthaelt DE89370400440532013000",
    )
    assert "DE89370400440532013000" in captured["ingress_source"]
    assert "Was ist meine IBAN?" in captured["ingress_source"]


def test_backwards_compatible_plain_text_return_preserved():
    provider = _FakeProvider([ProviderResult(text="Normale Antwort ohne PII.", stop_reason="end_turn")])
    client = GatedLLMClient()
    result = client.generate(
        provider, [{"role": "user", "content": "x"}], zweck=Zweck.NUTZER_AUSGABE,
        ingress_source="Auch hier keine PII.",
    )
    assert isinstance(result, str)
    assert result == "Normale Antwort ohne PII."
