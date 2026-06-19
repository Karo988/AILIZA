"""
AILIZA Cost-Log
==============
Token-Verbrauch und Kostenschaetzung. KEINE Inhalte.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

try:
    from ..database import write_cost_log, DEFAULT_TENANT_ID
except ImportError:  # pragma: no cover
    from database import write_cost_log, DEFAULT_TENANT_ID


class CostLog:
    def __init__(self, tenant_id: str = DEFAULT_TENANT_ID, retention_days: int = 365) -> None:
        self.tenant_id = tenant_id
        self.retention_days = retention_days

    def log(self, tokens_in: int, tokens_out: int, provider: str | None = None,
            model: str | None = None, use_case: str | None = None, cost_estimate: float = 0.0) -> None:
        expires = datetime.now(timezone.utc) + timedelta(days=self.retention_days)
        write_cost_log(tokens_in=tokens_in, tokens_out=tokens_out, provider=provider, model=model,
                       tenant_id=self.tenant_id, use_case=use_case, cost_estimate=cost_estimate,
                       expires_at=expires)


def log_cost(tokens_in: int, tokens_out: int, provider: str | None = None, model: str | None = None,
             tenant_id: str = DEFAULT_TENANT_ID, use_case: str | None = None,
             cost_estimate: float = 0.0) -> None:
    CostLog(tenant_id).log(tokens_in, tokens_out, provider, model, use_case, cost_estimate)
