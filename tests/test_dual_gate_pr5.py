"""Tests fuer Dual-Gate PR-5: Groq/OpenAI response_format-Live-Verdrahtung.

Scope (Karo-Freigabe): response_format nur bei require_schema=True UND
deklarierter Provider-Capability, kein Verhaltenseffekt fuer Plain-Text-
Flows, keine neue Fehlerklasse (nutzt bestehende PR-2-Degradation), keine
Rohinhalte in Diagnostics. Zusatzregel: nach einem JSON-Mode-Fehlversuch
wird response_format fuer den Rest desselben Requests NIE erneut versucht
(kein Fehler-Loop).
"""
from __future__ import annotations

import os

os.environ.setdefault("AILIZA_SECRET_KEY", "test-secret-key-minimum-32-chars-ok")

import pytest

from apps.backend.providers.gate_types import GateDiagnostic, ProviderResult, Zweck
from apps.backend.providers.gated_client import GatedLLMClient
from apps.backend.errors import AILIZAError


class _FakeProvider:
    provider_id = "fake_openai_compatible"
    supports_json_mode = True

    def __init__(self, results):
        self._results = list(results)
        self.calls_with_format: list[dict | None] = []

    def generate_with_meta(self, messages, context=None, response_format=None):
        self.calls_with_format.append(response_format)
        result = self._results.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


# ---------------------------------------------------------------------------
# T1/T2: Groq/OpenAI-kompatibler Provider bekommt response_format, wenn
# require_schema=True und Capability aktiv ist
# ---------------------------------------------------------------------------

def test_groq_generate_with_meta_sets_response_format_when_capability_active():
    from apps.backend.providers.groq_provider import GroqProvider

    provider = GroqProvider()
    assert provider.supports_json_mode is True
    # Direkter Beweis auf Adapter-Ebene: response_format landet im Payload.
    import json as _json
    import apps.backend.providers.groq_provider as groq_mod

    captured = {}

    class _FakeResp:
        def read(self):
            return _json.dumps({"choices": [{"message": {"content": "{}"}}]}).encode()

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def _fake_urlopen(req, timeout=20):
        captured["body"] = _json.loads(req.data)
        return _FakeResp()

    import urllib.request as _urllib_request

    orig = _urllib_request.urlopen
    _urllib_request.urlopen = _fake_urlopen
    try:
        os.environ["GROQ_API_KEY"] = "test-key"
        provider.generate_with_meta(
            [{"role": "user", "content": "x"}], response_format={"type": "json_object"},
        )
    finally:
        _urllib_request.urlopen = orig

    assert captured["body"].get("response_format") == {"type": "json_object"}


def test_openai_generate_with_meta_sets_response_format_when_capability_active():
    from apps.backend.providers.openai_provider import OpenAIProvider

    provider = OpenAIProvider()
    assert provider.supports_json_mode is True

    import json as _json
    captured = {}

    class _FakeResp:
        def read(self):
            return _json.dumps({"choices": [{"message": {"content": "{}"}}]}).encode()

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def _fake_urlopen(req, timeout=20):
        captured["body"] = _json.loads(req.data)
        return _FakeResp()

    import urllib.request as _urllib_request

    orig = _urllib_request.urlopen
    _urllib_request.urlopen = _fake_urlopen
    try:
        os.environ["OPENAI_API_KEY"] = "test-key"
        provider.generate_with_meta(
            [{"role": "user", "content": "x"}], response_format={"type": "json_object"},
        )
    finally:
        _urllib_request.urlopen = orig

    assert captured["body"].get("response_format") == {"type": "json_object"}


# ---------------------------------------------------------------------------
# T3: nicht unterstuetzter JSON-Modus faellt ueber die bestehende
# Degradations-Leiter auf den Textvertrag zurueck -- KEIN Block, und der
# response_format-Retry wird nicht wiederholt (kein Fehler-Loop)
# ---------------------------------------------------------------------------

def test_unsupported_json_mode_error_falls_back_to_text_contract():
    provider = _FakeProvider([
        AILIZAError.from_code("provider_error"),  # 1. Versuch: JSON-Modus abgelehnt
        ProviderResult(text="Prosa-Antwort ohne JSON.", stop_reason="end_turn"),  # 2. Versuch: ohne response_format
    ])
    client = GatedLLMClient()
    text = client.generate(
        provider, [{"role": "user", "content": "x"}], require_schema=True,
    )
    assert text == "Prosa-Antwort ohne JSON."
    assert client.last_diagnostic.degraded is True
    assert client.last_diagnostic.grund == "SCHEMA_DEGRADED"
    # 1. Call MIT response_format, 2. Call OHNE -- nie zweimal mit Format:
    assert provider.calls_with_format == [{"type": "json_object"}, None]


# ---------------------------------------------------------------------------
# T4: response_format wird NUR bei require_schema=True angefordert
# ---------------------------------------------------------------------------

def test_response_format_only_requested_for_require_schema_calls():
    provider = _FakeProvider([ProviderResult(text="Normale Plain-Text-Antwort.", stop_reason="end_turn")])
    client = GatedLLMClient()
    text = client.generate(provider, [{"role": "user", "content": "x"}])  # require_schema=False (Default)
    assert text == "Normale Plain-Text-Antwort."
    assert provider.calls_with_format == [None]


# ---------------------------------------------------------------------------
# T5: Diagnostics enthalten nach JSON-Mode-Fallback keine Rohinhalte
# ---------------------------------------------------------------------------

def test_diagnostics_contain_no_raw_content_after_json_mode_fallback():
    provider = _FakeProvider([
        AILIZAError.from_code("provider_error"),
        ProviderResult(text="Geheimer Entwurfsinhalt XYZ.", stop_reason="end_turn"),
    ])
    client = GatedLLMClient()
    client.generate(provider, [{"role": "user", "content": "geheime Nutzeranfrage ABC"}], require_schema=True)
    diag = client.last_diagnostic
    assert isinstance(diag, GateDiagnostic)
    for field_name in ("outcome", "zweck", "candidate_status", "grund", "pruefer_flag"):
        value = getattr(diag, field_name, None)
        if value is not None:
            assert "Geheimer Entwurfsinhalt" not in str(value)
            assert "geheime Nutzeranfrage" not in str(value)


# ---------------------------------------------------------------------------
# T6: kein Verhaltenseffekt fuer die bestehenden Plain-Text-Flows
# (require_schema=False bleibt exakt wie vor PR-5)
# ---------------------------------------------------------------------------

def test_no_behavior_change_when_require_schema_false():
    provider = _FakeProvider([ProviderResult(text="Unveraendertes Verhalten.", stop_reason="end_turn")])
    client = GatedLLMClient()
    text = client.generate(
        provider, [{"role": "user", "content": "x"}], zweck=Zweck.NUTZER_AUSGABE,
    )
    assert text == "Unveraendertes Verhalten."
    assert client.last_diagnostic.degraded is False
    assert client.last_diagnostic.grund is None
    assert provider.calls_with_format == [None]
