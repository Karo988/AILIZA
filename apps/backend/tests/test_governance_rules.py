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
    """
    Stand Freigabe Stufe 1 (P-A, 2026-07-02): Groq/OpenAI/Anthropic haben
    avv_signed=False. Ohne unterzeichneten AVV (DSGVO Art. 28) duerfen sie
    KEINE Datenklasse mehr verarbeiten, ausser der serverseitige Testmodus
    ist aktiv UND die Datenklasse ist PUBLIC/SYNTHETIC/DEMO (siehe
    test_avv_test_mode.py fuer die volle Akzeptanztabelle). Diese Tests
    pruefen ausschliesslich das AVV-unabhaengige Verhalten (Credentials/
    Special-Category-Block, Use-Case-Gate, lokaler Provider).
    """

    def test_groq_blocks_public_without_avv_or_test_mode(self, monkeypatch):
        monkeypatch.delenv("AILIZA_TEST_MODE", raising=False)
        allowed, reason = check_provider_policy("groq", [DataClass.PUBLIC])
        assert not allowed
        assert "AVV" in reason or "avv" in reason.lower()

    def test_groq_allows_public_with_test_mode(self, monkeypatch):
        monkeypatch.setenv("AILIZA_TEST_MODE", "true")
        allowed, reason = check_provider_policy("groq", [DataClass.PUBLIC])
        assert allowed, reason
        monkeypatch.delenv("AILIZA_TEST_MODE", raising=False)

    def test_groq_blocks_personal_data_without_avv(self, monkeypatch):
        """Ohne unterzeichneten AVV darf Groq PERSONAL_DATA nicht mehr
        verarbeiten (Freigabe Stufe 1, P-A) — auch nicht im Testmodus, da
        PERSONAL_DATA keine exempte Klasse ist (Haertung 2)."""
        monkeypatch.setenv("AILIZA_TEST_MODE", "true")
        allowed, reason = check_provider_policy("groq", [DataClass.PERSONAL_DATA])
        assert not allowed
        monkeypatch.delenv("AILIZA_TEST_MODE", raising=False)

    def test_groq_blocks_hr_without_avv(self, monkeypatch):
        monkeypatch.setenv("AILIZA_TEST_MODE", "true")
        allowed, reason = check_provider_policy("groq", [DataClass.HR])
        assert not allowed
        monkeypatch.delenv("AILIZA_TEST_MODE", raising=False)

    def test_groq_blocks_credentials(self):
        allowed, _ = check_provider_policy("groq", [DataClass.CREDENTIALS])
        assert not allowed

    def test_groq_blocks_special_category(self):
        allowed, _ = check_provider_policy("groq", [DataClass.SPECIAL_CATEGORY])
        assert not allowed

    def test_anthropic_allows_personal_data_with_documented_avv(self, monkeypatch):
        """Betreiber-Entscheidung 2026-07-06: Anthropic AVV/DPA als vorhanden
        dokumentiert (avv_signed=True) — PERSONAL_DATA ist damit auch OHNE
        Testmodus erlaubt (Redaction-Gate greift unabhaengig davon weiterhin)."""
        monkeypatch.delenv("AILIZA_TEST_MODE", raising=False)
        allowed, reason = check_provider_policy("anthropic", [DataClass.PERSONAL_DATA])
        assert allowed, reason

    def test_local_allows_all(self):
        for dc in DataClass:
            allowed, _ = check_provider_policy("local", [dc])
            assert allowed, f"local should allow {dc}"

    def test_groq_allows_text_generation_with_test_mode(self, monkeypatch):
        """Groq muss text_generation als Use Case erlauben (Schreibaufgaben) —
        AVV-Gate greift unabhaengig davon fuer PUBLIC ohne Testmodus."""
        monkeypatch.setenv("AILIZA_TEST_MODE", "true")
        allowed, reason = check_provider_policy("groq", [DataClass.PUBLIC], use_case="text_generation")
        assert allowed, reason
        monkeypatch.delenv("AILIZA_TEST_MODE", raising=False)

    def test_openai_profile_exists_and_active(self):
        from apps.backend.providers.provider_profiles import get_profile
        profile = get_profile("openai")
        assert profile is not None
        assert profile.active is True
        assert not profile.admin_disabled

    def test_openai_allows_text_generation_with_test_mode(self, monkeypatch):
        monkeypatch.setenv("AILIZA_TEST_MODE", "true")
        allowed, reason = check_provider_policy("openai", [DataClass.PUBLIC], use_case="text_generation")
        assert allowed, reason
        monkeypatch.delenv("AILIZA_TEST_MODE", raising=False)

    def test_openai_allows_personal_data_with_documented_avv(self, monkeypatch):
        """Betreiber-Entscheidung 2026-07-06: OpenAI AVV/DPA als vorhanden
        dokumentiert (avv_signed=True) — PERSONAL_DATA ist damit auch OHNE
        Testmodus erlaubt (Redaction-Gate greift unabhaengig davon weiterhin)."""
        monkeypatch.delenv("AILIZA_TEST_MODE", raising=False)
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
        """
        Groq 403 blockiert nicht OpenAI.
        Auch wenn Groq health_status=down hat (→ openai geht vor), muss
        mindestens einer der Provider antworten.
        Wenn beide Provider vorhanden sind und Groq fail-coded ist,
        muss OpenAI die Antwort liefern.
        """
        from apps.backend.providers.orchestrator import ProviderOrchestrator
        from apps.backend.errors import AILIZAError

        calls = []

        class FakeGroq:
            provider_id = "groq"
            model = "test-groq"
            def count_tokens(self, text): return 1
            def estimate_cost(self, i, o): return 0.0
            def generate(self, messages, context=None):
                calls.append("groq")
                raise AILIZAError.from_code("provider_forbidden",
                                             safe_alternatives=["Groq: HTTP 403"])

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
        # PUBLIC-Daten ohne unterzeichneten AVV nur im Testmodus erlaubt (P-A)
        monkeypatch.setenv("AILIZA_TEST_MODE", "true")

        orch = ProviderOrchestrator(providers={"groq": FakeGroq(), "openai": FakeOpenAI()})
        result = orch.generate([{"role": "user", "content": "Schreibe eine E-Mail"}])
        # OpenAI muss angeworfen worden sein (ob vor oder nach Groq)
        assert "openai" in calls
        assert "Betreff" in result
        # Wenn Groq trotzdem versucht wurde (z.B. als letzter Fallback), darf es nicht blockieren
        if "groq" in calls:
            assert "openai" in calls, "OpenAI muss nach Groq-Fehler versucht werden"

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
        monkeypatch.setenv("AILIZA_TEST_MODE", "true")

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
        monkeypatch.setenv("AILIZA_TEST_MODE", "true")

        orch = ProviderOrchestrator(providers={"openai": FailProvider()})
        with pytest.raises(AILIZAError) as exc_info:
            orch.generate([{"role": "user", "content": "test"}])
        assert exc_info.value.code == "all_providers_failed"


class TestOpenAIProviderErrorMapping:
    """Tests für präzise OpenAI-Fehlercodes in openai_provider.py (urllib-basiert, kein SDK)."""

    def _make_provider(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "fake-key-for-test")
        from apps.backend.providers.openai_provider import OpenAIProvider
        return OpenAIProvider(model="gpt-4o-mini")

    def _http_error(self, code: int) -> "urllib.error.HTTPError":
        import json, urllib.error
        from unittest.mock import MagicMock
        fp = MagicMock()
        fp.read.return_value = json.dumps({"error": {"message": "test"}}).encode()
        return urllib.error.HTTPError("https://api.openai.com/...", code, f"HTTP {code}", MagicMock(), fp)

    def test_authentication_error_maps_to_invalid_api_key(self, monkeypatch):
        import pytest, urllib.error
        from unittest.mock import patch
        from apps.backend.errors import AILIZAError
        provider = self._make_provider(monkeypatch)

        with patch("urllib.request.urlopen", side_effect=self._http_error(401)):
            with pytest.raises(AILIZAError) as exc_info:
                provider.generate([{"role": "user", "content": "test"}])
        assert exc_info.value.code == "invalid_api_key"

    def test_rate_limit_error_maps_to_rate_limited(self, monkeypatch):
        import pytest
        from unittest.mock import patch
        from apps.backend.errors import AILIZAError
        provider = self._make_provider(monkeypatch)

        with patch("urllib.request.urlopen", side_effect=self._http_error(429)):
            with pytest.raises(AILIZAError) as exc_info:
                provider.generate([{"role": "user", "content": "test"}])
        assert exc_info.value.code == "rate_limited"

    def test_openai_call_log_printed(self, monkeypatch, capsys):
        """AILIZA OPENAI CALL und RESULT müssen geloggt werden."""
        import json
        from unittest.mock import MagicMock, patch
        provider = self._make_provider(monkeypatch)

        mock_resp = MagicMock()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_resp.read.return_value = json.dumps({
            "choices": [{"message": {"content": "Antwort"}}]
        }).encode()

        with patch("urllib.request.urlopen", return_value=mock_resp):
            provider.generate([{"role": "user", "content": "test"}])

        captured = capsys.readouterr()
        assert "AILIZA OPENAI CALL" in captured.out
        assert "AILIZA OPENAI RESULT" in captured.out

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
        from unittest.mock import patch
        provider = self._make_provider(monkeypatch)

        with patch("urllib.request.urlopen", side_effect=self._http_error(500)):
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

    def test_reinsert_resolves_nested_placeholders(self):
        """
        Karo-Fund 2026-07-12: Wenn der Wert eines Platzhalters selbst einen
        anderen (bereits bekannten) Platzhalter als Literal-Text enthaelt,
        muss reinsert() das ueber mehrere Durchlaeufe korrekt aufloesen —
        nicht nur, wenn die Verarbeitungsreihenfolge zufaellig passt.
        """
        from apps.backend.governance.redaction import reinsert
        # Worst-Case-Reihenfolge: der AEUSSERE Platzhalter [OUTER_1] wird vor
        # dem darin enthaltenen [INNER_1] verarbeitet — ein Einzel-Durchlauf
        # wuerde [INNER_1] frisch einfuegen und nie wieder aufloesen.
        text = "Ergebnis: [OUTER_1]"
        reinsertion_map = {
            "[OUTER_1]": "Wert enthaelt [INNER_1] als Text",
            "[INNER_1]": "den echten inneren Wert",
        }
        reinserted, fully = reinsert(text, reinsertion_map)
        assert "[INNER_1]" not in reinserted
        assert "[OUTER_1]" not in reinserted
        assert "den echten inneren Wert" in reinserted
        assert fully is True

    def test_reinsert_nested_placeholder_loop_has_limit(self):
        """Ein Platzhalter, der sich selbst referenziert, darf keine
        Endlosschleife verursachen — Schleifen-Limit muss greifen."""
        from apps.backend.governance.redaction import reinsert
        text = "Start [A_1]"
        reinsertion_map = {"[A_1]": "Text mit [A_1] drin"}
        # Darf nicht haengen bleiben — reines Terminierungsverhalten wird geprueft.
        reinserted, fully = reinsert(text, reinsertion_map)
        assert isinstance(reinserted, str)

    def test_end_to_end_reply_mail_no_placeholders_leak(self, monkeypatch):
        """
        Karo-Fund 2026-07-12 (End-zu-End-Reproduktion): 'Antwort-Mail an
        mueller@example.com ... von Herrn Mueller' loeste durch das zu
        allgemeine 'Antwort'-Schluesselwort im credential-Muster eine
        verschachtelte Platzhalter-Situation aus. Die Nutzer-Antwort MUSS
        die echten Werte enthalten, KEINE Platzhalter-Reste.
        """
        import os as _os
        _os.environ.setdefault("AILIZA_SECRET_KEY", "test-secret-key-minimum-32-chars-ok")
        _os.environ.setdefault("AILIZA_DATABASE_URL", "sqlite:///:memory:")
        monkeypatch.setenv("AILIZA_EXTERNAL_LLM_ENABLED", "true")
        monkeypatch.setenv("AILIZA_TEST_MODE", "true")

        from fastapi.testclient import TestClient
        from apps.backend.main import app, _orchestrator
        from apps.backend.database import init_db, metadata_obj, engine
        metadata_obj.drop_all(engine)
        init_db()

        class EchoProvider:
            model = "echo-test"
            def count_tokens(self, text):
                return len(text.split())
            def generate(self, messages, context=None, **kwargs):
                last_user = [m["content"] for m in messages if m["role"] == "user"][-1]
                return f"Sehr geehrter {last_user}, vielen Dank fuer Ihre Nachricht."

        # monkeypatch.setattr statt direkter Zuweisung -- setzt den
        # ORIGINALEN _get_provider_order nach dem Test automatisch zurueck
        # (Karo-Fund 2026-07-12: direkte Zuweisung ohne Rueckgabe verschmutzte
        # globalen Modul-Zustand und liess spaetere Tests im selben Lauf
        # fehlschlagen, z.B. test_provider_order_env_respected).
        monkeypatch.setitem(_orchestrator.providers, "groq", EchoProvider())
        import apps.backend.providers.orchestrator as orch_mod
        monkeypatch.setattr(orch_mod, "_get_provider_order", lambda: ["groq"])

        client = TestClient(app, cookies={})
        client.post("/auth/self-register", json={"user_id": "e2ereinsert", "password": "SicherPass1!Xyz"})
        client.post("/auth/login", json={"user_id": "e2ereinsert", "password": "SicherPass1!Xyz"})

        task = "Schreibe eine Antwort-Mail an mueller@example.com bezueglich seiner Anfrage von Herrn Mueller."
        resp = client.post("/agent/run", json={"task": task})
        assert resp.status_code == 200
        answer = resp.json().get("ai_response") or resp.json().get("message") or ""
        assert "mueller@example.com" in answer
        assert "Herrn Mueller" in answer
        assert "[" not in answer, f"Platzhalter-Rest in der Antwort: {answer!r}"

    def test_antwort_credential_requires_colon(self):
        """
        Karo-Entscheidung 2026-07-12 (Option 1): 'Antwort' bleibt im
        credential-Muster, aber der Doppelpunkt ist Pflicht. 'Antwort-Mail'
        (kein Doppelpunkt) darf NICHT matchen, 'Antwort: Lucky'
        (Sicherheitsfrage) MUSS weiterhin geschwaerzt werden.
        """
        from apps.backend.governance.redaction_v2 import RedactionEngineV2
        r1 = RedactionEngineV2().redact(
            "Schreibe eine Antwort-Mail an mueller@example.com von Herrn Mueller."
        )
        assert "mueller@example.com" not in r1.redacted_text
        assert "Herrn Mueller" not in r1.redacted_text
        # Der Rest des Satzes ("Antwort-Mail an ... von ...") darf NICHT als
        # ein einziger Zugangsdaten-Block verschluckt worden sein.
        assert "Zugangsdaten" not in r1.redacted_text

        r2 = RedactionEngineV2().redact(
            "* Sicherheitsfrage: Name des ersten Haustieres\n* Antwort: Lucky"
        )
        assert "Lucky" not in r2.redacted_text
        assert "Zugangsdaten" in r2.redacted_text

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

    def test_knowledge_question_goes_direct_to_llm(self):
        """Wissensfragen (was ist, erkläre) gehen direkt ans LLM — kein search-Tool."""
        from apps.backend.agent_runtime import plan_tool_calls
        plan = plan_tool_calls("Was ist FastAPI und wofür wird es verwendet?")
        tools = [p.tool for p in plan]
        assert "search" not in tools, (
            "Einfache Wissensfragen sollen direkt ans LLM, nicht zur Websuche"
        )

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


# ── Karo-Fund 2026-07-13: Name ohne Anrede + europaeische Adressen ────────────
class TestNameContextAndEuropeanAddressRedaction:
    """
    Befund: "schreibe eine E-Mail, möchte kontakt mit paul sender in der
    Mathestr. 12 in 15823 Pingelhausen" liess Name ("paul") und Strasse
    ("Mathestr. 12") unredigiert durch, weil (a) die Namens-Muster eine
    Anrede + Grossschreibung voraussetzten und (b) das Adress-Muster nur
    die vollen Formen "strasse/straße" kannte, nicht die Abkuerzung "str.".
    Betreiber-Entscheidung: Option B (Namen auch ohne Anrede/Grossschreibung
    erkennen, aber nur mit engem Kontext-Ausloeser) + lokale, sprachueber-
    greifende Adress-Heuristik ohne externe Validierung (Datensparsamkeit).
    """

    def _redact(self, text: str) -> str:
        from apps.backend.governance.redaction_v2 import RedactionEngineV2
        return RedactionEngineV2().redact(text).redacted_text

    def test_original_karo_fund_case_fully_redacted(self):
        text = ("schreibe eine E-Mail, möchte kontakt mit paul sender in der "
                "Mathestr. 12 in 15823 Pingelhausen")
        result = self._redact(text)
        assert "paul" not in result
        assert "sender" not in result
        assert "Mathestr" not in result
        assert "Pingelhausen" not in result
        assert "[Name]" in result
        assert "[Adresse]" in result
        assert "[Ort]" in result

    def test_name_context_lowercase_without_title(self):
        result = self._redact("Bitte kontaktiere klaus mueller wegen des Projekts.")
        assert "klaus" not in result
        assert "mueller" not in result
        assert "[Name]" in result

    def test_name_context_false_positive_guard_pronoun(self):
        result = self._redact("Schreibe an ihn direkt, das ist dringend.")
        assert result == "Schreibe an ihn direkt, das ist dringend."

    def test_name_context_false_positive_guard_generic_phrase(self):
        result = self._redact("Wir sind in Kontakt mit anderen Abteilungen.")
        assert result == "Wir sind in Kontakt mit anderen Abteilungen."

    def test_name_context_false_positive_guard_no_trigger(self):
        result = self._redact("Berlin Mitte ist ein Stadtteil.")
        assert result == "Berlin Mitte ist ein Stadtteil."

    def test_address_abbreviation_str_punkt(self):
        result = self._redact("Die Adresse lautet Mathestr. 12.")
        assert "Mathestr" not in result
        assert "[Adresse]" in result

    def test_address_english_number_first_format(self):
        result = self._redact("Bitte senden an 12 Main Street, 90210 Los Angeles.")
        assert "Main Street" not in result
        assert "Los Angeles" not in result
        assert "[Adresse]" in result
        assert "[Ort]" in result

    def test_address_french_prefix_format(self):
        result = self._redact("Rue de la Paix 12, 75001 Paris")
        assert "Rue de la Paix" not in result
        assert "Paris" not in result
        assert "[Adresse]" in result
        assert "[Ort]" in result

    def test_existing_antwort_lucky_still_blocked(self):
        # Regression: der frueher gefixte "Antwort"-Credential-Fall
        # (f2913c3) darf durch die neuen Muster nicht beeinflusst werden.
        result = self._redact("Antwort: Lucky")
        assert result == "[Zugangsdaten]"

    def test_existing_antwort_mail_case_still_correct(self):
        # Regression: verschachtelte Platzhalter-Situation (f2913c3) darf
        # durch das neue name_context-Muster nicht wieder auftreten.
        result = self._redact("Antwort-Mail an mueller@example.com von Herrn Mueller")
        assert "mueller@example.com" not in result
        assert "[E-Mail]" in result
        assert "[Name]" in result

    def test_credential_60_char_cutoff_bug_fixed(self):
        # Karo-Fund 2026-07-14 (Golden-Brief): "Passwort: <langer Wert>"
        # wurde bei >60 Zeichen mitten im Wort abgeschnitten, sodass ein
        # unredigiertes Rest-Fragment hinter dem Platzhalter stehen blieb.
        text = "Passwort: Xy9!Zz-supergeheim-lang (kommt da nicht mehr rein!)"
        result = self._redact(text)
        assert result == "[Zugangsdaten]"
        assert "rein!)" not in result
        assert "ht mehr" not in result


# ── Karo-Fund 2026-07-14: mehrsprachige Redaction BG/CZ (Golden-Brief) ────────
class TestMultilingualRedactionBgCz:
    """
    Golden-Brief-Befund: Namens-/Adress-/Diagnose-Angaben in Bulgarisch
    (kyrillisch) und Tschechisch (Diakritika) rutschten unredigiert durch,
    weil alle Muster deutsche Schluesselwoerter + lateinische Zeichen-
    klassen voraussetzten. Betreiber-Entscheidung (Option 1): gezielt nur
    BG/CZ ergaenzen, nicht EU-weit. Label-basiert + Wert bis Zeilenende.
    """

    def _redact(self, text: str) -> str:
        from apps.backend.governance.redaction_v2 import RedactionEngineV2
        return RedactionEngineV2().redact(text).redacted_text

    def test_bulgarian_name_redacted(self):
        result = self._redact("Име: Димитър Иванов (Dimitar Ivanov)")
        assert "Димитър" not in result
        assert "Иванов" not in result
        assert "Dimitar" not in result
        assert "[Name]" in result

    def test_bulgarian_address_redacted(self):
        result = self._redact('Адрес: ул. "Граф Игнатиев" 15, 1000 София')
        assert "Граф Игнатиев" not in result
        assert "София" not in result
        assert "1000" not in result
        assert "[Adresse]" in result

    def test_bulgarian_diagnosis_redacted(self):
        result = self._redact(
            "Диагноза: Диабет тип 2, необходимо е ежедневно проследяване."
        )
        assert "Диабет" not in result
        assert "проследяване" not in result
        assert "GESCHWAERZT" in result

    def test_czech_name_redacted(self):
        result = self._redact("Jméno: Jan Novák")
        assert "Novák" not in result
        assert "[Name]" in result

    def test_czech_address_redacted(self):
        result = self._redact("Adresa: Na Příkopě 854/14, 110 00 Praha 1")
        assert "Příkopě" not in result
        assert "Praha" not in result
        assert "[Adresse]" in result

    def test_czech_diagnosis_redacted(self):
        result = self._redact(
            "Diagnóza: Diagnostikována klinická deprese, farmakologická léčba."
        )
        assert "deprese" not in result
        assert "léčba" not in result
        assert "GESCHWAERZT" in result

    def test_german_address_still_finegrained(self):
        # Regression: das deutsche "Adresse:" darf NICHT vom intl-Label
        # erfasst werden — feine Aufloesung [Adresse] + [Ort] bleibt.
        result = self._redact("Adresse: Hauptstr. 5, 10115 Berlin")
        assert "Hauptstr" not in result
        assert "Berlin" not in result
        assert "[Adresse]" in result
        assert "[Ort]" in result


# ── Karo-Fund 2026-07-15: User-Label, Serverpfad, Kontostand (Golden-Brief) ──
class TestCredentialPathAndBalanceRedaction:
    """
    Golden-Brief-Nachtest: "User: admin_root" und
    "Pfad: /var/www/internal/data/health_records_2026/" blieben unredigiert
    (Root-Zugang zu einem Server mit Patientenakten im Klartext an die KI).
    Ausserdem blieb der zur IBAN gehoerende Kontostand ungeschwaerzt.
    """

    def _redact(self, text: str) -> str:
        from apps.backend.governance.redaction_v2 import RedactionEngineV2
        return RedactionEngineV2().redact(text).redacted_text

    def test_english_user_label_redacted(self):
        result = self._redact("User: admin_root")
        assert "admin_root" not in result
        assert "[Zugangsdaten]" in result

    def test_username_label_redacted(self):
        result = self._redact("Username: admin_root")
        assert "admin_root" not in result
        assert "[Zugangsdaten]" in result

    def test_german_benutzername_still_works(self):
        # Regression: bestehendes deutsches Label darf nicht brechen.
        result = self._redact("Benutzername: karo123")
        assert "karo123" not in result
        assert "[Zugangsdaten]" in result

    def test_server_path_redacted(self):
        result = self._redact("Pfad: /var/www/internal/data/health_records_2026/")
        assert "health_records" not in result
        assert "[Systempfad]" in result

    def test_english_path_label_redacted(self):
        result = self._redact("Path: /etc/secrets/db.conf")
        assert "db.conf" not in result
        assert "[Systempfad]" in result

    def test_iban_with_german_balance_fully_redacted(self):
        result = self._redact("Konto: DE89370400440532013000, Stand: 42.500,20 EUR")
        assert "42.500,20" not in result
        assert "EUR" not in result
        assert "[IBAN]" in result

    def test_iban_with_bulgarian_balance_fully_redacted(self):
        result = self._redact("Сметка: BG80BNBG96611020345678, салдо: 12.450,00 BGN")
        assert "12.450,00" not in result
        assert "BGN" not in result
        assert "[IBAN]" in result

    def test_iban_with_czech_balance_fully_redacted(self):
        result = self._redact("Účet: CZ6508000000192000145399, zůstatek: 850.000,00 CZK")
        assert "850.000,00" not in result
        assert "CZK" not in result
        assert "[IBAN]" in result

    def test_iban_without_balance_still_works(self):
        # Regression: IBAN allein (ohne Kontostand-Zusatz) muss weiter
        # erkannt werden.
        result = self._redact("IBAN: DE89370400440532013000")
        assert "DE89370400440532013000" not in result
        assert "[IBAN]" in result

    def test_full_golden_brief_credential_block(self):
        text = (
            "Pfad: /var/www/internal/data/health_records_2026/\n\n"
            "User: admin_root\n\n"
            "Passwort: geheim123"
        )
        result = self._redact(text)
        assert "health_records" not in result
        assert "admin_root" not in result
        assert "geheim123" not in result


# ── Karo-Fund 2026-07-16: BaFin-/Riga-Kontrollbriefe (mehrsprachig) ──────────
class TestBaFinRigaControlBriefRedaction:
    """
    Zwei neue Kontrollbriefe deckten weitere Luecken auf: englische
    Zugangs-Labels (Password/Login), Chemotherapie, freistehende Konto-
    staende/Beitraege, Zoll-ID, Steuer-Straftatverdacht (Art. 10), und
    fehlender BLACK-Trigger bei englischem "automated"/"risk". Alle als
    gezielte Inline-Schwaerzung (keine Pauschal-Blockade).
    """

    def _redact(self, text: str):
        from apps.backend.governance.redaction_v2 import RedactionEngineV2
        return RedactionEngineV2().redact(text)

    def test_english_password_label_redacted(self):
        r = self._redact("Password: Qwerty_2026_Secure!")
        assert "Qwerty_2026_Secure" not in r.redacted_text
        assert "[Zugangsdaten]" in r.redacted_text

    def test_english_login_label_redacted(self):
        r = self._redact("Login: root_admin_latvia")
        assert "root_admin_latvia" not in r.redacted_text
        assert "[Zugangsdaten]" in r.redacted_text

    def test_chemotherapie_is_health_art9(self):
        r = self._redact("Versicherungsstatus: Chemotherapie-Plan Q3/Q4 hinterlegt.")
        assert "Chemotherapie" not in r.redacted_text
        assert "Gesundheit - Art. 9" in r.redacted_text

    def test_standalone_yearly_fee_redacted(self):
        r = self._redact("Jahresbeitrag: 14.500,00 EUR")
        assert "14.500,00" not in r.redacted_text
        assert "[Finanzangabe]" in r.redacted_text

    def test_latvian_balance_label_redacted(self):
        r = self._redact("Atlikums (Kontostand): 55.400,00 EUR")
        assert "55.400,00" not in r.redacted_text
        assert "[Finanzangabe]" in r.redacted_text

    def test_zoll_id_redacted(self):
        r = self._redact("Zoll-ID: LV-10029384756")
        assert "LV-10029384756" not in r.redacted_text

    def test_tax_fraud_suspicion_is_art10(self):
        r = self._redact("Betriebsprüfung: Verdacht auf unberechtigten Vorsteuerabzug.")
        assert "Art. 10" in r.redacted_text

    def test_neutral_tax_topic_not_flagged_as_art10(self):
        # Regression: harmlose Steuerfrage darf NICHT als Art.-10-Straftat gelten.
        r = self._redact("Wie funktioniert der Vorsteuerabzug allgemein?")
        assert "Art. 10" not in r.redacted_text

    def test_english_automated_risk_triggers_black(self):
        r = self._redact(
            "Please prepare automated reporting for these High-Risk profiles."
        )
        assert r.level.value == "black"

    def test_versicherungsnehmer_name_redacted(self):
        r = self._redact("Versicherungsnehmer: Thomas Müller-Lüdenscheid")
        assert "Müller-Lüdenscheid" not in r.redacted_text
        assert "[Name]" in r.redacted_text
