"""
Audit Vault Tests
=================
EU AI Act Art. 12: Aufzeichnungspflichten — Manipulationssicherheit
DSGVO Art. 30: Unveränderlichkeit des Verarbeitungsverzeichnisses

Prüft:
- Hash-Kette startet korrekt mit Genesis-Hash
- Jeder Eintrag bindet den Hash des Vorgängers ein
- verify_chain() erkennt intakte und manipulierte Ketten
- Sequenznummern steigen monoton
- Export enthält kein content-Feld (nur Metadaten)
- Schnittstelle bietet keine Update- oder Delete-Methode (write-once)
- Leerer Vault ist valide
- stats() liefert korrekten Zustand
"""

import hashlib
import pytest

from apps.backend.audit.vault import AuditVault, VaultEntry, _GENESIS_HASH, _compute_hash


@pytest.fixture
def vault():
    """Frischer In-Memory Vault für jeden Test."""
    return AuditVault(db_path=":memory:")


# ── Initialisierung ───────────────────────────────────────────────────────────

class TestVaultInit:
    def test_leerer_vault_ist_valide(self, vault):
        """Ein neuer Vault ohne Einträge muss verify_chain() bestehen."""
        intact, defect = vault.verify_chain()
        assert intact is True
        assert defect is None

    def test_leerer_vault_hat_null_eintraege(self, vault):
        assert vault.stats()["total_entries"] == 0

    def test_erster_eintrag_verwendet_genesis_hash(self, vault):
        entry = vault.record("CONSENT_GRANTED", "user-001")
        assert entry.previous_hash == _GENESIS_HASH


# ── Hash-Kette ────────────────────────────────────────────────────────────────

class TestHashChain:
    def test_zweiter_eintrag_bindet_hash_des_ersten(self, vault):
        first = vault.record("CONSENT_GRANTED", "user-001")
        second = vault.record("APPROVAL_GIVEN", "operator-001")
        assert second.previous_hash == first.entry_hash

    def test_dritter_eintrag_bindet_hash_des_zweiten(self, vault):
        vault.record("CONSENT_GRANTED", "user-001")
        second = vault.record("APPROVAL_GIVEN", "operator-001")
        third = vault.record("MEMORY_DEACTIVATED", "system")
        assert third.previous_hash == second.entry_hash

    def test_entry_hash_ist_sha256_der_vier_felder(self, vault):
        entry = vault.record("CONSENT_GRANTED", "user-001")
        expected = _compute_hash(
            _GENESIS_HASH,
            entry.event_type,
            entry.timestamp_iso,
            entry.actor_id,
        )
        assert entry.entry_hash == expected

    def test_entry_hash_ist_64_zeichen_hex(self, vault):
        entry = vault.record("TEST_EVENT", "actor-x")
        assert len(entry.entry_hash) == 64
        assert all(c in "0123456789abcdef" for c in entry.entry_hash)

    def test_sequenznummern_steigen_monoton(self, vault):
        a = vault.record("EVENT_A", "actor")
        b = vault.record("EVENT_B", "actor")
        c = vault.record("EVENT_C", "actor")
        assert a.sequence < b.sequence < c.sequence


# ── verify_chain() ────────────────────────────────────────────────────────────

class TestVerifyChain:
    def test_intakte_kette_wird_bestaetigt(self, vault):
        vault.record("CONSENT_GRANTED", "user-001")
        vault.record("APPROVAL_GIVEN", "operator-001")
        vault.record("MEMORY_DEACTIVATED", "system")
        intact, defect = vault.verify_chain()
        assert intact is True
        assert defect is None

    def test_manipulierter_entry_hash_wird_erkannt(self, vault):
        vault.record("CONSENT_GRANTED", "user-001")
        vault.record("APPROVAL_GIVEN", "operator-001")

        # Direkter SQL-Eingriff simuliert Manipulation
        vault._conn.execute(
            "UPDATE vault SET entry_hash = ? WHERE sequence = 1",
            ("a" * 64,),
        )
        vault._conn.commit()

        intact, defect = vault.verify_chain()
        assert intact is False
        assert defect is not None

    def test_manipulation_in_der_mitte_wird_erkannt(self, vault):
        vault.record("EVENT_1", "actor")
        vault.record("EVENT_2", "actor")
        vault.record("EVENT_3", "actor")

        # Eintrag 2 wird manipuliert
        vault._conn.execute(
            "UPDATE vault SET actor_id = 'manipulated' WHERE sequence = 2",
        )
        vault._conn.commit()

        intact, defect = vault.verify_chain()
        assert intact is False
        # Defekt wird spätestens bei Sequenz 2 erkannt
        assert defect is not None

    def test_manipulierter_previous_hash_wird_erkannt(self, vault):
        vault.record("EVENT_1", "actor")
        vault.record("EVENT_2", "actor")

        vault._conn.execute(
            "UPDATE vault SET previous_hash = ? WHERE sequence = 2",
            ("0" * 64,),
        )
        vault._conn.commit()

        intact, defect = vault.verify_chain()
        assert intact is False


# ── Kein Inhalt im Vault ──────────────────────────────────────────────────────

class TestKeinInhalt:
    def test_vault_entry_hat_kein_content_feld(self, vault):
        entry = vault.record("CONSENT_GRANTED", "user-001")
        entry_dict = entry.to_dict()
        assert "content" not in entry_dict
        assert "details" not in entry_dict
        assert "payload" not in entry_dict
        assert "data" not in entry_dict

    def test_export_enthaelt_nur_metadaten_felder(self, vault):
        vault.record("APPROVAL_GIVEN", "operator-001")
        exported = vault.export()
        assert len(exported) == 1
        erlaubte_felder = {"sequence", "event_type", "timestamp_iso", "actor_id", "previous_hash", "entry_hash"}
        assert set(exported[0].keys()) == erlaubte_felder

    def test_vault_entry_slots_enthalten_keinen_klartext(self, vault):
        """VaultEntry.__slots__ darf kein content/details/data enthalten."""
        verbotene = {"content", "details", "data", "payload", "message", "body"}
        slots = set(VaultEntry.__slots__)
        assert slots.isdisjoint(verbotene)


# ── Write-once Schnittstelle ──────────────────────────────────────────────────

class TestWriteOnce:
    def test_keine_update_methode_auf_vault(self, vault):
        assert not hasattr(vault, "update")
        assert not hasattr(vault, "edit")
        assert not hasattr(vault, "modify")

    def test_keine_delete_methode_auf_vault(self, vault):
        assert not hasattr(vault, "delete")
        assert not hasattr(vault, "remove")
        assert not hasattr(vault, "hard_delete")

    def test_eintraege_bleiben_nach_weiteren_records_erhalten(self, vault):
        vault.record("EVENT_1", "actor")
        vault.record("EVENT_2", "actor")
        vault.record("EVENT_3", "actor")
        assert vault.stats()["total_entries"] == 3


# ── Export und Stats ──────────────────────────────────────────────────────────

class TestExportStats:
    def test_export_liefert_alle_eintraege(self, vault):
        for i in range(5):
            vault.record(f"EVENT_{i}", "actor")
        exported = vault.export()
        assert len(exported) == 5

    def test_export_reihenfolge_ist_aufsteigend(self, vault):
        vault.record("FIRST", "actor")
        vault.record("SECOND", "actor")
        exported = vault.export()
        assert exported[0]["event_type"] == "FIRST"
        assert exported[1]["event_type"] == "SECOND"

    def test_stats_meldet_kette_intact(self, vault):
        vault.record("CONSENT_GRANTED", "user-001")
        s = vault.stats()
        assert s["chain_intact"] is True
        assert s["first_defect_at_sequence"] is None
        assert s["total_entries"] == 1

    def test_stats_meldet_kette_defekt_nach_manipulation(self, vault):
        vault.record("CONSENT_GRANTED", "user-001")
        vault._conn.execute("UPDATE vault SET entry_hash = ? WHERE sequence = 1", ("x" * 64,))
        vault._conn.commit()
        s = vault.stats()
        assert s["chain_intact"] is False
