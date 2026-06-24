import sqlite3
from datetime import datetime, timezone
from typing import Optional
from .models import MemoryEntry, MemoryPurpose, VisibilityLevel

class SqliteMemoryStore:
    """SQLite-Backend — gleiche Schnittstelle wie MemoryStore."""

    def __init__(self, db_path: str = "data/ailiza_memory.db"):
        self.db_path = db_path
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._init_schema()

    def _init_schema(self) -> None:
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS memory_entries (
                id TEXT PRIMARY KEY,
                purpose TEXT NOT NULL,
                content_hash TEXT NOT NULL,
                visibility TEXT NOT NULL,
                role_required TEXT NOT NULL,
                retention_until TEXT NOT NULL,
                created_at TEXT NOT NULL,
                deactivated_at TEXT,
                sensitive INTEGER NOT NULL DEFAULT 1
            )
        """)
        self._conn.commit()

    def _row_to_entry(self, row: tuple) -> MemoryEntry:
        """Lädt einen Eintrag aus der DB — keine Zukunftsprüfung."""
        (id_, purpose, content_hash, visibility, role_required,
         retention_until, created_at, deactivated_at, sensitive) = row
        return MemoryEntry(
            id=id_,
            purpose=MemoryPurpose(purpose),
            content_hash=content_hash,
            visibility=VisibilityLevel(visibility),
            role_required=role_required,
            retention_until=datetime.fromisoformat(retention_until),
            created_at=datetime.fromisoformat(created_at),
            deactivated_at=(
                datetime.fromisoformat(deactivated_at)
                if deactivated_at else None
            ),
            sensitive=bool(sensitive),
        )

    def add(self, entry: MemoryEntry) -> None:
        # Zukunftsprüfung hier — konsistent mit MemoryStore
        if entry.retention_until <= datetime.now(timezone.utc):
            raise ValueError(
                f"retention_until muss in der Zukunft liegen: {entry.retention_until}"
            )
        self._conn.execute("""
            INSERT INTO memory_entries
            (id, purpose, content_hash, visibility, role_required,
             retention_until, created_at, deactivated_at, sensitive)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            entry.id,
            entry.purpose.value,
            entry.content_hash,
            entry.visibility.value,
            entry.role_required,
            entry.retention_until.isoformat(),
            entry.created_at.isoformat(),
            entry.deactivated_at.isoformat() if entry.deactivated_at else None,
            int(entry.sensitive),
        ))
        self._conn.commit()

    def get(self, entry_id: str) -> Optional[MemoryEntry]:
        cur = self._conn.execute(
            "SELECT * FROM memory_entries WHERE id = ?", (entry_id,)
        )
        row = cur.fetchone()
        return self._row_to_entry(row) if row else None

    def list_active(self) -> list[MemoryEntry]:
        cur = self._conn.execute(
            "SELECT * FROM memory_entries WHERE deactivated_at IS NULL"
        )
        now = datetime.now(timezone.utc)
        return [
            e for e in (self._row_to_entry(r) for r in cur.fetchall())
            if not e.is_expired()
        ]

    def deactivate(self, entry_id: str) -> bool:
        now = datetime.now(timezone.utc).isoformat()
        cur = self._conn.execute("""
            UPDATE memory_entries
            SET deactivated_at = ?
            WHERE id = ? AND deactivated_at IS NULL
        """, (now, entry_id))
        self._conn.commit()
        return cur.rowcount > 0

    def purge_expired(self) -> int:
        now = datetime.now(timezone.utc).isoformat()
        cur = self._conn.execute("""
            DELETE FROM memory_entries
            WHERE retention_until <= ? OR deactivated_at IS NOT NULL
        """, (now,))
        self._conn.commit()
        return cur.rowcount

    def close(self) -> None:
        self._conn.close()
