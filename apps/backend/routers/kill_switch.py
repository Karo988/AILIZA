from __future__ import annotations

from typing import Literal, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..kill_switch_state import instance as kill_switch

router = APIRouter(prefix="/admin/kill-switch", tags=["kill-switch"])


class KillSwitchStatus(BaseModel):
    global_enabled: bool
    providers: dict[str, bool]
    modules: dict[str, bool]
    capabilities: dict[str, bool]


class HaltRequest(BaseModel):
    level: Literal["global", "provider", "module", "capability"]
    name: Optional[str] = None


class ResumeRequest(BaseModel):
    level: Literal["global", "provider", "module", "capability"]
    name: Optional[str] = None


class OperationResponse(BaseModel):
    status: str


@router.get("/status", response_model=KillSwitchStatus)
def get_status() -> KillSwitchStatus:
    return KillSwitchStatus(
        global_enabled=kill_switch._global,
        providers=dict(kill_switch._providers),
        modules=dict(kill_switch._modules),
        capabilities=dict(kill_switch._capabilities),
    )


@router.post("/halt", response_model=OperationResponse)
def halt(payload: HaltRequest) -> OperationResponse:
    if payload.level == "global":
        kill_switch.halt_global()
    elif payload.level == "provider":
        _require_name(payload)
        kill_switch.halt_provider(payload.name)
    elif payload.level == "module":
        _require_name(payload)
        kill_switch.halt_module(payload.name)
    elif payload.level == "capability":
        _require_name(payload)
        kill_switch.halt_capability(payload.name)
    return OperationResponse(status="halted")


@router.post("/resume", response_model=OperationResponse)
def resume(payload: ResumeRequest) -> OperationResponse:
    if payload.level == "global":
        kill_switch.resume_global()
    elif payload.level == "provider":
        _require_name(payload)
        kill_switch.resume(provider=payload.name)
    elif payload.level == "module":
        _require_name(payload)
        kill_switch.resume(module=payload.name)
    elif payload.level == "capability":
        _require_name(payload)
        kill_switch.resume(capability=payload.name)
    return OperationResponse(status="resumed")


def _require_name(payload: HaltRequest | ResumeRequest) -> None:
    if not payload.name:
        raise HTTPException(status_code=422, detail=f"name is required for level '{payload.level}'")
