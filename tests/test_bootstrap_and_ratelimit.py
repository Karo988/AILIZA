"""
Tests fuer Bootstrap-Script und Rate-Limiting.
"""
from __future__ import annotations

import os
import pytest

os.environ.setdefault("AILIZA_SECRET_KEY", "test-secret-key-minimum-32-chars-ok")
os.environ.setdefault("AILIZA_DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("AILIZA_EXTERNAL_LLM_ENABLED", "false")


# ── Passwort-Policy ───────────────────────────────────────────────────────────
def test_password_policy_ok():
    import sys
    sys.path.insert(0, "apps/backend")
    from create_admin import _check_password_policy
    assert _check_password_policy("Secure!Pass1@") == []


def test_password_policy_too_short():
    from create_admin import _check_password_policy
    errors = _check_password_policy("Ab1!")
    assert any("12 Zeichen" in e for e in errors)


def test_password_policy_no_upper():
    from create_admin import _check_password_policy
    errors = _check_password_policy("secure!pass1@")
    assert any("Großbuchstabe" in e for e in errors)


def test_password_policy_no_digit():
    from create_admin import _check_password_policy
    errors = _check_password_policy("Secure!PassAB")
    assert any("Zahl" in e for e in errors)


def test_password_policy_no_special():
    from create_admin import _check_password_policy
    errors = _check_password_policy("SecurePass123A")
    assert any("Sonderzeichen" in e for e in errors)


# ── Bootstrap-Sperre ─────────────────────────────────────────────────────────
def test_bootstrap_blocked_when_setup_done(monkeypatch):
    monkeypatch.setenv("AILIZA_SETUP_DONE", "true")
    from create_admin import main
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 1


def test_bootstrap_blocked_when_secret_missing(monkeypatch):
    monkeypatch.delenv("AILIZA_SETUP_DONE", raising=False)
    monkeypatch.setenv("AILIZA_SECRET_KEY", "short")
    from create_admin import main
    import importlib
    import create_admin
    importlib.reload(create_admin)
    with pytest.raises(SystemExit) as exc:
        create_admin.main()
    assert exc.value.code == 1


# ── Health/Ready-Endpoints ────────────────────────────────────────────────────
@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient
    from apps.backend.main import app
    from apps.backend.database import init_db
    init_db()
    return TestClient(app)


def test_health_endpoint(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["service"] == "ailiza-backend"


def test_ready_endpoint(client):
    resp = client.get("/ready")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] in ("ok", "degraded")
    assert "database" in data["checks"]
    assert "kill_switch" in data["checks"]


# ── Rate-Limit ────────────────────────────────────────────────────────────────
def test_login_rate_limit(client):
    """Login-Endpunkt darf maximal 10x/Minute aufgerufen werden."""
    payload = {"user_id": "nobody", "password": "wrong"}
    responses = [client.post("/auth/login", json=payload) for _ in range(12)]
    status_codes = [r.status_code for r in responses]
    # Erste 10: 401 (falsche Credentials), danach 429 (Rate-Limit)
    assert 429 in status_codes, f"Kein Rate-Limit ausgeloest: {status_codes}"
