"""
Sicherheits-Regressionstest: ein TOTP-Pending-Token (kurzlebig, ausgestellt
nach Passwort-Check aber VOR TOTP-Verifikation) darf niemals als vollwertiges
Session-Token akzeptiert werden.

Vorher: decode_token() pruefte nur Signatur + exp, nicht das Claim
"totp_pending". get_current_user()/require_role() riefen ausschliesslich
decode_token() auf -- ein TOTP-Pending-Token waere daher als gueltige Session
akzeptiert worden.

Fix: decode_token() lehnt Tokens mit totp_pending=true grundsaetzlich ab.
Nur decode_totp_pending_token() (verwendet ausschliesslich vom
/auth/totp/verify-Endpunkt) darf sie ueber ein internes Flag passieren
lassen.
"""
from __future__ import annotations

import os

os.environ.setdefault("AILIZA_SECRET_KEY", "test-secret-key-minimum-32-chars-ok")
os.environ.setdefault("AILIZA_DATABASE_URL", "sqlite:///:memory:")

import pytest


def test_decode_token_rejects_totp_pending_token():
    from apps.backend.auth.jwt_handler import create_totp_pending_token, decode_token

    pending = create_totp_pending_token("admin1", "default", "admin")
    with pytest.raises(ValueError):
        decode_token(pending)


def test_decode_totp_pending_token_still_accepts_it():
    from apps.backend.auth.jwt_handler import create_totp_pending_token, decode_totp_pending_token

    pending = create_totp_pending_token("admin1", "default", "admin")
    token_data = decode_totp_pending_token(pending)
    assert token_data.user_id == "admin1"
    assert token_data.role == "admin"


def test_decode_token_still_accepts_regular_token():
    from apps.backend.auth.jwt_handler import create_token, decode_token

    token = create_token("user1", "default", "user")
    token_data = decode_token(token)
    assert token_data.user_id == "user1"


def test_totp_pending_token_rejected_by_get_current_user():
    from apps.backend.auth.jwt_handler import create_totp_pending_token
    from apps.backend.auth.rbac import get_current_user
    from fastapi import HTTPException

    pending = create_totp_pending_token("admin1", "default", "admin")

    class _Creds:
        credentials = pending

    with pytest.raises(HTTPException) as exc_info:
        get_current_user(credentials=_Creds(), ailiza_session=None)
    assert exc_info.value.status_code == 401


def test_totp_pending_token_rejected_by_require_role():
    from apps.backend.auth.jwt_handler import create_totp_pending_token
    from apps.backend.auth.rbac import require_role, Role
    from fastapi import HTTPException

    pending = create_totp_pending_token("admin1", "default", "admin")
    check = require_role(Role.ADMIN)

    class _Creds:
        credentials = pending

    with pytest.raises(HTTPException) as exc_info:
        check(credentials=_Creds(), ailiza_session=None)
    assert exc_info.value.status_code == 401


def test_totp_pending_token_rejected_via_real_endpoint():
    """End-to-end: ein TOTP-Pending-Token darf keinen geschuetzten Endpunkt
    (z.B. /admin/*) als gueltige Session passieren."""
    from fastapi.testclient import TestClient
    from apps.backend.main import app
    from apps.backend.auth.jwt_handler import create_totp_pending_token

    pending = create_totp_pending_token("admin1", "default", "admin")
    client = TestClient(app, cookies={})
    resp = client.get("/auth/me", headers={"Authorization": f"Bearer {pending}"})
    assert resp.status_code == 401
