"""
Vault Router Tests — /audit/vault/export, /stats, /verify
"""
import pytest
from fastapi.testclient import TestClient
from fastapi import FastAPI

from apps.backend.routers.vault import router, get_vault
from apps.backend.audit.vault import AuditVault


@pytest.fixture
def vault(tmp_path):
    return AuditVault(db_path=str(tmp_path / "test_vault.db"))


@pytest.fixture
def client(vault):
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides = {}
    # Override the lazy singleton
    import apps.backend.routers.vault as vault_module
    original = vault_module._vault
    vault_module._vault = vault
    yield TestClient(app)
    vault_module._vault = original


class TestVaultExport:
    def test_export_leer(self, client):
        r = client.get("/audit/vault/export")
        assert r.status_code == 200
        assert r.json() == []

    def test_export_gibt_eintraege_zurueck(self, client, vault):
        vault.record("policy.decision", "system")
        vault.record("approval.granted", "operator")
        r = client.get("/audit/vault/export")
        assert r.status_code == 200
        data = r.json()
        assert len(data) == 2
        assert data[0]["sequence"] == 1
        assert data[1]["sequence"] == 2

    def test_export_felder_vollstaendig(self, client, vault):
        vault.record("test.event", "actor-1")
        r = client.get("/audit/vault/export")
        entry = r.json()[0]
        assert set(entry.keys()) == {"sequence", "event_type", "timestamp_iso", "actor_id", "previous_hash", "entry_hash"}

    def test_export_limit(self, client, vault):
        for i in range(5):
            vault.record(f"event.{i}", "system")
        r = client.get("/audit/vault/export?limit=3")
        assert len(r.json()) == 3


class TestVaultStats:
    def test_stats_leer(self, client):
        r = client.get("/audit/vault/stats")
        assert r.status_code == 200
        data = r.json()
        assert data["total_entries"] == 0
        assert data["chain_intact"] is True
        assert data["first_defect_at_sequence"] is None

    def test_stats_zaehlt_eintraege(self, client, vault):
        vault.record("ev1", "a")
        vault.record("ev2", "b")
        r = client.get("/audit/vault/stats")
        assert r.json()["total_entries"] == 2


class TestVaultVerify:
    def test_verify_intakte_kette(self, client, vault):
        vault.record("ev1", "a")
        vault.record("ev2", "b")
        r = client.get("/audit/vault/verify")
        assert r.status_code == 200
        data = r.json()
        assert data["intact"] is True
        assert data["first_defect_at_sequence"] is None

    def test_verify_leere_kette(self, client):
        r = client.get("/audit/vault/verify")
        assert r.json()["intact"] is True

    def test_verify_erkennt_manipulation(self, client, vault):
        vault.record("ev1", "a")
        vault.record("ev2", "b")
        # Direkte DB-Manipulation
        vault._conn.execute("UPDATE vault SET entry_hash = 'deadbeef' WHERE sequence = 1")
        vault._conn.commit()
        r = client.get("/audit/vault/verify")
        data = r.json()
        assert data["intact"] is False
        assert data["first_defect_at_sequence"] == 1

    def test_verify_erkennt_previous_hash_manipulation(self, client, vault):
        vault.record("ev1", "a")
        vault.record("ev2", "b")
        vault._conn.execute("UPDATE vault SET previous_hash = 'manipuliert' WHERE sequence = 2")
        vault._conn.commit()
        r = client.get("/audit/vault/verify")
        data = r.json()
        assert data["intact"] is False
        assert data["first_defect_at_sequence"] == 2
