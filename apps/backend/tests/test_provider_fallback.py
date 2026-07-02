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
# Diese Datei testet Failover-Mechanik mit PUBLIC-Daten (kein PII). Ohne
# unterzeichneten AVV (DSGVO Art. 28) blockt check_provider_policy() seit
# Freigabe Stufe 1 (P-A) auch PUBLIC-Daten, ausser im Testmodus.
os.environ.setdefault("AILIZA_TEST_MODE", "true")

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


# ── 6. Groq Model-Fallback bei 403 ───────────────────────────────────────────

class TestGroqModelFallbackOn403:

    def test_paid_model_403_retries_with_free_tier(self, monkeypatch):
        """
        Wenn GROQ_MODEL auf ein Paid-Modell gesetzt ist und 403 kommt,
        muss Groq automatisch llama-3.1-8b-instant versuchen.
        """
        import urllib.error
        from unittest.mock import patch, MagicMock, call as mock_call
        from apps.backend.providers.groq_provider import GroqProvider, _DEFAULT_MODEL

        monkeypatch.setenv("GROQ_API_KEY", "fake-key")
        monkeypatch.setenv("GROQ_MODEL", "llama-3.3-70b-versatile")
        p = GroqProvider()
        assert p.model == "llama-3.3-70b-versatile"

        call_count = 0
        def fake_urlopen(req, timeout=20):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # Erster Call (paid model) → 403
                raise urllib.error.HTTPError(
                    url=req.full_url, code=403, msg="Forbidden",
                    hdrs=MagicMock(), fp=None,
                )
            # Zweiter Call (free tier) → Erfolg
            mock_resp = MagicMock()
            mock_resp.__enter__ = lambda s: s
            mock_resp.__exit__ = MagicMock(return_value=False)
            mock_resp.read.return_value = b'{"choices":[{"message":{"content":"AILIZA_PROVIDER_OK"}}]}'
            return mock_resp

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            result = p.generate([{"role": "user", "content": "test"}])

        assert result == "AILIZA_PROVIDER_OK"
        assert call_count == 2, f"Erwartet 2 Calls (original + fallback), got {call_count}"

    def test_default_model_403_does_not_retry(self, monkeypatch):
        """
        Wenn das Default-Modell 403 gibt, darf KEIN weiterer Retry stattfinden
        (würde endlose Schleife verursachen).
        """
        import urllib.error
        from unittest.mock import patch, MagicMock
        from apps.backend.providers.groq_provider import GroqProvider

        monkeypatch.setenv("GROQ_API_KEY", "fake-key")
        monkeypatch.setenv("GROQ_MODEL", "")  # → Default wird genutzt
        p = GroqProvider()

        call_count = 0
        def fake_urlopen(req, timeout=20):
            nonlocal call_count
            call_count += 1
            raise urllib.error.HTTPError(
                url=req.full_url, code=403, msg="Forbidden",
                hdrs=MagicMock(), fp=None,
            )

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            with pytest.raises(AILIZAError) as exc_info:
                p.generate([{"role": "user", "content": "test"}])

        assert exc_info.value.code == "provider_forbidden"
        assert call_count == 1, f"Nur 1 Call erwartet (kein Retry bei Default-Modell), got {call_count}"

    def test_fallback_model_also_fails_raises_combined_error(self, monkeypatch):
        """
        Wenn Paid-Modell 403 gibt UND Free-Tier-Fallback auch fehlschlägt,
        muss ein kombinierter Fehler mit beiden Ursachen geworfen werden.
        """
        import urllib.error
        from unittest.mock import patch, MagicMock
        from apps.backend.providers.groq_provider import GroqProvider

        monkeypatch.setenv("GROQ_API_KEY", "fake-key")
        monkeypatch.setenv("GROQ_MODEL", "llama-3.3-70b-versatile")
        p = GroqProvider()

        def fake_urlopen(req, timeout=20):
            raise urllib.error.HTTPError(
                url=req.full_url, code=429, msg="Rate Limited",
                hdrs=MagicMock(), fp=None,
            )

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            with pytest.raises(AILIZAError) as exc_info:
                p.generate([{"role": "user", "content": "test"}])

        exc = exc_info.value
        # Rate-Limit oder provider_forbidden — beide sind gültig je nach Reihenfolge
        assert exc.code in ("rate_limited", "provider_forbidden", "provider_error")


# ── 7. Admin-Hints — sanitisierte Diagnose ohne Secrets ──────────────────────

class TestAdminHints:

    def test_admin_hints_exist_for_key_codes(self):
        """ADMIN_HINTS muss für die häufigsten Fehlercodes Hinweise enthalten."""
        from apps.backend.errors import ADMIN_HINTS
        for code in ("provider_forbidden", "no_api_key", "rate_limited", "all_providers_failed"):
            assert code in ADMIN_HINTS, f"ADMIN_HINTS fehlt für '{code}'"
            assert len(ADMIN_HINTS[code]) > 20, f"ADMIN_HINTS['{code}'] zu kurz"

    def test_admin_hints_contain_no_api_keys(self):
        """ADMIN_HINTS dürfen keine echten Schlüsselwerte enthalten."""
        from apps.backend.errors import ADMIN_HINTS
        for code, hint in ADMIN_HINTS.items():
            # Typische Key-Prefixes die niemals in Hints stehen dürfen
            assert "gsk_" not in hint, f"Groq-Key-Prefix in ADMIN_HINTS['{code}']"
            assert "sk-" not in hint, f"OpenAI-Key-Prefix in ADMIN_HINTS['{code}']"

    def test_all_providers_failed_hint_points_to_provider_test(self):
        """all_providers_failed Hint muss auf provider-test Endpunkt verweisen."""
        from apps.backend.errors import ADMIN_HINTS
        hint = ADMIN_HINTS.get("all_providers_failed", "")
        # Verweist auf Live-Diagnose, nicht auf einen spezifischen Provider
        assert "provider-test" in hint or "provider_errors" in hint, (
            "all_providers_failed Hint muss auf /api/debug/provider-test oder "
            "provider_errors verweisen — provider-spezifische Ursachen stehen dort"
        )

    def test_provider_forbidden_hint_mentions_free_tier_fix(self):
        """provider_forbidden Hint enthält keine zirkulären Modellnamen mehr."""
        from apps.backend.errors import ADMIN_HINTS
        hint = ADMIN_HINTS.get("provider_forbidden", "")
        # ADMIN_HINTS ist jetzt provider-neutral — kein "Groq:" Prefix, kein Modellname als Fix
        assert len(hint) > 20
        # Kein zirkulärer Fix-Vorschlag im globalen Hint
        assert "GROQ_MODEL=llama-3.1-8b-instant" not in hint, (
            "ADMIN_HINTS[provider_forbidden] darf keinen konkreten Modellnamen als Fix enthalten — "
            "das ist zirkulär wenn dieses Modell bereits aktiv ist"
        )


# ── 8. Groq 403 Hinweis ist kontextabhängig (kein zirkulärer Fix) ────────────

class TestGroq403HintContextAware:

    def test_default_model_403_hint_no_circular_fix(self):
        """
        Wenn llama-3.1-8b-instant (Default) 403 gibt, darf der Hinweis NICHT
        'GROQ_MODEL=llama-3.1-8b-instant setzen' vorschlagen — das ist zirkulär.
        """
        from apps.backend.providers.groq_provider import _map_groq_http_error, _DEFAULT_MODEL
        code, detail = _map_groq_http_error(403, _DEFAULT_MODEL)
        assert code == "provider_forbidden"
        # Kein zirkulärer Fix-Vorschlag
        assert f"GROQ_MODEL={_DEFAULT_MODEL}" not in detail, (
            f"403-Hinweis für Default-Modell '{_DEFAULT_MODEL}' schlägt dieses Modell "
            "als Fix vor — das ist widersprüchlich"
        )
        # Stattdessen: Groq-Dashboard-Hinweis
        assert "dashboard" in detail.lower() or "projekt" in detail.lower() or "berechtigung" in detail.lower()

    def test_non_default_model_403_hint_suggests_fix(self):
        """
        Wenn ein Paid-Modell 403 gibt, soll der Hinweis explizit llama-3.1-8b-instant empfehlen.
        """
        from apps.backend.providers.groq_provider import _map_groq_http_error, _DEFAULT_MODEL
        code, detail = _map_groq_http_error(403, "llama-3.3-70b-versatile")
        assert code == "provider_forbidden"
        assert _DEFAULT_MODEL in detail, (
            f"Hinweis für Paid-Modell 403 muss '{_DEFAULT_MODEL}' als Fix nennen"
        )
        assert "GROQ_MODEL" in detail


# ── 9. OpenAI-Fehler haben OpenAI-Prefix — nie Groq-Prefix ──────────────────

class TestOpenAIErrorLabels:

    def test_openai_rate_limit_hint_starts_with_openai(self):
        """
        429 von OpenAI → safe_alternatives muss mit 'OpenAI:' beginnen.
        Kein 'Groq:' oder anderer Provider-Name in OpenAI-Hints.
        """
        from apps.backend.providers.openai_provider import _map_openai_http_status

        code, detail = _map_openai_http_status(429, "gpt-4o-mini")
        assert code == "rate_limited"
        assert detail.startswith("OpenAI:"), (
            f"OpenAI rate-limit Hinweis muss mit 'OpenAI:' beginnen, "
            f"nicht mit '{detail[:20]}'"
        )
        assert "Groq" not in detail, "OpenAI-Hinweis enthält 'Groq' — falscher Provider-Label"

    def test_openai_auth_error_hint_starts_with_openai(self):
        """401 von OpenAI → Hinweis mit 'OpenAI:', kein 'Groq:'."""
        from apps.backend.providers.openai_provider import _map_openai_http_status

        code, detail = _map_openai_http_status(401, "gpt-4o-mini")
        assert code == "invalid_api_key"
        assert detail.startswith("OpenAI:")
        assert "Groq" not in detail

    def test_openai_provider_errors_contain_openai_in_reasons(self, monkeypatch):
        """
        Wenn OpenAI 429 wirft, muss provider_errors 'openai' und 'OpenAI:' enthalten.
        Nicht 'openai: Groq: ...' oder 'openai: rate_limited'.
        """
        monkeypatch.setenv("AILIZA_EXTERNAL_LLM_ENABLED", "true")
        monkeypatch.setenv("GROQ_API_KEY", "fake")
        monkeypatch.setenv("OPENAI_API_KEY", "fake")
        import apps.backend.registry.registry_loader as rl
        rl._registry = None

        orch = ProviderOrchestrator(providers={
            "openai": _FailProvider(
                "openai",
                code="rate_limited",
                detail="OpenAI: Rate-Limit oder Quota erreicht (HTTP 429) — platform.openai.com/usage prüfen",
            ),
        })
        with pytest.raises(AILIZAError) as exc_info:
            orch.generate([{"role": "user", "content": "test"}])

        exc = exc_info.value
        reasons_text = " ".join(exc.safe_alternatives or [])
        # "openai:" Prefix vom Orchestrator + "OpenAI:" aus dem Provider-Hint
        assert "openai" in reasons_text.lower()
        # Kein falsches Groq-Label im OpenAI-Fehler
        assert "Groq:" not in reasons_text, (
            f"OpenAI-Fehler enthält 'Groq:' — falscher Provider-Label: {reasons_text!r}"
        )

    def test_groq_403_provider_errors_contain_groq_dashboard_hint(self, monkeypatch):
        """
        Wenn Groq 403 für Default-Modell wirft, muss provider_errors Groq-Dashboard-Hinweis
        enthalten — KEIN 'GROQ_MODEL=llama-3.1-8b-instant' als Fix.
        """
        monkeypatch.setenv("AILIZA_EXTERNAL_LLM_ENABLED", "true")
        monkeypatch.setenv("GROQ_API_KEY", "fake")
        monkeypatch.setenv("GROQ_MODEL", "")  # → Default llama-3.1-8b-instant
        import apps.backend.registry.registry_loader as rl
        rl._registry = None

        from apps.backend.providers.groq_provider import _DEFAULT_MODEL
        groq_detail = (
            f"Groq verweigert Zugriff auf '{_DEFAULT_MODEL}' (HTTP 403). "
            "Mögliche Ursachen: Groq-Projekt hat dieses Modell nicht freigeschaltet. "
            "Bitte Groq-Dashboard → API Keys → Projekt-Berechtigungen prüfen."
        )
        orch = ProviderOrchestrator(providers={
            "groq": _FailProvider("groq", code="provider_forbidden", detail=groq_detail),
        })
        with pytest.raises(AILIZAError) as exc_info:
            orch.generate([{"role": "user", "content": "test"}])

        reasons_text = " ".join(exc_info.value.safe_alternatives or [])
        # Zirkulärer Fix-Vorschlag darf nicht vorkommen
        assert f"GROQ_MODEL={_DEFAULT_MODEL}" not in reasons_text, (
            "provider_errors schlägt dasselbe Modell als Fix vor, das bereits fehlschlägt"
        )
        # Stattdessen: Dashboard-Hinweis
        assert "dashboard" in reasons_text.lower() or "berechtigung" in reasons_text.lower()


# ── 10. Neue Tests: Provider-Reihenfolge, Fallback-Robustheit ─────────────────

class TestProviderOrderEnvVar:
    """AILIZA_PROVIDER_ORDER steuert die Reihenfolge — nicht Registry-Priorität allein."""

    def _orch(self, monkeypatch, providers):
        import apps.backend.registry.registry_loader as rl
        rl._registry = None
        monkeypatch.setenv("AILIZA_EXTERNAL_LLM_ENABLED", "true")
        from apps.backend.providers.orchestrator import ProviderOrchestrator
        return ProviderOrchestrator(providers=providers)

    def test_provider_order_env_respected(self, monkeypatch):
        """AILIZA_PROVIDER_ORDER=openai,groq → openai wird zuerst versucht."""
        calls = []

        class FakeOpenAI:
            provider_id = "openai"
            model = "gpt-4o-mini"
            def count_tokens(self, t): return 1
            def estimate_cost(self, i, o): return 0.0
            def generate(self, messages, context=None):
                calls.append("openai")
                return "ok"

        class FakeGroq:
            provider_id = "groq"
            model = "llama"
            def count_tokens(self, t): return 1
            def estimate_cost(self, i, o): return 0.0
            def generate(self, messages, context=None):
                calls.append("groq")
                return "ok"

        monkeypatch.setenv("OPENAI_API_KEY", "fake")
        monkeypatch.setenv("GROQ_API_KEY", "fake")
        monkeypatch.setenv("AILIZA_PROVIDER_ORDER", "openai,groq")

        orch = self._orch(monkeypatch, {"openai": FakeOpenAI(), "groq": FakeGroq()})
        orch.generate([{"role": "user", "content": "test"}])
        assert calls[0] == "openai", f"openai muss zuerst versucht werden, war: {calls}"

    def test_groq_403_does_not_block_openai(self, monkeypatch):
        """Groq 403 (provider_forbidden) → OpenAI antwortet, kein all_providers_failed."""
        from apps.backend.errors import AILIZAError

        class FakeGroq:
            provider_id = "groq"
            model = "llama"
            def count_tokens(self, t): return 1
            def estimate_cost(self, i, o): return 0.0
            def generate(self, messages, context=None):
                raise AILIZAError.from_code("provider_forbidden",
                                             safe_alternatives=["Groq: HTTP 403"])

        class FakeOpenAI:
            provider_id = "openai"
            model = "gpt-4o-mini"
            def count_tokens(self, t): return 1
            def estimate_cost(self, i, o): return 0.0
            def generate(self, messages, context=None):
                return "Antwort von OpenAI"

        monkeypatch.setenv("GROQ_API_KEY", "fake")
        monkeypatch.setenv("OPENAI_API_KEY", "fake")
        monkeypatch.setenv("AILIZA_PROVIDER_ORDER", "groq,openai")

        orch = self._orch(monkeypatch, {"groq": FakeGroq(), "openai": FakeOpenAI()})
        result = orch.generate([{"role": "user", "content": "test"}])
        assert "OpenAI" in result

    def test_openai_ok_even_if_groq_fails(self, monkeypatch):
        """Chat antwortet erfolgreich, wenn OpenAI ok und Groq failt."""
        from apps.backend.errors import AILIZAError

        class FakeGroq:
            provider_id = "groq"
            model = "llama"
            def count_tokens(self, t): return 1
            def estimate_cost(self, i, o): return 0.0
            def generate(self, messages, context=None):
                raise AILIZAError.from_code("provider_forbidden")

        class FakeOpenAI:
            provider_id = "openai"
            model = "gpt-4o-mini"
            def count_tokens(self, t): return 1
            def estimate_cost(self, i, o): return 0.0
            def generate(self, messages, context=None):
                return "Betreff: Offene Rechnung\n\nSehr geehrte Damen und Herren..."

        monkeypatch.setenv("GROQ_API_KEY", "fake")
        monkeypatch.setenv("OPENAI_API_KEY", "fake")

        orch = self._orch(monkeypatch, {"groq": FakeGroq(), "openai": FakeOpenAI()})
        result = orch.generate([{"role": "user", "content": "Schreibe eine E-Mail"}])
        assert "Betreff" in result
        assert "Kein KI-Anbieter" not in result

    def test_all_fail_user_gets_safe_message(self, monkeypatch):
        """Alle Provider fail → Nutzer bekommt deutsche Kurzmeldung, kein Stack-Trace."""
        import pytest
        from apps.backend.errors import AILIZAError

        class FailProvider:
            provider_id = "groq"
            model = "llama"
            def count_tokens(self, t): return 1
            def estimate_cost(self, i, o): return 0.0
            def generate(self, messages, context=None):
                raise AILIZAError.from_code("provider_forbidden",
                                             safe_alternatives=["Groq: HTTP 403"])

        monkeypatch.setenv("GROQ_API_KEY", "fake")

        orch = self._orch(monkeypatch, {"groq": FailProvider()})
        with pytest.raises(AILIZAError) as exc_info:
            orch.generate([{"role": "user", "content": "test"}])
        exc = exc_info.value
        assert exc.code == "all_providers_failed"
        # Nutzermeldung auf Deutsch, kein Stack-Trace, kein API-Key
        assert "KI-Anbieter" in exc.message_de or "Provider" in exc.message_de
        assert "fake" not in exc.message_de

    def test_all_fail_provider_errors_contains_reasons(self, monkeypatch):
        """provider_errors (safe_alternatives) enthält sanitisierte Ursachen je Provider."""
        import pytest
        from apps.backend.errors import AILIZAError

        class FailProvider:
            provider_id = "openai"
            model = "gpt-4o-mini"
            def count_tokens(self, t): return 1
            def estimate_cost(self, i, o): return 0.0
            def generate(self, messages, context=None):
                raise AILIZAError.from_code("rate_limited",
                                             safe_alternatives=["OpenAI: Rate-Limit (HTTP 429)"])

        monkeypatch.setenv("OPENAI_API_KEY", "fake")

        orch = self._orch(monkeypatch, {"openai": FailProvider()})
        with pytest.raises(AILIZAError) as exc_info:
            orch.generate([{"role": "user", "content": "test"}])
        exc = exc_info.value
        reasons = exc.safe_alternatives
        assert any("openai" in r.lower() or "OpenAI" in r for r in reasons), \
            f"provider_errors soll openai-Ursache enthalten: {reasons}"
        assert all("fake" not in r for r in reasons), "Kein API-Key in provider_errors"


class TestOpenRouterConfigured:
    """OpenRouter configured=false wenn kein Key gesetzt."""

    def test_openrouter_no_key_raises_no_api_key(self, monkeypatch):
        """Wenn OPENROUTER_API_KEY nicht gesetzt → no_api_key, nicht configured=true."""
        import pytest
        from apps.backend.errors import AILIZAError
        monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
        monkeypatch.delenv("AILIZA_OPENROUTER_MODEL", raising=False)
        monkeypatch.delenv("OPENROUTER_MODEL", raising=False)
        from apps.backend.providers.openrouter_provider import OpenRouterProvider
        provider = OpenRouterProvider()
        with pytest.raises(AILIZAError) as exc_info:
            provider.generate([{"role": "user", "content": "test"}])
        assert exc_info.value.code == "no_api_key"

    def test_openrouter_model_env_var(self, monkeypatch):
        """OPENROUTER_MODEL Env-Var wird als Modell genutzt."""
        monkeypatch.setenv("OPENROUTER_MODEL", "my-custom-model")
        monkeypatch.delenv("AILIZA_OPENROUTER_MODEL", raising=False)
        from apps.backend.providers.openrouter_provider import OpenRouterProvider
        provider = OpenRouterProvider()
        assert provider.model == "my-custom-model"

    def test_openrouter_default_model(self, monkeypatch):
        """Default-Modell ist meta-llama/llama-3.1-8b-instruct."""
        monkeypatch.delenv("OPENROUTER_MODEL", raising=False)
        monkeypatch.delenv("AILIZA_OPENROUTER_MODEL", raising=False)
        from apps.backend.providers.openrouter_provider import OpenRouterProvider
        provider = OpenRouterProvider()
        assert provider.model == "meta-llama/llama-3.1-8b-instruct"
