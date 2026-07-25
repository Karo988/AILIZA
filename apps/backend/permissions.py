"""PR 2: Zentraler Permission-Evaluator.

Default Deny: eine Aktion ist grundsaetzlich verboten und wird nur erlaubt,
wenn eine konkrete Regel sie ausdruecklich freigibt. Keine neue numerische
Rollenhierarchie -- fuer APPROVAL_DECIDE wird die BESTEHENDE, bereits an
anderer Stelle im Projekt verwendete Role-Hierarchie (auth/rbac.py) als
Uebergangsloesung genutzt, bis die vollstaendige Fachzustaendigkeits-
Freigabematrix in einem spaeteren PR steht (siehe Artefakt 1/4).

Unbekannte Rollenwerte fallen NICHT wie bei Role.from_str() auf USER zurueck
-- hier gilt Default Deny plus ein internes Diagnose-Audit-Ereignis.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

try:
    from .auth.jwt_handler import TokenData
    from .auth.rbac import Role
    from .database import get_agent_run, get_approval_request, has_active_case_assignment, write_audit_entry
except ImportError:
    from apps.backend.auth.jwt_handler import TokenData
    from apps.backend.auth.rbac import Role
    from apps.backend.database import (
        get_agent_run, get_approval_request, has_active_case_assignment, write_audit_entry,
    )

# ── Aktionsschluessel: stabil, technisch, sprachneutral ─────────────────────
AGENT_RUN_CREATE = "AGENT_RUN_CREATE"
AGENT_RUN_LIST = "AGENT_RUN_LIST"
AGENT_RUN_READ = "AGENT_RUN_READ"
APPROVAL_LIST = "APPROVAL_LIST"
APPROVAL_READ = "APPROVAL_READ"
APPROVAL_DECIDE = "APPROVAL_DECIDE"
CASE_ASSIGNMENT_READ = "CASE_ASSIGNMENT_READ"

GENERIC_DENIED_MESSAGE = "Der angeforderte Eintrag wurde nicht gefunden oder ist für Sie nicht verfügbar."

# Uebergangsweise Mindestrolle fuer APPROVAL_DECIDE ohne passende Zuweisung --
# bestehende Role-Hierarchie, keine Neuerfindung. Ersetzt die vollstaendige
# Fachzustaendigkeits-Matrix erst in einem spaeteren PR.
_DECIDE_MIN_ROLE = Role.MANAGER

_ROLE_MAPPING = {
    "user": Role.USER,
    "audit_viewer": Role.AUDIT_VIEWER,
    "manager": Role.MANAGER,
    "admin": Role.ADMIN,
    "dsb": Role.DSB,
}


@dataclass(frozen=True)
class PermissionResult:
    allowed: bool
    reason_code: str
    reason_de: str


def _allow(reason_code: str) -> PermissionResult:
    return PermissionResult(allowed=True, reason_code=reason_code, reason_de="Zugriff erlaubt.")


def _deny(reason_code: str, reason_de: str) -> PermissionResult:
    return PermissionResult(allowed=False, reason_code=reason_code, reason_de=reason_de)


def _deny_generic() -> PermissionResult:
    return _deny("NOT_FOUND_OR_FORBIDDEN", GENERIC_DENIED_MESSAGE)


def _resolve_role_strict(role_str: str | None) -> Role | None:
    """Strenge Rollenaufloesung NUR fuer neue Permission-Entscheidungen.
    Unbekannt/leer -> None (Default Deny), keine stille Umwandlung auf USER."""
    if not role_str:
        return None
    return _ROLE_MAPPING.get(role_str.lower())


def _as_aware_utc(dt: datetime) -> datetime:
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


def evaluate_permission(
    *,
    action: str,
    actor: TokenData | None,
    tenant_id: str,
    resource_type: str,
    resource_id: str,
    resource_owner_user_id: str | None = None,
    risk_level: str | None = None,
    risk_domains: set[str] | None = None,
) -> PermissionResult:
    # 1. gueltige Sitzung
    if actor is None:
        return _deny("NO_SESSION", "Bitte melden Sie sich an.")

    # Bekannte Rolle? Unbekannt -> Default Deny + Diagnose-Audit (kein stiller USER-Fallback).
    role = _resolve_role_strict(actor.role)
    if role is None:
        write_audit_entry(
            action="permission.unknown_role_denied",
            tenant_id=tenant_id,
            metadata={"action": action, "resource_type": resource_type},
        )
        return _deny("UNKNOWN_ROLE", "Ihre Berechtigung konnte nicht ermittelt werden.")

    # 2. Tenant muss uebereinstimmen -- sonst neutrale Antwort (kein Hinweis
    # auf Existenz/Nichtexistenz in einem fremden Tenant).
    if actor.tenant_id != tenant_id:
        return _deny_generic()

    if action in (AGENT_RUN_READ, APPROVAL_READ):
        if resource_owner_user_id is not None and resource_owner_user_id == actor.user_id:
            return _allow("OWNER")
        case_type = "AGENT_RUN" if action == AGENT_RUN_READ else "APPROVAL"
        if has_active_case_assignment(case_type, resource_id, tenant_id, actor.user_id):
            return _allow("ASSIGNED")
        return _deny_generic()

    if action == APPROVAL_DECIDE:
        return _evaluate_approval_decide(actor, tenant_id, resource_id, role)

    if action in (AGENT_RUN_LIST, APPROVAL_LIST, AGENT_RUN_CREATE, CASE_ASSIGNMENT_READ):
        # Grobe Freigabe der Aktionsklasse -- die eigentliche Owner-/Zuweisungs-
        # Filterung erfolgt direkt in der Datenbankabfrage (list_own_or_assigned_*),
        # nicht durch Laden aller Datensaetze und anschliessendes Verwerfen.
        return _allow("OK")

    return _deny("UNKNOWN_ACTION", "Unbekannte Aktion.")


def _evaluate_approval_decide(
    actor: TokenData, tenant_id: str, resource_id: str, role: Role,
) -> PermissionResult:
    """APPROVAL_DECIDE wird IMMER frisch aus der Datenbank geprueft (Status,
    Ablauf, Owner) -- kein Vertrauen auf vom Aufrufer mitgegebene Werte, da
    diese Pruefung unmittelbar vor der eigentlichen Freigabe/Ablehnung
    erfolgen muss."""
    try:
        approval_id = int(resource_id)
    except (TypeError, ValueError):
        return _deny_generic()

    approval = get_approval_request(approval_id)
    if approval is None or approval["tenant_id"] != tenant_id:
        return _deny_generic()

    if approval["status"] != "pending":
        return _deny("ALREADY_DECIDED", "Diese Anfrage wurde bereits entschieden.")

    expires_at = approval.get("expires_at")
    if expires_at is not None and _as_aware_utc(expires_at) < datetime.now(timezone.utc):
        return _deny("EXPIRED", "Diese Anfrage ist abgelaufen.")

    # Ausnahme vom Vier-Augen-Prinzip: bei "compliance_consent" gibt die
    # Person NICHT eine fremde Geschaeftsentscheidung frei, sondern erteilt
    # eine dokumentierte, task_sha256-gebundene Einwilligung zum Versand der
    # EIGENEN Nachricht (B2 Drei-Stufen-Modell). Das ist keine Freigabe im
    # Sinn dieser Regel und daher bewusst kein "self approval".
    owner = approval.get("owner_user_id")
    if owner is not None and owner == actor.user_id:
        if approval.get("tool") == "compliance_consent":
            return _allow("OWN_CONSENT")
        return _deny("SELF_APPROVAL_BLOCKED", "Sie können Ihre eigene Anfrage nicht selbst freigeben.")

    if role >= _DECIDE_MIN_ROLE:
        return _allow("ROLE")

    if has_active_case_assignment("APPROVAL", str(approval_id), tenant_id, actor.user_id):
        return _allow("ASSIGNED")

    return _deny_generic()
