from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..database import (
    get_approval_request,
    list_approval_requests,
    resolve_approval_request,
    update_agent_run,
    write_audit_entry,
)


router = APIRouter(prefix="/approvals", tags=["approvals"])


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


@router.get("")
def list_approvals(status: str | None = None) -> list[dict[str, Any]]:
    return [serialize_approval(entry) for entry in list_approval_requests(status=status)]


@router.get("/{approval_id}")
def get_approval(approval_id: int) -> dict[str, Any]:
    entry = get_approval_request(approval_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="Approval request not found")

    return serialize_approval(entry)


@router.post("/{approval_id}/approve")
def approve_approval(
    approval_id: int,
    payload: ResolveApprovalPayload | None = None,
) -> dict[str, Any]:
    return resolve_approval(approval_id, "approved", payload.note if payload else "")


@router.post("/{approval_id}/reject")
def reject_approval(
    approval_id: int,
    payload: ResolveApprovalPayload | None = None,
) -> dict[str, Any]:
    return resolve_approval(approval_id, "rejected", payload.note if payload else "")


def resolve_approval(approval_id: int, status: str, note: str) -> dict[str, Any]:
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
        },
    )

    if status == "rejected" and entry["run_id"]:
        update_agent_run(
            entry["run_id"],
            status="rejected",
            result={"approval_id": approval_id, "status": "rejected", "note": note},
        )

    return {"id": approval_id, "run_id": entry["run_id"], "status": status}
