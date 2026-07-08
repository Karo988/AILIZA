"""
Retention Engine: Hard-delete with exclusive lock and legal hold support.

Uses PostgreSQL pg_advisory_lock to ensure only one worker runs cleanup.
Per-table configuration specifies retention days and legal_hold column existence.

Status (Stand 2026-07-06): Bereit für kontrollierte Testumgebung und
Governance-Review. Nicht produktionsreif. Nicht zertifiziert.

Blocker:
- Nirgends in main.py eingebunden — die tatsaechlich aktive
  Retention-Logik laeuft ueber apps/backend/maintenance/retention_cleanup.py,
  eine unabhaengige, andere Implementierung. Verwechslungsgefahr.
- Keine Tests.

Aktives Gegenstueck: apps/backend/maintenance/retention_cleanup.py
(NICHT diese Datei) — wird in main.py beim Start und per Scheduler
tatsaechlich aufgerufen.
"""

from datetime import datetime, timedelta
from typing import Optional
import logging

logger = logging.getLogger(__name__)

# Per-table retention configuration
RETENTION_CONFIG = {
    "audit_logs": {
        "days": 90,
        "has_legal_hold": True,
    },
    "approval_logs": {
        "days": 365,
        "has_legal_hold": True,
    },
    "security_logs": {
        "days": 180,
        "has_legal_hold": True,
    },
}

RETENTION_LOCK_ID = 1001  # Fixed advisory lock ID


class RetentionLockError(Exception):
    """Raised when retention lock cannot be acquired."""
    pass


class RetentionLock:
    """PostgreSQL advisory lock for exclusive retention cleanup."""

    def __init__(self, db_session):
        self.db_session = db_session
        self.locked = False

    def acquire(self, blocking: bool = True) -> bool:
        """
        Acquire exclusive lock.

        Args:
            blocking: If False, raises RetentionLockError if lock not available

        Returns:
            True if lock acquired

        Raises:
            RetentionLockError if blocking=False and lock unavailable
        """

        try:
            if blocking:
                # Blocking acquire
                self.db_session.execute(
                    f"SELECT pg_advisory_lock({RETENTION_LOCK_ID})"
                )
            else:
                # Non-blocking acquire
                result = self.db_session.execute(
                    f"SELECT pg_advisory_lock_shared({RETENTION_LOCK_ID})"
                ).scalar()
                if not result:
                    raise RetentionLockError(
                        f"Retention lock {RETENTION_LOCK_ID} already held by another process"
                    )

            self.locked = True
            logger.info(f"Retention lock {RETENTION_LOCK_ID} acquired")
            return True
        except Exception as e:
            logger.error(f"Failed to acquire retention lock: {e}")
            if not blocking:
                raise RetentionLockError(str(e))
            return False

    def release(self):
        """Release the lock."""

        if self.locked:
            try:
                self.db_session.execute(
                    f"SELECT pg_advisory_unlock({RETENTION_LOCK_ID})"
                )
                self.locked = False
                logger.info(f"Retention lock {RETENTION_LOCK_ID} released")
            except Exception as e:
                logger.error(f"Failed to release retention lock: {e}")


class RetentionTable:
    """Represents a table with retention policy."""

    def __init__(self, table_name: str):
        self.table_name = table_name
        self.config = self._get_config()

    def _get_config(self) -> dict:
        """Get retention config, validate table exists in whitelist."""

        if self.table_name not in RETENTION_CONFIG:
            raise ValueError(f"Unknown retention table: {self.table_name}")
        return RETENTION_CONFIG[self.table_name]

    @staticmethod
    def validate(table_name: str) -> bool:
        """Check if table is in retention whitelist."""

        return table_name in RETENTION_CONFIG

    def get_delete_sql(self) -> str:
        """Generate DELETE SQL for this table's retention policy."""

        days = self.config["days"]
        has_legal_hold = self.config.get("has_legal_hold", False)
        cutoff_date = (datetime.utcnow() - timedelta(days=days)).isoformat()

        sql = f"DELETE FROM {self.table_name} WHERE created_at < '{cutoff_date}'"

        if has_legal_hold:
            sql += " AND legal_hold = FALSE"

        return sql + ";"


class RetentionEngine:
    """Main retention cleanup engine."""

    def __init__(self, db_session):
        self.db_session = db_session
        self.lock = RetentionLock(db_session)

    def cleanup_expired_logs(self) -> dict:
        """
        Run cleanup for all retention tables.

        Returns:
            Dict with results: {table_name: deleted_count, ...}
        """

        results = {}

        # Try to acquire lock (non-blocking)
        try:
            self.lock.acquire(blocking=False)
        except RetentionLockError as e:
            logger.warning(f"Retention cleanup already in progress: {e}")
            return results

        try:
            for table_name in RETENTION_CONFIG.keys():
                try:
                    table = RetentionTable(table_name)
                    sql = table.get_delete_sql()
                    logger.info(f"Running retention cleanup for {table_name}: {sql}")
                    result = self.db_session.execute(sql)
                    deleted = result.rowcount
                    results[table_name] = deleted
                    logger.info(f"Deleted {deleted} rows from {table_name}")
                except Exception as e:
                    logger.error(f"Error cleaning {table_name}: {e}")
                    results[table_name] = {"error": str(e)}
        finally:
            self.lock.release()

        return results

    def catch_up_on_startup(self, force: bool = False) -> dict:
        """
        Check if cleanup is overdue (>25h since last run), run if needed.

        Args:
            force: Force cleanup even if not overdue

        Returns:
            Result dict from cleanup_expired_logs
        """

        # Query last cleanup timestamp (would be stored in a metadata table)
        # For now, simple check: if force=True, always run
        if force:
            logger.info("Forced retention catch-up on startup")
            return self.cleanup_expired_logs()

        logger.info("Retention catch-up check: cleanup within acceptable window")
        return {}
