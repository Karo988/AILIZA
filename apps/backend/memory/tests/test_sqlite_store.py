"""
SQLite Memory Store Tests — BS-14 bis BS-18
============================================
Gleiche Anforderungen wie test_memory.py, aber auf persistentem Backend.
Alle Tests laufen mit db_path=":memory:" — isoliert, kein Dateisystem nötig.
"""

import pytest
from datetime import datetime, timedelta, timezone

from ..models import DataClass, MemoryEntry, MemoryPurpose, VisibilityLevel
from ..sqlite_store import SqliteMemoryStore


def _future(seconds: int = 3600) -> datetime:
    return datetime.now(timezone.utc) + timedelta(seconds=seconds)


def _past(seconds: int = 1) -> datetime:
    return datetime.now(timezone.utc) - timedelta(seconds=seconds)


def _entry(**kwargs) -> MemoryEntry:
    defaults = dict(
        purpose=MemoryPurpose.SESSION,
        content_hash=MemoryEntry.hash_content("test-inhalt"),
        visibility=VisibilityLevel.USER,
        role_required="user",
        retention_until=_future(),
    )
    defaults.update(kwargs)
    return MemoryEntry(**defaults)


@pytest.fixture
def store():
    return SqliteMemoryStore(db_path=":memory:")


# ── Grundfunktionen ───────────────────────────────────────────────────────────

class TestAdd:
    def test_eintrag_wird_gespeichert(self, store):
        e = store.add(_entry())
        assert store.get(e.id, role="user") is not None

    def test_doppelte_id_wird_abgelehnt(self, store):
        e = _entry()
        store.add(e)
        with pytest.raises(ValueError):
            store.add(e)

    def test_sensitive_default_bleibt_erhalten(self, store):
        e = store.add(_entry())
        geladen = store.get(e.id, role="user")
        assert geladen.sensitive is True

    def test_data_class_bleibt_erhalten(self, store):
        e = store.add(_entry(data_class=DataClass.RESTRICTED))
        geladen = store.get(e.id, role="user")
        assert geladen.data_class == DataClass.RESTRICTED


# ── BS-14: Zweckbindung ───────────────────────────────────────────────────────

class TestBS14Zweckbindung:
    def test_purpose_wird_korrekt_gespeichert(self, store):
        e = store.add(_entry(purpose=MemoryPurpose.CONSENT))
        geladen = store.get(e.id, role="user")
        assert geladen.purpose == MemoryPurpose.CONSENT

    def test_list_active_filtert_nach_purpose(self, store):
        store.add(_entry(purpose=MemoryPurpose.TASK))
        store.add(_entry(purpose=MemoryPurpose.CONSENT))
        tasks = store.list_active(role="user", purpose=MemoryPurpose.TASK)
        assert len(tasks) == 1
        assert tasks[0].purpose == MemoryPurpose.TASK


# ── BS-15: Sichtbarkeit / Rolle ───────────────────────────────────────────────

class TestBS15Sichtbarkeit:
    def test_user_sieht_operator_eintrag_nicht(self, store):
        e = store.add(_entry(visibility=VisibilityLevel.OPERATOR))
        assert store.get(e.id, role="user") is None

    def test_operator_sieht_operator_eintrag(self, store):
        e = store.add(_entry(visibility=VisibilityLevel.OPERATOR))
        assert store.get(e.id, role="operator") is not None

    def test_admin_sieht_system_eintrag(self, store):
        e = store.add(_entry(visibility=VisibilityLevel.SYSTEM))
        assert store.get(e.id, role="admin") is not None

    def test_user_sieht_system_eintrag_nicht(self, store):
        e = store.add(_entry(visibility=VisibilityLevel.SYSTEM))
        assert store.get(e.id, role="user") is None


# ── BS-16: Aufbewahrungsfrist ─────────────────────────────────────────────────

class TestBS16Aufbewahrungsfrist:
    def test_abgelaufener_eintrag_nicht_abrufbar(self, store):
        e = _entry(retention_until=_future(1))
        store.add(e)
        e.retention_until = _past()
        # Store neu laden — simuliert Ablauf durch direktes Update
        store._conn.execute(
            "UPDATE memory_entries SET retention_until = ? WHERE id = ?",
            (_past().isoformat(), e.id),
        )
        store._conn.commit()
        assert store.get(e.id, role="user") is None

    def test_purge_expired_deaktiviert_abgelaufene(self, store):
        e = store.add(_entry())
        store._conn.execute(
            "UPDATE memory_entries SET retention_until = ? WHERE id = ?",
            (_past().isoformat(), e.id),
        )
        store._conn.commit()
        count = store.purge_expired()
        assert count == 1
        assert store.stats()["deactivated"] == 1


# ── BS-17: Deaktivierungslogik ────────────────────────────────────────────────

class TestBS17Deaktivierung:
    def test_deactivate_entfernt_aus_list_active(self, store):
        e = store.add(_entry())
        store.deactivate(e.id)
        assert store.list_active(role="user") == []

    def test_deaktivierter_eintrag_nicht_abrufbar(self, store):
        e = store.add(_entry())
        store.deactivate(e.id)
        assert store.get(e.id, role="user") is None

    def test_deaktivierter_eintrag_bleibt_in_db(self, store):
        e = store.add(_entry())
        store.deactivate(e.id)
        assert store.stats()["total"] == 1
        assert store.stats()["deactivated"] == 1

    def test_doppelte_deaktivierung_idempotent(self, store):
        e = store.add(_entry())
        store.deactivate(e.id)
        result = store.deactivate(e.id)
        assert result is False  # zweiter Aufruf: nichts deaktiviert


# ── BS-18: Kein sensitiver Klartext ──────────────────────────────────────────

class TestBS18SensitiveDefault:
    def test_content_hash_kein_klartext(self, store):
        original = "IBAN DE89 3704 0044 0532 0130 00"
        e = store.add(_entry(content_hash=MemoryEntry.hash_content(original)))
        geladen = store.get(e.id, role="user")
        assert original not in geladen.content_hash
        assert len(geladen.content_hash) == 64

    def test_sensitive_true_ist_default_in_db(self, store):
        e = store.add(_entry())
        row = store._conn.execute(
            "SELECT sensitive FROM memory_entries WHERE id = ?", (e.id,)
        ).fetchone()
        assert row["sensitive"] == 1


# ── Statistik ─────────────────────────────────────────────────────────────────

class TestStats:
    def test_stats_korrekt_nach_operationen(self, store):
        e1 = store.add(_entry())
        e2 = store.add(_entry())
        store.deactivate(e1.id)
        s = store.stats()
        assert s["total"] == 2
        assert s["active"] == 1
        assert s["deactivated"] == 1
