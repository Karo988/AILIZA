"""Feld-Verschlüsselung at rest (Option A) — AES-256-GCM.

Verschlüsselt einzelne DB-Felder mit personenbezogenem Inhalt (Chat-Nachrichten,
Projekt-Namen/Beschreibungen), bevor sie gespeichert werden. Der Schlüssel liegt
NUR als Secret (Umgebungsvariable), niemals im Code oder Log.

Grundsätze (DSGVO / Zertifizierung):
- AES-256-GCM: authentifizierte Verschlüsselung (Vertraulichkeit + Integrität).
- Eigener Schlüssel unter unserer Kontrolle (Art. 32 DSGVO).
- Migrationssicher: `decrypt_field` gibt Alt-Klartext (ohne Präfix) unverändert
  zurück, damit bestehende Datensätze weiter lesbar bleiben, bis sie migriert
  sind. So kann verschlüsseltes Schreiben aktiviert werden, ohne Altdaten zu
  brechen.
- Fail-closed beim Schlüssel: ohne ableitbaren Schlüssel wird eine klare
  Exception geworfen (kein stilles Klartext-Speichern).

Token-Format:  enc:v1:<base64(nonce[12] || ciphertext+tag)>
"""
from __future__ import annotations

import base64
import json
import os
from functools import lru_cache
from typing import Any

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives import hashes

_PREFIX = "enc:v1:"
_NONCE_LEN = 12  # 96 Bit, Standard für AES-GCM
_KEY_LEN = 32    # 256 Bit
_HKDF_INFO = b"AILIZA-field-encryption-v1"


class FieldCryptoError(RuntimeError):
    """Verschlüsselung/Entschlüsselung fehlgeschlagen (nie mit PII im Text)."""


@lru_cache(maxsize=1)
def _get_key() -> bytes:
    """Schlüssel aus dediziertem Secret ODER abgeleitet aus AILIZA_SECRET_KEY.

    Vorrang: AILIZA_FIELD_ENCRYPTION_KEY (base64-kodierte 32 Byte). Fehlt dieser,
    wird deterministisch aus AILIZA_SECRET_KEY via HKDF-SHA256 abgeleitet, damit
    Verschlüsselung immer aktiv ist (kein Klartext-Fallback).
    """
    explicit = os.environ.get("AILIZA_FIELD_ENCRYPTION_KEY", "").strip()
    if explicit:
        try:
            raw = base64.b64decode(explicit)
        except Exception as exc:  # noqa: BLE001 - Ursache ohne Schlüsselmaterial
            raise FieldCryptoError("AILIZA_FIELD_ENCRYPTION_KEY ist kein gültiges base64.") from exc
        if len(raw) != _KEY_LEN:
            raise FieldCryptoError("AILIZA_FIELD_ENCRYPTION_KEY muss 32 Byte (base64) sein.")
        return raw

    secret = os.environ.get("AILIZA_SECRET_KEY", "").strip()
    if not secret or len(secret) < 32:
        raise FieldCryptoError(
            "Kein Verschlüsselungs-Schlüssel: setze AILIZA_FIELD_ENCRYPTION_KEY "
            "oder ein ausreichend langes AILIZA_SECRET_KEY."
        )
    return HKDF(algorithm=hashes.SHA256(), length=_KEY_LEN,
               salt=None, info=_HKDF_INFO).derive(secret.encode("utf-8"))


def is_encrypted(value: Any) -> bool:
    return isinstance(value, str) and value.startswith(_PREFIX)


def encrypt_field(plaintext: str | None) -> str | None:
    """Verschlüsselt einen String. None/"" werden unverändert durchgereicht
    (kein Sinn, Leerwerte zu verschlüsseln; spart Platz und bleibt eindeutig)."""
    if plaintext is None or plaintext == "":
        return plaintext
    if not isinstance(plaintext, str):
        raise FieldCryptoError("encrypt_field erwartet str.")
    if is_encrypted(plaintext):
        return plaintext  # bereits verschlüsselt — nicht doppelt
    key = _get_key()
    nonce = os.urandom(_NONCE_LEN)
    ct = AESGCM(key).encrypt(nonce, plaintext.encode("utf-8"), None)
    return _PREFIX + base64.b64encode(nonce + ct).decode("ascii")


def decrypt_field(value: str | None) -> str | None:
    """Entschlüsselt einen Token. Werte OHNE Präfix gelten als Alt-Klartext und
    werden unverändert zurückgegeben (Migrationssicherheit)."""
    if value is None or value == "":
        return value
    if not isinstance(value, str) or not value.startswith(_PREFIX):
        return value  # Legacy-Klartext — unverändert
    key = _get_key()
    try:
        blob = base64.b64decode(value[len(_PREFIX):])
        nonce, ct = blob[:_NONCE_LEN], blob[_NONCE_LEN:]
        return AESGCM(key).decrypt(nonce, ct, None).decode("utf-8")
    except Exception as exc:  # noqa: BLE001 - nie Klartext/Schlüssel im Fehlertext
        raise FieldCryptoError("Entschlüsselung fehlgeschlagen (Schlüssel/Datenintegrität).") from exc


def encrypt_json(value: Any) -> str | None:
    """Serialisiert ein JSON-fähiges Objekt (z. B. Nachrichten-Liste) und
    verschlüsselt es als einen String. Bereits verschlüsselte Strings (z. B.
    beim erneuten Lauf einer idempotenten Migration) werden erkannt und NICHT
    doppelt verschlüsselt — sonst würde decrypt_json nur die äußere Schicht
    entfernen und einen weiterhin verschlüsselten String zurückgeben."""
    if value is None:
        return None
    if is_encrypted(value):
        return value
    return encrypt_field(json.dumps(value, ensure_ascii=False, separators=(",", ":")))


def decrypt_json(value: str | None) -> Any:
    """Gegenstück zu encrypt_json. Alt-Klartext (bereits Liste/Dict) und
    unverschlüsselte JSON-Strings werden tolerant behandelt."""
    if value is None or value == "":
        return value
    if not isinstance(value, str):
        return value  # bereits deserialisiert (Alt-Datensatz aus JSON-Spalte)
    dec = decrypt_field(value)
    if dec is None or dec == "":
        return dec
    try:
        return json.loads(dec)
    except (ValueError, TypeError):
        return dec  # war kein JSON — unverändert zurück
