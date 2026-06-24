from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, field_validator

from ..memory import MemoryEntry, MemoryPurpose, VisibilityLevel
from ..memory.sqlite_store import SqliteMemoryStore

router = APIRouter(prefix="/memory", tags=["memory"])

_store: SqliteMemoryStore | None = None


def get_store() -> SqliteMemoryStore:
    global _store
    if _store is None:
        _store = SqliteMemoryStore()
    return _store


class MemoryEntryCreate(BaseModel):
    purpose: MemoryPurpose
    content_hash: str
    visibility: VisibilityLevel
    role_required: str
    retention_until: datetime
    sensitive: bool = True

    @field_validator("retention_until")
    @classmethod
    def must_be_future(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            v = v.replace(tzinfo=timezone.utc)
        if v <= datetime.now(timezone.utc):
            raise ValueError("retention_until muss in der Zukunft liegen")
        return v


class MemoryEntryResponse(BaseModel):
    id: str
    purpose: MemoryPurpose
    content_hash: str
    visibility: VisibilityLevel
    role_required: str
    retention_until: datetime
    created_at: datetime
    deactivated_at: Optional[datetime]
    sensitive: bool


class DeactivateResponse(BaseModel):
    id: str
    status: str


class PurgeResponse(BaseModel):
    purged: int


def _to_response(entry: MemoryEntry) -> MemoryEntryResponse:
    return MemoryEntryResponse(
        id=entry.id,
        purpose=entry.purpose,
        content_hash=entry.content_hash,
        visibility=entry.visibility,
        role_required=entry.role_required,
        retention_until=entry.retention_until,
        created_at=entry.created_at,
        deactivated_at=entry.deactivated_at,
        sensitive=entry.sensitive,
    )


@router.post("", status_code=201, response_model=MemoryEntryResponse)
def create_entry(payload: MemoryEntryCreate) -> MemoryEntryResponse:
    entry = MemoryEntry(
        purpose=payload.purpose,
        content_hash=payload.content_hash,
        visibility=payload.visibility,
        role_required=payload.role_required,
        retention_until=payload.retention_until,
        sensitive=payload.sensitive,
    )
    get_store().add(entry)
    return _to_response(entry)


@router.get("", response_model=list[MemoryEntryResponse])
def list_entries() -> list[MemoryEntryResponse]:
    return [_to_response(e) for e in get_store().list_active()]


@router.get("/{entry_id}", response_model=MemoryEntryResponse)
def get_entry(entry_id: str) -> MemoryEntryResponse:
    entry = get_store().get(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="Memory entry not found")
    return _to_response(entry)


@router.delete("/{entry_id}", status_code=200, response_model=DeactivateResponse)
def deactivate_entry(entry_id: str) -> DeactivateResponse:
    ok = get_store().deactivate(entry_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Memory entry not found or already deactivated")
    return DeactivateResponse(id=entry_id, status="deactivated")


@router.post("/purge", status_code=200, response_model=PurgeResponse)
def purge_expired() -> PurgeResponse:
    count = get_store().purge_expired()
    return PurgeResponse(purged=count)
