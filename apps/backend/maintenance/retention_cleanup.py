"""
AILIZA Retention-Cleanup-Job
=============================
Loescht abgelaufene Eintraege (expires_at) und setzt Pflicht-Retentionsfristen
fuer Daten die kein eigenes expires_at-Feld haben.

DSGVO Art. 5 Abs. 1 lit. e: Speicherbegrenzung — nur so lange wie noetig.

Retentionsfristen (DSGVO-konform, konfigurierbar via Env):
  AILIZA_RETAIN_AUDIT_DAYS         =  90  (Audit-Log — Login, Admin-Aktionen)
  AILIZA_RETAIN_SECURITY_DAYS      = 180  (Security-Incidents — laenger fuer Nachweispflicht)
  AILIZA_RETAIN_PERFORMANCE_DAYS   =  30  (Performance-Logs — kein Personenbezug)
  AILIZA_RETAIN_COST_DAYS          =  30  (Cost-Logs — kein Personenbezug)
  AILIZA_RETAIN_REFLECTION_DAYS    =  90  (Memory/Reflection-Facts — opt-in)
  AILIZA_RETAIN_TOTP_BACKUP_DAYS   = 365  (genutzte Backup-Codes — fuer Audit-Nachweis)
  AILIZA_RETAIN_MESSENGER_INACTIVE_DAYS = 365  (inaktive Telegram-Bindings)
  AILIZA_RETAIN_APPROVAL_DAYS          =  90  (Approval-Records — inkl. Rollenentscheid)
  AILIZA_RETAIN_AGENT_RUNS_DAYS        =  30  (Agent-Run-Metadaten)

Kann aufgerufen werden als:
  - Hintergrund-Task beim Start (lifespan)
  - Scheduled via APScheduler
  - Manuell ueber Admin-Endpoint POST /admin/cleanup
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import text

logger = logging.getLogger(__name__)


def _retain_days(env_key: str, default: int) -> int:
    try:
        return int(os.getenv(env_key, str(default)))
    except ValueError:
        return default


# ── Retentionsfristen ──────────────────────────────────────────────────────
RETENTION = {
    "audit_logs":            _retain_days("AILIZA_RETAIN_AUDIT_DAYS", 90),
    "security_logs":         _retain_days("AILIZA_RETAIN_SECURITY_DAYS", 180),
    "performance_logs":      _retain_days("AILIZA_RETAIN_PERFORMANCE_DAYS", 30),
    "cost_logs":             _retain_days("AILIZA_RETAIN_COST_DAYS", 30),
    "reflection_facts":      _retain_days("AILIZA_RETAIN_REFLECTION_DAYS", 90),
    "totp_backup_codes":     _retain_days("AILIZA_RETAIN_TOTP_BACKUP_DAYS", 365),
    "messenger_bindings":    _retain_days("AILIZA_RETAIN_MESSENGER_INACTIVE_DAYS", 365),
    "approval_requests":     _retain_days("AILIZA_RETAIN_APPROVAL_DAYS", 90),
    "agent_runs":            _retain_days("AILIZA_RETAIN_AGENT_RUNS_DAYS", 30),
}


def get_retention_policy() -> dict[str, int]:
    """Gibt aktuelle Retentionsfristen in Tagen zurueck (fuer Admin-Endpoint)."""
    return dict(RETENTION)


def run_cleanup() -> dict[str, Any]:
    """
    Schritt 1: Loescht alle Eintraege deren expires_at in der Vergangenheit liegt.
    Schritt 2: Setzt Pflicht-Retentionsfristen fuer Daten ohne expires_at.
    """
    try:
        from ..database import engine
    except ImportError:
        from database import engine

    now = datetime.now(timezone.utc)
    now_iso = now.isoformat()
    results: dict[str, int] = {}

    with engine.begin() as conn:
        # ── Schritt 1: expires_at-basierte Loeschung ─────────────────────
        for table in ("security_logs", "performance_logs", "cost_logs", "reflection_facts"):
            try:
                r = conn.execute(
                    text(f"DELETE FROM {table} WHERE expires_at IS NOT NULL AND expires_at < :now"),  # noqa: S608
                    {"now": now_iso},
                )
                results[f"{table}__expired"] = r.rowcount
            except Exception as exc:
                logger.warning("expires_at-Cleanup fuer %s fehlgeschlagen: %s", table, exc)
                results[f"{table}__expired"] = -1

        # ── Schritt 2: Pflicht-Retentionsfristen ohne expires_at ─────────
        # Audit-Logs (timestamp-basiert)
        try:
            cutoff = (now - timedelta(days=RETENTION["audit_logs"])).isoformat()
            r = conn.execute(
                text("DELETE FROM audit_logs WHERE timestamp < :cutoff"),
                {"cutoff": cutoff},
            )
            results["audit_logs__age"] = r.rowcount
            if r.rowcount > 0:
                logger.info("Retention audit_logs: %d Eintraege (>%d Tage) geloescht",
                            r.rowcount, RETENTION["audit_logs"])
        except Exception as exc:
            logger.warning("Retention audit_logs fehlgeschlagen: %s", exc)
            results["audit_logs__age"] = -1

        # Security-Logs (timestamp-basiert)
        try:
            cutoff = (now - timedelta(days=RETENTION["security_logs"])).isoformat()
            r = conn.execute(
                text("DELETE FROM security_logs WHERE timestamp < :cutoff AND expires_at IS NULL"),
                {"cutoff": cutoff},
            )
            results["security_logs__age"] = r.rowcount
        except Exception as exc:
            logger.warning("Retention security_logs fehlgeschlagen: %s", exc)
            results["security_logs__age"] = -1

        # Performance-Logs (timestamp-basiert)
        try:
            cutoff = (now - timedelta(days=RETENTION["performance_logs"])).isoformat()
            r = conn.execute(
                text("DELETE FROM performance_logs WHERE timestamp < :cutoff AND expires_at IS NULL"),
                {"cutoff": cutoff},
            )
            results["performance_logs__age"] = r.rowcount
        except Exception as exc:
            logger.warning("Retention performance_logs fehlgeschlagen: %s", exc)
            results["performance_logs__age"] = -1

        # Cost-Logs (timestamp-basiert)
        try:
            cutoff = (now - timedelta(days=RETENTION["cost_logs"])).isoformat()
            r = conn.execute(
                text("DELETE FROM cost_logs WHERE timestamp < :cutoff AND expires_at IS NULL"),
                {"cutoff": cutoff},
            )
            results["cost_logs__age"] = r.rowcount
        except Exception as exc:
            logger.warning("Retention cost_logs fehlgeschlagen: %s", exc)
            results["cost_logs__age"] = -1

        # Genutzte TOTP-Backup-Codes (used_at-basiert)
        try:
            cutoff = (now - timedelta(days=RETENTION["totp_backup_codes"])).isoformat()
            r = conn.execute(
                text("DELETE FROM totp_backup_codes WHERE used = 1 AND used_at < :cutoff"),
                {"cutoff": cutoff},
            )
            results["totp_backup_codes__used"] = r.rowcount
        except Exception as exc:
            logger.warning("Retention totp_backup_codes fehlgeschlagen: %s", exc)
            results["totp_backup_codes__used"] = -1

        # Inaktive Telegram-Bindings (opt_in_confirmed=0 oder widerrufen, aelter als Frist)
        try:
            cutoff = (now - timedelta(days=RETENTION["messenger_bindings"])).isoformat()
            r = conn.execute(
                text(
                    "DELETE FROM messenger_bindings "
                    "WHERE opt_in_confirmed = 0 AND created_at < :cutoff"
                ),
                {"cutoff": cutoff},
            )
            results["messenger_bindings__inactive"] = r.rowcount
        except Exception as exc:
            logger.warning("Retention messenger_bindings fehlgeschlagen: %s", exc)
            results["messenger_bindings__inactive"] = -1

        # Approval-Records (abgelaufene und aufgeloeste aelter als Frist)
        try:
            cutoff = (now - timedelta(days=RETENTION["approval_requests"])).isoformat()
            r = conn.execute(
                text(
                    "DELETE FROM approval_requests "
                    "WHERE created_at < :cutoff AND status IN ('approved','rejected','auto')"
                ),
                {"cutoff": cutoff},
            )
            results["approval_requests__resolved"] = r.rowcount
        except Exception as exc:
            logger.warning("Retention approval_requests fehlgeschlagen: %s", exc)
            results["approval_requests__resolved"] = -1

        # Agent-Run-Metadaten (abgeschlossene Runs aelter als Frist)
        try:
            cutoff = (now - timedelta(days=RETENTION["agent_runs"])).isoformat()
            r = conn.execute(
                text(
                    "DELETE FROM agent_runs "
                    "WHERE created_at < :cutoff AND status IN ('completed','failed','blocked')"
                ),
                {"cutoff": cutoff},
            )
            results["agent_runs__completed"] = r.rowcount
        except Exception as exc:
            logger.warning("Retention agent_runs fehlgeschlagen: %s", exc)
            results["agent_runs__completed"] = -1

    total = sum(v for v in results.values() if v >= 0)
    logger.info("Retention-Cleanup abgeschlossen. Gesamt: %d Eintraege geloescht.", total)
    return {
        "deleted_by_table": results,
        "total_deleted": total,
        "run_at": now_iso,
        "retention_days": get_retention_policy(),
    }
