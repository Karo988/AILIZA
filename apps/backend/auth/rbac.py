"""
RBAC fuer AILIZA
=================
Rollen: user < manager < admin < dsb

Verwendung in Endpunkten:
    @app.get("/admin/...")
    def my_endpoint(token_data: TokenData = Depends(require_role(Role.ADMIN))):
        ...

Alle oeffentlichen Endpunkte (/, /health, /agent/run) brauchen keine Auth.
Admin-Endpunkte erfordern mindestens Role.ADMIN.
"""
from __future__ import annotations

from enum import IntEnum
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

try:
    from .jwt_handler import TokenData, decode_token
except ImportError:
    from auth.jwt_handler import TokenData, decode_token

_bearer = HTTPBearer(auto_error=False)


class Role(IntEnum):
    USER = 0
    MANAGER = 1
    ADMIN = 2
    DSB = 3       # Datenschutzbeauftragter — Lese-/Kontrollrechte, keine Schreibrechte

    @classmethod
    def from_str(cls, name: str) -> "Role":
        mapping = {"user": cls.USER, "manager": cls.MANAGER, "admin": cls.ADMIN, "dsb": cls.DSB}
        return mapping.get(name.lower(), cls.USER)


def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)] = None,
) -> TokenData | None:
    """
    Extrahiert den aktuellen Nutzer aus dem Bearer-Token.
    Gibt None zurueck wenn kein Token vorhanden (Endpunkte ohne Pflicht-Auth).
    """
    if credentials is None:
        return None
    try:
        return decode_token(credentials.credentials)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Ungültiges oder abgelaufenes Token.",
            headers={"WWW-Authenticate": "Bearer"},
        )


def require_role(min_role: Role):
    """
    Dependency-Factory: erzwingt mindestens `min_role`.

    Beispiel:
        Depends(require_role(Role.ADMIN))
    """
    def _check(
        credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)] = None,
    ) -> TokenData:
        if credentials is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentifizierung erforderlich.",
                headers={"WWW-Authenticate": "Bearer"},
            )
        try:
            token_data = decode_token(credentials.credentials)
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
