"""
Tests: Registry-Orchestrator-Verbindung

Prüft:
- Provider enabled=True + admin_approved=False → blockiert (fail-closed)
- Provider fehlt in Registry → blockiert
- Provider enabled=False → blockiert
- public_data → freigegebene Provider nutzbar
- personal_data → nur erlaubte Provider
- writing_task → keine Websuche laut Routing-Regel
- sensitive_hr_task → human_review=True
- Registry hat Vorrang vor provider_profiles.py
- all_providers_failed enthält Registry-Ursachen
- Logs: REGISTRY CHECK, ROUTING RULE, PROVIDER SELECT sichtbar
"""
from __future__ import annotations

import pytest

from apps.backend.errors import AILIZAError
from apps.backend.governance.data_governance import DataClass


# ── Hilfsfunktionen ───────────────────────────────────────────────────────────

def _make_orchestrator(monkeypatch, providers: dict):
    """Erstellt einen Orchestrator mit kontrollierten Fake-Providern."""
    monkeypatch.setenv("AILIZA_EXTERNAL_LLM_ENABLED", "true")
    monkeypatch.setenv("GROQ_API_KEY", "fake")
    monkeypatch.setenv("OPENAI_API_KEY", "fake")
    # Ohne unterzeichneten AVV blockt check_provider_policy() seit Freigabe
    # Stufe 1 (P-A) auch PUBLIC-Daten, ausser im Testmodus.
    monkeypatch.setenv("AILIZA_TEST_MODE", "true")

    from apps.backend.providers.orchestrator import ProviderOrchestrator
    return ProviderOrchestrator(providers=providers)


def _fake_provider(provider_id: str, answer: str = "OK"):
    """Fake-LLM-Provider der immer eine feste Antwort gibt."""
    class _Fake:
        def __init__(self):
            self.provider_id = provider_id
            self.model = f"fake-{provider_id}"
        def count_tokens(self, text): return len(text.split())
        def estimate_cost(self, i, o): return 0.0
        def generate(self, messages, context=None): return answer
        def stream(self, messages, context=None): yield answer
    return _Fake()


def _failing_provider(provider_id: str, code: str = "provider_not_configured"):
    class _Fail:
        def __init__(self):
            self.provider_id = provider_id
            self.model = f"fail-{provider_id}"
        def count_tokens(self, text): return 1
        def estimate_cost(self, i, o): return 0.0
        def generate(self, messages, context=None):
            raise AILIZAError.from_code(code)
        def stream(self, messages, context=None):
            raise AILIZAError.from_code(code)
    return _Fail()


# ── 1. Registry-Check blockiert nicht freigegebene Provider ───────────────────

class TestRegistryCheckBlocking:

    def test_enabled_without_admin_approved_blocked(self, monkeypatch):
        """
        Provider enabled=True aber admin_approved=False →
        check_provider_in_registry gibt False zurück.
        """
        from apps.backend.registry.registry_loader import (
            check_provider_in_registry, _registry, reload_registry, ProviderEntry,
        )
        import apps.backend.registry.registry_loader as rl

        # Patch Registry mit unapproved Provider
        from apps.backend.registry.registry_loader import Registry
        fake_entry = ProviderEntry(
            provider_id="pending_provider",
            type="text_llm", enabled=True, admin_approved=False,
            region="us", transfer_basis="scc", avv_signed=False,
            allowed_data=["public"], forbidden_data=[],
            default_model="m", fallback_models=[],
            failover_priority=5, health_status="ok",
            logs_prompts=False, used_for_training=False,
        )
        fake_reg = Registry(providers={"pending_provider": fake_entry})
        monkeypatch.setattr(rl, "_registry", fake_reg)

        allowed, code, reason = check_provider_in_registry("pending_provider", ["public"])
        assert not allowed
        assert code == "registry_provider_not_approved"
        assert "Admin" in reason or "admin_approved" in reason

    def test_disabled_provider_blocked(self, monkeypatch):
        from apps.backend.registry.registry_loader import (
            check_provider_in_registry, Registry, ProviderEntry,
        )
        import apps.backend.registry.registry_loader as rl

        fake_entry = ProviderEntry(
            provider_id="disabled_prov",
            type="text_llm", enabled=False, admin_approved=True,
            region="us", transfer_basis="scc", avv_signed=False,
            allowed_data=["public"], forbidden_data=[],
            default_model="m", fallback_models=[],
            failover_priority=5, health_status="ok",
            logs_prompts=False, used_for_training=False,
        )
        fake_reg = Registry(providers={"disabled_prov": fake_entry})
        monkeypatch.setattr(rl, "_registry", fake_reg)

        allowed, code, reason = check_provider_in_registry("disabled_prov", ["public"])
        assert not allowed
        assert code == "registry_provider_disabled"

    def test_unknown_provider_blocked(self, monkeypatch):
        from apps.backend.registry.registry_loader import check_provider_in_registry
        allowed, code, reason = check_provider_in_registry("brand_new_unknown_provider", ["public"])
        assert not allowed
        assert code == "registry_provider_not_found"

    def test_data_class_not_allowed_blocked(self, monkeypatch):
        from apps.backend.registry.registry_loader import (
            check_provider_in_registry, Registry, ProviderEntry,
        )
        import apps.backend.registry.registry_loader as rl

        fake_entry = ProviderEntry(
            provider_id="restricted_prov",
            type="text_llm", enabled=True, admin_approved=True,
            region="us", transfer_basis="scc", avv_signed=False,
            allowed_data=["public"],          # nur public
            forbidden_data=["personal_data", "credentials"],
            default_model="m", fallback_models=[],
            failover_priority=5, health_status="ok",
            logs_prompts=False, used_for_training=False,
        )
        fake_reg = Registry(providers={"restricted_prov": fake_entry})
        monkeypatch.setattr(rl, "_registry", fake_reg)

        allowed, code, reason = check_provider_in_registry("restricted_prov", ["personal_data"])
        assert not allowed
        assert code == "registry_data_class_not_allowed"

    def test_transfer_basis_none_blocked(self, monkeypatch):
        from apps.backend.registry.registry_loader import (
            check_provider_in_registry, Registry, ProviderEntry,
        )
        import apps.backend.registry.registry_loader as rl

        fake_entry = ProviderEntry(
            provider_id="no_transfer_prov",
            type="text_llm", enabled=True, admin_approved=True,
            region="us", transfer_basis="none", avv_signed=False,  # kein Transfermechanismus
            allowed_data=["public"], forbidden_data=[],
            default_model="m", fallback_models=[],
            failover_priority=5, health_status="ok",
            logs_prompts=False, used_for_training=False,
        )
        fake_reg = Registry(providers={"no_transfer_prov": fake_entry})
        monkeypatch.setattr(rl, "_registry", fake_reg)

        allowed, code, reason = check_provider_in_registry("no_transfer_prov", ["public"])
        assert not allowed
        assert "Transfer" in reason or code == "registry_provider_not_approved"


# ── 2. Orchestrator nutzt Registry ────────────────────────────────────────────

class TestOrchestratorRegistryIntegration:

    def test_unapproved_provider_not_in_candidates(self, monkeypatch):
        """
        Wenn ein Provider in der Registry admin_approved=False ist,
        darf er nicht in der Kandidatenliste des Orchestrators auftauchen.
        """
        from apps.backend.registry.registry_loader import Registry, ProviderEntry
        import apps.backend.registry.registry_loader as rl

        fake_entry = ProviderEntry(
            provider_id="sneaky",
            type="text_llm", enabled=True, admin_approved=False,
            region="us", transfer_basis="scc", avv_signed=False,
            allowed_data=["public"], forbidden_data=[],
            default_model="m", fallback_models=[],
            failover_priority=1, health_status="ok",
            logs_prompts=False, used_for_training=False,
        )
        monkeypatch.setattr(rl, "_registry", Registry(providers={"sneaky": fake_entry}))
        monkeypatch.setenv("AILIZA_EXTERNAL_LLM_ENABLED", "true")

        from apps.backend.providers.orchestrator import ProviderOrchestrator
        orch = ProviderOrchestrator(providers={"sneaky": _fake_provider("sneaky", "SOLLTE NIE KOMMEN")})

        with pytest.raises(AILIZAError):
            orch.generate([{"role": "user", "content": "test"}])

    def test_public_data_allowed_for_approved_provider(self, monkeypatch):
        """public_data muss mit freigegebenem Provider funktionieren."""
        monkeypatch.setenv("AILIZA_EXTERNAL_LLM_ENABLED", "true")
        monkeypatch.setenv("GROQ_API_KEY", "fake")
        monkeypatch.setenv("AILIZA_TEST_MODE", "true")
        import apps.backend.registry.registry_loader as rl
        rl._registry = None  # echte Registry laden

        from apps.backend.providers.orchestrator import ProviderOrchestrator
        orch = ProviderOrchestrator(providers={"groq": _fake_provider("groq", "Antwort auf öffentliche Frage")})
        result = orch.generate([{"role": "user", "content": "Was ist DSGVO?"}])
        assert result == "Antwort auf öffentliche Frage"

    def test_all_providers_fail_raises_all_providers_failed(self, monkeypatch):
        """Wenn alle Registry-erlaubten Provider scheitern → all_providers_failed."""
        monkeypatch.setenv("AILIZA_EXTERNAL_LLM_ENABLED", "true")
        monkeypatch.setenv("GROQ_API_KEY", "fake")
        monkeypatch.setenv("OPENAI_API_KEY", "fake")
        monkeypatch.setenv("AILIZA_TEST_MODE", "true")
        import apps.backend.registry.registry_loader as rl
        rl._registry = None

        from apps.backend.providers.orchestrator import ProviderOrchestrator
        orch = ProviderOrchestrator(providers={
            "groq": _failing_provider("groq"),
            "openai": _failing_provider("openai"),
            "anthropic": _failing_provider("anthropic"),
        })
        with pytest.raises(AILIZAError) as exc_info:
            orch.generate([{"role": "user", "content": "test"}])
        assert exc_info.value.code == "all_providers_failed"

    def test_registry_unavailable_blocks_all_external(self, monkeypatch):
        """Wenn Registry nicht geladen werden kann → keine externen Provider (fail-closed)."""
        monkeypatch.setenv("AILIZA_EXTERNAL_LLM_ENABLED", "true")
        monkeypatch.setenv("GROQ_API_KEY", "fake")

        import apps.backend.registry.registry_loader as rl

        def _raise_on_load():
            raise RuntimeError("Registry-Datei beschädigt")

        monkeypatch.setattr(rl, "get_registry", _raise_on_load)
        monkeypatch.setattr(rl, "_registry", None)

        from apps.backend.providers.orchestrator import ProviderOrchestrator
        orch = ProviderOrchestrator(providers={"groq": _fake_provider("groq", "sollte blockiert sein")})

        with pytest.raises(AILIZAError) as exc_info:
            orch.generate([{"role": "user", "content": "test"}])
        # provider_not_configured oder registry_unavailable — kein Ergebnis
        assert exc_info.value.code in (
            "provider_not_configured", "registry_unavailable", "all_providers_failed"
        )

    def test_registry_has_priority_over_legacy_profiles(self, monkeypatch):
        """
        Registry blockiert Provider → kein Aufruf, auch wenn provider_profiles.py ihn erlauben würde.
        """
        from apps.backend.registry.registry_loader import Registry, ProviderEntry
        import apps.backend.registry.registry_loader as rl

        # Registry blockiert groq explizit (admin_approved=False)
        fake_entry = ProviderEntry(
            provider_id="groq",
            type="text_llm", enabled=True, admin_approved=False,
            region="us", transfer_basis="scc", avv_signed=False,
            allowed_data=["public"], forbidden_data=[],
            default_model="llama-3.3-70b-versatile", fallback_models=[],
            failover_priority=1, health_status="ok",
            logs_prompts=False, used_for_training=False,
        )
        monkeypatch.setattr(rl, "_registry", Registry(providers={"groq": fake_entry}))
        monkeypatch.setenv("AILIZA_EXTERNAL_LLM_ENABLED", "true")
        monkeypatch.setenv("GROQ_API_KEY", "fake")

        calls = []

        class TrackingProvider:
            provider_id = "groq"
            model = "test"
            def count_tokens(self, text): return 1
            def estimate_cost(self, i, o): return 0.0
            def generate(self, messages, context=None):
                calls.append("groq_called")
                return "sollte nicht kommen"

        from apps.backend.providers.orchestrator import ProviderOrchestrator
        orch = ProviderOrchestrator(providers={"groq": TrackingProvider()})

        with pytest.raises(AILIZAError):
            orch.generate([{"role": "user", "content": "test"}])

        assert "groq_called" not in calls, "Groq wurde aufgerufen obwohl Registry ihn blockiert hat"


# ── 3. Routing-Regeln ─────────────────────────────────────────────────────────

class TestRoutingRulesIntegration:

    def test_writing_task_web_search_false(self):
        """writing_task muss web_search=False haben."""
        from apps.backend.registry.registry_loader import get_routing_for_task
        rule = get_routing_for_task("writing_task")
        assert rule is not None
        assert not rule.web_search, "writing_task darf keine Websuche auslösen"

    def test_research_task_web_search_true(self):
        from apps.backend.registry.registry_loader import get_routing_for_task
        rule = get_routing_for_task("research_task")
        assert rule is not None
        assert rule.web_search

    def test_sensitive_hr_task_human_review(self):
        from apps.backend.registry.registry_loader import get_routing_for_task
        rule = get_routing_for_task("sensitive_hr_task")
        assert rule is not None
        assert rule.human_review, "HR-Aufgaben erfordern menschliche Überprüfung"
        assert rule.draft_only, "HR-Aufgaben müssen als Entwurf markiert sein"

    def test_unknown_task_falls_back_to_general(self):
        from apps.backend.registry.registry_loader import get_routing_for_task
        rule = get_routing_for_task("gibberish_task_that_does_not_exist")
        assert rule is not None
        assert rule.rule_id == "general_task"

    def test_writing_task_preferred_providers_in_registry(self):
        """Alle bevorzugten Provider für writing_task müssen in der Registry sein."""
        from apps.backend.registry.registry_loader import get_routing_for_task, get_registry
        rule = get_routing_for_task("writing_task")
        reg = get_registry()
        for pid in rule.preferred_providers:
            assert reg.get_provider(pid) is not None, (
                f"Provider '{pid}' aus writing_task-Routing fehlt in der Registry"
            )

    def test_routing_log_emitted(self, monkeypatch, capsys):
        """AILIZA ROUTING RULE muss im Log erscheinen."""
        monkeypatch.setenv("AILIZA_EXTERNAL_LLM_ENABLED", "true")
        monkeypatch.setenv("GROQ_API_KEY", "fake")
        monkeypatch.setenv("AILIZA_TEST_MODE", "true")
        import apps.backend.registry.registry_loader as rl
        rl._registry = None

        from apps.backend.providers.orchestrator import ProviderOrchestrator
        orch = ProviderOrchestrator(providers={"groq": _fake_provider("groq", "test")})

        class FakeContext:
            data_classes = [DataClass.PUBLIC]
            tenant_id = "test"
            user_id = None
            redaction_applied = False
            purpose = "kmu_assistant"
            task_type = "writing_task"

        orch.generate([{"role": "user", "content": "test"}], context=FakeContext())
        captured = capsys.readouterr()
        assert "AILIZA ROUTING RULE" in captured.out
        assert "writing_task" in captured.out


# ── 4. Fehlercodes und UI-Meldungen ───────────────────────────────────────────

class TestRegistryErrorCodes:

    def test_registry_error_codes_have_messages(self):
        """Alle neuen Registry-Fehlercodes müssen eine deutsche UI-Meldung haben."""
        from apps.backend.errors import MESSAGES
        required = [
            "registry_provider_not_found",
            "registry_provider_disabled",
            "registry_provider_not_approved",
            "registry_data_class_not_allowed",
            "registry_unavailable",
        ]
        for code in required:
            assert code in MESSAGES, f"Fehlercode '{code}' hat keine UI-Meldung"
            msg = MESSAGES[code]
            assert len(msg) > 10, f"Meldung für '{code}' ist zu kurz"
            # Meldung darf nicht sagen "API-Schlüssel fehlt" für Registry-Fehler
            assert "API-Schluessel" not in msg, (
                f"Registry-Fehler '{code}' zeigt irreführend 'API-Schlüssel fehlt'"
            )

    def test_not_approved_message_mentions_freigabe(self):
        from apps.backend.errors import MESSAGES
        msg = MESSAGES["registry_provider_not_approved"]
        assert "freigegeben" in msg.lower() or "freigabe" in msg.lower() or "Freigabe" in msg

    def test_data_class_blocked_message_mentions_datenklasse(self):
        from apps.backend.errors import MESSAGES
        msg = MESSAGES["registry_data_class_not_allowed"]
        assert "Datenklasse" in msg or "datenklasse" in msg.lower() or "Anbieter" in msg


# ── 5. Logs: kein PII, kein API-Key ──────────────────────────────────────────

class TestRegistryLogSafety:

    def test_registry_check_log_no_api_key(self, monkeypatch, capsys):
        """AILIZA REGISTRY CHECK Log darf keinen API-Key enthalten."""
        monkeypatch.setenv("GROQ_API_KEY", "super-secret-groq-key-12345")
        import apps.backend.registry.registry_loader as rl
        rl._registry = None

        from apps.backend.registry.registry_loader import check_provider_in_registry
        check_provider_in_registry("groq", ["public"])
        captured = capsys.readouterr()
        assert "super-secret-groq-key-12345" not in captured.out

    def test_provider_select_log_no_api_key(self, monkeypatch, capsys):
        """AILIZA PROVIDER SELECT Log darf keinen API-Key enthalten."""
        monkeypatch.setenv("GROQ_API_KEY", "top-secret-key-xyz")
        monkeypatch.setenv("AILIZA_EXTERNAL_LLM_ENABLED", "true")
        import apps.backend.registry.registry_loader as rl
        rl._registry = None

        from apps.backend.providers.orchestrator import ProviderOrchestrator
        orch = ProviderOrchestrator(providers={"groq": _fake_provider("groq", "ok")})
        try:
            orch.generate([{"role": "user", "content": "test"}])
        except Exception:
            pass
        captured = capsys.readouterr()
        assert "top-secret-key-xyz" not in captured.out
        assert "top-secret-key-xyz" not in captured.err
