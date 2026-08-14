"""Anonyme Sitzungstrennung (Paket B).

Vorher teilten sich ALLE nicht eingeloggten Nutzer denselben Pseudo-Wert
"__anonymous__" in der Pruefbeleg-Bindung -- ein in Browser A ausgestellter
Beleg waere in Browser B ebenfalls gueltig gewesen (kein Test bewies das
Gegenteil). Jetzt bekommt jede anonyme Sitzung ein eigenes, hochentropisches
HttpOnly-Cookie, das als Bindungsschluessel dient.
"""
from __future__ import annotations

import os

os.environ.setdefault("AILIZA_SECRET_KEY", "test-secret-key-minimum-32-chars-ok")
os.environ.setdefault("AILIZA_DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("AILIZA_EXTERNAL_LLM_ENABLED", "false")

from fastapi.testclient import TestClient

from apps.backend.main import app, _ANON_SESSION_COOKIE

_HARMLOS = "Wie formuliere ich eine freundliche Absage?"


def _preview(client: TestClient, text: str) -> dict:
    r = client.post("/api/policy-redact", json={"text": text})
    assert r.status_code == 200, r.text
    return r.json()


def test_anon_session_cookie_is_set_and_httponly():
    client = TestClient(app, cookies={})
    r = client.post("/api/policy-redact", json={"text": _HARMLOS})
    assert r.status_code == 200
    set_cookie_header = r.headers.get("set-cookie", "")
    assert _ANON_SESSION_COOKIE in set_cookie_header
    assert "httponly" in set_cookie_header.lower()
    assert "samesite=strict" in set_cookie_header.lower()


def test_anon_session_cookie_is_stable_across_requests():
    """Derselbe Browser (=derselbe TestClient mit Cookie-Jar) behaelt
    dieselbe Sitzungskennung ueber mehrere Requests hinweg."""
    client = TestClient(app, cookies={})
    client.post("/api/policy-redact", json={"text": _HARMLOS})
    first = client.cookies.get(_ANON_SESSION_COOKIE)
    assert first

    client.post("/api/policy-redact", json={"text": "Eine andere Frage."})
    second = client.cookies.get(_ANON_SESSION_COOKIE)
    assert second == first


def test_preview_from_one_anon_session_cannot_be_used_by_another():
    """Kernbeweis: ein in Browser A (Client 1) ausgestellter Beleg darf in
    Browser B (Client 2, eigenes Cookie-Jar) NICHT eingeloest werden."""
    browser_a = TestClient(app, cookies={})
    browser_b = TestClient(app, cookies={})

    preview = _preview(browser_a, _HARMLOS)
    if not preview.get("preview_id"):
        import pytest
        pytest.skip("Kein Beleg ausgestellt")

    result = browser_b.post(
        "/agent/run",
        json={"task": preview["safe_text"], "preview_id": preview["preview_id"]},
    )
    assert result.status_code == 200
    assert result.json()["status"] == "preview_invalid"


def test_preview_from_own_anon_session_still_works():
    """Gegenprobe: derselbe Browser darf seinen eigenen Beleg weiter nutzen --
    die Sitzungstrennung darf die normale anonyme Nutzung nicht kaputt machen."""
    browser = TestClient(app, cookies={})
    preview = _preview(browser, _HARMLOS)
    if not preview.get("preview_id"):
        import pytest
        pytest.skip("Kein Beleg ausgestellt")

    result = browser.post(
        "/agent/run",
        json={"task": preview["safe_text"], "preview_id": preview["preview_id"]},
    )
    assert result.status_code == 200
    assert result.json()["status"] != "preview_invalid"


def test_two_different_anon_browsers_get_different_session_ids():
    browser_a = TestClient(app, cookies={})
    browser_b = TestClient(app, cookies={})
    browser_a.post("/api/policy-redact", json={"text": _HARMLOS})
    browser_b.post("/api/policy-redact", json={"text": _HARMLOS})

    id_a = browser_a.cookies.get(_ANON_SESSION_COOKIE)
    id_b = browser_b.cookies.get(_ANON_SESSION_COOKIE)
    assert id_a and id_b
    assert id_a != id_b


def test_manipulated_short_cookie_gets_replaced_fail_closed():
    """Ein zu kurzes/geratenes Cookie wird NICHT als gueltige Sitzung
    akzeptiert -- der Server stellt fail-closed eine neue aus, statt eine
    schwache/erratbare Kennung zu vertrauen."""
    client = TestClient(app, cookies={_ANON_SESSION_COOKIE: "geraten123"})
    r = client.post("/api/policy-redact", json={"text": _HARMLOS})
    assert r.status_code == 200
    set_cookie_header = r.headers.get("set-cookie", "")
    assert f"{_ANON_SESSION_COOKIE}=geraten123" not in set_cookie_header
    assert f"{_ANON_SESSION_COOKIE}=" in set_cookie_header


def test_logged_in_user_cannot_use_anon_session_preview():
    """Bindung an eine Anmeldung bleibt bestehen: ein anonymer Beleg darf
    nicht einfach durch spaeteres Einloggen "aufgewertet" werden."""
    import pytest

    from apps.backend.database import create_user
    from apps.backend.auth import create_token

    create_user(user_id="erika", tenant_id="default", role="user", hashed_password="hash")
    token = create_token(user_id="erika", tenant_id="default", role="user")

    anon_client = TestClient(app, cookies={})
    preview = _preview(anon_client, _HARMLOS)
    if not preview.get("preview_id"):
        pytest.skip("Kein Beleg ausgestellt")

    logged_in_client = TestClient(app, cookies=dict(anon_client.cookies))
    result = logged_in_client.post(
        "/agent/run",
        json={"task": preview["safe_text"], "preview_id": preview["preview_id"]},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert result.status_code == 200
    assert result.json()["status"] == "preview_invalid"
