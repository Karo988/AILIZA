"""
AILIZA LLMProvider Basis-Interface
==================================
Abstrakte Basis fuer alle LLM-Provider-Adapter.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterator
from typing import Any


class LLMProvider(ABC):
    provider_region: str = "unknown"
    provider_profile_version: str = "0.0"
    provider_id: str = "base"

    @abstractmethod
    def generate(self, messages: list[dict[str, Any]], context: Any) -> str:
        ...

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
