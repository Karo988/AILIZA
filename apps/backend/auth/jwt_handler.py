"""
JWT-Handler fuer AILIZA
========================
HS256 via Python-Standardbibliothek (hmac + hashlib).
Kein Secret in Code. Key kommt aus AILIZA_SECRET_KEY (Env).
Mindestlaenge: 32 Zeichen.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

_SECRET = os.getenv("AILIZA_SECRET_KEY", "")
_ALGORITHM = "HS256"
_EXPIRY_MINUTES = int(os.getenv("AILIZA_JWT_EXPIRY_MINUTES", "60"))

if len(_SECRET) < 32:
    import warnings
    warnings.warn(
        "AILIZA_SECRET_KEY ist nicht gesetzt oder zu kurz (< 32 Zeichen). "
        "JWT-Auth ist deaktiviert bis ein gueltiges Secret gesetzt wird.",
        stacklevel=1,
    )


@dataclass
class TokenData:
    user_id: str
    tenant_id: str
    role: str
    exp: datetime | None = None


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _b64url_decode(s: str) -> bytes:
    pad = 4 - len(s) % 4
    return base64.urlsafe_b64decode(s + "=" * (pad % 4))


def create_token(user_id: str, tenant_id: str, role: str) -> str:
    """Erzeugt ein signiertes JWT (HS256)."""
    secret = os.getenv("AILIZA_SECRET_KEY", _SECRET)
    if len(secret) < 32:
        raise ValueError("AILIZA_SECRET_KEY muss mindestens 32 Zeichen haben.")
    expires = datetime.now(timezone.utc) + timedelta(minutes=_EXPIRY_MINUTES)
    header = _b64url_encode(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    payload = _b64url_encode(json.dumps({
        "sub": user_id,
        "tenant_id": tenant_id,
        "role": role,
        "exp": int(expires.timestamp()),
    }).encode())
    signing_input = f"{header}.{payload}"
    sig = hmac.new(secret.encode(), signing_input.encode(), hashlib.sha256).digest()
    return f"{signing_input}.{_b64url_encode(sig)}"


def decode_token(token: str) -> TokenData:
    """
    Dekodiert und validiert ein JWT.
    Wirft ValueError bei ungueltigem oder abgelaufenen Token.
    """
    secret = os.getenv("AILIZA_SECRET_KEY", _SECRET)
    if len(secret) < 32:
        raise ValueError("AILIZA_SECRET_KEY nicht konfiguriert.")
    parts = token.split(".")
    if len(parts) != 3:
        raise ValueError("Ungültiges Token-Format.")
    header_b64, payload_b64, sig_b64 = parts
    signing_input = f"{header_b64}.{payload_b64}"
    expected_sig = hmac.new(secret.encode(), signing_input.encode(), hashlib.sha256).digest()
    try:
        actual_sig = _b64url_decode(sig_b64)
    except Exception as exc:
        raise ValueError(f"Ungültiges Token: {exc}") from exc
    if not hmac.compare_digest(expected_sig, actual_sig):
        raise ValueError("Token-Signatur ungültig.")
    try:
        payload = json.loads(_b64url_decode(payload_b64))
    except Exception as exc:
        raise ValueError(f"Token-Payload ungültig: {exc}") from exc
    exp_ts = payload.get("exp")
    if exp_ts is None or datetime.fromtimestamp(exp_ts, tz=timezone.utc) < datetime.now(timezone.utc):
        raise ValueError("Token abgelaufen.")
    return TokenData(
        user_id=str(payload["sub"]),
        tenant_id=str(payload.get("tenant_id", "default")),
        role=str(payload.get("role", "user")),
        exp=datetime.fromtimestamp(exp_ts, tz=timezone.utc),
    )
