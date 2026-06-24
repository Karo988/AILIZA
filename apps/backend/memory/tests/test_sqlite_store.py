"""
SQLite Memory Store Tests — BS-14 bis BS-18 auf persistentem Backend
Alle Tests mit db_path=":memory:" — kein Dateisystem nötig.
"""

import hashlib
import pytest
from datetime import datetime, timedelta, timezone

from ..models import MemoryEntry, MemoryPurpose, VisibilityLevel
from ..sqlite_store import SqliteMemoryStore


def _future(seconds: int = 3600) -> datetime:
    return datetime.now(timezone.utc) + timedelta(seconds=seconds)


def _past(seconds: int = 1) -> datetime:
    return datetime.now(timezone.utc) - timedelta(seconds=seconds)


def _entry(**kwargs) -> MemoryEntry:
    defaults = dict(
        purpose=MemoryPurpose.SESSION,
        content_hash=hashlib.sha256(b"test").hexdigest(),
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

class TestGrundfunktionen:
    def test_add_und_get(self, store):
        e = _entry()
        store.add(e)
        geladen = store.get(e.id)
        assert geladen is not None
        assert geladen.id == e.id

    def test_get_unbekannte_id(self, store):
        assert store.get("nicht-vorhanden") is None

    def test_retention_in_vergangenheit_abgelehnt(self, store):
        with pytest.raises(ValueError):
            store.add(_entry(retention_until=_past()))

    def test_sensitive_default_bleibt_erhalten(self, store):
        e = _entry()
        store.add(e)
        assert store.get(e.id).sensitive is True

    def test_abgelaufener_eintrag_nicht_in_list_active(self, store):
        e = _entry()
        store.add(e)
        store._conn.execute(
            "UPDATE memory_entries SET retention_until = ? WHERE id = ?",
            (_past().isoformat(), e.id),
        )
        store._conn.commit()
        assert store.get(e.id).is_expired() is True
        assert all(not en.is_expired() for en in store.list_active())


# ── BS-14: Zweckbindung ───────────────────────────────────────────────────────

class TestBS14Zweckbindung:
    def test_purpose_wird_korrekt_persistiert(self, store):
        e = _entry(purpose=MemoryPurpose.CONSENT)
        store.add(e)
        assert store.get(e.id).purpose == MemoryPurpose.CONSENT

    def test_alle_purposes_persistierbar(self, store):
        for p in MemoryPurpose:
            e = _entry(purpose=p)
            store.add(e)
            assert store.get(e.id).purpose == p


# ── BS-15: Sichtbarkeit / Rolle ───────────────────────────────────────────────

class TestBS15Sichtbarkeit:
    def test_visibility_und_role_persistiert(self, store):
        e = _entry(visibility=VisibilityLevel.OPERATOR, role_required="operator")
        store.add(e)
        geladen = store.get(e.id)
        assert geladen.visibility == VisibilityLevel.OPERATOR
        assert geladen.role_required == "operator"


# ── BS-16: Aufbewahrungsfrist ─────────────────────────────────────────────────

class TestBS16Aufbewahrungsfrist:
    def test_purge_expired_loescht_abgelaufene(self, store):
        e = _entry()
        store.add(e)
        store._conn.execute(
            "UPDATE memory_entries SET retention_until = ? WHERE id = ?",
            (_past().isoformat(), e.id),
        )
        store._conn.commit()
        count = store.purge_expired()
        assert count >= 1
        assert store.get(e.id) is None

    def test_aktiver_eintrag_nicht_geloescht(self, store):
        e = _entry()
        store.add(e)
        store.purge_expired()
        assert store.get(e.id) is not None


# ── BS-17: Deaktivierung ─────────────────────────────────────────────────────

class TestBS17Deaktivierung:
    def test_deactivate_entfernt_aus_list_active(self, store):
        e = _entry()
        store.add(e)
        store.deactivate(e.id)
        assert all(en.id != e.id for en in store.list_active())

    def test_deaktivierter_eintrag_abrufbar_via_get(self, store):
        e = _entry()
        store.add(e)
        store.deactivate(e.id)
        geladen = store.get(e.id)
        assert geladen is not None
        assert geladen.is_active() is False

    def test_doppelte_deaktivierung_idempotent(self, store):
        e = _entry()
        store.add(e)
        store.deactivate(e.id)
        result = store.deactivate(e.id)
        assert result is False

    def test_close_schliesst_verbindung(self):
        s = SqliteMemoryStore(db_path=":memory:")
        s.close()


# ── BS-18: Kein sensitiver Klartext ──────────────────────────────────────────

class TestBS18SensitiveDefault:
    def test_sensitive_true_in_db(self, store):
        e = _entry()
        store.add(e)
        row = store._conn.execute(
            "SELECT sensitive FROM memory_entries WHERE id = ?", (e.id,)
        ).fetchone()
        assert row[0] == 1

    def test_content_hash_kein_klartext(self, store):
        original = "IBAN DE89 3704 0044"
        h = hashlib.sha256(original.encode()).hexdigest()
        e = _entry(content_hash=h)
        store.add(e)
        assert original not in store.get(e.id).content_hash
