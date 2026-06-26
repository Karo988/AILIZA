"""
AILIZA Registry Loader
======================
Lädt und validiert provider_registry.yaml, tool_registry.yaml,
routing_rules.yaml und provider_health.json.

Regeln:
- Unbekannter oder nicht freigegebener Provider → nie genutzt (fail-closed).
- Neuer Provider → bleibt pending bis Admin-Freigabe.
- Watch-Agent darf nur pending_changes schreiben, niemals direkt aktivieren.
- Alle Änderungen an der Registry → Audit-Log.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_REGISTRY_DIR = Path(__file__).parent

# ── Datenklassen ──────────────────────────────────────────────────────────────

@dataclass
class ProviderEntry:
    provider_id: str
    type: str
    enabled: bool
    admin_approved: bool
    region: str
    transfer_basis: str
    avv_signed: bool
    allowed_data: list[str]
    forbidden_data: list[str]
    default_model: str
    fallback_models: list[str]
    failover_priority: int
    health_status: str
    logs_prompts: bool
    used_for_training: bool
    notes: str = ""

    def is_usable(self) -> bool:
        """Fail-closed: Provider darf nur genutzt werden wenn enabled UND admin_approved."""
        return self.enabled and self.admin_approved

    def allows_data(self, data_class: str) -> bool:
        dc = data_class.lower()
        if dc in self.forbidden_data:
            return False
        return dc in self.allowed_data

    def blocks_reason(self) -> str | None:
        if not self.admin_approved:
            return f"Provider '{self.provider_id}' wartet auf Admin-Freigabe."
        if not self.enabled:
            return f"Provider '{self.provider_id}' ist deaktiviert."
        if self.transfer_basis == "none":
            return f"Provider '{self.provider_id}': kein Drittland-Transfermechanismus."
        return None


@dataclass
class ToolEntry:
    tool_id: str
    type: str
    enabled: bool
    admin_approved: bool
    runs_local: bool
    requires_user_approval: bool
    region: str
    transfer_basis: str
    avv_signed: bool
    allowed_data: list[str]
    forbidden_data: list[str]
    description: str = ""
    notes: str = ""

    def is_usable(self) -> bool:
        return self.enabled and self.admin_approved

    def allows_data(self, data_class: str) -> bool:
        dc = data_class.lower()
        if dc in self.forbidden_data:
            return False
        return dc in self.allowed_data


@dataclass
class RoutingRule:
    rule_id: str
    description: str
    preferred_providers: list[str]
    preferred_tools: list[str]
    web_search: bool
    draft_only: bool
    human_review: bool
    allowed_data: list[str]
    requires_approval: bool = False
    notes: str = ""


@dataclass
class PendingChange:
    change_id: str
    change_type: str        # provider_health | new_provider | model_update | routing_suggestion
    target: str             # provider_id oder tool_id
    proposed_value: Any
    reason: str
    created_at: str
    created_by: str         # watch_agent | admin | system
    status: str = "pending" # pending | approved | rejected


@dataclass
class Registry:
    providers: dict[str, ProviderEntry] = field(default_factory=dict)
    tools: dict[str, ToolEntry] = field(default_factory=dict)
    routing_rules: dict[str, RoutingRule] = field(default_factory=dict)
    provider_health: dict[str, Any] = field(default_factory=dict)
    pending_changes: list[PendingChange] = field(default_factory=list)

    def get_provider(self, provider_id: str) -> ProviderEntry | None:
        return self.providers.get(provider_id)

    def get_usable_providers(self) -> list[ProviderEntry]:
        return [p for p in self.providers.values() if p.is_usable()]

    def get_tool(self, tool_id: str) -> ToolEntry | None:
        return self.tools.get(tool_id)

    def get_usable_tools(self) -> list[ToolEntry]:
        return [t for t in self.tools.values() if t.is_usable()]

    def get_routing_rule(self, rule_id: str) -> RoutingRule | None:
        return self.routing_rules.get(rule_id, self.routing_rules.get("general_task"))


# ── YAML loader (ohne externe Abhängigkeit) ───────────────────────────────────

def _load_yaml(path: Path) -> dict:
    """Minimaler YAML-Parser für einfache Key-Value-Strukturen."""
    try:
        import yaml  # type: ignore[import]
        with open(path, encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except ImportError:
        pass
    # Fallback: json (yaml ist Superset von json für einfache Strukturen)
    try:
        with open(path.with_suffix(".json"), encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        pass
    logger.error("Registry-Datei nicht ladbar: %s (PyYAML fehlt und kein .json Fallback)", path)
    return {}


# ── Loader ────────────────────────────────────────────────────────────────────

def _load_providers(data: dict) -> dict[str, ProviderEntry]:
    entries: dict[str, ProviderEntry] = {}
    for pid, cfg in (data.get("providers") or {}).items():
        try:
            entries[pid] = ProviderEntry(
                provider_id=pid,
                type=cfg.get("type", "text_llm"),
                enabled=bool(cfg.get("enabled", False)),
                admin_approved=bool(cfg.get("admin_approved", False)),
                region=cfg.get("region", "unknown"),
                transfer_basis=cfg.get("transfer_basis", "none"),
                avv_signed=bool(cfg.get("avv_signed", False)),
                allowed_data=[d.lower() for d in cfg.get("allowed_data", [])],
                forbidden_data=[d.lower() for d in cfg.get("forbidden_data", [])],
                default_model=cfg.get("default_model", "unknown"),
                fallback_models=cfg.get("fallback_models", []),
                failover_priority=int(cfg.get("failover_priority", 99)),
                health_status=cfg.get("health_status", "unknown"),
                logs_prompts=bool(cfg.get("logs_prompts", True)),
                used_for_training=bool(cfg.get("used_for_training", False)),
                notes=cfg.get("notes", ""),
            )
        except Exception as exc:  # noqa: BLE001
            logger.error("Fehler beim Laden von Provider '%s': %s", pid, exc)
    return entries


def _load_tools(data: dict) -> dict[str, ToolEntry]:
    entries: dict[str, ToolEntry] = {}
    for tid, cfg in (data.get("tools") or {}).items():
        try:
            entries[tid] = ToolEntry(
                tool_id=tid,
                type=cfg.get("type", "unknown"),
                enabled=bool(cfg.get("enabled", False)),
                admin_approved=bool(cfg.get("admin_approved", False)),
                runs_local=bool(cfg.get("runs_local", False)),
                requires_user_approval=bool(cfg.get("requires_user_approval", True)),
                region=cfg.get("region", "unknown"),
                transfer_basis=cfg.get("transfer_basis", "none"),
                avv_signed=bool(cfg.get("avv_signed", False)),
                allowed_data=[d.lower() for d in cfg.get("allowed_data", [])],
                forbidden_data=[d.lower() for d in cfg.get("forbidden_data", [])],
                description=cfg.get("description", ""),
                notes=cfg.get("notes", ""),
            )
        except Exception as exc:  # noqa: BLE001
            logger.error("Fehler beim Laden von Tool '%s': %s", tid, exc)
    return entries


def _load_routing(data: dict) -> dict[str, RoutingRule]:
    rules: dict[str, RoutingRule] = {}
    for rid, cfg in (data.get("rules") or {}).items():
        try:
            rules[rid] = RoutingRule(
                rule_id=rid,
                description=cfg.get("description", ""),
                preferred_providers=cfg.get("preferred_providers", []),
                preferred_tools=cfg.get("preferred_tools", []),
                web_search=bool(cfg.get("web_search", False)),
                draft_only=bool(cfg.get("draft_only", False)),
                human_review=bool(cfg.get("human_review", False)),
                requires_approval=bool(cfg.get("requires_approval", False)),
                allowed_data=[d.lower() for d in cfg.get("allowed_data", [])],
                notes=cfg.get("notes", ""),
            )
        except Exception as exc:  # noqa: BLE001
            logger.error("Fehler beim Laden von Routing-Regel '%s': %s", rid, exc)
    return rules


def _load_pending_changes(health_data: dict) -> list[PendingChange]:
    changes = []
    for item in health_data.get("pending_changes", []):
        try:
            changes.append(PendingChange(
                change_id=item["change_id"],
                change_type=item["change_type"],
                target=item["target"],
                proposed_value=item.get("proposed_value"),
                reason=item.get("reason", ""),
                created_at=item.get("created_at", ""),
                created_by=item.get("created_by", "unknown"),
                status=item.get("status", "pending"),
            ))
        except Exception as exc:  # noqa: BLE001
            logger.error("Fehler beim Laden einer PendingChange: %s", exc)
    return changes


# ── Validierung ───────────────────────────────────────────────────────────────

_REQUIRED_PROVIDERS = {"groq", "openai", "local"}
_REQUIRED_RULES = {"writing_task", "research_task", "general_task"}


def validate_registry(registry: Registry) -> list[str]:
    """Gibt Liste von Warnungen zurück. Leere Liste = OK."""
    warnings: list[str] = []

    for pid in _REQUIRED_PROVIDERS:
        if pid not in registry.providers:
            warnings.append(f"Pflicht-Provider '{pid}' fehlt in der Registry.")

    for rid in _REQUIRED_RULES:
        if rid not in registry.routing_rules:
            warnings.append(f"Pflicht-Routing-Regel '{rid}' fehlt.")

    for pid, entry in registry.providers.items():
        if entry.enabled and not entry.admin_approved:
            warnings.append(
                f"Provider '{pid}' ist enabled=true aber admin_approved=false — "
                "wird trotzdem BLOCKIERT (fail-closed)."
            )
        if entry.transfer_basis == "none" and entry.enabled:
            warnings.append(
                f"Provider '{pid}': transfer_basis=none aber enabled=true — "
                "Provider wird blockiert."
            )
        for dc in entry.allowed_data:
            if dc in entry.forbidden_data:
                warnings.append(
                    f"Provider '{pid}': Datenklasse '{dc}' steht in allowed_data UND forbidden_data — "
                    "forbidden_data hat Vorrang."
                )

    return warnings


# ── Audit-Log für Registry-Änderungen ────────────────────────────────────────

def _audit_registry_change(
    action: str,
    target: str,
    change_type: str,
    actor: str = "system",
    details: str = "",
) -> None:
    """Schreibt Registry-Änderungen ins Security-Log. Niemals Inhalte loggen."""
    try:
        from audit.security_log import log_security
    except ImportError:
        try:
            from apps.backend.audit.security_log import log_security  # type: ignore[no-redef]
        except ImportError:
            logger.info(
                "AILIZA REGISTRY AUDIT | action=%s target=%s type=%s actor=%s details=%s",
                action, target, change_type, actor, details,
            )
            return
    log_security(
        incident_type=f"registry.{action}.{change_type}",
        severity="info",
    )
    logger.info(
        "AILIZA REGISTRY AUDIT | action=%s target=%s type=%s actor=%s details=%s",
        action, target, change_type, actor, details,
    )


# ── Pending-Change schreiben ──────────────────────────────────────────────────

def add_pending_change(
    change_type: str,
    target: str,
    proposed_value: Any,
    reason: str,
    created_by: str = "watch_agent",
) -> PendingChange:
    """
    Watch-Agent darf NUR pending_changes hinzufügen — niemals direkt aktivieren.
    Die Änderung wird in provider_health.json gespeichert und auditiert.
    """
    health_path = _REGISTRY_DIR / "provider_health.json"
    try:
        with open(health_path, encoding="utf-8") as f:
            health_data = json.load(f)
    except Exception:
        health_data = {"pending_changes": []}

    now = datetime.now(timezone.utc).isoformat()
    change_id = f"{change_type}_{target}_{now}"

    change = PendingChange(
        change_id=change_id,
        change_type=change_type,
        target=target,
        proposed_value=proposed_value,
        reason=reason,
        created_at=now,
        created_by=created_by,
        status="pending",
    )

    health_data.setdefault("pending_changes", []).append({
        "change_id": change_id,
        "change_type": change_type,
        "target": target,
        "proposed_value": proposed_value,
        "reason": reason,
        "created_at": now,
        "created_by": created_by,
        "status": "pending",
    })

    with open(health_path, "w", encoding="utf-8") as f:
        json.dump(health_data, f, indent=2, ensure_ascii=False)

    _audit_registry_change(
        action="pending_change_created",
        target=target,
        change_type=change_type,
        actor=created_by,
        details=f"reason={reason!r}",
    )

    print(
        f"AILIZA REGISTRY | pending_change created | type={change_type} "
        f"target={target} by={created_by}",
        flush=True,
    )
    return change


# ── Haupt-Load-Funktion ───────────────────────────────────────────────────────

def load_registry() -> Registry:
    """
    Lädt alle Registry-Dateien.
    Fail-safe: fehlende Dateien → Warnung + leere Registry (kein Absturz).
    Validierungswarnungen werden geloggt aber stoppen den Start nicht.
    """
    provider_data = _load_yaml(_REGISTRY_DIR / "provider_registry.yaml")
    tool_data = _load_yaml(_REGISTRY_DIR / "tool_registry.yaml")
    routing_data = _load_yaml(_REGISTRY_DIR / "routing_rules.yaml")

    health_path = _REGISTRY_DIR / "provider_health.json"
    try:
        with open(health_path, encoding="utf-8") as f:
            health_data = json.load(f)
    except FileNotFoundError:
        health_data = {}
    except Exception as exc:
        logger.warning("provider_health.json nicht lesbar: %s", exc)
        health_data = {}

    registry = Registry(
        providers=_load_providers(provider_data),
        tools=_load_tools(tool_data),
        routing_rules=_load_routing(routing_data),
        provider_health=health_data.get("providers", {}),
        pending_changes=_load_pending_changes(health_data),
    )

    warnings = validate_registry(registry)
    for w in warnings:
        logger.warning("AILIZA REGISTRY VALIDATION | %s", w)
        print(f"AILIZA REGISTRY WARN | {w}", flush=True)

    usable = [p.provider_id for p in registry.get_usable_providers()]
    usable_tools = [t.tool_id for t in registry.get_usable_tools()]
    pending_count = sum(1 for c in registry.pending_changes if c.status == "pending")

    print(
        f"AILIZA REGISTRY LOADED | providers={len(registry.providers)} "
        f"usable_providers={usable} "
        f"tools={len(registry.tools)} usable_tools={usable_tools} "
        f"routing_rules={len(registry.routing_rules)} "
        f"pending_changes={pending_count}",
        flush=True,
    )

    return registry


# ── Singleton ─────────────────────────────────────────────────────────────────

_registry: Registry | None = None


def get_registry() -> Registry:
    global _registry
    if _registry is None:
        _registry = load_registry()
    return _registry


def reload_registry() -> Registry:
    """Für Tests und Admin-Reload."""
    global _registry
    _registry = load_registry()
    return _registry
