from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import delete, insert, select, update

from ..auth.rbac import Role, TokenData, require_role
from ..database import (
    _compute_audit_hash,
    _get_latest_audit_hash,
    audit_logs,
    engine,
    get_approval_request,
    list_approval_requests,
    memory_items,
    memory_visibility,
    resolve_approval_request,
    update_agent_run,
    write_audit_entry,
)


router = APIRouter(tags=["approvals"])


class ResolveApprovalPayload(BaseModel):
    note: str = ""


def serialize_approval(entry: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": entry["id"],
        "created_at": entry["created_at"],
        "run_id": entry["run_id"],
        "tool": entry["tool"],
        "input_params": entry["input_params"],
        "risk_level": entry["risk_level"],
        "risk_reason": entry["risk_reason"],
        "status": entry["status"],
        "resolved_at": entry["resolved_at"],
        "note": entry["note"],
    }


def serialize_memory_fact(entry: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": entry["id"],
        "scope": entry["scope"],
        "title": entry["title"],
        "content": entry["content"],
        "category": entry["category"],
        "purpose": entry["purpose"],
        "status": entry["status"],
        "expires_at": entry["expires_at"],
        "created_at": entry["created_at"],
        "updated_at": entry["updated_at"],
    }


def _as_aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


def _write_memory_deleted_audit_in_transaction(
    conn: Any,
    *,
    tenant_id: str,
    memory_item_id: int,
    scope: str,
    actor_user_id: str,
    result: str,
) -> dict[str, Any]:
    """Write the memory.deleted audit event in the same transaction as deletion.

    This mirrors database.write_audit_entry so deletion is not reported as
    successful if the hash-chain audit insert fails.
    """
    ts = datetime.now(timezone.utc)
    previous_hash = _get_latest_audit_hash(conn)
    metadata = {
        "memory_item_id": memory_item_id,
        "scope": scope,
        "actor_user_id": actor_user_id,
        "result": result,
    }
    entry = {
        "timestamp": ts,
        "action": "memory.deleted",
        "metadata": metadata,
        "tenant_id": tenant_id,
        "previous_hash": previous_hash,
        "entry_hash": "pending",
    }
    inserted = conn.execute(insert(audit_logs).values(**entry))
    entry_id = inserted.inserted_primary_key[0]
    entry_hash = _compute_audit_hash(
        entry_id, ts.isoformat(), "memory.deleted", tenant_id, previous_hash
    )
    conn.execute(
        update(audit_logs)
        .where(audit_logs.c.id == entry_id)
        .values(entry_hash=entry_hash)
    )
    entry["id"] = entry_id
    entry["entry_hash"] = entry_hash
    return entry


@router.get("/approvals")
def list_approvals(status: str | None = None) -> list[dict[str, Any]]:
    return [serialize_approval(entry) for entry in list_approval_requests(status=status)]


@router.get("/approvals/{approval_id}")
def get_approval(approval_id: int) -> dict[str, Any]:
    entry = get_approval_request(approval_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="Approval request not found")

    return serialize_approval(entry)


@router.post("/approvals/{approval_id}/approve")
def approve_approval(
    approval_id: int,
    payload: ResolveApprovalPayload | None = None,
    token: TokenData = Depends(require_role(Role.USER)),
) -> dict[str, Any]:
    return resolve_approval(approval_id, "approved", payload.note if payload else "", token)


@router.post("/approvals/{approval_id}/reject")
def reject_approval(
    approval_id: int,
    payload: ResolveApprovalPayload | None = None,
    token: TokenData = Depends(require_role(Role.USER)),
) -> dict[str, Any]:
    return resolve_approval(approval_id, "rejected", payload.note if payload else "", token)


@router.get("/memory/facts")
def list_own_memory_facts(
    token: TokenData = Depends(require_role(Role.USER)),
) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    with engine.begin() as conn:
        rows = conn.execute(
            select(memory_items)
            .where(memory_items.c.tenant_id == token.tenant_id)
            .where(memory_items.c.owner_user_id == token.user_id)
            .where(memory_items.c.scope == "user_memory")
            .where(memory_items.c.status != "deleted")
            .order_by(memory_items.c.updated_at.desc())
        ).mappings().all()

    facts = []
    for row in rows:
        entry = dict(row)
        expires_at = entry.get("expires_at")
        if expires_at is not None and _as_aware(expires_at) <= now:
            continue
        facts.append(serialize_memory_fact(entry))
    return {"count": len(facts), "items": facts}


@router.delete("/memory/facts/{memory_item_id}")
def delete_own_memory_fact(
    memory_item_id: int,
    token: TokenData = Depends(require_role(Role.USER)),
) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    with engine.begin() as conn:
        row = conn.execute(
            select(memory_items)
            .where(memory_items.c.id == memory_item_id)
            .where(memory_items.c.tenant_id == token.tenant_id)
            .where(memory_items.c.owner_user_id == token.user_id)
            .where(memory_items.c.scope == "user_memory")
            .where(memory_items.c.status != "deleted")
        ).mappings().first()
        if row is None:
            raise HTTPException(status_code=404, detail="Memory-Fact nicht gefunden.")

        conn.execute(
            update(memory_items)
            .where(memory_items.c.id == memory_item_id)
            .where(memory_items.c.tenant_id == token.tenant_id)
            .where(memory_items.c.owner_user_id == token.user_id)
            .values(status="deleted", updated_at=now)
        )
        conn.execute(
            delete(memory_visibility).where(memory_visibility.c.memory_item_id == memory_item_id)
        )
        _write_memory_deleted_audit_in_transaction(
            conn,
            tenant_id=token.tenant_id,
            memory_item_id=memory_item_id,
            scope=row["scope"],
            actor_user_id=token.user_id,
            result="deleted",
        )

    return {"status": "deleted", "id": memory_item_id}


def resolve_approval(approval_id: int, status: str, note: str, token: TokenData) -> dict[str, Any]:
    existing = get_approval_request(approval_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="Approval request not found")

    if existing["status"] != "pending":
        raise HTTPException(status_code=409, detail=f"Already resolved: {existing['status']}")

    entry = resolve_approval_request(approval_id, status=status, note=note)
    if entry is None:
        raise HTTPException(status_code=404, detail="Approval request not found")

    write_audit_entry(
        action=f"approval.{status}",
        metadata={
            "approval_id": approval_id,
            "run_id": entry["run_id"],
            "tool": entry["tool"],
            "status": status,
            "note": note,
            "approved_by_user_id": token.user_id,
        },
    )

    if status == "rejected" and entry["run_id"]:
        update_agent_run(
            entry["run_id"],
            status="rejected",
            result={"approval_id": approval_id, "status": "rejected", "note": note},
        )

    return {"id": approval_id, "run_id": entry["run_id"], "status": status}
