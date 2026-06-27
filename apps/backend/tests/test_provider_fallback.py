"""
Provider-Fallback und Fehler-Diagnose Tests
============================================
Prüft:
1. external_llm_allowed=True, Groq wirft Fehler → OpenAI wird versucht
2. Groq + OpenAI fehlschlagen → final_error enthält beide Ursachen
3. Nicht-personenbezogene Schreibaufgabe → external LLM-Pfad erreichbar
4. Personenbezogene Anfrage → bleibt lokal / approval
5. all_providers_failed enthält sanitisierte Ursachen, keine Secrets
6. GROQ_MODEL-Env hat Vorrang — Default ist llama-3.1-8b-instant
"""
from __future__ import annotations

import os

os.environ.setdefault("AILIZA_SECRET_KEY", "test-secret-key-minimum-32-chars-ok")
os.environ.setdefault("AILIZA_DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("AILIZA_EXTERNAL_LLM_ENABLED", "true")
os.environ.setdefault("GROQ_API_KEY", "test-groq-key")
os.environ.setdefault("OPENAI_API_KEY", "test-openai-key")

import pytest
from apps.backend.errors import AILIZAError
from apps.backend.providers.orchestrator import ProviderOrchestrator
from apps.backend.providers.base import LLMProvider
from apps.backend.governance.data_governance import DataClass


# ── Fake Provider Helpers ─────────────────────────────────────────────────────

class _OKProvider(LLMProvider):
    def __init__(self, pid: str, answer: str = "AILIZA_PROVIDER_OK"):
        self.provider_id = pid
        self._answer = answer

    @property
    def max_context_tokens(self) -> int:
        return 4096

    def generate(self, messages, context=None) -> str:
        return self._answer

    def stream(self, messages, context=None):
        yield self._answer


class _FailProvider(LLMProvider):
    def __init__(self, pid: str, code: str = "provider_error", detail: str = ""):
        self.provider_id = pid
        self._code = code
        self._detail = detail or f"{pid}: test-Fehler"

    @property
    def max_context_tokens(self) -> int:
        return 4096

    def generate(self, messages, context=None) -> str:
        raise AILIZAError.from_code(self._code, safe_alternatives=[self._detail])

    def stream(self, messages, context=None):
        raise AILIZAError.from_code(self._code, safe_alternatives=[self._detail])


# ── 1. Groq fehlschlägt → OpenAI wird versucht ───────────────────────────────

class TestProviderFallback:

    def test_groq_fails_openai_succeeds(self, monkeypatch):
        """Wenn Groq fehlschlägt, muss OpenAI als Fallback genutzt werden."""
        monkeypatch.setenv("AILIZA_EXTERNAL_LLM_ENABLED", "true")
        monkeypatch.setenv("GROQ_API_KEY", "fake")
        monkeypatch.setenv("OPENAI_API_KEY", "fake")
        import apps.backend.registry.registry_loader as rl
        rl._registry = None

        orch = ProviderOrchestrator(providers={
            "groq": _FailProvider("groq", code="provider_forbidden",
                                  detail="Groq: Modell nicht im Plan (HTTP 403)"),
            "openai": _OKProvider("openai", "OpenAI-Antwort"),
        })
        result = orch.generate([{"role": "user", "content": "Test"}])
        assert result == "OpenAI-Antwort"

    def test_groq_fails_anthropic_succeeds(self, monkeypatch):
        """Wenn Groq und OpenAI fehlschlagen, muss Anthropic versucht werden."""
        monkeypatch.setenv("AILIZA_EXTERNAL_LLM_ENABLED", "true")
        monkeypatch.setenv("GROQ_API_KEY", "fake")
        monkeypatch.setenv("OPENAI_API_KEY", "fake")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "fake")
        import apps.backend.registry.registry_loader as rl
        rl._registry = None

        orch = ProviderOrchestrator(providers={
            "groq": _FailProvider("groq", code="rate_limited", detail="Groq: rate limit"),
            "openai": _FailProvider("openai", code="provider_unavailable", detail="OpenAI: timeout"),
            "anthropic": _OKProvider("anthropic", "Anthropic-Antwort"),
        })
        result = orch.generate([{"role": "user", "content": "Test"}])
        assert result == "Anthropic-Antwort"


# ── 2. Alle Provider fehlschlagen → all_providers_failed mit Ursachen ────────

class TestAllProvidersFailed:

    def test_all_fail_raises_all_providers_failed(self, monkeypatch):
        """Wenn Groq UND OpenAI fehlschlagen → AILIZAError code=all_providers_failed."""
        monkeypatch.setenv("AILIZA_EXTERNAL_LLM_ENABLED", "true")
        monkeypatch.setenv("GROQ_API_KEY", "fake")
        monkeypatch.setenv("OPENAI_API_KEY", "fake")
        import apps.backend.registry.registry_loader as rl
        rl._registry = None

        orch = ProviderOrchestrator(providers={
            "groq": _FailProvider("groq", code="provider_forbidden",
                                  detail="groq: Modell nicht im Plan (HTTP 403)"),
            "openai": _FailProvider("openai", code="no_api_key",
                                    detail="openai: ungültiger Key"),
        })
        with pytest.raises(AILIZAError) as exc_info:
            orch.generate([{"role": "user", "content": "Test"}])

        exc = exc_info.value
        assert exc.code == "all_providers_failed"
        reasons = " ".join(exc.safe_alternatives or [])
        assert "groq" in reasons.lower(), f"Groq-Fehler fehlt in Ursachen: {reasons}"
        assert "openai" in reasons.lower(), f"OpenAI-Fehler fehlt in Ursachen: {reasons}"

    def test_failure_reasons_contain_no_api_keys(self, monkeypatch):
        """safe_alternatives darf keine API-Keys enthalten."""
        monkeypatch.setenv("AILIZA_EXTERNAL_LLM_ENABLED", "true")
        monkeypatch.setenv("GROQ_API_KEY", "gsk_SECRET_KEY_DO_NOT_LOG")
        import apps.backend.registry.registry_loader as rl
        rl._registry = None

        orch = ProviderOrchestrator(providers={
            "groq": _FailProvider("groq", code="no_api_key",
                                  detail="Ungültiger API-Key für Groq (HTTP 401)"),
        })
        with pytest.raises(AILIZAError) as exc_info:
            orch.generate([{"role": "user", "content": "Test"}])

        exc = exc_info.value
        reasons = " ".join(exc.safe_alternatives or [])
        # Der echte Key darf niemals in den Ursachen auftauchen
        assert "gsk_SECRET_KEY_DO_NOT_LOG" not in reasons


# ── 3. Schreibaufgabe → externer LLM-Pfad erreichbar ─────────────────────────

class TestWritingTaskAllowedExternalLLM:

    def test_public_writing_task_reaches_external_llm(self, monkeypatch):
        """
        'Schreibe eine E-Mail' mit public-Daten darf externen LLM-Pfad erreichen.
        Die Capability llm_call muss für PUBLIC erlaubt sein.
        """
        monkeypatch.setenv("AILIZA_EXTERNAL_LLM_ENABLED", "true")
        import apps.backend.registry.registry_loader as rl
        rl._registry = None

        orch = ProviderOrchestrator(providers={
            "groq": _OKProvider("groq", "Betreff: Offene Rechnung\n\nSehr geehrte Damen und Herren,")
        })
        result = orch.generate(
            [{"role": "user", "content": "Schreibe eine kurze E-Mail wegen einer offenen Rechnung."}]
        )
        assert "Betreff" in result or len(result) > 10

    def test_credentials_task_blocked_by_capability(self, monkeypatch):
        """
        Anfrage mit CREDENTIALS-Datenklasse muss durch Capability-Check blockiert werden.
        """
        monkeypatch.setenv("AILIZA_EXTERNAL_LLM_ENABLED", "true")
        import apps.backend.registry.registry_loader as rl
        rl._registry = None

        from apps.backend.governance.data_governance import DataClass as DC

        class _FakeContext:
            data_classes = [DC.CREDENTIALS]
            tenant_id = "test"
            user_id = None
            redaction_applied = False
            purpose = "kmu_assistant"
            task_type = None

        orch = ProviderOrchestrator(providers={
            "groq": _OKProvider("groq", "sollte nie ankommen"),
        })
        with pytest.raises(AILIZAError) as exc_info:
            orch.generate(
                [{"role": "user", "content": "Mein Passwort ist 1234"}],
                context=_FakeContext(),
            )
        assert exc_info.value.code == "policy_blocked"


# ── 4. GROQ_MODEL Default und Env-Vorrang ─────────────────────────────────────

class TestGroqModelResolution:

    def test_default_model_is_free_tier(self):
        """Default-Modell muss llama-3.1-8b-instant sein (kostenloses Groq-Tier)."""
        from apps.backend.providers.groq_provider import _DEFAULT_MODEL
        assert _DEFAULT_MODEL == "llama-3.1-8b-instant", (
            f"Default-Modell ist '{_DEFAULT_MODEL}' — muss 'llama-3.1-8b-instant' sein "
            "(llama-3.3-70b-versatile erfordert bezahlten Plan → 403)."
        )

    def test_groq_model_env_overrides_default(self, monkeypatch):
        """GROQ_MODEL Env hat Vorrang vor Konstruktor-Default."""
        monkeypatch.setenv("GROQ_MODEL", "llama-3.3-70b-versatile")
        from apps.backend.providers.groq_provider import GroqProvider
        p = GroqProvider()
        assert p.model == "llama-3.3-70b-versatile"

    def test_empty_groq_model_env_uses_default(self, monkeypatch):
        """Leerer GROQ_MODEL-Wert → Default-Modell wird genutzt."""
        monkeypatch.setenv("GROQ_MODEL", "")
        from apps.backend.providers.groq_provider import GroqProvider, _DEFAULT_MODEL
        p = GroqProvider()
        assert p.model == _DEFAULT_MODEL

    def test_groq_403_maps_to_provider_forbidden(self, monkeypatch):
        """HTTP 403 von Groq → provider_forbidden (nicht no_api_key)."""
        import urllib.error
        from unittest.mock import patch, MagicMock
        from apps.backend.providers.groq_provider import GroqProvider

        monkeypatch.setenv("GROQ_API_KEY", "fake-key")
        p = GroqProvider(model="llama-3.3-70b-versatile")

        http_err = urllib.error.HTTPError(
            url="https://api.groq.com/openai/v1/chat/completions",
            code=403, msg="Forbidden", hdrs=MagicMock(), fp=None
        )
        with patch("urllib.request.urlopen", side_effect=http_err):
            with pytest.raises(AILIZAError) as exc_info:
                p.generate([{"role": "user", "content": "test"}])

        assert exc_info.value.code == "provider_forbidden", (
            "HTTP 403 von Groq muss 'provider_forbidden' ergeben, "
            "nicht 'no_api_key' — der Key ist vorhanden, das Modell ist nicht im Plan."
        )


# ── 5. Fehlermeldung enthält auditierbare Ursache ohne Secrets ───────────────

class TestErrorMessageSafety:

    def test_all_providers_failed_message_is_german_and_generic(self):
        """Die UI-Meldung für all_providers_failed ist deutsch und enthält keine Keys."""
        from apps.backend.errors import MESSAGES
        msg = MESSAGES.get("all_providers_failed", "")
        assert "anbieter" in msg.lower() or "provider" in msg.lower()
        # Kein Hinweis auf API-Schlüssel in der UI-Meldung
        assert "schlüssel" not in msg.lower() and "schluessel" not in msg.lower()
        assert "api-key" not in msg.lower()

    def test_provider_forbidden_message_exists(self):
        """provider_forbidden muss eine verständliche Meldung haben."""
        from apps.backend.errors import MESSAGES
        msg = MESSAGES.get("provider_forbidden", "")
        assert len(msg) > 10, "provider_forbidden-Meldung fehlt oder zu kurz"
        assert "api" not in msg.lower() or "schlüssel" not in msg.lower()
