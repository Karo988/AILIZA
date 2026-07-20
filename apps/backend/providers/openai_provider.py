"""
AILIZA OpenAI Provider
======================
Fallback-Adapter für die OpenAI Chat API (REST, kein SDK).
Nutzt urllib.request — keine externe Abhängigkeit über requirements.txt hinaus.
Wird genutzt wenn Groq nicht verfügbar ist.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from collections.abc import Iterator
from typing import Any

try:
    from .base import LLMProvider
    from .gate_types import ProviderResult
    from ..errors import AILIZAError
except ImportError:  # pragma: no cover
    from providers.base import LLMProvider
    from providers.gate_types import ProviderResult
    from errors import AILIZAError

_OPENAI_URL = "https://api.openai.com/v1/chat/completions"
_DEFAULT_MODEL = "gpt-4o-mini"


def _map_openai_http_status(status: int, model: str) -> tuple[str, str]:
    """Mappt HTTP-Statuscodes auf (AILIZA-Code, Admin-Hinweis). 'OpenAI:'-Prefix immer gesetzt."""
    if status == 401:
        return "invalid_api_key", "OpenAI: Ungültiger API-Key (HTTP 401) — OPENAI_API_KEY in Render prüfen"
    if status == 403:
        return "provider_forbidden", "OpenAI: Zugriff verweigert (HTTP 403) — API-Key-Berechtigungen prüfen"
    if status == 404:
        return "model_not_found", f"OpenAI: Modell '{model}' nicht gefunden (HTTP 404) — OPENAI_MODEL in Render prüfen"
    if status == 429:
        return "rate_limited", (
            "OpenAI: Rate-Limit oder Quota erreicht (HTTP 429) — "
            "platform.openai.com/usage und Billing prüfen"
        )
    if status >= 500:
        return "provider_unavailable", f"OpenAI: Server-Fehler (HTTP {status}) — temporär nicht erreichbar"
    return "provider_error", f"OpenAI: Unbekannter HTTP-Fehler ({status})"


class OpenAIProvider(LLMProvider):
    provider_region = "US"
    provider_profile_version = "1.1"
    provider_id = "openai"

    def __init__(self, model: str | None = None) -> None:
        self.model = model or os.getenv("OPENAI_MODEL", _DEFAULT_MODEL)

    @property
    def max_context_tokens(self) -> int:
        return 128000

    def estimate_cost(self, tokens_in: int, tokens_out: int) -> float:
        return round((tokens_in * 0.00000015) + (tokens_out * 0.0000006), 8)

    def _api_key(self) -> str:
        key = os.getenv("OPENAI_API_KEY")
        if not key:
            raise AILIZAError.from_code(
                "no_api_key",
                safe_alternatives=["OpenAI: OPENAI_API_KEY nicht gesetzt — in Render-Env prüfen"],
            )
        return key

    @property
    def supports_json_mode(self) -> bool:
        return True

    def generate(self, messages: list[dict[str, Any]], context: Any = None) -> str:
        return self._call(messages, response_format=None)

    def generate_with_meta(
        self,
        messages: list[dict[str, Any]],
        context: Any = None,
        response_format: dict[str, Any] | None = None,
    ) -> ProviderResult:
        return ProviderResult(text=self._call(messages, response_format=response_format), stop_reason=None)

    def _call(self, messages: list[dict[str, Any]], response_format: dict[str, Any] | None) -> str:
        api_key = self._api_key()
        print(f"AILIZA OPENAI CALL | model={self.model} json_mode={bool(response_format)}", flush=True)
        body: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "max_tokens": 1000,
            "temperature": 0.3,
        }
        if response_format:
            body["response_format"] = response_format
        payload = json.dumps(body).encode()
        req = urllib.request.Request(
            _OPENAI_URL,
            data=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                data = json.loads(resp.read())
                answer = data["choices"][0]["message"]["content"] or ""
                print(f"AILIZA OPENAI RESULT | result=ok chars={len(answer)}", flush=True)
                return answer
        except urllib.error.HTTPError as exc:
            code, detail = _map_openai_http_status(exc.code, self.model)
            print(
                f"AILIZA OPENAI FAILED | code={code} http_status={exc.code}",
                flush=True,
            )
            raise AILIZAError.from_code(code, safe_alternatives=[detail]) from exc
        except urllib.error.URLError as exc:
            detail = f"OpenAI: Verbindungsfehler — {type(exc.reason).__name__}"
            print(f"AILIZA OPENAI FAILED | code=provider_unavailable url_error={type(exc.reason).__name__}", flush=True)
            raise AILIZAError.from_code("provider_unavailable", safe_alternatives=[detail]) from exc
        except Exception as exc:  # noqa: BLE001
            detail = f"OpenAI: Unbekannter Fehler ({type(exc).__name__})"
            print(f"AILIZA OPENAI FAILED | code=provider_error type={type(exc).__name__}", flush=True)
            raise AILIZAError.from_code("provider_error", safe_alternatives=[detail]) from exc

    def stream(self, messages: list[dict[str, Any]], context: Any = None) -> Iterator[str]:
        yield self.generate(messages, context)
