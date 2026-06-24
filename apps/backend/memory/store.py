"""
AILIZA Memory Store
===================
In-Memory Store mit Zweckbindung, Ablauf und Soft-delete.

Absichtlich kein persistentes Backend in dieser Version —
das Memory-Backend (SQLite/DB) ist der nächste Schritt.
Diese Schicht definiert die Schnittstelle, die das Backend dann erfüllen muss.
"""

from __future__ import annotations

import threading
from datetime import datetime, timezone
from typing import Dict, List, Optional

from .models import MemoryEntry, MemoryPurpose, VisibilityLevel


class MemoryStore:
    """
    Thread-sicherer In-Memory Store für MemoryEntry-Objekte.

    Schnittstelle (wird später vom DB-Backend implementiert):
    - add()             Eintrag hinzufügen
    - get()             Eintrag abrufen (Sichtbarkeitsprüfung)
    - deactivate()      Soft-delete eines Eintrags
    - purge_expired()   Abgelaufene Einträge deaktivieren
    - list_active()     Alle aktiven, nicht abgelaufenen Einträge
    """

    def __init__(self) -> None:
        self._entries: Dict[str, MemoryEntry] = {}
        self._lock = threading.Lock()

    # ── Schreiben ─────────────────────────────────────────────────────────

    def add(self, entry: MemoryEntry) -> MemoryEntry:
        """
        Fügt einen neuen Eintrag hinzu.
        Wirft ValueError wenn id bereits existiert oder retention_until in der Vergangenheit liegt.
        """
        if entry.created_at > entry.retention_until:
            raise ValueError("retention_until muss in der Zukunft liegen")
        with self._lock:
            if entry.id in self._entries:
                raise ValueError(f"MemoryEntry {entry.id} existiert bereits")
            self._entries[entry.id] = entry
        return entry

    # ── Lesen ─────────────────────────────────────────────────────────────

    def get(self, entry_id: str, role: str) -> Optional[MemoryEntry]:
        """
        Gibt Eintrag zurück wenn aktiv, nicht abgelaufen und Rolle ausreichend.
        Gibt None zurück ohne Fehler — keine Informationsleckage über Existenz.
        """
        with self._lock:
            entry = self._entries.get(entry_id)
        if entry is None:
            return None
        if not entry.is_active():
            return None
        if entry.is_expired():
            return None
        if not entry.is_accessible_by(role):
            return None
        return entry

    def list_active(self, role: str, purpose: Optional[MemoryPurpose] = None) -> List[MemoryEntry]:
        """Alle aktiven, nicht abgelaufenen Einträge die Rolle sehen darf."""
        with self._lock:
            entries = list(self._entries.values())

        result = []
        for e in entries:
            if not e.is_active():
                continue
            if e.is_expired():
                continue
            if not e.is_accessible_by(role):
                continue
            if purpose is not None and e.purpose != purpose:
                continue
            result.append(e)
        return result

    # ── Deaktivieren / Bereinigen ─────────────────────────────────────────

    def deactivate(self, entry_id: str) -> bool:
        """
        Soft-delete eines Eintrags.
        Gibt True zurück wenn deaktiviert, False wenn nicht gefunden.
        """
        with self._lock:
            entry = self._entries.get(entry_id)
        if entry is None:
            return False
        entry.deactivate()
        return True

    def purge_expired(self) -> int:
        """
        Deaktiviert alle abgelaufenen Einträge (BS-16).
        Gibt Anzahl deaktivierter Einträge zurück.
        Kein Hard-delete — Einträge bleiben als deaktivierte Datensätze.
        """
        count = 0
        with self._lock:
            entries = list(self._entries.values())
        for entry in entries:
            if entry.is_active() and entry.is_expired():
                entry.deactivate()
                count += 1
        return count

    # ── Statistik ─────────────────────────────────────────────────────────

    def stats(self) -> dict:
        with self._lock:
            all_entries = list(self._entries.values())
        return {
            "total": len(all_entries),
            "active": sum(1 for e in all_entries if e.is_active() and not e.is_expired()),
            "expired": sum(1 for e in all_entries if e.is_expired()),
            "deactivated": sum(1 for e in all_entries if not e.is_active()),
        }
