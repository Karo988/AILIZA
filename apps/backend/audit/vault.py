"""
Audit-Vault Stufe 1 + 2
========================
Read-only, append-only Audit-Export-Service.
Stufe 2: Hash-Chain-Verifikation (SHA-256, append-only Integritätsprüfung).

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
    from apps.backend.database import (
        query_audit_events, count_audit_events,
        audit_logs, engine, _compute_audit_hash,
    )
except ImportError:
    from database import (  # type: ignore
        query_audit_events, count_audit_events,
        audit_logs, engine, _compute_audit_hash,
    )

from sqlalchemy import select as _select

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


def verify_audit_chain(
    *,
    tenant_id: str | None = None,
    limit: int = 5000,
) -> dict[str, Any]:
    """
    Prüft die SHA-256 Hash-Chain auf Manipulationen (Audit-Vault Stufe 2).

    Liest bis zu `limit` Einträge chronologisch und berechnet jeden Hash neu.
    Gibt bei Abweichung die erste fehlerhafte Eintrag-ID zurück.
    Kein PII, keine Metadaten im Ergebnis.
    """
    limit = min(limit, 10_000)

    with engine.connect() as conn:
        query = (
            _select(
                audit_logs.c.id,
                audit_logs.c.timestamp,
                audit_logs.c.action,
                audit_logs.c.tenant_id,
                audit_logs.c.previous_hash,
                audit_logs.c.entry_hash,
            )
            .order_by(audit_logs.c.id.asc())
            .limit(limit)
        )
        if tenant_id is not None:
            query = query.where(audit_logs.c.tenant_id == tenant_id)
        rows = conn.execute(query).fetchall()

    if not rows:
        return {
            "ok": True,
            "checked": 0,
            "first_invalid_id": None,
            "note": "Keine Einträge gefunden.",
        }

    checked = 0
    first_invalid: int | None = None
    expected_previous = "0" * 64

    for row in rows:
        entry_id, ts, action, tid, previous_hash, stored_hash = (
            row[0], row[1], row[2], row[3], row[4], row[5]
        )
        ts_str = ts.isoformat() if isinstance(ts, datetime) else str(ts)
        computed = _compute_audit_hash(entry_id, ts_str, action, tid, previous_hash)

        chain_ok = (previous_hash == expected_previous) and (stored_hash == computed)
        if not chain_ok and first_invalid is None:
            first_invalid = entry_id

        expected_previous = stored_hash
        checked += 1

    return {
        "ok": first_invalid is None,
        "checked": checked,
        "first_invalid_id": first_invalid,
        "note": (
            "Hash-Chain integer." if first_invalid is None
            else f"Manipulation erkannt ab Eintrag ID {first_invalid}."
        ),
    }


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
