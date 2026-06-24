from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from ..audit.vault import AuditVault
from ..auth import require_operator

router = APIRouter(prefix="/audit/vault", tags=["vault"])

_vault: AuditVault | None = None


def get_vault() -> AuditVault:
    global _vault
    if _vault is None:
        _vault = AuditVault()
    return _vault


class VaultEntryResponse(BaseModel):
    sequence: int
    event_type: str
    timestamp_iso: str
    actor_id: str
    previous_hash: str
    entry_hash: str


class VaultStatsResponse(BaseModel):
    total_entries: int
    chain_intact: bool
    first_defect_at_sequence: Optional[int]


class VaultVerifyResponse(BaseModel):
    intact: bool
    first_defect_at_sequence: Optional[int]


@router.get("/export", response_model=list[VaultEntryResponse])
def export_vault(limit: int = Query(default=1000, ge=1, le=10000), _role=Depends(require_operator)) -> list[VaultEntryResponse]:
    entries = get_vault().get_entries(limit=limit)
    return [VaultEntryResponse(**e.to_dict()) for e in entries]


@router.get("/stats", response_model=VaultStatsResponse)
def vault_stats(_role=Depends(require_operator)) -> VaultStatsResponse:
    s = get_vault().stats()
    return VaultStatsResponse(**s)


@router.get("/verify", response_model=VaultVerifyResponse)
def verify_vault(_role=Depends(require_operator)) -> VaultVerifyResponse:
    intact, defect_at = get_vault().verify_chain()
    return VaultVerifyResponse(intact=intact, first_defect_at_sequence=defect_at)
