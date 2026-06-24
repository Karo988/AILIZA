"""
Auth Tests — API-Key-Modell mit Rollentrennung
"""
import pytest
import apps.backend.auth as auth_module
from fastapi import FastAPI
from fastapi.testclient import TestClient

from apps.backend.auth import require_operator, require_admin
from apps.backend.routers.kill_switch import router as ks_router
from apps.backend.routers.vault import router as vault_router, get_vault
from apps.backend.audit.vault import AuditVault


OPERATOR_KEY = "test-operator-key"
ADMIN_KEY = "test-admin-key"


@pytest.fixture(autouse=True)
def patch_keys(monkeypatch):
    monkeypatch.setattr(auth_module, "_OPERATOR_KEY", OPERATOR_KEY)
    monkeypatch.setattr(auth_module, "_ADMIN_KEY", ADMIN_KEY)


@pytest.fixture
def app(tmp_path):
    a = FastAPI()
    a.include_router(ks_router)
    a.include_router(vault_router)
    import apps.backend.routers.vault as vm
    vm._vault = AuditVault(db_path=str(tmp_path / "vault.db"))
    return a


@pytest.fixture
def client(app):
    return TestClient(app, raise_server_exceptions=True)


# ── Kein Key ──────────────────────────────────────────────────────────────────

class TestNoKey:
    def test_status_ohne_key_liefert_401(self, client):
        r = client.get("/admin/kill-switch/status")
        assert r.status_code == 401

    def test_halt_ohne_key_liefert_401(self, client):
        r = client.post("/admin/kill-switch/halt", json={"level": "global"})
        assert r.status_code == 401

    def test_vault_export_ohne_key_liefert_401(self, client):
        r = client.get("/audit/vault/export")
        assert r.status_code == 401


# ── Falscher Key ──────────────────────────────────────────────────────────────

class TestWrongKey:
    def test_falscher_key_liefert_403(self, client):
        r = client.get("/admin/kill-switch/status", headers={"x-api-key": "wrong"})
        assert r.status_code == 403

    def test_vault_falscher_key_liefert_403(self, client):
        r = client.get("/audit/vault/stats", headers={"x-api-key": "wrong"})
        assert r.status_code == 403


# ── Operator-Rolle ────────────────────────────────────────────────────────────

class TestOperatorRole:
    def test_operator_darf_status_lesen(self, client):
        r = client.get("/admin/kill-switch/status", headers={"x-api-key": OPERATOR_KEY})
        assert r.status_code == 200

    def test_operator_darf_vault_export(self, client):
        r = client.get("/audit/vault/export", headers={"x-api-key": OPERATOR_KEY})
        assert r.status_code == 200

    def test_operator_darf_nicht_halt(self, client):
        r = client.post("/admin/kill-switch/halt", json={"level": "global"}, headers={"x-api-key": OPERATOR_KEY})
        assert r.status_code == 403

    def test_operator_darf_nicht_resume(self, client):
        r = client.post("/admin/kill-switch/resume", json={"level": "global"}, headers={"x-api-key": OPERATOR_KEY})
        assert r.status_code == 403


# ── Admin-Rolle ───────────────────────────────────────────────────────────────

class TestAdminRole:
    def test_admin_darf_status_lesen(self, client):
        r = client.get("/admin/kill-switch/status", headers={"x-api-key": ADMIN_KEY})
        assert r.status_code == 200

    def test_admin_darf_halt(self, client):
        r = client.post("/admin/kill-switch/halt", json={"level": "global"}, headers={"x-api-key": ADMIN_KEY})
        assert r.status_code == 200

    def test_admin_darf_resume(self, client):
        r = client.post("/admin/kill-switch/resume", json={"level": "global"}, headers={"x-api-key": ADMIN_KEY})
        assert r.status_code == 200

    def test_admin_darf_vault_verify(self, client):
        r = client.get("/audit/vault/verify", headers={"x-api-key": ADMIN_KEY})
        assert r.status_code == 200
