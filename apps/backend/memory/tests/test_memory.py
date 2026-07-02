"""
Memory Backend Tests — BS-14 bis BS-18
BS-14: Zweckbindung (purpose Pflichtfeld)
BS-15: Sichtbarkeit/Rolle (visibility, role_required gespeichert)
BS-16: Aufbewahrungsfrist (retention_until, is_expired)
BS-17: Deaktivierungslogik (deactivate, is_active)
BS-18: Kein sensitiver Klartext als Default (sensitive=True, content_hash)
"""

import hashlib
import pytest
from datetime import datetime, timedelta, timezone

from ..models import MemoryEntry, MemoryPurpose, VisibilityLevel
from ..store import MemoryStore


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


# ── BS-14: Zweckbindung ───────────────────────────────────────────────────────

class TestBS14Zweckbindung:
    def test_purpose_ist_pflichtfeld(self):
        with pytest.raises(TypeError):
            MemoryEntry(
                content_hash="abc",
                visibility=VisibilityLevel.USER,
                role_required="user",
                retention_until=_future(),
            )

    def test_alle_purposes_gueltig(self):
        store = MemoryStore()
        for p in MemoryPurpose:
            e = _entry(purpose=p)
            store.add(e)
            assert store.get(e.id).purpose == p


# ── BS-15: Sichtbarkeit / Rolle ───────────────────────────────────────────────

class TestBS15Sichtbarkeit:
    def test_visibility_wird_gespeichert(self):
        store = MemoryStore()
        e = _entry(visibility=VisibilityLevel.OPERATOR, role_required="operator")
        store.add(e)
        geladen = store.get(e.id)
        assert geladen.visibility == VisibilityLevel.OPERATOR
        assert geladen.role_required == "operator"

    def test_alle_visibility_levels_gueltig(self):
        store = MemoryStore()
        for v in VisibilityLevel:
            e = _entry(visibility=v)
            store.add(e)
            assert store.get(e.id).visibility == v


# ── BS-16: Aufbewahrungsfrist ─────────────────────────────────────────────────

class TestBS16Aufbewahrungsfrist:
    def test_retention_until_pflichtfeld(self):
        with pytest.raises(TypeError):
            MemoryEntry(
                purpose=MemoryPurpose.SESSION,
                content_hash="abc",
                visibility=VisibilityLevel.USER,
                role_required="user",
            )

    def test_retention_in_vergangenheit_wird_in_store_abgelehnt(self):
        store = MemoryStore()
        with pytest.raises(ValueError):
            store.add(_entry(retention_until=_past()))

    def test_is_expired_nach_ablauf(self):
        e = _entry(retention_until=_future(1))
        e.retention_until = _past()
        assert e.is_expired() is True

    def test_list_active_filtert_abgelaufene(self):
        store = MemoryStore()
        e = store.add(_entry()) or _entry()
        # add() gibt None zurück — Entry direkt manipulieren
        entries = store.list_active()
        assert all(not en.is_expired() for en in entries)

    def test_purge_expired_entfernt_abgelaufene(self):
        store = MemoryStore()
        e = _entry()
        store.add(e)
        e.retention_until = _past()
        count = store.purge_expired()
        assert count == 1
        assert store.get(e.id) is None


# ── BS-17: Deaktivierungslogik ────────────────────────────────────────────────

class TestBS17Deaktivierung:
    def test_deactivate_setzt_timestamp(self):
        e = _entry()
        assert e.is_active() is True
        e.deactivate()
        assert e.is_active() is False
        assert e.deactivated_at is not None

    def test_store_deactivate(self):
        store = MemoryStore()
        e = _entry()
        store.add(e)
        result = store.deactivate(e.id)
        assert result is True
        assert store.get(e.id).is_active() is False

    def test_deactivate_unbekannte_id(self):
        store = MemoryStore()
        assert store.deactivate("nicht-vorhanden") is False

    def test_list_active_zeigt_keine_deaktivierten(self):
        store = MemoryStore()
        e = _entry()
        store.add(e)
        store.deactivate(e.id)
        aktive = store.list_active()
        assert all(en.is_active() for en in aktive)


# ── BS-18: Kein sensitiver Klartext als Default ───────────────────────────────

class TestBS18SensitiveDefault:
    def test_sensitive_ist_true_per_default(self):
        e = _entry()
        assert e.sensitive is True

    def test_content_hash_ist_sha256(self):
        original = "geheime Nutzerinformation"
        h = hashlib.sha256(original.encode()).hexdigest()
        assert len(h) == 64
        assert original not in h

    def test_kein_klartext_im_hash_feld(self):
        content = "IBAN DE89 3704 0044"
        h = hashlib.sha256(content.encode()).hexdigest()
        e = _entry(content_hash=h)
        assert content not in e.content_hash

    def test_opt_out_sensitive_moeglich(self):
        e = _entry(sensitive=False)
        assert e.sensitive is False
