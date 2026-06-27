"""
AILIZA OpenAI Provider
======================
Fallback-Adapter für die OpenAI Chat API.
Wird genutzt wenn Groq nicht verfügbar ist.
"""
from __future__ import annotations

import os
from collections.abc import Iterator
from typing import Any

try:
    from .base import LLMProvider
    from ..errors import AILIZAError
except ImportError:  # pragma: no cover
    from providers.base import LLMProvider
    from errors import AILIZAError


def _map_openai_exc(exc: Exception) -> tuple[str, str]:
    """
    Mappt OpenAI-SDK-Exceptions auf (AILIZA-Fehlercode, OpenAI-spezifischer Admin-Hinweis).
    Hinweis: immer mit "OpenAI:" prefixiert — niemals Groq- oder anderen Provider-Namen.
    """
    name = type(exc).__name__
    status = getattr(exc, "status_code", None)

    if name == "AuthenticationError" or status == 401:
        return "invalid_api_key", "OpenAI: Ungültiger API-Key (HTTP 401) — OPENAI_API_KEY in Render prüfen"
    if name == "PermissionDeniedError" or status == 403:
        return "provider_forbidden", "OpenAI: Zugriff verweigert (HTTP 403) — API-Key-Berechtigungen prüfen"
    if name == "NotFoundError" or status == 404:
        return "model_not_found", f"OpenAI: Modell nicht gefunden (HTTP 404) — OPENAI_MODEL prüfen"
    if name == "RateLimitError" or status == 429:
        return "rate_limited", "OpenAI: Rate-Limit oder Quota erreicht (HTTP 429) — platform.openai.com/usage und Billing prüfen"
    if name in ("APIConnectionError", "APITimeoutError"):
        return "provider_unavailable", "OpenAI: Verbindungsfehler — temporär nicht erreichbar"
    return "provider_error", f"OpenAI: Unbekannter Fehler ({name})"


class OpenAIProvider(LLMProvider):
    provider_region = "US"
    provider_profile_version = "1.0"
    provider_id = "openai"

    def __init__(self, model: str = "gpt-4o-mini") -> None:
        self.model = model

    @property
    def max_context_tokens(self) -> int:
        return 128000

    def estimate_cost(self, tokens_in: int, tokens_out: int) -> float:
        return round((tokens_in * 0.00000015) + (tokens_out * 0.0000006), 8)

    def _no_api_key_error(self) -> AILIZAError:
        return AILIZAError.from_code(
            "no_api_key",
            safe_alternatives=["OpenAI: OPENAI_API_KEY nicht gesetzt — in Render-Env prüfen"],
        )

    def _build_client(self):
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise self._no_api_key_error()
        try:
            from openai import OpenAI
        except ImportError as exc:  # pragma: no cover
            raise AILIZAError.from_code(
                "provider_not_configured",
                safe_alternatives=["OpenAI: 'openai' Python-Paket nicht installiert"],
            ) from exc
        return OpenAI(api_key=api_key)

    def generate(self, messages: list[dict[str, Any]], context: Any = None) -> str:
        key_present = bool(os.getenv("OPENAI_API_KEY"))
        print(f"AILIZA OPENAI CALL | key_present={key_present} model={self.model}", flush=True)
        try:
            client = self._build_client()
            resp = client.chat.completions.create(
                model=self.model,
                messages=messages,  # type: ignore[arg-type]
                max_tokens=1000,
                temperature=0.3,
            )
            answer = resp.choices[0].message.content or ""
            print(f"AILIZA OPENAI RESULT | result=ok chars={len(answer)}", flush=True)
            return answer
        except AILIZAError:
            raise
        except Exception as exc:  # noqa: BLE001
            code, detail = _map_openai_exc(exc)
            status = getattr(exc, "status_code", None)
            print(
                f"AILIZA OPENAI FAILED | code={code} type={type(exc).__name__} status={status}",
                flush=True,
            )
            raise AILIZAError.from_code(code, safe_alternatives=[detail]) from exc

    def stream(self, messages: list[dict[str, Any]], context: Any = None) -> Iterator[str]:
        yield self.generate(messages, context)
