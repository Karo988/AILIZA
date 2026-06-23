"""
Audit-Vault Stufe 1
===================
Read-only, append-only Audit-Export-Service.

Regeln (DSGVO + EU AI Act):
- Kein UPDATE, kein DELETE auf Audit-Einträge.
- Keine Rohdaten / Prompts / Secrets in Exports.
- Nur erlaubte Felder: id, timestamp, action, tenant_id, metadata (gefiltert).
- Admin-only: Zugriff nur mit Role.ADMIN.
- Retention-Report: reine Zählung, kein stilles Löschen.

Verbotene Felder in metadata (werden herausgefiltert):
  task_content, prompt, input_summary, credentials, secret, totp, backup_code, password
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

try:
    from apps.backend.database import query_audit_events, count_audit_events
except ImportError:
    from database import query_audit_events, count_audit_events  # type: ignore

_METADATA_BLOCKED_KEYS: frozenset[str] = frozenset({
    "task_content", "prompt", "input_summary", "credentials",
    "secret", "totp", "backup_code", "password", "token",
})


def _sanitize_metadata(raw: Any) -> dict[str, Any]:
    """Entfernt verbotene Felder aus metadata — Rohdaten nie in Exports."""
    if not isinstance(raw, dict):
        return {}
    return {k: v for k, v in raw.items() if k.lower() not in _METADATA_BLOCKED_KEYS}


def _format_entry(row: dict[str, Any]) -> dict[str, Any]:
    ts = row.get("timestamp")
    if isinstance(ts, datetime):
        ts_str = ts.isoformat()
    else:
        ts_str = str(ts) if ts is not None else None

    return {
        "id": row.get("id"),
        "timestamp": ts_str,
        "action": row.get("action"),
        "tenant_id": row.get("tenant_id"),
        "metadata": _sanitize_metadata(row.get("metadata", {})),
    }


def query_vault_events(
    *,
    action: str | None = None,
    tenant_id: str | None = None,
    timestamp_from: datetime | None = None,
    timestamp_to: datetime | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """Liest Audit-Events paginiert aus der DB — read-only, sanitized."""
    rows = query_audit_events(
        action=action,
        tenant_id=tenant_id,
        timestamp_from=timestamp_from,
        timestamp_to=timestamp_to,
        limit=limit,
        offset=offset,
    )
    return [_format_entry(r) for r in rows]


def export_audit_events(
    *,
    action: str | None = None,
    tenant_id: str | None = None,
    timestamp_from: datetime | None = None,
    timestamp_to: datetime | None = None,
    limit: int = 1000,
    offset: int = 0,
    fmt: str = "json",
) -> str:
    """
    Exportiert Audit-Events als JSON oder JSONL-String.
    Maximal 1000 Einträge pro Export (Schutz vor Massenabfragen).
    """
    limit = min(limit, 1000)
    events = query_vault_events(
        action=action,
        tenant_id=tenant_id,
        timestamp_from=timestamp_from,
        timestamp_to=timestamp_to,
        limit=limit,
        offset=offset,
    )
    if fmt == "jsonl":
        return "\n".join(json.dumps(e, ensure_ascii=False, default=str) for e in events)
    return json.dumps({"events": events, "count": len(events)}, ensure_ascii=False, default=str)


def run_audit_retention_report(
    retention_days: int,
    *,
    tenant_id: str | None = None,
) -> dict[str, Any]:
    """
    Report-only Retention-Analyse — kein DELETE, kein stilles Ablaufen.

    Gibt zurück, wie viele Einträge älter als retention_days Tage sind.
    Löschen erfordert expliziten Admin-Auftrag mit DSGVO-Dokumentation (nicht automatisch).
    """
    from datetime import timedelta as _td
    cutoff = datetime.now(timezone.utc) - _td(days=retention_days)

    affected = count_audit_events(
        tenant_id=tenant_id,
        timestamp_to=cutoff,
    )
    total = count_audit_events(tenant_id=tenant_id)

    return {
        "report_mode": True,
        "retention_days": retention_days,
        "cutoff_before": cutoff.isoformat(),
        "total_entries": total,
        "entries_older_than_retention": affected,
        "action_required": affected > 0,
        "note": (
            "Einträge werden NICHT automatisch gelöscht. "
            "Löschung erfordert expliziten Admin-Auftrag mit DSGVO-Dokumentation."
        ),
    }
