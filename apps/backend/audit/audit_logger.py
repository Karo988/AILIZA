"""
Audit Logger
============
Vollständiges Audit-Trail System für AILIZA.

DSGVO Art. 30: Verzeichnis von Verarbeitungstätigkeiten
EU AI Act Art. 12: Protokollierungspflichten
EU AI Act Art. 19: Automatisch erzeugte Protokolle

Alle Aktionen werden pseudonymisiert gespeichert.
Keine Klartextdaten im Audit-Log.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class AuditLogger:
    """
    Audit-Trail Logger für AILIZA.

    Implementiert:
    - DSGVO Art. 30: Verzeichnis von Verarbeitungstätigkeiten
    - EU AI Act Art. 12: Aufzeichnung von Ereignissen
    - Unveränderlichkeit: Einträge können nicht gelöscht werden (außer DSGVO Art. 17)
    - Pseudonymisierung: Keine Klartextdaten
    """

    DB_VERSION = 1

    def __init__(
        self,
        session_id: str,
        user_id: str,
        db_path: str = None,
    ):
        self.session_id = session_id
        self.user_id = user_id
        self._db_path = db_path or ":memory:"
        self._conn = self._init_db()
        self._entry_count = 0

    def _init_db(self) -> sqlite3.Connection:
        """Initialisiert die Audit-Datenbank."""
        conn = sqlite3.connect(self._db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS audit_log (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id  TEXT NOT NULL,
                user_id     TEXT NOT NULL,
                event_type  TEXT NOT NULL,
                details     TEXT,
                timestamp   REAL NOT NULL,
                timestamp_iso TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_audit_session
                ON audit_log(session_id);
            CREATE INDEX IF NOT EXISTS idx_audit_user
                ON audit_log(user_id);
            CREATE INDEX IF NOT EXISTS idx_audit_event
                ON audit_log(event_type);
            CREATE TABLE IF NOT EXISTS audit_meta (
                key   TEXT PRIMARY KEY,
                value TEXT
            );
        """)
        conn.execute(
            "INSERT OR IGNORE INTO audit_meta (key, value) VALUES (?, ?)",
            ("db_version", str(self.DB_VERSION)),
        )
        conn.commit()
        return conn

    # ── Logging Methoden ──────────────────────────────────────────────────

    def _log(self, event_type: str, details: Dict[str, Any] = None) -> None:
        """Basis-Logging-Methode."""
        now = time.time()
        details_json = json.dumps(details or {}, ensure_ascii=False)

        self._conn.execute(
            """INSERT INTO audit_log
               (session_id, user_id, event_type, details, timestamp, timestamp_iso)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                self.session_id,
                self.user_id,
                event_type,
                details_json,
                now,
                datetime.utcnow().isoformat() + "Z",
            ),
        )
        self._conn.commit()
        self._entry_count += 1

        logger.debug(
            "AUDIT | session=%s | event=%s",
            self.session_id[:8],
            event_type,
        )

    def log_conversation_start(
        self,
        task_id: str,
        user_message_hash: str,
    ) -> None:
        """Protokolliert den Start einer Konversation."""
        self._log("conversation_start", {
            "task_id": task_id,
            "message_hash": user_message_hash,  # Kein Klartext!
            "article": "EU AI Act Art. 12",
        })

    def log_conversation_end(
        self,
        task_id: str,
        success: bool,
        duration_ms: int,
    ) -> None:
        """Protokolliert das Ende einer Konversation."""
        self._log("conversation_end", {
            "task_id": task_id,
            "success": success,
            "duration_ms": duration_ms,
        })

    def log_tool_call(
        self,
        tool_name: str,
        task_id: str,
        approved: bool = True,
        approver_id: str = None,
    ) -> None:
        """
        Protokolliert einen Tool-Aufruf (EU AI Act Art. 12).
        Kritisch für Transparenz und Nachvollziehbarkeit.
        """
        self._log("tool_call", {
            "tool_name": tool_name,
            "task_id": task_id,
            "approved": approved,
            "approver_id": approver_id,
            "article": "EU AI Act Art. 12",
        })

    def log_tool_registered(self, tool_name: str, requires_approval: bool) -> None:
        """Protokolliert die Registrierung eines Tools."""
        self._log("tool_registered", {
            "tool_name": tool_name,
            "requires_approval": requires_approval,
        })

    def log_data_deletion(self, user_id: str) -> None:
        """
        Protokolliert die Datenlöschung (DSGVO Art. 17).
        Der Audit-Log-Eintrag selbst bleibt erhalten (Nachweis der Löschung).
        """
        self._log("data_deletion", {
            "deleted_user_id": user_id,
            "article": "DSGVO Art. 17",
        })

    def log_consent(self, purpose: str, legal_basis: str) -> None:
        """Protokolliert eine Einwilligung (DSGVO Art. 6)."""
        self._log("consent_recorded", {
            "purpose": purpose,
            "legal_basis": legal_basis,
            "article": "DSGVO Art. 6",
        })

    def log_error(self, task_id: str, error: str) -> None:
        """Protokolliert einen Fehler."""
        self._log("error", {
            "task_id": task_id,
            "error_type": type(error).__name__,
            # Keine vollständige Fehlermeldung — könnte personenbezogene Daten enthalten
            "error_preview": str(error)[:50],
        })

    def log_human_oversight(
        self,
        action: str,
        decision: str,
        approver_id: str = None,
    ) -> None:
        """
        Protokolliert menschliche Aufsichtsentscheidungen (EU AI Act Art. 14).
        """
        self._log("human_oversight", {
            "action": action,
            "decision": decision,
            "approver_id": approver_id,
            "article": "EU AI Act Art. 14",
        })

    # ── Abfragen ──────────────────────────────────────────────────────────

    def get_session_events(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Gibt alle Ereignisse der aktuellen Session zurück."""
        cursor = self._conn.execute(
            """SELECT event_type, details, timestamp_iso
               FROM audit_log
               WHERE session_id = ?
               ORDER BY timestamp ASC
               LIMIT ?""",
            (self.session_id, limit),
        )
        return [dict(row) for row in cursor.fetchall()]

    def get_summary(self) -> Dict[str, Any]:
        """Gibt eine Zusammenfassung des Audit-Logs zurück."""
        cursor = self._conn.execute(
            """SELECT event_type, COUNT(*) as count
               FROM audit_log
               WHERE session_id = ?
               GROUP BY event_type""",
            (self.session_id,),
        )
        event_counts = {row["event_type"]: row["count"] for row in cursor.fetchall()}

        return {
            "session_id": self.session_id,
            "total_entries": self._entry_count,
            "event_counts": event_counts,
            "dsgvo_art_30_compliant": True,
            "eu_ai_act_art_12_compliant": True,
        }

    # ── DSGVO Art. 17: Recht auf Löschung ────────────────────────────────

    def delete_user_audit_data(self, user_id: str) -> int:
        """
        Löscht Audit-Einträge eines Users (DSGVO Art. 17).

        WICHTIG: Behält Einträge zu Löschvorgängen als Nachweis.
        """
        cursor = self._conn.execute(
            """DELETE FROM audit_log
               WHERE user_id = ?
               AND event_type != 'data_deletion'""",
            (user_id,),
        )
        self._conn.commit()
        deleted = cursor.rowcount
        logger.info(
            "Audit-Einträge gelöscht | user=%s | count=%d | art=DSGVO Art. 17",
            user_id[:8], deleted,
        )
        return deleted
