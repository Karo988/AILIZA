from __future__ import annotations

import os
from typing import Literal

from fastapi import Header, HTTPException, status

Role = Literal["operator", "admin"]

# Keys werden aus Umgebungsvariablen geladen — nie im Code
_OPERATOR_KEY = os.getenv("AILIZA_OPERATOR_KEY", "")
_ADMIN_KEY = os.getenv("AILIZA_ADMIN_KEY", "")


def _resolve_role(x_api_key: str) -> Role:
    if not x_api_key:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="API key required")
    if _ADMIN_KEY and x_api_key == _ADMIN_KEY:
        return "admin"
    if _OPERATOR_KEY and x_api_key == _OPERATOR_KEY:
        return "operator"
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid API key")


def require_operator(x_api_key: str = Header(default="")) -> Role:
    """Erlaubt operator und admin."""
    return _resolve_role(x_api_key)


def require_admin(x_api_key: str = Header(default="")) -> Role:
    """Nur admin."""
    role = _resolve_role(x_api_key)
    if role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin role required")
    return role
