"""
AILIZA Groq Provider
====================
Adapter fuer die Groq OpenAI-kompatible API.
Externe Calls erfolgen ausschliesslich ueber den Orchestrator.

Modell-Auswahl:
  GROQ_MODEL env var hat Vorrang vor dem Konstruktor-Default.
  Default: llama-3.1-8b-instant (kostenlos, breite Verfügbarkeit)
  Alternatives Modell: llama-3.3-70b-versatile (nur bestimmte Pläne)
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
    from ..errors import AILIZAError
except ImportError:  # pragma: no cover
    from providers.base import LLMProvider
    from errors import AILIZAError


GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"

# Sicherer Default: llama-3.1-8b-instant ist im kostenlosen Plan verfügbar.
# llama-3.3-70b-versatile erfordert einen bezahlten Plan → 403 wenn nicht freigeschaltet.
_DEFAULT_MODEL = "llama-3.1-8b-instant"


def _resolve_model(requested: str) -> str:
    """GROQ_MODEL env var hat Vorrang. Danach Konstruktor-Argument."""
    return os.getenv("GROQ_MODEL", "") or requested


def _map_groq_http_error(status: int, model: str) -> tuple[str, str]:
    """
    Gibt (error_code, log_detail) zurück.
    401 → ungültiger Key (no_api_key)
    403 → Zugriff verweigert, z.B. Modell nicht im Plan (provider_forbidden)
    404 → Modell existiert nicht (model_not_found)
    429 → Rate Limit (rate_limited)
    5xx → Provider-Fehler (provider_unavailable)
    """
    if status == 401:
        return "no_api_key", f"Ungültiger API-Key für Groq (HTTP 401)"
    if status == 403:
        return "provider_forbidden", (
            f"Groq verweigert Zugriff auf Modell '{model}' (HTTP 403). "
            "Mögliche Ursachen: Modell nicht im aktuellen Plan, "
            "Regions-Einschränkung oder Account-Sperre. "
            "Lösung: GROQ_MODEL auf 'llama-3.1-8b-instant' setzen."
        )
    if status == 404:
        return "model_not_found", f"Groq-Modell '{model}' nicht gefunden (HTTP 404)"
    if status == 429:
        return "rate_limited", f"Groq Rate-Limit erreicht (HTTP 429) für Modell '{model}'"
    if status >= 500:
        return "provider_unavailable", f"Groq Server-Fehler (HTTP {status})"
    return "provider_error", f"Groq unbekannter HTTP-Fehler (HTTP {status})"


class GroqProvider(LLMProvider):
    provider_region = "US"
    provider_profile_version = "1.0"
    provider_id = "groq"

    def __init__(self, model: str = _DEFAULT_MODEL) -> None:
        self.model = _resolve_model(model)

    def _api_key(self) -> str:
        key = os.getenv("GROQ_API_KEY")
        if not key:
            raise AILIZAError.from_code("no_api_key")
        return key

    @property
    def max_context_tokens(self) -> int:
        return 32768

    def estimate_cost(self, tokens_in: int, tokens_out: int) -> float:
        return round((tokens_in * 0.00000059) + (tokens_out * 0.00000079), 8)

    def generate(self, messages: list[dict[str, Any]], context: Any = None) -> str:
        api_key = self._api_key()
        key_present = True  # wenn wir hier ankommen, ist der Key vorhanden
        print(f"AILIZA GROQ CALL | model={self.model} key_present={key_present}", flush=True)

        payload = json.dumps({
            "model": self.model,
            "messages": messages,
            "max_tokens": 1000,
            "temperature": 0.3,
        }).encode()
        req = urllib.request.Request(
            GROQ_URL,
            data=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                data = json.loads(resp.read())
                result = data["choices"][0]["message"]["content"]
                print(f"AILIZA GROQ RESULT | result=ok chars={len(result)} model={self.model}", flush=True)
                return result
        except AILIZAError:
            raise
        except urllib.error.HTTPError as exc:
            status = exc.code
            code, detail = _map_groq_http_error(status, self.model)
            print(f"AILIZA GROQ HTTP ERROR | status={status} code={code} model={self.model}", flush=True)
            raise AILIZAError.from_code(code, safe_alternatives=[detail]) from exc
        except urllib.error.URLError as exc:
            print(f"AILIZA GROQ URL ERROR | reason={exc.reason} model={self.model}", flush=True)
            raise AILIZAError.from_code("provider_unavailable") from exc
        except Exception as exc:  # noqa: BLE001
            print(f"AILIZA GROQ ERROR | type={type(exc).__name__} model={self.model}", flush=True)
            raise AILIZAError.from_code("provider_error") from exc

    def stream(self, messages: list[dict[str, Any]], context: Any = None) -> Iterator[str]:
        yield self.generate(messages, context)
