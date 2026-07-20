"""Tests fuer die Feld-Verschlüsselung at rest (Option A, AES-256-GCM).

Prueft Happy-Path UND Fehlerbehandlung: Round-trip, Migrationssicherheit
(Alt-Klartext bleibt lesbar), Nonce-Zufaelligkeit, Manipulationserkennung
(GCM-Auth), leere/None-Werte, JSON-Felder, Fail-closed ohne Schluessel.
Kein Test schreibt echte PII in Logs.
"""
import base64
import importlib
import os

import pytest

os.environ.setdefault("AILIZA_SECRET_KEY", "test-secret-key-minimum-32-chars-ok")

from apps.backend.governance import field_crypto as fc


def test_roundtrip_basic():
    token = fc.encrypt_field("Max Mustermann, IBAN DE89...")
    assert token.startswith("enc:v1:")
    assert fc.decrypt_field(token) == "Max Mustermann, IBAN DE89..."


def test_ciphertext_hides_plaintext():
    token = fc.encrypt_field("streng geheim")
    assert "geheim" not in token


def test_none_and_empty_passthrough():
    assert fc.encrypt_field(None) is None
    assert fc.encrypt_field("") == ""
    assert fc.decrypt_field(None) is None
    assert fc.decrypt_field("") == ""


def test_legacy_plaintext_is_returned_unchanged():
    # Alt-Datensatz ohne Praefix -> Migrationssicherheit
    assert fc.decrypt_field("alter Klartext ohne Praefix") == "alter Klartext ohne Praefix"


def test_nonce_is_random_per_call():
    a = fc.encrypt_field("gleicher Text")
    b = fc.encrypt_field("gleicher Text")
    assert a != b                       # unterschiedliche Nonce
    assert fc.decrypt_field(a) == fc.decrypt_field(b) == "gleicher Text"


def test_double_encrypt_is_noop():
    once = fc.encrypt_field("x")
    twice = fc.encrypt_field(once)
    assert once == twice


def test_tamper_detection_raises():
    token = fc.encrypt_field("wichtig")
    blob = bytearray(base64.b64decode(token[len("enc:v1:"):]))
    blob[-1] ^= 0x01                    # letztes Byte (Auth-Tag) kippen
    tampered = "enc:v1:" + base64.b64encode(bytes(blob)).decode()
    with pytest.raises(fc.FieldCryptoError):
        fc.decrypt_field(tampered)


def test_json_roundtrip():
    msgs = [{"role": "user", "content": "Hallo Max"}, {"role": "ai", "content": "Servus"}]
    token = fc.encrypt_json(msgs)
    assert token.startswith("enc:v1:")
    assert fc.decrypt_json(token) == msgs


def test_json_double_encrypt_is_noop():
    # Wichtig fuer idempotente Migration: encrypt_json auf bereits
    # verschluesselten Strings darf NICHT nochmal verschluesseln, sonst
    # gibt decrypt_json nur die aeussere Schicht frei (noch verschluesselt).
    msgs = [{"role": "user", "content": "x"}]
    once = fc.encrypt_json(msgs)
    twice = fc.encrypt_json(once)
    assert once == twice
    assert fc.decrypt_json(twice) == msgs


def test_json_legacy_list_passthrough():
    # Alt-Datensatz aus JSON-Spalte kommt schon als Liste -> unveraendert
    msgs = [{"role": "user", "content": "x"}]
    assert fc.decrypt_json(msgs) == msgs


def test_fail_closed_without_key(monkeypatch):
    monkeypatch.delenv("AILIZA_FIELD_ENCRYPTION_KEY", raising=False)
    monkeypatch.delenv("AILIZA_SECRET_KEY", raising=False)
    mod = importlib.reload(fc)
    mod._get_key.cache_clear()
    with pytest.raises(mod.FieldCryptoError):
        mod.encrypt_field("x")
    # Umgebung/Modul fuer Folgetests wiederherstellen
    monkeypatch.setenv("AILIZA_SECRET_KEY", "test-secret-key-minimum-32-chars-ok")
    importlib.reload(fc)


def test_explicit_key_is_used(monkeypatch):
    key = base64.b64encode(os.urandom(32)).decode()
    monkeypatch.setenv("AILIZA_FIELD_ENCRYPTION_KEY", key)
    mod = importlib.reload(fc)
    mod._get_key.cache_clear()
    tok = mod.encrypt_field("mit explizitem Schluessel")
    assert mod.decrypt_field(tok) == "mit explizitem Schluessel"
    monkeypatch.delenv("AILIZA_FIELD_ENCRYPTION_KEY", raising=False)
    importlib.reload(fc)
