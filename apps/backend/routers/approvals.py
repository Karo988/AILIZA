from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..auth.rbac import Role, TokenData, require_role
from ..art9_transfer_registry import approval_identifier_details
from ..database import (
    get_accessible_approval,
    list_own_or_assigned_approvals,
    update_agent_run_for_tenant,
    write_audit_entry,
)
from ..permissions import APPROVAL_LIST, GENERIC_DENIED_MESSAGE, decide_approval, evaluate_permission


router = APIRouter(prefix="/approvals", tags=["approvals"])


class ResolveApprovalPayload(BaseModel):
    note: str = ""


def serialize_approval(entry: dict[str, Any]) -> dict[str, Any]:
    serialized = {
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
    if entry["tool"] in {"art9_external_transfer_pause", "art9_responsibility_handoff"}:
        serialized["identifier_details"] = approval_identifier_details(entry["input_params"])
    return serialized


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
    # PR 2 Nachbesserung: Tenant-/Owner-/Zuweisungsfilter direkt in der
    # Datenbankabfrage -- eine fremde Anfrage wird nie erst geladen und dann
    # verworfen, sie ist fuer die Abfrage schlicht nicht vorhanden.
    entry = get_accessible_approval(approval_id, token.tenant_id, token.user_id)
    if entry is None:
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
    # PR 2 Nachbesserung: Zustaendigkeit, Statuspruefung und Aenderung laufen
    # jetzt als EINE atomare Entscheidungsoperation (decide_approval). Kein
    # pauschales role >= MANAGER mehr -- nur aktive Zuweisung oder gepruefte
    # eigene compliance_consent begruenden eine Zustaendigkeit. Eine nicht
    # zustaendige Person erhaelt immer dieselbe neutrale 404-Antwort, egal ob
    # die Anfrage nicht existiert, fremd, bereits entschieden oder abgelaufen
    # ist -- kein Existenzleck ueber unterschiedliche Statuscodes.
    result = decide_approval(
        actor=token, tenant_id=token.tenant_id, approval_id=approval_id,
        new_status=status, note=note,
    )

    if not result.committed:
        if not result.allowed or result.reason_code == "NOT_FOUND_OR_FORBIDDEN":
            write_audit_entry(
                action="permission.denied",
                tenant_id=token.tenant_id,
                metadata={"action": "APPROVAL_DECIDE", "approval_id": approval_id, "reason_code": result.reason_code},
            )
            raise HTTPException(status_code=404, detail=GENERIC_DENIED_MESSAGE)
        # Person war zustaendig, aber die Anfrage war bereits entschieden,
        # abgelaufen, oder eine parallele Anfrage war schneller (CONFLICT).
        write_audit_entry(
            action="approval.decide_conflict",
            tenant_id=token.tenant_id,
            metadata={"approval_id": approval_id, "reason_code": result.reason_code},
        )
        raise HTTPException(status_code=409, detail=result.reason_de)

    entry = result.entry
    assert entry is not None

    # Audit-Minimierung: keine vollstaendige Freitextnotiz protokollieren,
    # sie kann personenbezogene/vertrauliche Inhalte enthalten.
    write_audit_entry(
        action=f"approval.{status}",
        tenant_id=token.tenant_id,
        metadata={
            "approval_id": approval_id,
            "run_id": entry["run_id"],
            "tool": entry["tool"],
            "status": status,
            "note_present": bool(note),
            "note_length": len(note or ""),
            "approved_by_user_id": token.user_id,
            "reason_code": result.reason_code,
        },
    )

    if status == "rejected" and entry["run_id"]:
        # PR 2 Nachbesserung: nur den Run desselben Tenants veraendern --
        # eine fehlerhafte oder tenant-fremde Verknuepfung darf niemals
        # einen fremden Run beeinflussen (update_agent_run_for_tenant
        # schreibt bei tenant-fremder Verknuepfung selbst ein Audit-
        # Diagnoseereignis und aendert nichts).
        update_agent_run_for_tenant(
            entry["run_id"], token.tenant_id,
            status="rejected",
            result={"approval_id": approval_id, "status": "rejected", "note_present": bool(note)},
        )

    return {"id": approval_id, "run_id": entry["run_id"], "status": status}
