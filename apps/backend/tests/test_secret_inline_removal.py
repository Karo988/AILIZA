"""
Karo-Fund 2026-07-15: Ein erkanntes Geheimnis (API-Key etc.) blockierte
bisher die GESAMTE Vorschau statt nur den Fund selbst zu entfernen.
Betreiber-Entscheidung: gezielt entfernen (Platzhalter), Rest der
Nachricht bleibt nutzbar. Der Platzhalter wird NIE wiedereingefuegt -
anders als PII wird ein Secret nicht nach der KI-Antwort zurueckgesetzt.
"""
from __future__ import annotations

import os

os.environ.setdefault("AILIZA_SECRET_KEY", "test-secret-key-minimum-32-chars-ok")
os.environ.setdefault("AILIZA_DATABASE_URL", "sqlite:///:memory:")

import pytest


@pytest.fixture(autouse=True)
def fresh_db():
    from apps.backend.database import init_db, metadata_obj, engine

    metadata_obj.drop_all(engine)
    init_db()
    yield


def _policy_redact(text: str):
    from apps.backend.main import policy_redact, PolicyRedactRequest
    return policy_redact(PolicyRedactRequest(text=text), current_user=None)


def test_openai_key_removed_not_whole_message_blocked():
    text = "Bitte nutze diesen Key: sk-abcdefghijklmnopqrstuvwxyz123456 fuer den Test."
    r = _policy_redact(text)
    assert "sk-abcdefghijklmnopqrstuvwxyz123456" not in r.safe_text
    assert "[API-KEY ENTFERNT]" in r.safe_text
    assert "Bitte nutze diesen Key" in r.safe_text
    assert "fuer den Test" in r.safe_text
    assert r.decision != "security_block"
    assert "[BLOCKIERT" not in r.safe_text


def test_groq_key_removed_not_whole_message_blocked():
    text = "Groq-Key: gsk_abcdefghijklmnopqrstuvwxyz123456"
    r = _policy_redact(text)
    assert "gsk_abcdefghijklmnopqrstuvwxyz123456" not in r.safe_text
    assert "[API-KEY ENTFERNT]" in r.safe_text


def test_bearer_token_removed_not_whole_message_blocked():
    text = "Header: Bearer abcdefghijklmnopqrstuvwxyz1234567890"
    r = _policy_redact(text)
    assert "abcdefghijklmnopqrstuvwxyz1234567890" not in r.safe_text
    assert "[API-KEY ENTFERNT]" in r.safe_text


def test_clean_text_without_secret_unaffected():
    r = _policy_redact("Ganz normale Anfrage ohne Geheimnisse.")
    assert "[API-KEY ENTFERNT]" not in r.safe_text
    assert r.safe_text == "Ganz normale Anfrage ohne Geheimnisse."


def test_secret_placeholder_not_reinserted():
    # Der Platzhalter selbst wird von der Reinsertion nicht angefasst -
    # er landet nicht in der reinsertion_map, weil er clientseitig/
    # serverseitig kein bekannter Platzhalter aus der PII-Redaction ist.
    from apps.backend.governance.redaction import reinsert
    text = "Vorher [API-KEY ENTFERNT] nachher"
    result, fully = reinsert(text, {})
    assert result == text
