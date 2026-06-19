import pytest

from apps.backend.providers.base import LLMProvider
from apps.backend.providers.orchestrator import ProviderOrchestrator
from apps.backend.errors import AILIZAError


class MockProvider(LLMProvider):
    provider_region = "EU"
    provider_profile_version = "1.0"
    provider_id = "mock"
    model = "mock-model"

    def generate(self, messages, context=None):
        return "MOCK_ANSWER"

    def stream(self, messages, context=None):
        yield "MOCK_ANSWER"


def _orch():
    return ProviderOrchestrator(providers={"mock": MockProvider()}, default_provider="mock")


def test_generate_blocked_when_kill_switch_off(monkeypatch):
    monkeypatch.setenv("AILIZA_EXTERNAL_LLM_ENABLED", "false")
    import importlib
    from apps.backend import kill_switch
    importlib.reload(kill_switch)
    with pytest.raises(AILIZAError) as exc:
        _orch().generate([{"role": "user", "content": "hi"}])
    assert exc.value.code == "kill_switch_active"


def test_generate_with_mock(monkeypatch):
    monkeypatch.setenv("AILIZA_EXTERNAL_LLM_ENABLED", "true")
    import importlib
    from apps.backend import kill_switch
    importlib.reload(kill_switch)
    import apps.backend.providers.orchestrator as orch_mod
    importlib.reload(orch_mod)
    o = orch_mod.ProviderOrchestrator(providers={"mock": MockProvider()}, default_provider="mock")
    assert o.generate([{"role": "user", "content": "hi"}]) == "MOCK_ANSWER"


def test_unknown_provider(monkeypatch):
    monkeypatch.setenv("AILIZA_EXTERNAL_LLM_ENABLED", "true")
    import importlib
    from apps.backend import kill_switch
    importlib.reload(kill_switch)
    import apps.backend.providers.orchestrator as orch_mod
    importlib.reload(orch_mod)
    o = orch_mod.ProviderOrchestrator(providers={"mock": MockProvider()}, default_provider="mock")
    with pytest.raises(AILIZAError):
        o.generate([{"role": "user", "content": "hi"}], provider_id="nope")
