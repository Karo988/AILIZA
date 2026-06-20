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
- Backup-Codes: 8 × 8 alphanumerisch, HMAC-SHA256 mit serverseitigem Pepper, einmalig nutzbar

TOTP-Secret at rest — Beta-Status und Production-Gate:
  TOTP-Secrets werden NICHT mit selbstgebauter Kryptografie verschlüsselt.
  Eigenimplementierungen (XOR+HMAC o.ä.) sind kein Ersatz für AES-GCM und sind VERBOTEN.

  Für Beta gilt:
    - TOTP-Secrets werden im zugriffsbeschränkten DB-Feld gespeichert.
    - Betriebliche Auflage: DB-/Volume-Verschlüsselung (z.B. SQLCipher, dm-crypt,
      verschlüsselte Cloud-Volumes), minimale DB-Rechte, Audit-Logging.

  Production-Gate (muss vor Produktiv-Einsatz erfüllt sein):
    - Secret-at-rest-Schutz via `cryptography` (AES-256-GCM / Fernet) oder
      KMS/Vault (z.B. HashiCorp Vault, AWS KMS, Azure Key Vault).
    - Keine selbstgebaute Kryptografie (XOR, eigener Keystream o.ä.) als Ersatz.
    - Implementierung in upsert_totp_secret() / get_totp_record() in database.py ergänzen.
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


def _pepper() -> bytes:
    """Pepper aus AILIZA_SECRET_KEY für HMAC-Operationen (Backup-Codes)."""
    key = os.getenv("AILIZA_SECRET_KEY", "")
    if len(key) < 32:
        raise ValueError("AILIZA_SECRET_KEY muss mindestens 32 Zeichen haben.")
    return key.encode()


# ── HOTP / TOTP ───────────────────────────────────────────────────────────────
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
    WICHTIG: URI enthält das Klartext-Secret → nur einmalig beim Setup anzeigen,
    nie in Logs schreiben, nicht cachen.
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


# ── Backup-Codes ──────────────────────────────────────────────────────────────
def generate_backup_codes(n: int = 8) -> list[str]:
    """
    Erzeugt n einmalig nutzbare Backup-Codes (je 8 alphanumerische Zeichen).
    Backup-Codes werden HMAC-SHA256+Pepper gehasht in der DB gespeichert.
    """
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # ohne O, I, 0, 1 (Lesbarkeit)
    return ["".join(secrets.choice(alphabet) for _ in range(8)) for _ in range(n)]


def hash_backup_code(code: str) -> str:
    """
    HMAC-SHA256 eines Backup-Codes mit serverseitigem Pepper.
    Schützt bei DB-Leak vor Offline-Brute-Force (8-stellige Codes: ~10^12 Kombinationen
    mit Pepper statt ~10^9 ohne).
    """
    return hmac.new(_pepper(), code.upper().strip().encode(), hashlib.sha256).hexdigest()


def verify_backup_code(plain: str, stored_hash: str) -> bool:
    return hmac.compare_digest(hash_backup_code(plain), stored_hash)

