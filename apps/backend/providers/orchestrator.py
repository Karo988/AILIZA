"""
AILIZA Provider-Orchestrator
============================
Einziger Pfad fuer externe LLM-Calls.

Reihenfolge je Call:
  Kill-Switch -> ProviderProfile aktiv -> Provider waehlen -> generate ->
  Performance + Cost loggen.

Fehlt ein API-Key oder Provider: verstaendliche deutsche Fehlermeldung, kein Crash.
"""
from __future__ import annotations

import time
from collections.abc import Iterator
from typing import Any

try:
    from ..kill_switch import enforce_kill_switch
    from ..errors import AILIZAError
    from .base import LLMProvider
    from .groq_provider import GroqProvider
    from .anthropic_provider import AnthropicProvider
except ImportError:  # pragma: no cover
    from kill_switch import enforce_kill_switch
    from errors import AILIZAError
    from providers.base import LLMProvider
    from providers.groq_provider import GroqProvider
    from providers.anthropic_provider import AnthropicProvider


class ProviderOrchestrator:
    def __init__(self, providers: dict[str, LLMProvider] | None = None, default_provider: str = "groq") -> None:
        if providers is None:
            providers = {
                "groq": GroqProvider(),
                "anthropic": AnthropicProvider(),
            }
        self.providers = providers
        self.default_provider = default_provider

    def _select(self, provider_id: str | None) -> LLMProvider:
        pid = provider_id or self.default_provider
        provider = self.providers.get(pid)
        if provider is None:
            raise AILIZAError.from_code("provider_not_configured")
        return provider

    def _log_metrics(self, context: Any, provider: LLMProvider, latency_ms: int,
                     tokens_in: int, tokens_out: int, error_type: str | None) -> None:
        try:
            from ..audit.performance_log import log_performance
            from ..audit.cost_log import log_cost
        except ImportError:  # pragma: no cover
            try:
                from audit.performance_log import log_performance
                from audit.cost_log import log_cost
            except Exception:
                return
        tenant = getattr(context, "tenant_id", "default") if context else "default"
        use_case = getattr(context, "purpose", "") if context else ""
        try:
            log_performance(latency_ms=latency_ms, route="external", provider=provider.provider_id,
                            error_type=error_type, tenant_id=tenant)
            log_cost(tokens_in=tokens_in, tokens_out=tokens_out, provider=provider.provider_id,
                     model=getattr(provider, "model", ""), tenant_id=tenant, use_case=use_case,
                     cost_estimate=provider.estimate_cost(tokens_in, tokens_out))
        except Exception:
            pass

    def generate(self, messages: list[dict[str, Any]], context: Any = None, provider_id: str | None = None) -> str:
        enforce_kill_switch()
        provider = self._select(provider_id)
        # ProviderProfile aktiv: hier ueber Vorhandensein einer Region/Version geprueft
        if not provider.provider_profile_version:
            raise AILIZAError.from_code("provider_not_configured")
        tokens_in = sum(provider.count_tokens(m.get("content", "")) for m in messages)
        start = time.time()
        error_type = None
        try:
            result = provider.generate(messages, context)
            tokens_out = provider.count_tokens(result)
            return result
        except AILIZAError as exc:
            error_type = exc.code
            tokens_out = 0
            raise
        except Exception as exc:  # noqa: BLE001
            error_type = type(exc).__name__
            tokens_out = 0
            raise AILIZAError.from_code("internal_error") from exc
        finally:
            latency_ms = int((time.time() - start) * 1000)
            self._log_metrics(context, provider, latency_ms, tokens_in, tokens_out, error_type)

    def stream(self, messages: list[dict[str, Any]], context: Any = None, provider_id: str | None = None) -> Iterator[str]:
        enforce_kill_switch()
        provider = self._select(provider_id)
        yield from provider.stream(messages, context)
