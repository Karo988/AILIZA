"""
AILIZA Anthropic Provider
=========================
Adapter fuer die Anthropic Messages API.
Graceful import: ohne installiertes SDK verstaendliche Fehlermeldung.
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


class AnthropicProvider(LLMProvider):
    provider_region = "US"
    provider_profile_version = "1.0"
    provider_id = "anthropic"

    def __init__(self, model: str = "claude-sonnet-4-6-20251001") -> None:
        self.model = model

    def _client(self):
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise AILIZAError.from_code("no_api_key")
        try:
            import anthropic
        except ImportError as exc:  # pragma: no cover
            raise AILIZAError.from_code("provider_not_configured") from exc
        return anthropic.Anthropic(api_key=api_key)

    @property
    def max_context_tokens(self) -> int:
        return 200000

    def estimate_cost(self, tokens_in: int, tokens_out: int) -> float:
        return round((tokens_in * 0.000003) + (tokens_out * 0.000015), 8)

    def _split_system(self, messages: list[dict[str, Any]]):
        system = ""
        convo = []
        for m in messages:
            if m.get("role") == "system":
                system = m.get("content", "")
            else:
                convo.append({"role": m["role"], "content": m.get("content", "")})
        return system, convo

    def generate(self, messages: list[dict[str, Any]], context: Any = None) -> str:
        client = self._client()
        system, convo = self._split_system(messages)
        try:
            resp = client.messages.create(
                model=self.model,
                max_tokens=1000,
                system=system or None,
                messages=convo,
            )
            return "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
        except AILIZAError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise AILIZAError.from_code("provider_not_configured") from exc

    def stream(self, messages: list[dict[str, Any]], context: Any = None) -> Iterator[str]:
        client = self._client()
        system, convo = self._split_system(messages)
        try:
            with client.messages.stream(
                model=self.model,
                max_tokens=1000,
                system=system or None,
                messages=convo,
            ) as stream:
                for text in stream.text_stream:
                    yield text
        except AILIZAError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise AILIZAError.from_code("provider_not_configured") from exc
