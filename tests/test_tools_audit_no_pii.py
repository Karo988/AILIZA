"""Audit-Logs der Tool-Endpunkte duerfen keine Nutzerinhalte enthalten.

Hintergrund: /tools/search und /tools/fetch schrieben die rohe Suchanfrage
bzw. die vollstaendige URL in die Audit-Metadaten. Beides kann
personenbezogene Daten oder Geheimnisse tragen (Namen, Adressen, Profil-IDs,
Tokens im Query-String). CLAUDE.md verbietet PII/Secrets/vollstaendige
Prompts in Logs -- diese Tests halten den Fix fest.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from apps.backend.main import app

client = TestClient(app)

_SENSITIVE_QUERY = "Krankenakte Erika Mustermann Diagnose"
_SENSITIVE_URL = "https://example.invalid/patient/erika-mustermann?token=geheim123"


_LOG_KEY = "test-log-hmac-key-mindestens-32-zeichen-lang"


def _captured_metadata(action_prefix: str, call_endpoint, log_key: str | None = _LOG_KEY) -> dict:
    captured: list[dict] = []

    def _fake_audit(action: str, **kwargs):
        if action.startswith(action_prefix):
            captured.append(kwargs.get("metadata") or {})

    env = {"AILIZA_LOG_HMAC_KEY": log_key} if log_key else {"AILIZA_LOG_HMAC_KEY": ""}
    with patch.dict("os.environ", env):
        with patch("apps.backend.main.write_audit_entry", side_effect=_fake_audit):
            with patch("apps.backend.main.guarded_tool_call", return_value={"status": "blocked"}):
                call_endpoint()

    assert captured, f"Kein Audit-Eintrag fuer {action_prefix} erfasst"
    return captured[0]


def test_search_audit_does_not_contain_raw_query():
    metadata = _captured_metadata(
        "tools.search",
        lambda: client.post("/tools/search", json={"query": _SENSITIVE_QUERY}),
    )
    flat = str(metadata)
    assert _SENSITIVE_QUERY not in flat
    assert "Mustermann" not in flat
    # Nachvollziehbarkeit bleibt erhalten, ohne Inhalt preiszugeben.
    assert metadata.get("query_len") == len(_SENSITIVE_QUERY)
    assert metadata.get("query_fingerprint", "").startswith("q_v")


def test_search_fingerprint_is_not_plain_sha256():
    """Regressionsschutz: ein unkeyed SHA-256 waere per Woerterbuchangriff
    umkehrbar -- wer Log-Zugriff hat, koennte Kandidaten durchhashen und
    vergleichen. Der Fingerprint MUSS vom Logging-Schluessel abhaengen."""
    import hashlib as _hashlib

    metadata = _captured_metadata(
        "tools.search",
        lambda: client.post("/tools/search", json={"query": _SENSITIVE_QUERY}),
    )
    plain = _hashlib.sha256(_SENSITIVE_QUERY.encode("utf-8")).hexdigest()
    fingerprint = metadata.get("query_fingerprint", "")
    assert plain[:20] not in fingerprint

    # Anderer Schluessel -> anderer Fingerprint fuer denselben Text.
    other = _captured_metadata(
        "tools.search",
        lambda: client.post("/tools/search", json={"query": _SENSITIVE_QUERY}),
        log_key="ein-voellig-anderer-schluessel-32-zeichen",
    )
    assert other.get("query_fingerprint") != fingerprint


def test_no_fingerprint_without_log_key():
    """Fehlt der Logging-Schluessel, wird KEIN Fingerprint erzeugt --
    kein stiller Rueckfall auf Klartext oder SHA-256 (gleiche Regel wie
    bei _mask_user_id_for_log)."""
    metadata = _captured_metadata(
        "tools.search",
        lambda: client.post("/tools/search", json={"query": _SENSITIVE_QUERY}),
        log_key=None,
    )
    assert "query_fingerprint" not in metadata
    assert _SENSITIVE_QUERY not in str(metadata)
    # Die inhaltsfreie Metrik bleibt trotzdem erhalten.
    assert metadata.get("query_len") == len(_SENSITIVE_QUERY)


def test_fetch_audit_does_not_contain_full_url():
    metadata = _captured_metadata(
        "tools.fetch",
        lambda: client.post("/tools/fetch", json={"url": _SENSITIVE_URL}),
    )
    flat = str(metadata)
    assert _SENSITIVE_URL not in flat
    assert "geheim123" not in flat, "Token aus dem Query-String darf nie im Audit stehen"
    assert "erika-mustermann" not in flat
    # Host bleibt erlaubt: er ist fuer die Sicherheitsbewertung noetig und
    # enthaelt selbst keine personenbezogenen Pfad-/Query-Daten.
    assert metadata.get("url_host") == "example.invalid"
    assert metadata.get("url_fingerprint", "").startswith("u_v")


def test_fetch_audit_handles_malformed_url_without_crashing():
    """Kaputte URL darf den Endpunkt nicht mit einer Exception beenden --
    sonst waere der Audit-Pfad selbst ein Absturzrisiko."""
    metadata = _captured_metadata(
        "tools.fetch",
        lambda: client.post("/tools/fetch", json={"url": "nicht-mal-eine-url"}),
    )
    assert metadata.get("url_host") == "unbekannt"
