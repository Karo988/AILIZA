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


class OpenAIProvider(LLMProvider):
    provider_region = "US"
    provider_profile_version = "1.0"
    provider_id = "openai"

    def __init__(self, model: str = "gpt-4o-mini") -> None:
        self.model = model

    def _client(self):
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise AILIZAError.from_code("no_api_key")
        try:
            from openai import OpenAI
        except ImportError as exc:  # pragma: no cover
            raise AILIZAError.from_code("provider_not_configured") from exc
        return OpenAI(api_key=api_key)

    @property
    def max_context_tokens(self) -> int:
        return 128000

    def estimate_cost(self, tokens_in: int, tokens_out: int) -> float:
        return round((tokens_in * 0.00000015) + (tokens_out * 0.0000006), 8)

    def generate(self, messages: list[dict[str, Any]], context: Any = None) -> str:
        client = self._client()
        try:
            resp = client.chat.completions.create(
                model=self.model,
                messages=messages,  # type: ignore[arg-type]
                max_tokens=1000,
                temperature=0.3,
            )
            return resp.choices[0].message.content or ""
        except AILIZAError:
            raise
        except Exception as exc:  # noqa: BLE001
            print(f"AILIZA OPENAI ERROR | type={type(exc).__name__} model={self.model}", flush=True)
            raise AILIZAError.from_code("provider_not_configured") from exc

    def stream(self, messages: list[dict[str, Any]], context: Any = None) -> Iterator[str]:
        yield self.generate(messages, context)
