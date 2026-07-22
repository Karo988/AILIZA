"""
B8a: Beta-Zugangsschutz (Freigabe Stufe 1, geschlossene Beta).

AILIZA_BETA_LOGIN_ENABLED=true UND AILIZA_BETA_ACCESS_CODE gesetzt -> die
gesamte App (inkl. API) ist nur mit gueltigem Zugangs-Cookie nutzbar.
/health bleibt immer frei. Der Cookie-Wert ist ein HMAC ueber (Secret-Key,
Zugangscode) - kein Klartext-Code im Cookie, und ein Code-Wechsel invalidiert
automatisch alle bestehenden Cookies (Betreiber-Anpassung ggue. der
urspruenglichen Planung).

Karo-Entscheidung 2026-07-22: AILIZA_BETA_ACCESS_CODE ALLEIN darf das Gate
nicht mehr aktivieren (Incident: versehentlich in Render gesetzter Code hat
die App auf einem anderen Handy gesperrt). Das Gate braucht seitdem BEIDE
Werte -- AILIZA_BETA_LOGIN_ENABLED=true UND einen Code.
"""
from __future__ import annotations

import os

os.environ.setdefault("AILIZA_SECRET_KEY", "test-secret-key-minimum-32-chars-ok")
os.environ.setdefault("AILIZA_DATABASE_URL", "sqlite:///:memory:")

from fastapi.testclient import TestClient

from apps.backend.main import app

COOKIE_NAME = "ailiza_beta_access"


def _client() -> TestClient:
    return TestClient(app)


def test_health_free_with_gate_active(monkeypatch):
    monkeypatch.setenv("AILIZA_BETA_LOGIN_ENABLED", "true")
    monkeypatch.setenv("AILIZA_BETA_ACCESS_CODE", "test-code-1")
    r = _client().get("/health")
    assert r.status_code == 200


def test_health_free_without_gate(monkeypatch):
    monkeypatch.delenv("AILIZA_BETA_LOGIN_ENABLED", raising=False)
    monkeypatch.delenv("AILIZA_BETA_ACCESS_CODE", raising=False)
    r = _client().get("/health")
    assert r.status_code == 200


def test_gate_disabled_when_env_not_set(monkeypatch):
    """Regressionsschutz: ohne gesetzten Code verhaelt sich alles wie vorher."""
    monkeypatch.delenv("AILIZA_BETA_LOGIN_ENABLED", raising=False)
    monkeypatch.delenv("AILIZA_BETA_ACCESS_CODE", raising=False)
    r = _client().post("/agent/run", json={"task": "hallo"})
    assert r.status_code != 403 or "geschlossenen Beta" not in r.text


def test_code_alone_does_not_activate_gate(monkeypatch):
    """Kern-Regressionstest fuer den Render-Incident (22.07.2026): ein
    versehentlich gesetzter AILIZA_BETA_ACCESS_CODE OHNE
    AILIZA_BETA_LOGIN_ENABLED darf die App NICHT sperren."""
    monkeypatch.delenv("AILIZA_BETA_LOGIN_ENABLED", raising=False)
    monkeypatch.setenv("AILIZA_BETA_ACCESS_CODE", "versehentlich-gesetzt")
    r = _client().get("/", headers={"accept": "text/html"})
    assert r.status_code == 200
    assert "geschlossenen Beta" not in r.text

    r2 = _client().post("/agent/run", json={"task": "hallo"})
    assert r2.status_code != 403 or "geschlossenen Beta" not in r2.text


def test_login_enabled_explicitly_false_does_not_activate_gate(monkeypatch):
    monkeypatch.setenv("AILIZA_BETA_LOGIN_ENABLED", "false")
    monkeypatch.setenv("AILIZA_BETA_ACCESS_CODE", "test-code-1")
    r = _client().get("/", headers={"accept": "text/html"})
    assert r.status_code == 200
    assert "geschlossenen Beta" not in r.text


def test_html_request_without_cookie_shows_gate_page(monkeypatch):
    monkeypatch.setenv("AILIZA_BETA_LOGIN_ENABLED", "true")
    monkeypatch.setenv("AILIZA_BETA_ACCESS_CODE", "test-code-1")
    r = _client().get("/", headers={"accept": "text/html"})
    assert r.status_code == 200
    assert "geschlossenen Beta" in r.text
    assert "Zugangscode" in r.text


def test_api_request_without_cookie_blocked_with_json(monkeypatch):
    monkeypatch.setenv("AILIZA_BETA_LOGIN_ENABLED", "true")
    monkeypatch.setenv("AILIZA_BETA_ACCESS_CODE", "test-code-1")
    r = _client().post("/agent/run", json={"task": "hallo"})
    assert r.status_code == 403
    assert r.headers["content-type"].startswith("application/json")


def test_wrong_code_rejected(monkeypatch):
    monkeypatch.setenv("AILIZA_BETA_LOGIN_ENABLED", "true")
    monkeypatch.setenv("AILIZA_BETA_ACCESS_CODE", "test-code-1")
    r = _client().post("/beta-access", json={"code": "falscher-code"})
    assert r.status_code == 401
    assert COOKIE_NAME not in r.cookies


def test_correct_code_grants_access(monkeypatch):
    monkeypatch.setenv("AILIZA_BETA_LOGIN_ENABLED", "true")
    monkeypatch.setenv("AILIZA_BETA_ACCESS_CODE", "test-code-1")
    client = _client()
    r = client.post("/beta-access", json={"code": "test-code-1"})
    assert r.status_code == 200
    assert COOKIE_NAME in r.cookies

    # Cookie wird von TestClient automatisch mitgeschickt (gleicher Client)
    r2 = client.get("/", headers={"accept": "text/html"})
    assert "geschlossenen Beta" not in r2.text

    r3 = client.post("/agent/run", json={"task": "hallo"})
    assert r3.status_code != 403 or "geschlossenen Beta" not in r3.text


def test_code_change_invalidates_old_cookie(monkeypatch):
    """Betreiber-Anpassung: HMAC ist an den Code gebunden, ein Code-Wechsel
    invalidiert automatisch alle alten Cookies."""
    monkeypatch.setenv("AILIZA_BETA_LOGIN_ENABLED", "true")
    monkeypatch.setenv("AILIZA_BETA_ACCESS_CODE", "alter-code")
    client = _client()
    r = client.post("/beta-access", json={"code": "alter-code"})
    old_cookie_value = r.cookies.get(COOKIE_NAME)
    assert old_cookie_value

    monkeypatch.setenv("AILIZA_BETA_ACCESS_CODE", "neuer-code")
    new_client = _client()
    new_client.cookies.set(COOKIE_NAME, old_cookie_value)
    r2 = new_client.post("/agent/run", json={"task": "hallo"})
    assert r2.status_code == 403


def test_cookie_does_not_contain_plaintext_code(monkeypatch):
    monkeypatch.setenv("AILIZA_BETA_LOGIN_ENABLED", "true")
    monkeypatch.setenv("AILIZA_BETA_ACCESS_CODE", "mein-geheimer-code")
    client = _client()
    r = client.post("/beta-access", json={"code": "mein-geheimer-code"})
    cookie_value = r.cookies.get(COOKIE_NAME)
    assert "mein-geheimer-code" not in cookie_value
