"""
AILIZA Groq Provider
====================
Adapter fuer die Groq OpenAI-kompatible API.
Externe Calls erfolgen ausschliesslich ueber den Orchestrator.
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


class GroqProvider(LLMProvider):
    provider_region = "US"  # Hinweis: Groq ist ein US-Anbieter, Transfer pruefen
    provider_profile_version = "1.0"
    provider_id = "groq"

    def __init__(self, model: str = "llama-3.3-70b-versatile") -> None:
        self.model = model

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
        payload = json.dumps({
            "model": self.model,
            "messages": messages,
            "max_tokens": 1000,
            "temperature": 0.3,
        }).encode()
        req = urllib.request.Request(
            GROQ_URL,
            data=payload,
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
        )
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                data = json.loads(resp.read())
                return data["choices"][0]["message"]["content"]
        except AILIZAError:
            raise
        except urllib.error.HTTPError as exc:
            status = exc.code
            print(f"AILIZA GROQ HTTP ERROR | status={status} model={self.model}", flush=True)
            if status in (401, 403):
                raise AILIZAError.from_code("no_api_key") from exc
            raise AILIZAError.from_code("provider_not_configured") from exc
        except urllib.error.URLError as exc:
            print(f"AILIZA GROQ URL ERROR | reason={exc.reason} model={self.model}", flush=True)
            raise AILIZAError.from_code("provider_not_configured") from exc
        except Exception as exc:  # noqa: BLE001
            print(f"AILIZA GROQ ERROR | type={type(exc).__name__} model={self.model}", flush=True)
            raise AILIZAError.from_code("provider_not_configured") from exc

    def stream(self, messages: list[dict[str, Any]], context: Any = None) -> Iterator[str]:
        # MVP: kein echtes Token-Streaming ueber urllib; gib Vollantwort als ein Chunk.
        yield self.generate(messages, context)
