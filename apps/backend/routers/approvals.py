from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..auth.rbac import Role, TokenData, require_role
from ..database import (
    get_approval_request,
    list_own_or_assigned_approvals,
    resolve_approval_request,
    update_agent_run,
    write_audit_entry,
)
from ..permissions import APPROVAL_DECIDE, APPROVAL_LIST, APPROVAL_READ, GENERIC_DENIED_MESSAGE, evaluate_permission


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
def list_approvals(
    status: str | None = None, token: TokenData = Depends(require_role(Role.USER)),
) -> list[dict[str, Any]]:
    # PR 2: nicht mehr ungefiltert -- nur eigene oder ausdruecklich zugewiesene
    # Genehmigungsanfragen. Filterung erfolgt direkt in der Datenbankabfrage.
    decision = evaluate_permission(
        action=APPROVAL_LIST, actor=token, tenant_id=token.tenant_id,
        resource_type="approval", resource_id="*",
    )
    if not decision.allowed:
        raise HTTPException(status_code=403, detail=decision.reason_de)
    entries = list_own_or_assigned_approvals(tenant_id=token.tenant_id, user_id=token.user_id, status=status)
    return [serialize_approval(entry) for entry in entries]


@router.get("/{approval_id}")
def get_approval(
    approval_id: int, token: TokenData = Depends(require_role(Role.USER)),
) -> dict[str, Any]:
    entry = get_approval_request(approval_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=GENERIC_DENIED_MESSAGE)

    decision = evaluate_permission(
        action=APPROVAL_READ, actor=token, tenant_id=entry["tenant_id"],
        resource_type="approval", resource_id=str(approval_id),
        resource_owner_user_id=entry.get("owner_user_id"),
    )
    if not decision.allowed:
        raise HTTPException(status_code=404, detail=GENERIC_DENIED_MESSAGE)

    return serialize_approval(entry)


@router.post("/{approval_id}/approve")
def approve_approval(
    approval_id: int,
    payload: ResolveApprovalPayload | None = None,
    token: TokenData = Depends(require_role(Role.USER)),
) -> dict[str, Any]:
    return resolve_approval(approval_id, "approved", payload.note if payload else "", token)


@router.post("/{approval_id}/reject")
def reject_approval(
    approval_id: int,
    payload: ResolveApprovalPayload | None = None,
    token: TokenData = Depends(require_role(Role.USER)),
) -> dict[str, Any]:
    return resolve_approval(approval_id, "rejected", payload.note if payload else "", token)


def resolve_approval(approval_id: int, status: str, note: str, token: TokenData) -> dict[str, Any]:
    existing = get_approval_request(approval_id)
    if existing is None:
        raise HTTPException(status_code=404, detail=GENERIC_DENIED_MESSAGE)

    # PR 2: zentrale, unmittelbar vor der Aenderung erneut ausgefuehrte
    # Pruefung -- Tenant, Status, Ablauf, Selbstfreigabe, Rolle/Zuweisung.
    # Ersetzt die bisherige reine require_role(USER)-Pruefung, die jede
    # eingeloggte Person unabhaengig von Tenant/Zustaendigkeit freigeben liess.
    decision = evaluate_permission(
        action=APPROVAL_DECIDE, actor=token, tenant_id=existing["tenant_id"],
        resource_type="approval", resource_id=str(approval_id),
        resource_owner_user_id=existing.get("owner_user_id"),
    )
    if not decision.allowed:
        status_code = 409 if decision.reason_code in ("ALREADY_DECIDED", "EXPIRED") else 404
        detail = decision.reason_de if status_code == 409 else GENERIC_DENIED_MESSAGE
        write_audit_entry(
            action="permission.denied",
            tenant_id=token.tenant_id,
            metadata={"action": "APPROVAL_DECIDE", "approval_id": approval_id, "reason_code": decision.reason_code},
        )
        raise HTTPException(status_code=status_code, detail=detail)

    entry = resolve_approval_request(approval_id, status=status, note=note)
    if entry is None:
        raise HTTPException(status_code=404, detail=GENERIC_DENIED_MESSAGE)

    write_audit_entry(
        action=f"approval.{status}",
        tenant_id=token.tenant_id,
        metadata={
            "approval_id": approval_id,
            "run_id": entry["run_id"],
            "tool": entry["tool"],
            "status": status,
            "note": note,
            "approved_by_user_id": token.user_id,
            "reason_code": decision.reason_code,
        },
    )

    if status == "rejected" and entry["run_id"]:
        update_agent_run(
            entry["run_id"],
            status="rejected",
            result={"approval_id": approval_id, "status": "rejected", "note": note},
        )

    return {"id": approval_id, "run_id": entry["run_id"], "status": status}
