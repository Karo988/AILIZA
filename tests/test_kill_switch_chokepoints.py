"""Der letzte Entscheidungspunkt liegt unmittelbar vor jedem LLM-Netzaufruf."""
from __future__ import annotations

import sys
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from apps.backend.errors import AILIZAError


def test_groq_provider_rechecks_before_urlopen(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "fake-key")
    monkeypatch.setenv("AILIZA_EXTERNAL_LLM_ENABLED", "false")
    network = Mock(side_effect=AssertionError("network called"))
    monkeypatch.setattr("urllib.request.urlopen", network)
    from apps.backend.providers.groq_provider import GroqProvider

    with pytest.raises(AILIZAError) as exc:
        GroqProvider().generate([{"role": "user", "content": "test"}])

    assert exc.value.code == "kill_switch_active"
    network.assert_not_called()


def test_openai_provider_rechecks_before_urlopen(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "fake-key")
    monkeypatch.setenv("AILIZA_EXTERNAL_LLM_ENABLED", "false")
    network = Mock(side_effect=AssertionError("network called"))
    monkeypatch.setattr("urllib.request.urlopen", network)
    from apps.backend.providers.openai_provider import OpenAIProvider

    with pytest.raises(AILIZAError) as exc:
        OpenAIProvider().generate([{"role": "user", "content": "test"}])

    assert exc.value.code == "kill_switch_active"
    network.assert_not_called()


def test_openrouter_requires_its_explicit_yaml_switch(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "fake-key")
    monkeypatch.setenv("AILIZA_EXTERNAL_LLM_ENABLED", "true")
    network = Mock(side_effect=AssertionError("network called"))
    monkeypatch.setattr("urllib.request.urlopen", network)
    from apps.backend.providers.openrouter_provider import OpenRouterProvider

    with pytest.raises(AILIZAError) as exc:
        OpenRouterProvider().generate([{"role": "user", "content": "test"}])

    assert exc.value.code == "kill_switch_active"
    network.assert_not_called()


def test_agent_openai_client_cannot_bypass_kill_switch(monkeypatch):
    monkeypatch.setenv("AILIZA_EXTERNAL_LLM_ENABLED", "false")
    create_call = Mock(side_effect=AssertionError("network called"))

    class FakeOpenAI:
        def __init__(self, **kwargs):
            self.chat = SimpleNamespace(completions=SimpleNamespace(create=create_call))

    monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(OpenAI=FakeOpenAI))
    from apps.backend.agent.api_client import call_llm_api

    agent = SimpleNamespace(
        model="openai/gpt-test", api_key="fake-key", _tool_registry={},
    )
    with pytest.raises(AILIZAError) as exc:
        call_llm_api(agent, [{"role": "user", "content": "test"}], "system")

    assert exc.value.code == "kill_switch_active"
    create_call.assert_not_called()


def test_agent_rejects_unapproved_base_url_before_client_creation(monkeypatch):
    monkeypatch.setenv("AILIZA_EXTERNAL_LLM_ENABLED", "true")
    monkeypatch.setenv("AILIZA_BASE_URL", "https://unapproved.example/v1")
    client_init = Mock(side_effect=AssertionError("client constructed"))
    monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(OpenAI=client_init))
    from apps.backend.agent.api_client import call_llm_api

    agent = SimpleNamespace(model="openai/gpt-test", api_key="fake-key", _tool_registry={})
    with pytest.raises(ValueError, match="freigegebenen Provider"):
        call_llm_api(agent, [{"role": "user", "content": "test"}], "system")

    client_init.assert_not_called()


def test_groq_diagnosis_stops_before_both_network_calls(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "fake-key")
    monkeypatch.setenv("AILIZA_EXTERNAL_LLM_ENABLED", "false")
    network = Mock(side_effect=AssertionError("network called"))
    monkeypatch.setattr("urllib.request.urlopen", network)
    from apps.backend.groq_client import run_groq_diagnosis

    result = run_groq_diagnosis()

    assert result["diagnosis"] == "kill_switch_active"
    assert result["env"]["external_llm_allowed"] is False
    network.assert_not_called()
