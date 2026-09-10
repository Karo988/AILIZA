"""
RBAC fuer AILIZA
=================
Rollen: user, audit_viewer, manager, admin, dsb

audit_viewer: darf Audit-Vault lesen, aber keine Admin-Aktionen ausfuehren.
              Gedacht fuer externe Prueferinnen und Datenschutzbeauftragte ohne
              vollstaendige Admin-Rechte.

DSB: reine Kontroll-/Leserolle. DSB erbt weder USER-, MANAGER- noch
     ADMIN-Schreibrechte. Notfall-Schreibrechte erfordern ein separates
     Break-Glass-Mandat; ein solches Mandat ist hier nicht implementiert.

Die Zahlenwerte von Role bleiben aus Kompatibilitaetsgruenden stabil, bilden
aber KEINE lineare Berechtigungshierarchie. Die erlaubten Beziehungen stehen
explizit in _ROLE_GRANTS.

Token-Extraktion: Bearer-Header ODER HttpOnly-Cookie "ailiza_session".
Cookie-Flow ist bevorzugt (sicherer gegen XSS als localStorage).
Bearer-Header bleibt fuer API-Clients und Tests erhalten.
"""
from __future__ import annotations

from enum import IntEnum
from typing import Annotated

from fastapi import Cookie, Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

try:
    from .jwt_handler import TokenData, decode_token
except ImportError:
    from auth.jwt_handler import TokenData, decode_token

_bearer = HTTPBearer(auto_error=False)

_COOKIE_NAME = "ailiza_session"


class Role(IntEnum):
    USER = 0
    AUDIT_VIEWER = 1  # Nur Audit-Lesen, kein normaler USER-/Admin-Zugriff
    MANAGER = 2
    ADMIN = 3
    DSB = 4           # Datenschutzbeauftragter — Lese-/Kontrollrechte, keine Schreibrechte

    @classmethod
    def try_from_str(cls, name: str) -> "Role | None":
        """Liefert nur fuer einen bekannten Rollenwert eine Rolle."""
        mapping = {
            "user": cls.USER,
            "audit_viewer": cls.AUDIT_VIEWER,
            "manager": cls.MANAGER,
            "admin": cls.ADMIN,
            "dsb": cls.DSB,
        }
        return mapping.get(str(name).strip().lower())

    @classmethod
    def from_str(cls, name: str) -> "Role":
        """Parst bekannte Rollen und verwirft unbekannte Werte fail-closed."""
        parsed = cls.try_from_str(name)
        if parsed is None:
            raise ValueError(f"Unbekannte Rolle: {name!r}")
        return parsed


# Explizite Rollenbeziehungen statt eines sicherheitskritischen IntEnum-
# Groesser-gleich-Vergleichs. MANAGER/ADMIN behalten die bisherige fachliche
# Vererbung. AUDIT_VIEWER und DSB bleiben getrennte reine Kontrollrollen.
_ROLE_GRANTS: dict[Role, frozenset[Role]] = {
    Role.USER: frozenset({Role.USER}),
    Role.AUDIT_VIEWER: frozenset({Role.AUDIT_VIEWER}),
    Role.MANAGER: frozenset({Role.USER, Role.AUDIT_VIEWER, Role.MANAGER}),
    Role.ADMIN: frozenset({Role.USER, Role.AUDIT_VIEWER, Role.MANAGER, Role.ADMIN}),
    Role.DSB: frozenset({Role.AUDIT_VIEWER, Role.DSB}),
}


def role_allows(actual_role: Role, required_role: Role) -> bool:
    """Prueft die explizite Rollenmatrix; keine numerische Vererbung."""
    return required_role in _ROLE_GRANTS.get(actual_role, frozenset())


def _extract_token(
    credentials: HTTPAuthorizationCredentials | None,
    cookie: str | None,
) -> str | None:
    """Bearer-Header hat Vorrang (API-Clients), Cookie als Fallback (Browser-Flow)."""
    if credentials is not None:
        return credentials.credentials
    return cookie


def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)] = None,
    ailiza_session: Annotated[str | None, Cookie()] = None,
) -> TokenData | None:
    """
    Extrahiert den aktuellen Nutzer aus Bearer-Token ODER HttpOnly-Cookie.
    Gibt None zurueck wenn kein Token vorhanden (Endpunkte ohne Pflicht-Auth).
    """
    raw = _extract_token(credentials, ailiza_session)
    if raw is None:
        return None
    try:
        return decode_token(raw)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Ungültiges oder abgelaufenes Token.",
            headers={"WWW-Authenticate": "Bearer"},
        )


def require_role(min_role: Role):
    """
    Dependency-Factory: erzwingt die explizite Berechtigung fuer `min_role`.
    Akzeptiert Bearer-Header oder HttpOnly-Cookie.
    """
    def _check(
        credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)] = None,
        ailiza_session: Annotated[str | None, Cookie()] = None,
    ) -> TokenData:
        raw = _extract_token(credentials, ailiza_session)
        if raw is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentifizierung erforderlich.",
                headers={"WWW-Authenticate": "Bearer"},
            )
        try:
            token_data = decode_token(raw)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Ungültiges oder abgelaufenes Token.",
                headers={"WWW-Authenticate": "Bearer"},
            )
        actual_role = Role.try_from_str(token_data.role)
        if actual_role is None or not role_allows(actual_role, min_role):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Rollenberechtigung '{min_role.name.lower()}' erforderlich.",
            )
        return token_data
    return _check
