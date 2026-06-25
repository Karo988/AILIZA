from __future__ import annotations

from typing import Any

from fastapi import HTTPException

from ..approval import ApprovalStatus, assess_risk
from ..database import create_approval_request, get_approval_request, write_audit_entry
from ..policy import check_tool_call
from ..tools import execute_tool


def _safe_param_summary(parameters: dict[str, Any]) -> dict[str, Any]:
    """Logt nur Parametertypen und -Längen, nie Inhalte (kein PII/Secret-Leak in Audit)."""
    return {k: f"<{type(v).__name__}:{len(str(v))}>" for k, v in parameters.items()}


def _safe_risk_summary(risk: Any) -> dict[str, Any]:
    """Logt Risk-Result ohne input_summary (enthält Prompt-Fragmente)."""
    d = risk.to_dict()
    d.pop("input_summary", None)
    return d


def enforce_policy(tool_name: str, parameters: dict[str, Any]) -> None:
    decision = check_tool_call(tool_name, parameters)
    write_audit_entry(
        action="policy.decision",
        metadata={
            "tool": tool_name,
            "parameters": _safe_param_summary(parameters),
            "decision": {
                "allowed": decision.allowed,
                "decision": decision.decision.value,
                "reason": decision.reason,
                "tool": decision.tool,
            },
        },
    )

    if not decision.allowed:
        raise HTTPException(status_code=403, detail=decision.reason)


def request_approval_if_needed(tool_name: str, parameters: dict[str, Any]) -> dict[str, Any] | None:
    risk = assess_risk(tool_name, parameters)
    if not risk.risky:
        write_audit_entry(
            action="approval.auto",
            metadata={
                "tool": tool_name,
                "parameters": _safe_param_summary(parameters),
                "risk": _safe_risk_summary(risk),
                "approval_status": ApprovalStatus.AUTO.value,
            },
        )
        return None

    approval = create_approval_request(
        tool=tool_name,
        input_params=parameters,
        risk_level=risk.risk_level,
        risk_reason=risk.reason,
    )
    write_audit_entry(
        action="approval.requested",
        metadata={
            "approval_id": approval["id"],
            "tool": tool_name,
            "parameters": _safe_param_summary(parameters),
            "risk": _safe_risk_summary(risk),
            "approval_status": ApprovalStatus.PENDING.value,
        },
    )

    return {
        "status": ApprovalStatus.PENDING.value,
        "approval_id": approval["id"],
        "message": f"Approval required: {risk.reason}",
        "risk_level": risk.risk_level,
        "tool": tool_name,
        "parameters": parameters,
    }


def guarded_tool_call(tool_name: str, parameters: dict[str, Any]) -> dict[str, Any]:
    enforce_policy(tool_name, parameters)
    approval_response = request_approval_if_needed(tool_name, parameters)
    if approval_response is not None:
        return approval_response

    result = execute_tool(tool_name, parameters)
    write_audit_entry(
        action="tools.executed",
        metadata={"tool": tool_name, "parameters": _safe_param_summary(parameters)},
    )

    return {
        "status": "completed",
        "tool": tool_name,
        "parameters": parameters,
        "result": result,
    }


def execute_approved_tool(approval_id: int) -> dict[str, Any]:
    approval = get_approval_request(approval_id)
    if approval is None:
        raise HTTPException(status_code=404, detail="Approval request not found")

    if approval["status"] == ApprovalStatus.PENDING.value:
        return {
            "status": ApprovalStatus.PENDING.value,
            "approval_id": approval_id,
            "run_id": approval["run_id"],
            "message": "Approval is still pending",
            "risk_level": approval["risk_level"],
            "tool": approval["tool"],
            "parameters": approval["input_params"],
        }

    if approval["status"] == ApprovalStatus.REJECTED.value:
        raise HTTPException(status_code=403, detail="Approval was rejected")

    if approval["status"] != ApprovalStatus.APPROVED.value:
        raise HTTPException(status_code=409, detail=f"Unsupported approval status: {approval['status']}")

    tool_name = approval["tool"]
    parameters = approval["input_params"]
    enforce_policy(tool_name, parameters)
    result = execute_tool(tool_name, parameters)
    write_audit_entry(
        action="approval.executed",
        metadata={"approval_id": approval_id, "tool": tool_name, "parameters": _safe_param_summary(parameters)},
    )

    return {
        "status": "completed",
        "approval_id": approval_id,
        "run_id": approval["run_id"],
        "tool": tool_name,
        "parameters": parameters,
        "result": result,
    }
