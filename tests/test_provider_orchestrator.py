import pytest
from types import SimpleNamespace

from apps.backend.providers.base import LLMProvider
from apps.backend.providers.orchestrator import ProviderOrchestrator
from apps.backend.errors import AILIZAError
from apps.backend.governance.data_governance import DataClass


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
    # Ohne unterzeichneten AVV nur mit serverseitigem Testmodus erlaubt
    # (Freigabe Stufe 1, P-A) — generate() klassifiziert PUBLIC per Default.
    monkeypatch.setenv("AILIZA_TEST_MODE", "true")
    import importlib
    from apps.backend import kill_switch
    importlib.reload(kill_switch)
    import apps.backend.providers.orchestrator as orch_mod
    importlib.reload(orch_mod)
    # "groq" ist im ProviderProfile-Register registriert (PUBLIC erlaubt)
    o = orch_mod.ProviderOrchestrator(providers={"groq": MockProvider()}, default_provider="groq")
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


def test_governed_route_does_not_retry_after_successful_external_call(
    monkeypatch,
):
    """An internal settlement failure must not cause a second provider call."""
    monkeypatch.setenv("AILIZA_EXTERNAL_LLM_ENABLED", "true")
    monkeypatch.setenv("AILIZA_TEST_MODE", "true")
    import importlib
    from apps.backend import component_system, kill_switch
    import apps.backend.providers.orchestrator as orch_mod

    importlib.reload(kill_switch)
    importlib.reload(orch_mod)
    monkeypatch.setattr(component_system, "recommend_active_model", lambda **_: {
        "provider": "groq", "model": "mock-model",
    })
    monkeypatch.setattr(component_system, "reserve_budget", lambda **_: {
        "reservation_id": "synthetic-reservation",
    })

    def fail_settlement(**_):
        raise RuntimeError("synthetic settlement failure")

    monkeypatch.setattr(component_system, "settle_budget", fail_settlement)
    provider = MockProvider()
    calls = []
    original_generate = provider.generate

    def counted_generate(messages, context=None):
        calls.append(1)
        return original_generate(messages, context)

    monkeypatch.setattr(provider, "generate", counted_generate)
    orchestrator = orch_mod.ProviderOrchestrator(
        providers={"groq": provider}, default_provider="groq",
    )
    context = SimpleNamespace(
        tenant_id="default", user_id="synthetic-user",
        task_package="chat", task_type="chat", purpose="kmu_assistant",
        data_classes=[DataClass.PUBLIC], redaction_applied=False,
    )
    monkeypatch.setattr(
        orchestrator, "_failover_order", lambda *_: [("groq", provider)],
    )

    with pytest.raises(AILIZAError) as exc:
        orchestrator.generate(
            [{"role": "user", "content": "synthetic prompt"}], context=context,
        )

    assert exc.value.code == "internal_error"
    assert len(calls) == 1
