"""
RBAC fuer AILIZA
=================
Rollen: user < manager < admin < dsb

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
    MANAGER = 1
    ADMIN = 2
    DSB = 3       # Datenschutzbeauftragter — Lese-/Kontrollrechte, keine Schreibrechte

    @classmethod
    def from_str(cls, name: str) -> "Role":
        mapping = {"user": cls.USER, "manager": cls.MANAGER, "admin": cls.ADMIN, "dsb": cls.DSB}
        return mapping.get(name.lower(), cls.USER)


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
    Dependency-Factory: erzwingt mindestens `min_role`.
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
        if Role.from_str(token_data.role) < min_role:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Mindestrolle '{min_role.name.lower()}' erforderlich.",
            )
        return token_data
    return _check
