from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import Column, DateTime, Integer, JSON, MetaData, String, Table, Text, create_engine, insert, select, update
from sqlalchemy.engine import Engine
from sqlalchemy.pool import StaticPool


DATABASE_URL = os.getenv("AILIZA_DATABASE_URL", "sqlite:///./audit_log.db")

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
)


def init_db() -> None:
    metadata_obj.create_all(engine)
    ensure_sqlite_schema()


def ensure_sqlite_schema() -> None:
    if not DATABASE_URL.startswith("sqlite"):
        return

    with engine.begin() as connection:
        approval_columns = {
            row[1] for row in connection.exec_driver_sql("PRAGMA table_info(approval_requests)").all()
        }
        if approval_columns and "run_id" not in approval_columns:
            connection.exec_driver_sql("ALTER TABLE approval_requests ADD COLUMN run_id VARCHAR(36)")


def write_audit_entry(action: str, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    entry = {
        "timestamp": datetime.now(timezone.utc),
        "action": action,
        "metadata": metadata or {},
    }

    with engine.begin() as connection:
        result = connection.execute(insert(audit_logs).values(**entry))
        entry["id"] = result.inserted_primary_key[0]

    return entry


def list_audit_entries(limit: int = 100) -> list[dict[str, Any]]:
    query = select(audit_logs).order_by(audit_logs.c.timestamp.desc()).limit(limit)

    with engine.begin() as connection:
        rows = connection.execute(query).mappings().all()

    return [dict(row) for row in rows]


def create_approval_request(
    tool: str,
    input_params: dict[str, Any],
    risk_level: str,
    risk_reason: str,
    run_id: str | None = None,
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
    }

    with engine.begin() as connection:
        connection.execute(insert(agent_runs).values(**entry))

    return entry


def get_agent_run(run_id: str) -> dict[str, Any] | None:
    query = select(agent_runs).where(agent_runs.c.id == run_id)

    with engine.begin() as connection:
        row = connection.execute(query).mappings().first()

    return dict(row) if row else None


def list_agent_runs(status: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
    query = select(agent_runs).order_by(agent_runs.c.updated_at.desc()).limit(limit)
    if status:
        query = query.where(agent_runs.c.status == status)

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
