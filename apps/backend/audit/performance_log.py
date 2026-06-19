"""
AILIZA Performance-Log
=====================
Latenz/Route/Provider/Fehlertyp. KEINE Inhalte.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

try:
    from ..database import write_performance_log, DEFAULT_TENANT_ID
except ImportError:  # pragma: no cover
    from database import write_performance_log, DEFAULT_TENANT_ID


class PerformanceLog:
    def __init__(self, tenant_id: str = DEFAULT_TENANT_ID, retention_days: int = 90) -> None:
        self.tenant_id = tenant_id
        self.retention_days = retention_days

    def log(self, latency_ms: int, route: str | None = None, provider: str | None = None,
            error_type: str | None = None) -> None:
        expires = datetime.now(timezone.utc) + timedelta(days=self.retention_days)
        write_performance_log(latency_ms=latency_ms, route=route, provider=provider,
                              error_type=error_type, tenant_id=self.tenant_id, expires_at=expires)


def log_performance(latency_ms: int, route: str | None = None, provider: str | None = None,
                    error_type: str | None = None, tenant_id: str = DEFAULT_TENANT_ID) -> None:
    PerformanceLog(tenant_id).log(latency_ms, route, provider, error_type)
