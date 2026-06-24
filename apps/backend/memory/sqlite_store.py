"""
AILIZA Memory Store — SQLite-Backend
=====================================
Persistente Implementierung der MemoryStore-Schnittstelle.
Gleiche API wie store.py (In-Memory), aber dauerhaft in SQLite.

DSGVO Art. 5: Zweckbindung, Speicherbegrenzung
DSGVO Art. 25: Privacy by Design
"""

from __future__ import annotations

import sqlite3
import threading
from datetime import datetime, timezone
from typing import List, Optional

from .models import DataClass, MemoryEntry, MemoryPurpose, VisibilityLevel


class SqliteMemoryStore:
    """
    SQLite-backed MemoryStore.

    Gleiche Schnittstelle wie MemoryStore (In-Memory).
    Tauschbar: SqliteMemoryStore(db_path) statt MemoryStore().
    """

    def __init__(self, db_path: str = ":memory:") -> None:
        self._db_path = db_path
        self._lock = threading.Lock()
        self._conn = self._init_db()

    def _init_db(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS memory_entries (
                id               TEXT PRIMARY KEY,
                purpose          TEXT NOT NULL,
                data_class       TEXT NOT NULL,
                content_hash     TEXT NOT NULL,
                visibility       TEXT NOT NULL,
                role_required    TEXT NOT NULL,
                retention_until  TEXT NOT NULL,
                created_at       TEXT NOT NULL,
                deactivated_at   TEXT,
                sensitive        INTEGER NOT NULL DEFAULT 1
            );
            CREATE INDEX IF NOT EXISTS idx_purpose ON memory_entries(purpose);
            CREATE INDEX IF NOT EXISTS idx_deactivated ON memory_entries(deactivated_at);
        """)
        conn.commit()
        return conn

    # ── Konvertierung ─────────────────────────────────────────────────────

    @staticmethod
    def _to_row(e: MemoryEntry) -> tuple:
        return (
            e.id,
            e.purpose.value,
            e.data_class.value,
            e.content_hash,
            e.visibility.value,
            e.role_required,
            e.retention_until.isoformat(),
            e.created_at.isoformat(),
            e.deactivated_at.isoformat() if e.deactivated_at else None,
            int(e.sensitive),
        )

    @staticmethod
    def _from_row(row: sqlite3.Row) -> MemoryEntry:
        def _dt(s: str) -> datetime:
            dt = datetime.fromisoformat(s)
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)

        return MemoryEntry(
            id=row["id"],
            purpose=MemoryPurpose(row["purpose"]),
            data_class=DataClass(row["data_class"]),
            content_hash=row["content_hash"],
            visibility=VisibilityLevel(row["visibility"]),
            role_required=row["role_required"],
            retention_until=_dt(row["retention_until"]),
            created_at=_dt(row["created_at"]),
            deactivated_at=_dt(row["deactivated_at"]) if row["deactivated_at"] else None,
            sensitive=bool(row["sensitive"]),
        )

    # ── Schreiben ─────────────────────────────────────────────────────────

    def add(self, entry: MemoryEntry) -> MemoryEntry:
        if entry.created_at > entry.retention_until:
            raise ValueError("retention_until muss in der Zukunft liegen")
        with self._lock:
            try:
                self._conn.execute(
                    """INSERT INTO memory_entries
                       (id, purpose, data_class, content_hash, visibility,
                        role_required, retention_until, created_at, deactivated_at, sensitive)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    self._to_row(entry),
                )
                self._conn.commit()
            except sqlite3.IntegrityError:
                raise ValueError(f"MemoryEntry {entry.id} existiert bereits")
        return entry

    # ── Lesen ─────────────────────────────────────────────────────────────

    def get(self, entry_id: str, role: str) -> Optional[MemoryEntry]:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM memory_entries WHERE id = ?", (entry_id,)
            ).fetchone()
        if row is None:
            return None
        entry = self._from_row(row)
        if not entry.is_active():
            return None
        if entry.is_expired():
            return None
        if not entry.is_accessible_by(role):
            return None
        return entry

    def list_active(self, role: str, purpose: Optional[MemoryPurpose] = None) -> List[MemoryEntry]:
        with self._lock:
            if purpose:
                rows = self._conn.execute(
                    "SELECT * FROM memory_entries WHERE deactivated_at IS NULL AND purpose = ?",
                    (purpose.value,),
                ).fetchall()
            else:
                rows = self._conn.execute(
                    "SELECT * FROM memory_entries WHERE deactivated_at IS NULL"
                ).fetchall()

        result = []
        for row in rows:
            entry = self._from_row(row)
            if entry.is_expired():
                continue
            if not entry.is_accessible_by(role):
                continue
            result.append(entry)
        return result

    # ── Deaktivieren / Bereinigen ─────────────────────────────────────────

    def deactivate(self, entry_id: str) -> bool:
        now = datetime.now(timezone.utc).isoformat()
        with self._lock:
            cursor = self._conn.execute(
                """UPDATE memory_entries
                   SET deactivated_at = ?
                   WHERE id = ? AND deactivated_at IS NULL""",
                (now, entry_id),
            )
            self._conn.commit()
        return cursor.rowcount > 0

    def purge_expired(self) -> int:
        now = datetime.now(timezone.utc).isoformat()
        with self._lock:
            cursor = self._conn.execute(
                """UPDATE memory_entries
                   SET deactivated_at = ?
                   WHERE deactivated_at IS NULL AND retention_until < ?""",
                (now, now),
            )
            self._conn.commit()
        return cursor.rowcount

    # ── Statistik ─────────────────────────────────────────────────────────

    def stats(self) -> dict:
        now = datetime.now(timezone.utc).isoformat()
        with self._lock:
            total = self._conn.execute("SELECT COUNT(*) FROM memory_entries").fetchone()[0]
            deactivated = self._conn.execute(
                "SELECT COUNT(*) FROM memory_entries WHERE deactivated_at IS NOT NULL"
            ).fetchone()[0]
            expired = self._conn.execute(
                "SELECT COUNT(*) FROM memory_entries WHERE deactivated_at IS NULL AND retention_until < ?",
                (now,),
            ).fetchone()[0]
        return {
            "total": total,
            "active": total - deactivated - expired,
            "expired": expired,
            "deactivated": deactivated,
        }
