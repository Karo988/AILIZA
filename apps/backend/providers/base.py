"""
AILIZA LLMProvider Basis-Interface
==================================
Abstrakte Basis fuer alle LLM-Provider-Adapter.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterator
from typing import Any

try:
    from .gate_types import ProviderResult
except ImportError:  # pragma: no cover
    from providers.gate_types import ProviderResult


class LLMProvider(ABC):
    provider_region: str = "unknown"
    provider_profile_version: str = "0.0"
    provider_id: str = "base"

    @abstractmethod
    def generate(self, messages: list[dict[str, Any]], context: Any) -> str:
        ...

    def generate_with_meta(
        self,
        messages: list[dict[str, Any]],
        context: Any = None,
        response_format: dict[str, Any] | None = None,
    ) -> ProviderResult:
        """Wie generate(), aber mit Metadaten (z.B. stop_reason) fuer das
        Dual-Gate-Refusal-Netz. response_format (optional, PR-5): nur
        wirksam bei Adaptern mit supports_json_mode=True, sonst ignoriert
        (Default-Implementierung fuer Adapter ohne Metadaten -- kein Bruch)."""
        return ProviderResult(text=self.generate(messages, context), stop_reason=None)

    @abstractmethod
    def stream(self, messages: list[dict[str, Any]], context: Any) -> Iterator[str]:
        ...

    def count_tokens(self, text: str) -> int:
        if not text:
            return 0
        return int(len(text.split()) * 1.3)

    def estimate_cost(self, tokens_in: int, tokens_out: int) -> float:
        # Default: grobe Schaetzung, Adapter ueberschreiben dies.
        return round((tokens_in + tokens_out) / 1000.0 * 0.001, 6)

    @property
    def supports_streaming(self) -> bool:
        return True

    @property
    def supports_json_mode(self) -> bool:
        return False

    @property
    def max_context_tokens(self) -> int:
        return 8192
