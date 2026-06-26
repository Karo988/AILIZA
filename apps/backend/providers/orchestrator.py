"""
AILIZA Provider-Orchestrator
============================
Einziger Pfad fuer externe LLM-Calls.

Reihenfolge je Call:
  Kill-Switch -> Registry-Check -> ProviderProfile (Legacy) -> Provider waehlen
  -> generate -> Performance + Cost loggen.

Registry-Regeln (Vorrang vor Legacy provider_profiles.py):
  - Provider muss in provider_registry.yaml vorhanden sein
  - enabled=True UND admin_approved=True erforderlich
  - Datenklassen duerfen nicht in forbidden_data stehen
  - Registry nicht ladbar → keine externen Provider (fail-closed)

Legacy provider_profiles.py bleibt als zweite Pruefschicht erhalten.
Kann spaeter entfernt werden, sobald Registry vollstaendig ist.
"""
from __future__ import annotations

import os
import time
from collections.abc import Iterator
from typing import Any

try:
    from ..kill_switch import enforce_kill_switch
    from ..errors import AILIZAError, MESSAGES
    from .base import LLMProvider
    from .groq_provider import GroqProvider
    from .anthropic_provider import AnthropicProvider
    from .openai_provider import OpenAIProvider
    from .provider_profiles import check_provider_policy, get_profile
    from ..capabilities.registry import check_capability
    from ..governance.data_governance import DataClass
    from ..registry.registry_loader import (
        check_provider_in_registry,
        get_routing_for_task,
        get_registry,
    )
except ImportError:  # pragma: no cover
    from kill_switch import enforce_kill_switch
    from errors import AILIZAError, MESSAGES
    from providers.base import LLMProvider
    from providers.groq_provider import GroqProvider
    from providers.anthropic_provider import AnthropicProvider
    from providers.openai_provider import OpenAIProvider
    from providers.provider_profiles import check_provider_policy, get_profile
    from capabilities.registry import check_capability
    from governance.data_governance import DataClass
    from registry.registry_loader import (
        check_provider_in_registry,
        get_routing_for_task,
        get_registry,
    )

try:
    from .openrouter_provider import OpenRouterProvider
    _HAS_OPENROUTER = True
except Exception:
    _HAS_OPENROUTER = False

# Mapping API-Key-Env-Variablen je Provider
_KEY_ENV: dict[str, str] = {
    "groq": "GROQ_API_KEY",
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
}


class ProviderOrchestrator:
    def __init__(
        self,
        providers: dict[str, LLMProvider] | None = None,
        default_provider: str = "groq",
    ) -> None:
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

    # ── Registry-Check ─────────────────────────────────────────────────────────

    def _registry_check(
        self,
        pid: str,
        data_class_strings: list[str],
    ) -> tuple[bool, str, str]:
        """
        Vorgelagerte Registry-Prüfung.
        Gibt (allowed, error_code, reason) zurück.
        Registry hat Vorrang vor Legacy provider_profiles.py.
        """
        allowed, code, reason = check_provider_in_registry(pid, data_class_strings)
        _check_reason = repr(reason) if not allowed else "'ok'"
        print(
            f"AILIZA REGISTRY CHECK | provider={pid} "
            f"usable={allowed} "
            f"reason={_check_reason}",
            flush=True,
        )
        return allowed, code, reason

    # ── Failover-Reihenfolge ────────────────────────────────────────────────────

    def _failover_order(
        self,
        preferred: str | None,
        data_classes: list[DataClass],
        use_case: str = "kmu_assistant",
        task_type: str | None = None,
    ) -> list[tuple[str, LLMProvider]]:
        """
        Gibt Provider sortiert nach Priorität zurück.
        Filtert nach:
          1. Registry (Vorrang): enabled + admin_approved + Datenklassen
          2. Legacy provider_profiles.py (zweite Schicht)
          3. Routing-Regel (optionale Bevorzugung aus routing_rules.yaml)

        health_status=down → Provider wird ans Ende gestellt, aber nicht entfernt
        (falls alle anderen auch scheitern, wird er als letzter Fallback versucht).
        """
        dc_strings = [dc.value if hasattr(dc, "value") else str(dc) for dc in data_classes]

        # Routing-Regel: bestimmt bevorzugte Provider für diesen Aufgabentyp
        routing_rule = get_routing_for_task(task_type or "general_task") if task_type else None
        preferred_by_routing: list[str] = getattr(routing_rule, "preferred_providers", [])

        if routing_rule:
            print(
                f"AILIZA ROUTING RULE | task={task_type or 'general_task'} "
                f"providers={len(preferred_by_routing)} "
                f"web_search={routing_rule.web_search} "
                f"human_review={routing_rule.human_review} "
                f"draft_only={routing_rule.draft_only}",
                flush=True,
            )

        candidates: list[tuple[int, int, str, LLMProvider]] = []

        for pid, prov in self.providers.items():
            key_present = bool(os.getenv(_KEY_ENV.get(pid, ""), ""))

            # 1. Registry-Check (Vorrang)
            reg_allowed, reg_code, reg_reason = self._registry_check(pid, dc_strings)

            # 2. Legacy provider_profiles.py (nur wenn Registry OK)
            legacy_allowed, legacy_reason = (True, "ok")
            if reg_allowed:
                legacy_allowed, legacy_reason = check_provider_policy(pid, data_classes, use_case)

            allowed = reg_allowed and legacy_allowed
            reason = reg_reason if not reg_allowed else (legacy_reason if not legacy_allowed else "ok")

            # Registry-Priorität als Basis, dann Routing-Bevorzugung
            reg_entry = None
            try:
                reg_entry = get_registry().get_provider(pid)
            except Exception:
                pass
            base_priority = reg_entry.failover_priority if reg_entry else 99
            # Routing-bevorzugte Provider bekommen einen Bonus in der Reihenfolge
            routing_bonus = preferred_by_routing.index(pid) if pid in preferred_by_routing else 50

            # health_status=down → ans Ende (Prio +1000), aber nicht entfernen
            health_penalty = 0
            if reg_entry and reg_entry.health_status == "down":
                health_penalty = 1000

            print(
                f"AILIZA PROVIDER SELECT | capability={use_case} provider={pid} "
                f"model={getattr(prov, 'model', 'unknown')} "
                f"key_present={key_present} allowed={allowed} "
                f"registry={reg_allowed} "
                f"blocked_reason={repr(reason) if not allowed else ''}",
                flush=True,
            )

            if allowed:
                candidates.append((base_priority + health_penalty, routing_bonus, pid, prov))

        # Sortierung: 1. preferred/explicit, 2. routing_bonus, 3. base_priority
        explicit_preferred = preferred or self.default_provider
        candidates.sort(
            key=lambda t: (
                0 if t[2] == explicit_preferred else 1,
                t[1],   # routing_bonus
                t[0],   # base_priority + health_penalty
            )
        )
        return [(pid, prov) for _, _, pid, prov in candidates]

    # ── Legacy _select (für stream()) ──────────────────────────────────────────

    def _select(self, provider_id: str | None, data_classes: list[DataClass]) -> LLMProvider:
        """
        Einzelner Provider-Select ohne Failover (für stream()).
        Prüft Registry UND Legacy-Profil.
        Fail-closed: kein passendes Profil → AILIZAError.
        """
        pid = provider_id or self.default_provider
        provider = self.providers.get(pid)
        if provider is None:
            raise AILIZAError.from_code("provider_not_configured")

        dc_strings = [dc.value if hasattr(dc, "value") else str(dc) for dc in data_classes]
        reg_allowed, reg_code, reg_reason = self._registry_check(pid, dc_strings)
        if not reg_allowed:
            raise AILIZAError.from_code(reg_code, safe_alternatives=[reg_reason])

        allowed, reason = check_provider_policy(pid, data_classes)
        if not allowed:
            raise AILIZAError.from_code("policy_blocked", safe_alternatives=[reason])

        return provider

    # ── Metrics ────────────────────────────────────────────────────────────────

    def _log_metrics(
        self,
        context: Any,
        provider: LLMProvider,
        latency_ms: int,
        tokens_in: int,
        tokens_out: int,
        error_type: str | None,
    ) -> None:
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
            log_performance(
                latency_ms=latency_ms, route="external",
                provider=provider.provider_id, error_type=error_type, tenant_id=tenant,
            )
            log_cost(
                tokens_in=tokens_in, tokens_out=tokens_out,
                provider=provider.provider_id, model=getattr(provider, "model", ""),
                tenant_id=tenant, use_case=use_case,
                cost_estimate=provider.estimate_cost(tokens_in, tokens_out),
            )
        except Exception:
            pass

    # ── generate() ─────────────────────────────────────────────────────────────

    def generate(
        self,
        messages: list[dict[str, Any]],
        context: Any = None,
        provider_id: str | None = None,
    ) -> str:
        enforce_kill_switch()

        data_classes = getattr(context, "data_classes", [DataClass.PUBLIC]) if context else [DataClass.PUBLIC]
        tenant_id = getattr(context, "tenant_id", "default") if context else "default"
        user_id = getattr(context, "user_id", None) if context else None
        redaction_applied = getattr(context, "redaction_applied", False) if context else False

        # Capability-Check (Governance-Gate — unverändert)
        cap_result = check_capability(
            "llm_call", data_classes=list(data_classes),
            tenant_id=tenant_id, user_id=user_id, redaction_applied=redaction_applied,
        )
        if not cap_result.allowed:
            raise AILIZAError.from_code("policy_blocked")

        use_case = getattr(context, "purpose", "kmu_assistant") if context else "kmu_assistant"
        task_type = getattr(context, "task_type", None) if context else None

        candidates = self._failover_order(provider_id, list(data_classes), use_case, task_type)
        if not candidates:
            raise AILIZAError.from_code("provider_not_configured")

        # Ursachen je Provider sammeln — für verständliche all_providers_failed-Meldung
        failure_reasons: list[str] = []
        last_exc: AILIZAError | None = None

        for pid, provider in candidates:
            tokens_in = sum(provider.count_tokens(m.get("content", "")) for m in messages)
            start = time.time()
            error_type = None
            try:
                result = provider.generate(messages, context)
                tokens_out = provider.count_tokens(result)
                print(
                    f"AILIZA PROVIDER OK | provider={pid} "
                    f"model={getattr(provider, 'model', 'unknown')}",
                    flush=True,
                )
                return result
            except AILIZAError as exc:
                error_type = exc.code
                tokens_out = 0
                # Ursache für finale Fehlermeldung merken (ohne PII/Keys)
                reason_parts = exc.safe_alternatives or []
                reason_summary = reason_parts[0] if reason_parts else exc.code
                failure_reasons.append(f"{pid}: {reason_summary}")
                print(f"AILIZA PROVIDER FAIL | provider={pid} code={exc.code} — trying next", flush=True)
                last_exc = exc
            except Exception as exc:  # noqa: BLE001
                error_type = type(exc).__name__
                tokens_out = 0
                failure_reasons.append(f"{pid}: {error_type}")
                print(f"AILIZA PROVIDER FAIL | provider={pid} type={error_type} — trying next", flush=True)
                last_exc = AILIZAError.from_code("internal_error")
            finally:
                latency_ms = int((time.time() - start) * 1000)
                self._log_metrics(context, provider, latency_ms, tokens_in, tokens_out, error_type)

        raise AILIZAError.from_code("all_providers_failed", safe_alternatives=failure_reasons)

    # ── stream() ───────────────────────────────────────────────────────────────

    def stream(
        self,
        messages: list[dict[str, Any]],
        context: Any = None,
        provider_id: str | None = None,
    ) -> Iterator[str]:
        enforce_kill_switch()
        data_classes = getattr(context, "data_classes", [DataClass.PUBLIC]) if context else [DataClass.PUBLIC]
        provider = self._select(provider_id, list(data_classes))
        yield from provider.stream(messages, context)
