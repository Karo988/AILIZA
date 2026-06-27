"""
AILIZA Core API — Andockpunkt fuer den Codex-Orchestrator
==========================================================
Alle Governance-Entscheidungen laufen durch dieses Modul.
Der Orchestrator (Codex oder Claude Code) darf NUR diese Funktionen nutzen —
niemals direkt Policy-/Registry-/Kill-Switch-Module importieren.

Wichtig:
- Jede Funktion ist fail-closed: bei Fehler → blockiert, nie allow.
- Keine Secrets, keine vollstaendigen Prompts, keine PII in Rueckgabewerten.
- Der Orchestrator kann anfragen — die Entscheidung liegt immer bei AILIZA Core.

Fuer den Codex-Orchestrator relevante Endpunkte:
  evaluate_policy(context)           → PolicyResultV2
  evaluate_capability(...)           → CapabilityCheckResult
  get_provider_profile(provider_id)  → dict | None
  list_providers()                   → list[dict]
  list_capabilities()                → list[dict]
  check_kill_switch(scope, name)     → dict
  create_approval_preview(...)       → ApprovalPreview
  write_audit_event(...)             → None
  get_core_status()                  → dict (Health-Check)
"""
from __future__ import annotations

from typing import Any

# ── Interne Importe (Governance-Core) ─────────────────────────────────────────
try:
    from .policy import PolicyContext, PolicyResultV2, evaluate_policy as _evaluate_policy
    from .capabilities.registry import (
        check_capability as _check_capability,
        get_all_capabilities,
        CapabilityCheckResult,
    )
    from .providers.provider_profiles import (
        get_profile,
        get_active_profiles,
        profile_to_dict,
        check_provider_policy,
    )
    from .kill_switch import (
        check_kill_switch as _check_kill_switch,
        is_external_llm_enabled,
        get_operation_mode,
        kill_switch_metadata,
    )
    from .approval import create_approval_preview as _create_approval_preview, ApprovalPreview
    from .governance.data_governance import DataClass, DataTarget
    from .governance.data_matrix import PolicyDecision
    from .errors import AILIZAError
except ImportError:
    from policy import PolicyContext, PolicyResultV2, evaluate_policy as _evaluate_policy
    from capabilities.registry import (
        check_capability as _check_capability,
        get_all_capabilities,
        CapabilityCheckResult,
    )
    from providers.provider_profiles import (
        get_profile,
        get_active_profiles,
        profile_to_dict,
        check_provider_policy,
    )
    from kill_switch import (
        check_kill_switch as _check_kill_switch,
        is_external_llm_enabled,
        get_operation_mode,
        kill_switch_metadata,
    )
    from approval import create_approval_preview as _create_approval_preview, ApprovalPreview
    from governance.data_governance import DataClass, DataTarget
    from governance.data_matrix import PolicyDecision
    from errors import AILIZAError


# ── Public API ─────────────────────────────────────────────────────────────────

def evaluate_policy(context: PolicyContext) -> PolicyResultV2:
    """
    Governance-Policy-Bewertung.
    Fail-closed: Fehler → BLOCK.
    Orchestrator fragt an — Core entscheidet.
    """
    try:
        return _evaluate_policy(context)
    except Exception:
        return PolicyResultV2(
            decision=PolicyDecision.BLOCK,
            reason="Policy-Bewertung fehlgeschlagen — fail-closed.",
        )


def evaluate_capability(
    capability_id: str,
    data_classes: list[str],
    tenant_id: str = "default",
    user_id: str | None = None,
    redaction_applied: bool = False,
    approval_given: bool = False,
    provider_profile_id: str | None = None,
) -> CapabilityCheckResult:
    """
    Prueft ob eine Capability fuer die gegebenen Datenklassen erlaubt ist.
    data_classes als Strings (z.B. ["public", "personal_data"]).
    Fail-closed: Fehler oder unbekannte Klasse → BLOCK.
    """
    try:
        parsed: list[DataClass] = []
        for dc_str in data_classes:
            try:
                parsed.append(DataClass(dc_str))
            except ValueError:
                # Unbekannte Datenklasse → strengste Annahme
                parsed.append(DataClass.CREDENTIALS)
        return _check_capability(
            capability_id=capability_id,
            data_classes=parsed,
            tenant_id=tenant_id,
            user_id=user_id,
            redaction_applied=redaction_applied,
            approval_given=approval_given,
            provider_profile_id=provider_profile_id,
        )
    except Exception as exc:
        from .capabilities.registry import RiskLevel
        return CapabilityCheckResult(
            capability_id=capability_id,
            allowed=False,
            decision=PolicyDecision.BLOCK,
            reason=f"Capability-Check fehlgeschlagen — fail-closed: {type(exc).__name__}",
            requires_approval=True,
            risk_level=RiskLevel.CRITICAL.value,
            capability_enabled=False,
        )


def get_provider_profile(provider_id: str) -> dict[str, Any] | None:
    """
    Gibt das ProviderProfile als Dict zurueck.
    None wenn nicht registriert oder blockiert.
    Kein API-Key, kein Secret im Rueckgabewert.
    """
    try:
        profile = get_profile(provider_id)
        if profile is None:
            return None
        return profile_to_dict(profile)
    except Exception:
        return None


def list_providers() -> list[dict[str, Any]]:
    """
    Gibt alle aktiven, nicht admin-disabled Provider zurueck.
    Fuer den Orchestrator zur Routingentscheidung.
    """
    try:
        return [profile_to_dict(p) for p in get_active_profiles()]
    except Exception:
        return []


def list_capabilities() -> list[dict[str, Any]]:
    """
    Gibt alle registrierten Capabilities zurueck.
    Fuer den Orchestrator zur Task-/Tool-Auswahl.
    """
    try:
        return get_all_capabilities()
    except Exception:
        return []


def check_kill_switch(scope: str, name: str) -> dict[str, Any]:
    """
    Prueft Kill-Switch fuer scope (global/provider/capability/module) und name.
    Fail-closed: bei Fehler allowed=False.
    """
    try:
        return _check_kill_switch(scope, name)
    except Exception:
        return {"allowed": False, "scope": scope, "name": name,
                "reason": "Kill-Switch-Pruefung fehlgeschlagen — fail-closed",
                "mode": "unknown"}


def create_approval_preview(
    action: str,
    tool: str,
    params: dict[str, Any],
    data_class: str = "unknown",
    capability_id: str | None = None,
    provider_id: str | None = None,
    safe_alternative: str = "Aktion abbrechen oder lokal verarbeiten",
) -> dict[str, Any]:
    """
    Erzeugt eine Vorschau der geplanten Aktion OHNE Ausfuehrung.
    Orchestrator nutzt dies, um dem Nutzer/Admin eine Freigabeanfrage zu zeigen.
    NIEMALS ausfuehren — nur anzeigen.
    """
    try:
        preview = _create_approval_preview(
            action=action,
            tool=tool,
            params=params,
            data_class=data_class,
            capability_id=capability_id,
            provider_id=provider_id,
            safe_alternative=safe_alternative,
        )
        return {
            "preview_only": True,
            "action": preview.action,
            "target_system": preview.target_system,
            "data_class": preview.data_class,
            "risk_level": preview.risk_level,
            "reason": preview.reason,
            "safe_alternative": preview.safe_alternative,
            "required_role": preview.required_role,
            "capability_id": preview.capability_id,
            "provider_id": preview.provider_id,
            "approval_timeout_seconds": preview.approval_timeout_seconds,
        }
    except Exception as exc:
        return {
            "preview_only": True,
            "action": action,
            "target_system": "unbekannt",
            "data_class": data_class,
            "risk_level": "high",
            "reason": f"Vorschau-Erzeugung fehlgeschlagen: {type(exc).__name__}",
            "safe_alternative": safe_alternative,
            "required_role": "admin",
            "capability_id": capability_id,
            "provider_id": provider_id,
            "approval_timeout_seconds": 1800,
        }


def write_audit_event(
    action: str,
    tenant_id: str = "default",
    metadata: dict[str, Any] | None = None,
) -> None:
    """
    Schreibt Audit-Event. Orchestrator nutzt dies nach jeder Entscheidung.
    Kein Inhalt, keine Secrets, keine Prompts in metadata.
    Fail-silent: Audit-Fehler stoppen nie die Hauptverarbeitung.
    """
    try:
        from .database import write_audit_entry
    except ImportError:
        try:
            from database import write_audit_entry
        except Exception:
            return
    # Sicherheitsfilter: blockierte Keys aus metadata entfernen
    _BLOCKED = frozenset({"prompt", "task_content", "secret", "password",
                          "token", "credentials", "totp", "backup_code"})
    safe_meta = {k: v for k, v in (metadata or {}).items()
                 if k.lower() not in _BLOCKED}
    try:
        write_audit_entry(action=action, tenant_id=tenant_id, metadata=safe_meta)
    except Exception:
        pass


def get_core_status() -> dict[str, Any]:
    """
    Health-Check fuer AILIZA Core.
    Gibt Betriebsmodus, Kill-Switch-Status und Anzahl aktiver Provider/Capabilities zurueck.
    Kein Secret, keine Keys.
    """
    try:
        ks_meta = kill_switch_metadata()
        active_providers = len(list_providers())
        active_caps = len([c for c in list_capabilities() if c.get("enabled", False)])
        return {
            "status": "ok",
            "operation_mode": ks_meta.get("operation_mode", "unknown"),
            "external_llm_enabled": ks_meta.get("external_llm_enabled", False),
            "active_providers": active_providers,
            "active_capabilities": active_caps,
            "checked_at": ks_meta.get("checked_at"),
        }
    except Exception as exc:
        return {
            "status": "error",
            "reason": f"Core-Status-Check fehlgeschlagen: {type(exc).__name__}",
            "external_llm_enabled": False,
        }
