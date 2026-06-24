from datetime import datetime, timezone
from typing import Optional
from .models import MemoryEntry

class MemoryStore:
    """In-Memory-Store — für Tests und lokale Entwicklung."""

    def __init__(self):
        self._entries: dict[str, MemoryEntry] = {}

    def add(self, entry: MemoryEntry) -> None:
        # Zukunftsprüfung hier — nicht im Modell
        if entry.retention_until <= datetime.now(timezone.utc):
            raise ValueError(
                f"retention_until muss in der Zukunft liegen: {entry.retention_until}"
            )
        self._entries[entry.id] = entry

    def get(self, entry_id: str) -> Optional[MemoryEntry]:
        return self._entries.get(entry_id)

    def list_active(self) -> list[MemoryEntry]:
        return [
            e for e in self._entries.values()
            if e.is_active() and not e.is_expired()
        ]

    def deactivate(self, entry_id: str) -> bool:
        entry = self._entries.get(entry_id)
        if entry is None:
            return False
        entry.deactivate()
        return True

    def purge_expired(self) -> int:
        expired = [
            eid for eid, e in self._entries.items()
            if e.is_expired() or not e.is_active()
        ]
        for eid in expired:
            del self._entries[eid]
        return len(expired)
