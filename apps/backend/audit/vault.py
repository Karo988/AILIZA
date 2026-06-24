"""
AILIZA Audit-Vault
==================
EU AI Act Art. 12: Aufzeichnungspflichten
DSGVO Art. 30: Verzeichnis von Verarbeitungstätigkeiten

Unterschied zu audit_logger.py:
- audit_logger: operativer Log mit Details (bestehend, bleibt unverändert)
- vault: manipulationssichere Hash-Kette für Entscheidungs- und Freigabemetadaten

Vault-Prinzipien:
- Kein content — nur event_type, actor_id, timestamp, previous_hash
- Write-once: Einträge werden niemals editiert oder gelöscht
- Hash-Kette: jeder Eintrag enthält den Hash des Vorgängers
- Manipulationsprüfung: verify_chain() traversiert die gesamte Kette
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional


_GENESIS_HASH = "0" * 64  # Startwert der Hash-Kette


def _compute_hash(previous_hash: str, event_type: str, timestamp_iso: str, actor_id: str) -> str:
    """SHA-256 über die vier unveränderlichen Felder eines Vault-Eintrags."""
    payload = f"{previous_hash}|{event_type}|{timestamp_iso}|{actor_id}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class VaultEntry:
    __slots__ = ("sequence", "event_type", "timestamp_iso", "actor_id", "previous_hash", "entry_hash")

    def __init__(
        self,
        sequence: int,
        event_type: str,
        timestamp_iso: str,
        actor_id: str,
        previous_hash: str,
        entry_hash: str,
    ) -> None:
        self.sequence = sequence
        self.event_type = event_type
        self.timestamp_iso = timestamp_iso
        self.actor_id = actor_id
        self.previous_hash = previous_hash
        self.entry_hash = entry_hash

    def to_dict(self) -> dict:
        return {
            "sequence": self.sequence,
            "event_type": self.event_type,
            "timestamp_iso": self.timestamp_iso,
            "actor_id": self.actor_id,
            "previous_hash": self.previous_hash,
            "entry_hash": self.entry_hash,
        }


class AuditVault:
    """
    Manipulationssicherer Audit-Vault mit Hash-Kette.

    Nur Entscheidungs- und Freigabemetadaten — kein Inhalt.
    """

    def __init__(self, db_path: Optional[str] = None) -> None:
        self._db_path = db_path or ":memory:"
        self._lock = threading.Lock()
        self._conn = self._init_db()

    def _init_db(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS vault (
                sequence        INTEGER PRIMARY KEY AUTOINCREMENT,
                event_type      TEXT NOT NULL,
                timestamp_iso   TEXT NOT NULL,
                actor_id        TEXT NOT NULL,
                previous_hash   TEXT NOT NULL,
                entry_hash      TEXT NOT NULL
            );
        """)
        conn.commit()
        return conn

    def _last_hash(self) -> str:
        row = self._conn.execute(
            "SELECT entry_hash FROM vault ORDER BY sequence DESC LIMIT 1"
        ).fetchone()
        return row["entry_hash"] if row else _GENESIS_HASH

    # ── Schreiben (write-once) ────────────────────────────────────────────

    def record(self, event_type: str, actor_id: str) -> VaultEntry:
        """
        Fügt einen neuen Vault-Eintrag an — write-once, keine Updates.

        event_type: z.B. MEMORY_DEACTIVATED, CONSENT_GRANTED, APPROVAL_GIVEN
        actor_id:   anonymisierte Nutzer- oder System-ID
        """
        with self._lock:
            previous_hash = self._last_hash()
            timestamp_iso = datetime.now(timezone.utc).isoformat()
            entry_hash = _compute_hash(previous_hash, event_type, timestamp_iso, actor_id)

            cursor = self._conn.execute(
                """INSERT INTO vault (event_type, timestamp_iso, actor_id, previous_hash, entry_hash)
                   VALUES (?, ?, ?, ?, ?)""",
                (event_type, timestamp_iso, actor_id, previous_hash, entry_hash),
            )
            self._conn.commit()
            sequence = cursor.lastrowid

        return VaultEntry(sequence, event_type, timestamp_iso, actor_id, previous_hash, entry_hash)

    # ── Lesen ─────────────────────────────────────────────────────────────

    def get_entries(self, limit: int = 100, offset: int = 0) -> List[VaultEntry]:
        rows = self._conn.execute(
            "SELECT * FROM vault ORDER BY sequence ASC LIMIT ? OFFSET ?",
            (limit, offset),
        ).fetchall()
        return [VaultEntry(**dict(r)) for r in rows]

    # ── Manipulationsprüfung ──────────────────────────────────────────────

    def verify_chain(self) -> tuple[bool, Optional[int]]:
        """
        Traversiert die gesamte Hash-Kette.

        Gibt (True, None) zurück wenn integer.
        Gibt (False, sequence) zurück beim ersten defekten Eintrag.
        """
        rows = self._conn.execute(
            "SELECT * FROM vault ORDER BY sequence ASC"
        ).fetchall()

        previous_hash = _GENESIS_HASH
        for row in rows:
            # Prüfung 1: gespeichertes previous_hash stimmt mit laufender Kette überein
            if row["previous_hash"] != previous_hash:
                return False, row["sequence"]

            # Prüfung 2: entry_hash ist korrekt aus den vier Feldern berechnet
            expected = _compute_hash(
                previous_hash,
                row["event_type"],
                row["timestamp_iso"],
                row["actor_id"],
            )
            if expected != row["entry_hash"]:
                return False, row["sequence"]

            previous_hash = row["entry_hash"]

        return True, None

    # ── Export ────────────────────────────────────────────────────────────

    def export(self, limit: int = 1000) -> List[dict]:
        """Export aller Vault-Einträge als JSON-serialisierbares Format."""
        return [e.to_dict() for e in self.get_entries(limit=limit)]

    def stats(self) -> dict:
        row = self._conn.execute("SELECT COUNT(*) as n FROM vault").fetchone()
        intact, defect_at = self.verify_chain()
        return {
            "total_entries": row["n"],
            "chain_intact": intact,
            "first_defect_at_sequence": defect_at,
        }
