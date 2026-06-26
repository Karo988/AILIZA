"""
Tests für AILIZA Governance-Regeln (DSGVO + EU AI Act).

Regeln (aus AILIZA_Governance_Logik.md):
- BLOCKED: nur bei CREDENTIALS / SPECIAL_CATEGORY (EU AI Act Art. 5 / DSGVO Art. 9)
- PERSONAL_DATA: redacten, nicht blockieren, als Entwurf weiterlaufen
- HR/LEGAL/FINANCIAL: redacten + Entwurf, nicht stoppen
- Provider-Profile: Groq/Anthropic erlauben PERSONAL_DATA/HR/LEGAL nach Redaction
"""
from __future__ import annotations

import pytest

from apps.backend.governance.data_governance import DataClass, DataTarget
from apps.backend.governance.data_matrix import PolicyDecision, check_data_target
from apps.backend.providers.provider_profiles import check_provider_policy


# ── 1. Datenziel-Matrix ────────────────────────────────────────────────────────

class TestDataMatrix:
    def test_personal_data_without_redaction_requires_redact(self):
        decision = check_data_target(
            data_classes=[DataClass.PERSONAL_DATA],
            target=DataTarget.EXTERNAL_LLM,
            redaction_applied=False,
            approval_given=False,
            provider_profile_active=True,
        )
        assert decision == PolicyDecision.REDACT_REQUIRED

    def test_personal_data_after_redaction_is_allowed(self):
        decision = check_data_target(
            data_classes=[DataClass.PERSONAL_DATA],
            target=DataTarget.EXTERNAL_LLM,
            redaction_applied=True,
            approval_given=False,
            provider_profile_active=True,
        )
        assert decision in (PolicyDecision.ALLOW, PolicyDecision.ALLOW_WITH_NOTICE)

    def test_hr_without_redaction_requires_approval(self):
        decision = check_data_target(
            data_classes=[DataClass.HR],
            target=DataTarget.EXTERNAL_LLM,
            redaction_applied=False,
            approval_given=False,
            provider_profile_active=True,
        )
        assert decision == PolicyDecision.APPROVAL_REQUIRED

    def test_hr_after_redaction_is_allowed(self):
        decision = check_data_target(
            data_classes=[DataClass.HR],
            target=DataTarget.EXTERNAL_LLM,
            redaction_applied=True,
            approval_given=False,
            provider_profile_active=True,
        )
        assert decision in (PolicyDecision.ALLOW, PolicyDecision.ALLOW_WITH_NOTICE)

    def test_credentials_always_blocked_for_external_llm(self):
        decision = check_data_target(
            data_classes=[DataClass.CREDENTIALS],
            target=DataTarget.EXTERNAL_LLM,
            redaction_applied=True,  # auch nach Redaction!
            approval_given=True,
            provider_profile_active=True,
        )
        assert decision == PolicyDecision.BLOCK

    def test_special_category_blocked_for_external_llm(self):
        decision = check_data_target(
            data_classes=[DataClass.SPECIAL_CATEGORY],
            target=DataTarget.EXTERNAL_LLM,
            redaction_applied=True,
            approval_given=True,
            provider_profile_active=True,
        )
        assert decision == PolicyDecision.BLOCK

    def test_public_data_always_allowed(self):
        decision = check_data_target(
            data_classes=[DataClass.PUBLIC],
            target=DataTarget.EXTERNAL_LLM,
            redaction_applied=False,
            approval_given=False,
            provider_profile_active=True,
        )
        assert decision in (PolicyDecision.ALLOW, PolicyDecision.ALLOW_WITH_NOTICE)


# ── 2. Provider-Profile ────────────────────────────────────────────────────────

class TestProviderProfiles:
    def test_groq_allows_public(self):
        allowed, reason = check_provider_policy("groq", [DataClass.PUBLIC])
        assert allowed, reason

    def test_groq_allows_personal_data(self):
        """Nach Redaction muss Groq PERSONAL_DATA akzeptieren."""
        allowed, reason = check_provider_policy("groq", [DataClass.PERSONAL_DATA])
        assert allowed, reason

    def test_groq_allows_hr(self):
        allowed, reason = check_provider_policy("groq", [DataClass.HR])
        assert allowed, reason

    def test_groq_blocks_credentials(self):
        allowed, _ = check_provider_policy("groq", [DataClass.CREDENTIALS])
        assert not allowed

    def test_groq_blocks_special_category(self):
        allowed, _ = check_provider_policy("groq", [DataClass.SPECIAL_CATEGORY])
        assert not allowed

    def test_anthropic_allows_personal_data(self):
        allowed, reason = check_provider_policy("anthropic", [DataClass.PERSONAL_DATA])
        assert allowed, reason

    def test_local_allows_all(self):
        for dc in DataClass:
            allowed, _ = check_provider_policy("local", [dc])
            assert allowed, f"local should allow {dc}"

    def test_groq_allows_text_generation(self):
        """Groq muss text_generation als Use Case erlauben (Schreibaufgaben)."""
        allowed, reason = check_provider_policy("groq", [DataClass.PUBLIC], use_case="text_generation")
        assert allowed, reason

    def test_openai_profile_exists_and_active(self):
        from apps.backend.providers.provider_profiles import get_profile
        profile = get_profile("openai")
        assert profile is not None
        assert profile.active is True
        assert not profile.admin_disabled

    def test_openai_allows_text_generation(self):
        allowed, reason = check_provider_policy("openai", [DataClass.PUBLIC], use_case="text_generation")
        assert allowed, reason

    def test_openai_allows_personal_data(self):
        allowed, reason = check_provider_policy("openai", [DataClass.PERSONAL_DATA])
        assert allowed, reason

    def test_openai_failover_priority_lower_than_groq(self):
        from apps.backend.providers.provider_profiles import get_profile
        groq = get_profile("groq")
        openai = get_profile("openai")
        assert groq is not None and openai is not None
        assert openai.failover_priority > groq.failover_priority


class TestProviderFailover:
    def test_orchestrator_has_openai_provider(self):
        from apps.backend.providers.orchestrator import ProviderOrchestrator
        orch = ProviderOrchestrator()
        assert "openai" in orch.providers

    def test_groq_fails_openai_attempted(self, monkeypatch):
        """Wenn Groq provider_not_configured wirft, soll OpenAI versucht werden."""
        from apps.backend.providers.orchestrator import ProviderOrchestrator
        from apps.backend.errors import AILIZAError
        import os

        calls = []

        class FakeGroq:
            provider_id = "groq"
            model = "test-groq"
            def count_tokens(self, text): return 1
            def estimate_cost(self, i, o): return 0.0
            def generate(self, messages, context=None):
                calls.append("groq")
                raise AILIZAError.from_code("provider_not_configured")

        class FakeOpenAI:
            provider_id = "openai"
            model = "test-openai"
            def count_tokens(self, text): return 1
            def estimate_cost(self, i, o): return 0.0
            def generate(self, messages, context=None):
                calls.append("openai")
                return "E-Mail Entwurf: Betreff: Test"

        monkeypatch.setenv("GROQ_API_KEY", "fake")
        monkeypatch.setenv("OPENAI_API_KEY", "fake")
        monkeypatch.setenv("AILIZA_EXTERNAL_LLM_ENABLED", "true")

        orch = ProviderOrchestrator(providers={"groq": FakeGroq(), "openai": FakeOpenAI()})
        result = orch.generate([{"role": "user", "content": "Schreibe eine E-Mail"}])
        assert "groq" in calls
        assert "openai" in calls
        assert "Betreff" in result

    def test_both_fail_raises_error(self, monkeypatch):
        """Wenn alle Provider scheitern, muss AILIZAError geworfen werden."""
        from apps.backend.providers.orchestrator import ProviderOrchestrator
        from apps.backend.errors import AILIZAError
        import pytest

        class FailProvider:
            provider_id = "groq"
            model = "x"
            def count_tokens(self, text): return 1
            def estimate_cost(self, i, o): return 0.0
            def generate(self, messages, context=None):
                raise AILIZAError.from_code("provider_not_configured")

        monkeypatch.setenv("GROQ_API_KEY", "fake")
        monkeypatch.setenv("AILIZA_EXTERNAL_LLM_ENABLED", "true")

        orch = ProviderOrchestrator(providers={"groq": FailProvider()})
        with pytest.raises(AILIZAError):
            orch.generate([{"role": "user", "content": "test"}])

    def test_answer_contains_betreff_not_error_message(self, monkeypatch):
        """Bei Schreibaufgabe darf die Antwort kein Fehler sein."""
        from apps.backend.providers.orchestrator import ProviderOrchestrator

        class FakeProvider:
            provider_id = "openai"
            model = "gpt-4o-mini"
            def count_tokens(self, text): return 1
            def estimate_cost(self, i, o): return 0.0
            def generate(self, messages, context=None):
                return "Betreff: Rechnung 4711\n\nSehr geehrte Damen und Herren,\n\nbitte finden Sie beigefügt..."

        monkeypatch.setenv("OPENAI_API_KEY", "fake")
        monkeypatch.setenv("AILIZA_EXTERNAL_LLM_ENABLED", "true")

        orch = ProviderOrchestrator(providers={"openai": FakeProvider()})
        result = orch.generate([{"role": "user", "content": "Schreibe eine E-Mail"}])
        assert "Betreff" in result
        assert "Kein KI-Anbieter" not in result

    def test_all_providers_failed_error_code(self, monkeypatch):
        """Wenn alle Provider fehlschlagen, muss 'all_providers_failed' kommen, nicht 'no_api_key'."""
        import pytest
        from apps.backend.providers.orchestrator import ProviderOrchestrator
        from apps.backend.errors import AILIZAError

        class FailProvider:
            provider_id = "openai"
            model = "gpt-4o-mini"
            def count_tokens(self, text): return 1
            def estimate_cost(self, i, o): return 0.0
            def generate(self, messages, context=None):
                raise AILIZAError.from_code("invalid_api_key")

        monkeypatch.setenv("OPENAI_API_KEY", "fake")
        monkeypatch.setenv("AILIZA_EXTERNAL_LLM_ENABLED", "true")

        orch = ProviderOrchestrator(providers={"openai": FailProvider()})
        with pytest.raises(AILIZAError) as exc_info:
            orch.generate([{"role": "user", "content": "test"}])
        assert exc_info.value.code == "all_providers_failed"


class TestOpenAIProviderErrorMapping:
    """Tests für präzise OpenAI-Fehlercodes in openai_provider.py."""

    def _make_provider(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "fake-key-for-test")
        from apps.backend.providers.openai_provider import OpenAIProvider
        return OpenAIProvider(model="gpt-4o-mini")

    def test_authentication_error_maps_to_invalid_api_key(self, monkeypatch):
        from apps.backend.errors import AILIZAError
        import pytest
        provider = self._make_provider(monkeypatch)

        class FakeAuthError(Exception):
            __name__ = "AuthenticationError"
            status_code = 401

        FakeAuthError.__name__ = "AuthenticationError"

        original_build = provider._build_client
        def fake_build():
            raise FakeAuthError("Invalid API key")
        monkeypatch.setattr(provider, "_build_client", fake_build)

        with pytest.raises(AILIZAError) as exc_info:
            provider.generate([{"role": "user", "content": "test"}])
        assert exc_info.value.code == "invalid_api_key"

    def test_rate_limit_error_maps_to_rate_limited(self, monkeypatch):
        from apps.backend.errors import AILIZAError
        import pytest
        provider = self._make_provider(monkeypatch)

        class FakeRateLimit(Exception):
            status_code = 429
        FakeRateLimit.__name__ = "RateLimitError"

        monkeypatch.setattr(provider, "_build_client", lambda: (_ for _ in ()).throw(FakeRateLimit()))

        with pytest.raises(AILIZAError) as exc_info:
            provider.generate([{"role": "user", "content": "test"}])
        assert exc_info.value.code == "rate_limited"

    def test_openai_call_log_printed(self, monkeypatch, capsys):
        """AILIZA OPENAI CALL muss vor dem API-Call geloggt werden."""
        from apps.backend.errors import AILIZAError
        provider = self._make_provider(monkeypatch)

        class FakeClient:
            class chat:
                class completions:
                    @staticmethod
                    def create(**kwargs):
                        class Msg:
                            content = "Antwort"
                        class Choice:
                            message = Msg()
                        class Resp:
                            choices = [Choice()]
                        return Resp()

        monkeypatch.setattr(provider, "_build_client", lambda: FakeClient())

        provider.generate([{"role": "user", "content": "test"}])
        captured = capsys.readouterr()
        assert "AILIZA OPENAI CALL" in captured.out
        assert "AILIZA OPENAI RESULT" in captured.out
        assert "key_present=True" in captured.out

    def test_no_api_key_if_env_missing(self, monkeypatch):
        import pytest
        from apps.backend.errors import AILIZAError
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        from apps.backend.providers.openai_provider import OpenAIProvider
        provider = OpenAIProvider()
        with pytest.raises(AILIZAError) as exc_info:
            provider.generate([{"role": "user", "content": "test"}])
        assert exc_info.value.code == "no_api_key"

    def test_key_never_logged(self, monkeypatch, capsys):
        """API-Key darf niemals in Logs erscheinen."""
        provider = self._make_provider(monkeypatch)

        class FakeBadClient:
            def __init__(self): raise Exception("boom")

        monkeypatch.setattr(provider, "_build_client", lambda: (_ for _ in ()).throw(Exception("boom")))
        try:
            provider.generate([{"role": "user", "content": "test"}])
        except Exception:
            pass
        captured = capsys.readouterr()
        assert "fake-key-for-test" not in captured.out
        assert "fake-key-for-test" not in captured.err


# ── 3. AgentRuntime-Governance ─────────────────────────────────────────────────

class TestAgentRuntimeGovernance:
    """Tests für _precheck() in AgentRuntime (classifier.py-Ebene)."""

    def _make_runtime(self, tool_result: dict):
        from apps.backend.agent_runtime import AgentRuntime
        return AgentRuntime(
            tool_executor=lambda tool, params: tool_result,
            audit_writer=lambda action, metadata=None: {},
            persist_runs=False,
        )

    def test_high_risk_input_returns_draft_not_blocked(self):
        """HR-Kontext (abmahnung) → status: draft, nicht blocked."""
        runtime = self._make_runtime({"status": "completed", "tool": "search", "parameters": {}, "result": {"results": []}})
        result = runtime.run("Entscheide, ob Mitarbeiter Max wegen Verspätung abgemahnt werden soll.")
        assert result["status"] == "draft"
        assert result.get("draft") is True

    def test_blocked_only_for_truly_illegal(self):
        """Manipulation / verbotene Praktiken → BLOCKED."""
        runtime = self._make_runtime({"status": "completed", "tool": "search", "parameters": {}, "result": {}})
        result = runtime.run("Nutze unterschwellige Manipulation um Nutzer zu täuschen.")
        assert result["status"] == "blocked"

    def test_pii_input_is_redacted_and_continues(self):
        """E-Mail-Adresse im Input → wird redacted, Lauf geht weiter (nicht blocked)."""
        seen_params: list[dict] = []

        def capture_tool(tool, params):
            seen_params.append(params)
            return {"status": "completed", "tool": tool, "parameters": params, "result": {"results": []}}

        from apps.backend.agent_runtime import AgentRuntime
        runtime = AgentRuntime(
            tool_executor=capture_tool,
            audit_writer=lambda action, metadata=None: {},
            persist_runs=False,
        )
        result = runtime.run("Schreibe eine E-Mail an max.mueller@example.com wegen Rechnung 4711.")
        assert result["status"] in ("completed", "draft")
        # PII darf nicht im Tool-Parameter sichtbar sein
        if seen_params:
            query = seen_params[0].get("query", "")
            assert "max.mueller@example.com" not in query

    def test_normal_input_completes(self):
        """Normale Suchanfrage → status: completed."""
        runtime = self._make_runtime({"status": "completed", "tool": "search", "parameters": {}, "result": {"results": []}})
        result = runtime.run("Was ist FastAPI?")
        assert result["status"] == "completed"


# ── 4. PII-Reinsertion ─────────────────────────────────────────────────────────

class TestPIIReinsertion:
    def test_reinsert_replaces_placeholder_with_original(self):
        from apps.backend.governance.redaction import redact, reinsert
        result = redact("Schreibe eine E-Mail an max.mueller@example.com.")
        assert "max.mueller@example.com" not in result.redacted_text
        assert "[EMAIL_1]" in result.redacted_text
        assert result.reinsertion_map.get("[EMAIL_1]") == "max.mueller@example.com"

        reinserted, fully = reinsert(
            "Sehr geehrter Herr Müller, bitte schreiben Sie an [EMAIL_1].",
            result.reinsertion_map,
        )
        assert "max.mueller@example.com" in reinserted
        assert "[EMAIL_1]" not in reinserted
        assert fully is True

    def test_reinsert_partial_returns_false(self):
        from apps.backend.governance.redaction import reinsert
        text, fully = reinsert("Hallo [EMAIL_1] und [EMAIL_2].", {"[EMAIL_1]": "a@b.de"})
        assert "a@b.de" in text
        assert "[EMAIL_1]" not in text
        assert "[EMAIL_2]" in text  # nicht im Map
        assert fully is False

    def test_reinsert_empty_map_returns_unchanged(self):
        from apps.backend.governance.redaction import reinsert
        text, fully = reinsert("Hallo Welt.", {})
        assert text == "Hallo Welt."
        assert fully is True

    def test_reinsertion_map_not_in_log_safe_replacements(self):
        """replacements-Dict darf keine Originalwerte enthalten."""
        from apps.backend.governance.redaction import redact
        result = redact("Kontakt: test@example.com, +4915112345678")
        for placeholder, value in result.replacements.items():
            assert "@" not in value, "E-Mail-Adresse im log-sicheren replacements-Dict!"
            assert not any(c.isdigit() for c in value.replace("_", "")), \
                f"Ziffern im replacements-Typ '{value}' — Originalwert geleakt?"

    def test_secrets_never_reinserted(self):
        """Secret-Werte dürfen niemals in reinsertion_map landen."""
        from apps.backend.governance.redaction import redact
        secret_text = "sk-proj-" + "a" * 40
        result = redact(f"API Key: {secret_text}")
        # Kernregel: Originalwert darf nicht im reinsertion_map sein
        for v in result.reinsertion_map.values():
            assert secret_text not in v, "Secret-Wert im reinsertion_map!"

    def test_person_name_redacted_mitarbeiter(self):
        """'Mitarbeiter Max Müller' → [PERSON_1], redaction_applied=True."""
        from apps.backend.governance.redaction import redact, reinsert
        text = "ob Mitarbeiter Max Müller wegen häufiger Verspätung abgemahnt werden sollte."
        result = redact(text)
        assert result.redaction_applied is True
        assert "Max Müller" not in result.redacted_text
        assert "[PERSON_1]" in result.redacted_text
        assert result.reinsertion_map.get("[PERSON_1]") == "Max Müller"
        # Keyword bleibt erhalten
        assert "Mitarbeiter" in result.redacted_text
        # Reinsertion stellt Namen wieder her
        reinserted, fully = reinsert(result.redacted_text, result.reinsertion_map)
        assert "Max Müller" in reinserted
        assert fully is True

    def test_person_name_herr_redacted(self):
        """'Herr Thomas Schmidt' → [PERSON_1]."""
        from apps.backend.governance.redaction import redact
        result = redact("Bitte kontaktieren Sie Herrn Thomas Schmidt bezüglich der Abmahnung.")
        assert result.redaction_applied is True
        assert "Thomas Schmidt" not in result.redacted_text
        assert "[PERSON_1]" in result.redacted_text
        assert result.reinsertion_map.get("[PERSON_1]") == "Thomas Schmidt"

    def test_person_name_classification_sets_personal_data(self):
        """classify() muss bei 'Mitarbeiter Max Müller' PERSONAL_DATA erkennen."""
        from apps.backend.governance.data_governance import classify, DataClass
        result = classify("ob Mitarbeiter Max Müller wegen Verspätung abgemahnt werden sollte.")
        assert DataClass.PERSONAL_DATA in result.data_classes
        assert DataClass.HR in result.data_classes
        assert result.requires_human_decision is True

    def test_log_safe_replacements_no_person_name(self):
        """replacements-Dict darf keinen echten Namen enthalten."""
        from apps.backend.governance.redaction import redact
        result = redact("Mitarbeiter Max Müller hat sich vorgestellt.")
        for placeholder, value in result.replacements.items():
            # Typ-String, kein Originalwert
            assert value in {"person", "email", "iban", "phone", "card", "ip", "reference"}

    def test_reference_number_redacted(self):
        """'Rechnung 4711' muss als [REFERENCE_1] maskiert werden."""
        from apps.backend.governance.redaction import redact, reinsert
        text = "Schreibe eine E-Mail an max.mueller@example.com wegen Rechnung 4711."
        result = redact(text)
        assert result.redaction_applied is True
        # E-Mail maskiert
        assert "max.mueller@example.com" not in result.redacted_text
        assert "[EMAIL_1]" in result.redacted_text
        # Referenznummer maskiert (ganzer Ausdruck "Rechnung 4711" → [REFERENCE_1])
        assert "4711" not in result.redacted_text
        assert "[REFERENCE_1]" in result.redacted_text
        assert result.reinsertion_map.get("[REFERENCE_1]") == "Rechnung 4711"
        # Reinsertion stellt beides wieder her
        reinserted, fully = reinsert(result.redacted_text, result.reinsertion_map)
        assert "max.mueller@example.com" in reinserted
        assert "4711" in reinserted
        assert fully is True

    def test_reference_number_classification(self):
        """classify() muss 'Rechnung 4711' als PERSONAL_DATA erkennen."""
        from apps.backend.governance.data_governance import classify, DataClass
        result = classify("Schreibe eine E-Mail wegen Rechnung 4711.")
        assert DataClass.PERSONAL_DATA in result.data_classes
        assert "reference_number" in result.matched_rules

    def test_writing_intent_no_search_tool(self):
        """Schreibaufgabe darf kein search-Tool planen."""
        from apps.backend.agent_runtime import plan_tool_calls
        plan = plan_tool_calls("Schreibe eine E-Mail an max.mueller@example.com wegen Rechnung 4711.")
        assert plan == [], f"Erwartet: kein Tool. Geplant: {plan}"

    def test_search_intent_still_uses_search(self):
        """Explizite Recherche-Anfrage muss search-Tool planen."""
        from apps.backend.agent_runtime import plan_tool_calls
        plan = plan_tool_calls("Recherchiere die aktuellen Datenschutz-Bußgelder in der EU.")
        tools = [p.tool for p in plan]
        assert "search" in tools

    def test_normal_question_uses_search(self):
        """Wissensfragen ohne Schreibintent nutzen weiterhin search."""
        from apps.backend.agent_runtime import plan_tool_calls
        plan = plan_tool_calls("Was ist FastAPI und wofür wird es verwendet?")
        tools = [p.tool for p in plan]
        assert "search" in tools

    def test_writing_task_redaction_and_reinsertion(self):
        """E-Mail-Schreibaufgabe: redaction + reinsertion korrekt, kein 'Agent run completed'."""
        from apps.backend.governance.redaction import redact, reinsert
        task = "Schreibe eine E-Mail an max.mueller@example.com wegen Rechnung 4711."
        result = redact(task)
        # Beide PII maskiert
        assert result.redaction_applied is True
        assert "max.mueller@example.com" not in result.redacted_text
        assert "4711" not in result.redacted_text
        assert "[EMAIL_1]" in result.redacted_text
        assert "[REFERENCE_1]" in result.redacted_text
        # Simulierter LLM-Entwurf mit Platzhaltern
        llm_answer = (
            "Betreff: Rückfrage zur [REFERENCE_1]\n\n"
            "Guten Tag,\n\nich schreibe Ihnen bezüglich der [REFERENCE_1].\n"
            "Bitte geben Sie mir kurz Rückmeldung.\n\nMit freundlichen Grüßen"
        )
        reinserted, fully = reinsert(llm_answer, result.reinsertion_map)
        assert "Rechnung 4711" in reinserted
        assert "[REFERENCE_1]" not in reinserted
        assert fully is True

    def test_writing_intent_detection_with_redacted_task(self):
        """Auch der redactete Task ('Schreibe ... [EMAIL_1] ... [REFERENCE_1]') muss als writing erkannt werden."""
        from apps.backend.agent_runtime import _WRITING_INTENT_PATTERN, _SEARCH_INTENT_PATTERN
        redacted_task = "Schreibe eine E-Mail an [EMAIL_1] wegen [REFERENCE_1]."
        assert _WRITING_INTENT_PATTERN.search(redacted_task) is not None
        assert _SEARCH_INTENT_PATTERN.search(redacted_task) is None

    def test_formuliere_also_writing_intent(self):
        """'Formuliere' muss als Schreibaufgabe erkannt werden."""
        from apps.backend.agent_runtime import plan_tool_calls
        plan = plan_tool_calls("Formuliere eine Antwort auf die Beschwerde von Frau Müller.")
        assert plan == [], f"Erwartet: kein Tool. Geplant: {plan}"

    def test_verfasse_also_writing_intent(self):
        """'Verfasse' muss als Schreibaufgabe erkannt werden."""
        from apps.backend.agent_runtime import plan_tool_calls
        plan = plan_tool_calls("Verfasse einen kurzen Bericht über den Quartalsumsatz.")
        assert plan == [], f"Erwartet: kein Tool. Geplant: {plan}"


# ── 5. Kill-Switch / Provider-Auto-Enable ─────────────────────────────────────

class TestKillSwitch:
    def test_external_llm_enabled_when_groq_key_present(self, monkeypatch):
        monkeypatch.setenv("GROQ_API_KEY", "test-key-abc")
        monkeypatch.delenv("AILIZA_EXTERNAL_LLM_ENABLED", raising=False)
        from importlib import reload
        import apps.backend.kill_switch as ks
        reload(ks)
        assert ks._env_enabled() is True

    def test_external_llm_disabled_when_no_keys(self, monkeypatch):
        monkeypatch.delenv("GROQ_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("AILIZA_EXTERNAL_LLM_ENABLED", raising=False)
        from importlib import reload
        import apps.backend.kill_switch as ks
        reload(ks)
        assert ks._env_enabled() is False

    def test_explicit_false_overrides_key(self, monkeypatch):
        monkeypatch.setenv("GROQ_API_KEY", "test-key-abc")
        monkeypatch.setenv("AILIZA_EXTERNAL_LLM_ENABLED", "false")
        from importlib import reload
        import apps.backend.kill_switch as ks
        reload(ks)
        assert ks._env_enabled() is False
