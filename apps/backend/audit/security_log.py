"""
AILIZA Security-Log
==================
Protokolliert Sicherheitsvorfaelle OHNE Inhalt (keine Prompts, keine Secrets).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

try:
    from ..database import write_security_log, DEFAULT_TENANT_ID
except ImportError:  # pragma: no cover
    from database import write_security_log, DEFAULT_TENANT_ID


class SecurityLog:
    def __init__(self, tenant_id: str = DEFAULT_TENANT_ID, retention_days: int = 365) -> None:
        self.tenant_id = tenant_id
        self.retention_days = retention_days

    def log(self, incident_type: str, severity: str = "info") -> None:
        expires = datetime.now(timezone.utc) + timedelta(days=self.retention_days)
        write_security_log(incident_type=incident_type, severity=severity,
                           tenant_id=self.tenant_id, expires_at=expires)


def log_security(incident_type: str, severity: str = "info",
                 tenant_id: str = DEFAULT_TENANT_ID, retention_days: int = 365) -> None:
    SecurityLog(tenant_id, retention_days).log(incident_type, severity)
