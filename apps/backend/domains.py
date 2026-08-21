"""Bereichsfreischaltung und Rechteverwaltung V1 -- Anwendungslogik.

Die Datenbanktabellen (business_domains, tenant_business_domains,
user_domain_memberships, domain_role_permissions) existieren seit den
Migrationen d4a1f7b93c20/e7c2b45d81a3/f9a3c61e07b2, waren bis hierhin aber
wirkungslos: ohne Bootstrapping, Standardrechte und einen Evaluator vergibt
niemand jemals eine Mitgliedschaft oder ein Recht -- die Tabellen bleiben
fail-closed leer.

Dieses Modul liefert:
  - bootstrap_domain(): Bereich fuer einen Mandanten aktivieren, erste
    domain_manager-Mitgliedschaft anlegen, Standard-Rechteprofile seeden.
  - Standard-Rechteprofile je Rolle (viewer/contributor/reviewer/
    domain_manager) -- additiv, kein Freifahrtschein: nur was hier
    ausdruecklich erlaubt wird, gilt als erlaubt.
  - Schutz des letzten domain_manager: ein Widerruf/eine Deaktivierung, die
    den letzten aktiven domain_manager eines Bereichs entfernen wuerde,
    wird abgelehnt (der Bereich duerfte sonst niemand mehr verwalten).
  - evaluate_domain_permission(): zentrale Entscheidungsfunktion fuer
    Endpunkte -- fail-closed, prueft Mandant-Aktivierung, aktive
    Mitgliedschaft und die konkrete Rechtezeile.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select

try:
    from .database import engine, write_audit_entry
    from .db_schema import (
        business_domains, tenant_business_domains,
        user_domain_memberships, domain_role_permissions,
    )
except ImportError:
    from database import engine, write_audit_entry  # type: ignore
    from db_schema import (  # type: ignore
        business_domains, tenant_business_domains,
        user_domain_memberships, domain_role_permissions,
    )

ROLES = ("viewer", "contributor", "reviewer", "domain_manager")
ACTIONS = (
    "domain.view", "content.read", "content.create", "content.update",
    "content.approve", "content.export", "action.execute", "membership.manage",
)

# Additive Standardrechte je Rolle. Jede Rolle erbt die Rechte der
# vorherigen -- ausdruecklich als Liste, nicht als Bitmaske, damit jede
# Zeile in domain_role_permissions einzeln nachvollziehbar bleibt.
DEFAULT_ROLE_ACTIONS: dict[str, tuple[str, ...]] = {
    "viewer": ("domain.view", "content.read"),
    "contributor": ("domain.view", "content.read", "content.create", "content.update"),
    "reviewer": (
        "domain.view", "content.read", "content.create", "content.update",
        "content.approve", "content.export",
    ),
    "domain_manager": (
        "domain.view", "content.read", "content.create", "content.update",
        "content.approve", "content.export", "action.execute", "membership.manage",
    ),
}


class DomainBootstrapError(RuntimeError):
    """Bootstrapping eines Bereichs ist fehlgeschlagen -- fail-closed."""


class LastDomainManagerError(RuntimeError):
    """Widerruf/Deaktivierung wuerde den letzten aktiven domain_manager
    eines Bereichs entfernen -- abgelehnt."""


@dataclass(frozen=True)
class DomainPermissionResult:
    allowed: bool
    reason_code: str
    reason_de: str


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _as_aware_utc(dt: datetime) -> datetime:
    """SQLite gibt DateTime(timezone=True)-Werte naiv zurueck (die tz-Info
    wird nicht persistiert). Ohne diese Normalisierung crasht der Vergleich
    mit einem tz-aware datetime.now(timezone.utc)."""
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


def _get_domain_id(connection, domain_code: str) -> int | None:
    row = connection.execute(
        select(business_domains.c.id).where(business_domains.c.code == domain_code)
    ).first()
    return row[0] if row else None


def bootstrap_domain(
    *,
    tenant_id: str,
    domain_code: str,
    enabled_by: str,
    reason: str,
    first_manager_user_id: str,
) -> dict[str, Any]:
    """Aktiviert einen Bereich fuer einen Mandanten, legt die erste aktive
    domain_manager-Mitgliedschaft an und seedet die Standard-Rechteprofile
    fuer alle vier Rollen. Idempotent: bereits aktivierte Bereiche werden
    nicht doppelt aktiviert, fehlende Rechtezeilen werden nachgezogen.

    Fail-closed: ohne first_manager_user_id bliebe ein aktivierter Bereich
    ohne jede handlungsfaehige Person -- das wird verweigert, nicht
    stillschweigend uebersprungen."""
    if not reason or len(reason.strip()) < 3:
        raise DomainBootstrapError("Begruendung fuer die Bereichsfreischaltung fehlt oder ist zu kurz.")
    if not first_manager_user_id:
        raise DomainBootstrapError("Ohne ersten domain_manager bliebe der Bereich unverwaltet.")

    with engine.begin() as connection:
        domain_id = _get_domain_id(connection, domain_code)
        if domain_id is None:
            raise DomainBootstrapError(f"Unbekannter Bereichscode: {domain_code!r}")

        existing = connection.execute(
            select(tenant_business_domains.c.id, tenant_business_domains.c.is_enabled)
            .where(tenant_business_domains.c.tenant_id == tenant_id)
            .where(tenant_business_domains.c.domain_id == domain_id)
        ).first()
        if existing is None:
            connection.execute(
                tenant_business_domains.insert().values(
                    tenant_id=tenant_id, domain_id=domain_id, is_enabled=1,
                    enabled_by=enabled_by, enabled_at=_now(), reason=reason, version=1,
                )
            )
        elif not existing[1]:
            connection.execute(
                tenant_business_domains.update()
                .where(tenant_business_domains.c.id == existing[0])
                .values(is_enabled=1, enabled_by=enabled_by, enabled_at=_now(),
                        disabled_by=None, disabled_at=None, reason=reason,
                        version=tenant_business_domains.c.version + 1)
            )

        # Standard-Rechteprofile seeden -- nur fehlende Kombinationen,
        # vorhandene (ggf. bewusst angepasste) Zeilen bleiben unberuehrt.
        existing_perms = {
            (row[0], row[1])
            for row in connection.execute(
                select(domain_role_permissions.c.role_in_domain, domain_role_permissions.c.action)
                .where(domain_role_permissions.c.tenant_id == tenant_id)
                .where(domain_role_permissions.c.domain_id == domain_id)
            ).all()
        }
        for role, actions in DEFAULT_ROLE_ACTIONS.items():
            for action in actions:
                if (role, action) in existing_perms:
                    continue
                connection.execute(
                    domain_role_permissions.insert().values(
                        tenant_id=tenant_id, domain_id=domain_id, role_in_domain=role,
                        action=action, allowed=1, granted_by=enabled_by, granted_at=_now(),
                        reason="Standard-Rechteprofil bei Bereichsfreischaltung", version=1,
                    )
                )

        # Erste aktive domain_manager-Mitgliedschaft, falls fuer diesen
        # Bereich/Mandanten noch keine aktive Mitgliedschaft existiert.
        has_active_manager = connection.execute(
            select(user_domain_memberships.c.id)
            .where(user_domain_memberships.c.tenant_id == tenant_id)
            .where(user_domain_memberships.c.domain_id == domain_id)
            .where(user_domain_memberships.c.role_in_domain == "domain_manager")
            .where(user_domain_memberships.c.is_active == 1)
        ).first()
        if has_active_manager is None:
            connection.execute(
                user_domain_memberships.insert().values(
                    tenant_id=tenant_id, domain_id=domain_id, user_id=first_manager_user_id,
                    role_in_domain="domain_manager", valid_from=_now(), assigned_by=enabled_by,
                    assignment_reason=reason, is_active=1, version=1,
                )
            )

    write_audit_entry(
        action="domain.bootstrap",
        tenant_id=tenant_id,
        metadata={"domain_code": domain_code, "first_manager_user_id": first_manager_user_id},
    )
    return {"domain_code": domain_code, "tenant_id": tenant_id, "status": "enabled"}


def _count_other_active_managers(connection, tenant_id: str, domain_id: int, exclude_membership_id: int) -> int:
    rows = connection.execute(
        select(user_domain_memberships.c.id)
        .where(user_domain_memberships.c.tenant_id == tenant_id)
        .where(user_domain_memberships.c.domain_id == domain_id)
        .where(user_domain_memberships.c.role_in_domain == "domain_manager")
        .where(user_domain_memberships.c.is_active == 1)
        .where(user_domain_memberships.c.id != exclude_membership_id)
    ).all()
    return len(rows)


def revoke_membership(
    *, tenant_id: str, membership_id: int, revoked_by: str, revocation_reason: str,
) -> dict[str, Any]:
    """Widerruft eine Mitgliedschaft. Lehnt ab, wenn dadurch der letzte
    aktive domain_manager eines Bereichs entfernt wuerde -- Pruefung und
    Widerruf laufen in derselben Transaktion, damit zwischen Pruefung und
    UPDATE kein zweiter gleichzeitiger Widerruf denselben Schutz umgehen
    kann."""
    if not revocation_reason or len(revocation_reason.strip()) < 3:
        raise LastDomainManagerError("Begruendung fuer den Widerruf fehlt oder ist zu kurz.")

    with engine.begin() as connection:
        row = connection.execute(
            select(
                user_domain_memberships.c.domain_id,
                user_domain_memberships.c.role_in_domain,
                user_domain_memberships.c.is_active,
            )
            .where(user_domain_memberships.c.id == membership_id)
            .where(user_domain_memberships.c.tenant_id == tenant_id)
        ).first()
        if row is None:
            raise LastDomainManagerError("Mitgliedschaft nicht gefunden.")
        domain_id, role_in_domain, is_active = row
        if not is_active:
            return {"membership_id": membership_id, "status": "already_inactive"}

        if role_in_domain == "domain_manager":
            remaining = _count_other_active_managers(connection, tenant_id, domain_id, membership_id)
            if remaining == 0:
                raise LastDomainManagerError(
                    "Der letzte aktive domain_manager dieses Bereichs kann nicht entfernt "
                    "werden -- der Bereich waere sonst unverwaltet. Bitte zuerst eine "
                    "weitere Person als domain_manager zuweisen."
                )

        connection.execute(
            user_domain_memberships.update()
            .where(user_domain_memberships.c.id == membership_id)
            .values(is_active=0, revoked_at=_now(), revoked_by=revoked_by,
                    revocation_reason=revocation_reason,
                    version=user_domain_memberships.c.version + 1)
        )

    write_audit_entry(
        action="domain.membership.revoked",
        tenant_id=tenant_id,
        metadata={"membership_id": membership_id, "role_in_domain": role_in_domain},
    )
    return {"membership_id": membership_id, "status": "revoked"}


def evaluate_domain_permission(
    *, tenant_id: str, user_id: str, domain_code: str, action: str,
) -> DomainPermissionResult:
    """Zentrale Entscheidung: darf user_id im Mandanten tenant_id die
    Aktion action im Bereich domain_code ausfuehren?

    Fail-closed in jedem Zweig: unbekannter Bereich, nicht aktivierter
    Bereich, keine aktive Mitgliedschaft oder keine passende Rechtezeile
    fuehren alle zu Deny. Es gibt keinen Pfad, der bei fehlenden Daten
    erlaubt."""
    if action not in ACTIONS:
        return DomainPermissionResult(False, "UNKNOWN_ACTION", "Unbekannte Aktion.")

    with engine.begin() as connection:
        domain_id = _get_domain_id(connection, domain_code)
        if domain_id is None:
            return DomainPermissionResult(False, "UNKNOWN_DOMAIN", "Unbekannter Bereich.")

        enabled_row = connection.execute(
            select(tenant_business_domains.c.is_enabled)
            .where(tenant_business_domains.c.tenant_id == tenant_id)
            .where(tenant_business_domains.c.domain_id == domain_id)
        ).first()
        if enabled_row is None or not enabled_row[0]:
            return DomainPermissionResult(False, "DOMAIN_NOT_ENABLED", "Bereich ist für diesen Mandanten nicht freigeschaltet.")

        now = _now()
        membership = connection.execute(
            select(user_domain_memberships.c.role_in_domain, user_domain_memberships.c.valid_until)
            .where(user_domain_memberships.c.tenant_id == tenant_id)
            .where(user_domain_memberships.c.domain_id == domain_id)
            .where(user_domain_memberships.c.user_id == user_id)
            .where(user_domain_memberships.c.is_active == 1)
        ).first()
        if membership is None:
            return DomainPermissionResult(False, "NO_MEMBERSHIP", "Keine Mitgliedschaft in diesem Bereich.")
        role_in_domain, valid_until = membership
        if valid_until is not None and _as_aware_utc(valid_until) <= now:
            return DomainPermissionResult(False, "MEMBERSHIP_EXPIRED", "Mitgliedschaft ist abgelaufen.")

        perm_row = connection.execute(
            select(domain_role_permissions.c.allowed)
            .where(domain_role_permissions.c.tenant_id == tenant_id)
            .where(domain_role_permissions.c.domain_id == domain_id)
            .where(domain_role_permissions.c.role_in_domain == role_in_domain)
            .where(domain_role_permissions.c.action == action)
        ).first()
        if perm_row is None or not perm_row[0]:
            return DomainPermissionResult(False, "ACTION_NOT_PERMITTED", "Für diese Rolle nicht freigegeben.")

    return DomainPermissionResult(True, "OK", "Zugriff erlaubt.")


def list_my_domain_memberships(*, tenant_id: str, user_id: str) -> list[dict[str, Any]]:
    """Fuer Nutzer-Selbstauskunft/UI: nur eigene aktive Mitgliedschaften."""
    query = (
        select(
            business_domains.c.code, business_domains.c.name,
            user_domain_memberships.c.role_in_domain, user_domain_memberships.c.valid_until,
        )
        .select_from(
            user_domain_memberships.join(
                business_domains, business_domains.c.id == user_domain_memberships.c.domain_id
            )
        )
        .where(user_domain_memberships.c.tenant_id == tenant_id)
        .where(user_domain_memberships.c.user_id == user_id)
        .where(user_domain_memberships.c.is_active == 1)
    )
    with engine.begin() as connection:
        rows = connection.execute(query).mappings().all()
    return [dict(row) for row in rows]


class DomainMembershipError(RuntimeError):
    """Mitgliedschaft konnte nicht vergeben werden -- fail-closed."""


def assign_membership(
    *,
    tenant_id: str,
    domain_code: str,
    user_id: str,
    role_in_domain: str,
    assigned_by: str,
    assignment_reason: str,
    valid_until: datetime | None = None,
) -> dict[str, Any]:
    """Weist einer Person eine Rolle in einem Bereich zu.

    Ohne diese Funktion war das Rechtemodell nicht bedienbar:
    bootstrap_domain() legt nur den ERSTEN domain_manager an, und
    revoke_membership() verweigert den Widerruf des letzten -- eine zweite
    Person konnte also nie hinzukommen.

    Fail-closed in jedem Zweig: unbekannter Bereich, im Mandanten nicht
    freigeschalteter Bereich, unbekannte Rolle oder fehlende Begruendung
    fuehren zur Ablehnung. Es wird nichts stillschweigend angelegt."""
    if role_in_domain not in ROLES:
        raise DomainMembershipError(f"Unbekannte Bereichsrolle: {role_in_domain!r}")
    if not assignment_reason or len(assignment_reason.strip()) < 3:
        raise DomainMembershipError("Begruendung fuer die Zuweisung fehlt oder ist zu kurz.")
    if not user_id or not user_id.strip():
        raise DomainMembershipError("Ohne Nutzerkennung kann keine Mitgliedschaft angelegt werden.")

    now = _now()
    if valid_until is not None and _as_aware_utc(valid_until) <= now:
        raise DomainMembershipError("Das Ablaufdatum liegt bereits in der Vergangenheit.")

    with engine.begin() as connection:
        domain_id = _get_domain_id(connection, domain_code)
        if domain_id is None:
            raise DomainMembershipError(f"Unbekannter Bereichscode: {domain_code!r}")

        # Ein im Mandanten nicht freigeschalteter Bereich darf keine
        # Mitgliedschaften bekommen -- sonst entstuenden Rechte auf Vorrat,
        # die bei einer spaeteren Freischaltung sofort wirksam waeren.
        enabled = connection.execute(
            select(tenant_business_domains.c.is_enabled)
            .where(tenant_business_domains.c.tenant_id == tenant_id)
            .where(tenant_business_domains.c.domain_id == domain_id)
        ).first()
        if enabled is None or not enabled[0]:
            raise DomainMembershipError(
                f"Bereich {domain_code!r} ist für diesen Mandanten nicht freigeschaltet."
            )

        already = connection.execute(
            select(user_domain_memberships.c.id, user_domain_memberships.c.role_in_domain)
            .where(user_domain_memberships.c.tenant_id == tenant_id)
            .where(user_domain_memberships.c.domain_id == domain_id)
            .where(user_domain_memberships.c.user_id == user_id)
            .where(user_domain_memberships.c.is_active == 1)
        ).first()
        if already is not None:
            raise DomainMembershipError(
                f"{user_id} ist in diesem Bereich bereits als {already[1]} aktiv. "
                "Bitte zuerst widerrufen, dann neu zuweisen -- so bleibt der "
                "Rollenwechsel im Nachweis sichtbar."
            )

        connection.execute(
            user_domain_memberships.insert().values(
                tenant_id=tenant_id, domain_id=domain_id, user_id=user_id,
                role_in_domain=role_in_domain, valid_from=now, valid_until=valid_until,
                assigned_by=assigned_by, assignment_reason=assignment_reason,
                is_active=1, version=1,
            )
        )

    write_audit_entry(
        action="domain.membership.assigned",
        tenant_id=tenant_id,
        metadata={"domain_code": domain_code, "role_in_domain": role_in_domain},
    )
    return {"domain_code": domain_code, "user_id": user_id,
            "role_in_domain": role_in_domain, "status": "assigned"}


def list_domains_for_tenant(*, tenant_id: str) -> list[dict[str, Any]]:
    """Alle bekannten Bereiche mit ihrem Freischaltstatus im Mandanten.

    Ein Bereich ohne Zeile in tenant_business_domains gilt als NICHT
    freigeschaltet -- deshalb Outer Join statt Inner Join: sonst waeren
    genau die nicht freigeschalteten Bereiche unsichtbar, also jene, die
    man in der Oberflaeche freischalten koennte."""
    query = (
        select(
            business_domains.c.code, business_domains.c.name,
            business_domains.c.category, business_domains.c.sensitivity_level,
            tenant_business_domains.c.is_enabled,
        )
        .select_from(
            business_domains.outerjoin(
                tenant_business_domains,
                (tenant_business_domains.c.domain_id == business_domains.c.id)
                & (tenant_business_domains.c.tenant_id == tenant_id),
            )
        )
        .order_by(business_domains.c.code)
    )
    with engine.begin() as connection:
        rows = connection.execute(query).mappings().all()
    return [
        {**dict(row), "is_enabled": bool(row["is_enabled"])}
        for row in rows
    ]


def list_domain_members(*, tenant_id: str, domain_code: str) -> list[dict[str, Any]]:
    """Aktive Mitgliedschaften eines Bereichs -- strikt tenant-gefiltert."""
    query = (
        select(
            user_domain_memberships.c.id, user_domain_memberships.c.user_id,
            user_domain_memberships.c.role_in_domain,
            user_domain_memberships.c.valid_until,
            user_domain_memberships.c.assigned_by,
        )
        .select_from(
            user_domain_memberships.join(
                business_domains, business_domains.c.id == user_domain_memberships.c.domain_id
            )
        )
        .where(user_domain_memberships.c.tenant_id == tenant_id)
        .where(business_domains.c.code == domain_code)
        .where(user_domain_memberships.c.is_active == 1)
        .order_by(user_domain_memberships.c.user_id)
    )
    with engine.begin() as connection:
        rows = connection.execute(query).mappings().all()
    return [dict(row) for row in rows]
