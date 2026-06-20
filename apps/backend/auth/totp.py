"""
AILIZA TOTP-Implementierung (RFC 6238)
======================================
Nur Python-Standardbibliothek: hmac, hashlib, struct, time, base64, os, secrets.
Kompatibel mit Google Authenticator, Authy, andOTP, FreeOTP.

Sicherheitsdesign:
- Secret: 20 Bytes kryptographisch zufällig (os.urandom)
- Kodierung: Base32 (RFC 4648) — Authenticator-Standard
- Algorithmus: HMAC-SHA1 (TOTP-Pflicht nach RFC 6238 / HOTP RFC 4226)
- Zeitfenster: 30 Sekunden, ±1 Schritt Toleranz (für Uhrabweichung)
- Codes: 6-stellig
- Backup-Codes: 8 × 8 alphanumerisch, einmalig nutzbar
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets
import struct
import time


_STEP = 30          # RFC 6238 Standard: 30 Sekunden
_DIGITS = 6         # 6-stellige Codes
_WINDOW = 1         # ±1 Schritt Toleranz
_SECRET_BYTES = 20  # 160 Bit — RFC 4226 Empfehlung


def generate_secret() -> str:
    """Erzeugt ein neues Base32-kodiertes TOTP-Secret (160 Bit)."""
    raw = os.urandom(_SECRET_BYTES)
    return base64.b32encode(raw).decode().rstrip("=")


def _hotp(secret_b32: str, counter: int) -> int:
    """HOTP nach RFC 4226: HMAC-SHA1 + Dynamic Truncation."""
    padding = (8 - len(secret_b32) % 8) % 8
    key = base64.b32decode(secret_b32.upper() + "=" * padding)
    msg = struct.pack(">Q", counter)
    h = hmac.new(key, msg, hashlib.sha1).digest()
    offset = h[-1] & 0x0F
    code_int = struct.unpack(">I", h[offset:offset + 4])[0] & 0x7FFFFFFF
    return code_int % (10 ** _DIGITS)


def _current_counter(ts: float | None = None) -> int:
    return int((ts if ts is not None else time.time()) / _STEP)


def get_totp(secret_b32: str, ts: float | None = None) -> str:
    """Aktueller TOTP-Code (6-stellig, mit führenden Nullen)."""
    return f"{_hotp(secret_b32, _current_counter(ts)):0{_DIGITS}d}"


def verify_totp(secret_b32: str, code: str, ts: float | None = None) -> bool:
    """
    Prüft einen TOTP-Code im Fenster ±_WINDOW Schritte.
    Konstante Zeit um Timing-Angriffe zu vermeiden.
    """
    if not code or not code.strip().isdigit() or len(code.strip()) != _DIGITS:
        return False
    code = code.strip()
    t = _current_counter(ts)
    for offset in range(-_WINDOW, _WINDOW + 1):
        expected = f"{_hotp(secret_b32, t + offset):0{_DIGITS}d}"
        if hmac.compare_digest(expected, code):
            return True
    return False


def build_otpauth_uri(secret_b32: str, user_id: str, issuer: str = "AILIZA") -> str:
    """
    Erzeugt otpauth:// URI für QR-Code-Generierung im Frontend.
    Format: otpauth://totp/{issuer}:{user_id}?secret={secret}&issuer={issuer}&algorithm=SHA1&digits=6&period=30
    """
    from urllib.parse import quote
    label = quote(f"{issuer}:{user_id}")
    params = (
        f"secret={secret_b32}"
        f"&issuer={quote(issuer)}"
        f"&algorithm=SHA1"
        f"&digits={_DIGITS}"
        f"&period={_STEP}"
    )
    return f"otpauth://totp/{label}?{params}"


def generate_backup_codes(n: int = 8) -> list[str]:
    """
    Erzeugt n einmalig nutzbare Backup-Codes (je 8 alphanumerische Zeichen).
    Backup-Codes werden gehasht in der DB gespeichert — nie im Klartext.
    """
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # ohne O, I, 0, 1 (Lesbarkeit)
    return ["".join(secrets.choice(alphabet) for _ in range(8)) for _ in range(n)]


def hash_backup_code(code: str) -> str:
    """SHA-256-Hash eines Backup-Codes für sichere DB-Speicherung."""
    return hashlib.sha256(code.upper().strip().encode()).hexdigest()


def verify_backup_code(plain: str, stored_hash: str) -> bool:
    return hmac.compare_digest(hash_backup_code(plain), stored_hash)
