"""
AILIZA Retention-Cleanup-Job
=============================
Loescht abgelaufene Eintraege aus allen Tabellen mit expires_at.

Kann aufgerufen werden als:
  - Hintergrund-Task beim Start (lifespan)
  - Scheduled via cron / APScheduler
  - Manuell ueber Admin-Endpoint POST /admin/cleanup

DSGVO Art. 5 Abs. 1 lit. e: Speicherbegrenzung.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import text

logger = logging.getLogger(__name__)


def run_cleanup() -> dict[str, Any]:
    """
    Loescht alle Eintraege deren expires_at in der Vergangenheit liegt.
    Gibt Anzahl geloeschter Zeilen je Tabelle zurueck.
    """
    try:
        from ..database import engine
    except ImportError:
        from database import engine

    now_iso = datetime.now(timezone.utc).isoformat()
    results: dict[str, int] = {}

    # Tabellen mit expires_at
    tables_with_expiry = [
        "security_logs",
        "performance_logs",
        "cost_logs",
        "reflection_facts",
    ]

    with engine.begin() as conn:
        for table in tables_with_expiry:
            try:
                result = conn.execute(
                    text(f"DELETE FROM {table} WHERE expires_at IS NOT NULL AND expires_at < :now"),  # noqa: S608
                    {"now": now_iso},
                )
                deleted = result.rowcount
                results[table] = deleted
                if deleted > 0:
                    logger.info("Retention-Cleanup: %s — %d Eintraege geloescht", table, deleted)
            except Exception as exc:
                logger.warning("Retention-Cleanup fuer %s fehlgeschlagen: %s", table, exc)
                results[table] = -1

    total = sum(v for v in results.values() if v >= 0)
    logger.info("Retention-Cleanup abgeschlossen. Gesamt: %d Eintraege geloescht.", total)
    return {"deleted_by_table": results, "total_deleted": total, "run_at": now_iso}
