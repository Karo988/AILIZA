"""
Memory Backend Tests — BS-14 bis BS-18 Basis
=============================================
BS-14: Zweckbindung je Memory-Eintrag
BS-15: Sichtbarkeit/Rolle
BS-16: Aufbewahrungsfrist und Ablauf
BS-17: Lösch-/Deaktivierungslogik (Soft-delete)
BS-18: Keine Vollspeicherung sensibler Inhalte als Default
"""

import pytest
from datetime import datetime, timedelta, timezone

from ..models import DataClass, MemoryEntry, MemoryPurpose, VisibilityLevel
from ..store import MemoryStore


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


# ── BS-14: Zweckbindung ───────────────────────────────────────────────────────

class TestBS14Zweckbindung:
    def test_purpose_ist_pflichtfeld(self):
        """Eintrag ohne Purpose ist nicht erstellbar."""
        with pytest.raises(TypeError):
            MemoryEntry(
                content_hash="abc",
                visibility=VisibilityLevel.USER,
                role_required="user",
                retention_until=_future(),
            )

    def test_alle_purposes_sind_gueltig(self):
        for purpose in MemoryPurpose:
            e = _entry(purpose=purpose)
            assert e.purpose == purpose

    def test_store_filtert_nach_purpose(self):
        store = MemoryStore()
        store.add(_entry(purpose=MemoryPurpose.TASK))
        store.add(_entry(purpose=MemoryPurpose.CONSENT))

        tasks = store.list_active(role="user", purpose=MemoryPurpose.TASK)
        assert len(tasks) == 1
        assert tasks[0].purpose == MemoryPurpose.TASK


# ── BS-15: Sichtbarkeit / Rolle ───────────────────────────────────────────────

class TestBS15Sichtbarkeit:
    def test_user_sieht_user_eintraege(self):
        e = _entry(visibility=VisibilityLevel.USER, role_required="user")
        assert e.is_accessible_by("user") is True

    def test_user_sieht_keine_operator_eintraege(self):
        e = _entry(visibility=VisibilityLevel.OPERATOR)
        assert e.is_accessible_by("user") is False

    def test_user_sieht_keine_system_eintraege(self):
        e = _entry(visibility=VisibilityLevel.SYSTEM)
        assert e.is_accessible_by("user") is False

    def test_admin_sieht_alles(self):
        for level in VisibilityLevel:
            e = _entry(visibility=level)
            assert e.is_accessible_by("admin") is True

    def test_store_get_respektiert_rolle(self):
        store = MemoryStore()
        e = store.add(_entry(visibility=VisibilityLevel.OPERATOR))

        assert store.get(e.id, role="user") is None
        assert store.get(e.id, role="operator") is not None


# ── BS-16: Aufbewahrungsfrist ─────────────────────────────────────────────────

class TestBS16Aufbewahrungsfrist:
    def test_retention_until_ist_pflichtfeld(self):
        with pytest.raises(TypeError):
            MemoryEntry(
                purpose=MemoryPurpose.SESSION,
                content_hash="abc",
                visibility=VisibilityLevel.USER,
                role_required="user",
            )

    def test_retention_in_vergangenheit_wird_abgelehnt(self):
        """Zukunftsprüfung liegt im Store, nicht im Modell."""
        store = MemoryStore()
        with pytest.raises(ValueError):
            store.add(_entry(retention_until=_past()))

    def test_abgelaufener_eintrag_ist_nicht_abrufbar(self):
        store = MemoryStore()
        e = _entry(retention_until=_future(1))
        store.add(e)
        # Ablauf simulieren: retention_until manuell überschreiben
        e.retention_until = _past()

        assert store.get(e.id, role="user") is None

    def test_purge_expired_deaktiviert_abgelaufene(self):
        store = MemoryStore()
        e = store.add(_entry())
        e.retention_until = _past()  # Ablauf simulieren

        count = store.purge_expired()
        assert count == 1
        assert not e.is_active()


# ── BS-17: Lösch-/Deaktivierungslogik ────────────────────────────────────────

class TestBS17Deaktivierung:
    def test_deactivate_setzt_timestamp(self):
        e = _entry()
        assert e.deactivated_at is None
        e.deactivate()
        assert e.deactivated_at is not None

    def test_doppelte_deaktivierung_ist_idempotent(self):
        e = _entry()
        e.deactivate()
        ts1 = e.deactivated_at
        e.deactivate()
        assert e.deactivated_at == ts1  # kein zweiter Timestamp

    def test_deaktivierter_eintrag_ist_nicht_abrufbar(self):
        store = MemoryStore()
        e = store.add(_entry())
        store.deactivate(e.id)
        assert store.get(e.id, role="user") is None

    def test_deaktivierter_eintrag_bleibt_im_store(self):
        """Soft-delete — kein Hard-delete (für Audit-Nachweis)."""
        store = MemoryStore()
        e = store.add(_entry())
        store.deactivate(e.id)
        stats = store.stats()
        assert stats["total"] == 1
        assert stats["deactivated"] == 1


# ── BS-18: Keine Vollspeicherung sensibler Inhalte ────────────────────────────

class TestBS18SensitiveDefault:
    def test_sensitive_ist_true_per_default(self):
        e = _entry()
        assert e.sensitive is True

    def test_content_hash_ist_sha256(self):
        original = "geheime Nutzerinformation"
        h = MemoryEntry.hash_content(original)
        assert len(h) == 64           # SHA-256 = 64 hex chars
        assert original not in h      # Klartext nie im Hash

    def test_kein_klartext_im_pflichtfeld(self):
        """content_hash-Feld enthält niemals den Originalinhalt."""
        content = "sensible Daten: IBAN DE89..."
        e = _entry(content_hash=MemoryEntry.hash_content(content))
        assert content not in e.content_hash
        assert len(e.content_hash) == 64

    def test_opt_out_von_sensitive_moeglich(self):
        """Nicht-sensitive Einträge sind explizit möglich (Opt-out)."""
        e = _entry(sensitive=False)
        assert e.sensitive is False


# ── DataClass: Sicherheitsklassifizierung ─────────────────────────────────────

class TestDataClass:
    def test_default_ist_confidential(self):
        """Sicherer Default — kein versehentliches PUBLIC."""
        e = _entry()
        assert e.data_class == DataClass.CONFIDENTIAL

    def test_alle_data_classes_setzbar(self):
        for dc in DataClass:
            e = _entry(data_class=dc)
            assert e.data_class == dc

    def test_nur_public_erlaubt_klartext(self):
        assert DataClass.PUBLIC.allows_plaintext_storage() is True
        assert DataClass.INTERNAL.allows_plaintext_storage() is False
        assert DataClass.CONFIDENTIAL.allows_plaintext_storage() is False
        assert DataClass.RESTRICTED.allows_plaintext_storage() is False

    def test_confidential_und_restricted_erfordern_hash(self):
        assert DataClass.CONFIDENTIAL.requires_hash_only() is True
        assert DataClass.RESTRICTED.requires_hash_only() is True
        assert DataClass.PUBLIC.requires_hash_only() is False
        assert DataClass.INTERNAL.requires_hash_only() is False

    def test_restricted_eintrag_hat_sensitive_true(self):
        """RESTRICTED impliziert immer sensitive=True — kein Widerspruch möglich."""
        e = _entry(data_class=DataClass.RESTRICTED)
        assert e.sensitive is True

    def test_store_filtert_nach_data_class(self):
        store = MemoryStore()
        store.add(_entry(data_class=DataClass.PUBLIC))
        store.add(_entry(data_class=DataClass.RESTRICTED))

        alle = store.list_active(role="user")
        assert len(alle) == 2
        klassen = {e.data_class for e in alle}
        assert DataClass.PUBLIC in klassen
        assert DataClass.RESTRICTED in klassen
