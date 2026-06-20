"""
AILIZA OpenRouter Provider
==========================
Adapter fuer die OpenRouter OpenAI-kompatible API.

WICHTIG — Governance-Gates vor Aktivierung:
1. AVV/DPA mit OpenRouter abschliessen (DSGVO Art. 28)
2. Subverarbeiter-Liste pruefen und dokumentieren (Art. 28 Abs. 4)
3. Transferbasis sicherstellen (SCC, DSGVO Art. 46)
4. Admin-Kill-Switch im ProviderProfile (admin_disabled=True) erst nach Pruefung deaktivieren
5. Nur PUBLIC-Daten erlaubt (Aggregator mit unklarer Sub-Provider-Kette)

Fail-closed: Provider ist standardmaessig im ProviderProfile deaktiviert.
Der Orchestrator prueft das ProviderProfile vor jedem Call.
"""
from __future__ import annotations

import json
import os
import urllib.request
from collections.abc import Iterator
from typing import Any

try:
    from .base import LLMProvider
    from ..errors import AILIZAError
except ImportError:  # pragma: no cover
    from providers.base import LLMProvider
    from errors import AILIZAError


OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"


class OpenRouterProvider(LLMProvider):
    provider_region = "US"
    provider_profile_version = "1.1.0"
    provider_id = "openrouter"

    def __init__(self, model: str | None = None) -> None:
        # Model aus Env oder sicherer Default (kein proprietaeres closed-source Modell als default)
        self.model = model or os.getenv("AILIZA_OPENROUTER_MODEL", "meta-llama/llama-3.3-70b-instruct")

    def _api_key(self) -> str:
        key = os.getenv("OPENROUTER_API_KEY")
        if not key:
            raise AILIZAError.from_code("no_api_key")
        return key

    @property
    def max_context_tokens(self) -> int:
        return 32768

    def estimate_cost(self, tokens_in: int, tokens_out: int) -> float:
        # Schaetzung fuer Llama-3.3-70B via OpenRouter (Stand 2026-06, variiert je Modell)
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
            OPENROUTER_URL,
            data=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
                "HTTP-Referer": "https://ailiza.eu",       # OpenRouter: Referer empfohlen
                "X-Title": "AILIZA",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                data = json.loads(resp.read())
                return data["choices"][0]["message"]["content"]
        except AILIZAError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise AILIZAError.from_code("provider_not_configured") from exc

    def stream(self, messages: list[dict[str, Any]], context: Any = None) -> Iterator[str]:
        yield self.generate(messages, context)
