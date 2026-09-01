from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..auth.rbac import Role, TokenData, require_role
from ..component_system import (
    BudgetExceeded, ComponentDecisionError, activate_component, approve_component,
    board_entries, configure_organization_mode, disable_component, set_budget_policy,
)

router = APIRouter(prefix="/admin/components", tags=["components"])


def _run(operation, **kwargs):
    try:
        return operation(**kwargs)
    except (ComponentDecisionError, BudgetExceeded) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


class ModePayload(BaseModel):
    mode: str


class ApprovalPayload(BaseModel):
    approval_mode: str
    task_package: str = Field(min_length=1, max_length=128)
    purpose: str = Field(min_length=1, max_length=500)
    allowed_data_classes: list[str]
    cost_limit: float = Field(gt=0)
    reason: str = Field(min_length=20, max_length=1000)
    totp_code: str | None = None
    max_records: int | None = Field(default=None, gt=0)
    validity_days: int | None = Field(default=None, ge=1, le=90)


class ActivationPayload(BaseModel):
    fallback_candidate_id: int | None = None


class DisablePayload(BaseModel):
    reason: str = Field(min_length=10, max_length=1000)


class BudgetPayload(BaseModel):
    task_package: str
    hard_limit: float = Field(gt=0)
    warning_threshold: float = Field(ge=0)
    period_start: datetime
    period_end: datetime
    currency: str = "EUR"


@router.get("/board")
def get_board(task_package: str, data_class: list[str] | None = None,
              token: TokenData = Depends(require_role(Role.USER))) -> dict[str, Any]:
    board = board_entries(tenant_id=token.tenant_id,
                          data_classes=data_class or ["public"],
                          task_package=task_package)
    # Anbieter-, Vertrags- und Freigabeentscheidungen sind keine Beschäftigtenansicht.
    if token.role not in {"admin", "manager", "dsb", "audit_viewer"}:
        return {"recommended": [], "active": board["active"], "blocked": []}
    return board


@router.post("/organization-mode")
def set_mode(payload: ModePayload,
             token: TokenData = Depends(require_role(Role.USER))) -> dict[str, Any]:
    return _run(configure_organization_mode, actor=token, mode=payload.mode)


@router.post("/{candidate_id}/approve-trial")
def approve_trial(candidate_id: int, payload: ApprovalPayload,
                  token: TokenData = Depends(require_role(Role.USER))) -> dict[str, Any]:
    return _run(approve_component, candidate_id=candidate_id, actor=token,
                approval_kind="trial", **payload.model_dump())


@router.post("/{candidate_id}/approve-full")
def approve_full(candidate_id: int, payload: ApprovalPayload,
                 token: TokenData = Depends(require_role(Role.USER))) -> dict[str, Any]:
    return _run(approve_component, candidate_id=candidate_id, actor=token,
                approval_kind="full", **payload.model_dump())


@router.post("/approvals/{approval_id}/activate")
def activate(approval_id: int, payload: ActivationPayload,
             token: TokenData = Depends(require_role(Role.USER))) -> dict[str, Any]:
    return _run(activate_component, approval_id=approval_id, actor=token,
                fallback_candidate_id=payload.fallback_candidate_id)


@router.post("/activations/{activation_id}/disable")
def disable(activation_id: int, payload: DisablePayload,
            token: TokenData = Depends(require_role(Role.USER))) -> dict[str, Any]:
    return _run(disable_component, activation_id=activation_id,
                actor=token, reason=payload.reason)


@router.post("/budgets")
def budget(payload: BudgetPayload,
           token: TokenData = Depends(require_role(Role.USER))) -> dict[str, Any]:
    return _run(set_budget_policy, actor=token, **payload.model_dump())
