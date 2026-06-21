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

conversations = Table(
    "conversations",
    metadata_obj,
    Column("id", String(36), primary_key=True),
    Column("user_id", String(64), nullable=False),
    Column("session_id", String(64), nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    Column("title", String(255), nullable=True),
    Column("metadata", JSON, nullable=False, default=dict),
)

messages = Table(
    "messages",
    metadata_obj,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("conversation_id", String(36), nullable=False),
    Column("role", String(16), nullable=False),
    Column("content", Text, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("token_count", Integer, nullable=True),
    Column("tool_name", String(64), nullable=True),
    Column("tool_result", JSON, nullable=True),
)

user_profiles = Table(
    "user_profiles",
    metadata_obj,
    Column("user_id", String(64), primary_key=True),
    Column("display_name", String(255), nullable=True),
    Column("company", String(255), nullable=True),
    Column("language", String(8), nullable=False, default="de"),
    Column("preferences", JSON, nullable=False, default=dict),
    Column("learned_facts", JSON, nullable=False, default=dict),
    Column("consent_records", JSON, nullable=False, default=list),
    Column("onboarding_done", Integer, nullable=False, default=0),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    Column("data_retention_days", Integer, nullable=False, default=90),
)

processing_records = Table(
    "processing_records",
    metadata_obj,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("user_id", String(64), nullable=True),
    Column("conversation_id", String(36), nullable=True),
    Column("message_id", Integer, nullable=True),
    Column("pii_types_detected", JSON, nullable=False, default=list),
    Column("pii_count", Integer, nullable=False, default=0),
    Column("legal_basis", String(64), nullable=True),
    Column("purpose", Text, nullable=True),
    Column("recipients", JSON, nullable=False, default=list),
    Column("retention_days", Integer, nullable=False, default=90),
    Column("consent_given", Integer, nullable=False, default=0),
    Column("documented_at", DateTime(timezone=True), nullable=True),
    Column("acknowledged_by_user", Integer, nullable=False, default=0),
)

feedback = Table(
    "feedback",
    metadata_obj,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("message_id", Integer, nullable=True),
    Column("user_id", String(64), nullable=True),
    Column("rating", Integer, nullable=True),
    Column("correction", Text, nullable=True),
    Column("tool_name", String(64), nullable=True),
    Column("was_helpful", Integer, nullable=True),
)

learned_rules = Table(
    "learned_rules",
    metadata_obj,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("user_id", String(64), nullable=False),
    Column("rule_text", Text, nullable=False),
    Column("source", String(32), nullable=False, default="correction"),
    Column("confidence", Integer, nullable=False, default=70),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("last_applied_at", DateTime(timezone=True), nullable=True),
    Column("apply_count", Integer, nullable=False, default=0),
    Column("conflicts_with", JSON, nullable=True),
    Column("active", Integer, nullable=False, default=1),
)

compliance_updates = Table(
    "compliance_updates",
    metadata_obj,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("checked_at", DateTime(timezone=True), nullable=False),
    Column("source_url", String(512), nullable=True),
    Column("source_name", String(128), nullable=True),
    Column("update_type", String(32), nullable=True),
    Column("summary_de", Text, nullable=True),
    Column("affected_articles", JSON, nullable=False, default=list),
    Column("severity", String(16), nullable=False, default="info"),
    Column("acknowledged", Integer, nullable=False, default=0),
)

skill_memory = Table(
    "skill_memory",
    metadata_obj,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("task_type", String(64), nullable=False, unique=True),
    Column("approach_worked", Text, nullable=True),
    Column("approach_failed", Text, nullable=True),
    Column("context", JSON, nullable=True),
    Column("success_count", Integer, nullable=False, default=0),
    Column("fail_count", Integer, nullable=False, default=0),
    Column("last_updated", DateTime(timezone=True), nullable=True),
)


def get_engine() -> Engine:
    return engine


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
    tool: str, input_params: dict[str, Any], risk_level: str,
    risk_reason: str, run_id: str | None = None,
) -> dict[str, Any]:
    entry = {
        "created_at": datetime.now(timezone.utc), "run_id": run_id, "tool": tool,
        "input_params": input_params, "risk_level": risk_level, "risk_reason": risk_reason,
        "status": "pending", "resolved_at": None, "note": None,
    }
    with engine.begin() as connection:
        result = connection.execute(insert(approval_requests).values(**entry))
        entry["id"] = result.inserted_primary_key[0]
    return entry


def create_agent_run(run_id: str, task: str, status: str = "running",
                     run_metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    entry = {
        "id": run_id, "created_at": now, "updated_at": now, "task": task,
        "status": status, "pending_approval_id": None, "result": None,
        "run_metadata": run_metadata or {},
    }
    with engine.begin() as connection:
        connection.execute(insert(agent_runs).values(**entry))
    return entry


def get_agent_run(run_id: str) -> dict[str, Any] | None:
    with engine.begin() as connection:
        row = connection.execute(select(agent_runs).where(agent_runs.c.id == run_id)).mappings().first()
    return dict(row) if row else None


def list_agent_runs(status: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
    query = select(agent_runs).order_by(agent_runs.c.updated_at.desc()).limit(limit)
    if status:
        query = query.where(agent_runs.c.status == status)
    with engine.begin() as connection:
        rows = connection.execute(query).mappings().all()
    return [dict(row) for row in rows]


def update_agent_run(
    run_id: str, *, status: str | None = None,
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
    with engine.begin() as connection:
        r = connection.execute(update(agent_runs).where(agent_runs.c.id == run_id).values(**values))
    return get_agent_run(run_id) if r.rowcount > 0 else None


def link_approval_to_run(approval_id: int, run_id: str) -> dict[str, Any] | None:
    with engine.begin() as connection:
        r = connection.execute(
            update(approval_requests).where(approval_requests.c.id == approval_id).values(run_id=run_id)
        )
    return get_approval_request(approval_id) if r.rowcount > 0 else None


def list_approval_requests(status: str | None = None) -> list[dict[str, Any]]:
    query = select(approval_requests).order_by(approval_requests.c.created_at.desc())
    if status:
        query = query.where(approval_requests.c.status == status)
    with engine.begin() as connection:
        rows = connection.execute(query).mappings().all()
    return [dict(row) for row in rows]


def get_approval_request(approval_id: int) -> dict[str, Any] | None:
    with engine.begin() as connection:
        row = connection.execute(
            select(approval_requests).where(approval_requests.c.id == approval_id)
        ).mappings().first()
    return dict(row) if row else None


# ── Nutzerprofile & Onboarding ─────────────────────────────────────────────────

def get_or_create_user_profile(user_id: str) -> dict[str, Any]:
    with engine.begin() as connection:
        row = connection.execute(
            select(user_profiles).where(user_profiles.c.user_id == user_id)
        ).mappings().first()
        if row:
            return dict(row)
        now = datetime.now(timezone.utc)
        connection.execute(insert(user_profiles).values(
            user_id=user_id, display_name=None, company=None, language="de",
            preferences={}, learned_facts={}, consent_records=[],
            onboarding_done=0, created_at=now, updated_at=now, data_retention_days=90,
        ))
    return get_or_create_user_profile(user_id)


def update_user_profile(user_id: str, **kwargs: Any) -> dict[str, Any]:
    get_or_create_user_profile(user_id)
    kwargs["updated_at"] = datetime.now(timezone.utc)
    with engine.begin() as connection:
        connection.execute(
            update(user_profiles).where(user_profiles.c.user_id == user_id).values(**kwargs)
        )
    return get_or_create_user_profile(user_id)


def complete_onboarding(user_id: str) -> dict[str, Any]:
    return update_user_profile(user_id, onboarding_done=1)


def delete_user_data(user_id: str) -> dict[str, int]:
    """DSGVO Art. 17 — vollständige Löschung aller Nutzerdaten."""
    counts: dict[str, int] = {}
    with engine.begin() as connection:
        conv_ids = [
            row[0] for row in connection.execute(
                select(conversations.c.id).where(conversations.c.user_id == user_id)
            ).all()
        ]
        if conv_ids:
            r = connection.execute(messages.delete().where(messages.c.conversation_id.in_(conv_ids)))
            counts["messages"] = r.rowcount
        counts["conversations"] = connection.execute(
            conversations.delete().where(conversations.c.user_id == user_id)).rowcount
        counts["user_profiles"] = connection.execute(
            user_profiles.delete().where(user_profiles.c.user_id == user_id)).rowcount
        counts["processing_records"] = connection.execute(
            processing_records.delete().where(processing_records.c.user_id == user_id)).rowcount
        counts["feedback"] = connection.execute(
            feedback.delete().where(feedback.c.user_id == user_id)).rowcount
        counts["learned_rules"] = connection.execute(
            learned_rules.delete().where(learned_rules.c.user_id == user_id)).rowcount
    write_audit_entry("dsgvo.art17.user_deleted", {"user_id": user_id, "counts": counts})
    return counts


# ── Konversationen ─────────────────────────────────────────────────────

def create_conversation(user_id: str, session_id: str | None = None, title: str | None = None) -> str:
    from uuid import uuid4
    now = datetime.now(timezone.utc)
    conv_id = str(uuid4())
    with engine.begin() as connection:
        connection.execute(insert(conversations).values(
            id=conv_id, user_id=user_id, session_id=session_id,
            created_at=now, updated_at=now,
            title=title or f"Gespräch {now.strftime('%d.%m.%Y %H:%M')}",
            metadata={},
        ))
    return conv_id


def append_message(
    conversation_id: str, role: str, content: str,
    token_count: int | None = None, tool_name: str | None = None, tool_result: Any = None,
) -> int:
    now = datetime.now(timezone.utc)
    with engine.begin() as connection:
        result = connection.execute(insert(messages).values(
            conversation_id=conversation_id, role=role, content=content,
            created_at=now, token_count=token_count, tool_name=tool_name, tool_result=tool_result,
        ))
        msg_id: int = result.inserted_primary_key[0]
        connection.execute(
            update(conversations).where(conversations.c.id == conversation_id).values(updated_at=now)
        )
    return msg_id


def get_conversation_history(conversation_id: str, limit: int = 20) -> list[dict[str, Any]]:
    query = (
        select(messages).where(messages.c.conversation_id == conversation_id)
        .order_by(messages.c.created_at.desc()).limit(limit)
    )
    with engine.begin() as connection:
        rows = connection.execute(query).mappings().all()
    return list(reversed([dict(r) for r in rows]))


def list_conversations(user_id: str, limit: int = 50) -> list[dict[str, Any]]:
    query = (
        select(conversations).where(conversations.c.user_id == user_id)
        .order_by(conversations.c.updated_at.desc()).limit(limit)
    )
    with engine.begin() as connection:
        rows = connection.execute(query).mappings().all()
    return [dict(r) for r in rows]


# ── Verarbeitungsverzeichnis Art. 30 ────────────────────────────────────────────

def record_processing(
    pii_types: list[str], pii_count: int,
    user_id: str | None = None, conversation_id: str | None = None,
    message_id: int | None = None, legal_basis: str | None = None,
    purpose: str | None = None, recipients: list[str] | None = None,
    retention_days: int = 90, consent_given: bool = False,
) -> int:
    now = datetime.now(timezone.utc)
    with engine.begin() as connection:
        result = connection.execute(insert(processing_records).values(
            created_at=now, user_id=user_id, conversation_id=conversation_id,
            message_id=message_id, pii_types_detected=pii_types, pii_count=pii_count,
            legal_basis=legal_basis, purpose=purpose,
            recipients=recipients or ["Intern — kein externer Empfänger"],
            retention_days=retention_days, consent_given=int(consent_given),
            documented_at=now, acknowledged_by_user=0,
        ))
        rec_id: int = result.inserted_primary_key[0]
    write_audit_entry("dsgvo.art30.processing_recorded", {"pii_types": pii_types, "legal_basis": legal_basis})
    return rec_id


def list_processing_records(user_id: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
    query = select(processing_records).order_by(processing_records.c.created_at.desc()).limit(limit)
    if user_id:
        query = query.where(processing_records.c.user_id == user_id)
    with engine.begin() as connection:
        rows = connection.execute(query).mappings().all()
    return [dict(r) for r in rows]


# ── Gelernte Regeln ────────────────────────────────────────────────────

def add_learned_rule(user_id: str, rule_text: str, source: str = "correction", confidence: int = 70) -> int:
    now = datetime.now(timezone.utc)
    with engine.begin() as connection:
        result = connection.execute(insert(learned_rules).values(
            user_id=user_id, rule_text=rule_text, source=source,
            confidence=confidence, created_at=now, apply_count=0, active=1,
        ))
        return result.inserted_primary_key[0]


def get_active_rules(user_id: str, min_confidence: int = 50) -> list[dict[str, Any]]:
    query = (
        select(learned_rules)
        .where(learned_rules.c.user_id == user_id)
        .where(learned_rules.c.active == 1)
        .where(learned_rules.c.confidence >= min_confidence)
        .order_by(learned_rules.c.confidence.desc())
        .limit(10)
    )
    with engine.begin() as connection:
        rows = connection.execute(query).mappings().all()
    return [dict(r) for r in rows]


def update_rule_confidence(rule_id: int, delta: int) -> None:
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "UPDATE learned_rules SET confidence = MAX(0, MIN(100, confidence + ?)) WHERE id = ?",
            (delta, rule_id),
        )


def deactivate_rule(rule_id: int, user_id: str | None = None) -> None:
    q = update(learned_rules).where(learned_rules.c.id == rule_id).values(active=0)
    if user_id:
        q = q.where(learned_rules.c.user_id == user_id)
    with engine.begin() as connection:
        connection.execute(q)


# ── Feedback ──────────────────────────────────────────────────────────────

def record_feedback(
    user_id: str | None = None, message_id: int | None = None,
    rating: int | None = None, correction: str | None = None,
    tool_name: str | None = None, was_helpful: bool | None = None,
) -> int:
    with engine.begin() as connection:
        result = connection.execute(insert(feedback).values(
            created_at=datetime.now(timezone.utc),
            message_id=message_id, user_id=user_id, rating=rating,
            correction=correction, tool_name=tool_name,
            was_helpful=None if was_helpful is None else int(was_helpful),
        ))
        return result.inserted_primary_key[0]


def resolve_approval_request(approval_id: int, status: str, note: str = "") -> dict[str, Any] | None:
    with engine.begin() as connection:
        connection.execute(
            update(approval_requests)
            .where(approval_requests.c.id == approval_id)
            .where(approval_requests.c.status == "pending")
            .values(status=status, resolved_at=datetime.now(timezone.utc), note=note)
        )
    return get_approval_request(approval_id)
