"""
Tests für Groq-Fehlerbehandlung und all_providers_failed-Ursachen.

Prüft:
- Groq HTTP 403 → provider_forbidden (NICHT no_api_key)
- Groq HTTP 401 → no_api_key
- Groq HTTP 404 → model_not_found
- Groq HTTP 429 → rate_limited
- Groq HTTP 500 → provider_unavailable
- GROQ_MODEL env var überschreibt Default
- all_providers_failed enthält Ursachen je Provider
- UI-Meldung sagt nicht fälschlich "API-Schlüssel fehlt" bei 403
- Logs: GROQ CALL, GROQ HTTP ERROR sichtbar
- API-Key niemals in Logs
"""
from __future__ import annotations

import urllib.error
from io import BytesIO

import pytest

from apps.backend.errors import AILIZAError


# ── Hilfsfunktionen ───────────────────────────────────────────────────────────

def _make_http_error(status: int) -> urllib.error.HTTPError:
    """Erstellt einen urllib HTTPError mit gegebenem Status-Code."""
    return urllib.error.HTTPError(
        url="https://api.groq.com/openai/v1/chat/completions",
        code=status,
        msg=f"HTTP Error {status}",
        hdrs=None,  # type: ignore[arg-type]
        fp=BytesIO(b'{"error": {"message": "test error"}}'),
    )


def _make_provider(monkeypatch, model: str = "llama-3.1-8b-instant"):
    monkeypatch.setenv("GROQ_API_KEY", "test-key-not-real")
    monkeypatch.delenv("GROQ_MODEL", raising=False)
    from apps.backend.providers.groq_provider import GroqProvider
    return GroqProvider(model=model)


# ── 1. HTTP-Fehlercode-Mapping ────────────────────────────────────────────────

class TestGroqHttpErrorMapping:

    def test_403_maps_to_provider_forbidden_not_no_api_key(self, monkeypatch):
        """
        HTTP 403 = Zugriff verweigert (Modell nicht im Plan).
        Darf NICHT als no_api_key interpretiert werden.
        """
        from apps.backend.providers.groq_provider import _map_groq_http_error
        code, detail = _map_groq_http_error(403, "llama-3.3-70b-versatile")
        assert code == "provider_forbidden", f"403 muss provider_forbidden sein, nicht '{code}'"
        assert "403" in detail or "verweigert" in detail.lower() or "Modell" in detail

    def test_401_maps_to_no_api_key(self, monkeypatch):
        from apps.backend.providers.groq_provider import _map_groq_http_error
        code, detail = _map_groq_http_error(401, "llama-3.1-8b-instant")
        assert code == "no_api_key"

    def test_404_maps_to_model_not_found(self, monkeypatch):
        from apps.backend.providers.groq_provider import _map_groq_http_error
        code, detail = _map_groq_http_error(404, "nonexistent-model")
        assert code == "model_not_found"

    def test_429_maps_to_rate_limited(self, monkeypatch):
        from apps.backend.providers.groq_provider import _map_groq_http_error
        code, detail = _map_groq_http_error(429, "llama-3.1-8b-instant")
        assert code == "rate_limited"

    def test_500_maps_to_provider_unavailable(self, monkeypatch):
        from apps.backend.providers.groq_provider import _map_groq_http_error
        code, detail = _map_groq_http_error(500, "llama-3.1-8b-instant")
        assert code == "provider_unavailable"

    def test_503_maps_to_provider_unavailable(self, monkeypatch):
        from apps.backend.providers.groq_provider import _map_groq_http_error
        code, detail = _map_groq_http_error(503, "llama-3.1-8b-instant")
        assert code == "provider_unavailable"


# ── 2. GroqProvider.generate() Exception-Handling ─────────────────────────────

class TestGroqProviderGenerate:

    def _patch_urlopen(self, monkeypatch, exc: Exception):
        """Lässt urlopen eine Exception werfen."""
        import urllib.request as ur

        def _raise(*a, **kw):
            raise exc

        monkeypatch.setattr(ur, "urlopen", _raise)

    def test_403_raises_provider_forbidden(self, monkeypatch):
        provider = _make_provider(monkeypatch)
        self._patch_urlopen(monkeypatch, _make_http_error(403))

        with pytest.raises(AILIZAError) as exc_info:
            provider.generate([{"role": "user", "content": "test"}])
        assert exc_info.value.code == "provider_forbidden", (
            f"403 muss provider_forbidden sein, nicht '{exc_info.value.code}'"
        )

    def test_403_error_message_not_api_key(self, monkeypatch):
        """Die UI-Meldung bei 403 darf nicht 'API-Schlüssel fehlt' sagen."""
        provider = _make_provider(monkeypatch)
        self._patch_urlopen(monkeypatch, _make_http_error(403))

        with pytest.raises(AILIZAError) as exc_info:
            provider.generate([{"role": "user", "content": "test"}])
        msg = exc_info.value.message_de.lower()
        assert "schluessel" not in msg and "schlüssel" not in msg, (
            f"403-Fehlermeldung sagt fälschlich 'Schlüssel': {msg!r}"
        )
        assert "zugriff" in msg or "verweigert" in msg.lower() or "berechtigung" in msg.lower() or "anbieter" in msg.lower()

    def test_401_raises_no_api_key(self, monkeypatch):
        provider = _make_provider(monkeypatch)
        self._patch_urlopen(monkeypatch, _make_http_error(401))

        with pytest.raises(AILIZAError) as exc_info:
            provider.generate([{"role": "user", "content": "test"}])
        assert exc_info.value.code == "no_api_key"

    def test_429_raises_rate_limited(self, monkeypatch):
        provider = _make_provider(monkeypatch)
        self._patch_urlopen(monkeypatch, _make_http_error(429))

        with pytest.raises(AILIZAError) as exc_info:
            provider.generate([{"role": "user", "content": "test"}])
        assert exc_info.value.code == "rate_limited"

    def test_404_raises_model_not_found(self, monkeypatch):
        provider = _make_provider(monkeypatch)
        self._patch_urlopen(monkeypatch, _make_http_error(404))

        with pytest.raises(AILIZAError) as exc_info:
            provider.generate([{"role": "user", "content": "test"}])
        assert exc_info.value.code == "model_not_found"

    def test_url_error_raises_provider_unavailable(self, monkeypatch):
        import urllib.error as ue
        provider = _make_provider(monkeypatch)
        self._patch_urlopen(monkeypatch, ue.URLError("Connection refused"))

        with pytest.raises(AILIZAError) as exc_info:
            provider.generate([{"role": "user", "content": "test"}])
        assert exc_info.value.code == "provider_unavailable"

    def test_groq_call_log_printed(self, monkeypatch, capsys):
        """AILIZA GROQ CALL muss vor dem API-Aufruf geloggt werden."""
        import urllib.request as ur
        provider = _make_provider(monkeypatch)
        self._patch_urlopen(monkeypatch, _make_http_error(403))

        with pytest.raises(AILIZAError):
            provider.generate([{"role": "user", "content": "test"}])

        captured = capsys.readouterr()
        assert "AILIZA GROQ CALL" in captured.out
        assert "AILIZA GROQ HTTP ERROR" in captured.out
        assert "status=403" in captured.out

    def test_api_key_never_in_logs(self, monkeypatch, capsys):
        """Der API-Key darf niemals in Logs erscheinen."""
        monkeypatch.setenv("GROQ_API_KEY", "ultra-secret-key-12345")
        monkeypatch.delenv("GROQ_MODEL", raising=False)
        import urllib.request as ur
        from apps.backend.providers.groq_provider import GroqProvider
        provider = GroqProvider()
        import urllib.request
        monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **kw: (_ for _ in ()).throw(_make_http_error(403)))

        with pytest.raises(AILIZAError):
            provider.generate([{"role": "user", "content": "test"}])

        captured = capsys.readouterr()
        assert "ultra-secret-key-12345" not in captured.out
        assert "ultra-secret-key-12345" not in captured.err


# ── 3. GROQ_MODEL env var ─────────────────────────────────────────────────────

class TestGroqModelEnvVar:

    def test_groq_model_env_var_overrides_default(self, monkeypatch):
        monkeypatch.setenv("GROQ_API_KEY", "fake")
        monkeypatch.setenv("GROQ_MODEL", "llama-3.1-8b-instant")
        from apps.backend.providers.groq_provider import GroqProvider
        provider = GroqProvider(model="llama-3.3-70b-versatile")
        assert provider.model == "llama-3.1-8b-instant", (
            f"GROQ_MODEL env var soll Konstruktor-Argument überschreiben, "
            f"aber model={provider.model!r}"
        )

    def test_default_model_is_safe(self, monkeypatch):
        """Default-Modell ist llama-3.1-8b-instant (kostenlos, breite Verfügbarkeit)."""
        monkeypatch.setenv("GROQ_API_KEY", "fake")
        monkeypatch.delenv("GROQ_MODEL", raising=False)
        from apps.backend.providers.groq_provider import GroqProvider, _DEFAULT_MODEL
        provider = GroqProvider()
        assert provider.model == _DEFAULT_MODEL
        assert "8b" in _DEFAULT_MODEL or "instant" in _DEFAULT_MODEL, (
            "Default-Modell sollte das kostenlose 8b-instant sein"
        )

    def test_no_groq_model_env_uses_constructor_arg(self, monkeypatch):
        monkeypatch.setenv("GROQ_API_KEY", "fake")
        monkeypatch.delenv("GROQ_MODEL", raising=False)
        from apps.backend.providers.groq_provider import GroqProvider
        provider = GroqProvider(model="llama-3.3-70b-versatile")
        assert provider.model == "llama-3.3-70b-versatile"


# ── 4. all_providers_failed mit Ursachen ─────────────────────────────────────

class TestAllProvidersFailedReasons:

    def test_failure_reasons_in_safe_alternatives(self, monkeypatch):
        """
        Wenn alle Provider scheitern, müssen die Ursachen in safe_alternatives stehen.
        Groq 403 + OpenAI 429 → beide Gründe in der Fehlermeldung.
        """
        monkeypatch.setenv("AILIZA_EXTERNAL_LLM_ENABLED", "true")
        monkeypatch.setenv("GROQ_API_KEY", "fake")
        monkeypatch.setenv("OPENAI_API_KEY", "fake")
        import apps.backend.registry.registry_loader as rl
        rl._registry = None

        from apps.backend.providers.orchestrator import ProviderOrchestrator

        class FakeGroq403:
            provider_id = "groq"
            model = "llama-3.1-8b-instant"
            def count_tokens(self, t): return 1
            def estimate_cost(self, i, o): return 0.0
            def generate(self, messages, context=None):
                raise AILIZAError.from_code(
                    "provider_forbidden",
                    safe_alternatives=["Groq verweigert Zugriff auf Modell 'llama-3.1-8b-instant' (HTTP 403)"],
                )

        class FakeOpenAI429:
            provider_id = "openai"
            model = "gpt-4o-mini"
            def count_tokens(self, t): return 1
            def estimate_cost(self, i, o): return 0.0
            def generate(self, messages, context=None):
                raise AILIZAError.from_code("rate_limited")

        orch = ProviderOrchestrator(providers={
            "groq": FakeGroq403(),
            "openai": FakeOpenAI429(),
        })

        with pytest.raises(AILIZAError) as exc_info:
            orch.generate([{"role": "user", "content": "test"}])

        exc = exc_info.value
        assert exc.code == "all_providers_failed"
        # Ursachen müssen in safe_alternatives stehen
        reasons_text = " ".join(exc.safe_alternatives)
        assert "groq" in reasons_text.lower(), f"Groq-Fehler fehlt in safe_alternatives: {exc.safe_alternatives}"
        assert "openai" in reasons_text.lower(), f"OpenAI-Fehler fehlt in safe_alternatives: {exc.safe_alternatives}"

    def test_all_providers_failed_message_not_api_key(self, monkeypatch):
        """all_providers_failed darf nicht 'API-Schlüssel fehlt' sagen."""
        from apps.backend.errors import MESSAGES
        msg = MESSAGES["all_providers_failed"]
        assert "schluessel" not in msg.lower() and "schlüssel" not in msg.lower()
        assert "anbieter" in msg.lower() or "provider" in msg.lower()

    def test_provider_forbidden_message_not_api_key(self, monkeypatch):
        """provider_forbidden darf nicht 'API-Schlüssel fehlt' sagen."""
        from apps.backend.errors import MESSAGES
        msg = MESSAGES["provider_forbidden"]
        assert "schluessel" not in msg.lower() and "schlüssel" not in msg.lower()

    def test_rate_limited_message_mentions_ausgelastet(self, monkeypatch):
        from apps.backend.errors import MESSAGES
        msg = MESSAGES["rate_limited"]
        assert "ausgelastet" in msg.lower() or "limit" in msg.lower() or "erneut" in msg.lower()
