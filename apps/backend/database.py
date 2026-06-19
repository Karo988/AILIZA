from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import Column, DateTime, Float, Integer, JSON, MetaData, String, Table, Text, create_engine, delete, insert, select, update
from sqlalchemy.engine import Engine
from sqlalchemy.pool import StaticPool


DATABASE_URL = os.getenv("AILIZA_DATABASE_URL", "sqlite:///./audit_log.db")
DEFAULT_TENANT_ID = os.getenv("AILIZA_DEFAULT_TENANT_ID", "default")

engine_options: dict[str, Any] = {}
if DATABASE_URL.startswith("sqlite"):
    engine_options["connect_args"] = {"check_same_thread": False}
if DATABASE_URL in {"sqlite:///:memory:", "sqlite://"}:
    engine_options["poolclass"] = StaticPool

engine: Engine = create_engine(DATABASE_URL, **engine_options)

metadata_obj = MetaData()
_UNSET = object()

audit_logs = Table(
    "audit_logs",
    metadata_obj,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("timestamp", DateTime(timezone=True), nullable=False),
    Column("action", String(255), nullable=False),
    Column("metadata", JSON, nullable=False, default=dict),
    Column("tenant_id", String(64), nullable=False, default=DEFAULT_TENANT_ID),
)

approval_requests = Table(
    "approval_requests",
    metadata_obj,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("run_id", String(36), nullable=True),
    Column("tool", String(64), nullable=False),
    Column("input_params", JSON, nullable=False),
    Column("risk_level", String(32), nullable=False),
    Column("risk_reason", Text, nullable=False),
    Column("status", String(32), nullable=False, default="pending"),
    Column("resolved_at", DateTime(timezone=True), nullable=True),
    Column("note", Text, nullable=True),
    Column("tenant_id", String(64), nullable=False, default=DEFAULT_TENANT_ID),
)

agent_runs = Table(
    "agent_runs",
    metadata_obj,
    Column("id", String(36), primary_key=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    Column("task", Text, nullable=False),
    Column("status", String(32), nullable=False),
    Column("pending_approval_id", Integer, nullable=True),
    Column("result", JSON, nullable=True),
    Column("run_metadata", JSON, nullable=False, default=dict),
    Column("tenant_id", String(64), nullable=False, default=DEFAULT_TENANT_ID),
)

# ── Getrennte Logs (KEINE Inhalte, keine Prompts, keine Secrets) ─────────────
security_logs = Table(
    "security_logs",
    metadata_obj,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("timestamp", DateTime(timezone=True), nullable=False),
    Column("incident_type", String(64), nullable=False),
    Column("severity", String(32), nullable=False),
    Column("tenant_id", String(64), nullable=False, default=DEFAULT_TENANT_ID),
    Column("expires_at", DateTime(timezone=True), nullable=True),
)

performance_logs = Table(
    "performance_logs",
    metadata_obj,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("timestamp", DateTime(timezone=True), nullable=False),
    Column("latency_ms", Integer, nullable=False),
    Column("route", String(32), nullable=True),
    Column("provider", String(64), nullable=True),
    Column("error_type", String(64), nullable=True),
    Column("tenant_id", String(64), nullable=False, default=DEFAULT_TENANT_ID),
    Column("expires_at", DateTime(timezone=True), nullable=True),
)

cost_logs = Table(
    "cost_logs",
    metadata_obj,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("timestamp", DateTime(timezone=True), nullable=False),
    Column("tokens_in", Integer, nullable=False, default=0),
    Column("tokens_out", Integer, nullable=False, default=0),
    Column("provider", String(64), nullable=True),
    Column("model", String(128), nullable=True),
    Column("tenant_id", String(64), nullable=False, default=DEFAULT_TENANT_ID),
    Column("use_case", String(128), nullable=True),
    Column("cost_estimate", Float, nullable=False, default=0.0),
    Column("expires_at", DateTime(timezone=True), nullable=True),
)

reflection_facts = Table(
    "reflection_facts",
    metadata_obj,
    Column("id", String(36), primary_key=True),
    Column("tenant_id", String(64), nullable=False, default=DEFAULT_TENANT_ID),
    Column("user_id", String(64), nullable=True),
    Column("data_classes", JSON, nullable=True),
    Column("content", Text, nullable=False),
    Column("quality_score", Float, nullable=False, default=1.0),
    Column("opt_in_confirmed", Integer, nullable=False, default=0),
    Column("created_at", String(40), nullable=False),
    Column("expires_at", String(40), nullable=False),
    Column("source", String(64), nullable=True),
    Column("purpose", String(128), nullable=True),
    Column("pii_cleared", Integer, nullable=False, default=0),
)

feedback = Table(
    "feedback",
    metadata_obj,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("tenant_id", String(64), nullable=False, default=DEFAULT_TENANT_ID),
    Column("run_id", String(36), nullable=True),
    Column("rating", String(32), nullable=False),
    Column("reason", Text, nullable=True),
    Column("quality_score_delta", Float, nullable=False, default=0.0),
    Column("created_at", DateTime(timezone=True), nullable=False),
)

routing_proposals = Table(
    "routing_proposals",
    metadata_obj,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("tenant_id", String(64), nullable=False, default=DEFAULT_TENANT_ID),
    Column("trigger_type", String(64), nullable=False),
    Column("description", Text, nullable=True),
    Column("previous_route", String(32), nullable=True),
    Column("proposed_route", String(32), nullable=True),
    Column("status", String(32), nullable=False, default="pending"),
    Column("changed_by", String(64), nullable=True),
    Column("reason", Text, nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("confirmed_at", DateTime(timezone=True), nullable=True),
    Column("policy_version", String(32), nullable=True),
)

kill_switch_state = Table(
    "kill_switch_state",
    metadata_obj,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("enabled", Integer, nullable=True),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)


def init_db() -> None:
    metadata_obj.create_all(engine)
    ensure_sqlite_schema()


def _add_column_if_missing(connection, table: str, column: str, ddl_type: str) -> None:
    cols = {row[1] for row in connection.exec_driver_sql(f"PRAGMA table_info({table})").all()}
    if cols and column not in cols:
        connection.exec_driver_sql(f"ALTER TABLE {table} ADD COLUMN {column} {ddl_type}")


def ensure_sqlite_schema() -> None:
    if not DATABASE_URL.startswith("sqlite"):
        return

    with engine.begin() as connection:
        approval_columns = {
            row[1] for row in connection.exec_driver_sql("PRAGMA table_info(approval_requests)").all()
        }
        if approval_columns and "run_id" not in approval_columns:
            connection.exec_driver_sql("ALTER TABLE approval_requests ADD COLUMN run_id VARCHAR(36)")
        # tenant_id Migration fuer Bestandstabellen
        tenant_ddl = f"VARCHAR(64) DEFAULT '{DEFAULT_TENANT_ID}'"
        for table in ("audit_logs", "approval_requests", "agent_runs"):
            _add_column_if_missing(connection, table, "tenant_id", tenant_ddl)


def get_kill_switch_flag() -> bool | None:
    """Liest optionales DB-Flag fuer den Kill-Switch. None = nicht gesetzt."""
    try:
        with engine.begin() as connection:
            row = connection.execute(
                select(kill_switch_state.c.enabled).order_by(kill_switch_state.c.id.desc()).limit(1)
            ).first()
    except Exception:
        return None
    if not row or row[0] is None:
        return None
    return bool(row[0])


# ── Getrennte Log-Writer ─────────────────────────────────────────────────────
def write_security_log(incident_type: str, severity: str, tenant_id: str = DEFAULT_TENANT_ID,
                       expires_at: datetime | None = None) -> None:
    with engine.begin() as connection:
        connection.execute(insert(security_logs).values(
            timestamp=datetime.now(timezone.utc), incident_type=incident_type,
            severity=severity, tenant_id=tenant_id, expires_at=expires_at))


def write_performance_log(latency_ms: int, route: str | None, provider: str | None,
                          error_type: str | None, tenant_id: str = DEFAULT_TENANT_ID,
                          expires_at: datetime | None = None) -> None:
    with engine.begin() as connection:
        connection.execute(insert(performance_logs).values(
            timestamp=datetime.now(timezone.utc), latency_ms=latency_ms, route=route,
            provider=provider, error_type=error_type, tenant_id=tenant_id, expires_at=expires_at))


def write_cost_log(tokens_in: int, tokens_out: int, provider: str | None, model: str | None,
                   tenant_id: str = DEFAULT_TENANT_ID, use_case: str | None = None,
                   cost_estimate: float = 0.0, expires_at: datetime | None = None) -> None:
    with engine.begin() as connection:
        connection.execute(insert(cost_logs).values(
            timestamp=datetime.now(timezone.utc), tokens_in=tokens_in, tokens_out=tokens_out,
            provider=provider, model=model, tenant_id=tenant_id, use_case=use_case,
            cost_estimate=cost_estimate, expires_at=expires_at))


def list_performance_logs(tenant_id: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
    query = select(performance_logs).order_by(performance_logs.c.timestamp.desc()).limit(limit)
    if tenant_id is not None:
        query = query.where(performance_logs.c.tenant_id == tenant_id)
    with engine.begin() as connection:
        return [dict(r) for r in connection.execute(query).mappings().all()]


def write_audit_entry(action: str, metadata: dict[str, Any] | None = None,
                      tenant_id: str = DEFAULT_TENANT_ID) -> dict[str, Any]:
    entry = {
        "timestamp": datetime.now(timezone.utc),
        "action": action,
        "metadata": metadata or {},
        "tenant_id": tenant_id,
    }

    with engine.begin() as connection:
        result = connection.execute(insert(audit_logs).values(**entry))
        entry["id"] = result.inserted_primary_key[0]

    return entry


def list_audit_entries(limit: int = 100, tenant_id: str | None = None) -> list[dict[str, Any]]:
    query = select(audit_logs).order_by(audit_logs.c.timestamp.desc()).limit(limit)
    if tenant_id is not None:
        query = query.where(audit_logs.c.tenant_id == tenant_id)

    with engine.begin() as connection:
        rows = connection.execute(query).mappings().all()

    return [dict(row) for row in rows]


def create_approval_request(
    tool: str,
    input_params: dict[str, Any],
    risk_level: str,
    risk_reason: str,
    run_id: str | None = None,
    tenant_id: str = DEFAULT_TENANT_ID,
) -> dict[str, Any]:
    entry = {
        "created_at": datetime.now(timezone.utc),
        "run_id": run_id,
        "tool": tool,
        "input_params": input_params,
        "risk_level": risk_level,
        "risk_reason": risk_reason,
        "status": "pending",
        "resolved_at": None,
        "note": None,
        "tenant_id": tenant_id,
    }

    with engine.begin() as connection:
        result = connection.execute(insert(approval_requests).values(**entry))
        entry["id"] = result.inserted_primary_key[0]

    return entry


def create_agent_run(
    run_id: str,
    task: str,
    status: str = "running",
    run_metadata: dict[str, Any] | None = None,
    tenant_id: str = DEFAULT_TENANT_ID,
) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    entry = {
        "id": run_id,
        "created_at": now,
        "updated_at": now,
        "task": task,
        "status": status,
        "pending_approval_id": None,
        "result": None,
        "run_metadata": run_metadata or {},
        "tenant_id": tenant_id,
    }

    with engine.begin() as connection:
        connection.execute(insert(agent_runs).values(**entry))

    return entry


def get_agent_run(run_id: str) -> dict[str, Any] | None:
    query = select(agent_runs).where(agent_runs.c.id == run_id)

    with engine.begin() as connection:
        row = connection.execute(query).mappings().first()

    return dict(row) if row else None


def list_agent_runs(status: str | None = None, limit: int = 100,
                    tenant_id: str | None = None) -> list[dict[str, Any]]:
    query = select(agent_runs).order_by(agent_runs.c.updated_at.desc()).limit(limit)
    if status:
        query = query.where(agent_runs.c.status == status)
    if tenant_id is not None:
        query = query.where(agent_runs.c.tenant_id == tenant_id)

    with engine.begin() as connection:
        rows = connection.execute(query).mappings().all()

    return [dict(row) for row in rows]


def update_agent_run(
    run_id: str,
    *,
    status: str | None = None,
    pending_approval_id: int | None | object = _UNSET,
    result: dict[str, Any] | None | object = _UNSET,
    run_metadata: dict[str, Any] | None | object = _UNSET,
) -> dict[str, Any] | None:
    values: dict[str, Any] = {"updated_at": datetime.now(timezone.utc)}
    if status is not None:
        values["status"] = status
    if pending_approval_id is not _UNSET:
        values["pending_approval_id"] = pending_approval_id
    if result is not _UNSET:
        values["result"] = result
    if run_metadata is not _UNSET:
        values["run_metadata"] = run_metadata or {}

    query = update(agent_runs).where(agent_runs.c.id == run_id).values(**values)
    with engine.begin() as connection:
        result_row = connection.execute(query)

    if result_row.rowcount == 0:
        return None

    return get_agent_run(run_id)


def link_approval_to_run(approval_id: int, run_id: str) -> dict[str, Any] | None:
    query = update(approval_requests).where(approval_requests.c.id == approval_id).values(run_id=run_id)
    with engine.begin() as connection:
        result = connection.execute(query)

    if result.rowcount == 0:
        return None

    return get_approval_request(approval_id)


def list_approval_requests(status: str | None = None) -> list[dict[str, Any]]:
    query = select(approval_requests).order_by(approval_requests.c.created_at.desc())
    if status:
        query = query.where(approval_requests.c.status == status)

    with engine.begin() as connection:
        rows = connection.execute(query).mappings().all()

    return [dict(row) for row in rows]


def get_approval_request(approval_id: int) -> dict[str, Any] | None:
    query = select(approval_requests).where(approval_requests.c.id == approval_id)

    with engine.begin() as connection:
        row = connection.execute(query).mappings().first()

    return dict(row) if row else None


def resolve_approval_request(approval_id: int, status: str, note: str = "") -> dict[str, Any] | None:
    resolved_at = datetime.now(timezone.utc)
    query = (
        update(approval_requests)
        .where(approval_requests.c.id == approval_id)
        .where(approval_requests.c.status == "pending")
        .values(status=status, resolved_at=resolved_at, note=note)
    )

    with engine.begin() as connection:
        result = connection.execute(query)

    if result.rowcount == 0:
        return get_approval_request(approval_id)

    return get_approval_request(approval_id)


# ── Reflection Facts ─────────────────────────────────────────────────────────
def insert_reflection_fact(values: dict[str, Any]) -> None:
    with engine.begin() as connection:
        connection.execute(insert(reflection_facts).values(**values))


def query_reflection_facts(tenant_id: str, purpose: str | None = None,
                           limit: int = 5) -> list[dict[str, Any]]:
    query = select(reflection_facts).where(reflection_facts.c.tenant_id == tenant_id)
    if purpose:
        query = query.where(reflection_facts.c.purpose == purpose)
    query = query.order_by(reflection_facts.c.quality_score.desc()).limit(limit)
    with engine.begin() as connection:
        return [dict(r) for r in connection.execute(query).mappings().all()]


def delete_reflection_fact(fact_id: str) -> int:
    with engine.begin() as connection:
        result = connection.execute(delete(reflection_facts).where(reflection_facts.c.id == fact_id))
    return result.rowcount


def delete_reflection_facts_for_tenant(tenant_id: str) -> int:
    with engine.begin() as connection:
        result = connection.execute(delete(reflection_facts).where(reflection_facts.c.tenant_id == tenant_id))
    return result.rowcount


def adjust_fact_quality_for_run(run_id: str, delta: float, tenant_id: str = DEFAULT_TENANT_ID) -> None:
    # MVP: passt quality_score aller Facts des Tenants mit passender source an.
    with engine.begin() as connection:
        connection.execute(
            update(reflection_facts)
            .where(reflection_facts.c.tenant_id == tenant_id)
            .where(reflection_facts.c.source == run_id)
            .values(quality_score=reflection_facts.c.quality_score + delta)
        )


# ── Feedback ─────────────────────────────────────────────────────────────────
def insert_feedback(tenant_id: str, run_id: str | None, rating: str,
                    reason: str | None, quality_score_delta: float) -> dict[str, Any]:
    entry = {
        "tenant_id": tenant_id, "run_id": run_id, "rating": rating,
        "reason": reason, "quality_score_delta": quality_score_delta,
        "created_at": datetime.now(timezone.utc),
    }
    with engine.begin() as connection:
        result = connection.execute(insert(feedback).values(**entry))
        entry["id"] = result.inserted_primary_key[0]
    return entry


def count_negative_feedback(tenant_id: str, run_id: str | None) -> int:
    query = select(feedback).where(feedback.c.tenant_id == tenant_id).where(
        feedback.c.rating == "not_helpful")
    if run_id is not None:
        query = query.where(feedback.c.run_id == run_id)
    with engine.begin() as connection:
        return len(connection.execute(query).all())


# ── Routing Proposals ────────────────────────────────────────────────────────
def insert_routing_proposal(tenant_id: str, trigger_type: str, description: str,
                            previous_route: str | None = None, proposed_route: str | None = None,
                            reason: str | None = None) -> dict[str, Any]:
    entry = {
        "tenant_id": tenant_id, "trigger_type": trigger_type, "description": description,
        "previous_route": previous_route, "proposed_route": proposed_route,
        "status": "pending", "changed_by": None, "reason": reason,
        "created_at": datetime.now(timezone.utc), "confirmed_at": None, "policy_version": None,
    }
    with engine.begin() as connection:
        result = connection.execute(insert(routing_proposals).values(**entry))
        entry["id"] = result.inserted_primary_key[0]
    return entry


def list_routing_proposals(tenant_id: str | None = None) -> list[dict[str, Any]]:
    query = select(routing_proposals).order_by(routing_proposals.c.created_at.desc())
    if tenant_id is not None:
        query = query.where(routing_proposals.c.tenant_id == tenant_id)
    with engine.begin() as connection:
        return [dict(r) for r in connection.execute(query).mappings().all()]
