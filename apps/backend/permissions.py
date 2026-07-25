"""PR 2: Zentraler Permission-Evaluator.

Default Deny: eine Aktion ist grundsaetzlich verboten und wird nur erlaubt,
wenn eine konkrete Regel sie ausdruecklich freigibt.

Nachbesserung (Betreiber-Review): KEINE pauschale Freigabe fuer
Manager/Admin/DSB mehr. Bis zur vollstaendigen Fachzustaendigkeits- und
Risikodomaenen-Matrix (spaeterer PR) darf eine Genehmigung NUR entschieden
werden durch:

  1. eine aktive, nicht widerrufene und nicht abgelaufene case_assignment,
  2. oder eine streng gepruefte eigene compliance_consent (B2-Einwilligung
     zum Versand der eigenen, vorher geflaggten Nachricht -- keine Freigabe
     einer fremden Entscheidung).

Eine organisatorische Rolle allein (auch Admin/DSB) gewaehrt keinen
Freigabezugriff auf fremde oder ownerlose historische Anfragen.

Unbekannte Rollenwerte fallen NICHT wie bei Role.from_str() auf USER zurueck
-- hier gilt Default Deny plus ein internes Diagnose-Audit-Ereignis, das
IMMER unter actor.tenant_id protokolliert wird (nie unter dem Tenant eines
fremden gefundenen Datensatzes).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

try:
    from .auth.jwt_handler import TokenData
    from .auth.rbac import Role
    from .database import (
        decide_approval_atomic, get_approval_request_for_tenant, get_user,
        has_active_case_assignment, write_audit_entry,
    )
except ImportError:
    from apps.backend.auth.jwt_handler import TokenData
    from apps.backend.auth.rbac import Role
    from apps.backend.database import (
        decide_approval_atomic, get_approval_request_for_tenant, get_user,
        has_active_case_assignment, write_audit_entry,
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


@dataclass(frozen=True)
class ApprovalDecisionResult:
    """Ergebnis einer atomaren Genehmigungsentscheidung."""
    allowed: bool
    committed: bool
    reason_code: str
    reason_de: str
    entry: dict[str, Any] | None = None


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


def _is_locked(db_user: dict[str, Any]) -> bool:
    locked_until = db_user.get("locked_until")
    if locked_until is None:
        return False
    return _as_aware_utc(locked_until) > datetime.now(timezone.utc)


def is_valid_own_compliance_consent(approval: dict[str, Any], actor: TokenData) -> bool:
    """Harte Pruefung der B2-Selbstkonsens-Ausnahme -- ein manipulierter
    oder unvollstaendiger Datensatz mit demselben Tool-Namen darf NIEMALS
    eine Selbstfreigabe ermoeglichen. Prueft Owner, Tenant, erwartete
    Datenstruktur und eine vorhandene Task-Hash-Bindung."""
    if approval.get("tool") != "compliance_consent":
        return False
    if approval.get("owner_user_id") != actor.user_id:
        return False
    if approval.get("tenant_id") != actor.tenant_id:
        return False
    params = approval.get("input_params") or {}
    task_sha256 = params.get("task_sha256")
    if not isinstance(task_sha256, str) or len(task_sha256) != 64:
        return False
    return True


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

    # 2. Tenant muss uebereinstimmen -- VOR jedem Audit-Eintrag, damit ein
    # Aufruf mit einer fremden Tenant-/Ressourcen-Kombination niemals einen
    # Audit-Eintrag unter einem fremden Tenant erzeugen kann.
    if actor.tenant_id != tenant_id:
        return _deny_generic()

    # Bekannte Rolle? Unbekannt -> Default Deny + Diagnose-Audit, IMMER
    # unter actor.tenant_id (== tenant_id, siehe obiger Abgleich).
    role = _resolve_role_strict(actor.role)
    if role is None:
        write_audit_entry(
            action="permission.unknown_role_denied",
            tenant_id=actor.tenant_id,
            metadata={"action": action, "resource_type": resource_type},
        )
        return _deny("UNKNOWN_ROLE", "Ihre Berechtigung konnte nicht ermittelt werden.")

    if action in (AGENT_RUN_READ, APPROVAL_READ):
        if resource_owner_user_id is not None and resource_owner_user_id == actor.user_id:
            return _allow("OWNER")
        case_type = "AGENT_RUN" if action == AGENT_RUN_READ else "APPROVAL"
        if has_active_case_assignment(case_type, resource_id, tenant_id, actor.user_id):
            return _allow("ASSIGNED")
        return _deny_generic()

    if action in (AGENT_RUN_LIST, APPROVAL_LIST, AGENT_RUN_CREATE, CASE_ASSIGNMENT_READ):
        # Grobe Freigabe der Aktionsklasse -- die eigentliche Owner-/Zuweisungs-
        # Filterung erfolgt direkt in der Datenbankabfrage (list_own_or_assigned_*),
        # nicht durch Laden aller Datensaetze und anschliessendes Verwerfen.
        return _allow("OK")

    return _deny("UNKNOWN_ACTION", "Unbekannte Aktion.")


def decide_approval(
    *, actor: TokenData, tenant_id: str, approval_id: int, new_status: str, note: str = "",
) -> ApprovalDecisionResult:
    """Fuehrt Autorisierung, Statuspruefung und Aenderung als eine
    zusammenhaengende, atomare Entscheidungsoperation aus.

    Reihenfolge ist sicherheitsrelevant: ZUSTAENDIGKEIT wird IMMER zuerst
    geprueft, bevor irgendetwas ueber Status oder Ablauf preisgegeben wird.
    Eine nicht zustaendige Person erhaelt in JEDEM Fall (egal ob die Anfrage
    nicht existiert, einem fremden Tenant gehoert, bereits entschieden oder
    abgelaufen ist) exakt dieselbe neutrale Antwort -- kein Existenzleck."""
    if actor is None:
        return ApprovalDecisionResult(False, False, "NO_SESSION", "Bitte melden Sie sich an.")

    role = _resolve_role_strict(actor.role)
    if role is None:
        write_audit_entry(
            action="permission.unknown_role_denied",
            tenant_id=actor.tenant_id,
            metadata={"action": APPROVAL_DECIDE, "resource_type": "approval"},
        )
        return ApprovalDecisionResult(False, False, "UNKNOWN_ROLE", "Ihre Berechtigung konnte nicht ermittelt werden.")

    # Aktuellen Nutzerstatus serverseitig aus der DB lesen, SOWEIT ein
    # Datensatz existiert -- ein zwischenzeitlich gesperrter/deaktivierter
    # Nutzer darf mit einem noch gueltigen alten Token keine Entscheidung
    # ausfuehren. Existiert (noch) kein users-Datensatz, wird das aktuelle,
    # rein tokenbasierte Architekturmodell beibehalten (kein neues Login-
    # Pflichtfeld in PR 2); die vollstaendige tenant_memberships-basierte
    # Session-Invalidierung folgt in PR 3.
    db_user = get_user(actor.user_id, tenant_id=actor.tenant_id)
    if db_user is not None and (not db_user.get("active") or _is_locked(db_user)):
        return ApprovalDecisionResult(False, False, "NOT_FOUND_OR_FORBIDDEN", GENERIC_DENIED_MESSAGE)

    # Tenant-gebundener Lookup: eine Anfrage eines fremden Tenants existiert
    # aus Sicht dieser Abfrage schlicht nicht.
    approval = get_approval_request_for_tenant(approval_id, tenant_id)
    if approval is None:
        return ApprovalDecisionResult(False, False, "NOT_FOUND_OR_FORBIDDEN", GENERIC_DENIED_MESSAGE)

    # ZUSTAENDIGKEIT ZUERST -- unabhaengig von Status/Ablauf. Kein pauschales
    # role >= MANAGER mehr. Nur aktive Zuweisung oder gepruefte eigene
    # compliance_consent begruenden ueberhaupt eine Zustaendigkeit.
    zustaendig = has_active_case_assignment(
        "APPROVAL", str(approval_id), tenant_id, actor.user_id,
    ) or is_valid_own_compliance_consent(approval, actor)

    if not zustaendig:
        # Absichtlich dieselbe neutrale Antwort wie bei Nichtexistenz --
        # sonst koennte eine nicht zustaendige Person ueber den HTTP-Status
        # erraten, ob eine Anfrage existiert/entschieden/abgelaufen ist.
        return ApprovalDecisionResult(False, False, "NOT_FOUND_OR_FORBIDDEN", GENERIC_DENIED_MESSAGE)

    # Erst NACH festgestellter Zustaendigkeit duerfen ALREADY_DECIDED/EXPIRED
    # ueberhaupt unterschieden werden.
    if approval["status"] != "pending":
        return ApprovalDecisionResult(True, False, "ALREADY_DECIDED", "Diese Anfrage wurde bereits entschieden.", approval)

    expires_at = approval.get("expires_at")
    if expires_at is not None and _as_aware_utc(expires_at) < datetime.now(timezone.utc):
        return ApprovalDecisionResult(True, False, "EXPIRED", "Diese Anfrage ist abgelaufen.", approval)

    # Atomare Aenderung: Autorisierung/Statuspruefung oben, die eigentliche
    # UPDATE-Bedingung (Tenant + weiterhin 'pending') wird in derselben
    # Transaktion erneut durchgesetzt, um ein Race zwischen zwei
    # gleichzeitigen Entscheidungen auszuschliessen.
    rowcount, entry = decide_approval_atomic(approval_id, tenant_id, new_status, note)
    if rowcount != 1:
        # Eine parallele Anfrage war schneller -- kein Erfolg, kein
        # Erfolgs-Audit, kontrollierter Konflikt statt stillem "OK".
        return ApprovalDecisionResult(True, False, "CONFLICT", "Diese Anfrage wurde soeben bereits entschieden.", entry)

    return ApprovalDecisionResult(True, True, "OK", "Entscheidung gespeichert.", entry)
