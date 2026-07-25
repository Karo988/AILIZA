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

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

_SHA256_HEX_RE = re.compile(r"^[0-9a-f]{64}$")

try:
    from .auth.jwt_handler import TokenData
    from .auth.rbac import Role
    from .database import (
        decide_approval_atomic, decide_approval_lock, get_approval_request_for_tenant,
        has_active_case_assignment, write_audit_entry,
    )
except ImportError:
    from apps.backend.auth.jwt_handler import TokenData
    from apps.backend.auth.rbac import Role
    from apps.backend.database import (
        decide_approval_atomic, decide_approval_lock, get_approval_request_for_tenant,
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

# required_approver_roles (siehe approval.py: APPROVAL_ROLES) verwendet
# teils literale RBAC-Rollennamen ("admin", "manager", "user"), teils
# fachliche Freigabe-Domaenen ("privacy", "security_lead", "legal",
# "operations_lead"). Nur diese vier Domaenen werden auf eine bestehende
# Fachrolle (PR 1, user_specialist_roles) abgebildet -- alles andere
# Unbekannte traegt NICHT zur Freigabe bei (Default Deny). "owner" wird
# IMMER ignoriert: das Vier-Augen-Prinzip erlaubt keine Selbstfreigabe
# ausser der separat streng geprueften compliance_consent-Ausnahme.
_LITERAL_ROLE_NAMES = {"user", "audit_viewer", "manager", "admin", "dsb"}
_REQUIRED_ROLE_TO_SPECIALIST_DOMAIN = {
    "privacy": "DATENSCHUTZBEAUFTRAGTER",
    "security_lead": "INFORMATIONSSICHERHEITSBEAUFTRAGTER",
    "legal": "RECHTSVERANTWORTLICHER",
    "operations_lead": "BETRIEBSVERANTWORTLICHER",
}


def _resolve_required_roles(required_approver_roles: list[str] | None) -> tuple[set[str], set[str], bool]:
    """(literale RBAC-Rollennamen, Fachrollen-Domaenen, hat_unbekannten_eintrag)
    aus required_approver_roles. 'owner' wird ignoriert (Vier-Augen-Prinzip).
    Enthaelt die Liste MINDESTENS EINEN unbekannten/nicht sicher abbildbaren
    Eintrag, muss die GESAMTE Entscheidung (nicht nur dieser Eintrag) mit
    Default Deny enden -- eine unvollstaendig abgebildete Anforderung darf
    nie durch die uebrigen, bekannten Eintraege "umgangen" werden."""
    literal_roles: set[str] = set()
    specialist_domains: set[str] = set()
    has_unknown = False
    for entry in required_approver_roles or []:
        if entry == "owner":
            continue
        if entry in _LITERAL_ROLE_NAMES:
            literal_roles.add(entry)
        elif entry in _REQUIRED_ROLE_TO_SPECIALIST_DOMAIN:
            specialist_domains.add(_REQUIRED_ROLE_TO_SPECIALIST_DOMAIN[entry])
        else:
            has_unknown = True
    return literal_roles, specialist_domains, has_unknown


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
    if not isinstance(task_sha256, str) or not _SHA256_HEX_RE.match(task_sha256):
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
    """Fuehrt Autorisierung (Zuweisung + passende Rolle/Fachzustaendigkeit
    ODER geprueften Selbstkonsens) UND die Statusaenderung als EINE
    atomare Datenbankoperation aus (decide_approval_atomic). Es gibt
    KEINE separate vorgelagerte Zuweisungs-/Rollenpruefung mehr -- die
    Bedingung ist Teil desselben UPDATE-Statements, damit ein Widerruf der
    Zuweisung (oder der Fachrolle) genau zwischen einer fruehen Pruefung
    und der Aenderung die Entscheidung nicht mehr durchrutschen lassen
    kann."""
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

    # decide_approval_lock wird ueber den GESAMTEN restlichen Vorgang
    # gehalten (Lesen + atomare Aenderung), nicht nur um das UPDATE. Grund:
    # die aktuelle SQLite-:memory:-Anbindung teilt sich ueber StaticPool
    # eine einzige rohe Verbindung zwischen allen Threads: nebenlaeufige
    # Lesezugriffe (get_approval_request_for_tenant) EINES anderen
    # Threads koennen die Cursor-/Verbindungszustaende sonst waehrend des
    # kritischen Abschnitts stoeren, selbst wenn nur das abschliessende
    # UPDATE separat gesperrt waere (siehe database.decide_approval_lock).
    with decide_approval_lock:
        # Nutzerstatus (aktiv/gesperrt) ist jetzt Teil der atomaren SQL-
        # Pruefung in decide_approval_atomic (kein separater, potenziell
        # veralteter Vorab-Check mehr) -- kein Token-Rollen-Fallback.

        # Tenant-gebundener Lookup NUR um required_approver_roles und die
        # compliance_consent-Ausnahme zu bestimmen -- das Ergebnis dieses
        # Lesens wird NICHT als Autorisierung verwendet (siehe unten),
        # sondern ausschliesslich zur Herleitung statischer, waehrend der
        # Laufzeit einer Anfrage nicht mehr aenderbarer Werte (Tool-Name,
        # Owner, geforderte Rollen -- diese Felder haben nach dem Erstellen
        # keinen Aenderungspfad).
        approval = get_approval_request_for_tenant(approval_id, tenant_id)
        if approval is None:
            return ApprovalDecisionResult(False, False, "NOT_FOUND_OR_FORBIDDEN", GENERIC_DENIED_MESSAGE)

        allow_consent_owner = is_valid_own_compliance_consent(approval, actor)
        literal_roles, specialist_domains, has_unknown_required_role = _resolve_required_roles(
            approval.get("required_approver_roles"),
        )

        # Mindestens ein unbekannter/nicht sicher abbildbarer Eintrag in
        # required_approver_roles blockiert die GESAMTE Entscheidung ueber
        # den Zuweisungs-/Rollen-Pfad -- bekannte Eintraege in derselben
        # Liste duerfen das nicht "umgehen". Die separat gepruefte eigene
        # compliance_consent bleibt davon unberuehrt (sie haengt nicht von
        # required_approver_roles ab).
        if has_unknown_required_role and not allow_consent_owner:
            return ApprovalDecisionResult(False, False, "NOT_FOUND_OR_FORBIDDEN", GENERIC_DENIED_MESSAGE)
        if has_unknown_required_role:
            literal_roles, specialist_domains = set(), set()

        # EINE atomare Operation: aktueller Nutzerstatus, Zuweisung (nicht
        # widerrufen/abgelaufen), passende Fachrolle/Rolle, Vier-Augen-
        # Prinzip, Tenant, Status=pending und Ablauf werden alle im selben
        # UPDATE-Statement geprueft.
        outcome, entry = decide_approval_atomic(
            approval_id=approval_id, tenant_id=tenant_id, actor_user_id=actor.user_id,
            new_status=new_status, note=note,
            allow_consent_owner=allow_consent_owner,
            literal_roles=literal_roles, specialist_domains=specialist_domains,
        )

    if outcome == "OK":
        return ApprovalDecisionResult(True, True, "OK", "Entscheidung gespeichert.", entry)
    if outcome == "NOT_ZUSTAENDIG":
        # Dieselbe neutrale Antwort wie bei Nichtexistenz/fremdem Tenant --
        # kein Existenzleck ueber unterschiedliche Antworten.
        return ApprovalDecisionResult(False, False, "NOT_FOUND_OR_FORBIDDEN", GENERIC_DENIED_MESSAGE)
    if outcome == "ALREADY_DECIDED":
        return ApprovalDecisionResult(True, False, "ALREADY_DECIDED", "Diese Anfrage wurde bereits entschieden.", entry)
    if outcome == "EXPIRED":
        return ApprovalDecisionResult(True, False, "EXPIRED", "Diese Anfrage ist abgelaufen.", entry)
    # CONFLICT: zustaendig, aber eine parallele Anfrage war zwischen
    # Pruefung und UPDATE schneller -- kein Erfolg, kein Erfolgs-Audit.
    return ApprovalDecisionResult(True, False, "CONFLICT", "Diese Anfrage wurde soeben bereits entschieden.", entry)
