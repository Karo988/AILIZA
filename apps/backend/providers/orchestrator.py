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
    from .openai_provider import OpenAIProvider
    from .provider_profiles import check_provider_policy, get_profile
    from ..capabilities.registry import check_capability
    from ..governance.data_governance import DataClass
except ImportError:  # pragma: no cover
    from kill_switch import enforce_kill_switch
    from errors import AILIZAError
    from providers.base import LLMProvider
    from providers.groq_provider import GroqProvider
    from providers.anthropic_provider import AnthropicProvider
    from providers.openai_provider import OpenAIProvider
    from providers.provider_profiles import check_provider_policy, get_profile
    from capabilities.registry import check_capability
    from governance.data_governance import DataClass

try:
    from .openrouter_provider import OpenRouterProvider
    _HAS_OPENROUTER = True
except Exception:
    _HAS_OPENROUTER = False


class ProviderOrchestrator:
    def __init__(self, providers: dict[str, LLMProvider] | None = None, default_provider: str = "groq") -> None:
        if providers is None:
            _p: dict[str, LLMProvider] = {
                "groq": GroqProvider(),
                "openai": OpenAIProvider(),
                "anthropic": AnthropicProvider(),
            }
            if _HAS_OPENROUTER:
                _p["openrouter"] = OpenRouterProvider()
            providers = _p
        self.providers = providers
        self.default_provider = default_provider

    def _failover_order(self, preferred: str | None, data_classes: list[DataClass], use_case: str = "kmu_assistant") -> list[tuple[str, LLMProvider]]:
        """Returns providers sorted by failover_priority, filtered to those allowed for data_classes+use_case."""
        candidates = []
        for pid, prov in self.providers.items():
            profile = get_profile(pid)
            key_present = bool(__import__("os").getenv(
                {"groq": "GROQ_API_KEY", "openai": "OPENAI_API_KEY", "anthropic": "ANTHROPIC_API_KEY"}.get(pid, ""),
                ""
            ))
            allowed, reason = check_provider_policy(pid, data_classes, use_case)
            priority = profile.failover_priority if profile else 99
            print(
                f"AILIZA PROVIDER SELECT | capability={use_case} provider={pid} "
                f"model={getattr(prov, 'model', 'unknown')} "
                f"key_present={key_present} allowed={allowed} "
                f"blocked_reason={repr(reason) if not allowed else ''}",
                flush=True,
            )
            if allowed:
                candidates.append((priority, pid, prov))
        # Sort: preferred provider first if allowed, else by priority
        candidates.sort(key=lambda t: (0 if t[1] == (preferred or self.default_provider) else 1, t[0]))
        return [(pid, prov) for _, pid, prov in candidates]

    def _select(self, provider_id: str | None, data_classes: list[DataClass]) -> LLMProvider:
        """
        Waehlt Provider und prueft ProviderProfile-Policy.
        Fail-closed: kein passendes Profil → AILIZAError.
        """
        pid = provider_id or self.default_provider
        provider = self.providers.get(pid)
        if provider is None:
            raise AILIZAError.from_code("provider_not_configured")

        allowed, reason = check_provider_policy(pid, data_classes)
        if not allowed:
            raise AILIZAError.from_code("policy_blocked", safe_alternatives=[reason])

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

        # Capability-Check: LLM-Call benoetigt Freigabe durch Registry
        data_classes = getattr(context, "data_classes", [DataClass.PUBLIC]) if context else [DataClass.PUBLIC]
        tenant_id = getattr(context, "tenant_id", "default") if context else "default"
        user_id = getattr(context, "user_id", None) if context else None
        redaction_applied = getattr(context, "redaction_applied", False) if context else False
        cap_result = check_capability(
            "llm_call", data_classes=list(data_classes),
            tenant_id=tenant_id, user_id=user_id, redaction_applied=redaction_applied,
        )
        if not cap_result.allowed:
            raise AILIZAError.from_code("policy_blocked")

        use_case = getattr(context, "purpose", "kmu_assistant") if context else "kmu_assistant"
        candidates = self._failover_order(provider_id, list(data_classes), use_case)
        if not candidates:
            raise AILIZAError.from_code("provider_not_configured")

        last_exc: AILIZAError | None = None
        for pid, provider in candidates:
            tokens_in = sum(provider.count_tokens(m.get("content", "")) for m in messages)
            start = time.time()
            error_type = None
            try:
                result = provider.generate(messages, context)
                tokens_out = provider.count_tokens(result)
                print(f"AILIZA PROVIDER OK | provider={pid} model={getattr(provider, 'model', 'unknown')}", flush=True)
                return result
            except AILIZAError as exc:
                error_type = exc.code
                tokens_out = 0
                print(f"AILIZA PROVIDER FAIL | provider={pid} code={exc.code} — trying next", flush=True)
                last_exc = exc
            except Exception as exc:  # noqa: BLE001
                error_type = type(exc).__name__
                tokens_out = 0
                print(f"AILIZA PROVIDER FAIL | provider={pid} type={error_type} — trying next", flush=True)
                last_exc = AILIZAError.from_code("internal_error")
            finally:
                latency_ms = int((time.time() - start) * 1000)
                self._log_metrics(context, provider, latency_ms, tokens_in, tokens_out, error_type)

        raise last_exc or AILIZAError.from_code("provider_not_configured")

    def stream(self, messages: list[dict[str, Any]], context: Any = None, provider_id: str | None = None) -> Iterator[str]:
        enforce_kill_switch()
        data_classes = getattr(context, "data_classes", [DataClass.PUBLIC]) if context else [DataClass.PUBLIC]
        provider = self._select(provider_id, list(data_classes))
        yield from provider.stream(messages, context)
